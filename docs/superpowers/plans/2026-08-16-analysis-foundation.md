# Phase 3a: Analysis Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Extract the two leaf modules of the `analysis/` subpackage out of `src/veny/cli.py`, introduce the first frozen settings object with a real consumer, and establish the layering guard the rest of phase 3 will lean on.

**Architecture:** `analysis/literals.py` is a pure move — it reads no `Options` at all. `analysis/custom_modules.py` is the first module to receive a `Settings` object plus explicit parameters instead of the god object, so `settings.py` is born with a consumer rather than as speculative scaffolding. A new test enforces the design's one-way import direction, so later extractions cannot quietly reintroduce a cycle.

**Tech Stack:** Python 3.12-3.13, pytest, ruff, mypy, pixi.

**Global Constraints:**
- **Which imports veny discovers must not change.** `tests/test_import_discovery.py` pins it. Task 2 is the single exception, and it *widens* discovery — see that task.
- `pixi run lint` (`ruff check .`) must report zero and `pixi run python -m ruff format --check .` must report every file formatted.
- The whole-repo mypy count must not rise above **37**. Measure with `pixi run typecheck 2>&1 | tail -1`.
- Invoke tools through pixi's `python -m` form — bare binaries hit a shebang problem on macOS.
- `.git/hooks/pre-commit` is not installed. Run `pixi run pre-commit run --files <paths>` by hand; its `mypy` hook is `mypy .` with `pass_filenames: false` and always reports the pre-existing errors.
- Do not use `git stash` or `git checkout <sha>` in the working tree.
- Stage paths explicitly. A run leaves `.veny_custom_modules_*.pkl` and `logs/` behind; never `git add -A`. `.claude/` and `CLAUDE.md` are untracked and not to be added.
- **Do not touch anything phase 3b-3e owns:** no `analysis/imports.py`, `call_graph.py` or `scan.py` extraction, no `classify.py`, `environment.py`, `verify.py`, `cache_search.py`, `last_used.py` or `pipeline.py`, and no `--full` deletion. This plan moves two modules and nothing else.

**User decisions (already made):**
- "(i)" — one target-architecture spec, then a plan per phase. Phase 3 is a *sequence* of plans; this is the first.
- "delete" — `--full` is removed rather than fixed, but in a **later** phase 3 plan, not this one.

**Design doc:** `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md`, phase 3 and phase 4 sections.

---

## Why phase 3 is a sequence, not one plan

The design's target layout is thirteen modules carved out of a 4,143-line `cli.py`, each extraction carrying its own state decomposition and tests. That is far past what one plan can specify without placeholders. The design already says phase 3 and 4 are "sequenced module by module in their **plans**".

Proposed sequence, ordered leaf-first so every plan lands on already-extracted foundations:

| Plan | Modules | Approx. lines moved |
|---|---|---|
| **3a (this plan)** | `analysis/literals.py`, `analysis/custom_modules.py`, `settings.py` | ~430 |
| 3b | `analysis/imports.py`, `call_graph.py`, `scan.py` | ~1,090 |
| 3c | `classify.py`, `environment.py` | ~600 |
| 3d | `verify.py`, `cache_search.py`, `last_used.py` | ~1,100 |
| 3e | `pipeline.py`, `cli.py` slimming, `--full` deletion, final `Options` drain | ~450 |

Each produces working, tested software on its own. This plan covers **3a only**.

## Two design-doc inaccuracies found while planning

Recorded here rather than silently worked around:

1. **The design says the layering rule can be enforced by `tests/test_import_guard.py`.** It cannot — that file guards *emmykit availability* (missing, present, too old) and says nothing about import direction. Task 4 creates the layering guard as a new file.
2. **The design says `pathlibcutoff` dies with the persistence change in phase 4.** It has a second consumer the design did not account for: `dict_of_custom_modules` uses it to decide whether an old *pickle* holds string paths needing conversion. That consumer is unrelated to the options-JSON persistence, so the field outlives phase 4's change. Task 3 rehomes it as a module constant in `custom_modules.py`, where it is honestly a historical fact rather than a setting.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/veny/analysis/__init__.py` | Subpackage marker. | Create |
| `src/veny/analysis/literals.py` | Restricted literal evaluation over AST nodes; pathlib alias collection. | Create (~205 lines moved) |
| `src/veny/analysis/custom_modules.py` | Local custom-module discovery and its pickle cache. | Create (~230 lines moved) |
| `src/veny/settings.py` | `Settings`, the frozen run-invariants object. | Create |
| `src/veny/cli.py` | Everything else. | Modify — ~435 lines removed |
| `tests/test_literals.py` | Pins `safe_eval` and `collect_pathlib_aliases`. | Create |
| `tests/test_layering.py` | Enforces the one-way import direction. | Create |
| `PROGRESS.md` | Project ledger. | Modify |

