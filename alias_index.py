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
import re
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
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


def _normalize_pip_name(name: str) -> str:
    """Reduce a pip project name to its PEP 503 normalized form.

    PyPI treats runs of ``-``, ``_``, and ``.`` as equivalent and matches
    case-insensitively, so "skill-metrics" and "skill_metrics" name the same
    project. This form is for comparison only -- pip always receives a
    candidate's original ``pip_name``, never this normalized string.

    Args:
        name: A pip project name.

    Returns:
        The normalized form, per PEP 503.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def rank(candidates: Iterable[Candidate]) -> tuple[Candidate, ...]:
    """Deduplicate candidates by project identity and order them deterministically.

    Two spellings of one project (e.g. "skill-metrics" and "skill_metrics")
    are the same PyPI project and must collapse to a single candidate: Task 6
    attempts at most 3 candidates, and two spellings of one project would
    burn two of those three attempts re-installing the same thing. Dedup
    keys on the PEP 503 normalized name; the surviving candidate keeps its
    original ``pip_name`` string, since that is what is passed to pip. When
    two equivalent spellings tie on source, the first one encountered in
    ``candidates`` survives (deterministic given a deterministic input order,
    but not lexicographic -- see ``strongest.get`` below). The final ordering
    across distinct projects is (source, pip_name) of each surviving
    candidate, so that identical inputs always produce an identical order,
    which keeps runs reproducible and logs comparable.

    Args:
        candidates: Candidates in any order, possibly naming the same project
            under different tiers or different spellings.

    Returns:
        Ranked, deduplicated candidates.
    """
    strongest: dict[str, Candidate] = {}
    for candidate in candidates:
        key = _normalize_pip_name(candidate.pip_name)
        existing = strongest.get(key)
        if existing is None or candidate.source < existing.source:
            strongest[key] = candidate
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
# The metadata and wheel requests share UrllibFetcher.get but must not share a
# byte cap: a project's /pypi/<name>/json body routinely exceeds MAX_WHEEL_BYTES
# on its own (grpcio is 8.8 MB; botocore, awscli, numpy, and boto3 all clear
# 3 MB), so capping it at MAX_WHEEL_BYTES silently blinds those projects.
MAX_METADATA_BYTES: Final[int] = 32 * 1024 * 1024
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
        self, url: str, headers: dict[str, str] | None = None, *, max_bytes: int
    ) -> tuple[int, dict[str, str], bytes]:
        """Retrieve a URL.

        Args:
            url:       The absolute URL to retrieve.
            headers:   Request headers, such as Range.
            max_bytes: Upper bound on bytes read from the response body. The
                caller chooses this per request -- a wheel body and a JSON
                metadata body have very different legitimate sizes -- so
                nothing here should default to a one-size-fits-all cap.

        Returns:
            The status code, response headers, and body bytes.

        Raises:
            FetchError: If the URL cannot be retrieved.
        """
        ...


class UrllibFetcher:
    """A Fetcher backed by urllib, so veny needs no third-party HTTP library."""

    def get(
        self, url: str, headers: dict[str, str] | None = None, *, max_bytes: int
    ) -> tuple[int, dict[str, str], bytes]:
        """Retrieve a URL with a bounded timeout and a bounded read.

        Args:
            url:       The absolute URL to retrieve.
            headers:   Request headers, such as Range.
            max_bytes: Upper bound on bytes read from the response body, so a
                server that ignores a Range header (or serves an
                unexpectedly large body) cannot make this method transfer
                more than the caller is willing to receive.

        Returns:
            The status code, response headers, and body bytes.

        Raises:
            FetchError: On any network or protocol failure.
        """
        if not url.startswith("https://"):
            raise FetchError(f"Refusing to fetch a non-https URL: {url}")
        request = urllib.request.Request(url, headers=headers or {})  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=_READ_TIMEOUT) as response:  # noqa: S310
                body = response.read(max_bytes)
                return int(response.status), dict(response.headers), body
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
    member path and sits at the end of the file. An absolute tail Range request
    (computed from the wheel's declared size) reads it without transferring the
    wheel body, so confirming a candidate costs one JSON request plus tens of
    kilobytes. A suffix Range request (``bytes=-N``) would be simpler, but
    files.pythonhosted.org answers that form with ``501 Unsupported client
    range``; only the absolute form (``bytes=start-end``) works against it.
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
        url = PYPI_JSON_URL.format(name=urllib.parse.quote(name, safe=""))
        try:
            _, _, body = self._fetcher.get(url, max_bytes=MAX_METADATA_BYTES)
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
                or not entry["url"].startswith("https://")
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
        except (FetchError, ValueError, zipfile.BadZipFile) as exc:
            logging.debug("Could not read the wheel listing for %s (%s).", name, exc)
            return None

    def _read_member_names(self, url: str, size: int) -> frozenset[str] | None:
        """Read a remote wheel's member listing without downloading its body.

        files.pythonhosted.org answers a suffix Range (``bytes=-N``) with
        ``501 Unsupported client range``, so the tail is instead requested as
        an absolute range computed from the wheel's declared size: for a
        window W, ``bytes={max(0, size - W)}-{size - 1}``.

        Args:
            url:  Absolute URL of the wheel.
            size: Wheel size in bytes, as reported by PyPI.

        Returns:
            The top-level names, or None when size is not usable, or the
            server refuses Range on a wheel larger than MAX_WHEEL_BYTES.

        Raises:
            FetchError: If the wheel cannot be retrieved.
        """
        if size <= 0:
            logging.debug(
                "Wheel size for %s is not usable (%d); skipping it.", url, size
            )
            return None
        for window in (_FIRST_WINDOW, _WIDE_WINDOW):
            start = max(0, size - window)
            status, _, chunk = self._fetcher.get(
                url,
                headers={"Range": f"bytes={start}-{size - 1}"},
                max_bytes=MAX_WHEEL_BYTES + 1,
            )
            if status != 206:
                # size is PyPI's claim; len(chunk) is what was actually
                # received. Both are checked -- a false or missing declared
                # size must not let an oversized body slip past the cap that
                # exists to bound it.
                if size > MAX_WHEEL_BYTES or len(chunk) > MAX_WHEEL_BYTES:
                    logging.debug(
                        "Server ignored Range for %s and the wheel is %d bytes; abandoning it.",
                        url,
                        max(size, len(chunk)),
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
        tail, the directory it points at is not fully inside tail, or the
        parsed walk does not satisfy the invariants a genuine central
        directory has (see below). Either way the caller should retry with a
        wider window.
    """
    marker = tail.rfind(_EOCD_SIGNATURE)
    if marker < 0:
        return None
    total_entries = int.from_bytes(tail[marker + 10 : marker + 12], "little")
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
    # A genuine central directory satisfies two invariants that garbage bytes
    # (e.g. a buffer that merely repeats the central-file signature) do not:
    # the walk ends exactly where the EOCD begins, and the number of entries
    # walked matches the EOCD's own total-entries field. Either mismatch
    # means this was not a real directory, so report "could not determine"
    # rather than a confidently wrong (and possibly empty) name list.
    if not names or cursor != marker or len(names) != total_entries:
        return None
    return tuple(names)


