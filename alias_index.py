#!/usr/bin/env python3
"""Resolve an import name to the pip package name that provides it.

veny needs to know that ``import cv2`` means ``pip install opencv-python``.
That mapping is a property of PyPI, not of veny, so this module derives it
from evidence -- the target interpreter's installed distributions, PyPI wheel
metadata, a small curated seed, a user override file, and a cache of results
that were verified by actually installing and importing them. See
docs/superpowers/specs/2026-08-12-module-alias-resolver-design.md.

This module deliberately imports nothing from veny or univ_defs, so it can be
tested on its own and so the dependency direction stays one-way. It never
installs anything: it produces ranked candidates and veny verifies them.
"""

from __future__ import annotations

import enum
import io
import json
import logging
import os
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol


class Source(enum.IntEnum):
    """How a candidate pip name was obtained, ordered strongest evidence first.

    There is deliberately no member for unverified name heuristics. A generated
    name becomes a candidate only once wheel inspection confirms it provides the
    import name, at which point its source is PYPI_CONFIRMED. That keeps "never
    install an unverified guess" a structural property rather than a runtime check.
    """

    OVERRIDE = 0
    CACHE = 1
    INSTALLED = 2
    SEED = 3
    PYPI_CONFIRMED = 4


@dataclass(frozen=True)
class Candidate:
    """One possible pip package name for an import name.

    Attributes:
        pip_name:   The name to pass to pip.
        source:     Where the evidence came from.
        evidence:   Human-readable justification, shown in logs and reports.
        top_levels: Top-level names the wheel declares, when one was inspected.
    """

    pip_name: str
    source: Source
    evidence: str
    top_levels: frozenset[str] | None = None


@dataclass(frozen=True)
class Resolution:
    """The ranked candidates for one import name.

    Attributes:
        import_name: The import name as written in the user's source.
        candidates:  Candidates, strongest evidence first. May be empty.
    """

    import_name: str
    candidates: tuple[Candidate, ...]


def rank(candidates: Iterable[Candidate]) -> tuple[Candidate, ...]:
    """Deduplicate candidates by pip name and order them deterministically.

    A pip name found by several tiers is kept once, at its strongest evidence.
    Ordering is (source, pip_name) so that identical inputs always produce an
    identical order, which keeps runs reproducible and logs comparable.

    Args:
        candidates: Candidates in any order, possibly with repeated pip names.

    Returns:
        Ranked, deduplicated candidates.
    """
    strongest: dict[str, Candidate] = {}
    for candidate in candidates:
        existing = strongest.get(candidate.pip_name)
        if existing is None or candidate.source < existing.source:
            strongest[candidate.pip_name] = candidate
    return tuple(sorted(strongest.values(), key=lambda c: (int(c.source), c.pip_name)))


# Import names whose pip name veny cannot derive, kept because they are worth
# resolving with no network and an empty cache. This is a short list of known
# exceptions, NOT a mapping table: anything not here is derived at run time.
# Curation is by correctness and reachability, not historical provenance.
# Exclusions: jnp→jax.numpy dropped (pip install jax.numpy fails);
# mypy.api→mypy dropped (dotted key unreachable after first-component normalization).
SEED: Final[dict[str, str]] = {
    "osgeo": "gdal",
    "ffmpeg": "ffmpeg-python",
    "cv2": "opencv-python",
    "netCDF4": "netcdf4",
    "skill_metrics": "SkillMetrics",
    "bugbear": "flake8-bugbear",
    "whisper": "openai-whisper",
    "speedtest": "speedtest-cli",
    "yaml": "PyYAML",
    "zmq": "pyzmq",
}

OVERRIDES_FILENAME: Final[str] = "module_aliases.toml"
CACHE_FILENAME: Final[str] = "module_aliases_cache.json"

_REJECTION_KINDS: Final[frozenset[str]] = frozenset({"import_failed", "install_failed"})


class AliasOverrideError(Exception):
    """Raised when the user's alias override file cannot be read.

    This is deliberately fatal. Falling back to derived answers would resolve
    names contrary to what the user explicitly wrote.
    """