Line numbers below are as of commit `8f247ed`. They shift as edits are applied, so **work bottom-up within each task** and locate code by symbol name.

---

### Task 1: Extract `analysis/literals.py`

**Goal:** The restricted-literal evaluator lives in its own module and has tests for the first time, with behaviour unchanged.

**Files:**
- Create: `src/veny/analysis/__init__.py`, `src/veny/analysis/literals.py`
- Create: `tests/test_literals.py`
- Modify: `src/veny/cli.py` — delete lines **679-883**, import from the new module

**Acceptance Criteria:**
- [x] `src/veny/analysis/literals.py` holds `PATHLIB_CONCRETE`, `PATHLIB_PURE`, `PATHLIB_ALL`, `collect_pathlib_aliases`, `is_pathlib_ctor`, `_safe_eval_node` and `safe_eval`, moved verbatim
- [x] `literals.py` imports nothing from `veny.cli`, `veny.alias_index`, `veny.venv_cache`, `veny.stdlib_index` or `veny.pypi_client` — only the standard library and `emmykit`
- [x] `cli.py`'s three consumers (`SysPathVisitor` twice, `_analyze_module` once) call it through the new module
- [x] `tests/test_literals.py` passes with 8 tests — **delivered as 7.** The eighth,
  `test_an_unaliased_pathlib_name_is_not_evaluated`, asserted behaviour the code
  does not have and was deferred to Task 2b as its red test; see that section.
- [x] All existing tests pass

**Verify:** `pixi run python -m pytest tests/test_literals.py -v` → 8 passed, then `pixi run test` → 276 passed
— **actual: 7 passed and 275 passed**, for the reason above.

**This is a pure move.** Do not fix, tidy, reformat or re-comment anything in the moved code. Task 2 makes the one behavioural change this plan contains, and keeping the move byte-identical is what lets a reviewer verify it by inspection.

**Test design.** Every expected value below was **measured against the current implementation** while writing this plan, not predicted. For each: behaviour, and the bug it catches.

1. `test_a_string_literal_evaluates_to_itself` → `safe_eval('"hello"') == "hello"`. Catches: any change that stops handling `ast.Constant`, which would make every `sys.path` string invisible.
2. `test_a_list_literal_evaluates_to_a_list` → `safe_eval('[1, 2]') == [1, 2]`. Catches: dropping the sequence branch, which appears in `sys.path` extension idioms.
3. `test_os_path_join_is_evaluated` → `safe_eval('os.path.join("a", "b")') == "a/b"`. Catches: narrowing the `os.path` allow-list, which silently drops a common `sys.path` idiom.
4. `test_os_getcwd_is_evaluated` → `safe_eval("os.getcwd()") == os.getcwd()`. Catches: removing the zero-arg `os.getcwd` branch. Compares against the live value rather than a hardcoded path, so it is machine-independent.
5. `test_pathlib_joinpath_is_evaluated` → `safe_eval('Path("a").joinpath("b", "c")', pathlib_aliases={"Path"}) == "a/b/c"`. Catches: breaking the `joinpath` branch or the alias plumbing.
6. `test_an_unaliased_pathlib_name_is_not_evaluated` → same expression with `pathlib_aliases=None` returns `None`. Catches: treating any name that looks like `Path` as pathlib regardless of what the module actually imported — which would mis-resolve a user's own class named `Path`.
7. `test_an_arbitrary_call_is_refused` → `safe_eval('open("x")') is None`. Catches: widening the evaluator into something that executes user code. This is the security-shaped test of the set: `safe_eval` is run over untrusted source.
8. `test_collect_pathlib_aliases_finds_a_renamed_import` → `collect_pathlib_aliases(ast.parse("from pathlib import Path as P")) == {"P"}`. Catches: matching on the literal name `Path` instead of the binding, which loses every renamed import.

No mocking: these are pure functions over hand-written expression strings.

**Steps:**

- [x] **Step 1: Create the subpackage**

Create `src/veny/analysis/__init__.py` containing only a docstring:

```python
"""AST analysis: what a script imports, and what it does with sys.path."""
```

- [x] **Step 2: Move the code**

Create `src/veny/analysis/literals.py`. Move `cli.py:679-883` into it **verbatim** — from `PATHLIB_CONCRETE = {...}` through the end of `safe_eval`, stopping before `class SysPathVisitor`. Add the module docstring and exactly the imports the moved code needs:

```python
"""Evaluate the restricted subset of expressions veny reads out of source.

A script's sys.path manipulation is only useful to veny if it can be read
without running the script, so this evaluates literals, a short allow-list of
os.path calls, and pathlib construction -- and refuses everything else.
"""

import ast
import logging
import os
from pathlib import Path
from typing import Any

import emmykit as ek
```

`ek` is needed by `safe_eval`'s debug log (`ek.return_method_name()`). Let ruff tell you if anything else is unused.

- [x] **Step 3: Point `cli.py` at the new module**

Delete `cli.py:679-883`. Add to `cli.py`'s imports, beside the existing `from . import ...` lines:

```python
from .analysis.literals import collect_pathlib_aliases, safe_eval
```

Import only those two names — they are the only ones `cli.py` still uses (`SysPathVisitor` at lines 901 and 918, `_analyze_module` at 1754). `is_pathlib_ctor`, `_safe_eval_node` and the `PATHLIB_*` constants are internal to the new module and must not be re-exported.

- [x] **Step 4: Write the tests**

Create `tests/test_literals.py`:

```python
"""Pin the restricted expression evaluator veny reads sys.path with."""

import ast
import os

from veny.analysis.literals import collect_pathlib_aliases, safe_eval


def test_a_string_literal_evaluates_to_itself() -> None:
    """Every sys.path string reaches veny through this branch."""
    assert safe_eval('"hello"') == "hello"


def test_a_list_literal_evaluates_to_a_list() -> None:
    """sys.path += [...] is a real idiom; the sequence branch serves it."""
    assert safe_eval("[1, 2]") == [1, 2]


def test_os_path_join_is_evaluated() -> None:
    """os.path.join is the pre-pathlib way to build a sys.path entry."""
    assert safe_eval('os.path.join("a", "b")') == "a/b"


def test_os_getcwd_is_evaluated() -> None:
    """Compared against the live value, so the test is machine-independent."""
    assert safe_eval("os.getcwd()") == os.getcwd()


def test_pathlib_joinpath_is_evaluated() -> None:
    """The alias set is what makes a local name count as pathlib."""
    result = safe_eval('Path("a").joinpath("b", "c")', pathlib_aliases={"Path"})
    assert result == "a/b/c"


def test_an_unaliased_pathlib_name_is_not_evaluated() -> None:
    """A user class named Path must not be mistaken for pathlib's."""
    assert safe_eval('Path("a").joinpath("b")') is None


def test_an_arbitrary_call_is_refused() -> None:
    """safe_eval runs over untrusted source; it must never execute a call."""
    assert safe_eval('open("x")') is None


def test_collect_pathlib_aliases_finds_a_renamed_import() -> None:
    """Matching the literal name 'Path' would lose every renamed import."""
    tree = ast.parse("from pathlib import Path as P\n")
    assert collect_pathlib_aliases(tree) == {"P"}
```

- [x] **Step 5: Run and prove one test can fail**

Run: `pixi run python -m pytest tests/test_literals.py -v` → expect `8 passed`.
Run: `pixi run test` → expect `276 passed` (268 + 8).

Then mutate: in `literals.py`'s `_safe_eval_node`, change the `os.path` allow-list `{"abspath", "join", "dirname", "realpath"}` to drop `"join"`. Confirm `test_os_path_join_is_evaluated` FAILS with `assert None == 'a/b'`. Restore and confirm green.

Mutate **in place** — pixi sets `PYTHONPATH = "src"` in `[activation.env]`, which overwrites an inherited value, so a side copy silently tests the real source and reports a false pass.

- [x] **Step 6: Commit**

```bash
pixi run pre-commit run --files src/veny/analysis/__init__.py src/veny/analysis/literals.py src/veny/cli.py tests/test_literals.py
git add src/veny/analysis/ src/veny/cli.py tests/test_literals.py
git commit -m "refactor: extract the literal evaluator into analysis/literals.py"
```

---

### Task 2: Fix the `/` operator, which the evaluator promises and does not deliver

**Goal:** `Path("a") / "b"` evaluates, as `safe_eval`'s own docstring has always claimed.

**Files:**
- Modify: `src/veny/analysis/literals.py` — `_safe_eval_node`'s call handling
- Modify: `tests/test_literals.py` — two new tests

