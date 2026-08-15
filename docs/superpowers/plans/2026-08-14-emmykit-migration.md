# emmykit Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the local 9,757-line `univ_defs.py` with the published `emmykit` package as a hard dependency of veny, moving veny's own JSON serialization into a type registry that emmykit gains in 0.4.0.

**Architecture:** `veny.py` is the only production consumer of the utility layer, so the swap is a single import line plus a width-preserving `ud.` → `ek.` rename at 106 call sites. veny's own types are registered with emmykit's new JSON type registry from a small new module, `veny_json_types.py`, rather than being patched into the utility library as they are today. Five helper scripts veny writes but never runs are dropped entirely; they move to the `killett/utilities` repository under a separate prompt.

**Tech Stack:** Python 3.12-3.13, pixi (PyPI dependency — emmykit is not on conda-forge), pytest, ruff, mypy.

**Global Constraints:**
- **Never run ruff-format or pre-commit's `ruff`/`ruff-format` hooks against `veny.py`.** A trial run once rewrote ~2,000 lines of its hand-aligned formatting. Scope every ruff invocation: `ruff check <file>`.
- `pixi run lint` and `pixi run typecheck` fail repo-wide on pre-existing debt. Gate on `ruff check <touched file> --statistics` before/after and `mypy <touched files>`, never the bare tasks.
- `.git/hooks/pre-commit` is not installed. Run `pixi run pre-commit run --files <paths>` by hand before each commit.
- The `ud` → `ek` rename must be width-preserving: both aliases are two characters, so `veny.py`'s hand-aligned comment and value columns must be byte-identical apart from the renamed tokens.
- One-way import discipline is unchanged: `alias_index.py`, `pypi_client.py`, `stdlib_index.py` and `venv_cache.py` import nothing from `veny` or the utility layer.
- Baseline before any change: **234 tests passing** (`pixi run test`).

**User decisions (already made):**
- emmykit is a **hard dependency**; veny exits with an install message if it is missing. This supersedes the 2026-08-12 "no third-party dependency" decision (recorded in PROGRESS.md).
- Serialization of veny's types lives in an **extension hook inside emmykit** (0.4.0), not in a veny-side wrapper and not as a boundary conversion.
- The alias is renamed **`ud` → `ek`**, not kept as `ud`.
- The five helper scripts move to **`killett/utilities`**; veny stops writing them and the `sys.path` shim is deleted outright.
- **Build now, merge after emmykit 0.4.0 exists** — no known-degraded state reaches `main`.

---

### Task 0: Release emmykit 0.4.0 (external, blocks Tasks 3-7)

**Goal:** emmykit 0.4.0, carrying the JSON type registry and the removal of the embedded script constants, is published and installable.

**Files:**
- Read: `docs/prompts/2026-08-14-emmykit-json-type-registry.md` (the prompt to paste)
- No files in this repository change.

**Acceptance Criteria:**
- [ ] `emmykit` 0.4.0 (or later) is installable from PyPI.
- [ ] `emmykit.register_json_type` and `emmykit.unregister_json_type` exist on the top-level namespace.
- [ ] `register_json_type` accepts an encode-only registration (no `tag`, no `decode`) without raising.
- [ ] The five script constants and `UNIV_DEFS_SYS_PATH_SCRIPT` are gone from emmykit.

**Verify:** `pixi run python -c "import emmykit as ek; print(ek.__version__); print(callable(ek.register_json_type), hasattr(ek, 'PRINTALL_SCRIPT'))"` → prints a version `>= 0.4.0`, then `True False`

**Steps:**

- [ ] **Step 1: Run the prompt in the emmykit repository**

Open a Claude Code session in the `emmykit` repo and paste the contents of
`docs/prompts/2026-08-14-emmykit-json-type-registry.md` (everything below its
`---` line). That prompt covers both jobs: the registry and the removal of the
embedded script constants.

- [ ] **Step 2: Confirm the release is installable**

```bash
pixi run python -c "import emmykit as ek; print(ek.__version__)"
```

If the pixi environment still holds 0.3.4, refresh it:

```bash
pixi update emmykit
```

- [ ] **Step 3: Confirm the new API shape**

```bash
pixi run python - <<'PY'
import emmykit as ek
import inspect
print(ek.__version__)
print(inspect.signature(ek.register_json_type))
print("encode-only supported:", "tag" in inspect.signature(ek.register_json_type).parameters)
print("script constants gone:", not hasattr(ek, "PRINTALL_SCRIPT"))
PY
```

Expected: a version of at least 0.4.0, a signature whose `tag` and `decode`
parameters are keyword-only with `None` defaults, `encode-only supported: True`,
`script constants gone: True`.

---

### Task 1: Declare emmykit as a dependency

**Goal:** veny declares emmykit in both `pyproject.toml` and `pixi.toml`, and the package is importable from the project environment.

**Files:**
- Modify: `pyproject.toml:5` (the `dependencies = []` line)
- Modify: `pixi.toml` (`[pypi-dependencies]` section, via `pixi add --pypi`)
- Modify: `pixi.lock` (regenerated by pixi)

**Acceptance Criteria:**
- [ ] `pyproject.toml` declares `dependencies = ["emmykit>=0.3.4"]`.
- [ ] `pixi.toml` has `emmykit = ">=0.3.4"` under `[pypi-dependencies]`.
- [ ] `pixi run python -c "import emmykit"` succeeds.
- [ ] The existing suite is unchanged: 234 tests pass.

**Verify:** `pixi run python -c "import emmykit as ek; print(ek.__version__)" && pixi run test -q 2>&1 | tail -1` → a version string, then `234 passed`

