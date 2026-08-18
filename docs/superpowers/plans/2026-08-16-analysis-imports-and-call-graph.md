# Phase 3b: Imports, Call Graph and Scan — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the three remaining `analysis/` modules — the AST import collector, the function call graph, and the script scanner — out of `src/veny/cli.py`, and give the call-graph half its first tests.

**Architecture:** This is the largest extraction in phase 3: ~1,100 lines with almost no test coverage behind it. So the plan inverts 3a's order — **characterization tests come first, before anything moves.** The layering guard forbids `analysis/` importing `cli`, which forces the scan's shared mutable state out of `Options` and into an `ImportScan` dataclass; `cli.py` builds one, hands it in, and copies the results back, so every downstream reader of `options.*` is untouched. Stdlib membership arrives as an injected `is_stdlib` predicate rather than a `StdlibIndex`, keeping `analysis/` free of index types.

**Tech Stack:** Python 3.12-3.13, pytest, ruff, mypy, pixi.

**Global Constraints:**
- **Behaviour must not change.** Which imports veny discovers, and which it classifies as stdlib, must be identical before and after every task in this plan. `tests/test_import_discovery.py` and `tests/test_split_imports.py` pin part of it and must pass unchanged throughout. **There is no sanctioned exception in this plan** — unlike 3a, which had two.

  > **Correction (whole-branch review, 2026-08-17):** read literally, this
  > collides with Task 4's own `process_import` signature change (`options`
  > replaced by `scan` plus an injected `is_stdlib`), since
  > `tests/test_split_imports.py` calls `process_import` directly. What
  > "pass unchanged" actually protects is `test_split_imports.py`'s
  > *assertions* — the imports it pins as discovered and the stdlib
  > classifications it pins — not its literal source text. Updating a test's
  > call site to match a moved function's new signature is mechanical and
  > within scope; changing what the test asserts is not. `process_import`'s
  > call site at `tests/test_split_imports.py:94` was updated exactly this
  > way (`process_import(scan, "tkinter", script, is_stdlib=...)`), and the
  > test's assertions are unchanged.
- The suite starts at **283 passing** and must never go down. Each task states its expected count.
- `pixi run lint` (`ruff check .`) must report zero and `pixi run python -m ruff format --check .` must report every file formatted.
- The whole-repo mypy count must not rise above **37**. Measure with `pixi run typecheck 2>&1 | tail -1`. It cannot reach zero — 37 is a ceiling to stay under, not a gate to satisfy, and the pre-commit `mypy` hook is `mypy .` with `pass_filenames: false`, so it always reports the pre-existing errors.
- `tests/test_layering.py` must stay green at every commit. Any new module under `src/veny/` needs a `FORBIDDEN` entry in the same commit that creates it, or `test_the_guard_covers_every_module_it_should` fails.
- `rg -n 'options\.' src/veny/analysis/` must return nothing when the plan is done, and `analysis/` must import nothing from `veny.cli`.
- Invoke tools through pixi's `python -m` form — bare binaries hit a shebang problem on macOS.
- `.git/hooks/pre-commit` is not installed. Run `pixi run pre-commit run --files <paths>` by hand.
- Do not use `git stash` or `git checkout <sha>` in the working tree. Use `git show <sha>:<path>` to read an old version.
- Mutate the working tree in place for mutation testing. `pixi.toml`'s `[activation.env]` sets `PYTHONPATH = "src"`, which *overwrites* an inherited value, so a side copy silently tests `/workspace/src` and reports a false pass.
- Stage paths explicitly. A run leaves `.veny_custom_modules_*.pkl` and `logs/` behind; never `git add -A`. `.claude/` and `CLAUDE.md` are untracked and not to be added.
- **Do not touch anything phase 3c-3e owns:** no `classify.py`, `environment.py`, `verify.py`, `cache_search.py`, `last_used.py` or `pipeline.py`, no `split_imports` extraction, and no `--full` deletion.

**User decisions (already made):**
- "Inject a predicate" — `analysis/` takes `is_stdlib: Callable[[str], bool]`, not a `StdlibIndex`. Decided 2026-08-16. The design doc's "takes neither `AliasIndex` nor `StdlibIndex`" then holds literally, behaviour is bit-identical, and it matches the injection pattern the design already chose for `verify.py`.
- "1" (merge locally) — phase 3a was merged to `main` at `3215df5` before this plan begins.
- Carried from 3a: "(i)" — one target-architecture spec, then a plan per phase; phase 3 is a *sequence* of plans, and this is the second. "delete" — `--full` is removed in a later phase 3 plan, not this one.

**Design doc:** `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md`, phase 3 section.

---

## Starting state (this plan was written in a different session — assume nothing)

- **Branch:** `analysis-imports-call-graph`, already created off `main` @ `3215df5`. It has exactly one commit, `e4f79ea`, which is this plan and its `.tasks.json`. **No task in this plan has been implemented.** Do not create a new branch.
- **Suite:** `pixi run test` reports **283 passed** at `e4f79ea`. Confirm that before Task 1; if it differs, stop and report rather than adjusting the plan's counts.
- **Line counts at `e4f79ea`:** `cli.py` 3,707; `analysis/literals.py` 229; `analysis/custom_modules.py` 274; `settings.py` 23. Every `cli.py` line number in this plan is as of that commit.
- **Phase 3a is merged** (`3215df5`). It created `src/veny/analysis/` with `literals.py` and `custom_modules.py`, `src/veny/settings.py` with a frozen five-field `Settings`, and `tests/test_layering.py`. Read `PROGRESS.md` first — its Gotchas section carries traps this plan does not repeat.
- **`pixi run typecheck` reports 37 errors and cannot reach zero.** It is a ceiling, not a gate. The pre-commit `mypy` hook is `mypy .` with `pass_filenames: false`, so it always reports them; that is expected, not a failure of your change.
- **`.git/hooks/pre-commit` is not installed**, so `git commit` runs no hooks. Run `pixi run pre-commit run --files <paths>` by hand before each commit.
- **The measured values in Task 1 were obtained by executing the code at `3215df5`.** Task 2's were deliberately *not* measured — see that task. Everywhere this plan states a value as measured, it was; everywhere it asks you to measure, do not substitute a value from this plan's prose.

---

## Three things this plan settles that the design did not

Recorded here rather than silently worked around. All three were found by measuring the tree at `3215df5`, not by reading.

1. **The design's `ImportScan` omits `seen_stdlib_imports`.** It is a genuine scan output, written at three sites, with a live consumer: `warn_about_system_packages` (`cli.py:2365-2379`), which produces the "needs the python3-tk system package" warning and is tested at `tests/test_split_imports.py:54-71`. Omitting it means that warning silently stops firing. **This plan's `ImportScan` carries it.**

