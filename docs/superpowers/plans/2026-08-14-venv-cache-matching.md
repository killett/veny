# Venv-cache matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Match cached virtual environments from a versioned manifest written inside each venv, with a correctly encoded folder name as a cheap prefilter, so hyphenated pip names, equivalent project spellings, `--reqs` pins, and interpreter changes all decide the match correctly.

**Architecture:** A new standard-library-only module `venv_cache.py` owns folder-name construction and parsing, `veny_manifest.json` read/write, the match predicate, and a limited fail-closed version comparator. `veny.py` keeps the filesystem walk, the flag logic, venv creation, and the venv probes, and calls into `venv_cache` for every decision. The import-level check added in Task 9 of the alias-resolver plan (`check_packages_in_venv(source_names=...)`) stays as the final confirmation of a chosen venv.

**Tech Stack:** Python 3.12+, standard library only for shipped code (`json`, `re`, `dataclasses`, `pathlib`, `subprocess`, `importlib.metadata` inside the venv). pytest for tests, run through pixi.

**Global Constraints:**
- No third-party dependency may be required to run veny. `packaging` is forbidden; PEP 440 handling is hand-rolled and deliberately partial.
- `venv_cache.py` imports only the standard library — nothing from `veny`, `univ_defs`, `alias_index`, or `pypi_client`. `veny.py` imports `venv_cache`, never the reverse.
- Flat repository layout: `venv_cache.py` sits at the repository root beside `veny.py`, `univ_defs.py`, `stdlib_index.py`, `alias_index.py`, `pypi_client.py`. There is no `src/` package here.
- Folder name format is exactly `<venv_name>-py<tag>-<YYYYMMDD>-<HHMMSS>-<packages>`; packages are PEP 503 normalized, joined with `_`, at most five listed, overflow tail `_and_<N>_more`.
- Manifest filename is exactly `veny_manifest.json`, `SCHEMA_VERSION` is `1`.
- Every cache-path failure means "not a match" and is logged; it never raises.
- `pixi run lint` and `pixi run typecheck` fail repo-wide on pre-existing debt. Gate on `ruff check <touched files> --statistics` and `mypy <touched files>` only. **Never** run the pre-commit `ruff` or `ruff-format` hooks against `veny.py` — a trial run once rewrote ~2,000 lines of its hand-aligned formatting.
- `.git/hooks/pre-commit` is not installed, so `git commit` runs no hooks. Run `pixi run pre-commit run --files <paths>` by hand, and never on `veny.py`.

**User decisions (already made):**
- "Format may change" — the folder-name format is free to change; existing cached venvs may be rebuilt once.
- "Machine index too" — the folder name stays both human-readable and exactly parseable, used as a cheap prefilter.
- "Fix both plus the cache-key layer" — this work covers the folder name, the `requirements.txt` comparison, and the whole match path.
- "Normalized pip name + manifest" — key on `normalize_pip_name(pip_name)` at every layer, backed by a versioned manifest.
- "Skip them" — venvs with no manifest are skipped and rebuilt; there is no legacy read path.
- "Record and match on it" — the manifest records the interpreter, and a mismatch rejects the venv.
- "Fix it here" — build the venv with `options.python_command` rather than `sys.executable`.
- "Rename after repair" — one `rename_venv` helper serves both the `failed-` prefix drop and repair-driven renames.
- "Version comparison, fail closed" — installed versions are recorded and compared; unsupported forms return no-match.
- "Underscore-joined, py tag" — the approved name format, with the interpreter field spelled `py3.12` (see the design doc for why the dot is kept).
- "Unit tests + one real run" — unit tests plus one manual end-to-end verification.

---

### Task 1: venv_cache folder naming

**Goal:** Create `venv_cache.py` with PEP 503 normalization and the folder-name build/parse pair, so a hyphenated pip name survives a round trip.

**Files:**
- Create: `venv_cache.py`
- Create: `tests/test_venv_cache.py`

**Acceptance Criteria:**
- [ ] `build_folder_name` normalizes, sorts, and joins package names with `_`
- [ ] `parse_folder_name` recovers hyphenated names exactly
- [ ] Overflow past five packages produces `_and_<N>_more`, and parsing recovers N
- [ ] Malformed names return `None` rather than raising
- [ ] `venv_cache.py` imports only the standard library

**Verify:** `pixi run test tests/test_venv_cache.py` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_venv_cache.py`:

```python
"""Tests for venv_cache."""

import venv_cache


def test_build_folder_name_normalizes_and_joins_with_underscores() -> None:
    """A hyphen inside a pip name must not be mistaken for a field separator."""
    name = venv_cache.build_folder_name(
        venv_name="myenv",
        interpreter_tag="3.12",
        timestamp="20260814-091500",
        pip_names=["ruamel.yaml", "NumPy", "types_requests"],
    )
    assert name == "myenv-py3.12-20260814-091500-numpy_ruamel-yaml_types-requests"


def test_parse_folder_name_recovers_hyphenated_package_names() -> None:
    """Splitting the whole name on '-' shatters 'ruamel-yaml' into two fragments."""
    parsed = venv_cache.parse_folder_name(
        "myenv-py3.12-20260814-091500-numpy_ruamel-yaml_types-requests"
    )
    assert parsed is not None
    assert parsed.venv_name == "myenv"
    assert parsed.interpreter_tag == "3.12"
    assert parsed.timestamp == "20260814-091500"
    assert parsed.packages == frozenset({"numpy", "ruamel-yaml", "types-requests"})
    assert parsed.unnamed_count == 0


def test_more_than_five_packages_are_summarised_and_counted() -> None:
    """An off-by-one in the overflow count makes the prefilter reject good venvs."""
    pip_names = ["a", "b", "c", "d", "e", "f", "g", "h"]
    name = venv_cache.build_folder_name("myenv", "3.12", "20260814-091500", pip_names)
    assert name == "myenv-py3.12-20260814-091500-a_b_c_d_e_and_3_more"
    parsed = venv_cache.parse_folder_name(name)
    assert parsed is not None
    assert parsed.packages == frozenset({"a", "b", "c", "d", "e"})
    assert parsed.unnamed_count == 3


def test_parse_folder_name_rejects_malformed_names() -> None:
    """An unrelated directory in ~/veny must not be treated as a venv candidate."""
    assert venv_cache.parse_folder_name("myenv-py3.12-20260814-091500") is None
    assert venv_cache.parse_folder_name("myenv-3.12-20260814-091500-numpy") is None
    assert venv_cache.parse_folder_name("myenv-py3.12-2026081-091500-numpy") is None
    assert venv_cache.parse_folder_name("myenv-py3.12-20260814-091500-") is None
    assert venv_cache.parse_folder_name("") is None


def test_normalize_pip_name_matches_pep503() -> None:
    """Comparing two spellings of one project requires the same rule on both sides."""
    assert venv_cache.normalize_pip_name("Ruamel.YAML") == "ruamel-yaml"
    assert venv_cache.normalize_pip_name("types__requests") == "types-requests"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_venv_cache.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'venv_cache'`

- [ ] **Step 3: Write the implementation**

Create `venv_cache.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test tests/test_venv_cache.py`
Expected: PASS, 5 tests

- [ ] **Step 5: Check the files you touched**

Run: `pixi run python -m ruff check venv_cache.py tests/test_venv_cache.py --statistics`
Run: `pixi run python -m mypy venv_cache.py tests/test_venv_cache.py`
Expected: no errors in either. (These two files are new, so unlike `veny.py` they must be clean.)

- [ ] **Step 6: Commit**

```bash
git add venv_cache.py tests/test_venv_cache.py
git commit -m "feat: encode venv folder names so hyphenated pip names survive"
```

---

### Task 2: The manifest

**Goal:** Add the `Manifest` dataclass with best-effort write and fail-soft read, so a venv records what it holds.

**Files:**
- Modify: `venv_cache.py`
- Modify: `tests/test_venv_cache.py`

**Acceptance Criteria:**
- [ ] `write_manifest` writes `veny_manifest.json` into a venv directory and returns whether it succeeded
- [ ] `read_manifest` round-trips every field, including `installed_version` and `requested_spec`
- [ ] Missing file, malformed JSON, and an unknown `schema_version` each return `None`
- [ ] No manifest failure raises

**Verify:** `pixi run test tests/test_venv_cache.py` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_venv_cache.py`:

```python
import json
from pathlib import Path


def a_manifest() -> venv_cache.Manifest:
    """Build a manifest fixture with one plain and one pinned package."""
    return venv_cache.Manifest(
        schema_version=venv_cache.SCHEMA_VERSION,
        created="20260814-091500",
        veny_version="0.2.2",
        interpreter_tag="3.12",
        interpreter_path="/usr/bin/python3.12",
        packages=(
            venv_cache.PackageRecord("yaml", "PyYAML", "6.0.2", None),
            venv_cache.PackageRecord("numpy", "numpy", "2.1.3", ">=1.2"),
        ),
    )


def test_manifest_round_trips_every_field(tmp_path: Path) -> None:
    """A dropped requested_spec would turn every pinned package into an unpinned one."""
    assert venv_cache.write_manifest(tmp_path, a_manifest()) is True
    assert venv_cache.read_manifest(tmp_path) == a_manifest()


def test_read_manifest_returns_none_for_a_missing_file(tmp_path: Path) -> None:
    """A pre-manifest venv must be skipped, not crash the run."""
    assert venv_cache.read_manifest(tmp_path) is None


def test_read_manifest_returns_none_for_malformed_json(tmp_path: Path) -> None:
    """A truncated write must cost one cache miss, not abort the run."""
    (tmp_path / venv_cache.MANIFEST_FILENAME).write_text('{"schema_version": 1,')
    assert venv_cache.read_manifest(tmp_path) is None


def test_read_manifest_returns_none_for_an_unknown_schema_version(tmp_path: Path) -> None:
    """A future schema read as version 1 would match on fields that changed meaning."""
    data = {
        "schema_version": venv_cache.SCHEMA_VERSION + 1,
        "created": "20260814-091500",
        "veny_version": "0.2.2",
        "interpreter_tag": "3.12",
        "interpreter_path": "/usr/bin/python3.12",
        "packages": [],
    }
    (tmp_path / venv_cache.MANIFEST_FILENAME).write_text(json.dumps(data))
    assert venv_cache.read_manifest(tmp_path) is None


def test_read_manifest_returns_none_when_a_package_entry_is_not_a_mapping(
    tmp_path: Path,
) -> None:
    """A hand-edited manifest must degrade to a cache miss, not a TypeError."""
    data = {
        "schema_version": venv_cache.SCHEMA_VERSION,
        "created": "20260814-091500",
        "veny_version": "0.2.2",
        "interpreter_tag": "3.12",
        "interpreter_path": "/usr/bin/python3.12",
        "packages": ["numpy"],
    }
    (tmp_path / venv_cache.MANIFEST_FILENAME).write_text(json.dumps(data))
    assert venv_cache.read_manifest(tmp_path) is None


def test_write_manifest_returns_false_when_the_directory_is_missing(tmp_path: Path) -> None:
    """A venv that cannot record itself is still usable now; it just will not be reused."""
    assert venv_cache.write_manifest(tmp_path / "absent", a_manifest()) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_venv_cache.py -k manifest`
Expected: FAIL — `AttributeError: module 'venv_cache' has no attribute 'Manifest'`

- [ ] **Step 3: Write the implementation**

Add to `venv_cache.py` (imports first, then the code):

```python
import json
import logging
import os
from pathlib import Path

MANIFEST_FILENAME: str = "veny_manifest.json"
SCHEMA_VERSION: int = 1


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
        with open(path, "w") as handle:
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
        with open(path, "r") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test tests/test_venv_cache.py`
Expected: PASS, 11 tests

- [ ] **Step 5: Check the files you touched**

Run: `pixi run python -m ruff check venv_cache.py tests/test_venv_cache.py --statistics`
Run: `pixi run python -m mypy venv_cache.py tests/test_venv_cache.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add venv_cache.py tests/test_venv_cache.py
git commit -m "feat: record what a virtual environment holds in a manifest"
```

---

### Task 3: The version comparator

**Goal:** Add `version_satisfies`, a limited PEP 440 comparator that returns False for anything it does not fully support.

**Files:**
- Modify: `venv_cache.py`
- Modify: `tests/test_venv_cache.py`

**Acceptance Criteria:**
- [ ] Release segments compare numerically, zero-padded to equal length
- [ ] `==`, `!=`, `>=`, `<=`, `>`, `<`, `~=`, and `==X.Y.*` are supported, comma-separated and conjunctive
- [ ] Epochs, pre/post/dev releases, local versions, `===`, and a `None` installed version return False
- [ ] No input raises

**Verify:** `pixi run test tests/test_venv_cache.py -k version` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_venv_cache.py`:

```python
import pytest


@pytest.mark.parametrize(
    ("installed", "spec", "expected"),
    [
        ("1.10.0", ">1.9", True),      # lexicographic compare would say "1.10" < "1.9"
        ("1.2", ">=1.2.0", True),      # zero padding
        ("1.2.0", "==1.2", True),      # zero padding, other direction
        ("1.2.3", "~=1.2.0", True),    # compatible release, in range
        ("1.3.0", "~=1.2.0", False),   # compatible release, above the bound
        ("1.9.9", "~=1.2", True),      # two-component compatible release
        ("2.0.0", "~=1.2", False),
        ("1.2.5", "==1.2.*", True),    # prefix match on release segments
        ("1.3.0", "==1.2.*", False),
        ("1.20.0", "==1.2.*", False),  # string prefix matching would say True
        ("1.5", ">=1.0,<2.0", True),   # every clause must hold
        ("2.1", ">=1.0,<2.0", False),
        ("1.5", "!=1.5", False),
        ("1.5", "!=1.6", True),
    ],
)
def test_version_satisfies_supported_forms(installed: str, spec: str, expected: bool) -> None:
    """A comparator that compares strings, or honours only the first clause, fails here."""
    assert venv_cache.version_satisfies(installed, spec) is expected


@pytest.mark.parametrize(
    ("installed", "spec"),
    [
        ("1.2b1", ">=1.0"),    # pre-release
        ("1.2.post1", ">=1.0"),
        ("1.2.dev0", ">=1.0"),
        ("1.2+cpu", ">=1.0"),  # local version
        ("1!2.0", ">=1.0"),    # epoch
        ("1.2", "===1.2"),     # arbitrary equality
        ("1.2", ">=1.0b1"),    # unsupported form on the spec side
        ("1.2", "~=1"),        # compatible release needs two components
        ("1.2", "1.2"),        # no operator
        ("1.2", ""),           # present but empty
        ("1.2", "@ https://example.invalid/x.whl"),
        (None, ">=1.0"),       # unknown installed version
    ],
)
def test_version_satisfies_fails_closed(installed: str | None, spec: str) -> None:
    """Stripping a suffix and comparing anyway would report a pre-release as satisfying a pin."""
    assert venv_cache.version_satisfies(installed, spec) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_venv_cache.py -k version`
Expected: FAIL — `AttributeError: module 'venv_cache' has no attribute 'version_satisfies'`

- [ ] **Step 3: Write the implementation**

Add to `venv_cache.py`:

```python
_RELEASE_RE = re.compile(r"\d+(?:\.\d+)*\Z")
_CLAUSE_RE = re.compile(r"(==|!=|>=|<=|~=|>|<)(.+)\Z", re.DOTALL)


def _release(text: str) -> tuple[int, ...] | None:
    """Parse a release segment made only of dot-separated integers.

    Args:
        text: A version string.

    Returns:
        Its release components, or None if it uses any form this module does not
        support -- epochs, pre/post/dev releases, local versions, wildcards.
    """
    text = text.strip()
    if not _RELEASE_RE.match(text):
        return None
    return tuple(int(part) for part in text.split("."))


def _compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    """Compare two release tuples, zero-padding the shorter one.

    Args:
        left:  The installed version's components.
        right: The specified version's components.

    Returns:
        -1, 0, or 1, so that 1.2 and 1.2.0 compare equal.
    """
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    return (padded_left > padded_right) - (padded_left < padded_right)


def _clause_holds(installed: tuple[int, ...], clause: str) -> bool:
    """Test one comma-separated clause of a version specifier.

    Args:
        installed: The installed version's release components.
        clause:    One clause, such as ">=1.2" or "==1.2.*".

    Returns:
        True if the clause holds. False for any form this module does not fully
        support, which is what makes the whole comparator fail closed.
    """
    match = _CLAUSE_RE.match(clause.strip())
    if match is None:
        return False
    operator, raw = match.group(1), match.group(2).strip()
    if operator == "==" and raw.endswith(".*"):
        prefix = _release(raw[:-2])
        if prefix is None:
            return False
        width = len(prefix)
        padded = installed + (0,) * max(0, width - len(installed))
        return padded[:width] == prefix
    wanted = _release(raw)
    if wanted is None:
        return False
    if operator == "~=":
        # PEP 440's compatible release: ~=X.Y.Z means >=X.Y.Z and <X.(Y+1).
        if len(wanted) < 2:
            return False
        upper = wanted[:-2] + (wanted[-2] + 1,)
        return _compare(installed, wanted) >= 0 and _compare(installed, upper) < 0
    order = _compare(installed, wanted)
    if operator == "==":
        return order == 0
    if operator == "!=":
        return order != 0
    if operator == ">=":
        return order >= 0
    if operator == "<=":
        return order <= 0
    if operator == ">":
        return order > 0
    return order < 0