**Note on the floor:** the pin is `>=0.3.4` here, not the final `>=0.4.0,<1.0`,
because 0.4.0 does not exist yet and pixi cannot resolve an unreleased version.
Task 7 tightens it. This is the only place in the plan where an intentionally
temporary value is written.

**Steps:**

- [ ] **Step 1: Add the dependency to pixi**

emmykit is not on conda-forge (the Anaconda API returns 404 for it), so it is a
PyPI dependency — this is exactly the case CLAUDE.md reserves `--pypi` for.

```bash
pixi add --pypi "emmykit>=0.3.4"
```

- [ ] **Step 2: Declare it in pyproject.toml**

Change line 5 of `pyproject.toml` from:

```toml
dependencies = []
```

to:

```toml
dependencies = ["emmykit>=0.3.4"]  # Tightened to >=0.4.0,<1.0 once emmykit 0.4.0 ships (Task 7).
```

- [ ] **Step 3: Verify the environment resolves and the suite is untouched**

```bash
pixi run python -c "import emmykit as ek; print(ek.__version__)"
pixi run test -q 2>&1 | tail -1
```

Expected: a version string (0.3.4 today), then `234 passed`.

- [ ] **Step 4: Commit**

```bash
pixi run pre-commit run --files pyproject.toml pixi.toml
git add pyproject.toml pixi.toml pixi.lock
git commit -m "build: declare emmykit as a runtime dependency"
```

---

### Task 2: Stop writing the five helper scripts and the sys-path shim

**Goal:** veny no longer writes `mydiff.py`, `myaudit.py`, `multireplace.py`, `treeview.py`, `printall.py` or `univ_defs_sys_path_script.py` into `options.my_dir`, and `Options` no longer carries their paths.

**Files:**
- Modify: `veny.py:94-100` (delete `univ_defs_path` and the six script path fields)
- Modify: `veny.py:326-331` (delete the six `verify_script` calls)
- Create: `tests/test_options_surface.py`

**Acceptance Criteria:**
- [ ] `veny.Options()` has none of `univ_defs_path`, `univ_defs_sys_path_script`, `mydiff_path`, `myaudit_path`, `multireplace_path`, `treeview_path`, `printall_path`.
- [ ] `veny.Options()` still has `my_dir` and `packages_dir` (the directories main() genuinely uses).
- [ ] No `verify_script` call remains in `veny.py`.
- [ ] Full suite green.

**Verify:** `pixi run test -q 2>&1 | tail -1` → `236 passed` (234 baseline + 2 new)

**Steps:**

- [ ] **Step 1: Write the failing tests**

Test 1 — behaviour: the retired fields are gone from `Options`' attribute
surface, which is also the surface `save_options_to_json` serializes.
Bug it catches: a merge or a revert restoring `univ_defs_path`, which after this
migration would evaluate `ensure_path(ek.__file__).resolve(strict=True)` and bake
a meaningless `site-packages/emmykit/__init__.py` path into every saved options
file.

Test 2 — behaviour: the deletion did not overshoot into fields main() still
depends on. Bug it catches: deleting the whole `94-100` block including
`my_dir`/`packages_dir` (which sit just above in the same visual column group),
leaving veny with no directory to build venvs in.

Expected values come from the design decision itself — the seven names are the
exact set the design retires — not from reading the implementation.

Create `tests/test_options_surface.py`:

```python
"""Tests for which fields veny's Options class carries."""

import veny


RETIRED_FIELDS = {
    "univ_defs_path",
    "univ_defs_sys_path_script",
    "mydiff_path",
    "myaudit_path",
    "multireplace_path",
    "treeview_path",
    "printall_path",
}


def test_options_no_longer_carries_helper_script_paths():
    options = veny.Options()
    present = RETIRED_FIELDS & set(vars(options))
    assert present == set(), f"retired fields still on Options: {sorted(present)}"


def test_options_still_carries_the_directories_veny_uses():
    options = veny.Options()
    assert options.my_dir == options.home / options.my_name
    assert options.packages_dir == options.my_dir / "packages"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pixi run python -m pytest tests/test_options_surface.py -v
```

Expected: `test_options_no_longer_carries_helper_script_paths` FAILS with
`retired fields still on Options: ['multireplace_path', 'mydiff_path', ...]`.
`test_options_still_carries_the_directories_veny_uses` PASSES already — it is
the guard against overshooting, so it must be green before and after.

- [ ] **Step 3: Delete the seven Options fields**

In `veny.py`, delete these seven lines (currently `94-100`):

```python
        self.univ_defs_path:                      Path = ud.ensure_path(ud.__file__).resolve(strict=True)
        self.univ_defs_sys_path_script:           Path = self.my_dir / "univ_defs_sys_path_script.py"
        self.mydiff_path:                         Path = self.my_dir / "mydiff.py"
        self.myaudit_path:                        Path = self.my_dir / "myaudit.py"
        self.multireplace_path:                   Path = self.my_dir / "multireplace.py"
        self.treeview_path:                       Path = self.my_dir / "treeview.py"
        self.printall_path:                       Path = self.my_dir / "printall.py"
```

Leave `self.pipreqs_available` (line 93) and `self.read_files` (line 101)
untouched — the deletion is exactly the seven lines between them.

- [ ] **Step 4: Delete the six verify_script calls**

In `main()`, delete these six lines (currently `326-331`) and the blank line
that follows them:

```python
    ud.verify_script(options, options.univ_defs_sys_path_script, ud.UNIV_DEFS_SYS_PATH_SCRIPT)
    ud.verify_script(options, options.mydiff_path,               ud.MYDIFF_SCRIPT)
    ud.verify_script(options, options.myaudit_path,              ud.MYAUDIT_SCRIPT)
    ud.verify_script(options, options.multireplace_path,         ud.MULTIREPLACE_SCRIPT)
    ud.verify_script(options, options.treeview_path,             ud.TREEVIEW_SCRIPT)
    ud.verify_script(options, options.printall_path,             ud.PRINTALL_SCRIPT)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
pixi run python -m pytest tests/test_options_surface.py -v
pixi run test -q 2>&1 | tail -1
rg -n "verify_script" veny.py || echo "no verify_script calls remain"
```

Expected: both new tests PASS, `236 passed`, and the `rg` prints the
"no verify_script calls remain" fallback.

- [ ] **Step 6: Commit**

```bash
ruff check veny.py --statistics | tail -3   # must not be worse than before
pixi run python -m mypy veny.py tests/test_options_surface.py | tail -3
pixi run pre-commit run --files tests/test_options_surface.py
git add veny.py tests/test_options_surface.py
git commit -m "refactor: stop writing the five helper scripts veny never runs"
```

Note: `pre-commit run --files` is scoped to the new test file deliberately —
`veny.py` must never be handed to the ruff hooks.

---

### Task 3: Register veny's types with emmykit's JSON registry

**Goal:** A new module registers `ResolvedImport`, `StdlibIndex` and `AliasIndex` with emmykit's type registry, giving the first two full round trips and the third an honest encode-only snapshot.

**Blocked by:** Task 0 (needs emmykit 0.4.0).

**Files:**
- Create: `veny_json_types.py`
- Create: `tests/test_json_types.py`

**Acceptance Criteria:**
- [ ] `veny_json_types.register_types()` registers all three types and is idempotent.
- [ ] A `ResolvedImport` survives `to_jsonable` → `json.dumps` → `json.loads` → `from_jsonable` as an equal `ResolvedImport`.
- [ ] A `StdlibIndex` survives the same trip with `names` still a `frozenset`, `python_version` still a tuple, and `source` preserved.
- [ ] An `AliasIndex` serializes to a four-key snapshot and comes back as a plain `dict`.
- [ ] `veny_json_types.py` imports `emmykit`, `alias_index` and `stdlib_index` only — never `veny`.

**Verify:** `pixi run python -m pytest tests/test_json_types.py -v` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Each test below states the bug it catches. Expected values are fixed by hand
from the type definitions (`alias_index.py:77-93`, `stdlib_index.py:32-43`), not
by running the encoders.

Create `tests/test_json_types.py`:

```python
"""Tests for registering veny's own types with emmykit's JSON registry."""

import json

import emmykit as ek
import pytest

import alias_index
import stdlib_index
import veny_json_types


@pytest.fixture(autouse=True)
def registered():
    veny_json_types.register_types()


def roundtrip(obj):
    """Send an object through the real JSON text layer and back."""
    return ek.from_jsonable(json.loads(json.dumps(ek.to_jsonable(obj))))


def test_resolved_import_survives_a_real_json_round_trip():
    # Catches: no registration at all (the record stringifies to
    # "ResolvedImport(import_name='cv2', ...)"), or a decoder that drops one of
    # the two names -- which would send pip the wrong package.
    record = alias_index.ResolvedImport(import_name="cv2", pip_name="opencv-python")

    restored = roundtrip(record)

    assert restored == record
    assert isinstance(restored, alias_index.ResolvedImport)
    assert restored.pip_name == "opencv-python"


def test_resolved_imports_survive_inside_a_set():
    # Catches: an encoder that works on a bare record but not on the shape veny
    # actually stores -- options.uninstalled_imports is a set, and sets are
    # themselves a tagged type, so the two handlers must nest.
    records = {
        alias_index.ResolvedImport(import_name="cv2", pip_name="opencv-python"),
        alias_index.ResolvedImport(import_name="yaml", pip_name="pyyaml"),
    }

    assert roundtrip(records) == records


def test_stdlib_index_survives_a_real_json_round_trip():
    # Catches: falling through to str(), which turns membership into substring
    # matching -- "ma" in the repr is True, so a restored index would call "ma"
    # a standard-library module and veny would skip installing a real package.
    index = stdlib_index.StdlibIndex(
        names=frozenset({"os", "sys", "xml"}),
        python_version=(3, 13),
        source=stdlib_index.SOURCE_PROBE,
    )

    restored = roundtrip(index)

    assert isinstance(restored, stdlib_index.StdlibIndex)
    assert restored.names == frozenset({"os", "sys", "xml"})
    assert restored.python_version == (3, 13)
    assert restored.source == stdlib_index.SOURCE_PROBE
    assert "xml.etree.ElementTree" in restored
    assert "cv2" not in restored


def test_an_empty_stdlib_index_round_trips_as_an_empty_frozenset():
    # Catches: an encoder guarded by `if names:` or a decoder using
    # `names or None` -- an empty index would come back as None and the next
    # membership test would raise TypeError instead of returning False.
    index = stdlib_index.StdlibIndex(
        names=frozenset(),
        python_version=(3, 12),
        source=stdlib_index.SOURCE_DEGRADED,
    )

    restored = roundtrip(index)

    assert restored.names == frozenset()
    assert "os" not in restored


def test_alias_index_serializes_as_a_snapshot_and_returns_a_plain_dict(tmp_path):
    # Catches: (a) falling through to str(), losing the structured snapshot;
    # (b) somebody adding a decoder -- a reconstructed AliasIndex would carry
    # installed={} and answer "nothing is installed" for every import, silently
    # reinstalling packages the target interpreter already has.
    index = alias_index.AliasIndex(
        overrides={"cv2": "my-opencv"},
        cache=alias_index.AliasCache(
            path=tmp_path / "cache.json",
            interpreter_tag="3.13",
            entries={},
            rejections={},
        ),
        installed={"cv2": ["opencv-python"]},
        pypi=None,
    )

    payload = json.loads(json.dumps(ek.to_jsonable(index)))

    assert payload["overrides"] == {"cv2": "my-opencv"}
    assert payload["interpreter_tag"] == "3.13"
    assert payload["cache_path"] == str(tmp_path / "cache.json")
    assert payload["offline"] is True
    assert "__type__" not in payload

    restored = ek.from_jsonable(payload)
    assert isinstance(restored, dict)
    assert not isinstance(restored, alias_index.AliasIndex)


def test_register_types_is_idempotent():
    # Catches: registering without guarding against a second call -- emmykit
    # raises on a duplicate tag, so the second veny.Options() in a test session
    # (or a second main() call) would die at import time.
    veny_json_types.register_types()
    veny_json_types.register_types()

    record = alias_index.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    assert roundtrip(record) == record
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pixi run python -m pytest tests/test_json_types.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'veny_json_types'`.