**Acceptance Criteria:**
- [x] `safe_eval('Path("a") / "b"', pathlib_aliases={"Path"})` returns `"a/b"`
- [x] `safe_eval('Path("a")', pathlib_aliases={"Path"})` returns `"a"`
- [x] A `sys.path.insert(0, Path("/opt/libs") / "extra")` line is discovered by `SysPathVisitor`
- [x] All three new tests fail before the fix and pass after
- [x] All other tests pass unchanged

**Verify:** `pixi run test` → 279 passed

**The bug, measured while planning.** `safe_eval`'s docstring lists *"The `/` operator for joining pathlib Paths"* as supported, and `_safe_eval_node` opens with a dedicated `ast.BinOp` / `ast.Div` branch for it. But there is **no branch for a bare `Path(...)` constructor** — only for `Path(...).resolve()`, `.absolute()` and `.joinpath(...)`. So evaluating the left operand of `Path("a") / "b"` falls through to `raise ValueError(f"Unsupported call: ...")`, which propagates out of the `Div` branch and is swallowed by `safe_eval`'s `except`, yielding `None`.

Measured:

| Expression | Today | Should be |
|---|---|---|
| `Path("a").joinpath("b", "c")` | `"a/b/c"` | unchanged |
| `Path("a") / "b"` | `None` | `"a/b"` |
| `Path("a")` | `None` | `"a"` |

**The user-visible symptom**, reproduced through `SysPathVisitor`:

```
source:   sys.path.insert(0, Path("/opt/libs") / "extra")
          sys.path.append(Path("/opt/libs").joinpath("other"))
          sys.path.append("/opt/plain")
found:    {'/opt/plain', '/opt/libs/other'}      # the `/` entry is missing
```

veny therefore never scans `/opt/libs/extra` for custom modules, so an import satisfied by a module living there is misclassified — reported as a bad import, or sent to PyPI to be installed. `/` is the more idiomatic pathlib form than `.joinpath()`, so this is likely to be hit in practice.

**Why this is a separate task from Task 1.** Task 1's characterization tests record current behaviour, and current behaviour here is wrong. The design's own stated limit is that "characterization tests describe *current* behaviour, and current behaviour is occasionally wrong" — the defence being that such cases are named rather than silently encoded. This is that case, named. Keeping the move and the fix in separate commits keeps the move auditable.

**Test design.**

1. `test_the_slash_operator_joins_a_pathlib_path` — behaviour: `/` joining works as documented. Bug caught: exactly the current one; the test fails today with `assert None == 'a/b'`.
2. `test_sys_path_built_with_the_slash_operator_is_discovered` — behaviour: the symptom, at the level a user experiences it. Bug caught: a fix to `_safe_eval_node` that somehow does not reach `SysPathVisitor`. This test crosses the module boundary deliberately: the unit test alone would not have revealed that the bug had a user-visible consequence.

**Steps:**

- [x] **Step 1: Write both failing tests**

Append to `tests/test_literals.py`:

```python
def test_the_slash_operator_joins_a_pathlib_path() -> None:
    """safe_eval's docstring promises '/' joining; it must actually work."""
    assert safe_eval('Path("a") / "b"', pathlib_aliases={"Path"}) == "a/b"


def test_a_bare_pathlib_constructor_evaluates_to_its_argument() -> None:
    """Path("a") alone is the left operand of every '/' join."""
    assert safe_eval('Path("a")', pathlib_aliases={"Path"}) == "a"
```

Add to `tests/test_literals.py` (it needs `ast` and the visitor):

```python
def test_sys_path_built_with_the_slash_operator_is_discovered() -> None:
    """The '/' gap silently hid whole sys.path directories from veny."""
    from veny.cli import SysPathVisitor

    tree = ast.parse(
        'import sys\n'
        'from pathlib import Path\n'
        'sys.path.insert(0, Path("/opt/libs") / "extra")\n'
    )
    visitor = SysPathVisitor(collect_pathlib_aliases(tree))
    visitor.visit(tree)

    assert visitor.paths == {"/opt/libs/extra"}
```

- [x] **Step 2: Run them and confirm they fail**

Run: `pixi run python -m pytest tests/test_literals.py -v`
Expected: the three new tests FAIL — the first two with `assert None == ...`, the third with `assert set() == {'/opt/libs/extra'}`. The eight from Task 1 still pass.

- [x] **Step 3: Add the missing branch**

In `_safe_eval_node`, immediately **before** the `# unsupported call` line that raises, add a branch for a bare pathlib constructor:

```python
        # pathlib.Path(<literal>) with no method call on it. This is what the
        # "/" operator's operands are, and its absence is why "/" joining
        # silently returned None despite the docstring promising it.
        if is_pathlib_ctor(node.func, aliases, allow_pure=True) and len(node.args) == 1:
            arg = _safe_eval_node(node.args[0], pathlib_aliases=aliases)
            if isinstance(arg, str):
                return os.fspath(Path(arg))
```

It must come after the `resolve`/`absolute`/`joinpath` branches so those keep priority, and before the `raise`. `allow_pure=True` matches `joinpath`'s treatment: a `PurePath` is a legitimate way to build a path string.

- [x] **Step 4: Confirm the fix and that nothing else moved**

Run: `pixi run python -m pytest tests/test_literals.py -v` → expect `11 passed`.
Run: `pixi run test` → expect `279 passed`.

This is the one place in this plan where discovery *changes*: `tests/test_import_discovery.py` must still pass unchanged, because its fixtures use no `/` joining. Confirm that specifically:

Run: `pixi run python -m pytest tests/test_import_discovery.py -v` → expect `3 passed`.

- [x] **Step 5: Commit**

```bash
pixi run pre-commit run --files src/veny/analysis/literals.py tests/test_literals.py
git add src/veny/analysis/literals.py tests/test_literals.py
git commit -m "fix: evaluate a bare pathlib constructor so '/' joining works"
```

---

### Task 2b: Gate bare pathlib names on the alias set

**Added during execution, 2026-08-16, by ruling of the human partner.** Not part
of the plan as approved.

Task 1's eighth test — `test_an_unaliased_pathlib_name_is_not_evaluated`,
asserting `safe_eval('Path("a").joinpath("b")') is None` — turned out to assert
behaviour the code does not have. This plan claims above that every expected
value in Task 1 was measured against the current implementation; that one was
not. `is_pathlib_ctor` reads `if fn.id in allowed or fn.id in pathlib_aliases`,
and `allowed` always contains the literal names `Path`, `PosixPath` and
`WindowsPath`, so the alias set only ever *adds* names and can never reject one.
A script defining its own `class Path`, importing pathlib nowhere, has its
`Path(...)` calls evaluated as though they were pathlib's.

The implementer stopped rather than pick between "write the test as given" and
"do not fix the moved code", both of which Task 1 mandates. The ruling: fix the
bug now, in its own task, with the deferred test as its red test. Task 1
therefore ships 7 tests, not 8.

**Goal:** `pathlib_aliases` actually decides which bare names count as pathlib
constructors.

**Files:**
- Modify: `src/veny/analysis/literals.py` — `is_pathlib_ctor`
- Modify: `tests/test_literals.py` — one new test

**Acceptance Criteria:**
- [x] `safe_eval('Path("a").joinpath("b")')` with no aliases returns `None`
- [x] The same expression with `pathlib_aliases={"Path"}` still returns `"a/b"`
- [x] `safe_eval('pathlib.Path("a").joinpath("b")')` still returns `"a/b"` — the attribute form does not consult the alias set
- [x] Task 2's three `/`-operator tests still pass
- [x] `tests/test_import_discovery.py` passes unchanged

**Verify:** `pixi run test` → 279 passed

**The fix** — require both halves for a bare `ast.Name`:

```python
    # Case: Name (possibly aliased import) e.g., Path(...), P(...), PurePath(...)
    if isinstance(fn, ast.Name):
        if fn.id in pathlib_aliases and fn.id in allowed:
            return True
```

The `allowed` half still earns its place: it is what `allow_pure=False` uses to
reject a `PurePath` where only a concrete path will do, even when `PurePath` is
a genuine alias the script imported. The `ast.Attribute` branch below is left
alone — `pathlib.Path(...)` names the module explicitly and needs no alias set.

**This is the one *narrowing* of import discovery in plan 3a,** and it required
relaxing the global constraint above, which names Task 2 as the single
exception. It is safe because `_analyze_module` (`cli.py:1548`) is the only
production path in, and it builds the alias set from the module's own tree
immediately before constructing the visitor. Any script that genuinely writes
`from pathlib import Path` is unaffected; the only expressions that stop
evaluating are ones where a bare pathlib class name was never imported from
pathlib.

**Counts shift for the tasks around it,** with the plan's final total unchanged:
Task 1 ends at 275, Task 2 at 278, Task 2b at 279, Task 3 at 279, Task 4 at 281.

---

### Task 3: Introduce `settings.py` and extract `analysis/custom_modules.py`

**Goal:** The first module to be handed a `Settings` object and explicit parameters rather than the god object.

