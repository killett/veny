"""Naming, manifests, and matching for veny's cached virtual environments.

A cached virtual environment is described by two artifacts. Its folder name is
a cheap, human-readable prefilter, and ``veny_manifest.json`` inside it is the
authority on what it holds and which interpreter it was built for.

This module is pure and standard-library only. It imports nothing from veny,
univ_defs, alias_index, or pypi_client, so it can be unit tested without
building a virtual environment.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

MAX_NAMED_PACKAGES: int = 5

MANIFEST_FILENAME: str = "veny_manifest.json"
SCHEMA_VERSION: int = 1

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


@dataclass(frozen=True)
class PackageRecord:
    """One package as a built virtual environment holds it.

    Attributes:
        import_name:       The name as written in the user's source.
        pip_name:          The name pip received, unnormalized.
        installed_version: The version the venv reports, or None if unknown.
        requested_spec:    The --reqs spec that asked for it, or None.
    """

    import_name: str
    pip_name: str
    installed_version: str | None
    requested_spec: str | None


@dataclass(frozen=True)
class Manifest:
    """What a cached virtual environment is.

    Attributes:
        schema_version:   The format version, checked on read.
        created:          The creation stamp, "YYYYMMDD-HHMMSS".
        veny_version:     veny's version when the venv was built. Diagnostic
                          only; never matched on.
        interpreter_tag:  The "major.minor" tag the venv was built for.
        interpreter_path: The interpreter that built it.
        packages:         What it holds, in the order written.
    """

    schema_version: int
    created: str
    veny_version: str
    interpreter_tag: str
    interpreter_path: str
    packages: tuple[PackageRecord, ...]


def write_manifest(venv_dir: str | os.PathLike[str], manifest: Manifest) -> bool:
    """Write a manifest into a virtual environment directory.

    Best effort by design: a venv whose manifest could not be written is still
    usable for this run and merely absent from the cache next time.

    Args:
        venv_dir: The virtual environment directory.
        manifest: What to record.

    Returns:
        True if the file was written.
    """
    path = Path(venv_dir) / MANIFEST_FILENAME
    payload = {
        "schema_version": manifest.schema_version,
        "created": manifest.created,
        "veny_version": manifest.veny_version,
        "interpreter_tag": manifest.interpreter_tag,
        "interpreter_path": manifest.interpreter_path,
        "packages": [
            {
                "import_name": record.import_name,
                "pip_name": record.pip_name,
                "installed_version": record.installed_version,
                "requested_spec": record.requested_spec,
            }
            for record in manifest.packages
        ],
    }
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
    except OSError as exc:
        logging.warning("Could not write %s (%s); this venv will not be reused.", path, exc)
        return False
    return True


def read_manifest(venv_dir: str | os.PathLike[str]) -> Manifest | None:
    """Read the manifest of a cached virtual environment.

    Every failure returns None rather than raising. A cached venv is an
    optimization, so an unreadable one costs a rebuild -- unlike the alias
    override file, which is fatal because it carries the user's explicit intent.

    Args:
        venv_dir: The virtual environment directory.

    Returns:
        The manifest, or None if it is absent, unreadable, malformed, or of a
        schema version this build does not understand.
    """
    path = Path(venv_dir) / MANIFEST_FILENAME
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logging.info("No usable manifest at %s (%s).", path, exc)
        return None
    try:
        if payload["schema_version"] != SCHEMA_VERSION:
            logging.info(
                "Ignoring %s: schema version %s, this veny understands %d.",
                path,
                payload["schema_version"],
                SCHEMA_VERSION,
            )
            return None
        packages = tuple(
            PackageRecord(
                import_name=str(entry["import_name"]),
                pip_name=str(entry["pip_name"]),
                installed_version=entry["installed_version"],
                requested_spec=entry["requested_spec"],
            )
            for entry in payload["packages"]
        )
        return Manifest(
            schema_version=SCHEMA_VERSION,
            created=str(payload["created"]),
            veny_version=str(payload["veny_version"]),
            interpreter_tag=str(payload["interpreter_tag"]),
            interpreter_path=str(payload["interpreter_path"]),
            packages=packages,
        )
    except (KeyError, TypeError, ValueError) as exc:
        logging.info("Ignoring %s: it is not a manifest this veny can read (%s).", path, exc)
        return None