def version_satisfies(installed: str | None, spec: str | None) -> bool:
    """Test whether an installed version satisfies a requested specifier.

    This is deliberately not a PEP 440 implementation. It supports comma-
    separated clauses using ==, !=, >=, <=, >, <, ~=, and ==X.Y.*, over versions
    made only of dot-separated integers. It refuses everything else -- epochs,
    pre/post/dev releases, local versions, arbitrary equality, URLs, environment
    markers -- by returning False.

    Refusing means "no match", which means a rebuild. That is the safe
    direction: being wrong toward reuse hands back a virtual environment that
    violates the user's pin and fails at their runtime, while being wrong toward
    rebuild only costs time.

    Args:
        installed: The version the venv reports, or None if it is unknown.
        spec:      The requested specifier, or None when nothing was requested.

    Returns:
        True only if every clause holds under the supported subset.
    """
    if installed is None or spec is None or not spec.strip():
        return False
    release = _release(installed)
    if release is None:
        return False
    return all(_clause_holds(release, clause) for clause in spec.split(","))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test tests/test_venv_cache.py`
Expected: PASS — the 26 parametrized version cases plus the earlier tests

- [ ] **Step 5: Check the files you touched**

Run: `pixi run python -m ruff check venv_cache.py tests/test_venv_cache.py --statistics`
Run: `pixi run python -m mypy venv_cache.py tests/test_venv_cache.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add venv_cache.py tests/test_venv_cache.py
git commit -m "feat: compare installed versions against pins, failing closed"
```

---

### Task 4: The match predicate

**Goal:** Add `Wanted`, `MatchResult`, `satisfies`, and the name-level prefilter `name_allows`, so one predicate answers "can this venv serve this run".

**Files:**
- Modify: `venv_cache.py`
- Modify: `tests/test_venv_cache.py`

**Acceptance Criteria:**
- [ ] Interpreter tag mismatch rejects
- [ ] Every wanted package must be present by normalized pip name; extras in the venv are fine
- [ ] A wanted spec is checked against the recorded installed version, and a `None` version rejects
- [ ] `MatchResult.reason` names the package or tag responsible for a rejection
- [ ] `name_allows` accepts a folder whose name lists a hyphenated wanted package, and tolerates summarised names within `unnamed_count`

**Verify:** `pixi run test tests/test_venv_cache.py` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_venv_cache.py`:

```python
def wanted(pip_name: str, spec: str | None = None) -> venv_cache.Wanted:
    """Shorthand for one wanted package."""
    return venv_cache.Wanted(pip_name=pip_name, spec=spec)


def test_satisfies_accepts_a_venv_holding_everything_wanted() -> None:
    """The floor of the predicate: an exact match must match."""
    result = venv_cache.satisfies(a_manifest(), [wanted("PyYAML"), wanted("numpy")], "3.12")
    assert result.matched is True


def test_satisfies_rejects_a_different_interpreter() -> None:
    """A 3.12 venv handed to a 3.13 run fails at the user's runtime."""
    result = venv_cache.satisfies(a_manifest(), [wanted("numpy")], "3.13")
    assert result.matched is False
    assert "3.12" in result.reason and "3.13" in result.reason


def test_satisfies_accepts_a_venv_holding_extra_packages() -> None:
    """Set equality here would defeat reuse entirely and make --smallest meaningless."""
    result = venv_cache.satisfies(a_manifest(), [wanted("numpy")], "3.12")
    assert result.matched is True


def test_satisfies_matches_equivalent_spellings() -> None:
    """Normalizing only one side misses PyYAML against pyyaml."""
    result = venv_cache.satisfies(a_manifest(), [wanted("pyyaml")], "3.12")
    assert result.matched is True


def test_satisfies_matches_a_dotted_spelling_against_a_hyphenated_one() -> None:
    """ruamel.yaml and ruamel-yaml are one project; comparing raw strings says otherwise."""
    manifest = venv_cache.Manifest(
        schema_version=venv_cache.SCHEMA_VERSION,
        created="20260814-091500",
        veny_version="0.2.2",
        interpreter_tag="3.12",
        interpreter_path="/usr/bin/python3.12",
        packages=(venv_cache.PackageRecord("ruamel.yaml", "ruamel.yaml", "0.18.6", None),),
    )
    assert venv_cache.satisfies(manifest, [wanted("ruamel-yaml")], "3.12").matched is True


def test_satisfies_rejects_a_missing_package() -> None:
    """A venv without scipy cannot run a script that imports scipy."""
    result = venv_cache.satisfies(a_manifest(), [wanted("scipy")], "3.12")
    assert result.matched is False
    assert "scipy" in result.reason


def test_satisfies_rejects_an_unsatisfied_pin() -> None:
    """Ignoring specs would hand back a venv that violates the user's --reqs pin."""
    result = venv_cache.satisfies(a_manifest(), [wanted("numpy", ">=3.0")], "3.12")
    assert result.matched is False
    assert "numpy" in result.reason


def test_satisfies_rejects_a_pin_when_the_installed_version_is_unknown() -> None:
    """Reading 'unknown version' as 'satisfies' is the fail-open direction."""
    manifest = venv_cache.Manifest(
        schema_version=venv_cache.SCHEMA_VERSION,
        created="20260814-091500",
        veny_version="0.2.2",
        interpreter_tag="3.12",
        interpreter_path="/usr/bin/python3.12",
        packages=(venv_cache.PackageRecord("numpy", "numpy", None, None),),
    )
    assert venv_cache.satisfies(manifest, [wanted("numpy", ">=1.2")], "3.12").matched is False


def test_satisfies_accepts_a_package_with_no_pin_and_no_known_version() -> None:
    """An unknown version must not reject a package nobody pinned."""
    manifest = venv_cache.Manifest(
        schema_version=venv_cache.SCHEMA_VERSION,
        created="20260814-091500",
        veny_version="0.2.2",
        interpreter_tag="3.12",
        interpreter_path="/usr/bin/python3.12",
        packages=(venv_cache.PackageRecord("numpy", "numpy", None, None),),
    )
    assert venv_cache.satisfies(manifest, [wanted("numpy")], "3.12").matched is True


def test_name_allows_keeps_a_folder_listing_a_hyphenated_package() -> None:
    """This is the reported bug: 'ruamel-yaml' must not be read as 'ruamel' plus 'yaml'."""
    parsed = venv_cache.parse_folder_name("myenv-py3.12-20260814-091500-numpy_ruamel-yaml")
    assert parsed is not None
    assert venv_cache.name_allows(parsed, {"ruamel.yaml"}) is True


def test_name_allows_rejects_a_folder_that_cannot_hold_the_package() -> None:
    """Without this cheap reject every folder in the cache costs a manifest read."""
    parsed = venv_cache.parse_folder_name("myenv-py3.12-20260814-091500-numpy_ruamel-yaml")
    assert parsed is not None
    assert venv_cache.name_allows(parsed, {"scipy"}) is False


def test_name_allows_tolerates_summarised_names_within_the_count() -> None:
    """A folder that summarised three packages away may still hold the one wanted."""
    parsed = venv_cache.parse_folder_name("myenv-py3.12-20260814-091500-a_b_c_d_e_and_3_more")
    assert parsed is not None
    assert venv_cache.name_allows(parsed, {"a", "zzz"}) is True
    assert venv_cache.name_allows(parsed, {"w", "x", "y", "z"}) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_venv_cache.py -k "satisfies or name_allows"`
Expected: FAIL — `AttributeError: module 'venv_cache' has no attribute 'Wanted'`

- [ ] **Step 3: Write the implementation**

Add to `venv_cache.py`:

```python
from collections.abc import Iterable


@dataclass(frozen=True)
class Wanted:
    """One package this run needs.

    Attributes:
        pip_name: The pip name this run resolved, unnormalized.
        spec:     The --reqs version specifier, or None.
    """

    pip_name: str
    spec: str | None = None


@dataclass(frozen=True)
class MatchResult:
    """Whether a cached venv can serve this run, and why not when it cannot.

    Attributes:
        matched: True if the venv satisfies every wanted package.
        reason:  A short explanation, suitable for logging either way.
    """

    matched: bool
    reason: str


def satisfies(
    manifest: Manifest, wanted: Iterable[Wanted], interpreter_tag: str
) -> MatchResult:
    """Decide whether a cached virtual environment can serve this run.

    Packages are matched by normalized pip name. Import names are deliberately
    not part of this key: "does this venv hold the right distributions" is a
    question about distributions, and "does this venv work for this script" is
    answered afterwards by actually importing the names, in
    veny.check_packages_in_venv.

    A venv holding packages beyond those wanted still matches; extras are what
    the --smallest flag exists to discriminate between.

    Args:
        manifest:        The cached venv's manifest.
        wanted:          What this run needs.
        interpreter_tag: The "major.minor" tag this run is classified against.

    Returns:
        The decision, with a reason string for logging.
    """
    if manifest.interpreter_tag != interpreter_tag:
        return MatchResult(
            False,
            f"it was built for Python {manifest.interpreter_tag}, "
            f"and this run needs Python {interpreter_tag}",
        )
    held = {normalize_pip_name(record.pip_name): record for record in manifest.packages}
    for item in sorted(wanted, key=lambda entry: entry.pip_name):
        record = held.get(normalize_pip_name(item.pip_name))
        if record is None:
            return MatchResult(False, f"it does not have {item.pip_name}")
        if item.spec and not version_satisfies(record.installed_version, item.spec):
            return MatchResult(
                False,
                f"its {item.pip_name} {record.installed_version} "
                f"does not satisfy {item.spec}",
            )
    return MatchResult(True, "it has every required package")


def name_allows(parsed: FolderName, wanted_pip_names: Iterable[str]) -> bool:
    """Test whether a folder name leaves room for every wanted package.

    This is a cheap reject before reading a manifest, not a decision. A name
    lists at most MAX_NAMED_PACKAGES packages and summarises the rest, so a
    wanted package missing from the listed names may still be among the
    summarised ones.

    Args:
        parsed:           The parsed folder name.
        wanted_pip_names: The pip names this run needs, unnormalized.

    Returns:
        True if the folder could hold everything wanted.
    """
    missing = {normalize_pip_name(name) for name in wanted_pip_names} - parsed.packages
    return len(missing) <= parsed.unnamed_count
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test tests/test_venv_cache.py`
Expected: PASS

- [ ] **Step 5: Check the files you touched**

Run: `pixi run python -m ruff check venv_cache.py tests/test_venv_cache.py --statistics`
Run: `pixi run python -m mypy venv_cache.py tests/test_venv_cache.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add venv_cache.py tests/test_venv_cache.py
git commit -m "feat: decide venv reuse from the manifest, keyed on normalized pip names"
```

---

### Task 5: Build the venv with the interpreter the run was classified against

**Goal:** Make `setup_virtualenv` create the venv with `options.python_command` and name the folder through `venv_cache`, so the venv, the stdlib index, and the alias index all describe one interpreter.

**Files:**
- Modify: `veny.py` (add helpers near `pretty_packages_list`, `veny.py:3978`; change `setup_virtualenv`, `veny.py:4354-4365`)
- Create: `tests/test_venv_naming.py`

**Acceptance Criteria:**
- [ ] `venv_build_interpreter(options)` returns `options.python_command` when set and `sys.executable` when it is `""`
- [ ] `interpreter_tag(options)` returns the `major.minor` tag from `options.stdlib.python_version`
- [ ] `setup_virtualenv` creates the venv with the interpreter from `venv_build_interpreter`
- [ ] The venv directory is named `failed-<venv_name>-py<tag>-<timestamp>-<packages>` via `venv_cache.build_folder_name`

**Verify:** `pixi run test tests/test_venv_naming.py` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_venv_naming.py`:

```python
"""Tests for veny's venv naming and interpreter selection."""

import sys

import stdlib_index
import veny


def an_options(python_command: str) -> veny.Options:
    """Build an Options carrying only what these helpers read."""
    options = veny.Options()
    options.python_command = python_command
    options.stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )
    return options


def test_venv_build_interpreter_prefers_the_classified_interpreter() -> None:
    """Building with sys.executable installs into a venv for the wrong Python."""
    assert veny.venv_build_interpreter(an_options("/usr/bin/python3.12")) == "/usr/bin/python3.12"


def test_venv_build_interpreter_falls_back_when_no_preferred_python_was_found() -> None:
    """find_preferred_python_version() returns "" when the preferred Python is absent."""
    assert veny.venv_build_interpreter(an_options("")) == sys.executable


def test_interpreter_tag_comes_from_the_stdlib_index() -> None:
    """A tag probed separately could disagree with the index the imports were classified against."""
    assert veny.interpreter_tag(an_options("/usr/bin/python3.12")) == "3.12"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_venv_naming.py`
Expected: FAIL — `AttributeError: module 'veny' has no attribute 'venv_build_interpreter'`

- [ ] **Step 3: Write the implementation**

Add to `veny.py`, immediately after `pretty_packages_list` (`veny.py:3991`):

```python
def venv_build_interpreter(options: Options) -> str:
    """Return the interpreter that should create the virtual environment.

    options.python_command is what stdlib and alias resolution were probed
    against, so it is what the venv must be built with; building with
    sys.executable instead classifies imports for one Python and installs them
    for another. find_preferred_python_version() returns "" when the preferred
    Python is absent from PATH, and only then does the running interpreter serve.

    Args:
        options: Options object; reads options.python_command.

    Returns:
        A path or command name for the interpreter to build with.
    """
    return options.python_command or sys.executable


def interpreter_tag(options: Options) -> str:
    """Return the "major.minor" tag of the interpreter this run is classified against.

    Taken from the standard-library index rather than probed again, so the tag in
    a venv's folder name, the tag in its manifest, and the version whose stdlib
    names decided what needed installing can never disagree.

    Args:
        options: Options object; reads options.stdlib.

    Returns:
        A tag such as "3.12".
    """
    major, minor = options.stdlib.python_version
    return f"{major}.{minor}"
```

Then change `setup_virtualenv` (`veny.py:4356-4365`). Replace:

```python
    use_pip_list(options)
    options.pretty_list = pretty_packages_list(options)
    # Create a virtual environment directory that starts with "failed" in case the process fails. Only remove the "failed" part if this process completes successfully.
    options.set_venv_dir(options.my_dir / f"failed-{options.venv_name}-versionless-{options.timestamp}-{options.pretty_list}")

    write_requirements_file_with_extras(options)

    if not options.rawlog: logging.info("Creating virtual environment...")
    assert options.venv_dir is not None, "options.venv_dir must be set"
    subprocess.check_call([sys.executable, "-m", "venv", os.fspath(options.venv_dir)])
```

with:

```python
    use_pip_list(options)
    # The folder name is a cheap prefilter for the cache search; veny_manifest.json
    # inside the venv is the authority. venv_cache owns the encoding so a
    # hyphenated pip name cannot be mistaken for a field separator.
    folder_name = venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=interpreter_tag(options),
        timestamp=options.timestamp,
        pip_names=[record.pip_name for record in options.uninstalled_imports],
    )
    # Create a virtual environment directory that starts with "failed" in case the process fails. Only remove the "failed" part if this process completes successfully.
    options.set_venv_dir(options.my_dir / f"failed-{folder_name}")

    write_requirements_file_with_extras(options)

    if not options.rawlog: logging.info("Creating virtual environment...")
    assert options.venv_dir is not None, "options.venv_dir must be set"
    subprocess.check_call([venv_build_interpreter(options), "-m", "venv", os.fspath(options.venv_dir)])
```

Add the import beside the other local modules at the top of `veny.py` (they sit together near `import alias_index`):

```python
import venv_cache
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test tests/test_venv_naming.py`
Expected: PASS, 3 tests

- [ ] **Step 5: Confirm nothing else regressed**

Run: `pixi run test`
Expected: the full suite passes (153 tests before this plan, plus the new ones)

Run: `pixi run python -m ruff check veny.py --statistics`
Expected: the total is not higher than 302, the count recorded in PROGRESS.md.

Run: `pixi run python -m mypy veny.py venv_cache.py tests/test_venv_naming.py`
Expected: no *new* errors. `veny.py` carries pre-existing ones; compare against `git stash`-free baseline by noting the count before your change.

- [ ] **Step 6: Commit**

```bash
git add veny.py tests/test_venv_naming.py
git commit -m "fix: build the venv with the interpreter the imports were classified against"
```

---

### Task 6: One rename helper

**Goal:** Replace the inline `failed-` prefix removal with a `rename_venv` helper that renames a venv and rewrites the paths recorded inside it, so a later repair-driven rename reuses one code path.

**Files:**
- Modify: `veny.py` (extract from `veny.py:472-495`, add the helper near `setup_virtualenv`)
- Create: `tests/test_rename_venv.py`

**Acceptance Criteria:**
- [ ] `rename_venv(options, new_name)` renames the directory and calls `options.set_venv_dir` with the new path
- [ ] `pyvenv.cfg` and `download_packages.sh` have the old directory name replaced with the new one
- [ ] Renaming to the current name is a no-op
- [ ] `main()`'s success path calls `rename_venv` instead of renaming inline

**Verify:** `pixi run test tests/test_rename_venv.py` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rename_venv.py`:

```python
"""Tests for renaming a virtual environment in place."""

from pathlib import Path

import veny


def a_venv(root: Path, name: str) -> veny.Options:
    """Create a directory that looks enough like a venv for renaming."""
    options = veny.Options()
    venv_dir = root / name
    venv_dir.mkdir(parents=True, exist_ok=True)
    (venv_dir / "pyvenv.cfg").write_text(
        "home = /usr/bin\n"
        f"command = /usr/bin/python3.12 -m venv {venv_dir}\n"
    )
    (venv_dir / "download_packages.sh").write_text(
        f"#!/bin/sh\n{venv_dir}/bin/pip download -r {venv_dir}/requirements.txt\n"
    )
    options.set_venv_dir(venv_dir)
    return options


def test_rename_venv_moves_the_directory(tmp_path: Path) -> None:
    """A venv that keeps its 'failed-' name is never found by the cache search."""
    options = a_venv(tmp_path, "failed-myenv-py3.12-20260814-091500-numpy")
    veny.rename_venv(options, "myenv-py3.12-20260814-091500-numpy")
    assert (tmp_path / "myenv-py3.12-20260814-091500-numpy").is_dir()
    assert not (tmp_path / "failed-myenv-py3.12-20260814-091500-numpy").exists()
    assert options.venv_dir == tmp_path / "myenv-py3.12-20260814-091500-numpy"


def test_rename_venv_rewrites_the_recorded_paths(tmp_path: Path) -> None:
    """A renamed venv that still records its old path is broken, not merely slow."""
    options = a_venv(tmp_path, "failed-myenv-py3.12-20260814-091500-numpy")
    veny.rename_venv(options, "myenv-py3.12-20260814-091500-numpy")
    config = (options.venv_dir / "pyvenv.cfg").read_text()
    script = (options.venv_dir / "download_packages.sh").read_text()
    assert "failed-" not in config
    assert "failed-" not in script
    assert "myenv-py3.12-20260814-091500-numpy" in config
    assert "home = /usr/bin" in config


def test_rename_venv_to_the_same_name_is_a_no_op(tmp_path: Path) -> None:
    """Renaming a directory onto itself must not raise or lose the venv."""
    options = a_venv(tmp_path, "myenv-py3.12-20260814-091500-numpy")
    veny.rename_venv(options, "myenv-py3.12-20260814-091500-numpy")
    assert options.venv_dir.is_dir()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_rename_venv.py`
Expected: FAIL — `AttributeError: module 'veny' has no attribute 'rename_venv'`

- [ ] **Step 3: Write the implementation**

Add to `veny.py`, after `setup_virtualenv`:

```python
def rename_venv(options: Options, new_name: str) -> None:
    """Rename a virtual environment directory and fix the paths recorded inside it.

    A venv records its own location in pyvenv.cfg and in the download script, so
    a rename that touches only the directory leaves a venv that points at a path
    that no longer exists. Two callers need this: dropping the "failed-" prefix
    once a run succeeds, and re-naming a venv whose package list changed when
    verify_and_repair_imports repaired a wrongly resolved pip name.

    Args:
        options:  Options object; reads and updates options.venv_dir.
        new_name: The directory's new name, not a path.

    Returns:
        None. Failure to rewrite a recorded path is logged, not raised: the venv
        has already moved and the run continues.
    """
    assert options.venv_dir is not None, "options.venv_dir must be set"
    old_dir  = options.venv_dir
    new_dir  = old_dir.with_name(new_name)
    if new_dir == old_dir:
        return
    old_dir.rename(new_dir)
    options.set_venv_dir(new_dir)
    for path in (options.venv_dir / "pyvenv.cfg", options.download_script_path):
        try:
            contents = path.read_text()
        except OSError as exc:
            logging.warning("Could not read %s after renaming the venv (%s).", path, exc)
            continue
        updated = contents.replace(old_dir.name, new_dir.name)
        if updated == contents:
            continue
        try:
            path.write_text(updated)
        except OSError as exc:
            logging.warning("Could not update %s after renaming the venv (%s).", path, exc)
```

Then replace the inline rename in `main()` (`veny.py:472-495`). Replace:

```python
            if options.venv_dir.name.startswith("failed-") and options.simultaneous_success:
                # If the program has made it to this point, it has run successfully, so the venv directory can be renamed because it DIDN'T fail.
                new = options.venv_dir.with_name(options.venv_dir.name.removeprefix("failed-"))
                if new != options.venv_dir:
                    options.venv_dir.rename(new)
                options.set_venv_dir(new)
                cfg_file_path = options.venv_dir / "pyvenv.cfg"
                with open(cfg_file_path, "r") as file:
                    lines = file.readlines()
                modified_lines = []
                for line in lines:
                    if line.startswith("command = "):
                        line = line.replace(os.sep+"failed-", os.sep)
                    modified_lines.append(line)
                with open(cfg_file_path, "w") as file:
                    file.writelines(modified_lines)
                with open(options.download_script_path, "r") as file:
                    lines = file.readlines()
                modified_lines = []
                for line in lines:
                    line = line.replace(os.sep+"failed-", os.sep)
                    modified_lines.append(line)
                with open(options.download_script_path , "w") as file:
                    file.writelines(modified_lines)
```

with:

```python
            if options.venv_dir.name.startswith("failed-") and options.simultaneous_success:
                # If the program has made it to this point, it has run successfully, so the venv directory can be renamed because it DIDN'T fail.
                rename_venv(options, options.venv_dir.name.removeprefix("failed-"))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test tests/test_rename_venv.py`
Expected: PASS, 3 tests

- [ ] **Step 5: Confirm nothing else regressed**

Run: `pixi run test`
Run: `pixi run python -m ruff check veny.py --statistics`
Expected: full suite green; ruff count not higher than before this task.

- [ ] **Step 6: Commit**

```bash
git add veny.py tests/test_rename_venv.py
git commit -m "refactor: rename a venv through one helper that fixes its recorded paths"
```

---

### Task 7: Write the manifest after installing and repairing

**Goal:** Probe the finished venv for installed versions, write its manifest, and rename the folder when repairs changed the package set.

**Files:**
- Modify: `veny.py` (add the probe and the manifest build near `verify_and_repair_imports`, `veny.py:4301`; call them at the end of `setup_virtualenv`)
- Create: `tests/test_manifest_writing.py`

**Acceptance Criteria:**
- [ ] `installed_versions_in_venv(options)` returns a `{normalized pip name: version}` mapping and `{}` on any failure
- [ ] `manifest_for(options, versions)` builds a `venv_cache.Manifest` from the final records, the interpreter, `veny.__version__`, and `options.extra_requirements`
- [ ] `setup_virtualenv` writes the manifest after `verify_and_repair_imports`
- [ ] When the repaired pip-name set no longer matches the folder name, the folder is renamed before the manifest is written

**Verify:** `pixi run test tests/test_manifest_writing.py` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_manifest_writing.py`:

```python
"""Tests for building a venv's manifest from its final state."""

import stdlib_index
import veny
import venv_cache
from alias_index import ResolvedImport


def an_options() -> veny.Options:
    """Build an Options carrying the fields manifest_for reads."""
    options = veny.Options()
    options.python_command = "/usr/bin/python3.12"
    options.stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )
    options.timestamp = "20260814-091500"
    options.uninstalled_imports = {
        ResolvedImport("yaml", "PyYAML"),
        ResolvedImport("numpy", "numpy"),
    }
    options.extra_requirements = {"numpy": ">=1.2"}
    return options


def test_manifest_for_records_versions_and_specs() -> None:
    """A manifest without versions cannot answer whether a pin is satisfied."""
    manifest = veny.manifest_for(an_options(), {"pyyaml": "6.0.2", "numpy": "2.1.3"})
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version == "6.0.2"
    assert by_pip["PyYAML"].requested_spec is None
    assert by_pip["numpy"].installed_version == "2.1.3"
    assert by_pip["numpy"].requested_spec == ">=1.2"
    assert manifest.interpreter_tag == "3.12"
    assert manifest.interpreter_path == "/usr/bin/python3.12"
    assert manifest.schema_version == venv_cache.SCHEMA_VERSION
    assert manifest.veny_version == veny.__version__


def test_manifest_for_records_an_unknown_version_as_none() -> None:
    """Inventing a version here would let an unsatisfiable pin look satisfied."""
    manifest = veny.manifest_for(an_options(), {})
    assert all(record.installed_version is None for record in manifest.packages)