**Files:**
- Create: `src/veny/settings.py`, `src/veny/analysis/custom_modules.py`
- Modify: `src/veny/cli.py` — delete lines **3915-4143**, build a `Settings` in `main()`, update the call site

**Acceptance Criteria:**
- [x] `settings.py` defines a frozen `Settings` dataclass carrying only fields `custom_modules` actually reads
- [x] `custom_modules.py` takes `Settings` plus an explicit `use_cache: bool`; it does **not** import `Options` and never touches `options.args`
- [x] `pathlibcutoff` is a module constant in `custom_modules.py`, not a `Settings` field
- [x] `cli.py`'s single call site passes the flags-derived boolean, not the `Namespace`
- [x] `rg -n 'options\.' src/veny/analysis/` returns nothing
- [x] All tests pass

**Verify:** `pixi run test` → 279 passed

**What `custom_modules` actually reads today**, measured: `rawlog`, `search_above_this_dir`, `pathlibcutoff`, `my_name`, `cwd`, `stay_out_list`, and `options.args` for the `--rc` and `--no-cache` flags. That last one is the god-object symptom in miniature — a leaf module reaching into the CLI parser. Its real input is one boolean.

**Steps:**

- [x] **Step 1: Create `settings.py`**

```python
"""The invariants of one veny run, fixed once and never mutated."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Run invariants that no stage may change.

    Attributes:
        my_name:                 The installed command's name, "veny".
        my_dir:                  Where veny keeps its environments and caches.
        cwd:                     The directory veny was invoked from.
        stay_out_list:           Path fragments never searched for local modules.
        search_above_this_dir:   Whether to search above cwd for local modules.
        rawlog:                  Suppress veny's own commentary.
    """

    my_name: str
    my_dir: Path
    cwd: Path
    stay_out_list: tuple[str, ...]
    search_above_this_dir: bool
    rawlog: bool
```

`stay_out_list` is a `tuple`, not a `list`: the dataclass is frozen and a mutable member would make that a lie. `Options.stay_out_list` stays a list; the conversion happens where `Settings` is built.

- [x] **Step 2: Move the code**

Create `src/veny/analysis/custom_modules.py`. Move `cli.py:3915-4143` into it — `is_standard_path`, `only_search_here_filename_boolean`, `search_anywhere_filename_boolean`, `only_search_here_path_boolean`, `search_anywhere_path_boolean`, `stayed_out_dir` and `dict_of_custom_modules`. Add:

```python
"""Find the local modules a script imports that are not on PyPI."""
```

Add this module constant, replacing every `options.pathlibcutoff` reference:

```python
# Before this moment, veny pickled custom-module paths as strings; after it, as
# pathlib.Path. A pickle older than this needs its values converted on load.
# A historical fact about veny's own on-disk format, not a setting.
PATHLIB_CUTOFF = "20250810-224900"
```

- [x] **Step 3: Change the signatures**

`dict_of_custom_modules(options: Options)` becomes:

```python
def dict_of_custom_modules(settings: Settings, *, use_cache: bool) -> dict[str, Path]:
```

Replace `options.<field>` with `settings.<field>` throughout for the five `Settings` fields, and replace the cache guard:

```python
    if not getattr(options.args, "rc", False) and not getattr(
        options.args, "no_cache", False
    ):
```

with:

```python
    if use_cache:
```

Change the other moved functions the same way: `is_standard_path` and `stayed_out_dir` take `settings` instead of `options`. The four filename/path boolean helpers take no options today — leave their signatures alone.

- [x] **Step 4: Update `cli.py`**

Delete `cli.py:3915-4143`. Add the import:

```python
from .analysis.custom_modules import dict_of_custom_modules
from .settings import Settings
```

In `main()`, build the `Settings` once, just before the existing `options.custom_modules = dict_of_custom_modules(options)` call, and pass it:

```python
    settings = Settings(
        my_name=options.my_name,
        my_dir=options.my_dir,
        cwd=options.cwd,
        stay_out_list=tuple(options.stay_out_list),
        search_above_this_dir=options.search_above_this_dir,
        rawlog=options.rawlog,
    )
    options.custom_modules = dict_of_custom_modules(
        settings,
        use_cache=not getattr(options.args, "rc", False)
        and not getattr(options.args, "no_cache", False),
    )
```

`Options` keeps its fields for now — later plans in phase 3 drain it as their own modules need to. Do not remove them here; other code still reads them.

If any other site in `cli.py` calls `is_standard_path` or `stayed_out_dir`, update it to pass `settings`. Search first: `rg -n 'is_standard_path|stayed_out_dir' src/veny/cli.py`. If a caller has no `Settings` in scope, report it rather than threading one through half of `main()` — that is a sign the call belongs to a later plan's module.

