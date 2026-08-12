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
import json
import logging
import time
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final


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
            entries = dict(payload["entries"])
            rejections = {
                key: list(value) for key, value in payload.get("rejections", {}).items()
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
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