def test_manifest_for_keys_versions_by_normalized_name() -> None:
    """pip reports 'PyYAML'; the record spells it differently; both name one project."""
    manifest = veny.manifest_for(an_options(), {"py-yaml": "6.0.2"})
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version is None
    manifest = veny.manifest_for(an_options(), {"pyyaml": "6.0.2"})
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version == "6.0.2"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_manifest_writing.py`
Expected: FAIL — `AttributeError: module 'veny' has no attribute 'manifest_for'`

- [ ] **Step 3: Write the implementation**

Add to `veny.py`, after `verify_and_repair_imports`:

```python
_VERSION_PROBE_CODE = (
    "import json\n"
    "from importlib.metadata import distributions\n"
    "print(json.dumps({d.metadata['Name']: d.version for d in distributions()"
    " if d.metadata['Name']}))\n"
)


def installed_versions_in_venv(options: Options) -> dict[str, str]:
    """Ask a virtual environment which versions it actually has.

    This is what the manifest records, rather than what was requested or what
    pip printed: only the venv itself knows what ended up installed, including
    versions pip chose for unpinned packages.

    Args:
        options: Options object; reads options.venv_python.

    Returns:
        A mapping of normalized pip name to version. Empty on any failure --
        a version veny could not read is recorded as unknown, which makes any
        later pin check on that package fail closed.
    """
    command = [os.fspath(options.venv_python), "-c", _VERSION_PROBE_CODE]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        logging.warning("Could not list installed versions in the venv (%s).", exc)
        return {}
    if result.returncode != 0:
        logging.warning("Could not list installed versions in the venv: %s", result.stderr.strip())
        return {}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logging.warning("Could not read the installed versions reported by the venv (%s).", exc)
        return {}
    return {venv_cache.normalize_pip_name(name): str(version)
            for name, version in payload.items()}


def manifest_for(options: Options, versions: dict[str, str]) -> venv_cache.Manifest:
    """Build the manifest describing a finished virtual environment.

    Args:
        options:  Options object; reads options.uninstalled_imports (after any
                  repairs), options.extra_requirements, and the interpreter.
        versions: Installed versions, keyed by normalized pip name.

    Returns:
        The manifest to write into the venv.
    """
    packages = tuple(
        venv_cache.PackageRecord(
            import_name=record.import_name,
            pip_name=record.pip_name,
            installed_version=versions.get(venv_cache.normalize_pip_name(record.pip_name)),
            requested_spec=options.extra_requirements.get(record.pip_name),
        )
        for record in sorted(options.uninstalled_imports, key=lambda r: r.pip_name)
    )
    return venv_cache.Manifest(
        schema_version=venv_cache.SCHEMA_VERSION,
        created=options.timestamp,
        veny_version=__version__,
        interpreter_tag=interpreter_tag(options),
        interpreter_path=venv_build_interpreter(options),
        packages=packages,
    )


def record_venv_state(options: Options) -> None:
    """Rename the venv if repairs changed its packages, then write its manifest.

    verify_and_repair_imports can replace a record whose pip_name was wrong, so
    the folder name written before installing may list a package the venv does
    not have. The name is only a prefilter, but a stale one rejects a venv the
    manifest would accept -- so the name is brought back into agreement first.

    Args:
        options: Options object; reads the final records and updates
                 options.venv_dir if a rename happens.

    Returns:
        None.
    """
    assert options.venv_dir is not None, "options.venv_dir must be set"
    wanted_name = venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=interpreter_tag(options),
        timestamp=options.timestamp,
        pip_names=[record.pip_name for record in options.uninstalled_imports],
    )
    prefix       = "failed-" if options.venv_dir.name.startswith("failed-") else ""
    if options.venv_dir.name != prefix + wanted_name:
        if not options.rawlog:
            logging.info("Repairs changed this venv's packages; renaming it to %s.",
                         prefix + wanted_name)
        rename_venv(options, prefix + wanted_name)
    venv_cache.write_manifest(options.venv_dir, manifest_for(options, installed_versions_in_venv(options)))
```

Then call it from `setup_virtualenv` (`veny.py:4388-4390`), replacing:

```python
    verify_and_repair_imports(options)
    # Check that all packages can be imported in the venv.
    return check_packages_in_venv(options)
```

with:

```python
    verify_and_repair_imports(options)
    # The manifest records the venv's final state, so it is written after any
    # repair -- it must describe what really provided each import, not what was
    # first attempted.
    record_venv_state(options)
    # Check that all packages can be imported in the venv.
    return check_packages_in_venv(options)
```

Confirm `json` is imported at the top of `veny.py`; add `import json` beside the other standard-library imports if it is not.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test tests/test_manifest_writing.py`
Expected: PASS, 3 tests

- [ ] **Step 5: Confirm nothing else regressed**

Run: `pixi run test`
Run: `pixi run python -m ruff check veny.py --statistics`

- [ ] **Step 6: Commit**

```bash
git add veny.py tests/test_manifest_writing.py
git commit -m "feat: record each venv's final state in a manifest"
```

---

### Task 8: Match cached venvs from the manifest

**Goal:** Rewrite the cache search in `find_match_dir_in_cache` to parse folder names through `venv_cache`, reject cheaply on the name, and decide on the manifest.

**Files:**
- Modify: `veny.py` (`find_match_dir_in_cache`, `veny.py:4609-4647`; add `wanted_packages` beside it)
- Create: `tests/test_cache_search.py`

**Acceptance Criteria:**
- [ ] `wanted_packages(options)` builds `venv_cache.Wanted` entries from the records and `options.extra_requirements`
- [ ] `cache_candidates(options, folders)` returns only folders whose name parses, whose tag matches, whose name allows the wanted packages, and whose manifest satisfies the run
- [ ] A folder listing a hyphenated pip name is kept for a run wanting that package
- [ ] A folder with no manifest is skipped
- [ ] `requirements.txt` is no longer read for matching

**Verify:** `pixi run test tests/test_cache_search.py` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cache_search.py`:

```python
"""Tests for choosing cached virtual environments."""

from pathlib import Path

import stdlib_index
import veny
import venv_cache
from alias_index import ResolvedImport


def an_options(records: set[ResolvedImport]) -> veny.Options:
    """Build an Options carrying what the cache search reads."""
    options = veny.Options()
    options.stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )
    options.uninstalled_imports = records
    options.extra_requirements = {}
    return options


def a_cached_venv(root: Path, name: str, packages: list[venv_cache.PackageRecord],
                  tag: str = "3.12") -> Path:
    """Create a cached venv directory with a manifest."""
    venv_dir = root / name
    venv_dir.mkdir(parents=True, exist_ok=True)
    venv_cache.write_manifest(
        venv_dir,
        venv_cache.Manifest(
            schema_version=venv_cache.SCHEMA_VERSION,
            created="20260814-091500",
            veny_version="0.2.2",
            interpreter_tag=tag,
            interpreter_path="/usr/bin/python3.12",
            packages=tuple(packages),
        ),
    )
    return venv_dir


def test_a_hyphenated_package_does_not_disqualify_its_own_venv(tmp_path: Path) -> None:
    """This is the reported bug: 'ruamel-yaml' read as 'ruamel' plus 'yaml' rejects a good venv."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-ruamel-yaml",
        [venv_cache.PackageRecord("ruamel.yaml", "ruamel-yaml", "0.18.6", None)],
    )
    options = an_options({ResolvedImport("ruamel.yaml", "ruamel-yaml")})
    assert veny.cache_candidates(options, [venv_dir]) == [venv_dir]


def test_a_venv_without_a_manifest_is_skipped(tmp_path: Path) -> None:
    """Pre-manifest venvs must be rebuilt, not matched on their names alone."""
    venv_dir = tmp_path / "myenv-py3.12-20260814-091500-numpy"
    venv_dir.mkdir()
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert veny.cache_candidates(options, [venv_dir]) == []


def test_a_venv_for_another_interpreter_is_skipped(tmp_path: Path) -> None:
    """A 3.13 venv cannot serve a run classified against 3.12's standard library."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.13-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
        tag="3.13",
    )
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert veny.cache_candidates(options, [venv_dir]) == []


def test_a_venv_missing_a_package_is_skipped(tmp_path: Path) -> None:
    """Matching on the name alone would accept a venv whose manifest disagrees."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    options = an_options({ResolvedImport("numpy", "numpy"), ResolvedImport("scipy", "scipy")})
    assert veny.cache_candidates(options, [venv_dir]) == []


def test_a_pin_is_checked_against_the_installed_version(tmp_path: Path) -> None:
    """Ignoring --reqs pins hands back a venv that violates them."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "1.0.0", ">=1.2")],
    )
    options = an_options({ResolvedImport("numpy", "numpy")})
    options.extra_requirements = {"numpy": ">=1.2"}
    assert veny.cache_candidates(options, [venv_dir]) == []
    options.extra_requirements = {"numpy": ">=0.9"}
    assert veny.cache_candidates(options, [venv_dir]) == [venv_dir]


