# Phase 1: Delete the File/Network Visitor Block — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the ~1,600-line file/network AST-visitor subsystem from `src/veny/cli.py`, whose entire product is four `logging.info` calls, without changing which imports veny discovers.

**Architecture:** This is a pure deletion guarded by a characterization test. `FileOperationsVisitor`, `NetworkOperationsVisitor` and their two `TopLevel*` subclasses populate `options.read_files`, `write_files`, `download_urls` and `upload_urls`; the only consumer is a reporting block at `cli.py:3607-3634`. Nothing gates on the result, no manifest records it, and no test references it. Deleting it makes two module caches (`module_contents`, `module_trees`) write-only, so they go too, and `find_imports_and_IO_in_script` loses the `_and_IO_` half of its name.

**Tech Stack:** Python 3.12-3.13, pytest, ruff, mypy, pixi.

**Global Constraints:**
- The set of imports veny discovers must not change. This is the whole risk of the phase, and Task 1 exists to pin it before anything is deleted.
- `pixi run lint` (`ruff check .`) and `ruff format --check .` pass repo-wide today and must still pass. Do not reintroduce hand-aligned columns; `ruff format` will undo them.
- `pixi run typecheck` cannot pass — 46 pre-existing whole-repo errors across `src/veny/cli.py` and `tests/test_split_imports.py`. The gate is that the count must not **rise**. Measure with `pixi run typecheck 2>&1 | tail -1` before and after.
- Invoke tools through pixi's `python -m <tool>` form (`pixi run python -m pytest`, `pixi run python -m mypy`), matching the tasks in `pixi.toml` — bare binaries hit a shebang-resolution problem on macOS.
- `.git/hooks/pre-commit` is not installed, so `git commit` does not run hooks. Run `pixi run pre-commit run --files <paths>` by hand before each commit.
- Do not use `git stash` or `git checkout <sha>` in the working tree. Use `git worktree add` for any comparison against another commit.
- Stage paths explicitly. A test run can leave `.veny_custom_modules_*.pkl` and `logs/` behind; never `git add -A`.

**User decisions (already made):**
- "delete" — the visitor block is removed outright, not parked in a `script_effects.py` and not promoted to a real feature.
- "b" — uv depth: environment layer to uv, veny keeps its own venv cache. (Phase 2; constrains nothing here.)
- "(i)" — one target-architecture spec, then a plan per phase. This is the phase 1 plan.
- "delete" — `--full` is removed rather than fixed. (Phase 3; do not touch `--full` in this plan.)

**Design doc:** `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md`

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `tests/test_import_discovery.py` | Pins which imports the scan discovers, across module-level, function-body and custom-module reachability. | Create |
| `src/veny/cli.py` | Everything else. | Modify — net ~1,600 lines removed |
| `PROGRESS.md` | Project ledger. | Modify — record phase 1 complete |

All line numbers below are as of commit `f696da7`. They shift as edits are applied, so **work bottom-up within each task** and locate code by symbol name, not by line number alone.

---

### Task 1: Pin import discovery with a characterization test

**Goal:** A test that fails if the deletion disturbs which imports veny finds — written and passing *before* any code is removed.

**Files:**
- Create: `tests/test_import_discovery.py`

**Acceptance Criteria:**
- [ ] Three tests pass against the current, undeleted `cli.py`
- [ ] Each test asserts an exact set, never `assertTrue` or "no exception raised"
- [ ] The mutation check in Step 3 makes `test_function_body_import_in_a_custom_module_is_discovered` fail, proving the test can fail

**Verify:** `pixi run python -m pytest tests/test_import_discovery.py -v` → 3 passed

**Test design.** Stating, per test, the behavior, the bug it catches, and where the expected value came from:

1. `test_function_body_import_in_a_custom_module_is_discovered` — behavior: an import written inside a function body of a local custom module is discovered when the script calls that function. Bug it catches, and this is the specific one this phase risks: Task 2 deletes the visitor calls at `cli.py:3515-3519`, and `collect_imports_from_module(first_module_key)` sits on line 3514, immediately above them. Taking that line along with the block seeds the call-graph traversal with nothing, and `pandas` vanishes. **Verified** — replacing line 3514 with `pass` yields `{'numpy', 'requests'}` against the expected `{'numpy', 'pandas', 'requests'}`. `numpy` and `requests` survive that mutation because they are module-level imports reached by `_enqueue_top_level_imports`, which is a different path; only the function-body import discriminates. Expected value from hand-reading the fixture: `helper.py` imports `numpy` at module level and `pandas` inside `h()`; `s.py` imports `requests` at module level and calls `helper.h()`.
2. `test_standard_library_imports_are_not_reported_as_needing_install` — behavior: stdlib names are recorded as seen, not as imports to install. Bug it catches: removing or inverting the stdlib filter would put `os` and `json` into `all_imports` and veny would try to `pip install os`. Expected value from domain knowledge: `os` and `json` are in `sys.stdlib_module_names` on every supported interpreter.
3. `test_a_script_with_no_third_party_imports_yields_an_empty_import_set` — behavior: the empty case is genuinely empty. Bug it catches: any change that seeds the set with the module's own name, or that stops filtering stdlib when nothing else is present. Expected value: hand-derived — a script importing only `sys` has no third-party imports.

No mocking is used. The scan touches only the filesystem, and the fixture files are the point of the test rather than an irrelevant detail, so `tmp_path` is real and unmocked.

**Steps:**

- [ ] **Step 1: Write the characterization test**

Create `tests/test_import_discovery.py`:

```python
"""Pin which imports veny's scan discovers, independent of I/O recording."""

from pathlib import Path

from veny import cli


def _scan(script: Path, custom_modules: dict[str, Path]) -> cli.Options:
    """Run the import scan over one script and return the populated options.

    Args:
        script:         The Python file to analyze.
        custom_modules: Local module name to file path, as main() would supply.

    Returns:
        The Options object the scan wrote its findings into.
    """
    options = cli.Options()
    options.rawlog = True
    options.python_script = script
    options.script_dir = script.parent
    options.custom_modules = custom_modules
    cli.find_imports_and_IO_in_script(options, script)
    return options


def test_function_body_import_in_a_custom_module_is_discovered(
    tmp_path: Path,
) -> None:
    """An import inside a called function of a local module still counts."""
    helper = tmp_path / "helper.py"
    helper.write_text(
        "import numpy\n\n\ndef h():\n    import pandas\n\n    return pandas\n"
    )
    script = tmp_path / "s.py"
    script.write_text(
        "import requests\n"
        "import helper\n\n\n"
        "def main():\n"
        "    requests.get('https://example.com')\n"
        "    return helper.h()\n\n\n"
        "main()\n"
    )

    options = _scan(script, {"helper": helper})

    assert options.all_imports == {"numpy", "pandas", "requests"}
    assert options.loaded_custom_modules == {"helper"}


def test_standard_library_imports_are_not_reported_as_needing_install(
    tmp_path: Path,
) -> None:
    """Stdlib names are recorded as seen, never as imports to install."""
    script = tmp_path / "s.py"
    script.write_text("import os\nimport json\nimport requests\n\nprint(os, json)\n")

    options = _scan(script, {})

    assert options.all_imports == {"requests"}
    assert {"os", "json"} <= options.seen_stdlib_imports


def test_a_script_with_no_third_party_imports_yields_an_empty_import_set(
    tmp_path: Path,
) -> None:
    """The empty case is empty -- nothing is seeded into the import set."""
    script = tmp_path / "s.py"
    script.write_text("import sys\n\nprint(sys.version)\n")

    options = _scan(script, {})

    assert options.all_imports == set()
```

- [ ] **Step 2: Run the tests against the current code**

Run: `pixi run python -m pytest tests/test_import_discovery.py -v`
Expected: `3 passed`. These characterize existing behavior, so they pass *before* the deletion — that is the point. If any fails now, stop and investigate; the fixture assumption is wrong and the rest of the plan is unsafe.

- [ ] **Step 3: Prove the first test can fail**

The test is worthless if it cannot fail. Temporarily break the exact thing Task 2 puts at risk — in `find_imports_and_IO_in_script`, replace the call-graph seed at `cli.py:3514`:

```python
    collect_imports_from_module(first_module_key)
```

with:

```python
    pass  # MUTATED
```

Note this is the `first_module_key` call on line 3514, **not** either of the two `new_module_key` calls further down (3552 and 3574). Those two were tried and neither changes the result — the seed is the discriminating line.

**Mutate the working tree copy, not a side copy.** `pixi.toml`'s `[activation.env]` sets `PYTHONPATH = "src"`, and that **overwrites** an inherited `PYTHONPATH`. Copying `src/` elsewhere, mutating the copy and pointing `PYTHONPATH` at it silently tests `/workspace/src` anyway and reports a false pass. Edit `src/veny/cli.py` in place and restore it in the next step.

Run: `pixi run python -m pytest tests/test_import_discovery.py -v`
Expected: `1 failed, 2 passed`. `test_function_body_import_in_a_custom_module_is_discovered` fails with `assert {'numpy', 'requests'} == {'numpy', 'pandas', 'requests'}` — `pandas` is the sole missing item. The other two tests still pass, which is correct: they exercise the module-level path, which this mutation does not touch. (This exact result was measured while writing the plan.)

Then **restore the line** and re-run:

Run: `pixi run python -m pytest tests/test_import_discovery.py -v`
Expected: `3 passed`

- [ ] **Step 4: Confirm the working tree is clean apart from the new test**

Run: `git status --short`
Expected: only `?? tests/test_import_discovery.py`. If `cli.py` shows as modified, Step 3's restore was incomplete — fix it before committing.

- [ ] **Step 5: Run pre-commit and commit**

```bash
pixi run pre-commit run --files tests/test_import_discovery.py
git add tests/test_import_discovery.py
git commit -m "test: pin import discovery before deleting the visitor block"
```

---

### Task 2: Delete the visitor classes, their helpers, and their consumer

**Goal:** Remove the visitor subsystem and every reference to it, with the import set unchanged.

**Files:**
- Modify: `src/veny/cli.py` — `Options.__init__` (114-126), `_literal_str` through `TopLevelNetworkOperationsVisitor` (665-2195), `transform_call` (2236-2277), the four resets (3394-3397), the first-module visitor calls (3515-3519), the per-module visitor loop (3585-3606), the reporting block (3607-3640)

**Acceptance Criteria:**
- [ ] `rg 'OperationsVisitor|_record_IO|read_files|write_files|download_urls|upload_urls|current_method_name|transform_call' src/veny/cli.py` returns nothing
- [ ] `collect_pathlib_aliases`, `is_pathlib_ctor`, `_safe_eval_node` and `safe_eval` still exist — `SysPathVisitor` and `_analyze_module` need them
- [ ] All tests pass, including Task 1's three
- [ ] `ruff check .` reports zero

