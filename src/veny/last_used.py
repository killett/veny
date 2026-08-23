"""The one record veny keeps between runs: which environment last ran this script."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Final

import emmykit as ek

from . import state


def is_virtualenv() -> bool:
    """Check if currently running in a virtual environment."""
    return sys.prefix != sys.base_prefix


def active_virtualenv_dir() -> Path:
    """Return the virtual environment this process is running inside.

    is_virtualenv() answers *whether*; this answers *which*. VIRTUAL_ENV is
    what an activate script exports and is the user's own statement of which
    environment they meant; sys.prefix is the fallback for an environment
    entered by running its interpreter directly, where no activation happened.

    Returns:
        The environment's root directory. Meaningful only when
        is_virtualenv() is true.
    """
    declared = os.environ.get("VIRTUAL_ENV")
    if declared:
        return ek.ensure_path(declared)
    return Path(sys.prefix)


RECORD_SUFFIX: Final[str] = "-last-used.json"


def record_path(script_dir: Path, python_script: Path, my_name: str) -> Path:
    """Where this script's last-used record lives.

    One fixed file per script, not one per run: veny used to leave a
    timestamped JSON in the user's directory on every successful run and then
    glob, regex and sort them to find the newest. The name still starts with
    a dot and still contains "-{my_name}-", which is what --blank-slate's
    filter matches on.

    Args:
        script_dir:    The directory the script lives in.
        python_script: The script the record belongs to.
        my_name:       The program's own name, as it appears in the filename.

    Returns:
        The record's path. Says nothing about whether it exists.
    """
    return script_dir / f".{python_script.name}-{my_name}{RECORD_SUFFIX}"


def save(
    record: state.LastUsed,
    *,
    script_dir: Path,
    python_script: Path,
    my_name: str,
) -> Path:
    """Write this run's record, replacing any earlier one for the same script.

    Args:
        record:        What to remember: the environment and its interpreter.
        script_dir:    The directory the script lives in.
        python_script: The script the record belongs to.
        my_name:       The program's own name, for the filename.

    Returns:
        The path written.
    """
    path = record_path(script_dir, python_script, my_name)
    payload = {
        "venv_dir": os.fspath(record.venv_dir),
        "venv_python": os.fspath(record.venv_python),
        "timestamp": record.timestamp,
    }
    path.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")
    return path


def load(
    *,
    script_dir: Path,
    python_script: Path,
    my_name: str,
    rawlog: bool,
) -> state.LastUsed | None:
    """Read this script's last-used record, or None if there is not a usable one.

    Every degraded input -- absent, unreadable, not JSON, not an object,
    missing either path -- is "no record", never an exception: this runs on
    the first line of a user's ordinary run, and the cost of no record is one
    cache scan.

    Records written before phase 4b are a different format under a different
    filename and are ignored by construction: this reads one named file and
    never globs. (User ruling, 2026-08-21.)

    Args:
        script_dir:    The directory the script lives in.
        python_script: The script whose record is wanted.
        my_name:       The program's own name, for the filename.
        rawlog:        True suppresses veny's own commentary.

    Returns:
        The record, or None.
    """
    path = record_path(script_dir, python_script, my_name)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if not rawlog:
            logging.info("No usable last-used record for %s.", os.fspath(python_script))
        return None
    if not isinstance(payload, dict):
        if not rawlog:
            logging.info("Last-used record %s is not an object.", os.fspath(path))
        return None
    venv_dir = payload.get("venv_dir")
    venv_python = payload.get("venv_python")
    if not isinstance(venv_dir, str) or not isinstance(venv_python, str):
        if not rawlog:
            logging.info("Last-used record %s names no environment.", os.fspath(path))
        return None
    if not venv_dir or not venv_python:
        if not rawlog:
            logging.info("Last-used record %s names an empty path.", os.fspath(path))
        return None
    timestamp = payload.get("timestamp")
    return state.LastUsed(
        venv_dir=ek.ensure_path(venv_dir),
        venv_python=ek.ensure_path(venv_python),
        timestamp=timestamp if isinstance(timestamp, str) else "",
    )


def load_venv_python(
    *,
    script_dir: Path,
    python_script: Path,
    my_name: str,
    rawlog: bool,
) -> Path | None:
    """The interpreter the last successful run used, if it still exists.

    Args:
        script_dir:    The directory the script lives in.
        python_script: The script whose record is wanted.
        my_name:       The program's own name, for the filename.
        rawlog:        True suppresses veny's own commentary.

    Returns:
        The recorded interpreter, or None when there is no record or the
        interpreter it names is gone.
    """
    record = load(
        script_dir=script_dir,
        python_script=python_script,
        my_name=my_name,
        rawlog=rawlog,
    )
    if record is None:
        if not rawlog:
            logging.info("No last used record found, so no venv_python to return.")
        return None
    if not ek.safe_is_file(record.venv_python):
        if not rawlog:
            logging.warning(
                "Last used venv_python %s is no longer valid.",
                os.fspath(record.venv_python),
            )
        return None
    if not rawlog:
        logging.info("Last used venv_python found: %s", os.fspath(record.venv_python))
    return record.venv_python
