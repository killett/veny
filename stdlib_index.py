#!/usr/bin/env python3
"""Derive the standard-library module names of a given Python interpreter.

veny needs to know whether an import must be installed with pip. That is a
property of the interpreter which will run the user's script, so this module
asks an interpreter instead of carrying a hardcoded list. See
docs/superpowers/specs/2026-08-12-stdlib-index-design.md for the rationale.

This module deliberately imports nothing from veny or univ_defs, so it can be
tested on its own and so the dependency direction stays one-way.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

SOURCE_RUNNING: Final[str] = "running"
SOURCE_PROBE: Final[str] = "probe"
SOURCE_DEGRADED: Final[str] = "degraded"


@dataclass(frozen=True)
class StdlibIndex:
    """The standard-library module names of one Python interpreter.

    Attributes:
        names:          Top-level standard-library module names.
        python_version: The (major, minor) version the names came from.
        source:         One of SOURCE_RUNNING, SOURCE_PROBE, SOURCE_DEGRADED.
    """

    names: frozenset[str]
    python_version: tuple[int, int]
    source: str

    def __contains__(self, import_name: object) -> bool:
        """Return True if an import name resolves to the standard library.

        Only the first dotted component matters: "xml.etree.ElementTree" is
        standard library because "xml" is.

        Args:
            import_name: The import name as written in the source file.

        Returns:
            True if the name belongs to this interpreter's standard library.
        """
        if not isinstance(import_name, str) or not import_name:
            return False
        return import_name.partition(".")[0] in self.names


def for_running_interpreter() -> StdlibIndex:
    """Build an index from the interpreter that is running veny itself.

    Returns:
        A StdlibIndex tagged with SOURCE_RUNNING.
    """
    return StdlibIndex(
        names=frozenset(sys.stdlib_module_names),
        python_version=(sys.version_info.major, sys.version_info.minor),
        source=SOURCE_RUNNING,
    )


_PROBE_TIMEOUT: Final[float] = 10.0

_PROBE_CODE: Final[str] = (
    "import sys, json; "
    "print(json.dumps({'version': list(sys.version_info[:2]), "
    "'names': sorted(sys.stdlib_module_names)}))"
)


def _degraded() -> StdlibIndex:
    """Build a usable index from the running interpreter, tagged as degraded.

    Returns:
        A StdlibIndex with the running interpreter's names and SOURCE_DEGRADED.
    """
    running = for_running_interpreter()
    return StdlibIndex(
        names=running.names,
        python_version=running.python_version,
        source=SOURCE_DEGRADED,
    )


@lru_cache(maxsize=8)
def for_interpreter(
    python: str | os.PathLike[str], timeout: float = _PROBE_TIMEOUT
) -> StdlibIndex:
    """Probe another interpreter for its standard-library module names.

    Any failure -- missing executable, timeout, non-zero exit, unparseable
    output -- degrades to the running interpreter with a warning rather than
    raising, because veny's job is to keep the user's script running.

    Args:
        python:  Path or command name of the interpreter to probe.
        timeout: Seconds to wait for the probe before giving up.

    Returns:
        A StdlibIndex tagged SOURCE_PROBE on success, SOURCE_DEGRADED otherwise.
    """
    command = [os.fspath(python), "-c", _PROBE_CODE]
    try:
        result = subprocess.run(  # noqa: S603
            command, capture_output=True, text=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logging.warning(
            "Could not run %s to list its standard library (%s); "
            "using this interpreter's standard library instead.",
            python,
            exc,
        )
        return _degraded()
    if result.returncode != 0:
        logging.warning(
            "%s exited with %d while listing its standard library (%s); "
            "using this interpreter's standard library instead.",
            python,
            result.returncode,
            result.stderr.strip(),
        )
        return _degraded()
    try:
        payload = json.loads(result.stdout)
        names = frozenset(payload["names"])
        major, minor = payload["version"]
    except (ValueError, KeyError, TypeError) as exc:
        logging.warning(
            "Could not read the standard library list from %s (%s); "
            "using this interpreter's standard library instead.",
            python,
            exc,
        )
        return _degraded()
    return StdlibIndex(
        names=names, python_version=(int(major), int(minor)), source=SOURCE_PROBE
    )


def _is_running_interpreter(python: str | os.PathLike[str]) -> bool:
    """Return True if a path or command name refers to the interpreter running veny.

    Args:
        python: Path or command name such as "python3.12" or "/usr/bin/python3".

    Returns:
        True if it resolves to the same file as sys.executable.
    """
    located = shutil.which(os.fspath(python))
    if located is None:
        return False
    return os.path.realpath(located) == os.path.realpath(sys.executable)


def resolve(python: str | os.PathLike[str] | None) -> StdlibIndex:
    """Build the standard-library index for the interpreter that will run the script.

    Args:
        python: The target interpreter, or None if none has been chosen yet.

    Returns:
        The running interpreter's index when the target is absent or is the
        running interpreter, otherwise the probed target's index.
    """
    if python is None or _is_running_interpreter(python):
        return for_running_interpreter()
    return for_interpreter(os.fspath(python))
