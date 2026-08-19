# Phase 3d: Verify, Cache Search and Last Used — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **ANNOTATED IN PLACE BY TASK 10, 2026-08-18 (execution complete, branch
> `verify-cache-search-last-used` @ `7debbb3`).** Every block below marked
> **[EXECUTION]** records something this plan's own text got wrong. Phases 3b
> and 3c both did this and both found real errors; so did this one, seven
> times. The checkboxes are all marked complete.

**Goal:** Extract `verify.py`, `cache_search.py` and `last_used.py` out of
`src/veny/cli.py` — 1,088 measured lines of it (**[EXECUTION]** it removed
**1,232**: `cli.py` went 2,296 → 1,064. The 1,088 figure counted the measured
symbol *bodies* in the File Structure tables below and missed the import
lines, blank lines and comment blocks that went with them.) — with each extraction stating
what it is handed and what it returns, and with tests written at the new
interface before the code moves.

**Architecture:** Three new top-level modules under `src/veny/`, in a strict
one-way stack: `last_used` (no veny imports at all) sits beside
`classify`/`environment`; `verify` sits above them because it calls
`environment`; `cache_search` sits above `verify` because `check_venv_dir`
confirms a cached venv by import-checking it. `cli.py` keeps `main()`,
`setup_virtualenv`, the reporting block and the `Options` object, and calls
into all three through module attributes (`verify.check_packages_in_venv(...)`),
never `from .verify import ...` — that is what keeps `monkeypatch.setattr`
working and what phase 3c established.

**Tech Stack:** Python 3.12/3.13, pixi, pytest, ruff, mypy, `uv` (through
`environment.py` only), emmykit ≥ 0.4.0.

**Global Constraints:**

1. **Behaviour-preserving, with exactly two sanctioned exceptions** (Task 7's
   duplicate-`satisfies` removal, and the deletion of the three dead symbols
   named in Task 8). Everything else must be a move plus an argument list.
2. **Tests before moves.** Each extraction characterizes the current behaviour
   at the *new* interface first, in its own commit, then moves the code.
3. **`cli.py` calls through the module object** — `verify.foo(...)`,
   `cache_search.foo(...)`, `last_used.foo(...)`. Never `from .verify import foo`.
