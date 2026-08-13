# AliasIndex Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 1,219-line hardcoded `Options.module_aliases` table in `veny.py` with `alias_index.py`, a resolver that returns ranked import-name-to-pip-name candidates backed by evidence and verified by install-and-import.

**Architecture:** A new flat module `alias_index.py` beside `veny.py`, mirroring the `stdlib_index.py` precedent (derived truth, probed from the target interpreter, degrading on failure, no veny imports). It walks five evidence tiers — user overrides, verified cache, target-interpreter distribution metadata, a small in-repo seed, and PyPI wheel inspection — and returns ranked `Candidate` objects. `veny.py` owns a separate attempt loop that installs candidates in order and caches whichever one actually imports.

**Tech Stack:** Python 3.12+, standard library only (`urllib.request`, `zipfile`, `tomllib`, `json`, `subprocess`, `dataclasses`, `enum`). pytest for tests, ruff + mypy (strict) for checks, all run through pixi.

**Global Constraints:**
- **No third-party runtime dependency.** veny bootstraps environments on bare interpreters. Standard library only in `alias_index.py` and in the `veny.py` code that calls it.
- **Never install an unverified guess.** A generated name mutation may only become a `Candidate` after wheel inspection confirms that project declares the import name. There must be no code path from a raw string mutation to `pip install`.
- **Deterministic ranking.** Candidate order is `(source, pip_name)`, stable across runs.
- **Silence for absent information, noise for contradicted information.** Missing network, missing cache, missing metadata: debug/warn and continue. Malformed override file: raise.
- **`alias_index.py` imports nothing from `veny` or `univ_defs`**, keeping the dependency direction one-way (same rule `stdlib_index.py` follows).
- **Style:** `from __future__ import annotations`, full type hints, Google-style docstrings, `ruff` rules `F,E,W,B,B9,UP,I,ANN,D,S` with `convention = "google"`, mypy `strict = true`.
- **Verification is scoped to touched files.** Repo-wide `pixi run lint` / `pixi run typecheck` fail on 1,171 pre-existing ruff and 158 mypy errors in `veny.py` / `univ_defs.py`. Never run them bare and never claim they pass.
- **`.git/hooks/pre-commit` is not installed.** Run `pixi run pre-commit run --files <paths>` by hand before every commit.

**User decisions (already made):**
- "Resolver + layered sources" over relocating, fetching, or pruning the table — chosen as the best long-term foundation.
- Network calls allowed by default during classification, degrading silently when unavailable.
- "Ranked chain, auto-retry by default" — the resolver returns ranked candidates; one-shot and prompt-first remain policy settings over the same mechanism.
- Two stores split by authority: `module_aliases.toml` (human, read-only to veny) and `module_aliases_cache.json` (machine, verified, disposable).
- Delete the pipreqs bulk; keep the ~10 hand-added aliases as an in-repo seed.
- Thread a `Resolution`/record type through the call sites rather than shimming dict-shaped properties.
- Wheel metadata is fetched and inspected to confirm top-level names before any install.
- Seed does not stop the resolution walk, accepting one PyPI round trip on a cold cache for seeded names.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `alias_index.py` (new) | Everything about *deciding* which pip name provides an import name. Data model, stores, interpreter probe, PyPI client, resolution chain. Installs nothing. |
| `tests/test_alias_index.py` (new) | Unit tests for the resolver. No network, no venv — all collaborators injected. |
| `veny.py` (modify) | Owns the *attempt* loop (`resolve_and_verify`), the `Options.aliases` field, and the rewired `split_imports` / `check_packages_in_venv` call sites. |
| `tests/test_split_imports.py` (modify) | Gains tests for `resolve_and_verify` and the record-based classification. |
| `univ_defs.py` (modify) | Gains a `to_jsonable` handler for `AliasIndex`. |
| `PROGRESS.md` (modify) | Index, gotchas, deferred items. |

`alias_index.py` is one module rather than a package because `stdlib_index.py` set that precedent and the repo is a flat two-script layout. It should land around 400 lines; if it grows past roughly 600, split the PyPI client into `pypi_client.py` and keep the chain in `alias_index.py`.

---

### Task 1: Data model and ranking

**Goal:** Define `Source`, `Candidate`, `Resolution`, the deterministic `rank()` function, and the curated `SEED` mapping.

**Files:**
- Create: `alias_index.py`
- Create: `tests/test_alias_index.py`

**Acceptance Criteria:**
- [ ] `Source` is an `IntEnum` with exactly `OVERRIDE=0`, `CACHE=1`, `INSTALLED=2`, `SEED=3`, `PYPI_CONFIRMED=4`, and no heuristic member
- [ ] `rank()` sorts by `(source, pip_name)` and is stable across calls
- [ ] `rank()` deduplicates by `pip_name`, keeping the strongest-evidence occurrence
- [ ] `SEED` is a curated set of exceptions that are both correct and reachable — derived from the hand-added block at `veny.py:136-146`, but **not a verbatim copy** of it (see the note below the code block for what was dropped and added, and why)
- [ ] `alias_index.py` imports nothing from `veny` or `univ_defs`

**Verify:** `pixi run python -m pytest tests/test_alias_index.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_alias_index.py`:

```python
import alias_index
from alias_index import Candidate, Source


def _candidate(pip_name, source, evidence="test"):
    return Candidate(pip_name=pip_name, source=source, evidence=evidence)


def test_stronger_evidence_ranks_first():
    # A heuristic-derived PyPI name must never outrank a human override.
    ranked = alias_index.rank([
        _candidate("guessed", Source.PYPI_CONFIRMED),
        _candidate("chosen", Source.OVERRIDE),
    ])
    assert [c.pip_name for c in ranked] == ["chosen", "guessed"]


def test_same_source_ranks_alphabetically():
    # Without a tiebreak, set iteration order would make runs non-reproducible.
    ranked = alias_index.rank([
        _candidate("zzz", Source.PYPI_CONFIRMED),
        _candidate("aaa", Source.PYPI_CONFIRMED),
    ])
    assert [c.pip_name for c in ranked] == ["aaa", "zzz"]


def test_duplicate_pip_name_keeps_strongest_source():
    # The same name found by two tiers must appear once, at its best evidence,
    # or the attempt loop wastes an attempt installing it twice.
    ranked = alias_index.rank([
        _candidate("pillow", Source.PYPI_CONFIRMED),
        _candidate("pillow", Source.INSTALLED),
    ])
    assert len(ranked) == 1
    assert ranked[0].source is Source.INSTALLED


def test_rank_returns_a_tuple_not_a_generator():
    # Callers iterate candidates more than once; a generator would silently
    # yield nothing on the second pass.
    ranked = alias_index.rank([_candidate("numpy", Source.SEED)])
    assert isinstance(ranked, tuple)


def test_source_has_no_unverified_heuristic_tier():
    # The structural typosquat guard: if a HEURISTIC source ever exists, an
    # unverified name mutation can reach the installer.
    assert not any(member.name == "HEURISTIC" for member in Source)


def test_seed_carries_the_hand_added_aliases():
    assert alias_index.SEED["cv2"] == "opencv-python"
    assert alias_index.SEED["osgeo"] == "gdal"
    assert alias_index.SEED["netCDF4"] == "netcdf4"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run python -m pytest tests/test_alias_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alias_index'`