2. **The design says `analysis/*` "takes neither `AliasIndex` nor `StdlibIndex`", but the scan reads `options.stdlib` at three sites** (`cli.py:735`, `1592`, `1759`) to skip stdlib names before any filesystem probe. Settled by the user decision above: inject `is_stdlib: Callable[[str], bool]`.

   A bare `frozenset[str]` was considered and rejected. `StdlibIndex.__contains__` (`stdlib_index.py:45`) is not plain set membership — it is `import_name.partition(".")[0] in self.names` plus a non-string/empty guard. Passing a frozenset would quietly change classification for any dotted or empty name, resting on an unverified claim that every name reaching those sites is pre-normalized.

3. **The design's "Pure AST in, names out" is not literally true today, and this plan does not make it true.** `ImportFunctionCollector._register_constant_path_for_module` (`cli.py:1287-1299`) calls `ek.safe_exists`/`ek.safe_is_dir` during the AST walk, and `process_import` probes the filesystem throughout. Making the walk pure is a behaviour change and belongs to no task here. The plan records it; it does not fix it.

## `get_all_imports` and `stayed_out_dir` stay in `cli.py`

Both look like they belong to `scan.py`, and both are deliberately left behind:

- The design's `scan.py` budget (~300) matches `find_imports_in_script + _analyze_module + _enqueue_top_level_imports` (203+62+29 = 294) **without** them.
- `get_all_imports` has no analysis logic of its own — it is a directory-walk dispatcher, architecturally the same kind of driver as `list_packages`, which the design assigns to `pipeline.py` in phase 3e.
- `stayed_out_dir` serves only `get_all_imports`, and reads `stay_out_list`, which `Settings` already carries. When 3e gives `get_all_imports` a home, `stayed_out_dir` should move with it and take `settings` — the next `Options` shedding, already half paid for by 3a.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `tests/test_call_graph.py` | Characterizes the call graph before it moves. | Create (Task 1) |
| `tests/test_import_collector.py` | Characterizes `ImportFunctionCollector`'s resolution paths before they move. | Create (Task 2) |
| `src/veny/analysis/call_graph.py` | `FunctionInfo`, `ModuleInfo`, `build_call_graph`, `collect_used_imports`. | Create (~180 lines moved) |
| `src/veny/analysis/scan_state.py` | `ImportScan`, the mutable state one scan accumulates. | Create (Task 4) |
| `src/veny/analysis/imports.py` | `SysPathVisitor`, `process_import`, `ImportFunctionCollector`. | Create (~690 lines moved) |
| `src/veny/analysis/scan.py` | `_analyze_module`, `_enqueue_top_level_imports`, `find_imports_in_script`. | Create (~320 lines moved) |
| `src/veny/cli.py` | Everything else; builds the `ImportScan` and copies results back. | Modify — ~1,190 lines removed |
| `tests/test_layering.py` | `FORBIDDEN` gains four entries. | Modify |
| `tests/test_literals.py` | Loses the misplaced `SysPathVisitor` test. | Modify (Task 5) |
| `PROGRESS.md` | Project ledger. | Modify (Task 7) |

Line numbers below are as of commit `3215df5` on `main`. They shift as edits are applied, so **work bottom-up within each task** and locate code by symbol name.

---

### Task 1: Characterize the call graph before moving it

**Goal:** The call-graph half of the pipeline has tests for the first time, describing exactly what it does today.

**Files:**
- Create: `tests/test_call_graph.py`

**Acceptance Criteria:**
- [ ] Six tests pass, covering: module/function collection, in-function imports, the `Class.method` naming, the `::` graph-key format, base-class method fallback, and recursion-guarded traversal
- [ ] Every expected value is obtained by running the code, not predicted
- [ ] No source file is modified in this task
- [ ] Deleting `build_call_graph`'s base-class fallback (`cli.py:1419-1433`) makes a test fail

**Verify:** `pixi run python -m pytest tests/test_call_graph.py -v` → 6 passed, then `pixi run test` → 289 passed

**Why tests come before the move.** `build_call_graph`, `collect_used_imports`, `_analyze_module`, `split_function_name`, `_resolve`, `FunctionInfo` and `ModuleInfo` have **zero** tests — `rg` over `tests/` returns no hit for any of those names. They are also the subtlest code in the neighbourhood. Moving them first would mean a refactor with no net underneath it, in the part of the codebase most likely to break quietly. 3a moved first and tested after; that was safe because `literals.py` was a byte-identical move of pure functions. This is not that.

**A trap that will cost you an hour if you hit it blind.** `ImportFunctionCollector` populates its **own** `self.base_classes`, not the `ModuleInfo`'s. Only `_analyze_module` (`cli.py:1575`, `module_info.base_classes = collector.base_classes`) copies it across. So a test that constructs the collector directly and reads `module_info.base_classes` gets `{}`, the base-class fallback never fires, and inherited methods look broken when they are not. **Every test below goes through `_analyze_module`, against a real file on `tmp_path`.** Measured both ways while writing this plan: direct collector → `base_classes == {}` and `collect_used_imports` returns `set()`; through `_analyze_module` → `base_classes == {'Base': [], 'Child': ['Base']}` and `collect_used_imports` returns `{'base64'}`.

**Test design.** Every expected value below was obtained by executing the code at `3215df5` through `_analyze_module`. For each: the behaviour, and the bug it catches.

1. `test_functions_are_collected_with_their_class_prefix` → `sorted(mi.functions) == ["Base.helper", "Child.run", "top"]`. Catches: losing the `Class.method` naming, which would make every method unreachable in the graph.
2. `test_a_function_records_the_imports_inside_it` → `Base.helper`'s `imports_in_function == {"base64"}`. Catches: dropping in-function import recording, which is the whole reason the call graph exists.
3. `test_a_graph_key_is_the_file_path_and_the_function` → the graph's keys start with the module's absolute path followed by `::`. Catches: reverting to the legacy dotted key format, which `split_function_name` still parses but which collides with dotted module names.
4. `test_an_inherited_method_call_resolves_to_the_base_class` → `Child.run`'s edge set is `{f"{key}::Base.helper"}`, not `Child.helper`. Catches: the base-class fallback silently not firing — which is exactly what the direct-collector trap above looks like.
5. `test_an_import_inside_an_inherited_method_is_reachable` → `collect_used_imports(key, "top", graph, mods) == {"base64"}`. Catches: a break anywhere along `top` → `Child.run` → `Base.helper`. This is the test that matters most: if it fails, veny stops installing a package the script needs and the failure surfaces at the user's runtime, which PROGRESS.md's cross-cutting decisions name as the worse direction to be wrong in.
6. `test_recursion_does_not_hang_the_traversal` → two mutually recursive functions return their union without hanging. Catches: dropping the `visited` guard in `collect_used_imports`.

No mocking: these run the real functions over real files.

**Steps:**

- [ ] **Step 1: Write the tests**

Create `tests/test_call_graph.py`:

```python
"""Characterize the call graph before phase 3b moves it out of cli.py.

Everything here goes through _analyze_module rather than constructing
ImportFunctionCollector directly: the collector fills its own base_classes,
and only _analyze_module copies them onto the ModuleInfo. A test that skips
that step sees an empty base-class map and wrongly concludes inheritance is
broken.
"""

from pathlib import Path

from veny.cli import Options, _analyze_module, build_call_graph, collect_used_imports

INHERITANCE_SOURCE = """\
class Base:
    def helper(self):
        import base64
        return base64


class Child(Base):
    def run(self):
        return self.helper()


def top():
    return Child().run()
"""


def _analyze(source: str, tmp_path: Path) -> tuple[str, dict]:
    """Write source to a file and analyze it the way find_imports_in_script does.

    Args:
        source: Python source text to analyze.
        tmp_path: pytest's per-test temporary directory.

    Returns:
        The module key _analyze_module assigned, and the modules_info dict.
    """
    module_path = tmp_path / "mod.py"
    module_path.write_text(source)
    options = Options()
    options.rawlog = True
    modules_info: dict = {}
    result = _analyze_module(options, module_path, modules_info, False)
    assert result is not None, "_analyze_module refused the fixture"
    return result[0], modules_info


def test_functions_are_collected_with_their_class_prefix(tmp_path: Path) -> None:
    """Losing the Class.method prefix makes every method unreachable."""
    key, modules_info = _analyze(INHERITANCE_SOURCE, tmp_path)
    assert sorted(modules_info[key].functions) == ["Base.helper", "Child.run", "top"]


def test_a_function_records_the_imports_inside_it(tmp_path: Path) -> None:
    """In-function imports are the entire reason the call graph exists."""
    key, modules_info = _analyze(INHERITANCE_SOURCE, tmp_path)
    helper = modules_info[key].functions["Base.helper"]
    assert helper.imports_in_function == {"base64"}


def test_a_graph_key_is_the_file_path_and_the_function(tmp_path: Path) -> None:
    """The '::' key format is what keeps a dotted module name unambiguous."""
    key, modules_info = _analyze(INHERITANCE_SOURCE, tmp_path)
    graph = build_call_graph(modules_info)
    assert f"{key}::top" in graph


def test_an_inherited_method_call_resolves_to_the_base_class(tmp_path: Path) -> None:
    """self.helper() on a subclass must find Base.helper, not Child.helper."""
    key, modules_info = _analyze(INHERITANCE_SOURCE, tmp_path)
    graph = build_call_graph(modules_info)
    assert graph[f"{key}::Child.run"] == {f"{key}::Base.helper"}


def test_an_import_inside_an_inherited_method_is_reachable(tmp_path: Path) -> None:
    """A missed import here means veny skips an install the script needs."""
    key, modules_info = _analyze(INHERITANCE_SOURCE, tmp_path)
    graph = build_call_graph(modules_info)
    assert collect_used_imports(key, "top", graph, modules_info) == {"base64"}


def test_recursion_does_not_hang_the_traversal(tmp_path: Path) -> None:
    """Without the visited guard, mutual recursion never terminates."""
    source = """\
def ping():
    import base64
    return pong()


def pong():
    import csv
    return ping()
"""
    key, modules_info = _analyze(source, tmp_path)
    graph = build_call_graph(modules_info)
    assert collect_used_imports(key, "ping", graph, modules_info) == {"base64", "csv"}
```

- [ ] **Step 2: Run them**

Run: `pixi run python -m pytest tests/test_call_graph.py -v` → expect `6 passed`.
Run: `pixi run test` → expect `289 passed` (283 + 6).

If any test fails, **do not adjust the test to match** — you have found a discrepancy between this plan's measurements and the tree. Stop and report it. That has happened before on this project and the plan was wrong, not the code.

- [ ] **Step 3: Prove the fallback test bites**

Mutate in place: in `cli.py`'s `build_call_graph`, delete the base-class fallback branch (`if called_name not in mi.functions and cls in mi.base_classes:` and its body, `cli.py:1419-1433`). Confirm `test_an_inherited_method_call_resolves_to_the_base_class` and `test_an_import_inside_an_inherited_method_is_reachable` both FAIL. Restore with `git checkout -- src/veny/cli.py` and confirm green.

Record the real failure text.

- [ ] **Step 4: Commit**

```bash
pixi run pre-commit run --files tests/test_call_graph.py
git add tests/test_call_graph.py
git commit -m "test: characterize the call graph before extracting it"
```

---

### Task 2: Characterize the import collector's resolution paths

**Goal:** The 518-line `ImportFunctionCollector` — the single largest and least-tested symbol in this extraction — has direct tests of the paths a refactor is most likely to break.

**Files:**
- Create: `tests/test_import_collector.py`

**Acceptance Criteria:**
- [ ] Five tests pass, covering: dotted-name normalization, `from X import Y` handling, top-level vs in-function import separation, dynamic `importlib.import_module`, and alias recording
- [ ] Every expected value is obtained by running the code, not predicted
- [ ] No source file is modified in this task
- [ ] All five tests go through `_analyze_module`, for the reason given in Task 1

**Verify:** `pixi run python -m pytest tests/test_import_collector.py -v` → 5 passed, then `pixi run test` → 294 passed

**Why these five.** The collector handles `self.`/`cls.`/`super()` call resolution, dynamic `__import__`, `importlib.import_module`, `spec_from_file_location`, `SourceFileLoader(...).load_module()`, and attribute-type inference — none of it directly tested. Five tests will not cover all of that, and this plan does not pretend otherwise: they cover the paths whose breakage would change *which imports veny finds*, which is this plan's binding constraint. The exotic loader paths are recorded as a coverage gap in Task 7 rather than papered over.

**Measure before you write.** Unlike Task 1, this plan does **not** hand you the expected values for all five. Task 1's were measured; these must be measured by you, the same way, before the test is written:

Save this as `/tmp/probe.py` and run it with `pixi run python /tmp/probe.py`, editing `SRC` for each fixture. It is written as a file rather than a `-c` one-liner because the fixture source contains quotes and newlines that do not survive shell quoting:

```python
import pathlib
import tempfile

from veny.cli import Options, _analyze_module

SRC = """\
import xml.etree.ElementTree
from json import loads


def go():
    import csv
    return csv
"""

directory = pathlib.Path(tempfile.mkdtemp())
module_path = directory / "mod.py"
module_path.write_text(SRC)

options = Options()
options.rawlog = True
modules_info: dict = {}
result = _analyze_module(options, module_path, modules_info, False)
assert result is not None, "_analyze_module refused the fixture"
key = result[0]
info = modules_info[key]

print("top_level_imports:", sorted(info.top_level_imports))
print("functions:", {k: sorted(f.imports_in_function) for k, f in info.functions.items()})
print("aliases:", info.alias_to_key)
print("class_names:", info.class_names)
print("base_classes:", info.base_classes)
```

`ModuleInfo`'s attribute names are worth confirming against `cli.py:841-852` before you rely on them — this plan names `top_level_imports`, `functions`, `alias_to_key`, `class_names` and `base_classes`, and if the probe raises `AttributeError` on any of them, read the class and report the real name rather than guessing.