def load_overrides(path: Path) -> dict[str, str]:
    """Read the user's import-name-to-pip-name overrides.

    Args:
        path: Path to the TOML override file. Absence is not an error.

    Returns:
        The mapping under the file's [aliases] table, empty if the file is absent.

    Raises:
        AliasOverrideError: If the file exists but cannot be parsed, or its
            [aliases] table is not a table of strings.
    """
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AliasOverrideError(
            f"Could not read alias overrides from {path}: {exc}"
        ) from exc
    aliases = payload.get("aliases", {})
    if not isinstance(aliases, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in aliases.items()
    ):
        raise AliasOverrideError(
            f"The [aliases] table in {path} must map import names to pip names, as strings."
        )
    return dict(aliases)


@dataclass
class AliasCache:
    """Verified import-name-to-pip-name results for one interpreter version.

    Only results that actually installed and imported are stored, so a hit is a
    fact rather than a guess. The file is safe to delete at any time; the only
    cost is a slower next run.

    Attributes:
        path:            Where the cache is stored.
        interpreter_tag: Version tag entries must match to be used, e.g. "3.12".
        entries:         import name -> {"pip_name": str, "python": str}.
        rejections:      import name -> {pip names that installed but did not import}.
    """

    path: Path
    interpreter_tag: str
    entries: dict[str, dict[str, str]]
    rejections: dict[str, list[str]]

    @classmethod
    def load(cls, path: Path, interpreter_tag: str) -> AliasCache:
        """Read the cache, quarantining it if it cannot be parsed.

        Args:
            path:            Where the cache is stored.
            interpreter_tag: Version tag of the interpreter being resolved for.

        Returns:
            The cache, empty if the file was absent or unreadable.
        """
        if not path.is_file():
            return cls(
                path=path, interpreter_tag=interpreter_tag, entries={}, rejections={}
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Cache payload must be a dict")
            if not isinstance(payload.get("entries"), dict):
                raise ValueError("Cache entries must be a dict")
            for key, value in payload["entries"].items():
                if not isinstance(key, str):
                    raise ValueError("Entry keys must be strings")
                if not isinstance(value, dict):
                    raise ValueError("Entry values must be dicts")
                if not isinstance(value.get("pip_name"), str):
                    raise ValueError("Entry pip_name must be a string")
                if not isinstance(value.get("python"), str):
                    raise ValueError("Entry python version must be a string")
            rejections_data = payload.get("rejections", {})
            if not isinstance(rejections_data, dict):
                raise ValueError("Cache rejections must be a dict")
            for key, value in rejections_data.items():
                if not isinstance(key, str):
                    raise ValueError("Rejection keys must be strings")
                if not isinstance(value, list) or not all(
                    isinstance(v, str) for v in value
                ):
                    raise ValueError("Rejection values must be lists of strings")
            entries = dict(payload["entries"])
            rejections = {key: list(value) for key, value in rejections_data.items()}
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            quarantine = path.with_name(
                f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"
            )
            logging.warning(
                "Could not read the alias cache %s (%s); moving it to %s and starting empty.",
                path,
                exc,
                quarantine,
            )
            try:
                path.rename(quarantine)
            except OSError as rename_exc:  # pragma: no cover - filesystem-specific
                logging.warning("Could not quarantine %s (%s).", path, rename_exc)
            return cls(
                path=path, interpreter_tag=interpreter_tag, entries={}, rejections={}
            )
        return cls(
            path=path,
            interpreter_tag=interpreter_tag,
            entries=entries,
            rejections=rejections,
        )

    def get(self, import_name: str) -> str | None:
        """Return the verified pip name for an import name, if one applies.

        Args:
            import_name: The import name to look up.

        Returns:
            The pip name, or None when absent or recorded under a different
            interpreter version.
        """
        entry = self.entries.get(import_name)
        if entry is None or entry.get("python") != self.interpreter_tag:
            return None
        return entry["pip_name"]

    def rejected_names(self, import_name: str) -> frozenset[str]:
        """Return pip names already known to install without providing this import.

        Args:
            import_name: The import name being resolved.

        Returns:
            The rejected pip names, empty if none were recorded.
        """
        return frozenset(self.rejections.get(import_name, ()))

    def confirm(self, import_name: str, pip_name: str) -> None:
        """Record that pip_name installed and provided import_name, and save.

        Args:
            import_name: The import name that was satisfied.
            pip_name:    The pip package that satisfied it.
        """
        self.entries[import_name] = {
            "pip_name": pip_name,
            "python": self.interpreter_tag,
        }
        remaining = [
            name for name in self.rejections.get(import_name, []) if name != pip_name
        ]
        if remaining:
            self.rejections[import_name] = remaining
        else:
            self.rejections.pop(import_name, None)
        self._save()

    def reject(self, import_name: str, pip_name: str, kind: str) -> None:
        """Record a failed attempt, persisting only deterministic failures.

        An "installed but did not import" result is a fact about the package and
        is persisted. A failed install may be transient -- a network blip or an
        index outage -- so persisting it would permanently blacklist a package
        that is actually correct.

        Args:
            import_name: The import name being resolved.
            pip_name:    The candidate that failed.
            kind:        Either "import_failed" or "install_failed".

        Raises:
            ValueError: If kind is not a recognised rejection kind.
        """
        if kind not in _REJECTION_KINDS:
            raise ValueError(
                f"Unknown rejection kind {kind!r}; expected one of {sorted(_REJECTION_KINDS)}."
            )
        if kind == "install_failed":
            return
        recorded = self.rejections.setdefault(import_name, [])
        if pip_name not in recorded:
            recorded.append(pip_name)
        self._save()

    def _save(self) -> None:
        """Write the cache to disk, warning but not raising if that fails."""
        payload = {"entries": self.entries, "rejections": self.rejections}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
        except OSError as exc:
            logging.warning("Could not write the alias cache %s (%s).", self.path, exc)


_PROBE_TIMEOUT: Final[float] = 10.0

_PROBE_CODE: Final[str] = (
    "import sys, json; "
    "from importlib.metadata import packages_distributions; "
    "print(json.dumps({'version': list(sys.version_info[:2]), "
    "'packages': packages_distributions()}))"
)


def _running_tag() -> str:
    """Return the running interpreter's version tag.

    Returns:
        A tag such as "3.12".
    """
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def probe_interpreter(
    python: str | os.PathLike[str], timeout: float = _PROBE_TIMEOUT
) -> tuple[str, dict[str, list[str]]]:
    """Ask an interpreter for its version and which distributions provide which imports.

    importlib.metadata.packages_distributions() answers the reverse question
    exactly -- top-level import name to distribution names -- but only for
    distributions installed in that interpreter. Any failure degrades to an
    empty mapping with a warning, because a missing probe is absent information,
    not contradicted information.

    Args:
        python:  Path or command name of the interpreter to probe.
        timeout: Seconds to wait before giving up.

    Returns:
        The interpreter's version tag and its top-level-name to distribution
        mapping. On failure, the running interpreter's tag and an empty mapping.
    """
    command = [os.fspath(python), "-c", _PROBE_CODE]
    try:
        result = subprocess.run(  # noqa: S603
            command, capture_output=True, text=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logging.warning(
            "Could not run %s to list its installed distributions (%s); "
            "alias resolution will rely on other evidence.",
            python,
            exc,
        )
        return _running_tag(), {}
    if result.returncode != 0:
        logging.warning(
            "%s exited with %d while listing its installed distributions (%s); "
            "alias resolution will rely on other evidence.",
            python,
            result.returncode,
            result.stderr.strip(),
        )
        return _running_tag(), {}
    try:
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError("Probe payload must be a dict")
        if (
            not isinstance(payload.get("version"), (list, tuple))
            or len(payload.get("version", [])) != 2
        ):
            raise ValueError("Probe version must be a 2-element sequence")
        major, minor = payload["version"]
        major = int(major)
        minor = int(minor)

        if not isinstance(payload.get("packages"), dict):
            raise ValueError("Probe packages must be a dict")
        packages = {}
        for key, value in payload["packages"].items():
            if not isinstance(key, str):
                raise ValueError("Package keys must be strings")
            if not isinstance(value, list) or not all(
                isinstance(name, str) for name in value
            ):
                raise ValueError("Package values must be lists of strings")
            packages[key] = value
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        logging.warning(
            "Could not read the installed distribution list from %s (%s); "
            "alias resolution will rely on other evidence.",
            python,
            exc,
        )
        return _running_tag(), {}
    return f"{major}.{minor}", packages


PYPI_JSON_URL: Final[str] = "https://pypi.org/pypi/{name}/json"
MAX_WHEEL_BYTES: Final[int] = 5 * 1024 * 1024
_FIRST_WINDOW: Final[int] = 64 * 1024
_WIDE_WINDOW: Final[int] = 1024 * 1024
_CONNECT_TIMEOUT: Final[float] = 5.0
_READ_TIMEOUT: Final[float] = 10.0
_EXCLUDED_SUFFIXES: Final[tuple[str, ...]] = (".dist-info", ".data")


class FetchError(Exception):
    """Raised by a fetcher when a URL cannot be retrieved."""


class Fetcher(Protocol):
    """Minimal HTTP surface the PyPI client needs, so tests can inject a fake."""

    def get(
        self, url: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        """Retrieve a URL.

        Args:
            url:     The absolute URL to retrieve.
            headers: Request headers, such as Range.

        Returns:
            The status code, response headers, and body bytes.

        Raises:
            FetchError: If the URL cannot be retrieved.
        """
        ...


class UrllibFetcher:
    """A Fetcher backed by urllib, so veny needs no third-party HTTP library."""

    def get(
        self, url: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        """Retrieve a URL with a bounded timeout.

        Args:
            url:     The absolute URL to retrieve.
            headers: Request headers, such as Range.

        Returns:
            The status code, response headers, and body bytes.

        Raises:
            FetchError: On any network or protocol failure.
        """
        request = urllib.request.Request(url, headers=headers or {})  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=_READ_TIMEOUT) as response:  # noqa: S310
                return int(response.status), dict(response.headers), response.read()
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise FetchError(str(exc)) from exc


def _top_levels_from_names(member_names: Iterable[str]) -> frozenset[str]:
    """Reduce zip member paths to the top-level import names a wheel provides.

    Args:
        member_names: Archive member paths, as stored in the central directory.

    Returns:
        The top-level names, excluding packaging metadata directories.
    """
    found: set[str] = set()
    for member in member_names:
        head, _, tail = member.replace("\\", "/").partition("/")
        if (
            not head
            or head.startswith("__pycache__")
            or head.endswith(_EXCLUDED_SUFFIXES)
        ):
            continue
        if tail:
            found.add(head)
        elif head.endswith(".py"):
            found.add(head.removesuffix(".py"))
    return frozenset(found)


class PyPIClient:
    """Answers whether a PyPI project declares a given top-level import name.

    The answer comes from the wheel's zip central directory, which lists every
    member path and sits at the end of the file. A suffix Range request reads it
    without transferring the wheel body, so confirming a candidate costs one
    JSON request plus tens of kilobytes.
    """

    def __init__(self, fetcher: Fetcher | None = None) -> None:
        """Store the fetcher and start an empty per-project cache.

        Args:
            fetcher: HTTP surface to use. Defaults to UrllibFetcher.
        """
        self._fetcher: Fetcher = fetcher if fetcher is not None else UrllibFetcher()
        self._cache: dict[str, frozenset[str] | None] = {}

    def top_levels(self, name: str) -> frozenset[str] | None:
        """Return the top-level names the project's smallest wheel declares.

        Args:
            name: The PyPI project name.

        Returns:
            The declared top-level names, or None when the project does not
            exist, ships no wheel, or cannot be inspected within the size cap.
        """
        if name not in self._cache:
            self._cache[name] = self._inspect(name)
        return self._cache[name]

    def _inspect(self, name: str) -> frozenset[str] | None:
        """Fetch project metadata and read its smallest wheel's member listing.

        Args:
            name: The PyPI project name.

        Returns:
            The declared top-level names, or None if anything prevents inspection.
        """
        try:
            _, _, body = self._fetcher.get(PYPI_JSON_URL.format(name=name))
            payload = json.loads(body)
        except (FetchError, ValueError) as exc:
            logging.debug("No PyPI metadata for %s (%s).", name, exc)
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("urls"), list):
            logging.debug("Malformed PyPI metadata for %s.", name)
            return None
        wheels = []
        for entry in payload["urls"]:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("filename"), str)
                or not isinstance(entry.get("url"), str)
                or not isinstance(entry.get("size"), int)
            ):
                logging.debug("Malformed PyPI file entry for %s.", name)
                return None
            if entry["filename"].endswith(".whl"):
                wheels.append(entry)
        if not wheels:
            logging.debug(
                "Project %s ships no wheel, so its top-level names cannot be read.",
                name,
            )
            return None
        smallest = min(wheels, key=lambda entry: entry["size"])
        try:
            return self._read_member_names(smallest["url"], smallest["size"])
        except (FetchError, zipfile.BadZipFile) as exc:
            logging.debug("Could not read the wheel listing for %s (%s).", name, exc)
            return None

    def _read_member_names(self, url: str, size: int) -> frozenset[str] | None:
        """Read a remote wheel's member listing without downloading its body.

        Args:
            url:  Absolute URL of the wheel.
            size: Wheel size in bytes, as reported by PyPI.

        Returns:
            The top-level names, or None when the server refuses Range on a
            wheel larger than MAX_WHEEL_BYTES.

        Raises:
            FetchError: If the wheel cannot be retrieved.
        """
        for window in (_FIRST_WINDOW, _WIDE_WINDOW):
            status, _, chunk = self._fetcher.get(
                url, headers={"Range": f"bytes=-{window}"}
            )
            if status != 206:
                if size > MAX_WHEEL_BYTES:
                    logging.debug(
                        "Server ignored Range for %s and the wheel is %d bytes; abandoning it.",
                        url,
                        size,
                    )
                    return None
                return _top_levels_from_names(_names_from_zip_bytes(chunk))
            names = _names_from_tail(chunk)
            if names is not None:
                return _top_levels_from_names(names)
        logging.debug("Could not locate the central directory of %s.", url)
        return None