def mutations(import_name: str) -> tuple[str, ...]:
    """Generate plausible PyPI project names for an import name.

    These are guesses, not answers. Every one is checked against wheel metadata
    before it can become a candidate, so a name generated here can never reach
    pip on its own.

    Args:
        import_name: The import name as written in the user's source.

    Returns:
        Distinct candidate project names, excluding the import name itself.
    """
    base = import_name.lower()
    generated = [
        base.replace("_", "-"),
        f"python-{base.replace('_', '-')}",
        f"{base.replace('_', '-')}-python",
        f"py{base}",
        base.removeprefix("py") if base.startswith("py") and len(base) > 2 else base,
    ]
    seen: dict[str, None] = {}
    for name in generated:
        if name and name != import_name:
            seen.setdefault(name, None)
    return tuple(seen)


@dataclass
class AliasIndex:
    """Resolves import names to ranked, evidence-backed pip package names.

    Attributes:
        overrides: The user's authoritative import-to-pip mapping.
        cache:     Verified results from previous runs.
        installed: Top-level name to distributions, from the target interpreter.
        pypi:      PyPI client, or None when resolution must stay offline.
        seed:      Curated exceptions that need no network to resolve.
    """

    overrides: dict[str, str]
    cache: AliasCache
    installed: dict[str, list[str]]
    pypi: PyPIClient | None
    seed: dict[str, str] = field(default_factory=lambda: dict(SEED))

    def resolve(self, import_name: str) -> Resolution:
        """Return ranked candidate pip names for an import name.

        Overrides short-circuit unconditionally: an override is the user's
        stated intent and outranks even a recorded failure. A cache hit is
        also a settled fact -- it was verified by installing and importing --
        but only while nothing has since proven it wrong; if the cached name
        was later rejected (e.g. a broken native dependency, a yanked
        release), it must not keep being re-offered, so the cache branch is
        checked against the recorded rejections before it short-circuits.
        Every other tier contributes without stopping the walk, so weaker
        evidence can never hide stronger evidence. Rejections are compared on
        the PEP 503 normalized name, matching rank()'s dedup key, so a name
        rejected under one spelling (e.g. "skill-metrics") cannot be
        re-offered under an equivalent one (e.g. "skill_metrics").

        Args:
            import_name: The import name as written in the user's source.

        Returns:
            The ranked candidates, possibly empty.
        """
        override = self.overrides.get(import_name)
        if override is not None:
            return Resolution(
                import_name,
                (
                    Candidate(
                        pip_name=override,
                        source=Source.OVERRIDE,
                        evidence=f"{OVERRIDES_FILENAME} maps {import_name} to {override}",
                    ),
                ),
            )
        cached = self.cache.get(import_name)
        rejected_normalized = {
            _normalize_pip_name(name) for name in self.cache.rejected_names(import_name)
        }
        if (
            cached is not None
            and _normalize_pip_name(cached) not in rejected_normalized
        ):
            return Resolution(
                import_name,
                (
                    Candidate(
                        pip_name=cached,
                        source=Source.CACHE,
                        evidence=f"previously installed and imported as {cached}",
                    ),
                ),
            )

        found: list[Candidate] = []
        for distribution in self.installed.get(import_name, []):
            found.append(
                Candidate(
                    pip_name=distribution,
                    source=Source.INSTALLED,
                    evidence=f"{distribution} provides {import_name} in the target interpreter",
                )
            )
        seeded = self.seed.get(import_name)
        if seeded is not None:
            found.append(
                Candidate(
                    pip_name=seeded,
                    source=Source.SEED,
                    evidence=f"known exception: {import_name} ships in {seeded}",
                )
            )
        found.extend(self._confirmed_by_pypi(import_name))

        return Resolution(
            import_name,
            tuple(
                c
                for c in rank(found)
                if _normalize_pip_name(c.pip_name) not in rejected_normalized
            ),
        )

    def _confirmed_by_pypi(self, import_name: str) -> list[Candidate]:
        """Return candidates whose wheels declare the import name.

        Args:
            import_name: The import name being resolved.

        Returns:
            Confirmed candidates, empty when offline or when nothing confirms.
        """
        if self.pypi is None:
            return []
        confirmed: list[Candidate] = []
        for project in (import_name, *mutations(import_name)):
            top_levels = self.pypi.top_levels(project)
            if top_levels is None or import_name not in top_levels:
                continue
            confirmed.append(
                Candidate(
                    pip_name=project,
                    source=Source.PYPI_CONFIRMED,
                    evidence=f"the {project} wheel declares the top-level name {import_name}",
                    top_levels=top_levels,
                )
            )
        return confirmed

    def confirm(self, import_name: str, pip_name: str) -> None:
        """Record that pip_name installed and satisfied import_name.

        Args:
            import_name: The import name that was satisfied.
            pip_name:    The pip package that satisfied it.
        """
        self.cache.confirm(import_name, pip_name)

    def reject(self, import_name: str, pip_name: str, kind: str) -> None:
        """Record that a candidate failed.

        Args:
            import_name: The import name being resolved.
            pip_name:    The candidate that failed.
            kind:        Either "import_failed" or "install_failed".
        """
        self.cache.reject(import_name, pip_name, kind)