**Verify:** `pixi run test` → 260 passed (257 existing + Task 1's 3)

**Steps:**

- [ ] **Step 1: Record the mypy baseline**

Run: `pixi run typecheck 2>&1 | tail -1`
Expected: `Found 46 errors in 2 files (checked 22 source files)` — measured on `f696da7`, across `src/veny/cli.py` and `tests/test_split_imports.py`. Task 5 compares against this. Note the task is `typecheck`, not `mypy`; every pixi task goes through `python -m <tool>` to dodge a macOS shebang-resolution problem, so invoke tools that way rather than bare.

- [ ] **Step 2: Delete bottom-up, largest ranges last**

Line numbers shift as you edit, so delete in **descending** line order. Each range below is inclusive and stated as of `f696da7`; confirm the first and last line of each range by symbol before deleting.

1. **The reporting block**, `cli.py:3607-3640` — from `    if not options.rawlog:` through the closing `)` of the "Found no file or network operations" call. This is the entire consumer. The function ends there, so after deletion `find_imports_and_IO_in_script` ends with the loop you delete next.

2. **The per-module visitor loop**, `cli.py:3585-3606` — from the comment `    # For every *other* local module, do:` through `            NetworkOperationsVisitor(options, func_src).visit(func_node)`. The whole loop exists only to run visitors; nothing inside it feeds anything else.

3. **The first-module visitor calls**, `cli.py:3515-3519`:

```python
    init_src = module_contents[first_module_key]
    init_tree = module_trees[first_module_key]

    FileOperationsVisitor(options, init_src).visit(init_tree)
    NetworkOperationsVisitor(options, init_src).visit(init_tree)
```

   Delete all five lines — and **stop there**. The line immediately above them is:

```python
    collect_imports_from_module(first_module_key)
```

   **Keep it.** It seeds the call-graph traversal and has nothing to do with the visitors; it is adjacent to them only by accident. Deleting it is the single most likely mistake in this task, which is exactly why Task 1 pinned it. The failure signature if you take it: `test_function_body_import_in_a_custom_module_is_discovered` fails with `assert {'numpy', 'requests'} == {'numpy', 'pandas', 'requests'}`.

4. **The four resets**, `cli.py:3394-3397`:

```python
    options.read_files = []
    options.write_files = []
    options.download_urls = []
    options.upload_urls = []
```

5. **`transform_call`**, `cli.py:2236-2277` — the whole function. It is already dead: its only reference is its own `def`.

6. **The helpers and the four visitor classes**, `cli.py:665-2195` — from `def _literal_str(expr_node: ast.AST) -> str | None:` through the final line of `TopLevelNetworkOperationsVisitor`, stopping **before** `def collect_pathlib_aliases` at 2196. This covers `_literal_str`, `get_evaluated_arg`, `_record_IO`, `_get_full_attr_name`, `unpack_method_call`, `FileOperationsVisitor`, `TopLevelFileOperationsVisitor`, `NetworkOperationsVisitor` and `TopLevelNetworkOperationsVisitor`.

7. **The five `Options` fields**, `cli.py:114-126`:

```python
        self.read_files: list[
            Path
        ] = []  # List of files read       by the Python script.
        self.write_files: list[
            Path
        ] = []  # List of files written    by the Python script.
        self.download_urls: list[
            Path
        ] = []  # List of  URLs downloaded by the Python script.
        self.upload_urls: list[
            Path
        ] = []  # List of  URLs uploaded   by the Python script.
        self.current_method_name: str = ""  # Name of the current method being executed.
```

- [ ] **Step 3: Verify nothing survives**

Run:

```bash
rg -n 'OperationsVisitor|_record_IO|_literal_str|get_evaluated_arg' src/veny/cli.py
rg -n 'read_files|write_files|download_urls|upload_urls' src/veny/cli.py
rg -n 'transform_call|current_method_name|_get_full_attr_name' src/veny/cli.py
```

Expected: all three return no output.

Then confirm the survivors are intact:

```bash
rg -n '^def (collect_pathlib_aliases|is_pathlib_ctor|_safe_eval_node|safe_eval)' src/veny/cli.py
```

Expected: four lines.

- [ ] **Step 4: Let ruff find the imports the deletion orphaned**

Run: `pixi run lint`
Expected: `F401` unused-import errors are likely, since the visitors were the only users of some module-level imports. Delete exactly the imports ruff names — do not guess at others. Re-run until it reports zero.

Run: `pixi run format` then `pixi run lint`
Expected: zero.

- [ ] **Step 5: Run the full suite**

Run: `pixi run test`
Expected: `260 passed`. If Task 1's first test fails, the traversal was over-deleted — most likely `collect_imports_from_module(first_module_key)` went with Step 2.3. Restore it.

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files src/veny/cli.py
git add src/veny/cli.py
git commit -m "refactor: delete the file and network operation visitors"
```

---

### Task 3: Remove the module caches the deletion made write-only

**Goal:** Delete `module_contents` and `module_trees`, which after Task 2 are written and never read.

**Files:**
- Modify: `src/veny/cli.py` — `_analyze_module` signature, docstring and body; `find_imports_and_IO_in_script` locals and both `_analyze_module` call sites

**Acceptance Criteria:**
- [ ] `rg 'module_contents|module_trees' src/veny/cli.py` returns nothing
- [ ] `_analyze_module` takes three parameters plus `options` and `do_sys_path_scan`, and still returns `tuple[str, ModuleInfo] | None`
- [ ] All tests pass

**Verify:** `pixi run test` → 260 passed

**Why this is safe:** `_analyze_module` wrote `module_contents[module_key] = file_content` and `module_trees[module_key] = tree` as caches. Their only readers were `cli.py:3515-3516` and `cli.py:3588-3592`, both deleted in Task 2. `file_content` and `tree` are still used *locally* inside `_analyze_module` (for `ast.parse` and `collector.visit`); only the dictionary writes go.

**Steps:**

- [ ] **Step 1: Confirm they are write-only before touching anything**

Run: `rg -n 'module_contents|module_trees' src/veny/cli.py`
Expected: only the parameter declarations, docstring lines, the two assignments in `_analyze_module`, the two local dict initializations, and the two call-site argument pairs. **No reads.** If a read appears, stop — Task 2 was incomplete.

- [ ] **Step 2: Remove the two parameters from `_analyze_module`**

Delete these two lines from the signature (`cli.py:3269-3270`):

```python
    module_contents: dict[str, str],
    module_trees: dict[str, ast.AST],
```

Delete these two lines from the docstring Args block (`cli.py:3286-3287`):

```python
        module_contents:  Dictionary mapping module keys to their source code.
        module_trees:     Dictionary mapping module keys to their ASTs.
```

Amend the docstring summary line at `cli.py:3276` from:

```python
    - Updates modules_info / module_contents / module_trees.
```

to:

```python
    - Updates modules_info.
```

Delete the two assignments at `cli.py:3307-3308`:

```python
    module_contents[module_key] = file_content
    module_trees[module_key] = tree
```

- [ ] **Step 3: Remove the locals and both call sites**

Delete the two local initializations at `cli.py:3401-3402`:

```python
    module_contents: dict[str, str] = {}
    module_trees: dict[str, ast.AST] = {}
```

Delete the argument pair from the first `_analyze_module` call (`cli.py:3437-3438`) and from the second (`cli.py:3562-3563`):

```python
            module_contents,
            module_trees,
```

- [ ] **Step 4: Verify and test**

Run: `rg -n 'module_contents|module_trees' src/veny/cli.py`
Expected: no output.

Run: `pixi run test`
Expected: `260 passed`

Run: `pixi run lint`
Expected: zero. If `ast` is now unused at module level, ruff says so — but `ast` is still used by `_safe_eval_node`, `SysPathVisitor` and `ImportFunctionCollector`, so it should stay.

- [ ] **Step 5: Commit**

```bash
pixi run pre-commit run --files src/veny/cli.py
git add src/veny/cli.py
git commit -m "refactor: drop the module content and tree caches nothing reads"
```

**Note on `visited_funcs`:** it is still passed to `collect_used_imports`, which uses it as a recursion guard, so it stays. After Task 2 nothing *reads* it in `find_imports_and_IO_in_script` itself. Leave it alone — removing it would change `collect_used_imports`, which is out of scope here.

---

### Task 4: Rename the scan to match what it now does

**Goal:** `find_imports_and_IO_in_script` no longer finds I/O. Rename it and correct its docstring.

**Files:**
- Modify: `src/veny/cli.py` — the definition (3367) and both call sites (4353, 4411)
- Modify: `tests/test_import_discovery.py` — the helper's call

**Acceptance Criteria:**
- [ ] `rg 'find_imports_and_IO_in_script' src/veny/ tests/` returns nothing
- [ ] The function is named `find_imports_in_script`, matching the name the design doc assigns to `analysis/scan.py`
- [ ] The docstring no longer claims to find or return I/O
- [ ] All tests pass

**Verify:** `pixi run test` → 260 passed

**Steps:**

- [ ] **Step 1: Rename the definition and fix the docstring**

At `cli.py:3367`, change:

```python
def find_imports_and_IO_in_script(
    options: Options, first_path: str | os.PathLike[str]
) -> None:
    """Find all imports and I/O in the script.
```

to:

```python
def find_imports_in_script(
    options: Options, first_path: str | os.PathLike[str]
) -> None:
    """Find all imports in the script.
```

In the same docstring, change the Returns line from:

```python
        None - modifies options to include all imports and I/O operations found in the script.
```

to:

```python
        None - modifies options to include all imports found in the script.
```

Also change the Args line for `first_path` from `...to analyze for imports and I/O.` to `...to analyze for imports.`

- [ ] **Step 2: Update both call sites**

At `cli.py:4353` and `cli.py:4411`, change `find_imports_and_IO_in_script(` to `find_imports_in_script(`. Everything else on those lines is unchanged.

- [ ] **Step 3: Update the test helper**

In `tests/test_import_discovery.py`, change the line in `_scan`:

```python
    cli.find_imports_and_IO_in_script(options, script)
```

to:

```python
    cli.find_imports_in_script(options, script)
```

- [ ] **Step 4: Verify and test**

Run: `rg -n 'find_imports_and_IO_in_script' src/veny/ tests/ --glob '!*.pyc'`
Expected: no output.

Run: `pixi run test`
Expected: `260 passed`

- [ ] **Step 5: Commit**

```bash
pixi run pre-commit run --files src/veny/cli.py tests/test_import_discovery.py
git add src/veny/cli.py tests/test_import_discovery.py
git commit -m "refactor: rename the scan now that it no longer finds I/O"
```

---

### Task 5: Run the gates and record the outcome

**Goal:** Prove the phase held every gate, and leave `PROGRESS.md` accurate for the next session.

**Files:**
- Modify: `PROGRESS.md`

**Acceptance Criteria:**
- [ ] `pixi run test` passes with 260 tests
- [ ] `ruff check .` reports zero and `ruff format --check .` reports every file formatted
- [ ] The whole-repo `mypy .` error count is less than or equal to Task 2 Step 1's baseline
- [ ] `pixi run smoke` is green
- [ ] `PROGRESS.md`'s **Current work** names phase 2 as the next action, with the measured line count

**Verify:** `pixi run test && pixi run lint && pixi run smoke` → all green

**Steps:**

- [ ] **Step 1: Run every gate and capture the numbers**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run smoke
```

Expected: `260 passed`; `ruff check .` zero; `26 files already formatted` (25 today plus the new test); smoke green. Note `pixi run format` **rewrites** files — use `--check` as above for a gate, and only run the rewriting form if the check fails.

`pixi run smoke` builds a wheel and installs it into a throwaway venv, so it **needs the network** and is deliberately excluded from `pixi run test`. If you are offline, say so in the task's completion note rather than reporting the gate as passed.

Then, separately, because these are counts rather than pass/fail:

```bash
pixi run typecheck 2>&1 | tail -1
wc -l src/veny/cli.py
```

Expected: at or below `Found 46 errors in 2 files (checked 22 source files)`; `cli.py` at roughly 4,400 lines, down from 6,020.

If the mypy count **rose**, find the new errors with `pixi run python -m mypy src/veny/cli.py` and fix only those. Per the project's conflict rule, tests passing outranks mypy clean, but a rise is a regression this phase introduced and must be resolved rather than accepted.

- [ ] **Step 2: Update PROGRESS.md**

In the **Current work** section, replace the `**Next action:**` paragraph with the phase 2 pointer, substituting the numbers measured in Step 1:

```markdown
**Next action:** write the phase 2 implementation plan (migrate to `uv`, with
veny keeping its own venv cache). Phase 1 is complete: the file/network visitor
block is deleted, `src/veny/cli.py` is <MEASURED> lines (was 6,020), and
`tests/test_import_discovery.py` pins the import set that deletion had to
preserve.
```

Also update the Deferred-items line recording `cli.py`'s length to the measured value, so the two do not disagree.

- [ ] **Step 3: Commit**

```bash
pixi run pre-commit run --files PROGRESS.md
git add PROGRESS.md
git commit -m "docs: record phase 1 complete and point at the uv migration"
```

---

## Rollback

Every task is one commit and the phase touches one source file plus one new test. To undo the whole phase: `git revert --no-commit <task-5-sha>..<task-1-sha>~1` on a branch, or simply reset the branch. Do not use `git stash` — a formatter hook rewriting files mid-stash has blocked the pop in this repository before.