- [x] **Step 5: Verify and test**

Run: `rg -n 'options\.' src/veny/analysis/` → expect no output.
Run: `pixi run test` → expect `279 passed`.
Run: `pixi run lint` → expect zero; delete only what ruff names as unused.

The suite has no direct test of `dict_of_custom_modules` — it is exercised through `tests/test_import_discovery.py`, which passes `custom_modules` in explicitly. So confirm the real path still works with a live run:

```bash
printf 'import yaml\nprint(yaml.safe_load("h: 8"))\n' > /tmp/veny-3a.py
pixi run veny --justprint /tmp/veny-3a.py
```

Expected: it resolves `yaml` to `PyYAML` and reports it, without crashing in custom-module discovery. Capture the output.

- [x] **Step 6: Commit**

```bash
pixi run pre-commit run --files src/veny/settings.py src/veny/analysis/custom_modules.py src/veny/cli.py
git add src/veny/settings.py src/veny/analysis/custom_modules.py src/veny/cli.py
git commit -m "refactor: hand custom-module discovery a Settings instead of Options"
```

---

### Task 4: Enforce the layering

**Goal:** A test fails if a later extraction points an arrow the wrong way.

**Files:**
- Create: `tests/test_layering.py`

**Acceptance Criteria:**
- [x] The test fails if `veny/analysis/*` imports `veny.cli`
- [x] The test fails if `veny/settings.py` imports anything from `veny`
- [x] The existing one-way rules among `alias_index`, `venv_cache`, `pypi_client` and `json_types` are covered by the same mechanism
- [x] It reads source with `ast`, not by importing — an import-based check would execute module bodies and could pass by accident
- [x] All tests pass

**Verify:** `pixi run python -m pytest tests/test_layering.py -v` → 2 passed, then `pixi run test` → 281 passed

**Why `ast` rather than importing:** importing a module runs it, so a cycle broken by a function-local import would look clean, and a module that imports `veny.cli` inside a function would slip through. Reading the source finds every `import` statement wherever it sits.

**Test design.** Behaviour: the design's dependency direction holds. Bug caught: any later extraction that reaches back up the stack — for instance `analysis/scan.py` importing `Options` from `cli` in phase 3b, which would make the subpackage untestable in isolation and reintroduce the coupling this whole phase exists to remove. Expected values come from the design doc's stated layering, not from what the code happens to do.

**Steps:**

- [x] **Step 1: Write the test**

Create `tests/test_layering.py`:

```python
"""Enforce the one-way import direction the re-architecture design fixes."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "veny"

# Module (relative to src/veny, without .py) -> names it may NOT import from veny.
FORBIDDEN = {
    "settings": {"cli", "alias_index", "venv_cache", "stdlib_index",
                 "pypi_client", "json_types", "analysis"},
    "analysis/literals": {"cli", "alias_index", "venv_cache", "stdlib_index",
                          "pypi_client", "json_types"},
    "analysis/custom_modules": {"cli", "alias_index", "venv_cache",
                                "pypi_client", "json_types"},
    "alias_index": {"cli", "venv_cache", "json_types", "analysis"},
    "venv_cache": {"cli", "alias_index", "pypi_client", "json_types", "analysis"},
    "pypi_client": {"cli", "alias_index", "venv_cache", "json_types", "analysis"},
    "stdlib_index": {"cli", "alias_index", "venv_cache", "pypi_client",
                     "json_types", "analysis"},
    "json_types": {"cli", "venv_cache", "pypi_client", "analysis"},
}


def veny_imports(path: Path) -> set[str]:
    """Return the veny module names a source file imports, at any nesting depth.

    Args:
        path: The source file to read.

    Returns:
        Top-level veny module names, e.g. {"cli", "analysis"}.
    """
    found: set[str] = set()
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # `from . import x` has module None; `from .analysis.literals import y`
            # has module "analysis.literals".
            if node.level and node.module:
                found.add(node.module.split(".")[0])
            elif node.level:
                found.update(alias.name for alias in node.names)
            elif node.module and node.module.startswith("veny."):
                found.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("veny."):
                    found.add(alias.name.split(".")[1])
    return found


def test_no_module_imports_above_its_layer() -> None:
    """A module reaching back up the stack cannot be tested in isolation."""
    violations = []
    for module, forbidden in FORBIDDEN.items():
        path = SRC / f"{module}.py"
        assert path.is_file(), f"{module}.py is missing; update FORBIDDEN"
        for imported in sorted(veny_imports(path) & forbidden):
            violations.append(f"{module} imports {imported}")
    assert violations == []


def test_the_guard_covers_every_module_it_should() -> None:
    """A new module with no FORBIDDEN entry would be silently unguarded."""
    on_disk = {
        str(p.relative_to(SRC).with_suffix("")).replace("\\", "/")
        for p in SRC.rglob("*.py")
        if p.name not in {"__init__.py", "__main__.py"}
    }
    unguarded = on_disk - set(FORBIDDEN) - {"cli"}
    assert unguarded == set(), f"add these to FORBIDDEN: {sorted(unguarded)}"
```

