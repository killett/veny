"""The one record veny keeps between runs: which environment last ran this script."""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import sys
from pathlib import Path
from typing import cast

import emmykit as ek


def is_virtualenv() -> bool:
    """Check if currently running in a virtual environment."""
    return sys.prefix != sys.base_prefix


def load_last_used_options(
    options: ek.Options,
    *,
    script_dir: Path,
    python_script: Path,
    pathlibcutoff: str,
    rawlog: bool,
) -> ek.Options | None:
    """Look for the most recent JSON file in the script directory that matches the script name and load it into a new Options object. Ignore any JSON files created before the options.pathlibcutoff timestamp."""
    pattern = re.compile(r"last-used-on-(\d{8}-\d{6})")
    json_files = [
        f
        for f in script_dir.iterdir()
        if f.name.startswith("." + python_script.name)
        and f.suffix.casefold() == ".json"
        and (m := pattern.search(f.name))  # extract timestamp
        and m.group(1) >= pathlibcutoff  # compare as strings
    ]
    if not json_files:
        if not rawlog:
            logging.info("No previous JSON files found in the script directory.")
        return None
    if len(json_files) > 1:
        json_files.sort(
            key=lambda x: dt.datetime.strptime(
                x.name.split("-")[-2] + x.name.split("-")[-1].replace(".json", ""),
                "%Y%m%d%H%M%S",
            ),
            reverse=True,
        )
    return ek.load_options_from_json(options, script_dir / json_files[0])


def load_last_used_venv_python(
    options: ek.Options,
    *,
    script_dir: Path,
    python_script: Path,
    pathlibcutoff: str,
    rawlog: bool,
) -> Path | None:
    """Look for the most recent JSON file in the script directory that matches the script name and return the venv_python from it.

    Args:
        options: The template ek.Options object to fill in from the JSON.
        script_dir: The directory to scan for last-used JSON files.
        python_script: The script whose last-used record is being sought.
        pathlibcutoff: Ignore JSON files timestamped before this cutoff.
        rawlog: Suppress informational logging when True.

    Returns:
        The Path object of the last used venv_python, or None if not found or invalid.
    """
    last_used_options = load_last_used_options(
        options,
        script_dir=script_dir,
        python_script=python_script,
        pathlibcutoff=pathlibcutoff,
        rawlog=rawlog,
    )
    if not last_used_options:
        if not rawlog:
            logging.info("No last used options found, so no venv_python to return.")
        return None
    elif not hasattr(last_used_options, "venv_python"):
        if not rawlog:
            logging.info("Last used options do not have a venv_python attribute.")
        return None
    elif last_used_options.venv_python is None:
        if not rawlog:
            logging.info("Last used venv_python is None.")
        return None
    elif not ek.safe_is_file(last_used_options.venv_python):
        if not rawlog:
            logging.warning(
                "Last used venv_python %s is no longer valid.",
                os.fspath(last_used_options.venv_python),
            )
        return None
    else:
        if not rawlog:
            logging.info(
                "Last used venv_python found: %s",
                os.fspath(last_used_options.venv_python),
            )
        return cast(Path, last_used_options.venv_python)