> **Correction (whole-branch review, 2026-08-17):** `alias_to_key` and
> `class_names` are not `ModuleInfo`'s real attribute names — this probe
> would have raised `AttributeError` on both, exactly the situation the
> paragraph above asks the implementer to catch. The real fields, as
> declared in `src/veny/analysis/call_graph.py`'s `ModuleInfo.__init__`,
> are `aliases` (`self.aliases: dict[str, str] = {}`) and `classes`
> (`self.classes: set[str] = set()`).

Put the values you actually observe into the assertions, and paste that observed output into your report. If an observed value contradicts what a test name below implies, **report it before writing the test** — that is precisely the situation that produced 3a's Task 2b.

**Test design.** Behaviour and the bug caught, for each:

1. `test_a_dotted_import_is_normalized_to_its_top_level_name` — fixture imports `xml.etree.ElementTree`; assert the recorded name is `xml`. Catches: losing the normalize-before-classify order in `visit_Import` (`cli.py:868`), which would make every dotted stdlib name miss the stdlib check and get sent to PyPI.
2. `test_from_import_records_the_module_not_the_symbol` — fixture does `from json import loads`; assert `json` is recorded, not `loads`. Catches: recording the imported symbol as a package name, which would try to install a function.
3. `test_a_top_level_import_is_not_recorded_as_an_in_function_import` — fixture has one of each; assert they land in different collections. Catches: collapsing the two, which would make the call-graph reachability filter meaningless.
4. `test_a_dynamic_importlib_call_is_recorded` — fixture calls `importlib.import_module("csv")`; assert `csv` is found. Catches: dropping the dynamic-import branch, a documented feature of the collector.
5. `test_an_aliased_import_records_the_real_module_name` — fixture does `import numpy as np`; assert `numpy` is recorded. Catches: recording the local binding as the package name.

**Steps:**

- [ ] **Step 1: Measure each fixture**

Run the probe above once per fixture. Capture the output verbatim — it goes in your report and in the assertions.

- [ ] **Step 2: Write the tests**

Create `tests/test_import_collector.py`, following the structure of `tests/test_call_graph.py` from Task 1 — same `_analyze` helper (copy it; the two files are independent and a shared conftest fixture is not worth the coupling for two callers), same docstring discipline: every test's docstring names the bug it catches, not what the code does.

Use the values you measured in Step 1. Do not carry a value over from this plan's prose.

- [ ] **Step 3: Run them**

Run: `pixi run python -m pytest tests/test_import_collector.py -v` → expect `5 passed`.
Run: `pixi run test` → expect `294 passed` (289 + 5).

- [ ] **Step 4: Prove one bites**

Mutate in place: in `cli.py`'s `visit_Import`, change `top_level_package = full_name.split(".")[0]` to `top_level_package = full_name`. Confirm `test_a_dotted_import_is_normalized_to_its_top_level_name` FAILS. Restore with `git checkout -- src/veny/cli.py` and confirm green. Record the real failure text.

- [ ] **Step 5: Commit**

```bash
pixi run pre-commit run --files tests/test_import_collector.py
git add tests/test_import_collector.py
git commit -m "test: characterize the import collector before extracting it"
```

---

### Task 3: Extract `analysis/call_graph.py`

**Goal:** The call-graph types and traversal live in their own module, behaviour unchanged, with Task 1's tests proving it.

**Files:**
- Create: `src/veny/analysis/call_graph.py`
- Modify: `src/veny/cli.py` — delete `FunctionInfo` (830-839), `ModuleInfo` (841-852), `_SEP` (1375), `split_function_name` (1378-1391), `_resolve` (1394-1396), `build_call_graph` (1399-1450), `collect_used_imports` (1453-1513); import from the new module
- Modify: `tests/test_layering.py` — add the `FORBIDDEN` entry
- Modify: `tests/test_call_graph.py` — update import paths

**Acceptance Criteria:**
- [ ] `call_graph.py` holds all seven symbols, moved **verbatim**
- [ ] `call_graph.py` imports only the standard library — nothing from `veny` at all
- [ ] `tests/test_layering.py`'s `FORBIDDEN` gains `"analysis/call_graph"`, forbidding every other `veny` module, and the layering tests pass
- [ ] `tests/test_call_graph.py` imports `build_call_graph` and `collect_used_imports` from `veny.analysis.call_graph`; `_analyze_module` and `Options` still come from `veny.cli`
- [ ] All tests pass

**Verify:** `pixi run test` → 294 passed

**This is a pure move.** Do not fix, tidy, reformat, rename or re-comment anything in the moved code. `FunctionInfo.ast_node` is dealt with in Task 6, separately, so that the move stays auditable by inspection. If you notice anything else wrong, report it as a concern rather than fixing it.

These seven symbols read no `Options` at all — they take plain parameters and return plain data. That is why this module goes first: it is the only one of the three that needs no signature change.

**Steps:**

- [ ] **Step 1: Move the code**

Create `src/veny/analysis/call_graph.py` with this docstring and exactly the imports the moved code needs:

```python
"""The call graph of a scanned script, and what each function reaches.

An import inside a function only matters if that function is actually
reachable from the script's entry point, so this records who calls whom and
walks the result.
"""

import ast
import logging
```

Then move the seven symbols in source order: `FunctionInfo`, `ModuleInfo`, `_SEP`, `split_function_name`, `_resolve`, `build_call_graph`, `collect_used_imports`. Let ruff tell you if an import is unused.

- [ ] **Step 2: Point `cli.py` at the new module**

Delete the seven symbols from `cli.py`. Add, beside the existing `from .analysis...` imports and **below** the emmykit availability guard:

```python
from .analysis.call_graph import (
    FunctionInfo,
    ModuleInfo,
    build_call_graph,
    collect_used_imports,
)
```

`cli.py` still needs `FunctionInfo` and `ModuleInfo` because `ImportFunctionCollector` constructs them and has not moved yet. `_SEP`, `split_function_name` and `_resolve` are internal to the new module — do not re-export them. Verify with `rg -n '_SEP|split_function_name|_resolve' src/veny/cli.py` that `cli.py` has no remaining reference.

> **Correction (whole-branch review, 2026-08-17):** only `_resolve` turned
> out to be genuinely internal. `_SEP` and `split_function_name` both gained
> live callers outside `call_graph.py` as later tasks landed: `_SEP` is
> imported at `src/veny/analysis/imports.py:16`
> (`from .call_graph import _SEP, FunctionInfo, ModuleInfo`), and
> `split_function_name` is imported at `src/veny/analysis/scan.py:17-22`
> and called at `scan.py:247`. Re-exporting them was necessary, not an
> error to avoid.

The import must go below the emmykit guard. 3a's Task 3 hit this: an import placed above it broke the friendly "install emmykit" message that `tests/test_import_guard.py` protects.

- [ ] **Step 3: Add the layering entry**

In `tests/test_layering.py`'s `FORBIDDEN`, add:

```python
    "analysis/call_graph": {"cli", "alias_index", "venv_cache", "stdlib_index",
                            "pypi_client", "json_types", "settings"},
```

`call_graph.py` genuinely imports nothing from `veny`, so every module is forbidden to it — the strictest entry in the table, and correct.