`cli` is exempt from the second test because it sits at the top of the stack and may import anything.

- [x] **Step 2: Run and prove both can fail**

Run: `pixi run python -m pytest tests/test_layering.py -v` → expect `2 passed`.

Then prove the first bites: add `from .. import cli  # noqa: F401` to the top of `src/veny/analysis/literals.py` and confirm `test_no_module_imports_above_its_layer` FAILS reporting `analysis/literals imports cli`. Remove it and confirm green.

Then prove the second bites: create an empty `src/veny/scratch.py` and confirm `test_the_guard_covers_every_module_it_should` FAILS naming `scratch`. Delete the file and confirm green.

Both mutations go in the working tree, not a side copy.

- [x] **Step 3: Commit**

```bash
pixi run pre-commit run --files tests/test_layering.py
git add tests/test_layering.py
git commit -m "test: enforce the design's one-way import direction"
```

---

### Task 5: Run the gates and update PROGRESS

**Goal:** Every gate confirmed, and `PROGRESS.md` points at plan 3b.

**Files:**
- Modify: `PROGRESS.md`

**Acceptance Criteria:**
- [x] `pixi run test` passes with 281 tests
- [x] `ruff check .` zero; `ruff format --check .` every file formatted
- [x] `pixi run typecheck 2>&1 | tail -1` at or below 37
- [x] `pixi run smoke` green, or the note says it was skipped for lack of network
- [x] A live `pixi run veny --no-cache` run still builds and runs
- [x] `PROGRESS.md` **Current work** names plan 3b as the next action, with the measured `wc -l src/veny/cli.py`, and records the 3a-3e sequence
- [x] A Gotchas entry records the `/`-operator bug Task 2 fixed and its symptom
- [x] The two design-doc inaccuracies noted at the top of this plan are recorded

**Verify:** `pixi run test && pixi run lint && pixi run smoke` → all green

**Steps:**

- [x] **Step 1: Run every gate**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run smoke
pixi run typecheck 2>&1 | tail -1
wc -l src/veny/cli.py
```

Then the live check, because the unit suite does not exercise custom-module discovery through `main()`:

```bash
printf 'import yaml\nprint(yaml.safe_load("i: 9"))\n' > /tmp/veny-3a-final.py
pixi run veny --no-cache /tmp/veny-3a-final.py
```

Expected: `{'i': 9}`.

- [x] **Step 2: Update PROGRESS.md**

Replace the **Current work** `**Next action:**` block with a plan 3b pointer carrying the measured line count, and add the 3a-3e sequence table from the top of this plan so the next session knows phase 3 is a sequence rather than one plan.

Add a Gotchas entry:

```markdown
- **`safe_eval` silently dropped every `sys.path` entry built with pathlib's
  `/` operator** until 2026-08-16. Its docstring promised the operator and
  `_safe_eval_node` had a `BinOp`/`Div` branch for it, but no branch existed
  for a bare `Path(...)` constructor, so evaluating the left operand raised
  `ValueError` and `safe_eval` swallowed it to `None`. `Path("x").joinpath("y")`
  worked throughout, which is what made the gap hard to notice. The symptom was
  invisible: veny simply never scanned that directory for custom modules, and
  imports satisfied there were reported bad or sent to PyPI. Found by probing
  the evaluator while planning its extraction, not by any test.
```

Add the two design-doc inaccuracies (the layering guard is not `test_import_guard.py`; `pathlibcutoff` outlives phase 4) to Deferred items or Gotchas as appropriate.

- [x] **Step 3: Commit**

```bash
pixi run pre-commit run --files PROGRESS.md
git add PROGRESS.md
git commit -m "docs: record plan 3a and point at the analysis extraction"
```

---

## Rollback

Each task is one commit on branch `analysis-foundation`, off `8f247ed`. To undo the plan, reset the branch. Do not use `git stash` — a pre-commit formatter hook rewriting files mid-stash has blocked the pop in this repository before.