def build(
    python: str | os.PathLike[str], my_dir: Path, *, offline: bool = False
) -> AliasIndex:
    """Assemble an AliasIndex for one target interpreter.

    Args:
        python:  The interpreter that will run the user's script.
        my_dir:  veny's own directory, where the stores live.
        offline: Skip the PyPI tier entirely.

    Returns:
        A ready-to-use AliasIndex.

    Raises:
        AliasOverrideError: If the override file exists but cannot be read.
    """
    tag, installed = probe_interpreter(python)
    return AliasIndex(
        overrides=load_overrides(my_dir / OVERRIDES_FILENAME),
        cache=AliasCache.load(my_dir / CACHE_FILENAME, interpreter_tag=tag),
        installed=installed,
        pypi=None if offline else PyPIClient(),
    )


def empty(my_dir: Path) -> AliasIndex:
    """Build an index with no interpreter evidence and no network access.

    Options() is constructed before the target interpreter is known, and in
    tests, so it must not pay for a probe. main() replaces this with build().

    Args:
        my_dir: veny's own directory, where the stores live.

    Returns:
        An AliasIndex backed only by the override file, cache, and seed.

    Raises:
        AliasOverrideError: If the override file exists but cannot be read.
    """
    return AliasIndex(
        overrides=load_overrides(my_dir / OVERRIDES_FILENAME),
        cache=AliasCache.load(my_dir / CACHE_FILENAME, interpreter_tag=_running_tag()),
        installed={},
        pypi=None,
    )