4. **STANDING CHECK (from PROGRESS Gotchas, added by 3c's review):** after
   moving a symbol, mutate *every argument* at *every* new call site and confirm
   a **named** test fails. An extraction turns an implicit `options.<field>`
   read into an explicit, mis-wirable argument; the new module's own unit tests
   pass values directly and never exercise the wiring. Task 9 runs this
   mechanically over the complete call-site table in this plan.
5. **Never `git stash`, never `git checkout -- <path>`, never
   `git checkout <sha>`.** To mutate a file for a mutation check, copy it to
   the scratch directory first and restore from the copy. `git checkout --`
   cost 3c's Task 4 an entire session of edits.
6. **`PYTHONHASHSEED=0` goes inside any differential driver script**, not in
   the invocation. Nothing in the repository carries it today.
7. **Gates that must hold at the end of every task:** `pixi run test` green,
   `pixi run lint` zero, `pixi run python -m ruff format --check .` all files
   formatted, `pixi run typecheck` **≤ 36 errors** (the current ceiling — it
   may fall, it must not rise), `pixi run smoke` green.
   **[EXECUTION]** It fell, twice, without anyone setting out to lower it:
   36 → 35 at Task 5, back to 36 at Task 6, then **36 → 33 at Task 8**. Final:
   **33 errors in 6 files** (`tests/test_verify.py` 15, `src/veny/cli.py` 7,
   `tests/test_split_imports.py` 6, `analysis/imports.py` 3,
   `analysis/literals.py` 1, `analysis/call_graph.py` 1). Lowest it has ever
   been. Final suite: **359 passed** (321 at the branch point).
8. **Do not reintroduce hand-aligned columns.** `ruff format` owns the layout.
9. `pixi run pre-commit run --files <paths>` before every commit —
   `.git/hooks/pre-commit` is not installed, so `git commit` does not run them.

**User decisions (already made):**

- The re-architecture design doc
  `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md` was approved
  2026-08-15 and fixes module boundaries and ownership. Phase 3 is sequenced
  module by module in its plans; this is the fourth of five.
- Phase 3's module list, sizes and ownership statements are the design's, not
  this plan's: `verify.py ~600`, `cache_search.py ~600`, `last_used.py ~120`.
- `analysis/` receives stdlib membership as an injected predicate, not an index
  (owner's decision, 2026-08-16); the same style of injection is used here for
  the last-used loader.
- Hand-alignment in `cli.py` was retired on the owner's instruction;
  `ruff check` and `ruff format` pass repo-wide and must stay that way.
- `mypy` cannot pass; it is scoped manually against a ceiling (36).

---

## Starting state (this plan may be executed in a different session — assume nothing)

Measured on `main` @ `313e800`, 2026-08-18:

- `src/veny/cli.py` is **2,296 lines**. Phases 1, 2, 3a, 3b and 3c are all
  merged to `main`.
- `pixi run test` → **321 passed**. `pixi run lint` → zero. `ruff format
  --check .` → 45 files formatted. `pixi run typecheck` → **36 errors in 5
  files** (`tests/test_split_imports.py` 21, `src/veny/cli.py` 10,
  `analysis/imports.py` 3, `analysis/literals.py` 1, `analysis/call_graph.py` 1).
- Existing modules: `alias_index.py` 826, `analysis/imports.py` 683,
  `venv_cache.py` 465, `analysis/scan.py` 347, `pypi_client.py` 314,
  `environment.py` 280, `analysis/custom_modules.py` 274, `classify.py` 274,
  `stdlib_index.py` 233, `analysis/literals.py` 229, `analysis/call_graph.py`
  177, `json_types.py` 136, `state.py` 51, `analysis/scan_state.py` 30,
  `settings.py` 23.
- **No branch exists for this plan.** Create one off `main`:
  `git switch -c verify-cache-search-last-used`.

Read `PROGRESS.md`'s Gotchas and Deferred items before starting. The entries
that bear directly on this plan are: the STANDING CHECK, the
differential-corpus technique, the stale-`__pycache__` trap, the
`PYTHONHASHSEED` gap, the RESIDUAL RISK carried into 3d from 3c's differential,
and the "Named for 3d to pick up" list.

## What this plan measured, and what you must measure

**Measured while writing this plan** (re-derive with the commands given if you
doubt any of it — a plan's "measured" is not evidence, which is a standing
lesson in PROGRESS after 3a shipped a wrong one):

- Every span and line count in the File Structure section below
  (`ast` walk over `src/veny/cli.py`).
- The complete call-site tables below (`rg -n '<symbol>\('` over `src/` and
  `tests/`).
- 39 string-based `monkeypatch.setattr(<module>, "<name>", ...)` sites across
  four test files — the largest single rewiring cost in this plan. They are
  enumerated per task.
- `args.latest` / `args.oldest` / `args.smallest` / `args.last_used` are read
  and written **only inside `find_match_dir_in_cache`** (`cli.py:2172-2295`).
  Nothing else in `src/` touches them.
- `cli.load_last_used_venv_dir` has zero references anywhere in `src/` or
  `tests/` — definition only. `tests/test_split_imports.py:314`'s `_index_with`
  has zero references. Both are deleted by Task 8.
- `ek.save_options_to_json` serializes `options.__dict__.copy()`, so the `args`
  Namespace is part of the written JSON payload. Nothing in veny ever reads
  those four keys back — `load_last_used_options` is consumed only for
  `venv_dir` and `venv_python`.

**You must measure, not assume:**

- Every expected value in a characterization test. Obtain it by running the
  current code, not by reading it. Record how you obtained it in the test's
  docstring.
- The post-move mypy count, per file, before claiming the ceiling held.
- The `wc -l` of every file you touched, for the closing ledger.

## What this plan settles that the design did not

Three amendments, numbered on from the eight 3b and 3c recorded. Each is a
consequence of a behaviour-preserving move, not a defect, and each belongs in
PROGRESS's Deferred items at Task 10.

9. **`find_match_dir_in_cache` keeps taking the `argparse.Namespace` and keeps
   mutating it.** The design says argparse dies at the `cli.py` boundary
   (line 260, and the phase-4 note that `args` dies at the argparse boundary).
   It cannot die here: the function's selection policy *writes* `args.last_used
   = True` as its "no flags given" default and `args.latest = True` /
   `args.last_used = False` as its fallback after a last-used miss, and those
   writes land in the options JSON through `save_options_to_json`. Passing four
   booleans in and dropping the write-back would change the bytes of a
   user-visible artifact. `argparse.Namespace` is a stdlib type, so taking it
   introduces no veny-layer dependency. **What resolves it:** phase 3e or 4,
   when `cli.py` owns the flag surface and the persistence change removes the
   JSON payload the mutation leaks into.
10. **`verify.py` imports `environment.py`.** The design's stack (line 267)
    lists them as peers under `pipeline`. They are not peers:
    `repair_unsatisfied_import` installs and uninstalls through
    `environment`, and `verify_and_repair_imports` rewrites `requirements.txt`
    through `environment.write_requirements_file_with_extras`. `verify` is
    therefore a layer above `environment`, and `cache_search` a layer above
    `verify`. `tests/test_layering.py`'s `LAYERS` is updated accordingly
    (Task 2 and Task 6), with no new same-layer exception.
11. **`venv_python_for` moves to `environment.py`, not to `verify.py`.** The
    design does not place it. It is venv-layout knowledge (`bin/python` vs
    `Scripts/python.exe`), which is what `environment.py` owns, and
    `tests/test_environment.py` already carries a parked note that its live
    test hardcodes the layout "instead of reusing `cli.venv_python_for`". Its
    `options`-defaulting branch dies with the move: every caller now passes a
    directory. Phase 4's `VenvHandle` replaces it outright.

## The mypy ceiling

The ceiling is **36** and must not rise. PROGRESS records where the 21 errors
in `tests/test_split_imports.py` live and states that **17 are 3d's
territory** — 11 in the `resolve_and_verify` tests (`_RecordingIndex` passed
where `AliasIndex` is declared, plus `Candidate | None` dereferences), 2 in
`_run_check_against_fake_venv`, 4 at `_live_index`'s `AliasIndex(**fields)`.

Those 17 travel to `tests/test_verify.py` with the tests that carry them.

> **[EXECUTION] Fifteen travelled, not seventeen** — measured at `7debbb3`:
> `tests/test_split_imports.py` fell 21 → **6**, `tests/test_verify.py`
> arrived at **15**. The two that did not travel are
> `_run_check_against_fake_venv`'s untyped-def pair. The helper now exists in
> **both** files: the migrated copy at `tests/test_verify.py:553` was given
> type hints on arrival (so it contributes zero), while the untyped original
> stayed at `tests/test_split_imports.py:145` for the one test still using it
> (`:218`). This plan's "the migration is meant to move the tests verbatim"
> and its arithmetic do not survive a helper being *duplicated* rather than
> moved — a prediction that adds up only if every symbol has exactly one home
> is not a prediction, it is an assumption. `src/veny/cli.py` also fell 10 →
> **7** with nobody typing anything: the errors left with the code.
**This plan does not promise to clear them** — clearing them means typing the
fakes properly, which is a change to test code the migration is meant to move
verbatim. The requirement is: measure the count per file after Task 3 and after
Task 6, and record both. If the number falls, say by how much and why. If it
rises above 36, the task is not done.

The **other 4** errors are not 3d's and will not move: 2 in
`test_enqueue_top_level_imports_records_stdlib_and_skips_enqueue` (a scan-layer
test) and 2 in the `build_alias_index` offline/online pair.

New source modules and new test files must contribute **zero** mypy errors,
the standard 3c held.

## Deferred items this plan picks up

From PROGRESS's "Named for 3d to pick up" and the older parked lists:

- Delete `cli.load_last_used_venv_dir` — dead at `dc1c3c4`, dead now (Task 8).
- Delete `tests/test_split_imports.py:314`'s `_index_with` — dead (Task 8).
- Simplify `rename_venv`'s single-element tuple loop (Task 6).
- Fix `test_a_record_carrying_a_pip_spelling_is_never_repaired`, which is
  decorative: it sets `all_imports = set()` so the function returns before the
  branch it names, and deleting the filter leaves the suite green (Task 3).
- De-duplicate the three-assert block and the `pip_name` generator at the two
  `write_requirements_file_with_extras` call sites, and delete the dead
  `assert options.uninstalled_imports is not None` in
  `verify_and_repair_imports` (Task 3).
- Consolidate `tests/test_classify.py`'s two near-duplicate recording helpers
  (`_RecordingIndex` at :57, `_CountingIndex` at :558) (Task 8).
- Delete the write-only `options.installed_imports` chain (Task 8).
- Close design ledger item 2 — `satisfies()` running twice on the winning
  candidate (Task 7).
- Cover `install_into_venv`'s success predicate in the differential, which 3c's
  driver could not (Task 9).
- Sweep the ~eight stale `src/veny/cli.py` line citations in PROGRESS (Task 10).

## Deferred items this plan explicitly declines

State these in the closing commit rather than leaving them ambiguous:

- **The `environment.uv_binary` / `create_venv` exit-ownership change**
  (amendment 4). It is a real behaviour-boundary change; PROGRESS names 3e as
  its natural home because 3e owns the final `cli.py` slimming. Declined here.
- **The reachability gap** — a single-file scan missing imports inside a
  submodule reached via `from package import submodule`. It is an `analysis/`
  question; none of this plan's three modules can see it. Declined here.
- **Removing the probe venv from classification.** 3c's amendment 3 records
  that the probe is injected, not removed, and PROGRESS measures exactly what
  it can still answer "installed" to (`test`, plus three CPython demo modules).
  Not 3d's.
- **The two pre-existing `AssertionError` crashes.** Out of scope by the
  design. Task 3 must *preserve* the second one exactly — see its Step 6.

---

## File Structure

### Symbols moving to `verify.py` (measured spans, 601 lines of body)

| Span in `cli.py` | Lines | Symbol |
|---|---|---|
| `678-700` | 23 | `MACHINE_SCOPED_IMPORT_MARKERS`, `_SHARED_LIBRARY_PATTERN` (+ their comment block) |
| `703-728` | 26 | `ImportOutcome` |
| `731-744` | 14 | `import_error_detail` |
| `747-766` | 20 | `import_providers` |
| `769-821` | 53 | `import_outcome_in_venv` |
| `824-843` | 20 | `_credited_with_the_import` |
| `846-921` | 76 | `resolve_and_verify` |
| `947-1018` | 72 | `run_import_check_in_venv` |
| `1021-1043` | 23 | `source_import_names` |
| `1046-1133` | 88 | `check_packages_in_venv` |
| `1366-1438` | 73 | `repair_unsatisfied_import` |
| `1441-1480` | 40 | `confirm_if_attributable` |
| `1483-1555` | 73 | `verify_and_repair_imports` |

### Symbols moving to `environment.py` (measured span, 21 lines)

| Span in `cli.py` | Lines | Symbol |
|---|---|---|
| `924-944` | 21 | `venv_python_for` |

### Symbols moving to `cache_search.py` (measured spans, 549 lines of body)

| Span in `cli.py` | Lines | Symbol |
|---|---|---|
| `1349-1363` | 15 | `interpreter_tag` |
| `1558-1565` | 8 | `_VERSION_PROBE_CODE` |
| `1568-1621` | 54 | `installed_state_in_venv` |
| `1624-1669` | 46 | `manifest_for` |
| `1672-1717` | 46 | `record_venv_state` |
| `1790-1831` | 42 | `rename_venv` |
| `1936-1954` | 19 | `latest_venv` |
| `1957-1975` | 19 | `oldest_venv` |
| `1978-1999` | 22 | `smallest_venv` |
| `2002-2058` | 57 | `check_venv_dir` |
| `2061-2086` | 26 | `wanted_packages` |
| `2089-2106` | 18 | `CacheCandidate` |
| `2109-2156` | 48 | `cache_candidates` |
| `2159-2296` | 138 | `find_match_dir_in_cache` |

### Symbols moving to `last_used.py` (measured spans, 65 lines of body)

| Span in `cli.py` | Lines | Symbol |
|---|---|---|
| `1834-1836` | 3 | `is_virtualenv` |
| `1839-1864` | 26 | `load_last_used_options` |
| `1898-1933` | 36 | `load_last_used_venv_python` |
| `1867-1895` | 29 | `load_last_used_venv_dir` — **deleted, not moved** |

### Staying in `cli.py` (phase 3e's territory, do not touch)

`Options`, `parse_arguments`, `build_alias_index`, `main`,
`find_imports_in_script`, `warn_about_system_packages`, `_probe_venv`,
`split_imports` (the adapter), `list_packages`, `stayed_out_dir`,
`get_all_imports`, `setup_virtualenv`.

### Layering

`tests/test_layering.py`'s `LAYERS` becomes, bottom to top:

```python
frozenset({"__init__"}),
frozenset({"settings"}),
frozenset({"analysis", "alias_index", "venv_cache", "stdlib_index",
           "pypi_client", "json_types"}),
frozenset({"state"}),
frozenset({"classify", "environment", "last_used"}),
frozenset({"verify"}),
frozenset({"cache_search"}),
frozenset({"cli"}),
```

`last_used` joins the `classify`/`environment` layer because it imports nothing
from veny at all (only `emmykit`, `datetime`, `re`, `os`, `logging`). `verify`
gets its own layer above it (it imports `environment` and `alias_index`).
`cache_search` gets its own layer above `verify` (it imports `verify`,
`environment`, `venv_cache`, `last_used` and `stdlib_index`). **No new entry in
`SANCTIONED_EXCEPTIONS` is required** — verify that claim by running the
layering suite, not by reading this sentence.

### Complete call-site table (measured — this is the whole list)

`cli.py` call sites that change:

| Site | Today | After |
|---|---|---|
| `cli.py:349` | `load_last_used_venv_python(options)` | `last_used.load_last_used_venv_python(...)` |
| `cli.py:529` | `is_virtualenv()` | `last_used.is_virtualenv()` |
| `cli.py:532` | `check_packages_in_venv(options)` | `verify.check_packages_in_venv(...)` — see Task 3 Step 6 |
| `cli.py:554` | `find_match_dir_in_cache(options)` | `cache_search.find_match_dir_in_cache(...)` |
| `cli.py:605` | `rename_venv(options, ...)` | `options.set_venv_dir(cache_search.rename_venv(...))` |
| `cli.py:1182` (`_probe_venv`) | `check_packages_in_venv(options, record=..., venv_dir=...)` | `verify.check_packages_in_venv(environment.venv_python_for(venv_dir), record=...)` |
| `cli.py:1727` (`setup_virtualenv`) | `interpreter_tag(options)` | `cache_search.interpreter_tag(options.stdlib)` |
| `cli.py:1781` | `verify_and_repair_imports(options)` | `options.uninstalled_imports = set(verify.verify_and_repair_imports(...))` |
| `cli.py:1785` | `record_venv_state(options)` | `options.set_venv_dir(cache_search.record_venv_state(...))` |
| `cli.py:1787` | `check_packages_in_venv(options)` | `verify.check_packages_in_venv(...)` |

> **[EXECUTION] This table is not "the whole list", and the gap was large.**
> Task 9 re-derived it from the tree with
> `rg -n 'verify\.|cache_search\.|last_used\.|environment\.' src/veny/*.py`
> and found **26 named call sites (40 once each `check_venv_dir` branch and
> each duplicated site is counted separately) carrying 147 arguments** —
> against the **14 rows** above. Twelve of the 26 have no row here at all,
> including every `environment.*` site the extraction created
> (`create_venv`/`venv_build_interpreter` at two places, `run_uv_pip`,
> `write_requirements_file_with_extras`, `parse_extra_requirements`), all
> three `verify.source_import_names` sites, both `cache_search.interpreter_tag`
> sites, `venv_cache.build_folder_name`, and `cli._load_last_used` →
> `last_used.load_last_used_options`, which has no row whatsoever. Row 9's
> "all four keywords" is also wrong — `load_last_used_venv_python` takes
> **five** arguments. Consequence, measured: **104 of the 147 arguments could
> be replaced with an empty or wrong value with all 338 tests still green**
> before Task 9 closed them. A plan-authored call-site table is a starting
> point for the standing check, never its scope: 3e must re-derive its own
> from the tree.


Test files that must be repointed, with measured counts:

| File | Tests touching 3d symbols | Note |
|---|---|---|
| `tests/test_split_imports.py` | 35 verify + 1 cache | 35 migrate to `tests/test_verify.py` |
| `tests/test_cache_search.py` | 15 | stay, repointed at `cache_search` |
| `tests/test_manifest_writing.py` | 13 | stay, repointed at `cache_search` |
| `tests/test_uv_backend.py` | 2 (6 setattr sites) | stubs repointed |
| `tests/test_classify.py` | 4 setattr sites | repointed at `verify` |
| `tests/test_rename_venv.py` | 3 | stay, repointed at `cache_search` |
| `tests/test_venv_naming.py` | 1 | `interpreter_tag` repointed |
| `tests/test_layering.py` | — | `LAYERS` updated twice (Tasks 2, 6) |

---

## Task 1: A shared wheel-builder fixture for live tests

**Goal:** `tests/test_verify.py` can build a real, installable wheel without
copying 30 lines out of `tests/test_environment.py`.

**Files:**
- Create: `tests/wheels.py`
- Modify: `tests/test_environment.py:27-57` (delete `_build_wheel`, import it)

**Acceptance Criteria:**
- [x] `tests/wheels.py` exposes `build_wheel(directory, *, name="venytest", version="0.1", value=42) -> Path`, byte-identical in behaviour to `tests/test_environment.py`'s current `_build_wheel`
- [x] `tests/test_environment.py` imports it and its live round trip still passes untouched otherwise
- [x] Test count unchanged at 321

**Verify:** `pixi run test -q` → 321 passed

**Steps:**

- [x] **Step 1: Move the helper**

Create `tests/wheels.py` with the body of `_build_wheel` from
`tests/test_environment.py:27-57`, renamed `build_wheel` and with the
docstring kept verbatim (it records that the format was verified against real
`uv pip install` with no network on 2026-08-18):

```python
"""Build a minimal, real, installable wheel for tests that cross the uv boundary."""

import zipfile
from pathlib import Path


def build_wheel(
    directory: Path, *, name: str = "venytest", version: str = "0.1", value: int = 42
) -> Path:
    """Build a minimal, real, installable wheel entirely from scratch.

    A plain zip carrying ``<name>/__init__.py`` plus a
    ``<name>-<version>.dist-info/`` with METADATA, WHEEL and RECORD -- the
    format verified (2026-08-18, while planning phase 3c's Task 1) to install
    through real ``uv pip install`` with no --no-index/--offline flag and no
    network.

    Args:
        directory: Where to write the wheel and its staging tree.
        name:      The distribution and package name.
        version:   The distribution version.
        value:     The integer the built package's ``value`` attribute holds.

    Returns:
        The path to the built wheel.
    """
    staging = directory / "wheel-staging"
    pkg_dir = staging / name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text(f"value = {value}\n")

    dist_info = staging / f"{name}-{version}.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    )
    (dist_info / "WHEEL").write_text(
        "Wheel-Version: 1.0\nGenerator: test_environment\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    (dist_info / "RECORD").write_text("")

    wheel_path = directory / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging))
    return wheel_path
```

- [x] **Step 2: Repoint `tests/test_environment.py`**

Delete its `_build_wheel` and add, beside its other imports:

```python
from tests.wheels import build_wheel
```

Replace its single call `wheel_path = _build_wheel(tmp_path)` with
`wheel_path = build_wheel(tmp_path)`.

- [x] **Step 3: Run the suite**

Run: `pixi run test -q`
Expected: 321 passed. If the `from tests.wheels import ...` form fails to
import, use `from .wheels import build_wheel` — `tests/__init__.py` exists, so
the package-relative form is available; pick whichever the suite accepts and
use the same form in Task 2.

- [x] **Step 4: Commit**

```bash
pixi run pre-commit run --files tests/wheels.py tests/test_environment.py
git add tests/wheels.py tests/test_environment.py
git commit -m "test: share the wheel builder between live boundary tests"
```

---

## Task 2: Characterize the verify boundary before it moves

**Goal:** every behaviour `verify.py` will own is pinned against the *current*
`cli.py` implementation, including one test that crosses the real interpreter
boundary, before a line of it moves.

**Files:**
- Create: `tests/test_verify.py`

**Acceptance Criteria:**
- [x] A **live** test: build a real venv with `environment.create_venv`, install the Task 1 wheel with `environment.install_into_venv`, and assert `cli.import_outcome_in_venv` reports `imported=True` and `providers == frozenset({"venytest"})`; then uninstall and assert `imported=False`, `rejection_kind == "import_failed"`, and a non-empty `detail`. Nothing about the subprocess is stubbed.
- [x] `source_import_names` pinned for three cases: no `--reqs` (returns `all_imports` unchanged), `--reqs` with entries that overlap `all_imports` (they are subtracted), `--reqs` with entries that do not overlap (no change)
- [x] `check_packages_in_venv`'s bulk branch pinned to fail when `source_names` is empty but `uninstalled` is not — the mis-wiring Task 3 makes possible
- [x] Every expected value obtained by running code, and the docstring says how
- [x] Test count rises to 321 + N; record N

**Verify:** `pixi run test tests/test_verify.py -q` → all pass against
*unmoved* `cli.py`

**Steps:**

- [x] **Step 1: Write the live boundary test first**

It is the one test in this file that cannot be faked into passing. Note that it
imports from `veny.cli` — this file is written *before* the move and repointed
in Task 3.

```python
"""Characterize the verification boundary before it becomes veny.verify.

The live test below is the reason this file exists in this order: PROGRESS
records three phase-2 regressions that a green 264-test suite shipped past,
every one of them because the subprocess was stubbed. run_import_check_in_venv
builds a Python source string and hands it to a real interpreter; a fake can
only ever prove the fake.
"""

import shutil

from veny import cli, environment
from veny.alias_index import ResolvedImport
from tests.wheels import build_wheel


def test_a_live_import_check_reports_the_distribution_that_provided_it(tmp_path):
    """import_outcome_in_venv credits the real distribution, from real metadata.

    A bug that would make this fail: import_providers parsing the wrong prefix,
    or run_import_check_in_venv dropping report_providers, would leave
    providers empty -- and an empty providers set makes
    _credited_with_the_import refuse every confirm(), silently disabling the
    alias cache. No unit test with a fake stdout can catch a mismatch between
    the string the probe script prints and the string the parser expects,
    because both sides are written together in the fake.

    Expected values: "venytest" is the distribution name tests/wheels.py builds;
    the run below was executed to confirm the parse, not reasoned about.
    """
    venv_dir = tmp_path / "venv"
    python = shutil.which("python3")
    assert python is not None, "test host must have a python3 on PATH"
    environment.create_venv(venv_dir, python)
    wheel_path = build_wheel(tmp_path)
    venv_python = venv_dir / "bin" / "python"
    assert environment.install_into_venv(venv_python, str(wheel_path)) is True

    options = cli.Options()
    options.set_venv_dir(venv_dir)

    outcome = cli.import_outcome_in_venv(options, "venytest")
    assert outcome.imported is True
    assert outcome.rejection_kind == ""
    assert outcome.providers == frozenset({"venytest"})

    environment.uninstall_from_venv(venv_python, "venytest")
    after = cli.import_outcome_in_venv(options, "venytest")
    assert after.imported is False
    assert after.rejection_kind == "import_failed"
    assert "venytest" in after.detail
```

- [x] **Step 2: Run it and record what it actually reports**

Run: `pixi run test tests/test_verify.py -q`
If `providers` does not come back as `frozenset({"venytest"})`, **do not adjust
the production code** — adjust the assertion to what was measured and say so in
the docstring. The point of this test is to record today's answer.

- [x] **Step 3: Pin `source_import_names`, all three cases**

```python
def test_source_import_names_returns_all_imports_when_reqs_is_off():
    """Without --reqs nothing is subtracted, even if extra_requirements is set.

    A bug that would make this fail: dropping the `getattr(options.args,
    "reqs", False)` guard, which would subtract requirement spellings from a
    run that never asked for them and stop those imports being verified.
    """
    options = cli.Options()
    options.all_imports = {"yaml", "requests"}
    options.extra_requirements = {"requests": None}
    assert cli.source_import_names(options) == {"yaml", "requests"}


def test_source_import_names_subtracts_requirement_spellings_under_reqs():
    """With --reqs the requirement spellings are removed from the source names.

    A bug that would make this fail: subtracting the wrong dict (keys vs
    values), which would leave a pip spelling in the set that import_module()
    can never satisfy, condemning a package that installed perfectly well.
    """
    options = cli.Options()
    options.all_imports = {"yaml", "opencv-python"}
    options.extra_requirements = {"opencv-python": ">=4"}
    options.args.reqs = True
    assert cli.source_import_names(options) == {"yaml"}


def test_source_import_names_leaves_non_overlapping_requirements_alone():
    """A requirement that is not in all_imports subtracts nothing.

    A bug that would make this fail: replacing the set difference with an
    intersection or an assignment, which would empty the result and skip
    verification entirely.
    """
    options = cli.Options()
    options.all_imports = {"yaml"}
    options.extra_requirements = {"requests": None}
    options.args.reqs = True
    assert cli.source_import_names(options) == {"yaml"}
```

- [x] **Step 4: Pin the bulk branch against an empty `source_names`**

This is the test that has to die in Task 9 when the argument is mutated. It
must fail for its own reason, not incidentally.

```python
def test_the_bulk_branch_checks_a_source_name_under_that_name_alone(monkeypatch):
    """A name the user wrote is import-checked under exactly that name.

    A bug that would make this fail: handing the bulk branch an empty
    source_names, which drops the name out of the `entry.import_name in
    source_names` test and falls through to the distribution's whole top-level
    list -- fail-open, because a wrongly resolved pip name then passes on
    whatever it does provide. This is the mis-wiring the STANDING CHECK exists
    to catch, pinned here so the mutation has a named test to kill.

    Expected value obtained by running the current implementation and printing
    the `alternatives` list it builds.
    """
    seen: list[list[list[str]]] = []

    def fake_run(venv_python, alternatives, report_providers=False):
        seen.append(alternatives)
        return True, ""

    monkeypatch.setattr(cli, "run_import_check_in_venv", fake_run)
    monkeypatch.setattr(
        cli.alias_index, "probe_interpreter", lambda _p: ("3.13", {})
    )
    monkeypatch.setattr(
        cli.alias_index,
        "import_names_by_distribution",
        lambda _d: {"opencv-python": frozenset({"cv2", "cv"})},
    )

    options = cli.Options()
    options.set_venv_dir("/tmp/does-not-need-to-exist")
    options.uninstalled_imports = {
        ResolvedImport(import_name="cv2", pip_name="opencv-python")
    }
    assert cli.check_packages_in_venv(options, source_names={"cv2"}) is True
    assert seen == [[["cv2"]]]
```

- [x] **Step 5: Run, then mutate to prove each test can fail**

Run: `pixi run test tests/test_verify.py -q` → all pass.
Then, for each test, make the one-line mutation its docstring names (copy the
file to the scratch directory first; restore from that copy — never
`git checkout --`), run the file, confirm the named test fails, restore.
Record the four mutation results in the commit message.

- [x] **Step 6: Commit**

```bash
pixi run pre-commit run --files tests/test_verify.py
git add tests/test_verify.py
git commit -m "test: characterize the verification boundary before it moves"
```

---

## Task 3: Extract `src/veny/verify.py`

**Goal:** the twelve verification symbols leave `cli.py` with explicit
arguments in place of every `options.<field>` read, and `cli.py` calls them
through the module.

**Files:**
- Create: `src/veny/verify.py`
- Modify: `src/veny/environment.py` (gains `venv_python_for`)
- Modify: `src/veny/cli.py` (delete the moved spans; rewire 5 call sites)
- Modify: `tests/test_layering.py` (`LAYERS` gains `verify`)
- Modify: `tests/test_verify.py` (repoint at `veny.verify`)
- Modify: `tests/test_split_imports.py` (35 tests migrate out; 22 setattr sites)
- Modify: `tests/test_classify.py` (4 setattr sites)
- Modify: `tests/test_uv_backend.py` (4 setattr sites)

**Acceptance Criteria:**
- [x] `src/veny/verify.py` exists with the signatures given in Step 2, and no function in it takes an `Options`
- [x] `environment.venv_python_for(venv_dir)` exists; `cli.venv_python_for` is gone
- [x] `verify_and_repair_imports` **returns** the final uninstalled set instead of mutating `options`
- [x] `tests/test_layering.py` passes with `verify` in its own layer and no new sanctioned exception
- [x] The 35 verify tests measured in `tests/test_split_imports.py` now live in `tests/test_verify.py`, assertions unchanged except where a signature forced it
- [x] `test_a_record_carrying_a_pip_spelling_is_never_repaired` is repaired: it gains a second record that fails the bulk check, with `all_imports` naming only that second record, so deleting the `source_import_names` filter makes it fail
- [x] The already-in-a-venv branch at `cli.py:532` still raises `AssertionError("options.venv_dir must be set")`, not `TypeError`

> **[EXECUTION] Preserved, but it took a fix round, and the branch is
> unreachable either way.** The move dropped `venv_python_for`'s
> `options`-defaulting branch (amendment 11) and with it the assert that
> lived inside it; Task 5's fix round (`937951f`) re-asserted at the `main()`
> call site to restore the exact `AssertionError`. Separately, Task 9's
> standing check could not kill *any* argument of this branch, which is how
> it surfaced that the branch is **unreachable**: nothing between `Options()`
> and the assert ever assigns `venv_dir`, so a real run inside an activated
> virtualenv with an uninstalled import dies on the assertion. Measured
> byte-identical at `313e800` (the assert sat one frame deeper, inside
> `cli.venv_python_for`), so this is **pre-existing and out of scope for a
> behaviour-preserving phase** — it is PROGRESS's already-recorded
> `AssertionError` crash #2, re-found from a new direction, not a new one.
> `test_main_checks_the_surrounding_virtualenv_against_this_runs_imports`
> now pins the wiring so whoever repairs the branch inherits a test.
- [x] `pixi run test` green; lint zero; format clean; mypy ≤ 36

**Verify:** `pixi run test -q` → all pass, and
`pixi run python -c "from veny import verify; print(verify.__file__)"` prints
the new module

**Steps:**

- [x] **Step 1: Add `venv_python_for` to `environment.py`**

Move `cli.py:924-944` into `environment.py`, dropping the `options` parameter
and its `None` branch — every caller now passes a directory:

```python
def venv_python_for(venv_dir: str | os.PathLike[str]) -> Path:
    """Return the interpreter inside a virtual environment.

    Args:
        venv_dir: The venv to look in.

    Returns:
        The path to that venv's python.
    """
    venv_dir = ek.ensure_dir(venv_dir)
    if sys.platform == "win32":
        return (venv_dir / "Scripts" / "python.exe").absolute()
    # Do NOT use resolve() here because this is a symlink and resolve() would break it
    return (venv_dir / "bin" / "python").absolute()
```

Note the pre-existing inconsistency, and **do not fix it here**:
`Options.set_venv_dir` (`cli.py:172`) hardcodes `p / "bin" / "python"` with no
Windows branch. That is today's behaviour on both paths; changing it is a
behaviour change and belongs to phase 4's `VenvHandle`.

- [x] **Step 2: Create `src/veny/verify.py` with these exact signatures**

Move the bodies verbatim; change only what the argument list forces.

```python
"""Prove what a virtual environment really provides, and repair what it does not."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path

from . import alias_index, environment
from .alias_index import ResolvedImport

MACHINE_SCOPED_IMPORT_MARKERS: tuple[str, ...] = (...)   # verbatim from cli.py:692-696
_SHARED_LIBRARY_PATTERN = re.compile(...)                # verbatim from cli.py:698-700


@dataclass(frozen=True)
class ImportOutcome:            # verbatim from cli.py:703-728
    ...


def import_error_detail(output: str) -> str: ...          # verbatim
def import_providers(output: str) -> frozenset[str]: ...  # verbatim
def _credited_with_the_import(outcome: bool | ImportOutcome, pip_name: str) -> bool: ...
def run_import_check_in_venv(
    venv_python: str | os.PathLike[str],
    alternatives: list[list[str]],
    report_providers: bool = False,
) -> tuple[bool, str]: ...                                # verbatim
def resolve_and_verify(
    resolution: alias_index.Resolution,
    index: alias_index.AliasIndex,
    installer: Callable[[str], bool],
    importer: Callable[[str], bool | ImportOutcome],
    uninstaller: Callable[[str], None],
    max_attempts: int = 3,
) -> alias_index.Candidate | None: ...                    # verbatim


def import_outcome_in_venv(
    venv_python: str | os.PathLike[str], import_name: str
) -> ImportOutcome:
    """(body of cli.py:769-821, with the first statement becoming:)"""
    imported, output = run_import_check_in_venv(
        venv_python, [[import_name]], report_providers=True
    )
    ...


def source_import_names(
    all_imports: AbstractSet[str],
    extra_requirements: Mapping[str, str | None],
    use_reqs: bool,
) -> set[str]:
    """(body of cli.py:1021-1043, reading the three arguments instead of options)"""
    names = set(all_imports)
    if use_reqs:
        names -= set(extra_requirements)
    return names


def check_packages_in_venv(
    venv_python: str | os.PathLike[str],
    *,
    record: ResolvedImport | None = None,
    uninstalled: AbstractSet[ResolvedImport] = frozenset(),
    source_names: AbstractSet[str] = frozenset(),
) -> bool:
    """(body of cli.py:1046-1133, minus the venv_python_for call and minus the
    `if source_names is None` default -- the caller now always supplies it)"""


def repair_unsatisfied_import(
    record: ResolvedImport,
    installed_distributions: dict[str, frozenset[str]],
    outcome: ImportOutcome,
    *,
    venv_python: str | os.PathLike[str],
    index: alias_index.AliasIndex,
    rawlog: bool,
) -> ResolvedImport:
    """(body of cli.py:1366-1438; options.venv_python -> venv_python,
    options.aliases -> index, options.rawlog -> rawlog, and the inner
    `importer` closure calls import_outcome_in_venv(venv_python, import_name))"""


def confirm_if_attributable(
    record: ResolvedImport,
    installed_distributions: dict[str, frozenset[str]],
    index: alias_index.AliasIndex,
) -> None:
    """(body of cli.py:1441-1480; options.aliases -> index)"""


def verify_and_repair_imports(
    *,
    venv_python: str | os.PathLike[str],
    requirements_file: Path,
    uninstalled: AbstractSet[ResolvedImport],
    extra_requirements: Mapping[str, str | None],
    source_names: AbstractSet[str],
    index: alias_index.AliasIndex,
    rawlog: bool,
) -> frozenset[ResolvedImport]:
    """Record what the install actually provided, and repair what it did not.

    (docstring body of cli.py:1483-1501 kept verbatim, plus:)

    Returns:
        The final uninstalled records -- the input set with every repaired
        record replaced. Returned rather than written back onto a shared
        object, because the design's mutation direction is that each stage
        returns its product.
    """
```

`verify_and_repair_imports`'s body changes in exactly four ways:

1. `from_source = source_import_names(options)` becomes
   `from_source = source_names` (the caller computes it once and passes it to
   both this and the bulk check).
2. `check_packages_in_venv(options)` becomes
   `check_packages_in_venv(venv_python, uninstalled=uninstalled,
   source_names=source_names)`.
3. The three `assert options.<field> is not None` lines go. Two were dead
   (`uninstalled_imports` is dereferenced two lines above the assert), and the
   remaining `requirements_file` is now a non-optional parameter.
4. The tail becomes:

```python
    final = frozenset(uninstalled)
    if repaired:
        final = (final - frozenset(repaired)) | frozenset(repaired.values())
        # Keep the venv's own requirements.txt describing what is really installed.
        environment.write_requirements_file_with_extras(
            requirements_file,
            (record.pip_name for record in final),
            extra_requirements,
        )
    return final
```

- [x] **Step 3: Delete the moved spans from `cli.py` and import the module**

Add `verify` to the existing `from . import classify, environment, json_types,
venv_cache` line (keep it alphabetical: `classify, environment, json_types,
venv_cache, verify`). Delete `cli.py:678-728`, `731-766`, `769-843`, `846-944`,
`947-1133`, `1366-1555`. Leave `warn_about_system_packages` (`1136-1150`) and
`_probe_venv` (`1153-1188`) where they are.

- [x] **Step 4: Rewire `cli._probe_venv`**

```python
        def is_importable(import_name: str) -> bool:
            """Report whether one import name imports in the probe venv.

            Args:
                import_name: The name as it would be written in source.

            Returns:
                True if the probe venv can import it.
            """
            return verify.check_packages_in_venv(
                environment.venv_python_for(venv_dir),
                record=ResolvedImport(import_name=import_name, pip_name=import_name),
            )
```

- [x] **Step 5: Rewire `cli.setup_virtualenv`**

Replace `verify_and_repair_imports(options)` at `cli.py:1781` and the bulk
check at `:1787`:

```python
    source_names = verify.source_import_names(
        options.all_imports,
        options.extra_requirements,
        getattr(options.args, "reqs", False),
    )
    assert options.requirements_file is not None, (
        "options.requirements_file must be set"
    )
    options.uninstalled_imports = set(
        verify.verify_and_repair_imports(
            venv_python=options.venv_python,
            requirements_file=options.requirements_file,
            uninstalled=options.uninstalled_imports,
            extra_requirements=options.extra_requirements,
            source_names=source_names,
            index=options.aliases,
            rawlog=options.rawlog,
        )
    )
    record_venv_state(options)
    return verify.check_packages_in_venv(
        environment.venv_python_for(options.venv_dir),
        uninstalled=options.uninstalled_imports,
        source_names=source_names,
    )
```

- [x] **Step 6: Rewire `cli.py:532` and preserve its crash exactly**

That branch runs with `options.venv_dir` still `None` (a pre-existing defect
PROGRESS records and the design puts out of scope). Today the `AssertionError`
comes from inside `venv_python_for`. Reproduce it at the call site so the
exception type and message are unchanged:

```python
    elif last_used.is_virtualenv():
        if not options.rawlog:
            logging.info("Already in a virtual environment.")
        assert options.venv_dir is not None, "options.venv_dir must be set"
        if verify.check_packages_in_venv(
            environment.venv_python_for(options.venv_dir),
            uninstalled=options.uninstalled_imports,
            source_names=verify.source_import_names(
                options.all_imports,
                options.extra_requirements,
                getattr(options.args, "reqs", False),
            ),
        ):
```

(`last_used.is_virtualenv` lands in Task 5; until then leave `is_virtualenv()`
as it is and change only the `check_packages_in_venv` call.)

- [x] **Step 7: Update `tests/test_layering.py`**

Insert `frozenset({"verify"})` between the `{"classify", "environment"}` layer
and `{"cli"}`, with a comment saying why it is not a peer of `environment`:
`verify` installs, uninstalls and rewrites `requirements.txt` through it
(design amendment 10).

- [x] **Step 8: Migrate the 35 verify tests and repoint every stub**

Move these 35 test functions from `tests/test_split_imports.py` to
`tests/test_verify.py` **with their assertions unchanged**, adjusting only the
call signature and the patch target:

`test_first_working_candidate_is_confirmed`,
`test_a_candidate_credited_to_another_distribution_is_not_confirmed`,
`test_a_candidate_credited_with_the_import_is_confirmed`,
`test_candidate_that_installs_but_does_not_import_is_uninstalled`,
`test_failed_install_is_recorded_but_not_uninstalled`,
`test_attempts_are_bounded`,
`test_empty_resolution_never_touches_the_installer`,
`test_check_packages_in_venv_import_checks_the_import_name`,
`test_check_packages_in_venv_without_a_record_checks_every_import_name`,
`test_check_packages_in_venv_bulk_branch_resolves_requirement_via_venv_metadata`,
`test_check_packages_in_venv_bulk_branch_matches_pep503_spelling`,
`test_check_packages_in_venv_bulk_branch_falls_back_when_distribution_unknown`,
`test_check_packages_in_venv_probes_the_venv_once_per_call`,
`test_check_packages_in_venv_passes_when_any_top_level_name_imports`,
`test_check_packages_in_venv_bulk_branch_checks_the_records_own_import_name`,
`test_check_packages_in_venv_bulk_branch_fails_an_unprovided_source_import`,
`test_check_packages_in_venv_still_fails_a_genuinely_missing_package`,
`test_a_verified_import_is_written_to_the_alias_cache`,
`test_an_import_provided_by_another_distribution_is_not_confirmed`,
`test_an_import_attributable_to_its_own_distribution_is_confirmed`,
`test_an_import_the_batch_install_did_not_provide_is_repaired`,
`test_the_repair_path_import_checks_the_import_name_never_the_pip_name`,
`test_a_record_carrying_a_pip_spelling_is_never_repaired`,
`test_a_repair_that_cannot_succeed_leaves_the_run_going`,
`test_a_missing_shared_library_is_classified_as_machine_scoped`,
`test_an_absent_module_is_still_classified_as_a_package_fault`,
`test_a_working_import_reports_no_rejection`,
`test_a_successful_import_reports_which_distribution_provided_it`,
`test_a_per_record_success_credited_elsewhere_is_not_confirmed`,
`test_a_second_candidates_machine_scoped_failure_is_also_not_persisted`,
`test_a_missing_shared_library_is_reported_to_the_user`,
`test_a_machine_scoped_failure_leaves_no_persisted_rejection`,
`test_a_package_that_lacks_the_import_is_still_rejected_durably`,
`test_a_repair_rewrites_requirements_txt_with_the_extra_requirements`,
`test_the_repair_installer_is_given_the_venvs_own_interpreter`.

The 22 `monkeypatch.setattr(veny, "...", ...)` sites in
`tests/test_split_imports.py` (lines 894, 895, 899, 915, 943, 944, 963, 983,
984, 1016, 1017, 1041, 1042, 1061, 1062, 1163, 1164, 1190, 1191, 1255, 1256,
1292, 1293, 1329, 1330, 1375, 1376) become `monkeypatch.setattr(verify,
"check_packages_in_venv", ...)` / `(verify, "import_outcome_in_venv", ...)` /
`(verify, "verify_and_repair_imports", ...)`, except `record_venv_state`
(line 899) which stays on `cli` until Task 6.

`tests/test_classify.py` lines 130, 526, 543, 581 become
`monkeypatch.setattr(verify, "check_packages_in_venv", ...)`.

`tests/test_uv_backend.py` lines 75, 76, 123, 124 become
`monkeypatch.setattr(verify, "verify_and_repair_imports", ...)` and
`(verify, "check_packages_in_venv", ...)`; lines 77 and 125
(`record_venv_state`) stay on `cli` until Task 6.

**A stub whose signature no longer matches will now be called with the new
keyword arguments.** Rewrite each `lambda opts: ...` to `lambda *a, **k: ...`
only where the test does not assert on the arguments; where it does, update the
assertion to the new argument names rather than loosening it. PROGRESS records
that loosening `write_requirements_file_with_extras`'s stub to `lambda *args`
lost a real assertion.

- [x] **Step 9: Repair the decorative test**

`test_a_record_carrying_a_pip_spelling_is_never_repaired` currently passes
`all_imports=set()`, so `verify_and_repair_imports` returns before reaching the
filter it names — PROGRESS measured that deleting the filter leaves the whole
suite green. Give it a second record that fails the bulk check, with
`source_names` naming only that second record:

```python
def test_a_record_carrying_a_pip_spelling_is_never_repaired(monkeypatch, tmp_path):
    """A --reqs record whose "import name" is a pip name is never uninstalled.

    A bug that would make this fail: dropping the source_names filter in
    verify_and_repair_imports, which would send the pip-spelled record down the
    repair path -- uninstalling a package that installed perfectly well,
    because import_module() can never succeed on "opencv-python".

    The second record is what makes this test load-bearing: with only the
    pip-spelled record present the function returns before the filter is
    reached, and PROGRESS records that the earlier version of this test passed
    with the filter deleted.
    """
    ...
    assert fake.uninstalled == []
```

Then prove it: delete the filter, run this test, confirm it now fails, restore
the filter. Record the evidence in the commit message.

- [x] **Step 10: Run everything**

```
pixi run test -q
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
```
Expected: suite green; lint zero; format clean; mypy ≤ 36 — and record the
per-file breakdown, because 17 of `test_split_imports.py`'s 21 errors travel to
`test_verify.py` with the tests that carry them.

- [x] **Step 11: Commit**

```bash
pixi run pre-commit run --files src/veny/verify.py src/veny/environment.py \
    src/veny/cli.py tests/test_verify.py tests/test_split_imports.py \
    tests/test_classify.py tests/test_uv_backend.py tests/test_layering.py
git add -u
git add src/veny/verify.py
git commit -m "refactor: extract src/veny/verify.py"
```

---

## Task 4: Characterize the last-used loader before it moves

**Goal:** the three last-used behaviours are pinned before the module exists —
they have **zero** direct tests today (measured: `load_last_used_venv_python`
has two references in `src/` and none in `tests/`).

**Files:**
- Create: `tests/test_last_used.py`

**Acceptance Criteria:**
- [x] `load_last_used_options` pinned to pick the **most recent** JSON when several match, and to return `None` when the directory holds none
- [x] The `pathlibcutoff` filter pinned: a JSON whose timestamp is older than the cutoff is ignored
- [x] `load_last_used_venv_python` pinned to return `None` when the recorded interpreter no longer exists on disk, and the path when it does
- [x] Each expected value obtained by writing real files into `tmp_path` and running the current `cli.py`

**Verify:** `pixi run test tests/test_last_used.py -q` → all pass against
*unmoved* `cli.py`

**Steps:**

- [x] **Step 1: Write the tests**

**First, measure the filename format**, rather than transcribing it: build an
`Options`, point `script_dir`/`python_script`/`timestamp` at a `tmp_path`
script, call `ek.save_options_to_json(options)`, and print
`options.options_json_filepath.name`. `cli.py:1843`'s regex
(`last-used-on-(\d{8}-\d{6})`) and its `f.name.startswith("." +
options.python_script.name)` prefix test are what the fixture must satisfy;
the printed name is the authority on the rest.

```python
"""Characterize the last-used record before it becomes veny.last_used."""

import json

import emmykit as ek

from veny import cli


def _write_record(script_dir, script, stamp, payload):
    """Write one last-used options JSON the loader will recognise.

    Args:
        script_dir: The directory the loader scans.
        script:     The script Path the record belongs to.
        stamp:      The "YYYYmmdd-HHMMSS" the filename carries.
        payload:    The JSON body, already jsonable.

    Returns:
        The path written.
    """
    path = script_dir / f".{script.name}-veny-last-used-on-{stamp}.json"
    path.write_text(json.dumps(payload))
    return path


def _options_for(tmp_path):
    """An Options pointed at a real script inside tmp_path."""
    script = tmp_path / "thing.py"
    script.write_text("import yaml\n")
    options = cli.Options()
    options.python_script = script
    options.script_dir = tmp_path
    return options


def test_the_most_recent_matching_json_wins(tmp_path):
    """Two candidates, and the newer timestamp is the one loaded.

    A bug that would make this fail: dropping the reverse=True on the sort,
    which would resurrect the oldest venv on every run and quietly stop the
    cache from ever advancing.

    Expected value: the venv_dir recorded in the *newer* file. Obtained by
    running the current loader against both files, not by reading the sort key.
    """
    options = _options_for(tmp_path)
    _write_record(tmp_path, options.python_script, "20260101-010101",
                  {"venv_dir": str(tmp_path / "older")})
    _write_record(tmp_path, options.python_script, "20260202-020202",
                  {"venv_dir": str(tmp_path / "newer")})
    loaded = cli.load_last_used_options(options)
    assert loaded is not None
    assert str(loaded.venv_dir).endswith("newer")


def test_a_json_older_than_the_pathlib_cutoff_is_ignored(tmp_path):
    """Pre-cutoff files stored paths as strings and must not be loaded.

    A bug that would make this fail: comparing the timestamps as numbers, or
    dropping the `>= options.pathlibcutoff` term, which would feed str-typed
    paths into code that calls Path methods on them. The cutoff is
    "20250810-224900" (cli.py's Options default).
    """
    options = _options_for(tmp_path)
    _write_record(tmp_path, options.python_script, "20250101-000000",
                  {"venv_dir": str(tmp_path / "ancient")})
    assert cli.load_last_used_options(options) is None


def test_no_matching_json_returns_none(tmp_path):
    """An empty script directory yields None, not an exception."""
    options = _options_for(tmp_path)
    assert cli.load_last_used_options(options) is None


def test_a_recorded_interpreter_that_no_longer_exists_returns_none(tmp_path):
    """A deleted venv's interpreter is not offered to --feeling-lucky.

    A bug that would make this fail: dropping the ek.safe_is_file guard, which
    would hand main() a path to a missing interpreter and turn
    --feeling-lucky's fast path into a FileNotFoundError.
    """
    options = _options_for(tmp_path)
    _write_record(tmp_path, options.python_script, "20260202-020202",
                  {"venv_python": str(tmp_path / "gone" / "bin" / "python")})
    assert cli.load_last_used_venv_python(options) is None


def test_a_recorded_interpreter_that_exists_is_returned(tmp_path):
    """The happy path, so the guard above cannot pass by always returning None."""
    options = _options_for(tmp_path)
    interpreter = tmp_path / "venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("")
    _write_record(tmp_path, options.python_script, "20260202-020202",
                  {"venv_python": str(interpreter)})
    assert cli.load_last_used_venv_python(options) == interpreter
```

If `ek.load_options_from_json` rejects a hand-written payload (it round-trips
tagged values, so a bare string may not decode to a `Path`), write the fixtures
with `ek.save_options_to_json` instead and keep the assertions. Whichever route
works, say in the module docstring which one was used and why.

- [x] **Step 2: Run, and mutate to prove each can fail**

Run: `pixi run test tests/test_last_used.py -q`
Then delete the `reverse=True`, then the `>= options.pathlibcutoff` term, then
the `ek.safe_is_file` guard — one at a time, restoring from a scratch copy each
time — and confirm the named test fails each time.

- [x] **Step 3: Commit**

```bash
pixi run pre-commit run --files tests/test_last_used.py
git add tests/test_last_used.py
git commit -m "test: characterize the last-used record before it moves"
```

---

## Task 5: Extract `src/veny/last_used.py`

**Goal:** the last-used record's three live functions leave `cli.py`; the dead
fourth is deleted.

**Files:**
- Create: `src/veny/last_used.py`
- Modify: `src/veny/cli.py` (delete `1834-1933`; rewire `:349`, `:529`)
- Modify: `tests/test_layering.py` (`last_used` joins the classify/environment layer)
- Modify: `tests/test_last_used.py` (repoint)
- Modify: `tests/test_cache_search.py:289` (setattr target)

**Acceptance Criteria:**
- [x] `src/veny/last_used.py` imports nothing from veny — only stdlib and emmykit
- [x] `load_last_used_venv_dir` is deleted, not moved
- [x] `cli.py:349` and `cli.py:529` call through `last_used`
- [x] `tests/test_layering.py` passes with `last_used` in the `{"classify", "environment"}` layer
- [x] `pixi run test` green; lint zero; format clean; mypy ≤ 36

**Verify:** `pixi run test -q` → all pass;
`rg -n '^from \.|^from veny' src/veny/last_used.py` → no veny imports

**Steps:**

- [x] **Step 1: Create the module**

```python
"""The one record veny keeps between runs: which environment last ran this script."""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
from pathlib import Path

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
    """(docstring of cli.py:1840 verbatim)

    The `options` argument is the template ek.load_options_from_json fills in;
    it is annotated ek.Options rather than veny's own subclass so this module
    can stay free of any veny import.
    """


def load_last_used_venv_python(
    options: ek.Options,
    *,
    script_dir: Path,
    python_script: Path,
    pathlibcutoff: str,
    rawlog: bool,
) -> Path | None:
    """(docstring of cli.py:1899 verbatim)"""
```

Both bodies are `cli.py:1841-1864` and `cli.py:1907-1933` with
`options.script_dir` → `script_dir`, `options.python_script` → `python_script`,
`options.pathlibcutoff` → `pathlibcutoff`, `options.rawlog` → `rawlog`. The two
`assert ... is not None` lines at `cli.py:1841-1842` go: the parameters are
non-optional. `load_last_used_venv_python` calls `load_last_used_options` with
the same keywords it received.

`is_virtualenv` needs `import sys`; keep the import list minimal and let
`ruff check` tell you what is unused.

- [x] **Step 2: Delete `cli.py:1834-1933` entirely**

That span is all four functions, including `load_last_used_venv_dir`
(`1867-1895`), which is deleted rather than moved: measured zero references in
`src/` and `tests/`, and already dead at `dc1c3c4`.

- [x] **Step 3: Rewire `cli.py`**

Add `last_used` to the `from . import ...` line. At `:349`:

```python
        last_used_venv_python = last_used.load_last_used_venv_python(
            options,
            script_dir=options.script_dir,
            python_script=options.python_script,
            pathlibcutoff=options.pathlibcutoff,
            rawlog=options.rawlog,
        )
```

`options.script_dir` is `Path | None`; it is not None inside this branch
(guarded by `options.python_script` being truthy, which is where `script_dir`
is set at `:341`). Add `assert options.script_dir is not None` immediately
above, matching the assertion the old body carried.

At `:529`, `is_virtualenv()` becomes `last_used.is_virtualenv()`.

- [x] **Step 4: Update the layering test and the one test stub**

`LAYERS`'s `frozenset({"classify", "environment"})` becomes
`frozenset({"classify", "environment", "last_used"})`, with a comment: it
imports nothing from veny, so it forbids everything at or above its layer and
needs nothing from its peers.

`tests/test_cache_search.py:289`'s
`monkeypatch.setattr(veny, "load_last_used_options", lambda opts: ek.Options())`
becomes `monkeypatch.setattr(last_used, "load_last_used_options", lambda *a, **k: ek.Options())`
— and note that Task 6 replaces this patch entirely with an injected callable.

- [x] **Step 5: Run the gates and commit**

```bash
pixi run test -q && pixi run lint && pixi run python -m ruff format --check . && pixi run typecheck
pixi run pre-commit run --files src/veny/last_used.py src/veny/cli.py \
    tests/test_last_used.py tests/test_layering.py tests/test_cache_search.py
git add -u && git add src/veny/last_used.py
git commit -m "refactor: extract src/veny/last_used.py and delete its dead loader"
```

---

## Task 6: Extract `src/veny/cache_search.py`

**Goal:** the fourteen cache-selection and manifest symbols leave `cli.py`,
with the last-used loader injected as a callable rather than reached for.

**Files:**
- Create: `src/veny/cache_search.py`
- Modify: `src/veny/cli.py` (delete the moved spans; rewire 4 call sites)
- Modify: `tests/test_layering.py` (`cache_search` gets its own layer)
- Modify: `tests/test_cache_search.py`, `tests/test_manifest_writing.py`,
  `tests/test_rename_venv.py`, `tests/test_venv_naming.py`,
  `tests/test_uv_backend.py`, `tests/test_split_imports.py` (repoint)

**Acceptance Criteria:**
- [x] `src/veny/cache_search.py` exists with the signatures in Step 1; no function in it takes an `Options`
- [x] `rename_venv` and `record_venv_state` **return** the (possibly new) venv directory instead of mutating `options`
- [x] `find_match_dir_in_cache` takes the `argparse.Namespace` and a
      `load_last_used: Callable[[], ek.Options | None]`, and its four flag
      writes are preserved exactly (design amendment 9)
- [x] `rename_venv`'s single-element tuple loop is gone (deferred item closed)
- [x] `tests/test_layering.py` passes with `cache_search` above `verify`
- [x] `pixi run test` green; lint zero; format clean; mypy ≤ 36

**Verify:** `pixi run test -q` → all pass;
`pixi run python -c "from veny import cache_search; print(cache_search.__file__)"`

**Steps:**

- [x] **Step 1: Create the module with these signatures**

```python
"""Choose a cached virtual environment, and record the state of a fresh one."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
from collections.abc import Callable, Mapping, Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path

import emmykit as ek

from . import __version__, alias_index, environment, stdlib_index, venv_cache, verify
from .alias_index import ResolvedImport


def interpreter_tag(stdlib: stdlib_index.StdlibIndex) -> str: ...
def installed_state_in_venv(
    venv_python: str | os.PathLike[str],
) -> tuple[dict[str, str], str]: ...
def manifest_for(
    *,
    uninstalled: AbstractSet[ResolvedImport],
    extra_requirements: Mapping[str, str | None],
    timestamp: str,
    python_command: str,
    run_tag: str,
    versions: dict[str, str],
    venv_tag: str = "",
) -> venv_cache.Manifest: ...
def rename_venv(venv_dir: Path, new_name: str) -> Path: ...
def record_venv_state(
    venv_dir: Path,
    *,
    venv_python: str | os.PathLike[str],
    venv_name: str,
    timestamp: str,
    run_tag: str,
    python_command: str,
    uninstalled: AbstractSet[ResolvedImport],
    extra_requirements: Mapping[str, str | None],
    rawlog: bool,
) -> Path: ...
def latest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None: ...
def oldest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None: ...
def smallest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None: ...
def wanted_packages(
    uninstalled: AbstractSet[ResolvedImport],
    extra_requirements: Mapping[str, str | None],
) -> list[venv_cache.Wanted]: ...


@dataclass(frozen=True)
class CacheCandidate: ...          # verbatim from cli.py:2089-2106


def cache_candidates(
    folders: list[Path],
    *,
    wanted: list[venv_cache.Wanted],
    tag: str,
    rawlog: bool,
) -> list[CacheCandidate]: ...
def check_venv_dir(
    venv_dir: str | os.PathLike[str],
    *,
    wanted: list[venv_cache.Wanted],
    tag: str,
    uninstalled: AbstractSet[ResolvedImport],
    source_names: AbstractSet[str],
    rawlog: bool,
    manifest: venv_cache.Manifest | None = None,
) -> bool: ...
def find_match_dir_in_cache(
    args: argparse.Namespace,
    *,
    my_dir: Path,
    venv_name: str,
    uninstalled: AbstractSet[ResolvedImport],
    extra_requirements: Mapping[str, str | None],
    source_names: AbstractSet[str],
    tag: str,
    rawlog: bool,
    load_last_used: Callable[[], ek.Options | None],
) -> Path | None: ...
```

Body changes, all mechanical:

- `interpreter_tag`: `options.stdlib.python_version` → `stdlib.python_version`.
- `installed_state_in_venv`: the `assert options.venv_python is not None` goes
  (the parameter is non-optional); `options.venv_python` → `venv_python`.
- `manifest_for`: `interpreter_tag(options)` → `run_tag`;
  `options.timestamp` → `timestamp`; `options.python_command` →
  `python_command`; `options.uninstalled_imports` → `uninstalled`;
  `options.extra_requirements` → `extra_requirements`.
- `rename_venv`: takes the directory, returns the new one, and the
  `for path in (venv_dir / "pyvenv.cfg",):` loop collapses to a straight-line
  block over the single path (deferred item closed). It no longer calls
  `set_venv_dir`; the caller does. Early return becomes `return venv_dir` when
  the name is unchanged.
- `record_venv_state`: `rename_venv(options, ...)` becomes
  `venv_dir = rename_venv(venv_dir, ...)`, and the function returns `venv_dir`
  after `venv_cache.write_manifest(venv_dir, ...)`.
- `check_venv_dir`: `wanted_packages(options)`/`interpreter_tag(options)`
  become the `wanted`/`tag` parameters; `check_packages_in_venv(options,
  venv_dir=..., source_names=...)` becomes
  `verify.check_packages_in_venv(environment.venv_python_for(venv_dir),
  uninstalled=uninstalled, source_names=source_names)`; and the manifest read
  becomes `manifest = manifest if manifest is not None else
  venv_cache.read_manifest(venv_dir)` — **the default path is unchanged in this
  task**; Task 7 is what starts passing one in.
- `cache_candidates`: takes `wanted` and `tag` instead of computing them from
  `options`.
- `find_match_dir_in_cache`: `options.my_dir` → `my_dir`, `options.venv_name` →
  `venv_name`, `options.rawlog` → `rawlog`, `options.args` → `args` (still
  read *and written*, deliberately — amendment 9),
  `load_last_used_options(options)` → `load_last_used()`, and each
  `check_venv_dir(options, X)` → `check_venv_dir(X, wanted=wanted, tag=tag,
  uninstalled=uninstalled, source_names=source_names, rawlog=rawlog)`.
  Compute `wanted = wanted_packages(uninstalled, extra_requirements)` once at
  the top and pass it to both `cache_candidates` and every `check_venv_dir`.

- [x] **Step 2: Delete the moved spans from `cli.py`**

Delete `cli.py:1349-1363`, `1558-1621`, `1624-1669`, `1672-1717`, `1790-1831`,
`1936-2296`. Add `cache_search` to the `from . import ...` line.

- [x] **Step 3: Rewire the four `cli.py` call sites**

`setup_virtualenv`'s folder name (`:1725-1730`):

```python
    run_tag = cache_search.interpreter_tag(options.stdlib)
    folder_name = venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=run_tag,
        timestamp=options.timestamp,
        pip_names=[record.pip_name for record in options.uninstalled_imports],
    )
```

`setup_virtualenv`'s state record (replacing `record_venv_state(options)`):

```python
    options.set_venv_dir(
        cache_search.record_venv_state(
            options.venv_dir,
            venv_python=options.venv_python,
            venv_name=options.venv_name,
            timestamp=options.timestamp,
            run_tag=run_tag,
            python_command=options.python_command,
            uninstalled=options.uninstalled_imports,
            extra_requirements=options.extra_requirements,
            rawlog=options.rawlog,
        )
    )
```

`main()`'s cache search (`:554`):

```python
            match_dir = cache_search.find_match_dir_in_cache(
                options.args,
                my_dir=options.my_dir,
                venv_name=options.venv_name,
                uninstalled=options.uninstalled_imports,
                extra_requirements=options.extra_requirements,
                source_names=verify.source_import_names(
                    options.all_imports,
                    options.extra_requirements,
                    getattr(options.args, "reqs", False),
                ),
                tag=cache_search.interpreter_tag(options.stdlib),
                rawlog=options.rawlog,
                load_last_used=lambda: last_used.load_last_used_options(
                    options,
                    script_dir=options.script_dir,
                    python_script=options.python_script,
                    pathlibcutoff=options.pathlibcutoff,
                    rawlog=options.rawlog,
                ),
            )
```

`main()`'s success rename (`:605`):

```python
                options.set_venv_dir(
                    cache_search.rename_venv(
                        options.venv_dir,
                        options.venv_dir.name.removeprefix("failed-"),
                    )
                )
```

**Careful:** `set_venv_dir` calls `mkdir(parents=True, exist_ok=True)` on the
directory it is given. The old `rename_venv` also called `set_venv_dir`, so
this is the same number of `mkdir` calls on the same path, not a new one.
Confirm that by reading `set_venv_dir` before you claim it.

- [x] **Step 4: Update the layering test**

Insert `frozenset({"cache_search"})` between `{"verify"}` and `{"cli"}`, with a
comment: it selects a cached environment and confirms the selection by
import-checking it, so it sits above `verify`.

- [x] **Step 5: Repoint the four test files**

`tests/test_manifest_writing.py` (13 tests), `tests/test_cache_search.py` (15),
`tests/test_rename_venv.py` (3) and `tests/test_venv_naming.py` (1) all change
from `veny.<symbol>(options, ...)` to `cache_search.<symbol>(...)` with the new
argument lists. Keep every assertion. Two specific changes:

- `tests/test_cache_search.py:289`'s `monkeypatch.setattr` of the last-used
  loader is **deleted**; the test passes `load_last_used=lambda: ek.Options()`
  instead. That is the injection this extraction buys.
- `tests/test_rename_venv.py`'s three tests assert on `options.venv_dir` after
  the call; they now assert on the returned path, and one of them must also
  assert the returned path is what a caller would set — otherwise a
  `return old_dir` mutation survives.

`tests/test_uv_backend.py:77,125` and `tests/test_split_imports.py:899`
(`record_venv_state` stubs) become
`monkeypatch.setattr(cache_search, "record_venv_state", lambda *a, **k: <the
venv dir>)` — note the stub must now **return a Path**, since
`setup_virtualenv` feeds the result to `set_venv_dir`. A stub returning `None`
here is exactly the kind of seam defect this plan's Task 9 hunts; make the stub
return the directory it was given.

- [x] **Step 6: Run the gates and commit**

```bash
pixi run test -q && pixi run lint && pixi run python -m ruff format --check . && pixi run typecheck
pixi run pre-commit run --files src/veny/cache_search.py src/veny/cli.py tests/
git add -u && git add src/veny/cache_search.py
git commit -m "refactor: extract src/veny/cache_search.py"
```

---

## Task 7: Stop reading the manifest twice (design ledger item 2)

**Goal:** close the design's own ledger item — `satisfies()` running twice on
the winning candidate, once in `cache_candidates` and again in
`check_venv_dir`, which re-reads the manifest from disk.

**This is a deliberate behaviour change**, sanctioned by the design
("Closed in phase 3: `find_match_dir_in_cache` passes the manifest it already
holds to `check_venv_dir`, which is left doing only the import-level
confirmation"). It is the only such change in this plan besides the three
deletions.

**Files:**
- Modify: `src/veny/cache_search.py`
- Modify: `tests/test_cache_search.py`

**Acceptance Criteria:**
- [x] `find_match_dir_in_cache` keeps the `CacheCandidate` for each ranked folder and passes its already-read `manifest` into `check_venv_dir`
- [x] `check_venv_dir` with a supplied manifest performs **zero** `read_manifest` calls and **one** `satisfies` call

> **[EXECUTION] This criterion is wrong, and a half-fix satisfied it.** The
> design it cites says `check_venv_dir` "is left doing only the import-level
> confirmation" — which means **zero** `satisfies` calls on the supplied
> manifest, not one, because `cache_candidates` has already run it. Writing
> "one" into the acceptance criteria made the first attempt (`93bca53`) look
> complete: it removed the redundant `read_manifest` and left the redundant
> `satisfies` in place, meeting every box on this list while closing only
> half of design ledger item 2. The review caught it and `f961ada` finished
> the job — and renamed the parameter `manifest` → **`matched_manifest`**, so
> the trust contract ("this was read from this folder during the scan and has
> already been checked") is stated in the name rather than implied. The real
> post-condition, measured per cache hit: **1 `read_manifest`, 1 `satisfies`
> for the whole search** (down from 2 and 2), with `check_venv_dir` itself
> contributing zero of each on the supplied-manifest path. The last-used
> path, which passes `matched_manifest=None`, still does its own 1 and 1.
> Lesson for 3e: when a criterion restates a design sentence in numbers,
> derive the numbers from the sentence — an off-by-one in an acceptance
> criterion is indistinguishable from success.
- [x] The last-used path, which has no candidate, still reads the manifest itself
- [x] A test counts the `read_manifest` calls for a cache hit and pins the new number
- [x] A folder that loses its manifest between the scan and the check is still handled — pin what happens now

**Verify:** `pixi run test tests/test_cache_search.py -q` → all pass, including
the new call-count test

**Steps:**

- [x] **Step 1: Measure the current call counts first**

Wrap `venv_cache.read_manifest` and `venv_cache.satisfies` with counting
spies in a scratch test, run `find_match_dir_in_cache` against a cache with one
matching folder, and record both numbers. Write them into the commit message.
Do not proceed on the assumption that they are 2 and 2.

- [x] **Step 2: Keep the candidate, not just the folder**

`find_match_dir_in_cache` currently reduces each `CacheCandidate` to two ints
in `final_venv_folders`. Keep a `dict[Path, CacheCandidate]` beside it, and at
each of the three selection branches pass
`manifest=candidates[chosen].manifest` into `check_venv_dir`.

- [x] **Step 3: Write the call-count test**

```python
def test_a_cache_hit_reads_each_manifest_once(monkeypatch, tmp_path):
    """The winning candidate's manifest is read once, not twice.

    A bug that would make this fail: dropping the manifest= argument at a
    selection branch, which restores the second read -- and with it the
    second satisfies() call the design's ledger item 2 names, plus a window
    where a folder changing underneath the run gives two different answers.

    Expected value measured before the change: <N> reads, <M> satisfies calls
    for one matching folder. After: 1 and 1.
    """
```

- [x] **Step 4: Prove the old behaviour is gone and the new one is pinned**

Restore the `manifest=` argument to `None` at one branch, run the test, confirm
it fails, restore.

- [x] **Step 5: Commit**

```bash
pixi run test -q && pixi run lint && pixi run python -m ruff format --check .
pixi run pre-commit run --files src/veny/cache_search.py tests/test_cache_search.py
git add -u
git commit -m "refactor: read a cached venv's manifest once, closing ledger item 2"
```

---

## Task 8: The three dead symbols and the two duplicate helpers

**Goal:** delete what this phase proved dead, and consolidate what it
duplicated, in one reviewable commit.

**Files:**
- Modify: `src/veny/cli.py` (the `installed_imports` chain)
- Modify: `src/veny/classify.py` / `src/veny/state.py` — **only if** the
  `installed_imports` deletion reaches them; see Step 2
- Modify: `tests/test_split_imports.py` (delete `_index_with`)
- Modify: `tests/test_classify.py` (consolidate the two recording helpers)
- Modify: `tests/test_layering.py` (the copy-back guard's field list)

**Acceptance Criteria:**
- [x] `tests/test_split_imports.py`'s `_index_with` is gone
- [x] `tests/test_classify.py` has one recording helper, not two, and the two probe-stubbing idioms are one
- [x] The write-only `options.installed_imports` chain is deleted: the `Options.__init__` default, the copy-back in `cli.split_imports`, and the docstring field description

> **[EXECUTION] "Write-only" was true of `src/`, not of `tests/`.** Task 8's
> brief and this criterion both assumed the chain had no readers anywhere;
> `tests/test_classify.py` held **five live `installed_imports` readers**
> that the deletion broke. They were rewired onto the `Requirements` product
> (`result.installed`) rather than deleted, which is the right outcome — they
> were asserting a real classification fact through veny's mirror of it. The
> measurement that would have caught this before the delete is the one the
> plan prescribes two paragraphs earlier and this task's Step 1 repeats:
> `rg -nw 'installed_imports' src/ tests/` — **with `tests/`**, and with
> `-w`, since `installed_imports` is a substring of `uninstalled_imports`
> and the unworded search returns 26 hits.
- [x] `state.Requirements.installed` is **kept** — `classify` still computes it and it is part of the product; only veny's write-only mirror of it on `Options` goes
- [x] `tests/test_layering.py`'s copy-back totality guard is updated to the four remaining fields, and still fails if a field stops being copied

**Verify:** `pixi run test -q` → green;
`rg -nw 'installed_imports' src/veny/cli.py` → no hits (note `-w`: without it
the pattern also matches `uninstalled_imports`, which is why an earlier
PROGRESS entry miscounted)

**Steps:**

- [x] **Step 1: Re-measure before deleting**

Run `rg -nw 'installed_imports' src/ tests/`. PROGRESS records three hits in
`cli.py` at `143f909` — the `Options.__init__` default, the copy-back, and a
docstring — and that none is a reader. Re-measure on this branch; the line
numbers have moved twice since.

- [x] **Step 2: Delete the chain**

Remove `self.installed_imports: set[...] = set()` from `Options.__init__`, the
`options.installed_imports = set(result.installed)` line from
`cli.split_imports`, and the docstring field description. Do **not** touch
`Requirements.installed` or anything in `classify.py`: classification still
computes it, `tests/test_classify.py` asserts on it, and it is a product field
the design lists.

- [x] **Step 3: Update the copy-back guard**

`tests/test_layering.py:320`'s guard proves the copy-back is *total*. Its field
list must drop `installed_imports` and still fail when a remaining field stops
being copied — prove that by deleting one copy-back line and watching it fail.
PROGRESS also records that this guard proves totality and **not** source
correctness (`options.bad_imports = set(result.installed)` still passes it);
leave that limitation as it is, but say so in the guard's docstring if it does
not already.

- [x] **Step 4: Delete `_index_with` and consolidate the classify helpers**

`tests/test_split_imports.py:314`'s `_index_with` has zero references. Delete
it. In `tests/test_classify.py`, fold `_CountingIndex` (:558) into
`_RecordingIndex` (:57) — the count is derivable from the recorded calls — and
collapse the two probe-stubbing idioms into one. Every assertion stays.

- [x] **Step 5: Run and commit**

```bash
pixi run test -q && pixi run lint && pixi run python -m ruff format --check . && pixi run typecheck
pixi run pre-commit run --files src/veny/cli.py tests/test_split_imports.py \
    tests/test_classify.py tests/test_layering.py
git add -u
git commit -m "refactor: delete the write-only installed_imports chain and two dead test helpers"
```

---

## Task 9: The STANDING CHECK and the differential

**Goal:** prove the wiring, not just the units — the two techniques PROGRESS
records as the only ones that have caught a real regression in this program.

**Files:**
- Create: `scripts/differential_3d.py` (committed, unlike 3c's throwaway)
- Modify: whichever test files the STANDING CHECK proves are missing an assertion

**Acceptance Criteria:**
- [x] Every argument at every new call site in the table below has been substituted with an empty/None/default value, the suite run, and a **named** test observed to fail. Any argument with no named failure gets a test in this task.
- [x] The differential driver is committed, sets `PYTHONHASHSEED=0` **inside the script**, sets `sys.dont_write_bytecode = True` and purges `__pycache__` before the first import, takes the tree root as an argument (never `PYTHONPATH`), and prints `veny.cli.__file__` first
- [x] Three differentials come back empty: the classification state, the argv handed to `uv`, and the cache-search decision (which folder is chosen, and the `read_manifest`/`satisfies` call sequence)
- [x] The differential is proved able to fail at least four times by deliberate mutation, one per layer

> **[EXECUTION] The third differential cannot come back empty, and this plan
> should have said so.** Layer 3 compares the `read_manifest`/`satisfies`
> call sequence — which is exactly what **Task 7 deliberately changed**, with
> this same plan's blessing (Global Constraint 1 names it as one of two
> sanctioned exceptions). An empty layer-3 diff would have meant Task 7 did
> nothing. What layer 3 actually shows is **one sanctioned divergence** (one
> fewer read, one fewer satisfies) with the chosen folder and the flag
> write-back identical, which is the correct pass condition and is what was
> recorded. Layers 1 and 2 are byte-identical as written. The mutation count
> came in at **six**, not four. Lesson for 3e: a differential's pass
> condition is "the diff is exactly the sanctioned change", not "the diff is
> empty" — state the expected divergence in the plan, or the criterion
> contradicts the phase.
- [x] `install_into_venv`'s success predicate is covered this time: the driver's fake `subprocess.run` must return `returncode=0` for at least one case and the return value must be compared, closing the gap PROGRESS names

**Verify:** `pixi run python scripts/differential_3d.py /tmp/old-veny` and
`... /workspace` produce byte-identical output for all three layers

**Steps:**

- [x] **Step 1: The call sites to mutate (this is the complete list)**

| Call site | Arguments to mutate |
|---|---|
| `cli._probe_venv.is_importable` | `venv_python_for(venv_dir)`, `record` |
| `cli.setup_virtualenv` → `verify_and_repair_imports` | all seven keywords |
| `cli.setup_virtualenv` → `check_packages_in_venv` | `venv_python`, `uninstalled`, `source_names` |
| `cli.setup_virtualenv` → `record_venv_state` | all nine arguments |
| `cli.setup_virtualenv` → `build_folder_name` | `interpreter_tag`, `pip_names` |
| `cli.main` → `check_packages_in_venv` (`:532` branch) | `venv_python`, `uninstalled`, `source_names` |
| `cli.main` → `find_match_dir_in_cache` | `args` plus all eight keywords |
| `cli.main` → `rename_venv` | `venv_dir`, `new_name` |
| `cli.main` → `load_last_used_venv_python` | all four keywords |
| `cache_search.check_venv_dir` → `verify.check_packages_in_venv` | `venv_python`, `uninstalled`, `source_names` |
| `cache_search.find_match_dir_in_cache` → `check_venv_dir` (×4 branches) | `wanted`, `tag`, `manifest`, `source_names` |
| `cache_search.record_venv_state` → `manifest_for` | `versions`, `venv_tag`, `run_tag` |
| `verify.verify_and_repair_imports` → `repair_unsatisfied_import` | `venv_python`, `index`, `rawlog` |
| `verify.verify_and_repair_imports` → `write_requirements_file_with_extras` | `requirements_file`, the generator, `extra_requirements` |

Method, per argument: copy the file to the scratch directory, substitute the
value in place, run `pixi run test -q`, record which named test failed, restore
from the copy. **Never `git checkout --`.** Record the whole table's results in
the commit message; PROGRESS's 3c entry is the model.

- [x] **Step 2: Write the differential driver**

Follow the technique write-up in PROGRESS's Gotchas exactly. Materialize the
old tree with `git archive <base> src/veny | tar -x -C /tmp/old-veny` — no
worktree, no `git checkout`. Take the tree root as `sys.argv[1]` and insert it
with `sys.path.insert(0, ...)`. Set `PYTHONHASHSEED=0` inside the script (via
re-exec if it is not already set), `sys.dont_write_bytecode = True`, and delete
`__pycache__` under the tree before the first import — a same-size source edit
restored within the same integer second otherwise serves the pre-restore
behaviour, which PROGRESS reproduced from scratch.

Three capture layers:

1. **Classification state** — the nine-entry corpus 3c used, offline
   `AliasIndex`, throwaway `my_dir`, sorted serialization.
2. **uv argv** — captured at the `subprocess` boundary. The fake must return
   `returncode=0` for at least one case *and* the driver must record what
   `install_into_venv` returned, which 3c's driver discarded.
3. **Cache-search decision** — new to 3d. Build a fake `~/veny` with three
   manifest-bearing folders (one matching, one wrong tag, one missing a
   package) and record: the folder `find_match_dir_in_cache` returns, the
   ordered sequence of `read_manifest`/`satisfies` calls, and the final state
   of the four `args` flags.

- [x] **Step 3: Run it both ways and prove it can fail**

```bash
git archive dc1c3c4 src/veny | tar -x -C /tmp/old-veny
pixi run python scripts/differential_3d.py /tmp/old-veny > /tmp/old.txt
pixi run python scripts/differential_3d.py /workspace   > /tmp/new.txt
diff /tmp/old.txt /tmp/new.txt
```

Use the phase-3d **branch point** as `<base>`, not `dc1c3c4` — that was 3c's.
Then mutate the new tree four times (one per capture layer, plus one in the
`install_into_venv` predicate), confirm the diff appears each time, restore,
confirm it vanishes.

Note what layer 3 cannot see: the same bounds PROGRESS records for 3c still
apply (online alias resolution excluded, interpreter selection bypassed,
`requirements.txt` contents uncompared). Carry the unclosed parts forward as a
residual risk in Task 10 rather than implying they were covered.

- [x] **Step 4: Commit**

```bash
pixi run pre-commit run --files scripts/differential_3d.py
git add scripts/differential_3d.py && git add -u
git commit -m "test: pin every new call site's wiring and add the 3d differential"
```

---

## Task 10: Close the phase — gates, README, PROGRESS

**Goal:** measured gates, an accurate README, and a PROGRESS entry the next
session can resume from.

**Files:**
- Modify: `README.md` (project structure)
- Modify: `PROGRESS.md`
- Modify: `docs/superpowers/plans/2026-08-18-verify-cache-search-last-used.md`
  (annotate in place anything execution proved wrong)

**Acceptance Criteria:**
- [x] All five gates measured and recorded with their numbers: `pixi run test`, `pixi run lint`, `ruff format --check .`, `pixi run typecheck` (≤ 36, with the per-file breakdown), `pixi run smoke` (and whether the network was up)
- [x] A live run recorded: `pixi run veny --no-cache` on a script importing `yaml`, plus a **second** run without `--no-cache` proving the cache path this phase touched still matches the venv the first run built
- [x] `wc -l` for `cli.py` and every new module, recorded
- [x] README's project-structure block lists `verify.py`, `cache_search.py` and `last_used.py`
- [x] PROGRESS's Current work names 3e as the next action and states 3d's amendments (9, 10, 11), its declined items, and its residual risk
- [x] The ~eight stale `src/veny/cli.py` citations PROGRESS names are swept, each rewritten as a symbol name plus a commit-qualified line number
- [x] The plan's own task checkboxes and `.tasks.json` marked complete

**Verify:** `pixi run test -q && pixi run lint && pixi run python -m ruff format
--check . && pixi run typecheck && pixi run smoke`

**Steps:**

- [x] **Step 1: Measure the gates.** Record the actual numbers, not "green".
- [x] **Step 2: Live-run twice.** First `pixi run veny --no-cache` against a
  throwaway script importing `yaml`; then the same script with no flag, and
  confirm the log says `Using existing virtual environment: <the folder the
  first run built>`. The second run is what exercises Task 7's change end to
  end; a unit test cannot.
- [x] **Step 3: Update README's project structure.**
- [x] **Step 4: Update PROGRESS.** Current work gets 3d's ledger in the shape
  3c's has: commits, gates, line counts, what was and was not delivered.
  Deferred items gets amendments 9-11, the declined list, the residual risk
  from Task 9 Step 3, and anything the STANDING CHECK found that was fixed
  rather than pinned. Move nothing that is now done — delete it and say where
  it landed.
- [x] **Step 5: Sweep the stale citations.** PROGRESS names the starting
  points: `cli.py:1005` (dead — the symbol left in 3b), `cli.py:2606`,
  `:2860`, `:3304`, `:3323` (all beyond EOF), `cli.py:124` (actual `:63`),
  `:229` (actual `:168`), `:537`/`:552` (actual `:480`/`:495`). Every one of
  those will have moved *again* under this phase; re-measure each against this
  branch's HEAD and rewrite it as `symbol name @ <sha>:<line>`.
- [x] **Step 6: Annotate this plan in place** with anything execution proved
  wrong. 3b and 3c both did this and both found real errors in their own text;
  assume this plan has some too.
- [x] **Step 7: Commit, then request a whole-branch review** with
  `superpowers-extended-cc:requesting-code-review` before merging. Every phase
  so far has had a whole-branch review find something no per-task review did.

```bash
git add -u
git commit -m "docs: close phase 3d with measured gates and its ledger"
```

---

## Rollback

Every task is a single commit on `verify-cache-search-last-used`, branched off
`main`. To undo one task, `git revert <sha>`; to abandon the phase, delete the
branch — `main` is untouched until the merge, which is `--no-ff` like 3b's and
3c's. Do not rebase: the per-task commits are the record of what was measured
when, and PROGRESS cites their SHAs.
