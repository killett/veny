"""Naming, manifests, and matching for veny's cached virtual environments.

A cached virtual environment is described by two artifacts. Its folder name is
a cheap, human-readable prefilter, and ``veny_manifest.json`` inside it is the
authority on what it holds and which interpreter it was built for.

This module is pure and standard-library only. It imports nothing from veny,
univ_defs, alias_index, or pypi_client, so it can be unit tested without
building a virtual environment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_NAMED_PACKAGES: int = 5

_NORMALIZE_RE = re.compile(r"[-_.]+")


def normalize_pip_name(name: str) -> str:
    """Reduce a pip project name to its PEP 503 normalized form.

    This duplicates alias_index.normalize_pip_name deliberately: this module may
    not import alias_index, because veny.py imports both and the dependency must
    stay one-way. The two implementations must be kept identical -- a second,
    silent implementation of a comparison rule is exactly the kind of thing that
    drifts apart.

    Args:
        name: A pip project name.

    Returns:
        The normalized form: lowercase, with runs of "-", "_", and "." collapsed
        to a single "-".
    """
    return _NORMALIZE_RE.sub("-", name).lower()


@dataclass(frozen=True)
class FolderName:
    """The fields recovered from a cached venv's folder name.

    Attributes:
        venv_name:       The configured venv name prefix.
        interpreter_tag: The "major.minor" tag the venv was built for.
        timestamp:       The creation stamp, "YYYYMMDD-HHMMSS".
        packages:        Normalized pip names listed in the name.
        unnamed_count:   How many further packages the name summarised away.
    """

    venv_name: str
    interpreter_tag: str
    timestamp: str
    packages: frozenset[str]
    unnamed_count: int


def build_folder_name(
    venv_name: str, interpreter_tag: str, timestamp: str, pip_names: list[str]
) -> str:
    """Build the folder name for a virtual environment.

    Package names are normalized first, so each contains only [a-z0-9-], and are
    joined with "_", which therefore cannot occur inside a name. That is what
    lets a hyphenated pip name survive a round trip through the name.

    Args:
        venv_name:       The configured venv name prefix. Must not contain "-".
        interpreter_tag: The "major.minor" tag of the building interpreter.
        timestamp:       The creation stamp, "YYYYMMDD-HHMMSS".
        pip_names:       The pip names the venv is being built for.

    Returns:
        The folder name, without any "failed-" prefix.
    """
    normalized = sorted({normalize_pip_name(name) for name in pip_names})
    listed = normalized[:MAX_NAMED_PACKAGES]
    remainder = len(normalized) - len(listed)
    tail = f"_and_{remainder}_more" if remainder else ""
    return f"{venv_name}-py{interpreter_tag}-{timestamp}-{'_'.join(listed)}{tail}"


def parse_folder_name(name: str) -> FolderName | None:
    """Recover the fields of a folder name built by build_folder_name.

    Args:
        name: A directory name, without any "failed-" prefix.

    Returns:
        The parsed fields, or None if the name is not one of ours. A name that
        does not parse is skipped, never repaired: an unrelated directory in
        the cache directory must not be mistaken for a virtual environment.
    """
    parts = name.split("-", 4)
    if len(parts) != 5:
        return None
    venv_name, interpreter_field, date, time, package_section = parts
    if not interpreter_field.startswith("py") or len(interpreter_field) == 2:
        return None
    if not (len(date) == 8 and date.isdigit() and len(time) == 6 and time.isdigit()):
        return None
    if not package_section:
        return None
    items = package_section.split("_")
    unnamed_count = 0
    if len(items) > 3 and items[-3] == "and" and items[-2].isdigit() and items[-1] == "more":
        unnamed_count = int(items[-2])
        items = items[:-3]
    if not items or any(not item for item in items):
        return None
    return FolderName(
        venv_name=venv_name,
        interpreter_tag=interpreter_field[2:],
        timestamp=f"{date}-{time}",
        packages=frozenset(items),
        unnamed_count=unnamed_count,
    )