- [ ] **Step 4: Update the test imports**

In `tests/test_call_graph.py`, change the import line to:

```python
from veny.analysis.call_graph import build_call_graph, collect_used_imports
from veny.cli import Options, _analyze_module
```

- [ ] **Step 5: Verify the move was faithful**

```bash
git show HEAD:src/veny/cli.py > /tmp/before.py
```

Diff the moved region against the new file's body by hand. It must differ only by the module docstring and import block. Report the result.

Run: `pixi run test` → expect `294 passed`.
Run: `pixi run python -m pytest tests/test_layering.py -v` → expect `3 passed`.
Run: `pixi run lint` → expect zero.

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files src/veny/analysis/call_graph.py src/veny/cli.py tests/test_layering.py tests/test_call_graph.py
git add src/veny/analysis/call_graph.py src/veny/cli.py tests/test_layering.py tests/test_call_graph.py
git commit -m "refactor: extract the call graph into analysis/call_graph.py"
```

---

### Task 4: Introduce `ImportScan` and extract `analysis/imports.py`

**Goal:** The AST import collector and the per-import resolver move out, taking a mutable `ImportScan` and an injected `is_stdlib` predicate instead of `Options`.

**Files:**
- Create: `src/veny/analysis/scan_state.py`, `src/veny/analysis/imports.py`
- Modify: `src/veny/cli.py` — delete `SysPathVisitor` (689-728), `process_import` (731-828), `ImportFunctionCollector` (855-1372); import from the new modules
- Modify: `tests/test_layering.py` — two more `FORBIDDEN` entries
- Modify: `tests/test_import_collector.py` — update import paths

**Acceptance Criteria:**
- [ ] `ImportScan` is a mutable dataclass carrying exactly the seven fields the scan accumulates, with the same element types `Options` declares
- [ ] `process_import(scan, module_name, file_path, *, is_stdlib)` takes no `Options` and no `StdlibIndex`
- [ ] `ImportFunctionCollector(scan, module_name, file_path)` takes no `Options`
- [ ] `rg -n 'options\.' src/veny/analysis/` returns nothing
- [ ] `analysis/imports.py` imports nothing from `veny.cli`, `veny.stdlib_index`, `veny.alias_index`, `veny.venv_cache`, `veny.pypi_client` or `veny.json_types`
- [ ] `tests/test_layering.py` covers both new modules
- [ ] All tests pass

**Verify:** `pixi run test` → 294 passed

**Why `ImportScan` is forced, not chosen.** `process_import` reads and writes eight `Options` attributes, and `ImportFunctionCollector` writes one. Once these live under `analysis/`, they cannot name `Options` at all — the type annotation alone would make `analysis/imports.py` import `cli`, which `tests/test_layering.py` fails on. Passing the eight fields as separate parameters would give `process_import` ten arguments. So the scan's shared mutable state becomes one object. That object is the design's `ImportScan`, arriving one plan earlier than the design implies, because the layering guard requires it.

It is **mutable**, unlike `Settings`. It is accumulated during a scan; a frozen dataclass would be a lie, the same argument 3a used to make `Settings.stay_out_list` a tuple.

It lives in its own module because both `imports.py` and `scan.py` need it, and `scan.py` imports `imports.py` — putting `ImportScan` in either would make that circular.

**The seven fields, with the types `Options` declares** (`cli.py:138-182`; note `subfolders` is `list[str]`, not `list[Path]`):

| Field | Type | Written by |
|---|---|---|
| `all_imports` | `set[str]` | `_enqueue_top_level_imports`, `find_imports_in_script` |
| `custom_modules` | `dict[str, Path]` | `process_import`, `ImportFunctionCollector` |
| `loaded_custom_modules` | `set[str]` | `process_import` |
| `samedir_files` | `list[Path]` | `process_import` |
| `subfolders` | `list[str]` | `process_import` |
| `sys_path_hints` | `set[Path]` | `_analyze_module` (read by `process_import`) |
| `seen_stdlib_imports` | `set[str]` | `process_import`, `_enqueue_top_level_imports`, `find_imports_in_script` |

**Steps:**

- [ ] **Step 1: Create `scan_state.py`**

```python
"""The mutable state one import scan accumulates."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImportScan:
    """What scanning a script and its local modules discovered.

    Mutable by design: a scan accumulates into it as it walks. Contrast
    Settings, which is frozen because it is fixed before the run starts.

    Attributes:
        all_imports:           Import names the reachable code actually uses.
        custom_modules:        Local module name to the file that provides it.
        loaded_custom_modules: Names resolved to a local module.
        samedir_files:         Local files found beside the script.
        subfolders:            Package subfolders found under the script.
        sys_path_hints:        Directories the script adds to sys.path.
        seen_stdlib_imports:   Standard-library names skipped during the scan.
    """

    all_imports: set[str] = field(default_factory=set)
    custom_modules: dict[str, Path] = field(default_factory=dict)
    loaded_custom_modules: set[str] = field(default_factory=set)
    samedir_files: list[Path] = field(default_factory=list)
    subfolders: list[str] = field(default_factory=list)
    sys_path_hints: set[Path] = field(default_factory=set)
    seen_stdlib_imports: set[str] = field(default_factory=set)
```

- [ ] **Step 2: Move the three symbols**

Create `src/veny/analysis/imports.py`:

```python
"""Walk a module's AST and record what it imports, and from where.