- [ ] **Step 3: Write the module**

Create `veny_json_types.py`:

```python
"""Registers veny's own types with emmykit's JSON type registry.

emmykit serializes options files through ``to_jsonable``/``from_jsonable``, and
knows nothing about veny's types. Rather than teaching the utility library about
its consumer -- which is what the retired ``univ_defs.py`` did, by lazily
importing ``alias_index`` inside its own serializer -- veny supplies the
knowledge here and emmykit supplies only the mechanism.

This module imports ``emmykit``, ``alias_index`` and ``stdlib_index``. It must
never import ``veny``: that would close an import cycle, since ``veny`` imports
this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import emmykit as ek

import alias_index
import stdlib_index

_registered = False


def register_types() -> None:
    """Register veny's types with emmykit's JSON registry.

    Idempotent: a second call is a no-op, so importing veny twice (or calling
    main() twice in one process, as the tests do) cannot raise on a duplicate
    tag.
    """
    global _registered
    if _registered:
        return

    ek.register_json_type(
        alias_index.ResolvedImport,
        _encode_resolved_import,
        tag="resolved_import",
        decode=_decode_resolved_import,
    )
    ek.register_json_type(
        stdlib_index.StdlibIndex,
        _encode_stdlib_index,
        tag="stdlib_index",
        decode=_decode_stdlib_index,
    )
    # Encode-only, deliberately: see _encode_alias_index's docstring.
    ek.register_json_type(alias_index.AliasIndex, _encode_alias_index)

    _registered = True


def _encode_resolved_import(record: alias_index.ResolvedImport) -> dict[str, Any]:
    """Return the JSON payload for a ResolvedImport."""
    return {"import_name": record.import_name, "pip_name": record.pip_name}


def _decode_resolved_import(payload: dict[str, Any]) -> alias_index.ResolvedImport:
    """Rebuild a ResolvedImport from its JSON payload."""
    return alias_index.ResolvedImport(
        import_name=payload.get("import_name", ""),
        pip_name=payload.get("pip_name", ""),
    )


def _encode_stdlib_index(index: stdlib_index.StdlibIndex) -> dict[str, Any]:
    """Return the JSON payload for a StdlibIndex."""
    return {
        "names": sorted(index.names),
        "python_version": list(index.python_version),
        "source": index.source,
    }


def _decode_stdlib_index(payload: dict[str, Any]) -> stdlib_index.StdlibIndex:
    """Rebuild a StdlibIndex from its JSON payload.

    ``names`` is restored as a frozenset and ``python_version`` as a two-tuple,
    because a list would make ``__contains__`` linear and would compare unequal
    to every freshly built index.
    """
    version = tuple(payload.get("python_version", []))
    return stdlib_index.StdlibIndex(
        names=frozenset(payload.get("names", [])),
        python_version=(int(version[0]), int(version[1])) if len(version) == 2 else (0, 0),
        source=payload.get("source", stdlib_index.SOURCE_DEGRADED),
    )


def _encode_alias_index(index: alias_index.AliasIndex) -> dict[str, Any]:
    """Return a diagnostic snapshot of an AliasIndex.

    Registered without a tag or a decoder, so this payload reloads as a plain
    dict. That is deliberate and must not be "fixed": an AliasIndex holds
    ``installed``, obtained by probing the target interpreter, and ``pypi``, a
    live HTTP client. A decoder could rebuild the other fields, but the result
    would resolve imports differently from the real index while looking
    identical -- reporting nothing as installed, and reinstalling packages the
    interpreter already has. A readable snapshot plus an honest dict on reload
    beats a plausible-but-wrong object.
    """
    return {
        "overrides": dict(index.overrides),
        "interpreter_tag": index.cache.interpreter_tag,
        "cache_path": _fspath(index.cache.path),
        "offline": index.pypi is None,
    }


def _fspath(path: Path | str) -> str:
    """Return a path as a plain string for JSON."""
    return str(path)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pixi run python -m pytest tests/test_json_types.py -v
```

Expected: all six tests PASS. If `test_alias_index_...` fails on `"__type__" not
in payload`, the encode-only registration was given a tag — remove it rather
than adapting the test.

- [ ] **Step 5: Confirm the import discipline**

```bash
rg -n "^import|^from" veny_json_types.py
```

Expected: `emmykit`, `alias_index`, `stdlib_index`, `pathlib`, `typing`,
`__future__` — and no `veny`.

- [ ] **Step 6: Commit**