def test_wanted_packages_carries_the_requested_specs() -> None:
    """A spec dropped here makes every pin invisible to matching."""
    options = an_options({ResolvedImport("numpy", "numpy")})
    options.extra_requirements = {"numpy": ">=1.2"}
    assert veny.wanted_packages(options) == [venv_cache.Wanted("numpy", ">=1.2")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_cache_search.py`
Expected: FAIL — `AttributeError: module 'veny' has no attribute 'cache_candidates'`

- [ ] **Step 3: Write the implementation**

Add to `veny.py`, before `find_match_dir_in_cache`:

```python
def wanted_packages(options: Options) -> list[venv_cache.Wanted]:
    """Describe what this run needs, for matching against a cached venv.

    Args:
        options: Options object; reads options.uninstalled_imports and
                 options.extra_requirements.

    Returns:
        One entry per record, carrying its pip name and any --reqs spec.
    """
    return [venv_cache.Wanted(pip_name=record.pip_name,
                              spec=options.extra_requirements.get(record.pip_name))
            for record in sorted(options.uninstalled_imports, key=lambda r: r.pip_name)]


def cache_candidates(options: Options, folders: list[Path]) -> list[Path]:
    """Filter cached venv folders down to those that can serve this run.

    The folder name is a cheap reject; veny_manifest.json is the decision. A
    folder with no readable manifest is skipped, which is what retires every
    virtual environment built before manifests existed.

    Args:
        options: Options object; reads the records, the specs, and the tag.
        folders: Candidate directories, already filtered by name prefix.

    Returns:
        The folders that match, in the order given.
    """
    tag    = interpreter_tag(options)
    wanted = wanted_packages(options)
    names  = [item.pip_name for item in wanted]
    matches: list[Path] = []
    for folder in folders:
        parsed = venv_cache.parse_folder_name(folder.name)
        if parsed is None:
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug("Skipping %s: not a venv folder name veny wrote.", os.fspath(folder))
            continue
        if parsed.interpreter_tag != tag or not venv_cache.name_allows(parsed, names):
            continue
        manifest = venv_cache.read_manifest(folder)
        if manifest is None:
            if not options.rawlog:
                logging.info("Skipping the cached venv %s: it has no readable manifest.",
                             os.fspath(folder))
            continue
        result = venv_cache.satisfies(manifest, wanted, tag)
        if not result.matched:
            if not options.rawlog:
                logging.info("Skipping the cached venv %s because %s.",
                             os.fspath(folder), result.reason)
            continue
        matches.append(folder)
    return matches
```

Then replace the folder-scanning block in `find_match_dir_in_cache` (`veny.py:4609-4647`, from the "Search for all venv_name folders" comment through the construction of `final_venv_folders`) with:

```python
    if not options.rawlog: logging.info("Checking the cache for a virtual environment with all the required packages...")
    all_venv_folders = [f for f in options.my_dir.iterdir()
                        if ud.safe_is_dir(f) and f.name.startswith(options.venv_name)]
    final_venv_folders: dict[Path, dict[str, int]] = {}
    for folder in cache_candidates(options, all_venv_folders):
        parsed = venv_cache.parse_folder_name(folder.name)
        assert parsed is not None, "cache_candidates only returns folders whose names parse"
        manifest = venv_cache.read_manifest(folder)
        assert manifest is not None, "cache_candidates only returns folders with a manifest"
        final_venv_folders[folder] = {"timestamp"    : int(parsed.timestamp.replace("-", "")),
                                      "num_packages" : len(manifest.packages)}
```

Note what this deletes: the `pretty_list` name splitting, the `known_packages` reconstruction, and the `requirements.txt` read. `num_packages` now counts what the venv holds rather than the lines of a requirements file, which is the number `--smallest` was always trying to compare.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test tests/test_cache_search.py`
Expected: PASS, 6 tests

- [ ] **Step 5: Confirm nothing else regressed**

Run: `pixi run test`
Run: `pixi run python -m ruff check veny.py --statistics`

- [ ] **Step 6: Commit**

```bash
git add veny.py tests/test_cache_search.py
git commit -m "feat: choose cached venvs from their manifests"
```

---

### Task 9: One authority for the last-used venv

**Goal:** Make `check_venv_dir` take a directory and ask that directory's manifest, so the `--last-used` path stops trusting records inside an options JSON.

**Files:**
- Modify: `veny.py` (`check_venv_dir`, `veny.py:4537-4576`; its four call sites in `find_match_dir_in_cache`)
- Modify: `tests/test_cache_search.py`

**Acceptance Criteria:**
- [ ] `check_venv_dir(options, venv_dir)` reads the manifest at `venv_dir` and applies `venv_cache.satisfies`
- [ ] It returns False for a missing directory and for a missing manifest, without raising
- [ ] It still confirms a match with `check_packages_in_venv(source_names=source_import_names(options))`
- [ ] All four call sites pass a directory; the `copy.deepcopy(options)` dance is gone
- [ ] The `--last-used` path uses the JSON only for `venv_dir`

**Verify:** `pixi run test tests/test_cache_search.py` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cache_search.py`:

```python
def test_check_venv_dir_rejects_a_directory_with_no_manifest(tmp_path: Path) -> None:
    """The last-used pointer can outlive the venv it points at."""
    venv_dir = tmp_path / "myenv-py3.12-20260814-091500-numpy"
    venv_dir.mkdir()
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert veny.check_venv_dir(options, venv_dir) is False


def test_check_venv_dir_rejects_a_missing_directory(tmp_path: Path) -> None:
    """A deleted venv must be a cache miss, not an exception."""
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert veny.check_venv_dir(options, tmp_path / "gone") is False


def test_check_venv_dir_rejects_a_manifest_that_does_not_match(tmp_path: Path) -> None:
    """Reusing a venv that lacks a package fails at the user's runtime."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    options = an_options({ResolvedImport("scipy", "scipy")})
    assert veny.check_venv_dir(options, venv_dir) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_cache_search.py -k check_venv_dir`
Expected: FAIL — `TypeError: check_venv_dir() takes ... ` (it currently expects a second Options)

- [ ] **Step 3: Write the implementation**

Replace `check_venv_dir` (`veny.py:4537-4576`) with:

```python
def check_venv_dir(options: Options, venv_dir: str | os.PathLike[str]) -> bool:
    """Check whether a cached venv directory can serve this run.

    The venv's own manifest is the authority. An options JSON written by an
    earlier run says what that run wanted, not what the venv holds, and its
    records compare by exact spelling -- so a venv built when "yaml" resolved to
    "PyYAML" was rejected by a run spelling it "pyyaml". Asking the manifest puts
    every candidate, last-used or not, through one comparison.

    Args:
        options:  Options object containing the current settings.
        venv_dir: The cached virtual environment directory.

    Returns:
        True if the venv holds what this run needs, for the right interpreter,
        and its imports really import.
    """
    venv_dir = ud.ensure_path(venv_dir)
    if not ud.safe_is_dir(venv_dir):
        if not options.rawlog:
            logging.info("The cached venv directory %s is no longer there.", os.fspath(venv_dir))
        return False
    manifest = venv_cache.read_manifest(venv_dir)
    if manifest is None:
        if not options.rawlog:
            logging.info("The cached venv directory %s has no readable manifest.",
                         os.fspath(venv_dir))
        return False
    result = venv_cache.satisfies(manifest, wanted_packages(options), interpreter_tag(options))
    if not result.matched:
        if not options.rawlog:
            logging.info("The cached venv directory %s cannot be used because %s.",
                         os.fspath(venv_dir), result.reason)
        return False
    # The manifest says the packages are there; this says the imports really
    # import. source_names comes from the live run, because the venv was built
    # for whatever the run that created it wrote.
    if check_packages_in_venv(options, venv_dir=venv_dir,
                              source_names=source_import_names(options)):
        return True
    logging.error("The cached venv directory %s failed check_packages_in_venv.",
                  os.fspath(venv_dir))
    return False
```

Update the four call sites in `find_match_dir_in_cache`:

```python
        options_last_used = load_last_used_options(options)
        if options_last_used is not None and options_last_used.venv_dir is not None \
           and check_venv_dir(options, options_last_used.venv_dir):
            return ud.ensure_path(options_last_used.venv_dir)
```

and, for each of the `--latest`, `--oldest`, and `--smallest` branches, replace the `copy.deepcopy(options)` block with the direct form — shown here for `--latest`, and written the same way for the other two with `oldest_venv` / `smallest_venv` and their own log wording:

```python
            latest_venv_folder: Path | None = latest_venv(final_venv_folders)
            if latest_venv_folder is None:
                if not options.rawlog:
                    logging.error("Could not determine the latest venv folder from the cache.")
                return None
            if check_venv_dir(options, latest_venv_folder):
                return latest_venv_folder
            if not options.rawlog:
                logging.error("The latest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
            return None
```

If `copy` is left unused in `veny.py` after this, remove the `import copy`; check with `rg -n "copy\." veny.py` first.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test tests/test_cache_search.py`
Expected: PASS

- [ ] **Step 5: Confirm nothing else regressed**

Run: `pixi run test`
Run: `pixi run python -m ruff check veny.py --statistics`
Run: `pixi run python -m mypy veny.py venv_cache.py`

- [ ] **Step 6: Commit**

```bash
git add veny.py tests/test_cache_search.py
git commit -m "refactor: judge every cached venv, last-used included, by its manifest"
```

---

### Task 10: Remove what the manifest replaced

**Goal:** Delete the now-unused name-building and requirements-comparison leftovers, and update the documentation.

**Files:**
- Modify: `veny.py` (`pretty_packages_list`, `veny.py:3978`; `options.pretty_list`, `veny.py:70`; `options.pretty_requirements`, `veny.py:88` and `veny.py:4103-4137`)
- Modify: `README.md`
- Modify: `PROGRESS.md`

**Acceptance Criteria:**
- [ ] Every symbol deleted has no remaining reference (`rg` shows none)
- [ ] `write_requirements_file_with_extras` still writes `requirements.txt` for pip, minus the dead `pretty_requirements` accumulation
- [ ] README describes the manifest and the folder-name format
- [ ] PROGRESS.md records the new gotchas and the remaining deferred items

**Verify:** `pixi run test` → full suite passes; `rg -n "pretty_list|pretty_requirements|pretty_packages_list" veny.py` → no matches

**Steps:**

- [ ] **Step 1: Confirm each symbol is dead before deleting it**

Run:
```bash
rg -n "pretty_packages_list|pretty_list" veny.py univ_defs.py tests/
rg -n "pretty_requirements" veny.py univ_defs.py tests/
```
Expected: only the definitions and the assignments inside `write_requirements_file_with_extras` — no readers. If anything else reads them, stop and keep that symbol.

- [ ] **Step 2: Delete them**

- Remove `pretty_packages_list` entirely (`veny.py:3978-3991`).
- Remove `self.pretty_list` (`veny.py:70`) and `self.pretty_requirements` (`veny.py:88`).
- In `write_requirements_file_with_extras`, remove the `replacements` list, the `pretty_version_spec` handling, the `pretty_package` variables, and the trailing accumulation, keeping only the loop that writes each line to the file.

- [ ] **Step 3: Run the suite**

Run: `pixi run test`
Expected: PASS. If a test fails, a symbol was not dead — restore it and note why in PROGRESS.md.

- [ ] **Step 4: Update README.md**

Add to the project structure section a line for `venv_cache.py` ("folder naming, manifests, and matching for cached virtual environments"), and document, in the section describing the cache:

```markdown
Each cached virtual environment carries a `veny_manifest.json` recording the
interpreter it was built for and, per package, the import name, the pip name,
the installed version, and any `--reqs` pin. veny matches a cached environment
against that file; the folder name
(`<venv_name>-py<major.minor>-<YYYYMMDD>-<HHMMSS>-<packages>`) is only a quick
filter. Environments built by earlier versions of veny have no manifest and are
rebuilt once.
```

- [ ] **Step 5: Update PROGRESS.md**

- Point **Current work** at this plan and set the next action.
- Add to **Gotchas**: `venv_cache.normalize_pip_name` duplicates `alias_index.normalize_pip_name` deliberately (one-way imports), and the two must be changed together; the folder name is a prefilter only, and a stale one costs a rebuild, which is why `record_venv_state` renames after repairs; `version_satisfies` refuses every non-numeric version form, so a pre-release install always rebuilds.
- Add to **Deferred items**: full PEP 440 support in the comparator; garbage collection of stale venvs in `~/veny`, including the pre-manifest ones this work orphans.

- [ ] **Step 6: Commit**

```bash
git add veny.py README.md PROGRESS.md
git commit -m "refactor: drop the name and requirements plumbing the manifest replaced"
```

---

### Task 11: Prove it on a real run

**Goal:** Confirm by mutation and by one live run that the new guards are load-bearing and that a real cached venv is reused.

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Modify: `PROGRESS.md` (record what the run showed)
- Test: no new test files; this task runs the existing suite and the real program

**Acceptance Criteria:**
- [ ] Deleting the interpreter-tag check in `venv_cache.satisfies` makes at least one test fail (restore it afterwards)
- [ ] Deleting the `installed_version is None` fail-closed path in `version_satisfies` makes at least one test fail (restore it afterwards)
- [ ] Deleting the rename in `record_venv_state` makes at least one test fail, or is recorded in PROGRESS.md as unguarded with the reason
- [ ] A first real run against a script importing a hyphenated-pip-name package builds a venv containing `veny_manifest.json`, and the manifest names that package with a version
- [ ] A second real run of the same script reports reusing that venv (`Using existing virtual environment:`) and does not create a second folder in `~/veny`
- [ ] The captured output of both runs, and the `ls ~/veny` before and after, are pasted into the task's completion notes

**Verify:** `pixi run test` → full suite passes, and the two real runs behave as described above

**Steps:**

- [ ] **Step 1: Mutation-check the new guards**

For each guard below: delete it, run the suite, confirm a failure, restore it, confirm green again.

```bash
pixi run test tests/test_venv_cache.py
```
Guards: the `manifest.interpreter_tag != interpreter_tag` early return in `satisfies`; the `installed is None` term in `version_satisfies`; the rename branch in `record_venv_state`.

A guard whose deletion leaves the suite green has no test — write one before closing this task, or record it in PROGRESS.md as knowingly unguarded, with the reason.

- [ ] **Step 2: Write the throwaway script**

```bash
mkdir -p /tmp/veny-check
printf 'import ruamel.yaml\nprint("ok", ruamel.yaml.__name__)\n' \
  > /tmp/veny-check/check.py
```

- [ ] **Step 3: Record the cache directory before the run**

```bash
ls ~/veny | tee /tmp/veny-check/before.txt
```

- [ ] **Step 4: First run — builds the venv**

```bash
pixi run python veny.py /tmp/veny-check/check.py
```
Expected: the script prints `ok ruamel.yaml`, and a new folder appears in `~/veny` whose name contains `py3.` and `ruamel-yaml`.

- [ ] **Step 5: Inspect the manifest**

```bash
cat ~/veny/myenv-py3*-*-ruamel-yaml/veny_manifest.json
```
Expected: `schema_version` 1, an `interpreter_tag` matching the Python that ran, and a package entry whose `pip_name` is the hyphenated name with a non-null `installed_version`.

- [ ] **Step 6: Second run — must reuse**

```bash
pixi run python veny.py /tmp/veny-check/check.py
ls ~/veny | tee /tmp/veny-check/after.txt
diff /tmp/veny-check/before.txt /tmp/veny-check/after.txt
```
Expected: the log says `Using existing virtual environment:` and names the folder from step 4; the diff shows exactly one added folder across both runs, not two.

If a second folder appears, the cache still misses. Do not close this task — the prefilter, the manifest, or the tag is disagreeing with what was written, and the reason belongs in PROGRESS.md before any further work.

- [ ] **Step 7: Record the outcome and commit**

Paste both runs' relevant log lines and the `diff` into PROGRESS.md under **Current work**, then:

```bash
git add PROGRESS.md
git commit -m "docs: record the live verification of manifest-based venv matching"
```

---

## Self-Review

**Spec coverage:** module boundary (Task 1), folder name (Tasks 1, 5), manifest schema (Tasks 2, 7), matching (Tasks 4, 8, 9), version comparison (Task 3), interpreter fix (Task 5), rename (Tasks 6, 7), creation flow (Tasks 5, 7), search flow (Task 8), `--last-used` (Task 9), error handling (Tasks 2, 3, 8, 9), migration by skipping (Task 8), testing (every task), documentation and dead code (Task 10), live verification and mutation (Task 11). The spec's "Consequences" note about `pretty_requirements` is Task 10, step 1, guarded by a check that it is really unread.

**Type consistency:** `venv_cache.Wanted(pip_name, spec)`, `venv_cache.PackageRecord(import_name, pip_name, installed_version, requested_spec)`, `venv_cache.Manifest(schema_version, created, veny_version, interpreter_tag, interpreter_path, packages)`, `venv_cache.FolderName(venv_name, interpreter_tag, timestamp, packages, unnamed_count)`, and `venv_cache.MatchResult(matched, reason)` are used with those exact fields in Tasks 4, 7, 8, and 9. `check_venv_dir(options, venv_dir)` has one signature after Task 9 and all four call sites use it.