Import names are normalized to their top-level component before anything
classifies them, so a dotted name never reaches the stdlib check verbatim.
"""

import ast
import logging
import os
from collections.abc import Callable
from pathlib import Path

import emmykit as ek

from .call_graph import FunctionInfo, ModuleInfo
from .literals import safe_eval
from .scan_state import ImportScan
```

Move `SysPathVisitor`, `process_import` and `ImportFunctionCollector` in source order. Everything in their bodies stays as it is except the substitutions in Step 3.

- [ ] **Step 3: Change the signatures**

`process_import` becomes:

```python
def process_import(
    scan: ImportScan,
    module_name: str,
    file_path: str | os.PathLike[str],
    *,
    is_stdlib: Callable[[str], bool],
) -> bool:
```

Inside it, make exactly these substitutions and no others:

- `if module_name in options.stdlib:` → `if is_stdlib(module_name):`
- every other `options.<field>` → `scan.<field>`
- `getattr(options, "sys_path_hints", set())` → `scan.sys_path_hints`. The `getattr` default existed because `Options` might not have had the attribute; `ImportScan` always does, and the dataclass makes that a guarantee rather than a hope.

`ImportFunctionCollector.__init__` becomes `(self, scan: ImportScan, module_name: str, file_path: str | os.PathLike[str])`, storing `self.scan = scan`. Its only two uses of the old attribute are writes to `custom_modules` in `_register_constant_path_for_module` (`cli.py:1297`, `1299`) — change `self.options.custom_modules` to `self.scan.custom_modules` there. `rg -n 'self\.options' src/veny/analysis/imports.py` must return nothing when you are done.

`SysPathVisitor` needs no change — it already takes `pathlib_aliases` directly and touches no `Options`.

- [ ] **Step 4: Update `cli.py`**

Delete the three symbols. Add below the emmykit guard:

```python
from .analysis.imports import ImportFunctionCollector, SysPathVisitor, process_import
from .analysis.scan_state import ImportScan
```

`cli.py`'s remaining callers of `process_import` are inside `_enqueue_top_level_imports` and `find_imports_in_script`, which have not moved yet. Give them a scan to pass. The bridge, built once in `find_imports_in_script` and copied back at the end, is specified in Task 5 — for **this** task, build the `ImportScan` at the top of `find_imports_in_script` from the current `options` values and copy the seven fields back before it returns, so behaviour is unchanged while the orchestrator is still in `cli.py`:

```python
    scan = ImportScan(
        all_imports=options.all_imports,
        custom_modules=options.custom_modules,
        loaded_custom_modules=options.loaded_custom_modules,
        samedir_files=options.samedir_files,
        subfolders=options.subfolders,
        sys_path_hints=options.sys_path_hints,
        seen_stdlib_imports=options.seen_stdlib_imports,
    )
```

These are **the same objects, not copies** — the dataclass holds references to the very sets and lists `options` holds, so mutating through `scan` mutates what `options` exposes and no copy-back is needed. That is deliberate for this task: it keeps the diff to signatures only. Task 5 revisits it.

Pass `is_stdlib=options.stdlib.__contains__` at every `process_import` call site.

- [ ] **Step 5: Add the layering entries**

```python
    "analysis/scan_state": {"cli", "alias_index", "venv_cache", "stdlib_index",
                            "pypi_client", "json_types", "settings"},
    "analysis/imports": {"cli", "alias_index", "venv_cache", "stdlib_index",
                         "pypi_client", "json_types"},
```

`analysis/imports` may import `analysis` (its siblings `call_graph`, `literals`, `scan_state`), which is why `analysis` is absent from its forbidden set. It must not reach `stdlib_index` — that is the injection decision, enforced.

- [ ] **Step 6: Update the collector tests**

`tests/test_import_collector.py` constructs nothing directly (it goes through `_analyze_module`), so it may need no change at all. Run it and see. If it imports `ImportFunctionCollector` for a type reference, update the path.

- [ ] **Step 7: Verify**

Run: `rg -n 'options\.' src/veny/analysis/` → expect no output.
Run: `rg -n 'self\.options' src/veny/analysis/imports.py` → expect no output.
Run: `pixi run test` → expect `294 passed`.
Run: `pixi run python -m pytest tests/test_layering.py tests/test_import_discovery.py -v` → expect `3 passed` and `3 passed`.
Run: `pixi run lint` → expect zero.
Run: `pixi run typecheck 2>&1 | tail -1` → at or below 37.

- [ ] **Step 8: Commit**

```bash
pixi run pre-commit run --files src/veny/analysis/scan_state.py src/veny/analysis/imports.py src/veny/cli.py tests/test_layering.py
git add src/veny/analysis/scan_state.py src/veny/analysis/imports.py src/veny/cli.py tests/test_layering.py
git commit -m "refactor: hand the import collector an ImportScan instead of Options"
```

---

### Task 5: Extract `analysis/scan.py`

**Goal:** The scanner itself moves out, and `cli.py` becomes a caller that builds an `ImportScan` and reads the result.

**Files:**
- Create: `src/veny/analysis/scan.py`
- Modify: `src/veny/cli.py` — delete `_analyze_module` (1516-1577), `_enqueue_top_level_imports` (1580-1608), `find_imports_in_script` (1611-1813); add the wrapper
- Modify: `tests/test_layering.py` — one more `FORBIDDEN` entry
- Modify: `tests/test_literals.py` — remove the misplaced `SysPathVisitor` test
- Modify: `tests/test_call_graph.py`, `tests/test_import_collector.py`, `tests/test_split_imports.py` — update import paths
- Create: `tests/test_imports.py` — new home for the relocated `SysPathVisitor` test

**Acceptance Criteria:**
- [ ] `find_imports_in_script(settings, first_path, *, is_stdlib)` returns an `ImportScan` and takes no `Options`
- [ ] `cli.py` keeps a thin `find_imports_in_script(options, first_path)` wrapper that builds `Settings`, calls the new function, and copies the seven fields onto `options`
- [ ] `analysis/scan.py` imports nothing from `veny.cli` or any index module
- [ ] The `SysPathVisitor` test moves from `tests/test_literals.py` to a new `tests/test_imports.py` and imports from `veny.analysis.imports`
- [ ] `rg -n 'options\.' src/veny/analysis/` returns nothing
- [ ] All tests pass, and a live `pixi run veny --justprint` run still discovers imports

**Verify:** `pixi run test` → 294 passed

**Why `cli.py` keeps a wrapper.** `list_packages` (`cli.py:2479-2553`) is the only external caller, and it reads results off `options` afterwards, as do `split_imports` and `warn_about_system_packages`. Rewriting all of those is phase 3c and 3e's work. A wrapper that copies the scan's seven fields back onto `options` keeps this plan's diff bounded and its behaviour constraint provable. **Say so in a comment** — an undocumented bridge reads as an oversight to whoever writes 3c.

Unlike Task 4's aliasing trick, the wrapper here copies **values**, because `find_imports_in_script` now constructs its own `ImportScan` rather than being handed one. Assign each of the seven fields onto `options` after the call. Do not rebind `options.all_imports` to the scan's set and then mutate it later expecting `options` to see it — assign once, at the end.

**The live run is an acceptance criterion, not a formality.** The unit suite mocks nothing here, but `tests/test_import_discovery.py` is three tests over single-file scripts and never exercises the BFS across several local modules. This project has shipped three regressions past a green suite. Run:

```bash
mkdir -p /tmp/veny-3b/pkg
printf 'import yaml\nfrom pkg import helper\nprint(helper.go())\n' > /tmp/veny-3b/main.py
printf 'def go():\n    import base64\n    return base64.b64encode(b"x")\n' > /tmp/veny-3b/pkg/helper.py
touch /tmp/veny-3b/pkg/__init__.py
pixi run veny --justprint /tmp/veny-3b/main.py
```

Expected: it resolves `yaml` to `PyYAML`, treats `pkg`/`helper` as local custom modules rather than PyPI packages, and does not report `base64` as needing installation. Capture the output.

**Steps:**

- [ ] **Step 1: Move the code**

Create `src/veny/analysis/scan.py`:

```python
"""Walk a script and the local modules it reaches, collecting imports.