```bash
ruff check veny_json_types.py tests/test_json_types.py
pixi run python -m mypy veny_json_types.py
pixi run pre-commit run --files veny_json_types.py tests/test_json_types.py
git add veny_json_types.py tests/test_json_types.py
git commit -m "feat: register veny's types with emmykit's JSON registry"
```

---

### Task 4: Swap veny.py from univ_defs to emmykit

**Goal:** `veny.py` and the test suite import `emmykit as ek` instead of `univ_defs as ud`, and veny's type registrations are wired in.

**Blocked by:** Task 3.

**Files:**
- Modify: `veny.py:28` (the import), `veny.py:33-37` (the stale comment), `veny.py:45` (comment), and 106 `ud.` call sites
- Modify: `tests/test_split_imports.py` (8 `ud` references), `tests/test_cache_search.py` (2), `tests/test_alias_index.py` (2)

**Acceptance Criteria:**
- [ ] `rg '\bud\b' veny.py tests/` returns nothing.
- [ ] `veny.py` imports `emmykit as ek` and calls `veny_json_types.register_types()` at module scope.
- [ ] Importing `veny` alone is enough to make a `ResolvedImport` round-trip — no separate registration call needed by consumers.
- [ ] Apart from the import block, every changed line in `veny.py` differs only by `ud.` → `ek.`; column alignment is untouched.
- [ ] `veny.Options().args` is still `None`, pinned by a test.
- [ ] Full suite green.

**Verify:** `pixi run test -q 2>&1 | tail -1` → `244 passed` (242 + 2 new)

**On the `Options.args` difference:** emmykit's base `Options` defaults
`self.args` to `argparse.Namespace()` where `univ_defs`' defaulted it to `None`,
and narrows the annotation from `argparse.Namespace | None`. In veny this is
masked: `veny.py:106` re-assigns `self.args: argparse.Namespace | None = None`
*after* `super().__init__()`, so veny's own default is unchanged by the swap.
Step 1 pins that with a test rather than leaving it as an assumption — a later
"the base class handles this now" cleanup that deletes line 106 would flip the
default silently.

**Refinement of the spec, applied here:** the design says `register_types()` is
called "early in `main()`". This plan calls it at `veny.py` module scope instead,
directly after the imports. Same explicit call, same idempotence, but it also
covers every consumer that imports `veny` without running `main()` — which is
what the entire test suite does. `main()` would leave the serialization tests
registering by hand and prove nothing about production wiring.

**Steps:**

- [ ] **Step 1: Write the failing test**

Behaviour: importing `veny` is by itself sufficient for veny's types to
serialize. Bug it catches: the registration call being dropped, or moved
somewhere only `main()` reaches — under which `save_options_to_json` would
silently write `"ResolvedImport(import_name='cv2', ...)"` strings into the
last-used options file, and nothing would raise.

Append to `tests/test_json_types.py`:

```python
def test_importing_veny_is_enough_to_register_the_types():
    # Catches: register_types() never called from veny, or called only inside
    # main() -- production would then write repr strings into the options file
    # while every direct-registration test stayed green.
    import subprocess
    import sys
    from pathlib import Path

    source = (
        "import veny, json, emmykit as ek, alias_index;"
        "r = alias_index.ResolvedImport(import_name='cv2', pip_name='opencv-python');"
        "print(ek.from_jsonable(json.loads(json.dumps(ek.to_jsonable(r)))) == r)"
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"
```

The subprocess matters: registration is process-global, so an in-process test
would pass on registrations left behind by the other tests in this file.

Second test — behaviour: veny's own `args` default survives the base-class
swap. Bug it catches: deleting `veny.py:106` on the reasoning that emmykit's
base class now sets `args` itself, which would change the default from `None` to
an empty `argparse.Namespace` and make every `getattr(options.args, "flag",
False)` read succeed against a namespace that was never populated by
`parse_arguments`, turning a loud `AttributeError` on an unparsed run into a
silent "all flags false".

Append to `tests/test_options_surface.py`:

```python
import argparse


def test_options_args_defaults_to_none_after_the_emmykit_swap():
    options = veny.Options()
    assert options.args is None
    assert not isinstance(options.args, argparse.Namespace)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
pixi run python -m pytest tests/test_json_types.py::test_importing_veny_is_enough_to_register_the_types -v
pixi run python -m pytest tests/test_options_surface.py -v
```

Expected: `test_importing_veny_is_enough_to_register_the_types` FAILS — `assert
result.stdout.strip() == "True"` sees `False`, because `veny` still imports
`univ_defs` and never registers anything with emmykit.

`test_options_args_defaults_to_none_after_the_emmykit_swap` PASSES already, both
before and after this task. That is intended: it is a regression guard on a
default the swap could plausibly change, in the same family as
`test_options_still_carries_the_directories_veny_uses`. Its value is in Step 7,
where it must still be green once `veny.Options` inherits from `ek.Options`.

- [ ] **Step 3: Rename the alias mechanically**

```bash
sed -i 's/\bud\./ek./g' veny.py tests/test_split_imports.py tests/test_cache_search.py tests/test_alias_index.py
```

This touches only `ud.`-prefixed tokens. The bare `import ... as ud` lines are
handled in the next step.

- [ ] **Step 4: Fix the import blocks by hand**

In `veny.py`, replace line 28:

```python
import univ_defs as ud
```

with:

```python
import emmykit as ek
```

Then replace the comment block at lines 33-37, which describes an arrangement
that no longer exists:

```python
# An import name paired with the pip package that provides it. Defined in
# alias_index so that univ_defs can serialize it without importing veny (which
# would close an import cycle), and re-exported here because veny is where it
# is used.
ResolvedImport = alias_index.ResolvedImport
```

with:

```python
# An import name paired with the pip package that provides it. Defined in
# alias_index, which imports nothing of veny's, and re-exported here because
# veny is where it is used. Its JSON handlers live in veny_json_types.
ResolvedImport = alias_index.ResolvedImport

# Registers veny's own types with emmykit's JSON registry. At module scope, not
# inside main(), so that anything importing veny -- including every test -- gets
# the same serialization behaviour production does. The call is idempotent.
veny_json_types.register_types()
```

Add `import veny_json_types` to the import block, after `import venv_cache`
(line 29), keeping alphabetical order:

```python
import venv_cache
import veny_json_types
```

Finally, fix the comment on line 45, which names the retired file:

```python
        super().__init__()                  # Call the parent class's __init__ method from emmykit
```

- [ ] **Step 5: Update the test files' imports**

In `tests/test_split_imports.py:9` and `tests/test_cache_search.py:14`, replace:

```python
import univ_defs as ud
```

with:

```python
import emmykit as ek
```

In `tests/test_alias_index.py`, lines 384 and 402 are comments mentioning
`ud.find_preferred_python_version`; the `sed` in Step 3 already rewrote them to
`ek.`. Confirm they read sensibly.

Also update the comment in `tests/test_split_imports.py:1420`, which the sed
rewrote to `ek.my_critical_error()` — that is correct and needs no further
change.

- [ ] **Step 6: Verify the rename changed nothing else**

```bash
rg -n '\bud\b' veny.py tests/ || echo "no ud references remain"
git diff -U0 veny.py | rg '^[-+]' | rg -v '^\+\+\+|^---' | rg -v 'ud\.|ek\.|emmykit|univ_defs|veny_json_types' || echo "only alias lines changed"
```

Expected: the first prints the fallback message; the second prints "only alias
lines changed", proving no alignment or unrelated line was touched.

- [ ] **Step 7: Run the tests**

```bash
pixi run python -m pytest tests/test_json_types.py -v
pixi run test -q 2>&1 | tail -1
```

Expected: both new tests PASS, and `244 passed`.

The three existing serialization tests in `tests/test_split_imports.py` (around
lines 1466-1502) now exercise `ek.to_jsonable`/`ek.from_jsonable` and must still
pass — they are the proof that the registry replaced the univ_defs handlers
faithfully rather than merely compiling.

- [ ] **Step 8: Commit**

```bash
ruff check veny.py --statistics | tail -3
pixi run python -m mypy veny.py veny_json_types.py | tail -3
pixi run pre-commit run --files tests/test_json_types.py tests/test_split_imports.py tests/test_cache_search.py tests/test_alias_index.py
git add veny.py tests/
git commit -m "refactor: import emmykit as ek in place of univ_defs as ud"
```

---

### Task 5: Delete univ_defs.py

**Goal:** The 9,757-line local utility file is gone, along with the one test that only made sense while it existed, and every remaining reference to it in code and docs.

**Blocked by:** Task 4.

**Files:**
- Delete: `univ_defs.py`
- Modify: `tests/test_split_imports.py` (delete `test_univ_defs_imports_without_the_alias_modules_beside_it`, currently around line 1437)
- Modify: `README.md:52`, `alias_index.py:11`, `alias_index.py:84`, `stdlib_index.py:9`, `venv_cache.py:8`

**Acceptance Criteria:**
- [ ] `univ_defs.py` no longer exists.
- [ ] `rg 'univ_defs' -- '*.py' 'README.md'` returns nothing.
- [ ] README's project structure lists `veny_json_types.py` and records the emmykit dependency.
- [ ] Full suite green with one test fewer.

**Verify:** `pixi run test -q 2>&1 | tail -1` → `243 passed`

**Steps:**

- [ ] **Step 1: Delete the test that guarded standalone deployment**

In `tests/test_split_imports.py`, delete
`test_univ_defs_imports_without_the_alias_modules_beside_it` in full, including
its comment block. It asserted that `univ_defs.py` could be copied somewhere on
its own and still import without `alias_index.py` beside it — a property of a
loose file that no longer exists, since emmykit ships as an installed package
with its dependencies declared.

- [ ] **Step 2: Delete the file**

```bash
git rm univ_defs.py
```

- [ ] **Step 3: Update the docstrings that name it**

`alias_index.py:11` — replace:

```python
This module deliberately imports nothing from veny or univ_defs, so it can be
```

with:

```python
This module deliberately imports nothing from veny or emmykit, so it can be
```

`alias_index.py:84` — replace:

```python
    This lives here rather than in veny.py so that univ_defs can serialize it
    without importing veny, which would close an import cycle.
```

with:

```python
    This lives here rather than in veny.py so that veny_json_types can register
    its JSON handlers without importing veny, which would close an import cycle.
```

`stdlib_index.py:9` — replace `univ_defs` with `emmykit` in the same sentence
shape as `alias_index.py:11`.

`venv_cache.py:8` — replace:

```python
univ_defs, alias_index, or pypi_client, so it can be unit tested without
```

with:

```python
emmykit, alias_index, or pypi_client, so it can be unit tested without
```

- [ ] **Step 4: Update the README**

Replace line 52:

```
univ_defs.py       # Shared utilities and the base Options class.
```

with:

```
veny_json_types.py # Registers veny's own types with emmykit's JSON registry.
```

and add a line under installation stating the dependency:

```markdown
veny requires the [emmykit](https://pypi.org/project/emmykit/) package
(`pip install 'emmykit>=0.4.0'`), which provides its utility layer and the base
`Options` class.
```

- [ ] **Step 5: Verify nothing still refers to it**