- [ ] **Step 3: Write the implementation**

Create `alias_index.py`:

```python
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
from collections.abc import Iterable
from dataclasses import dataclass
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
    return tuple(
        sorted(strongest.values(), key=lambda c: (int(c.source), c.pip_name))
    )


# Import names whose pip name veny cannot derive, kept because they are worth
# resolving with no network and an empty cache. This is a short list of known
# exceptions, NOT a mapping table: anything not here is derived at run time.
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
```

**Why `SEED` is not a verbatim copy of `veny.py:136-146`** (ruled on 2026-08-12):

- **`jnp` → `jax.numpy` dropped: broken data.** `jax.numpy` is not a PyPI
  project, so `pip install jax.numpy` fails. The correct pip name is `jax`.
  Rather than silently repair a value nobody has exercised, the entry is left
  out — the PyPI tier resolves `jax` correctly once it exists.
- **`mypy.api` → `mypy` dropped: unreachable.** veny normalizes dotted imports
  to their first component before any classification, so a key containing a dot
  can never match. It is also an identity mapping, so it earns nothing.
- **`yaml` → `PyYAML` and `zmq` → `pyzmq` added.** Both are correct,
  high-traffic aliases that no other tier resolves with an empty cache and no
  network. They appear in the deleted bulk table too, but they are here on
  their merits, not as a reintroduction of it.

The distinction that matters: `SEED` is curated by correctness and reachability,
not by provenance. Its size is the constraint — a short list of exceptions, never
a mapping table.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run python -m pytest tests/test_alias_index.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Check the touched files only**

```bash
pixi run python -m ruff check alias_index.py tests/test_alias_index.py
pixi run python -m ruff format --check alias_index.py tests/test_alias_index.py
pixi run python -m mypy alias_index.py
```

Expected: clean. Do **not** run `pixi run lint` or `pixi run typecheck` bare — they fail on pre-existing errors elsewhere.

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files alias_index.py tests/test_alias_index.py
git add alias_index.py tests/test_alias_index.py
git commit -m "feat: add AliasIndex data model with deterministic candidate ranking"
```

---

### Task 2: Override and cache stores

**Goal:** Load the human override file (hard failure on malformed TOML), and load/save the verified cache (quarantine on corruption, interpreter-tagged entries, persisted import-failure rejections).

**Files:**
- Modify: `alias_index.py`
- Modify: `tests/test_alias_index.py`

**Acceptance Criteria:**
- [ ] `load_overrides()` returns `{}` for a missing file and raises `AliasOverrideError` for malformed TOML
- [ ] `AliasCache.load()` on a corrupt file renames it to `<name>.corrupt-<timestamp>` and starts empty rather than raising. **Corrupt means any unusable file, not only invalid JSON**: validate the payload's shape inside the same `try` that triggers quarantine — top level a dict; `entries` a dict of string keys to dicts carrying string `pip_name` and string `python`; `rejections` a dict of string keys to lists of strings. Anything else takes the quarantine path, so nothing malformed can reach `get()` or `rejected_names()`
- [ ] A cache entry recorded under one interpreter tag is ignored under a different tag
- [ ] `confirm()` writes through to disk immediately and round-trips
- [ ] `reject()` persists only `import_failed` rejections; `install_failed` is not persisted
- [ ] `rejected_names()` reports persisted rejections so the chain can filter them

**Verify:** `pixi run python -m pytest tests/test_alias_index.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_alias_index.py`:

```python
import json

import pytest

from alias_index import AliasCache, AliasOverrideError


def test_missing_override_file_is_not_an_error(tmp_path):
    # Most users never write one; treating absence as failure would break them.
    assert alias_index.load_overrides(tmp_path / "nope.toml") == {}


def test_override_file_is_read(tmp_path):
    path = tmp_path / "module_aliases.toml"
    path.write_text('[aliases]\ncv2 = "my-fork-of-opencv"\n')
    assert alias_index.load_overrides(path) == {"cv2": "my-fork-of-opencv"}


def test_malformed_override_file_raises(tmp_path):
    # Continuing here would resolve names contrary to what the user wrote --
    # the exact silent-wrongness this design exists to remove.
    path = tmp_path / "module_aliases.toml"
    path.write_text("[aliases\ncv2 = broken")
    with pytest.raises(AliasOverrideError) as excinfo:
        alias_index.load_overrides(path)
    assert str(path) in str(excinfo.value)