Breadth-first: analyze a file, enqueue every local module its top-level
imports resolve to, repeat. Then build the call graph and keep only the
imports the reachable code actually uses.
"""

import ast
import collections
import logging
import os
from collections.abc import Callable
from pathlib import Path

import emmykit as ek

from ..settings import Settings
from .call_graph import ModuleInfo, build_call_graph, collect_used_imports
from .imports import ImportFunctionCollector, SysPathVisitor, process_import
from .literals import collect_pathlib_aliases
from .scan_state import ImportScan
```

Move `_analyze_module`, `_enqueue_top_level_imports` and `find_imports_in_script` in source order.

- [ ] **Step 2: Change the signatures**

```python
def _analyze_module(
    settings: Settings,
    scan: ImportScan,
    module_path: Path,
    modules_info: dict[str, ModuleInfo],
    do_sys_path_scan: bool,
) -> tuple[str, ModuleInfo] | None:


def _enqueue_top_level_imports(
    scan: ImportScan,
    module_path: Path,
    import_names: set[str],
    processed_paths: set[Path],
    modules_to_process: collections.deque[Path],
    *,
    is_stdlib: Callable[[str], bool],
) -> None:


def find_imports_in_script(
    settings: Settings,
    first_path: str | os.PathLike[str],
    *,
    is_stdlib: Callable[[str], bool],
) -> ImportScan:
```

> **Correction (whole-branch review, 2026-08-17):** this mandated signature
> has no parameter through which a caller can hand in prior scan state. That
> is not a style gap — `get_all_imports` calls `find_imports_in_script` once
> per file and relies on results accumulating across calls (see the note
> below on `cli.py:2589`-ish), so a signature that always starts from a
> fresh `ImportScan` loses the scan's read direction and made veny report a
> known local module as a PyPI package. This was a measured behaviour
> regression caught during implementation, not a style preference the
> implementer chose to override. The shipped signature in
> `src/veny/analysis/scan.py` adds a seed parameter:
> `find_imports_in_script(settings, first_path, *, is_stdlib, scan: ImportScan | None = None) -> ImportScan`,
> defaulting to a fresh `ImportScan()` when none is given and returning the
> same object it was handed (or a new one) so a caller can accumulate across
> multiple calls the way `options.all_imports` used to.

Substitutions, and nothing else:

- `options.rawlog` → `settings.rawlog`
- `import_name in options.stdlib` → `is_stdlib(import_name)`, at both `cli.py:1592` and `cli.py:1759`
- every other `options.<field>` → `scan.<field>`
- `find_imports_in_script` creates `scan = ImportScan()` at the top and `return scan` at the end. It currently returns `None`; the `return` statements inside it must return the scan too.

Preserve the stdlib-skip asymmetry exactly. PROGRESS.md records that `_enqueue_top_level_imports` and `find_imports_in_script`'s used-imports loop both `continue` on stdlib membership **before** calling `process_import`, so `process_import`'s own debug line never fires for those paths. Do not "tidy" that into a single path — the log output is documented behaviour.

- [ ] **Step 3: Write the `cli.py` wrapper**

Delete the three functions and add:

```python
def find_imports_in_script(options: Options, first_path: str | os.PathLike[str]) -> None:
    """Scan a script for imports and record what was found on options.

    A bridge, not a design: analysis/scan.py returns an ImportScan, while
    list_packages, split_imports and warn_about_system_packages all still read
    these fields off Options. Phase 3c and 3e retire the copy-back by giving
    those consumers the ImportScan directly.

    Args:
        options: The run's Options; the seven scan fields are overwritten.
        first_path: The script to scan.
    """
    settings = Settings(
        my_name=options.my_name,
        cwd=options.cwd,
        stay_out_list=tuple(options.stay_out_list),
        search_above_this_dir=options.search_above_this_dir,
        rawlog=options.rawlog,
    )
    scan = analysis_scan.find_imports_in_script(
        settings, first_path, is_stdlib=options.stdlib.__contains__
    )
    options.all_imports = scan.all_imports
    options.custom_modules = scan.custom_modules
    options.loaded_custom_modules = scan.loaded_custom_modules
    options.samedir_files = scan.samedir_files
    options.subfolders = scan.subfolders
    options.sys_path_hints = scan.sys_path_hints
    options.seen_stdlib_imports = scan.seen_stdlib_imports
```

Import it as `from .analysis import scan as analysis_scan`, below the emmykit guard, so the wrapper's own name does not shadow the module's.

**`get_all_imports` calls `find_imports_in_script` once per file** (`cli.py:2589`-ish) and relies on results accumulating across calls. The wrapper above **overwrites** rather than accumulates, which would break it. Check `get_all_imports`'s loop before you finish this step: if it needs accumulation, the wrapper must union into the existing values rather than assign. Measure the current behaviour — `find_imports_in_script` today does `options.all_imports.add(...)` while `get_all_imports` does `options.all_imports = set()` once before the loop — and make the wrapper reproduce it exactly. **Report which you found and what you did.** This is the single most likely place for this task to introduce a silent regression.

- [ ] **Step 4: Add the layering entry**

```python
    "analysis/scan": {"cli", "alias_index", "venv_cache", "stdlib_index",
                      "pypi_client", "json_types"},
```

> **Correction (whole-branch review, 2026-08-17):** collecting this
> `FORBIDDEN` entry, `analysis/imports`'s (above) `settings`-less set, and
> `analysis/call_graph`'s and `analysis/scan_state`'s `settings`-*including*
> sets (earlier in this plan) exposes an unexplained inconsistency: two of
> these four modules give `settings` a free pass and two do not, with no
> stated reason for the split. The review's Finding 2 replaced this whole
> hand-written table with a derived one — every module's forbidden set comes
> from a declared layer ordering (`tests/test_layering.py`'s `LAYERS`) rather
> than being typed out per module — which makes the question moot: under
> that ordering, `settings` sits in a layer below all of `analysis/*`, so
> nothing in `analysis/` may be forbidden from importing it, and the
> `settings`-including sets were the actual anomaly, not the ones that
> omitted it.

- [ ] **Step 5: Relocate the misplaced test**

`tests/test_literals.py:56-68` holds `test_sys_path_built_with_the_slash_operator_is_discovered`, which tests `SysPathVisitor` — a symbol that never belonged to `literals.py` and now lives in `analysis/imports.py`. Move it, unchanged apart from its imports, into a new `tests/test_imports.py`:

```python
"""Pin the AST walker that finds what a module imports and where from."""

import ast

from veny.analysis.imports import SysPathVisitor
from veny.analysis.literals import collect_pathlib_aliases
```

Delete it from `tests/test_literals.py`. The suite total does not change — one test moved, none added or removed.

- [ ] **Step 6: Verify**

Run: `rg -n 'options\.' src/veny/analysis/` → expect no output.
Run: `pixi run test` → expect `294 passed`.
Run: `pixi run python -m pytest tests/test_import_discovery.py tests/test_split_imports.py tests/test_layering.py -v` → all pass.
Run the live check from the task preamble and capture its output.
Run: `pixi run lint`, `pixi run python -m ruff format --check .`, `pixi run typecheck 2>&1 | tail -1`.

- [ ] **Step 7: Commit**

```bash
pixi run pre-commit run --files src/veny/analysis/scan.py src/veny/cli.py tests/test_layering.py tests/test_literals.py tests/test_imports.py
git add src/veny/analysis/scan.py src/veny/cli.py tests/test_layering.py tests/test_literals.py tests/test_imports.py
git commit -m "refactor: extract the script scanner into analysis/scan.py"
```

---

### Task 6: Retire `FunctionInfo.ast_node`

**Goal:** A field that has been write-only since phase 1 is removed, at the moment the design said to decide it.

**Files:**
- Modify: `src/veny/analysis/call_graph.py` — `FunctionInfo.__init__`
- Modify: `src/veny/analysis/imports.py` — the one construction site

**Acceptance Criteria:**
- [ ] `FunctionInfo` no longer stores `ast_node`, and its constructor no longer takes `node`
- [ ] `rg -n 'ast_node' src/ tests/` returns nothing
- [ ] All tests pass, with no change in what any of them assert

**Verify:** `pixi run test` → 294 passed

**Why now, and why it is safe.** PROGRESS.md parked this in phase 1: *"`FunctionInfo.ast_node` is write-only as of phase 1. Its only reader was the per-function loop that ran `FileOperationsVisitor` over each reachable `FunctionDef`, deleted with the visitor block. ... phase 3 splits `FunctionInfo` and the call graph into `analysis/call_graph.py`, which is the right moment to decide whether the field has a consumer in the new shape."* This is that moment, and the answer is no: `rg '\.ast_node' src/ tests/` returns exactly one hit, the assignment itself. Every analyzed function of every analyzed module currently retains a live `ast.FunctionDef` reference that nothing reads.

Confirm that `rg` result yourself before deleting — the note is from phase 1 and its stated line number is already stale.

**Steps:**

- [ ] **Step 1: Confirm there is no reader**

Run: `rg -n 'ast_node' src/ tests/`. Expect exactly one hit: the assignment in `FunctionInfo.__init__`. If there is more than one, **stop and report** — the parked note is out of date and this task needs rethinking.

- [ ] **Step 2: Remove the field**

In `analysis/call_graph.py`, drop the `node` parameter from `FunctionInfo.__init__` and the `self.ast_node = node` line, and update the docstring's `Args:` section.

In `analysis/imports.py`, the single construction site (`cli.py:911` before the move) becomes `FunctionInfo(function_name)`.

- [ ] **Step 3: Verify**

Run: `rg -n 'ast_node' src/ tests/` → expect no output.
Run: `pixi run test` → expect `294 passed`, with no test edited.
Run: `pixi run lint` and `pixi run typecheck 2>&1 | tail -1`.

If any test needed editing to keep passing, the field was not write-only — stop and report.

- [ ] **Step 4: Commit**

```bash
pixi run pre-commit run --files src/veny/analysis/call_graph.py src/veny/analysis/imports.py
git add src/veny/analysis/call_graph.py src/veny/analysis/imports.py
git commit -m "refactor: drop FunctionInfo.ast_node, write-only since phase 1"
```

---

### Task 7: Run the gates and update PROGRESS

**Goal:** Every gate confirmed, and `PROGRESS.md` points at plan 3c.

**Files:**
- Modify: `PROGRESS.md`

**Acceptance Criteria:**
- [ ] `pixi run test` passes with 294 tests
- [ ] `ruff check .` zero; `ruff format --check .` every file formatted
- [ ] `pixi run typecheck 2>&1 | tail -1` at or below 37
- [ ] `pixi run smoke` green, or the note says explicitly it was skipped and why
- [ ] A live `pixi run veny --no-cache` run still builds a venv and runs the script
- [ ] `PROGRESS.md` **Current work** names plan 3c as the next action, with the measured `wc -l src/veny/cli.py`, and updates the 3a-3e table
- [ ] Gotchas records the `base_classes` copy trap and the `ImportScan` bridge
- [ ] Deferred items records the remaining coverage gaps and the design amendments

**Verify:** `pixi run test && pixi run lint && pixi run smoke` → all green

**Steps:**

- [ ] **Step 1: Run every gate**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run smoke
pixi run typecheck 2>&1 | tail -1
wc -l src/veny/cli.py src/veny/analysis/*.py
```

Then the live check:

```bash
printf 'import yaml\nprint(yaml.safe_load("j: 10"))\n' > /tmp/veny-3b-final.py
pixi run veny --no-cache /tmp/veny-3b-final.py
```

Expected: `{'j': 10}`.

- [ ] **Step 2: Update PROGRESS.md**

Replace the **Current work** `**Next action:**` block with a plan 3c pointer carrying the measured line count, and update the 3a-3e table's 3b row.

Add these Gotchas entries, in PROGRESS.md's existing prose register:

- **`ImportFunctionCollector` does not fill `ModuleInfo.base_classes`; `analysis/scan.py`'s `_analyze_module` does**, as a separate assignment after the walk. A test that constructs the collector directly and reads `module_info.base_classes` gets `{}`, so `build_call_graph`'s base-class fallback never fires and an inherited method's imports look unreachable — which reads exactly like a bug in inheritance handling and is not one. Measured both ways while planning 3b: direct collector gives `base_classes == {}` and `collect_used_imports` returns `set()`; through `_analyze_module` it gives `{'Base': [], 'Child': ['Base']}` and `{'base64'}`. Test the call graph through `_analyze_module`.
- **`cli.py`'s `find_imports_in_script` is a bridge, not a design.** `analysis/scan.py` returns an `ImportScan`; the wrapper copies its seven fields onto `Options` because `list_packages`, `split_imports` and `warn_about_system_packages` still read them there. Phase 3c and 3e retire the copy-back by handing those consumers the `ImportScan` directly. Do not add new readers of the copied fields in the meantime.

Add to Deferred items:

- `ImportFunctionCollector`'s exotic resolution paths — `super()`, dynamic `__import__`, `spec_from_file_location`, `SourceFileLoader(...).load_module()`, and the `self.<attr>` type inference — still have no direct tests. Plan 3b added five covering the paths that decide *which* imports are found; these decide *whether a call edge is drawn*, and a break in them silently narrows reachability.
- `get_all_imports` and `stayed_out_dir` remain in `cli.py` deliberately. When phase 3e gives `get_all_imports` a home in `pipeline.py`, `stayed_out_dir` should move with it and take `settings` — it reads only `stay_out_list`, which `Settings` already carries.
- The design doc needs two amendments recorded by 3b: `ImportScan` must list `seen_stdlib_imports` (its omission would silence `warn_about_system_packages`), and "analysis/* ... takes neither `AliasIndex` nor `StdlibIndex`" is satisfied by injecting `is_stdlib: Callable[[str], bool]` rather than by removing the dependency. Its "Pure AST in, names out" claim remains untrue — `_register_constant_path_for_module` and `process_import` both touch the filesystem during a scan — and 3b did not change that.

- [ ] **Step 3: Commit**

```bash
pixi run pre-commit run --files PROGRESS.md
git add PROGRESS.md
git commit -m "docs: record plan 3b and point at the classify extraction"
```

---

## Rollback

Each task is one commit on a branch off `3215df5`. To undo the plan, reset the branch. Do not use `git stash` — a pre-commit formatter hook rewriting files mid-stash has blocked the pop in this repository before.