```bash
rg -n "univ_defs" -- '*.py' README.md || echo "no univ_defs references remain"
pixi run test -q 2>&1 | tail -1
```

Expected: the fallback message, then `243 passed` (244 minus the deleted test).

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files README.md alias_index.py stdlib_index.py venv_cache.py tests/test_split_imports.py
git add -u
git commit -m "refactor: delete univ_defs.py in favour of the emmykit package"
```

---

### Task 6: Fail loudly when emmykit is missing

**Goal:** A veny run on an interpreter without emmykit exits with an actionable install message instead of an ImportError traceback.

**Blocked by:** Task 4.

**Files:**
- Modify: `veny.py:28` (wrap the import)
- Create: `tests/test_import_guard.py`

**Acceptance Criteria:**
- [ ] With emmykit unimportable, `import veny` exits non-zero with a message naming the package and the install command.
- [ ] The message reaches stderr, not stdout.
- [ ] With emmykit present, `import veny` still succeeds — the guard does not misfire.
- [ ] The guard catches `ImportError` only, not bare `Exception`.

**Verify:** `pixi run python -m pytest tests/test_import_guard.py -v` → 2 tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Behaviour: veny's startup path degrades usefully when its one dependency is
absent. Bug it catches: a plain `import emmykit as ek`, which gives a user who
copied `veny.py` onto a fresh machine a traceback ending in
`ModuleNotFoundError: No module named 'emmykit'` with no indication that a
`pip install` fixes it.

Second test — bug it catches: a guard written as `except Exception`, or one that
exits unconditionally, which would break every normal run. Setting
`sys.modules["emmykit"] = None` is the standard way to make an import raise
`ImportError` without touching the filesystem.

Create `tests/test_import_guard.py`:

```python
"""Tests for veny's behaviour when its emmykit dependency is missing."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_python(source):
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_veny_exits_with_an_install_message_when_emmykit_is_missing():
    result = run_python("import sys; sys.modules['emmykit'] = None; import veny")

    assert result.returncode != 0
    assert "emmykit" in result.stderr
    assert "pip install" in result.stderr
    assert "Traceback" not in result.stdout


def test_veny_imports_normally_when_emmykit_is_present():
    result = run_python("import veny; print(veny.__version__)")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.2.2"
```

- [ ] **Step 2: Run them to verify the first fails**

```bash
pixi run python -m pytest tests/test_import_guard.py -v
```

Expected: `test_veny_exits_with_an_install_message_when_emmykit_is_missing`
FAILS on `assert "pip install" in result.stderr` — the traceback names the
module but offers no remedy. The second test PASSES already; it is the
guard-against-overshooting test.

- [ ] **Step 3: Add the guard**

Replace `import emmykit as ek` in `veny.py` with:

```python
try:
    import emmykit as ek
except ImportError as exc:  # stdlib only: none of emmykit's helpers exist yet.
    raise SystemExit(
        "veny requires the emmykit package (>=0.4.0), which is not installed.\n"
        "Install it with:  pip install 'emmykit>=0.4.0'"
    ) from exc
```

`SystemExit` writes its message to stderr and exits 1. Catching `ImportError`
specifically matters: a broad `except Exception` would swallow a genuine failure
inside emmykit's own import and report it as "not installed".

Keep this block with the other third-party imports, after `import venv_cache`
would place it out of order — put it immediately where `import emmykit as ek`
sat, so import order is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pixi run python -m pytest tests/test_import_guard.py -v
pixi run test -q 2>&1 | tail -1
```

Expected: both tests PASS, `245 passed`.

- [ ] **Step 5: Commit**

```bash
ruff check veny.py --statistics | tail -3
pixi run pre-commit run --files tests/test_import_guard.py
git add veny.py tests/test_import_guard.py
git commit -m "feat: exit with an install message when emmykit is missing"
```

---

### Task 7: Pin emmykit 0.4.0, verify live, and record the migration

**Goal:** **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

The dependency floor is raised to the released 0.4.0, veny is proven to work end-to-end against a real script, and PROGRESS.md records the outcome.

**Blocked by:** Tasks 5 and 6.

**Files:**
- Modify: `pyproject.toml:5`, `pixi.toml` (`[pypi-dependencies]`), `pixi.lock`
- Modify: `PROGRESS.md`

**Acceptance Criteria:**
- [ ] `pyproject.toml` and `pixi.toml` both pin `emmykit>=0.4.0,<1.0`, and `pixi install` resolves.
- [ ] Full suite green: 245 tests pass.
- [ ] `ruff check veny.py --statistics` total is no worse than the pre-migration baseline captured in Step 1.
- [ ] `mypy veny.py veny_json_types.py` reports no *new* errors versus the Step 1 baseline.
- [ ] A live run of veny against a real Python script creates or reuses a virtual environment and runs the script successfully, with the captured stdout showing the script's own output.
- [ ] After that live run, none of `printall.py`, `mydiff.py`, `myaudit.py`, `multireplace.py`, `treeview.py`, `univ_defs_sys_path_script.py` has been re-created or modified in `~/veny` (compare against the mtimes captured before the run).
- [ ] The saved last-used options JSON from that run contains no `univ_defs` key and no `ResolvedImport(` repr string.
- [ ] PROGRESS.md's Current work block records the migration as complete and points at the two cross-repo prompts' status.

**Verify:** `pixi run test -q 2>&1 | tail -1` → `245 passed`, plus the live-run evidence captured in Steps 3-5

**Steps:**

- [ ] **Step 1: Capture the baselines you will compare against**

```bash
git stash list > /dev/null   # no-op; ensures a clean shell
ruff check veny.py --statistics | tail -1
pixi run python -m mypy veny.py veny_json_types.py 2>&1 | tail -1
ls -l --time-style=full-iso ~/veny/*.py 2>/dev/null | awk '{print $6, $7, $9}'
```

Record all three outputs in the task notes. The third is the mtime list the
helper-script check compares against.

- [ ] **Step 2: Raise the pin**

```bash
pixi add --pypi "emmykit>=0.4.0,<1.0"
```

and in `pyproject.toml`, replace line 5 with:

```toml
dependencies = ["emmykit>=0.4.0,<1.0"]
```

The temporary `>=0.3.4` comment from Task 1 goes away with it.

- [ ] **Step 3: Run the full suite and the scoped tool checks**

```bash
pixi run test -q 2>&1 | tail -1
ruff check veny.py --statistics | tail -1
pixi run python -m mypy veny.py veny_json_types.py 2>&1 | tail -1
```

Expected: `245 passed`; the ruff and mypy tails no worse than Step 1's.

- [ ] **Step 4: Run veny live against a real script**

```bash
cat > /tmp/veny_live_check.py <<'PY'
import yaml
print("live check ok:", yaml.safe_load("a: 1"))
PY

ls -l --time-style=full-iso ~/veny/*.py 2>/dev/null | awk '{print $6, $7, $9}' > /tmp/veny_before.txt
pixi run python veny.py /tmp/veny_live_check.py
ls -l --time-style=full-iso ~/veny/*.py 2>/dev/null | awk '{print $6, $7, $9}' > /tmp/veny_after.txt
diff /tmp/veny_before.txt /tmp/veny_after.txt && echo "helper scripts untouched"
```

Expected: veny builds or reuses a venv, installs PyYAML, and the script prints
`live check ok: {'a': 1}`. The `diff` prints "helper scripts untouched" — if it
shows a changed mtime for any of the five scripts or the shim, Task 2's deletion
did not take effect and this task is not done.

- [ ] **Step 5: Inspect the options JSON that run wrote**

```bash
ls -t /tmp/.veny_live_check.py-veny-last-used-on-*.json 2>/dev/null | head -1
rg -c "univ_defs|ResolvedImport\(" "$(ls -t /tmp/.veny_live_check.py-veny-last-used-on-*.json | head -1)" || echo "options JSON is clean"
rg -o '"__type__": "[a-z_]+"' "$(ls -t /tmp/.veny_live_check.py-veny-last-used-on-*.json | head -1)" | sort -u
```

Expected: "options JSON is clean", and the tag list includes
`"__type__": "resolved_import"` if the run recorded any uninstalled imports.
A `ResolvedImport(` string anywhere in that file means the registration is not
reaching production.

- [ ] **Step 6: Update PROGRESS.md**

In the **Current work** block, replace the "Next action" line with a completion
record: tasks 0-7 done, emmykit version pinned, and the status of the two
cross-repo prompts (emmykit 0.4.0 released; the utilities-repo adoption done or
still outstanding). Add to **Gotchas**:

```markdown
- veny's own types are serialized by `veny_json_types.register_types()`, called
  at `veny.py` module scope, not inside `main()`. Anything that imports veny --
  including every test -- gets production's serialization behaviour. If you move
  the call into `main()`, `save_options_to_json` will silently write
  `"ResolvedImport(...)"` repr strings for any consumer that does not go through
  `main()`, and no test will notice unless it runs in a subprocess.
- `alias_index.AliasIndex` is registered **encode-only** on purpose. It holds
  `installed` (probed from the target interpreter) and a live `pypi` client, so a
  decoder would return an index that reports nothing as installed while looking
  identical to a real one. It reloads as a plain dict by design.
```

- [ ] **Step 7: Commit and merge**

```bash
pixi run pre-commit run --files pyproject.toml pixi.toml PROGRESS.md
git add pyproject.toml pixi.toml pixi.lock PROGRESS.md
git commit -m "build: pin emmykit>=0.4.0 and record the migration"
```

Then follow the repository's branch-finishing practice to merge into `main`.

```json:metadata
{"userGate": true, "tags": ["user-gate"], "requiresUserSpecification": false, "verifyCommand": "pixi run test -q 2>&1 | tail -1 && pixi run python veny.py /tmp/veny_live_check.py", "acceptanceCriteria": ["pyproject.toml and pixi.toml pin emmykit>=0.4.0,<1.0 and pixi install resolves", "245 tests pass", "ruff check veny.py --statistics no worse than the Step 1 baseline", "mypy veny.py veny_json_types.py reports no new errors versus baseline", "a live veny run executes a real script successfully and prints its output", "no helper script in ~/veny was re-created or modified during the live run", "the run's options JSON contains no univ_defs key and no ResolvedImport( repr string", "PROGRESS.md records the migration as complete"], "modelTier": "standard"}
```

---

## Notes for the executing engineer

- **Baseline test count is 234.** Running totals after each task: Task 2 →
  236 (+2), Task 3 → 242 (+6), Task 4 → 244 (+2), Task 5 → 243 (-1, the deleted
  standalone-deployment test), Task 6 → 245 (+2), Task 7 → 245 (no new tests).
  If a count is off by more than the task's own delta, stop and find out why
  before continuing.
- **Tasks 1 and 2 are unblocked today.** Tasks 3-7 need emmykit 0.4.0 (Task 0).
- **`veny.py` formatting is load-bearing.** Its columns are hand-aligned and
  ruff-format must never touch it. The `ud.` → `ek.` rename is safe precisely
  because both aliases are two characters wide.
- **`pixi run test` runs with `-v` by default** (set in `pyproject.toml`'s
  `addopts`); the `-q` in the verify commands overrides it for a one-line tail.