def test_corrupt_cache_is_quarantined_not_fatal(tmp_path):
    # A cache is regenerable; refusing to run because of one would be absurd.
    # The bad file is kept, because a corrupt cache is evidence of a bug.
    path = tmp_path / "module_aliases_cache.json"
    path.write_text("{not json at all")
    cache = AliasCache.load(path, interpreter_tag="3.12")
    assert cache.get("anything") is None
    quarantined = list(tmp_path.glob("module_aliases_cache.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text() == "{not json at all"


def test_confirm_round_trips_through_disk(tmp_path):
    path = tmp_path / "cache.json"
    AliasCache.load(path, interpreter_tag="3.12").confirm("cv2", "opencv-python")
    reloaded = AliasCache.load(path, interpreter_tag="3.12")
    assert reloaded.get("cv2") == "opencv-python"


def test_entry_from_another_interpreter_is_ignored(tmp_path):
    # A name verified under 3.12 must not silently govern a 3.13 run, where a
    # different distribution may provide it.
    path = tmp_path / "cache.json"
    AliasCache.load(path, interpreter_tag="3.12").confirm("cv2", "opencv-python")
    assert AliasCache.load(path, interpreter_tag="3.13").get("cv2") is None


def test_import_failure_is_persisted_as_a_rejection(tmp_path):
    # "Installed but did not provide the module" is a fact about the package,
    # so re-attempting it on the next run wastes an install every time.
    path = tmp_path / "cache.json"
    AliasCache.load(path, interpreter_tag="3.12").reject("cv2", "cv2", "import_failed")
    reloaded = AliasCache.load(path, interpreter_tag="3.12")
    assert reloaded.rejected_names("cv2") == frozenset({"cv2"})


def test_install_failure_is_not_persisted(tmp_path):
    # An install can fail for transient reasons (network, index outage);
    # persisting that would permanently blacklist a correct package.
    path = tmp_path / "cache.json"
    AliasCache.load(path, interpreter_tag="3.12").reject("cv2", "cv2", "install_failed")
    reloaded = AliasCache.load(path, interpreter_tag="3.12")
    assert reloaded.rejected_names("cv2") == frozenset()


def test_unknown_rejection_kind_raises(tmp_path):
    # Guards against a typo'd kind silently behaving like install_failed.
    cache = AliasCache.load(tmp_path / "cache.json", interpreter_tag="3.12")
    with pytest.raises(ValueError):
        cache.reject("cv2", "cv2", "exploded")


def test_cache_file_is_written_as_readable_json(tmp_path):
    # The file is user-inspectable by design; a pickle or a blob would not be.
    path = tmp_path / "cache.json"
    AliasCache.load(path, interpreter_tag="3.12").confirm("cv2", "opencv-python")
    payload = json.loads(path.read_text())
    assert payload["entries"]["cv2"]["pip_name"] == "opencv-python"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run python -m pytest tests/test_alias_index.py -v`
Expected: FAIL — `ImportError: cannot import name 'AliasCache' from 'alias_index'`

- [ ] **Step 3: Write the implementation**

Add to `alias_index.py` (imports first, then the code below `SEED`):

```python
import json
import logging
import time
import tomllib
from pathlib import Path

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
        raise AliasOverrideError(f"Could not read alias overrides from {path}: {exc}") from exc
    aliases = payload.get("aliases", {})
    if not isinstance(aliases, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in aliases.items()
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
            return cls(path=path, interpreter_tag=interpreter_tag, entries={}, rejections={})
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries = dict(payload["entries"])
            rejections = {key: list(value) for key, value in payload.get("rejections", {}).items()}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            quarantine = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
            logging.warning(
                "Could not read the alias cache %s (%s); moving it to %s and starting empty.",
                path, exc, quarantine,
            )
            try:
                path.rename(quarantine)
            except OSError as rename_exc:  # pragma: no cover - filesystem-specific
                logging.warning("Could not quarantine %s (%s).", path, rename_exc)
            return cls(path=path, interpreter_tag=interpreter_tag, entries={}, rejections={})
        return cls(
            path=path, interpreter_tag=interpreter_tag, entries=entries, rejections=rejections
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
        self.entries[import_name] = {"pip_name": pip_name, "python": self.interpreter_tag}
        remaining = [name for name in self.rejections.get(import_name, []) if name != pip_name]
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
            raise ValueError(f"Unknown rejection kind {kind!r}; expected one of {sorted(_REJECTION_KINDS)}.")
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
            self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except OSError as exc:
            logging.warning("Could not write the alias cache %s (%s).", self.path, exc)
```

> **The `AliasCache.load()` shown above is not sufficient on its own** (found in
> review, 2026-08-12). It survives invalid JSON but not valid JSON of the wrong
> shape: `rejections` as a list raises `AttributeError` out of `load()` itself
> (not in the caught tuple), and an `entries` value that is a string, or a dict
> missing `pip_name`, crashes later inside `get()` — far from the corrupt file.
> Add the shape validation named in the acceptance criteria inside the same
> `try` block, and cover each case with a test asserting the file was
> quarantined and `get()` returns `None` rather than raising.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run python -m pytest tests/test_alias_index.py -v`
Expected: PASS (16 tests, plus the shape-corruption tests above)

- [ ] **Step 5: Check the touched files only**

```bash
pixi run python -m ruff check alias_index.py tests/test_alias_index.py
pixi run python -m mypy alias_index.py
```

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files alias_index.py tests/test_alias_index.py
git add alias_index.py tests/test_alias_index.py
git commit -m "feat: add alias override and verified-cache stores"
```

---

### Task 3: Target-interpreter probe

**Goal:** Ask the target interpreter for its version and its `packages_distributions()` mapping in one subprocess, degrading to empty on any failure.

**Files:**
- Modify: `alias_index.py`
- Modify: `tests/test_alias_index.py`

**Acceptance Criteria:**
- [ ] `probe_interpreter()` returns `(tag, {top_level: [dist, ...]})` on success
- [ ] Any failure — missing executable, non-zero exit, timeout, unparseable output — logs a warning and returns the running interpreter's tag with an empty mapping
- [ ] The probe runs exactly one subprocess
- [ ] Probing the real `sys.executable` returns a tag matching the running interpreter

**Verify:** `pixi run python -m pytest tests/test_alias_index.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_alias_index.py`:

```python
import subprocess
import sys


def test_probe_reads_version_and_distributions(monkeypatch):
    payload = '{"version": [3, 12], "packages": {"cv2": ["opencv-python"]}}'
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

    monkeypatch.setattr(alias_index.subprocess, "run", fake_run)
    tag, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert tag == "3.12"
    assert packages == {"cv2": ["opencv-python"]}
    assert len(calls) == 1


def test_probe_degrades_when_the_interpreter_cannot_run(monkeypatch, caplog):
    # veny's job is to keep going; a missing probe must not stop a run.
    def fake_run(command, **kwargs):
        raise OSError("no such executable")

    monkeypatch.setattr(alias_index.subprocess, "run", fake_run)
    with caplog.at_level("WARNING"):
        tag, packages = alias_index.probe_interpreter("/nope/python3")
    assert packages == {}
    assert tag == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert "no such executable" in caplog.text


def test_probe_degrades_on_unparseable_output(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="not json", stderr="")

    monkeypatch.setattr(alias_index.subprocess, "run", fake_run)
    _, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert packages == {}


def test_probe_degrades_on_nonzero_exit(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="boom")

    monkeypatch.setattr(alias_index.subprocess, "run", fake_run)
    _, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert packages == {}


def test_probe_of_the_running_interpreter_reports_its_own_version():
    # Integration check that the probe code itself is valid Python.
    tag, _ = alias_index.probe_interpreter(sys.executable)
    assert tag == f"{sys.version_info.major}.{sys.version_info.minor}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run python -m pytest tests/test_alias_index.py -v`
Expected: FAIL — `AttributeError: module 'alias_index' has no attribute 'probe_interpreter'`

- [ ] **Step 3: Write the implementation**

Add to `alias_index.py`:

```python
import os
import subprocess
import sys

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
            "alias resolution will rely on other evidence.", python, exc,
        )
        return _running_tag(), {}
    if result.returncode != 0:
        logging.warning(
            "%s exited with %d while listing its installed distributions (%s); "
            "alias resolution will rely on other evidence.",
            python, result.returncode, result.stderr.strip(),
        )
        return _running_tag(), {}
    try:
        payload = json.loads(result.stdout)
        major, minor = payload["version"]
        packages = {str(key): [str(name) for name in value] for key, value in payload["packages"].items()}
    except (ValueError, KeyError, TypeError) as exc:
        logging.warning(
            "Could not read the installed distribution list from %s (%s); "
            "alias resolution will rely on other evidence.", python, exc,
        )
        return _running_tag(), {}
    return f"{int(major)}.{int(minor)}", packages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run python -m pytest tests/test_alias_index.py -v`
Expected: PASS (21 tests)

- [ ] **Step 5: Check the touched files only**

```bash
pixi run python -m ruff check alias_index.py tests/test_alias_index.py
pixi run python -m mypy alias_index.py
```

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files alias_index.py tests/test_alias_index.py
git add alias_index.py tests/test_alias_index.py
git commit -m "feat: probe the target interpreter for installed distributions"
```

---

### Task 4: PyPI client and wheel top-level inspection

**Goal:** Confirm that a PyPI project declares a given top-level import name, by reading the wheel's zip central directory over an HTTP Range request instead of downloading the wheel.

**Files:**
- Modify: `alias_index.py`
- Modify: `tests/test_alias_index.py`

**Acceptance Criteria:**
- [ ] `PyPIClient.top_levels(name)` returns the declared top-level names, or `None` when the project does not exist or cannot be inspected
- [ ] The smallest available wheel is selected
- [ ] An **absolute** tail Range request is used — `bytes={size - W}-{size - 1}`, computed from the declared size — and when the server honours it the whole wheel is never transferred. **Not a suffix range** (`bytes=-W`): `files.pythonhosted.org` answers `501 Unsupported client range` to those, which makes the whole PyPI tier inert. Found in review against the live CDN; a declared size that is absent, zero, or negative means "cannot inspect" and returns `None`
- [ ] The metadata fetch and the wheel fetch carry **separate** byte caps. Reusing `MAX_WHEEL_BYTES` for both truncates large PyPI JSON payloads (`grpcio` is 8.8 MB) and silently blinds those projects
- [ ] A server that ignores Range is accepted only below `MAX_WHEEL_BYTES` (5 MB); otherwise the candidate is abandoned (returns `None`)
- [ ] `.dist-info`, `.data`, and `__pycache__` members are excluded; top-level single-file modules contribute their name without the `.py` suffix
- [ ] Network errors return `None` and log at debug level, never raise
- [ ] **Malformed PyPI metadata returns `None` rather than raising.** Validate the payload's shape before use — top level a dict, `urls` a list of dicts, each candidate file's `filename`/`url` strings and `size` an int. Do not rely on the caught-exception tuple alone: this same defect class (valid JSON of the wrong shape raising an uncaught `AttributeError` or `TypeError`) was found in review in both Task 2 and Task 3
- [ ] A wheel whose central directory is not in the first window triggers exactly one widened re-read

**Verify:** `pixi run python -m pytest tests/test_alias_index.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_alias_index.py`. The helper builds a real zip so the parser is tested against genuine bytes, not a mock of itself:

```python
import io
import zipfile

from alias_index import MAX_WHEEL_BYTES, PyPIClient


def _wheel_bytes(names, comment=b""):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, b"x")
        archive.comment = comment
    return buffer.getvalue()


class _FakeFetcher:
    """Serves one JSON document and one wheel, recording every request."""

    def __init__(self, json_payload, wheel, honour_range=True):
        self.json_payload = json_payload
        self.wheel = wheel
        self.honour_range = honour_range
        self.requests = []

    def get(self, url, headers=None):
        self.requests.append((url, dict(headers or {})))
        if url.endswith("/json"):
            if self.json_payload is None:
                raise alias_index.FetchError("404")
            return 200, {}, json.dumps(self.json_payload).encode()
        range_header = (headers or {}).get("Range")
        if range_header and self.honour_range:
            start = int(range_header.removeprefix("bytes=").split("-")[0] or 0)
            if range_header.startswith("bytes=-"):
                length = int(range_header.removeprefix("bytes=-"))
                return 206, {}, self.wheel[-length:]
            end = range_header.split("-")[1]
            stop = int(end) + 1 if end else len(self.wheel)
            return 206, {}, self.wheel[start:stop]
        return 200, {}, self.wheel


def _json_for(wheel, extra_files=()):
    files = [{"filename": "pkg-1.0-py3-none-any.whl", "url": "https://files/pkg.whl",
              "packagetype": "bdist_wheel", "size": len(wheel)}]
    files.extend(extra_files)
    return {"urls": files}


def test_top_levels_are_read_from_the_wheel_listing():
    wheel = _wheel_bytes(["cv2/__init__.py", "cv2/data.py", "pkg-1.0.dist-info/METADATA"])
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    assert PyPIClient(fetcher).top_levels("opencv-python") == frozenset({"cv2"})


def test_dist_info_and_data_members_are_excluded():
    # Without exclusion, every wheel would "provide" a top level named
    # "<project>-<version>.dist-info", matching nothing and confirming nonsense.
    wheel = _wheel_bytes([
        "thing/__init__.py", "pkg-1.0.dist-info/RECORD", "pkg-1.0.data/scripts/run",
        "__pycache__/stale.pyc",
    ])
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    assert PyPIClient(fetcher).top_levels("thing") == frozenset({"thing"})


def test_single_file_module_contributes_its_stem():
    # six.py and its kin ship as one top-level file, not a package directory.
    wheel = _wheel_bytes(["six.py", "pkg-1.0.dist-info/METADATA"])
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    assert PyPIClient(fetcher).top_levels("six") == frozenset({"six"})


def test_smallest_wheel_is_chosen():
    wheel = _wheel_bytes(["small/__init__.py"])
    payload = _json_for(wheel, extra_files=[
        {"filename": "pkg-1.0-cp312-manylinux.whl", "url": "https://files/big.whl",
         "packagetype": "bdist_wheel", "size": len(wheel) * 100},
    ])
    fetcher = _FakeFetcher(payload, wheel)
    PyPIClient(fetcher).top_levels("pkg")
    assert any(url == "https://files/pkg.whl" for url, _ in fetcher.requests)
    assert not any(url == "https://files/big.whl" for url, _ in fetcher.requests)


def test_range_request_avoids_transferring_the_whole_wheel():
    wheel = _wheel_bytes([f"pkg/mod{i}.py" for i in range(200)])
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    PyPIClient(fetcher).top_levels("pkg")
    wheel_requests = [headers for url, headers in fetcher.requests if url.endswith(".whl")]
    assert wheel_requests
    assert all("Range" in headers for headers in wheel_requests)


def test_oversized_wheel_is_abandoned_when_range_is_ignored():
    # Fail closed: an unprovable candidate must not be attempted, and veny must
    # not silently download 200 MB to find out.
    wheel = _wheel_bytes(["pkg/__init__.py"])
    payload = _json_for(wheel)
    payload["urls"][0]["size"] = MAX_WHEEL_BYTES + 1
    fetcher = _FakeFetcher(payload, wheel, honour_range=False)
    assert PyPIClient(fetcher).top_levels("pkg") is None


def test_small_wheel_is_accepted_when_range_is_ignored():
    wheel = _wheel_bytes(["pkg/__init__.py"])
    fetcher = _FakeFetcher(_json_for(wheel), wheel, honour_range=False)
    assert PyPIClient(fetcher).top_levels("pkg") == frozenset({"pkg"})


def test_central_directory_outside_the_first_window_is_still_found():
    # A long archive comment pushes the end-of-central-directory record out of
    # the initial suffix read; a single-window parser would silently return None.
    wheel = _wheel_bytes(["pkg/__init__.py"], comment=b"c" * 70_000)
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    assert PyPIClient(fetcher).top_levels("pkg") == frozenset({"pkg"})


def test_missing_project_returns_none():
    fetcher = _FakeFetcher(None, b"")
    assert PyPIClient(fetcher).top_levels("does-not-exist") is None


def test_project_without_wheels_returns_none():
    # sdist-only projects cannot be inspected without building them.
    fetcher = _FakeFetcher({"urls": [{"filename": "pkg-1.0.tar.gz", "url": "https://files/pkg.tar.gz",
                                      "packagetype": "sdist", "size": 10}]}, b"")
    assert PyPIClient(fetcher).top_levels("pkg") is None


def test_results_are_cached_per_project():
    # resolve() asks about the same name from several generators; re-fetching
    # would multiply network cost by the number of mutations.
    wheel = _wheel_bytes(["pkg/__init__.py"])
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    client = PyPIClient(fetcher)
    client.top_levels("pkg")
    before = len(fetcher.requests)
    client.top_levels("pkg")
    assert len(fetcher.requests) == before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run python -m pytest tests/test_alias_index.py -v`
Expected: FAIL — `ImportError: cannot import name 'MAX_WHEEL_BYTES' from 'alias_index'`

- [ ] **Step 3: Write the implementation**

Add to `alias_index.py`:

```python
import urllib.error
import urllib.request
import zipfile
from typing import Protocol

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
        if not head or head.startswith("__pycache__") or head.endswith(_EXCLUDED_SUFFIXES):
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
        wheels = [
            entry for entry in payload.get("urls", [])
            if str(entry.get("filename", "")).endswith(".whl")
        ]
        if not wheels:
            logging.debug("Project %s ships no wheel, so its top-level names cannot be read.", name)
            return None
        smallest = min(wheels, key=lambda entry: int(entry.get("size", 0) or 0))
        try:
            return self._read_member_names(str(smallest["url"]), int(smallest.get("size", 0) or 0))
        except (FetchError, ValueError, KeyError, zipfile.BadZipFile) as exc:
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
            status, _, chunk = self._fetcher.get(url, headers={"Range": f"bytes=-{window}"})
            if status != 206:
                if size > MAX_WHEEL_BYTES:
                    logging.debug(
                        "Server ignored Range for %s and the wheel is %d bytes; abandoning it.",
                        url, size,
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
        names.append(tail[name_start : name_start + name_length].decode("utf-8", "replace"))
        cursor = name_start + name_length + extra_length + comment_length
    if not names:
        return None
    return tuple(names)
```

Also add `import io` to the imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run python -m pytest tests/test_alias_index.py -v`
Expected: PASS (32 tests). If the zip64 / long-comment test fails, the tail arithmetic is wrong — fix it there, not by widening `_FIRST_WINDOW`.

- [ ] **Step 5: Check the touched files only**

```bash
pixi run python -m ruff check alias_index.py tests/test_alias_index.py
pixi run python -m mypy alias_index.py
```

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files alias_index.py tests/test_alias_index.py
git add alias_index.py tests/test_alias_index.py
git commit -m "feat: confirm wheel top-level names over ranged central-directory reads"
```

---

### Task 5: The resolution chain

**Goal:** Assemble `AliasIndex` — the five-tier walk, name-mutation generation gated behind wheel confirmation, `confirm()`/`reject()` pass-through, and a `build()` constructor.

**Files:**
- Modify: `alias_index.py`
- Modify: `tests/test_alias_index.py`

**Acceptance Criteria:**
- [ ] An override hit returns a single candidate and performs no network access
- [ ] A cache hit returns a single candidate and performs no network access
- [ ] `INSTALLED`, `SEED`, and `PYPI_CONFIRMED` tiers all contribute without stopping the walk
- [ ] A mutation whose wheel does not declare the import name never appears in `candidates`
- [ ] Persisted rejections are filtered out of `candidates`
- [ ] With no PyPI client (offline), resolution still returns override/cache/installed/seed candidates
- [ ] `build()` wires overrides, cache, probe, and client together from a directory and an interpreter
- [ ] `empty()` builds an index with no probe and no network, for use before an interpreter is known

**Verify:** `pixi run python -m pytest tests/test_alias_index.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_alias_index.py`:

```python
from alias_index import AliasIndex


class _StubPyPI:
    """Stands in for PyPIClient with a fixed project-to-top-levels table."""

    def __init__(self, table):
        self.table = table
        self.asked = []

    def top_levels(self, name):
        self.asked.append(name)
        return self.table.get(name)


def _index(tmp_path, *, overrides=None, installed=None, pypi=None, tag="3.12"):
    return AliasIndex(
        overrides=overrides or {},
        cache=AliasCache.load(tmp_path / "cache.json", interpreter_tag=tag),
        installed=installed or {},
        pypi=pypi,
    )


def test_override_wins_and_costs_no_network(tmp_path):
    pypi = _StubPyPI({})
    index = _index(tmp_path, overrides={"cv2": "my-opencv"}, pypi=pypi)
    resolution = index.resolve("cv2")
    assert [c.pip_name for c in resolution.candidates] == ["my-opencv"]
    assert resolution.candidates[0].source is Source.OVERRIDE
    assert pypi.asked == []


def test_cache_hit_costs_no_network(tmp_path):
    pypi = _StubPyPI({})
    index = _index(tmp_path, pypi=pypi)
    index.confirm("cv2", "opencv-python")
    resolution = index.resolve("cv2")
    assert [c.pip_name for c in resolution.candidates] == ["opencv-python"]
    assert pypi.asked == []


def test_installed_metadata_and_seed_both_contribute(tmp_path):
    # The seed must not stop the walk, or a stale seed entry could hide better
    # evidence permanently.
    index = _index(tmp_path, installed={"cv2": ["opencv-python-headless"]},
                   pypi=_StubPyPI({}))
    names = [c.pip_name for c in index.resolve("cv2").candidates]
    assert names == ["opencv-python-headless", "opencv-python"]


def test_unconfirmed_mutation_never_becomes_a_candidate(tmp_path):
    # The highest-consequence bug in the design: installing a plausible-looking
    # name that does not actually provide the import.
    pypi = _StubPyPI({"typosquat": frozenset({"something_else"})})
    index = _index(tmp_path, pypi=pypi)
    assert index.resolve("typosquat").candidates == ()


def test_confirmed_mutation_becomes_a_pypi_candidate(tmp_path):
    pypi = _StubPyPI({"python-dateutil": frozenset({"dateutil"})})
    index = _index(tmp_path, pypi=pypi)
    candidates = index.resolve("dateutil").candidates
    assert [c.pip_name for c in candidates] == ["python-dateutil"]
    assert candidates[0].source is Source.PYPI_CONFIRMED
    assert candidates[0].top_levels == frozenset({"dateutil"})


def test_identity_candidate_is_confirmed_when_the_project_provides_itself(tmp_path):
    pypi = _StubPyPI({"numpy": frozenset({"numpy"})})
    index = _index(tmp_path, pypi=pypi)
    assert [c.pip_name for c in index.resolve("numpy").candidates] == ["numpy"]


def test_rejected_candidate_is_filtered_out(tmp_path):
    # Re-offering a package already proven not to provide the import wastes an
    # install attempt on every subsequent run.
    pypi = _StubPyPI({"numpy": frozenset({"numpy"})})
    index = _index(tmp_path, pypi=pypi)
    index.reject("numpy", "numpy", "import_failed")
    assert index.resolve("numpy").candidates == ()


def test_offline_index_still_resolves_from_local_evidence(tmp_path):
    index = _index(tmp_path, installed={"cv2": ["opencv-python"]}, pypi=None)
    assert [c.pip_name for c in index.resolve("cv2").candidates] == ["opencv-python"]


def test_unknown_name_offline_resolves_to_nothing(tmp_path):
    assert _index(tmp_path, pypi=None).resolve("mystery").candidates == ()


def test_build_wires_the_pieces_together(tmp_path, monkeypatch):
    monkeypatch.setattr(alias_index, "probe_interpreter", lambda python: ("3.12", {"cv2": ["opencv-python"]}))
    (tmp_path / "module_aliases.toml").write_text('[aliases]\nfoo = "bar"\n')
    index = alias_index.build(python=sys.executable, my_dir=tmp_path, offline=True)
    assert index.overrides == {"foo": "bar"}
    assert index.pypi is None
    assert [c.pip_name for c in index.resolve("cv2").candidates] == ["opencv-python"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run python -m pytest tests/test_alias_index.py -v`
Expected: FAIL — `ImportError: cannot import name 'AliasIndex' from 'alias_index'`

- [ ] **Step 3: Write the implementation**

Add to `alias_index.py`:

```python
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

        Overrides and cache hits short-circuit, because both are settled facts:
        one is the user's stated intent, the other was verified by installing
        and importing. Every other tier contributes without stopping the walk,
        so weaker evidence can never hide stronger evidence.

        Args:
            import_name: The import name as written in the user's source.

        Returns:
            The ranked candidates, possibly empty.
        """
        override = self.overrides.get(import_name)
        if override is not None:
            return Resolution(import_name, (Candidate(
                pip_name=override, source=Source.OVERRIDE,
                evidence=f"{OVERRIDES_FILENAME} maps {import_name} to {override}",
            ),))
        cached = self.cache.get(import_name)
        if cached is not None:
            return Resolution(import_name, (Candidate(
                pip_name=cached, source=Source.CACHE,
                evidence=f"previously installed and imported as {cached}",
            ),))

        found: list[Candidate] = []
        for distribution in self.installed.get(import_name, []):
            found.append(Candidate(
                pip_name=distribution, source=Source.INSTALLED,
                evidence=f"{distribution} provides {import_name} in the target interpreter",
            ))
        seeded = self.seed.get(import_name)
        if seeded is not None:
            found.append(Candidate(
                pip_name=seeded, source=Source.SEED,
                evidence=f"known exception: {import_name} ships in {seeded}",
            ))
        found.extend(self._confirmed_by_pypi(import_name))

        rejected = self.cache.rejected_names(import_name)
        return Resolution(
            import_name,
            tuple(c for c in rank(found) if c.pip_name not in rejected),
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
            confirmed.append(Candidate(
                pip_name=project, source=Source.PYPI_CONFIRMED,
                evidence=f"the {project} wheel declares the top-level name {import_name}",
                top_levels=top_levels,
            ))
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
```

Add a cheap constructor for callers that need an index before an interpreter is
known, so building `Options` never costs a subprocess:

```python
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
```

Add `field` to the `dataclasses` import: `from dataclasses import dataclass, field`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run python -m pytest tests/test_alias_index.py -v`
Expected: PASS (42 tests)

- [ ] **Step 5: Check the touched files only**

```bash
pixi run python -m ruff check alias_index.py tests/test_alias_index.py
pixi run python -m mypy alias_index.py
```

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files alias_index.py tests/test_alias_index.py
git add alias_index.py tests/test_alias_index.py
git commit -m "feat: assemble the layered alias resolution chain"
```

---

### Task 6: The attempt loop in veny.py

**Goal:** Add `resolve_and_verify` to `veny.py` — install candidates in rank order, accept the first that installs *and* imports, uninstall rejects, record outcomes. It installs; the resolver never does.

**Files:**
- Modify: `veny.py` (add near `check_packages_in_venv`, around line 4372)
- Modify: `tests/test_split_imports.py`

**Acceptance Criteria:**
- [ ] Returns the first candidate that installs and imports, and calls `index.confirm()` for it
- [ ] On import failure, uninstalls the candidate and records an `import_failed` rejection
- [ ] On install failure, records an `install_failed` rejection and does not uninstall
- [ ] Stops after `max_attempts` candidates (default 3) even when more remain
- [ ] Returns `None` for an empty candidate list without calling the installer
- [ ] Installer, importer, and uninstaller are injected parameters, so the function is testable with no venv

**Verify:** `pixi run python -m pytest tests/test_split_imports.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_split_imports.py`:

```python
import alias_index
from alias_index import Candidate, Resolution, Source


class _RecordingIndex:
    def __init__(self):
        self.confirmed = []
        self.rejected = []

    def confirm(self, import_name, pip_name):
        self.confirmed.append((import_name, pip_name))

    def reject(self, import_name, pip_name, kind):
        self.rejected.append((import_name, pip_name, kind))


def _resolution(*pip_names):
    return Resolution(
        import_name="thing",
        candidates=tuple(
            Candidate(pip_name=name, source=Source.PYPI_CONFIRMED, evidence="test")
            for name in pip_names
        ),
    )


def test_first_working_candidate_is_confirmed():
    index = _RecordingIndex()
    winner = veny.resolve_and_verify(
        _resolution("wrong", "right"), index,
        installer=lambda name: True,
        importer=lambda name: name == "right",
        uninstaller=lambda name: None,
    )
    assert winner.pip_name == "right"
    assert index.confirmed == [("thing", "right")]


def test_candidate_that_installs_but_does_not_import_is_uninstalled():
    # Leaving it behind pollutes the venv and can shadow the correct package.
    removed = []
    index = _RecordingIndex()
    veny.resolve_and_verify(
        _resolution("wrong", "right"), index,
        installer=lambda name: True,
        importer=lambda name: name == "right",
        uninstaller=removed.append,
    )
    assert removed == ["wrong"]
    assert ("thing", "wrong", "import_failed") in index.rejected


def test_failed_install_is_recorded_but_not_uninstalled():
    # Nothing was installed, and the failure may be transient, so it must not
    # be persisted as a fact about the package.
    removed = []
    index = _RecordingIndex()
    veny.resolve_and_verify(
        _resolution("broken", "right"), index,
        installer=lambda name: name != "broken",
        importer=lambda name: True,
        uninstaller=removed.append,
    )
    assert removed == []
    assert ("thing", "broken", "install_failed") in index.rejected


def test_attempts_are_bounded():
    # One obscure import must not stall a run behind unbounded pip attempts.
    tried = []

    def installer(name):
        tried.append(name)
        return True

    result = veny.resolve_and_verify(
        _resolution("a", "b", "c", "d", "e"), _RecordingIndex(),
        installer=installer, importer=lambda name: False,
        uninstaller=lambda name: None, max_attempts=3,
    )
    assert result is None
    assert tried == ["a", "b", "c"]


def test_empty_resolution_never_touches_the_installer():
    tried = []
    result = veny.resolve_and_verify(
        Resolution("thing", ()), _RecordingIndex(),
        installer=tried.append, importer=lambda name: True,
        uninstaller=lambda name: None,
    )
    assert result is None
    assert tried == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run python -m pytest tests/test_split_imports.py -v`
Expected: FAIL — `AttributeError: module 'veny' has no attribute 'resolve_and_verify'`

- [ ] **Step 3: Write the implementation**

Add to `veny.py`, immediately above `def check_packages_in_venv` (line 4372), and add `import alias_index` beside the existing `import stdlib_index`:

```python
def resolve_and_verify(
    resolution: alias_index.Resolution,
    index: alias_index.AliasIndex,
    installer: Callable[[str], bool],
    importer: Callable[[str], bool],
    uninstaller: Callable[[str], None],
    max_attempts: int = 3,
) -> alias_index.Candidate | None:
    """Install candidates in rank order until one actually provides the import.

    The resolver produces ranked guesses; only installing and importing proves
    one right. A candidate that installs without providing the import name is
    uninstalled, so a rejected package cannot pollute the environment or shadow
    the correct one on a later attempt.

    Args:
        resolution:   The ranked candidates for one import name.
        index:        The AliasIndex to record the outcome in.
        installer:    Installs a pip name, returning True on success.
        importer:     Returns True if the import name now imports.
        uninstaller:  Removes a pip name that was installed but rejected.
        max_attempts: How many candidates to try before giving up.

    Returns:
        The verified candidate, or None if none of the attempts worked.
    """
    for candidate in resolution.candidates[:max_attempts]:
        logging.debug(
            "Trying %s for import %s (%s)",
            candidate.pip_name, resolution.import_name, candidate.evidence,
        )
        if not installer(candidate.pip_name):
            index.reject(resolution.import_name, candidate.pip_name, "install_failed")
            continue
        if importer(resolution.import_name):
            index.confirm(resolution.import_name, candidate.pip_name)
            return candidate
        logging.debug(
            "%s installed but did not provide %s; removing it.",
            candidate.pip_name, resolution.import_name,
        )
        uninstaller(candidate.pip_name)
        index.reject(resolution.import_name, candidate.pip_name, "import_failed")
    return None
```

Ensure `Callable` is imported in `veny.py` (`from collections.abc import Callable`); add it if absent.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run python -m pytest tests/test_split_imports.py -v`
Expected: PASS

- [ ] **Step 5: Check the touched files only**

```bash
pixi run python -m pytest tests/ -v
pixi run python -m ruff check tests/test_split_imports.py
```

`veny.py` has 1,171 pre-existing ruff errors, so lint it only to confirm you added none: capture the count before and after with `pixi run python -m ruff check veny.py --statistics`.

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files veny.py tests/test_split_imports.py
git add veny.py tests/test_split_imports.py
git commit -m "feat: add the candidate attempt loop that verifies aliases by import"
```

---

### Task 7: Rewire the call sites and delete the table

**Goal:** Replace `Options.module_aliases` and `Options.reversed_module_aliases` with `Options.aliases`, thread resolved records through `split_imports` and `check_packages_in_venv`, and add the `to_jsonable` handler.

**Files:**
- Modify: `veny.py:133-1351` (delete `module_aliases`), `veny.py:1352` (delete `reversed_module_aliases`), `veny.py:4372` (`check_packages_in_venv`), `veny.py:4462` (`split_imports`), `main()` near `veny.py:1478`
- Modify: `univ_defs.py` (`to_jsonable`)
- Modify: `tests/test_split_imports.py`

**Acceptance Criteria:**
- [ ] `Options.module_aliases` and `Options.reversed_module_aliases` no longer exist anywhere in the repo
- [ ] `Options.aliases` is built in `main()` after `options.python_command` resolves
- [ ] `installed_imports` and `uninstalled_imports` hold `ResolvedImport` records carrying both names, not bare strings
- [ ] `check_packages_in_venv` reads `record.import_name` and no longer inverts any dict
- [ ] `univ_defs.to_jsonable` serializes an `AliasIndex` as structured data, not `repr()`
- [ ] `veny.py` drops roughly 1,210 lines
- [ ] All existing tests still pass

**Verify:** `pixi run python -m pytest tests/ -v` → all pass, and `rg -n "module_aliases" veny.py` → no matches

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_split_imports.py`:

```python
def test_options_no_longer_carries_an_alias_table():
    # The whole point of the change: the 1,219-line literal is gone.
    options = veny.Options()
    assert not hasattr(options, "module_aliases")
    assert not hasattr(options, "reversed_module_aliases")


def test_resolved_import_record_carries_both_names():
    # The old code put pip names in one set and import names in another, so
    # every consumer had to guess which kind of string it held.
    record = veny.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    assert record.import_name == "cv2"
    assert record.pip_name == "opencv-python"


def test_alias_index_is_serialized_as_structured_data():
    # Serializing via repr() turns lookups into substring matching, which
    # silently returns wrong answers instead of raising.
    import univ_defs as ud

    index = alias_index.AliasIndex(
        overrides={"cv2": "my-opencv"},
        cache=alias_index.AliasCache(
            path=Path("/tmp/none.json"), interpreter_tag="3.12", entries={}, rejections={}
        ),
        installed={},
        pypi=None,
    )
    payload = ud.to_jsonable(index)
    assert isinstance(payload, dict)
    assert payload["overrides"] == {"cv2": "my-opencv"}
    assert payload["interpreter_tag"] == "3.12"
```

Add `from pathlib import Path` to the test imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run python -m pytest tests/test_split_imports.py -v`
Expected: FAIL — `Options` still has `module_aliases`; `veny.ResolvedImport` does not exist.

- [ ] **Step 3: Delete the table and add the record type**

Delete `veny.py` lines 133–1351 (the whole `self.module_aliases = {...}` literal, from the `self.module_aliases: dict[str, str] = {` line through the closing `"zopyx": "zopyx.textindexng3"}`) and line 1352 (`self.reversed_module_aliases = ...`).

Add to `veny.py` near the other module-level dataclasses:

```python
@dataclass(frozen=True)
class ResolvedImport:
    """An import name paired with the pip package that provides it.

    Attributes:
        import_name: The name as written in the user's source.
        pip_name:    The package name to hand to pip.
    """

    import_name: str
    pip_name: str
```

In `Options.__init__`, replace the deleted attributes with the declaration only:

```python
        # Import-name-to-pip-name resolution. Replaced in main() once
        # options.python_command is known, so the resolver probes the
        # interpreter that will actually run the user's script. See
        # docs/superpowers/specs/2026-08-12-module-alias-resolver-design.md
        self.aliases: alias_index.AliasIndex = alias_index.empty(self.my_dir)
```

`empty()` rather than `build()` here: `Options()` is constructed before
`python_command` is known and in every test, and `build()` spawns a probe
subprocess.

In `main()`, beside the existing `options.stdlib` assignment (around `veny.py:1478`), rebuild it against the target interpreter:

```python
    options.aliases = alias_index.build(options.python_command, options.my_dir)
```

- [ ] **Step 4: Rewire `split_imports`**

Replace the classification body at `veny.py:4483-4497` so it resolves and stores records:

```python
        for i, imp in enumerate(options.all_imports, 1):
            resolution = options.aliases.resolve(imp)
            primary = resolution.candidates[0].pip_name if resolution.candidates else imp
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug("Resolved import %s to candidates %s", imp,
                              [c.pip_name for c in resolution.candidates])
            record = ResolvedImport(import_name=imp, pip_name=primary)
            if imp in options.custom_modules.keys():
                status_str = f"{ud.ANSI_CYAN}YES - custom module{ud.ANSI_RESET}"
            elif check_packages_in_venv(options, record=record, venv_dir=venv_dir):
                status_str = f"{ud.ANSI_GREEN}YES -     installed{ud.ANSI_RESET}"
                options.installed_imports.add(record)
            else:
                status_str = " NO - NOT installed"
                options.uninstalled_imports.add(record)
```

Both sets now hold `ResolvedImport`. Update every other reader of those sets — `veny.py:1578`, `1591`, `4347-4368`, `4505`, `4747`, `4762`, `4809-4816`, `4861-4865`, `5081-5083`, `5148` — to use `record.pip_name` where a pip name is needed and `record.import_name` where an import name is needed. Work through them with `rg -n "installed_imports|uninstalled_imports" veny.py` and handle each hit; do not guess from memory.

- [ ] **Step 5: Rewire `check_packages_in_venv`**

Change its signature from `package: str | None` to `record: ResolvedImport | None` and replace the reverse-map lookups at `veny.py:4398` and `4401`:

```python
    if record is not None:
        packages = [record.import_name]
    else:
        use_pip_list(options)
        packages = [entry.import_name for entry in options.uninstalled_imports]
```

The function import-checks inside a venv, so it always wants the *import* name. Reading it off the record is what retires the lossy `reversed_module_aliases` inversion.

- [ ] **Step 6: Add the `to_jsonable` handler**

In `univ_defs.py`, beside the existing handlers, add:

```python
    if isinstance(value, alias_index.AliasIndex):
        return {
            "overrides": dict(value.overrides),
            "interpreter_tag": value.cache.interpreter_tag,
            "cache_path": os.fspath(value.cache.path),
            "offline": value.pypi is None,
        }
```

Place it **before** any generic fallback that calls `repr()`, or the handler will never run. Add `import alias_index` and `import os` at the top of `univ_defs.py` if either is absent — and keep the direction one-way: `univ_defs` imports `alias_index`, never the reverse. Note in the commit message that the equivalent `StdlibIndex` gap remains open.

- [ ] **Step 7: Run the full suite**

Run: `pixi run python -m pytest tests/ -v`
Expected: PASS

Then confirm the deletion and the line drop:

```bash
rg -n "module_aliases|reversed_module_aliases" veny.py
wc -l veny.py
```

Expected: no matches; `veny.py` around 4,220 lines (was 5,427).

- [ ] **Step 8: Smoke-test a real run**

```bash
pixi run python veny.py --justprint --help
```

Expected: the usage text prints without a traceback. Then remove any run byproducts (`.veny_custom_modules_*.pkl`, `logs/`) rather than committing them — they are gitignored, but stage paths explicitly regardless.

- [ ] **Step 9: Commit**

```bash
pixi run pre-commit run --files veny.py univ_defs.py tests/test_split_imports.py
git add veny.py univ_defs.py tests/test_split_imports.py
git commit -m "refactor: resolve module aliases through AliasIndex records"
```

---

### Task 8: Update PROGRESS.md and close out

**Goal:** Record what the next session needs — new gotchas, the retired deferred item, the still-open `StdlibIndex` serialization gap — and confirm the whole suite is green.

**Files:**
- Modify: `PROGRESS.md`

**Acceptance Criteria:**
- [ ] **Current work** points at this plan and states the next action
- [ ] New gotchas recorded: the override file is fatal on malformed TOML; the cache is interpreter-tagged; only import failures persist as rejections; `alias_index.py` must never import `veny`
- [ ] The deferred `also_needs` item survives; the module-alias half is marked done
- [ ] The `univ_defs.to_jsonable` deferred item is narrowed to `StdlibIndex` only
- [ ] Line counts in PROGRESS.md updated to the post-deletion reality

**Verify:** `pixi run python -m pytest tests/ -v` → all pass, and `git status --short` → clean

**Steps:**

- [ ] **Step 1: Update PROGRESS.md**

Set **Next action** to name the first unstarted follow-up (splitting `univ_defs.py` / `veny.py`, per Deferred items). Add to **Gotchas**:

- A malformed `~/veny/module_aliases.toml` raises `AliasOverrideError` and stops the run. This is deliberate: continuing would resolve names contrary to what the user wrote. Every other missing or unreadable input degrades silently instead.
- Cache entries in `~/veny/module_aliases_cache.json` are tagged with the target interpreter's version and ignored under a different one. A "why did it re-resolve?" question usually has this answer.
- Only `import_failed` rejections persist. `install_failed` is deliberately forgotten, because a failed install can be a network blip and persisting it would blacklist a correct package forever.
- `alias_index.py` must not import `veny` or `univ_defs`; the dependency direction is one-way, same rule as `stdlib_index.py`. `univ_defs.py` imports `alias_index`, not the reverse.
- Wheel top-level names come from the zip central directory read over an HTTP `Range` request. If a mirror or proxy strips `Range`, inspection silently falls back to a full download and refuses wheels over 5 MB, so alias resolution gets weaker behind such a proxy without any error.

Update the deferred `univ_defs.to_jsonable` item to cover `StdlibIndex` only, and update the line-count item (`veny.py` is now ~4,220 lines).

- [ ] **Step 2: Verify the tree is green and clean**

```bash
pixi run python -m pytest tests/ -v
pixi run python -m pytest --cov
git status --short
```

Expected: all tests pass; no unexpected untracked files.

- [ ] **Step 3: Commit**

```bash
pixi run pre-commit run --files PROGRESS.md
git add PROGRESS.md
git commit -m "docs: record AliasIndex completion, gotchas, and remaining deferrals"
```

---

## Verification Notes for the Implementer

- **Never run bare `pixi run lint` or `pixi run typecheck`.** They fail on 1,171 pre-existing ruff and 158 pre-existing mypy errors in `veny.py` / `univ_defs.py`, none of which are yours. Scope every check to the files you touched. For `veny.py` itself, compare `--statistics` output before and after to prove you added nothing new.
- **`.git/hooks/pre-commit` is not installed**, so `git commit` runs no hooks. Run `pixi run pre-commit run --files <paths>` yourself before each commit.
- **Do not `git add -A`.** A `--justprint` run drops `.veny_custom_modules_*.pkl` and `logs/` into the tree. They are gitignored, but stage paths explicitly anyway.
- **No test may hit the network.** Every PyPI test injects `_FakeFetcher`. If a test starts taking seconds, something is reaching pypi.org — fix the injection, do not add a skip.