def _names_from_zip_bytes(blob: bytes) -> tuple[str, ...]:
    """List member names of a complete zip archive held in memory.

    Args:
        blob: The whole archive.

    Returns:
        Member names.
    """
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        return tuple(archive.namelist())


_EOCD_SIGNATURE: Final[bytes] = b"PK\x05\x06"
_CENTRAL_SIGNATURE: Final[bytes] = b"PK\x01\x02"


def _names_from_tail(tail: bytes) -> tuple[str, ...] | None:
    """Parse member names from a zip's trailing bytes.

    A zip's central directory lists every member path and ends immediately
    before the end-of-central-directory record, so the whole listing can be read
    from the tail alone and no member is ever decompressed.

    Args:
        tail: The trailing bytes of the archive.

    Returns:
        Member names, or None if the end-of-central-directory record is not in
        tail, or the directory it points at is not fully inside tail. Either way
        the caller should retry with a wider window.
    """
    marker = tail.rfind(_EOCD_SIGNATURE)
    if marker < 0:
        return None
    directory_size = int.from_bytes(tail[marker + 12 : marker + 16], "little")
    start = marker - directory_size
    if start < 0:
        return None
    names: list[str] = []
    cursor = start
    while tail[cursor : cursor + 4] == _CENTRAL_SIGNATURE:
        name_length = int.from_bytes(tail[cursor + 28 : cursor + 30], "little")
        extra_length = int.from_bytes(tail[cursor + 30 : cursor + 32], "little")
        comment_length = int.from_bytes(tail[cursor + 32 : cursor + 34], "little")
        name_start = cursor + 46
        names.append(
            tail[name_start : name_start + name_length].decode("utf-8", "replace")
        )
        cursor = name_start + name_length + extra_length + comment_length
    if not names:
        return None
    return tuple(names)
