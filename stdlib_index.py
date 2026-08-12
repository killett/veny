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

import sys
from dataclasses import dataclass
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
