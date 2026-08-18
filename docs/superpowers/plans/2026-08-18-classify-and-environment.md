# Phase 3c: Classify and Environment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract `classify.py` (import classification: bad/installed/uninstalled, plus dependency expansion) and `environment.py` (the sole owner of `uv` invocation) out of `src/veny/cli.py`, and give each its first tests — including a live, network-free integration test of the real `uv pip install`/`uninstall` path that today is stubbed everywhere.

**Architecture:** Two independent extractions, environment first because `classify`'s probe venv is built through it. `environment.py` sheds `Options` entirely and takes explicit parameters. `classify.py` is handed an `ImportScan`, returns a new frozen `Requirements`, and mutates nothing it was given; `cli.py` keeps a thin `split_imports(options)` adapter that builds the probe and performs one **total** copy-back of five `Options` fields. The temporary probe venv does not disappear in this phase — it becomes an injected `ContextManager[Callable[[str], bool]]`, which is what actually makes `classify` unit-testable, and the plan says so plainly rather than claiming the design's stronger wording.

**Tech Stack:** Python 3.12-3.13, pytest, ruff, mypy, pixi, uv.

**Design doc:** `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md`, phase 3 section.

---

## Global Constraints

- **Behaviour must not change.** Which imports veny classifies bad / installed / uninstalled, the uv command lines it builds, and the requirements files it writes must be identical before and after every task. Task 5's differential corpus check is what proves it; a green suite is not sufficient evidence in this repository and has three times not been.
- The suite starts at **296 passing** (measured at `dc1c3c4`, `pixi run test`) and must never go down. Each task states its expected count.
- `pixi run lint` (`ruff check .`) must report zero. `pixi run python -m ruff format --check .` must report every file formatted (**40 files** at `dc1c3c4`).
- **The whole-repo mypy count must not rise above 37.** Measure with `pixi run typecheck 2>&1 | tail -1`. It cannot reach zero; it is a ceiling to stay under, not a gate to satisfy, and the pre-commit `mypy` hook is `mypy .` with `pass_filenames: false`, so it always fails. See "The mypy ceiling" below for the per-file baseline and what this plan does and does not clean up.
- `tests/test_layering.py` must stay green at every commit. Every new module under `src/veny/` needs its group added to `LAYERS` **in the same commit that creates it**, or `test_the_guard_covers_every_module_it_should` fails.
- When this plan is done, `rg -n 'options\.' src/veny/classify.py src/veny/environment.py src/veny/state.py` must return nothing, and none of the three may import `veny.cli`.
- Invoke tools through pixi's `python -m` form — bare binaries hit a shebang problem on macOS.
- `.git/hooks/pre-commit` is not installed. Run `pixi run pre-commit run --files <paths>` by hand before each commit.
- Do not use `git stash` or `git checkout <sha>` in the working tree. Use `git show <sha>:<path>` to read an old version, or `git archive` / `git worktree add` on a side path.
- Mutate the working tree in place for mutation testing, and restore with `git checkout -- <path>`. `pixi.toml`'s `[activation.env]` sets `PYTHONPATH = "src"`, which *overwrites* an inherited value, so a side copy silently tests `/workspace/src` and reports a false pass. Confirm which file was loaded with `pixi run python -c "import veny.cli as c; print(c.__file__)"`.
- Stage paths explicitly. A veny run leaves `.veny_custom_modules_*.pkl` and `logs/` behind; never `git add -A`. `.claude/` and `CLAUDE.md` are untracked and must not be added.
- **Do not touch anything phase 3d–3e owns.** No `verify.py`, `cache_search.py`, `last_used.py` or `pipeline.py`. Specifically, these stay in `cli.py` in this phase and moving them is out of scope: `interpreter_tag`, `venv_python_for`, `installed_state_in_venv`, `_VERSION_PROBE_CODE`, `check_packages_in_venv`, `run_import_check_in_venv`, `source_import_names`, `warn_about_system_packages`, `list_packages`, `get_all_imports`, `stayed_out_dir`, `setup_virtualenv`, `verify_and_repair_imports`. No `--full` deletion. No `Options` drain beyond the five fields Task 4 names.
- `src/veny/analysis/` is not touched by this plan at all. PROGRESS records a deferred cleanup in `analysis/scan.py` (a function-local `from collections import deque` beside a module-level `import collections` used only for an annotation) conditioned on "when 3c touches the file". **3c does not touch that file**, so the cleanup stays deferred; do not do it here.

**User decisions (already made):**
- Carried from 3a/3b: one target-architecture spec, then a plan per phase; phase 3 is a *sequence* of plans, and this is the third. `--full` is deleted in 3e, not here.
- Carried from 3b: injection is how a module satisfies the design's "takes neither `AliasIndex` nor `StdlibIndex`" wording when it genuinely needs the information (`is_stdlib: Callable[[str], bool]`, owner's decision 2026-08-16). This plan applies the same pattern to `classify`'s probe (`is_importable`).
- **Decided 2026-08-18, on this plan's three open points:**
  1. `Requirements` lives in a new `src/veny/state.py` with its own layer, not inside `classify.py` — so 3d's `verify.py` and `cache_search.py` import it without a same-layer exception.
  2. The probe venv is **kept and injected** as a `ContextManager`, not deleted. 3c stays behaviour-preserving; deleting the probe is a separate decision, and the measurement that informs it is recorded in PROGRESS by Task 6.
  3. `tests/test_split_imports.py`'s mypy errors are **left to 3d**. The ceiling stays 37; 36 is the predicted end state.

---

## Starting state (this plan may be executed in a different session — assume nothing)

- **Branch:** off `main` @ `dc1c3c4`. The branch's first commit is this plan and its `.tasks.json`. **No task in this plan has been implemented.**
- **Gates at `dc1c3c4`, all measured, not predicted:**
  - `pixi run test` → **296 passed**
  - `pixi run lint` → `All checks passed!`
  - `pixi run python -m ruff format --check .` → `40 files already formatted`
  - `pixi run typecheck` → `Found 37 errors in 5 files (checked 37 source files)`
- **Line counts at `dc1c3c4`** (`wc -l`): `cli.py` **2,626**; `analysis/imports.py` 683; `analysis/scan.py` 347; `analysis/custom_modules.py` 274; `analysis/literals.py` 229; `analysis/call_graph.py` 177; `analysis/scan_state.py` 30; `settings.py` 23; `tests/test_split_imports.py` 1,510. Every `cli.py` line number in this plan is as of `dc1c3c4`.
- Read `PROGRESS.md` first, all of it. Its Gotchas section carries traps this plan does not repeat.

---

## What this plan measured, and what you must measure

Plan 3b's text was wrong in six places — attributes that did not exist, symbols called internal that still had callers, a global constraint that forbade an edit one of its own tasks required. Every one was caught by an implementer refusing to guess; none by a test. So this plan splits its claims explicitly.

**Measured while writing this plan, by executing code at `dc1c3c4`. You may build on these, but any one that contradicts what you see is a stop-and-report, not something to adjust around.**

| Claim | How it was measured |
|---|---|
| `cli.py` symbol line spans (table in "File Structure") | `ast.parse` over `src/veny/cli.py`, `lineno`/`end_lineno` per top-level def |
| classify's five symbols total **178** lines; environment's eight total **230** — not the design's ~350 + ~350 | same AST pass, summed |
| Every in-repo caller of every symbol this plan moves (see "Call sites") | AST `ast.Name` walk attributing each reference to its enclosing top-level def, plus `rg` over `tests/` |
| `all_imports` is stdlib-free by construction when it reaches `split_imports` | `analysis/scan.py:288-291` and `:108-110` `continue` past `is_stdlib(name)` before any `all_imports.add` |
| In a bare `uv venv`, the only names that import but are **not** in `sys.stdlib_module_names` are `test`, `_virtualenv` (uv's own `.pth` shim) and equivalents. `yaml`, `numpy`, `requests`, `pip`, `setuptools`, `pkg_resources`, `_distutils_hack`, `cgi`, `cv2`, `sklearn`, `emmykit` all fail | built a real `uv venv` at `/tmp/probevenv` against `shutil.which("python3")` and ran `import_module` over that list |
| A hand-built wheel (zip + `dist-info`) installs offline through real `uv pip install`, imports, uninstalls, and then fails to import — **with no `--no-index`/`--offline` flags needed**, verified again under `UV_OFFLINE=1` | ran it end to end at `/tmp/wheeltest` |
| `options.total_imports == len(options.all_imports)` holds exactly on exit from `split_imports` (the `len()` is taken after the `--reqs` union, and `all_imports` is not touched again) | read `cli.py:1303-1316` and `1389-1395`; `rg` found no other writer |
| `options.installed_imports` has no production reader — its only read in the tree is `tests/test_split_imports.py:422` | `rg -n 'installed_imports'` over `src/` and `tests/` |
| All 10 of `cli.py`'s mypy errors live in `main()` (lines 428-676) and `load_last_used_options` (2194) — **none** in any symbol this plan moves | `pixi run typecheck` output cross-referenced against the AST span table |
| 21 of `tests/test_split_imports.py`'s 22 mypy errors belong to `resolve_and_verify` / `check_packages_in_venv` / the `AliasIndex` fakes — 3d's territory. Exactly one (line 531, `test_only_genuinely_uninstalled_imports_are_resolved`) is in 3c's blast radius | same cross-reference, attributing each error line to its enclosing test function |

**You must measure these yourself. This plan deliberately states no value for them.**

1. Every expected value in every characterization test in Tasks 1 and 3. Obtain them by running the code at the branch point, not by predicting them and not by copying a number out of this plan's prose.
2. The mypy count after each task (`pixi run typecheck 2>&1 | tail -1`), and — if it moves at all — which file moved, per `pixi run typecheck 2>&1 | grep -E '^[^ ]+\.py:' | sed 's/:.*//' | sort | uniq -c`.
3. Whether `parse_extra_requirements`' new return type is assignable to `Options.extra_requirements`. That attribute is declared `dict[str, str | None]` at `cli.py:158`; `dict` is invariant in mypy, so returning `dict[str, str]` and assigning it **will** add an error. Pick the annotation that keeps the ceiling and say which you picked.
4. The exact suite count after each task. This plan predicts counts; if yours differs, report the difference rather than editing the plan's number to match.

---

## Three things this plan settles that the design did not

Recorded here rather than silently worked around. All three come from measuring the tree at `dc1c3c4`.

1. **The design's "`classify.py` is handed ... a `StdlibIndex`" is not what the code needs.** `split_imports`' only standard-library input is `stdlib_index.PYTHON2_ONLY`, a module-level `Final[frozenset[str]]` at `stdlib_index.py:187`, consumed by `_compute_bad_imports`. No `StdlibIndex` *instance* is involved. `classify.py` therefore imports `stdlib_index` for that constant and takes no index object. (`interpreter_tag` is the function that reads `options.stdlib`, and it stays in `cli.py` for 3d.)

2. **"This is where `split_imports` stops needing a temporary virtual environment" is not achieved by this plan, and the plan does not pretend otherwise.** What the probe venv actually decides was measured: `all_imports` is stdlib-free by the time it reaches `split_imports`, and a bare `uv venv` can import nothing third-party, so the probe's only reachable "YES - installed" answers are names importable from a bare interpreter yet absent from `sys.stdlib_module_names` — measured on this machine: `test` and `_virtualenv`. Deleting the probe is therefore a small but real, user-visible behaviour change (a script importing `test` would go from silently "installed" to being sent to PyPI, where a package named `test` exists), and it needs its own decision about whether `test` belongs in `known_bad_imports`. **This plan keeps the probe and injects it** as `is_importable: ContextManager[Callable[[str], bool]]`, which is what actually delivers the design's stated payoff — `classify` becomes unit-testable without a venv — while leaving behaviour bit-identical. The measurement above is recorded in PROGRESS by Task 6 so whoever finally deletes the probe deletes it knowingly.

3. **The design's `Requirements` field list is short by one.** It lists `installed, uninstalled, bad, seen_stdlib, extra_requirements`. But the post-filter `all_imports` — `(all_imports - bad) ∪ extra_requirements.keys()` when `--reqs` — is read by three consumers outside `split_imports` (`source_import_names` at `cli.py:1168`, `list_packages`' logging at `1467`, and via `options.all_imports` on the `check_venv_dir` path), and it is **not** derivable from `installed ∪ uninstalled`, because a custom module lands in neither set. `Requirements` carries it as `all_imports`. `total_imports` is not a field — it is `len(all_imports)`, exactly as the design says, and that equality was measured to hold on exit today.

## Why the `ImportScan` bridge is not touched, and what replaces the risk

PROGRESS is emphatic that the `ImportScan` bridge in `find_imports_in_script` (`cli.py:687-732`) must be retired in one commit if it is touched at all, because it hands the scanner the seven live objects `Options` holds and relies on in-place mutation with **no copy-back** — safe only because it is total. A partial migration is where a copy-back regression hides, and `dbf013c` proved it survives a green suite and a live run.

**This plan does not touch that bridge**, and the reason is worth stating precisely rather than asserting:

- `classify` reads exactly two of the seven fields — `all_imports` and `custom_modules` — and reads them only. It never writes through the `ImportScan` it is handed. So it adds no second mutation path to the bridge.
- Everything `classify` produces leaves through its return value. `cli.py`'s adapter then performs **one total copy-back of five `Options` fields at one call site**: `all_imports`, `bad_imports`, `installed_imports`, `uninstalled_imports`, `total_imports`. Those five are the complete set `split_imports` writes today (measured — see the table above); there is no sixth.
- The bridge's remaining consumers (`list_packages`, `get_all_imports`, `warn_about_system_packages`, and `main()`'s `samedir_files`/`subfolders` reporting) are 3e's `pipeline.py`, and they are untouched here. Retiring the bridge means moving all of them, which is 3e's job, not a partial step this plan can take safely.

Task 4's acceptance criteria pin the copy-back's totality with an executable check, not with prose.

## The mypy ceiling

37 errors, in 5 files. Measured per-file at `dc1c3c4`:

| File | Errors |
|---|---|
| `tests/test_split_imports.py` | 22 |
| `src/veny/cli.py` | 10 |
| `src/veny/analysis/imports.py` | 3 |
| `src/veny/analysis/literals.py` | 1 |
| `src/veny/analysis/call_graph.py` | 1 |

**Decision: 3c does not clean up `tests/test_split_imports.py`, and this is deliberate rather than an oversight.** 21 of its 22 errors are attached to `resolve_and_verify`, `check_packages_in_venv` and the `_RecordingIndex`/`_CountingIndex`/`_live_index` fakes — that is `verify.py`, which phase 3d extracts and whose tests 3d will rewrite. Fixing them here means editing tests that are about to be rewritten, and it inflates 3c's diff with changes no reviewer of 3c can judge.

Exactly one is in 3c's blast radius: line 531, inside `test_only_genuinely_uninstalled_imports_are_resolved`, which is a `split_imports` test and therefore moves to `tests/test_classify.py` in Task 4. **It must be annotated when it moves**, because Task 4's gate is that the new files contribute zero errors.

Consequently the ceiling arithmetic for this plan is:

- `cli.py`'s 10 errors cannot fall — none of them is in a symbol that moves. Expect 10 throughout.
- `tests/test_split_imports.py` goes 22 → 21 when the one test moves out.
- `src/veny/environment.py`, `src/veny/classify.py`, `src/veny/state.py`, `tests/test_environment.py`, `tests/test_classify.py` must each contribute **zero**.
- Expected end state: **36 errors in 5 files**. The gate is still "≤ 37"; 36 is what this plan predicts, and a rise above 37 is a stop-and-report.

---

## File Structure

Line spans are as of `dc1c3c4`, measured by AST. They shift as edits are applied, so **work bottom-up within each task and locate code by symbol name, never by line number alone.**

| File | Responsibility | Change |
|---|---|---|
| `tests/test_environment.py` | Characterizes the uv boundary before it moves, including one live offline install/uninstall. | Create (Task 1) |
| `src/veny/environment.py` | The only module that invokes `uv`. | Create (Task 2, ~230 lines moved) |
| `tests/test_classify.py` | Characterizes classification before it moves; becomes classify's own suite. | Create (Task 3) |
| `src/veny/state.py` | `Requirements`, the frozen product of classification. | Create (Task 4) |
| `src/veny/classify.py` | `split_imports`, `add_dependencies`, `resolve_records`, `requirement_records`, `_compute_bad_imports`. | Create (Task 4, ~178 lines moved) |
| `src/veny/cli.py` | Everything else; keeps thin adapters for both extractions. | Modify (Tasks 2, 4) |
| `tests/test_layering.py` | `LAYERS` gains two entries. | Modify (Tasks 2, 4) |
| `tests/test_uv_backend.py` | Call sites follow the moved symbols. | Modify (Task 2) |
| `tests/test_venv_naming.py` | `venv_build_interpreter` call sites follow. | Modify (Task 2) |
| `tests/test_split_imports.py` | Loses the classify-owned tests; keeps everything 3d owns. | Modify (Tasks 2, 4) |
| `README.md` | Project-structure block. | Modify (Task 6) |
| `PROGRESS.md` | Project ledger. | Modify (Task 6) |

### Symbols moving to `environment.py` (measured spans, 230 lines)

| Symbol | `cli.py` span | Lines |
|---|---|---|
| `uv_binary` | 47-78 | 32 |
| `create_venv` | 81-101 | 21 |
| `venv_build_interpreter` | 1517-1556 | 40 |
| `parse_extra_requirements` | 1576-1605 | 30 |
| `write_requirements_file_with_extras` | 1608-1634 | 27 |
| `run_uv_pip` | 1637-1677 | 41 |
| `install_into_venv` | 1680-1703 | 24 |
| `uninstall_from_venv` | 1706-1720 | 15 |

`interpreter_tag` (1559-1573, 15 lines) sits between two of these and **does not move**: it invokes no uv, it reads `options.stdlib`, and four of its five callers (`cache_candidates`, `check_venv_dir`, `manifest_for`, `record_venv_state`) are `cache_search.py`, which is 3d's. It belongs with them.

### Symbols moving to `classify.py` (measured spans, 178 lines)

| Symbol | `cli.py` span | Lines |
|---|---|---|
| `resolve_records` | 735-754 | 20 |
| `requirement_records` | 757-769 | 13 |
| `add_dependencies` | 772-805 | 34 |
| `_compute_bad_imports` | 1266-1281 | 16 |
| `split_imports` | 1301-1395 | 95 |

`warn_about_system_packages` (1284-1298) sits between two of these and **does not move**: the design assigns it to `pipeline.py`, and it is called from `main()`'s reporting block (`cli.py:562`), not from classification.

### Call sites (measured — this is the complete list)

In `src/veny/cli.py`:

| Moved symbol | Called from |
|---|---|
| `uv_binary` | `create_venv`, `run_uv_pip` (both move with it) |
| `create_venv` | `setup_virtualenv`, `split_imports` |
| `venv_build_interpreter` | `manifest_for`, `setup_virtualenv`, `split_imports` |
| `parse_extra_requirements` | `main` |
| `write_requirements_file_with_extras` | `setup_virtualenv`, `verify_and_repair_imports` |
| `run_uv_pip` | `install_into_venv`, `uninstall_from_venv` (both move), `setup_virtualenv` |
| `install_into_venv` | `repair_unsatisfied_import` |
| `uninstall_from_venv` | `repair_unsatisfied_import` |
| `resolve_records` | `add_dependencies` (moves with it) |
| `requirement_records` | `split_imports` (moves with it) |
| `add_dependencies` | `split_imports` (moves with it) |
| `_compute_bad_imports` | `split_imports` (moves with it) |
| `split_imports` | `list_packages` |

In `tests/`: `tests/test_uv_backend.py` (`uv_binary`, `create_venv`, `venv_build_interpreter`, `write_requirements_file_with_extras`, `run_uv_pip`), `tests/test_venv_naming.py` (`venv_build_interpreter`), `tests/test_split_imports.py` (`uv_binary`, `create_venv`, `write_requirements_file_with_extras`, `install_into_venv`, `uninstall_from_venv`, `split_imports`, `resolve_records`, `requirement_records`, `_compute_bad_imports`).

**Note the monkeypatch hazard.** Several tests patch these symbols *on the `cli` module* (`monkeypatch.setattr(cli, "run_uv_pip", ...)`, `monkeypatch.setattr(cli, "uv_binary", ...)`). Once a symbol lives in `environment.py` and `cli.py` calls it as `environment.run_uv_pip(...)`, patching `cli.run_uv_pip` silently patches nothing and the test exercises the real subprocess. Every such patch must be repointed at the `environment` module in the same commit as the move. Task 2 makes this an explicit acceptance criterion because it is the failure mode that would otherwise show up as a mysterious network call rather than as a red test.

### Layering

`tests/test_layering.py`'s `LAYERS` is a bottom-to-top list; a module may import strictly below its own layer, never its peers (absent a `SANCTIONED_EXCEPTIONS` entry) and never above. `classify.py` needs `alias_index` (for `AliasIndex` and `ResolvedImport`), `stdlib_index` (for `PYTHON2_ONLY`) and `analysis.scan_state` (for `ImportScan`), all of which are in layer index 2 today — so `classify` must sit above them. The end-state stack this plan installs:

```python
LAYERS: list[frozenset[str]] = [
    frozenset({"__init__"}),
    frozenset({"settings"}),
    frozenset({"analysis", "alias_index", "venv_cache", "stdlib_index",
               "pypi_client", "json_types"}),
    frozenset({"state"}),                     # new in Task 4
    frozenset({"classify", "environment"}),   # environment in Task 2, classify in Task 4
    frozenset({"cli"}),
]
```

`state.py` gets its own layer rather than joining `classify`/`environment` because `Requirements` annotates its members with `ResolvedImport`, so `state` imports `alias_index` — and `classify`, `verify` and `cache_search` all need to import `state` without a same-layer exception. Putting `Requirements` inside `classify.py` instead would force 3d's `verify.py` and `cache_search.py` to import a peer, which is exactly the kind of exception the guard exists to keep rare. Adding it now costs one ~35-line file and buys 3d and 3e a clean import.

---

### Task 1: Characterize the uv boundary, live

**Goal:** `environment.py`'s behaviour is pinned before a line of it moves — including one test that crosses the real `uv` boundary, because PROGRESS records three phase-2 regressions that a 264-test suite of stubs shipped past.

**Files:**
- Create: `tests/test_environment.py`

**What to write.** Tests go against the symbols where they live *today* (`veny.cli.*`); Task 2 repoints them mechanically. Use the `test-design` skill: for each test state the behaviour under test and a concrete bug that would make it fail, and obtain every expected value by running the code, never by predicting it.

Cover at least:

- [ ] **The live install/uninstall round trip.** Build a real `uv venv` in `tmp_path`, then drive the real `install_into_venv` and `uninstall_from_venv` against a wheel this test builds itself. **Measured while writing this plan:** a hand-built wheel (a zip carrying `pkg/__init__.py` plus a `pkg-VERSION.dist-info/` with `METADATA`, `WHEEL` and `RECORD`) installs through real `uv pip install` with **no** `--no-index` or `--offline` flag and no network — re-verified under `UV_OFFLINE=1` — imports inside the venv, uninstalls cleanly, and then fails to import. So this test needs no network and no marker, and belongs in the ordinary suite. Assert all four states: install returns `True`, the import succeeds in the venv, uninstall leaves no error, and the import then fails. A test that only asserts the argv would not have caught any of phase 2's three regressions.
- [ ] `run_uv_pip` returns `None` (and logs, rather than raising) when there is no venv interpreter.
- [ ] `run_uv_pip` builds `[uv, "pip", <verb>, "--python", <venv python>, *rest]` in that order. The `--python` flag's position matters: it precedes the package arguments.
- [ ] `install_into_venv` returns `False` on a non-zero uv return code instead of raising, and logs the stderr.
- [ ] `uninstall_from_venv` warns but does not raise on a non-zero return code.
- [ ] `parse_extra_requirements` over a fixture file: a bare name, a name with a specifier, a `#` comment line, a blank line, and leading/trailing whitespace. Measure what today's regex (`^\s*([A-Za-z0-9_\-\.]+)\s*(.*)$`) actually produces for each — do not predict it.
- [ ] `write_requirements_file_with_extras` writes pip names in sorted order, one per line, appending a specifier only where `extra_requirements` supplies a non-empty one. Include a record whose pip name is absent from `extra_requirements` and one whose specifier is empty.
- [ ] `venv_build_interpreter` falls back to the unresolved command **and warns** when `shutil.which` finds nothing (this branch is called out in PROGRESS as untested and believed practically dead).

Do **not** duplicate what `tests/test_uv_backend.py` already pins: `uv_binary`'s three resolution outcomes, the resolved-interpreter argv assertion, and the `create_venv`-before-requirements ordering are already covered there and stay there.

**Acceptance Criteria:**
- [ ] Every expected value obtained by running code at the branch point, not predicted
- [ ] The live test uses the real `uv` binary and a real venv, with no `subprocess` stubbing anywhere in it
- [ ] The live test passes with no network (verify by re-running it with `UV_OFFLINE=1` in the environment)
- [ ] No source file under `src/` is modified in this task
- [ ] `tests/test_environment.py` contributes zero mypy errors
- [ ] **Mutation check:** delete `run_uv_pip`'s `"--python", os.fspath(options.venv_python)` pair and watch a named test fail; restore it and watch it pass. Record which test.
- [ ] **Mutation check:** invert `install_into_venv`'s `if result.returncode != 0` and watch a named test fail. Record which test.

**Verify:** `pixi run python -m pytest tests/test_environment.py -v`, then `pixi run test` → 296 + (number of tests added). State the number.

---

### Task 2: Extract `src/veny/environment.py`

**Goal:** `uv` is invoked from exactly one module, and that module has never heard of `Options`.

**Files:**
- Create: `src/veny/environment.py`
- Modify: `src/veny/cli.py`, `tests/test_layering.py`, `tests/test_environment.py`, `tests/test_uv_backend.py`, `tests/test_venv_naming.py`, `tests/test_split_imports.py`

**Signatures.** Each function loses `options` and takes what it actually reads. These are the intended shapes; adjust only if the tree contradicts them, and say so if you do.

```python
def uv_binary() -> str: ...                                   # unchanged
def create_venv(target: str | os.PathLike[str], python: str = "") -> None: ...  # unchanged
def venv_build_interpreter(python_command: str) -> str: ...   # was options.python_command
def parse_extra_requirements(path: str | os.PathLike[str], *, rawlog: bool) -> dict[str, ...]: ...
def write_requirements_file_with_extras(
    requirements_file: str | os.PathLike[str],
    pip_names: Iterable[str],
    extra_requirements: Mapping[str, str | None],
) -> None: ...
def run_uv_pip(
    venv_python: str | os.PathLike[str] | None, *args: str
) -> subprocess.CompletedProcess[str] | None: ...
def install_into_venv(venv_python: str | os.PathLike[str] | None, pip_name: str) -> bool: ...
def uninstall_from_venv(venv_python: str | os.PathLike[str] | None, pip_name: str) -> None: ...
```

Notes that are not optional:

- `parse_extra_requirements` **returns** the dict instead of writing `options.extra_requirements`; `main()` assigns it. Its return annotation is one of the four things you must measure — `Options.extra_requirements` is declared `dict[str, str | None]` at `cli.py:158`, and mypy's dict invariance means a `dict[str, str]` return will add an error at the assignment. Pick the annotation that keeps the ceiling.
- `venv_build_interpreter`'s `python_command or sys.executable` fallback stays **inside** the function; the caller passes `options.python_command` unchanged. Moving the fallback to the call site would change behaviour at `manifest_for`, which is 3d's.
- `write_requirements_file_with_extras` takes an iterable of pip names, not records, so `environment.py` need not import `ResolvedImport`. Callers pass `(r.pip_name for r in options.uninstalled_imports)`. The sort stays inside the function, exactly as today. Its three `assert ... is not None` lines belong to `Options` and move to the call sites in `cli.py` (or are dropped where the caller already asserts) — do not silently delete a check.
- `run_uv_pip`'s `venv_python is None` branch and its log message are preserved verbatim; it is the reason every caller can treat a missing interpreter as "no result".

**In `cli.py`:** add `from . import environment`, delete the eight moved definitions, and repoint every call site listed in "Call sites" above. `main()` becomes `options.extra_requirements = environment.parse_extra_requirements(options.extra_requirements_file, rawlog=options.rawlog)`.

**Acceptance Criteria:**
- [ ] `src/veny/environment.py` exists and `rg -n 'options\.' src/veny/environment.py` returns nothing
- [ ] `environment.py` imports nothing from `veny.cli` (`tests/test_layering.py` proves it)
- [ ] `LAYERS` gains `frozenset({"environment"})` above the index layer, in this commit
- [ ] Every one of the eight symbols is gone from `cli.py` — `rg -n '^def (uv_binary|create_venv|venv_build_interpreter|parse_extra_requirements|write_requirements_file_with_extras|run_uv_pip|install_into_venv|uninstall_from_venv)\b' src/veny/cli.py` returns nothing
- [ ] **Every `monkeypatch.setattr(cli, "<moved symbol>", ...)` in `tests/` is repointed at the `environment` module.** Find them with `rg -n 'setattr\(\s*(cli|veny)\s*,\s*"(uv_binary|create_venv|venv_build_interpreter|run_uv_pip|install_into_venv|uninstall_from_venv|write_requirements_file_with_extras|parse_extra_requirements)"' tests/` and confirm that command returns nothing when the task is done. A missed patch does not fail loudly — it runs the real subprocess.
- [ ] Bodies moved verbatim. Diff each one against `git show dc1c3c4:src/veny/cli.py` and confirm the only differences are the parameter substitutions the signatures above require.
- [ ] `pixi run typecheck` ≤ 37, with `environment.py` and `tests/test_environment.py` at zero

**Verify:** `pixi run test` (same count as end of Task 1 — this task moves code, it does not add tests), `pixi run lint`, `pixi run python -m ruff format --check .`, `pixi run typecheck 2>&1 | tail -1`. Then a live end-to-end run: `pixi run veny --no-cache <a throwaway script importing yaml>` must build a venv, install, and print the script's output. Capture the output in the task report.

---

### Task 3: Characterize classification before it moves

**Goal:** The largest untested block in the codebase gets tests describing exactly what it does today, written against `cli.split_imports(options)` as it stands, before any interface changes.

**Files:**
- Create: `tests/test_classify.py`

Today's coverage of `split_imports` in `tests/test_split_imports.py` is four tests (`test_split_imports_wires_python2_table_end_to_end`, `test_split_imports_stores_both_names_on_the_record`, `test_split_imports_falls_back_to_the_import_name_when_nothing_resolves`, `test_split_imports_probe_venv_is_given_the_classified_interpreter`) plus three `_compute_bad_imports` unit tests and `test_only_genuinely_uninstalled_imports_are_resolved`. Whole branches are unpinned. Write tests for at least these, and stub the probe venv (patch `check_packages_in_venv`) so no test in this file builds one except where noted:

- [ ] **A custom module is classified as neither installed nor uninstalled.** An import name present in `options.custom_modules` must appear in neither set and must never be resolved through the alias index. Nothing pins this today, and it is the branch that makes `all_imports` a superset of `installed ∪ uninstalled` — the fact that forces `Requirements.all_imports` to exist.
- [ ] **The zero-import early return builds no venv.** With `all_imports` empty and `--reqs` off, `split_imports` must return before `create_venv` is reached. Assert it by patching `create_venv` with something that fails the test if called. This branch is load-bearing for Task 4's context-manager design and nothing pins it today.
- [ ] **`--reqs` folds requirement keys into `all_imports` before the count is taken**, so a run with zero source imports but a non-empty requirements file *does* build the probe venv.
- [ ] **`--reqs` records are unioned into `uninstalled_imports` after the loop**, with `import_name == pip_name`.
- [ ] **`add_dependencies` expands nested dependencies to a fixed point.** Build an `also_needs` chain of at least three levels (a → b, b → c) and pin that all three arrive. The `while added` loop is unpinned today.
- [ ] **`add_dependencies` resolves dependency names through the alias index**, so a dependency's pip name is the resolved one, not the bare name.
- [ ] **Bad imports are removed from `all_imports` and never reach the probe or the resolver.**
- [ ] **On exit, `options.total_imports == len(options.all_imports)`.** This is the equality Task 4 turns into a property; pin it here first.

**Acceptance Criteria:**
- [ ] Every expected value obtained by running the code, not predicted
- [ ] No source file under `src/` is modified in this task
- [ ] Each test names, in its docstring, the concrete bug that would make it fail
- [ ] `tests/test_classify.py` contributes zero mypy errors
- [ ] **Mutation check, three of them, each recorded with the test that caught it:** (a) delete the `if imp in options.custom_modules.keys()` branch; (b) delete the `if not options.total_imports: return` early return; (c) delete `add_dependencies`' `while added` loop body. Each must turn a named test red, and restoring it must turn it green with `git diff` empty.

**Verify:** `pixi run python -m pytest tests/test_classify.py -v`, then `pixi run test`. State the count.

---

### Task 4: Introduce `Requirements` and extract `src/veny/classify.py`

**Goal:** Classification is a value-returning function over an `ImportScan`, and `cli.py` holds one total adapter instead of fifteen scattered writes.

**Files:**
- Create: `src/veny/state.py`, `src/veny/classify.py`
- Modify: `src/veny/cli.py`, `tests/test_layering.py`, `tests/test_classify.py`, `tests/test_split_imports.py`

**`src/veny/state.py`:**

```python
@dataclass(frozen=True)
class Requirements:
    """What classification decided about one run's imports."""

    all_imports: frozenset[str]          # post-bad-filter, post---reqs-union
    bad: frozenset[str]
    installed: frozenset[ResolvedImport]
    uninstalled: frozenset[ResolvedImport]
    seen_stdlib: frozenset[str]          # pass-through from the scan, for 3e's reporting
    extra_requirements: Mapping[str, str | None]   # pass-through input, for 3d's manifest

    @property
    def total_imports(self) -> int:
        return len(self.all_imports)
```

`seen_stdlib` and `extra_requirements` are pass-throughs, not products — say so in the docstring. They are there because the design's phase-4 field list names them and because 3d/3e read them; `classify` neither computes nor changes them.

**`src/veny/classify.py`:**

```python
def split_imports(
    scan: ImportScan,
    *,
    aliases: alias_index.AliasIndex,
    known_bad_imports: set[str],
    also_needs: Mapping[str, list[str]],
    extra_requirements: Mapping[str, str | None],
    use_reqs: bool,
    probe: AbstractContextManager[Callable[[str], bool]],
    rawlog: bool,
) -> Requirements: ...

def add_dependencies(
    uninstalled: set[ResolvedImport],
    *,
    also_needs: Mapping[str, list[str]],
    aliases: alias_index.AliasIndex,
    rawlog: bool,
) -> set[ResolvedImport]: ...

def resolve_records(
    aliases: alias_index.AliasIndex, import_names: Iterable[str]
) -> set[ResolvedImport]: ...

def requirement_records(pip_names: Iterable[str]) -> set[ResolvedImport]: ...   # unchanged

def _compute_bad_imports(
    all_imports: set[str], known_bad: set[str], py2_only: frozenset[str]
) -> set[str]: ...                                                             # unchanged
```

**The `probe` parameter is the heart of this task.** Today `split_imports` opens `tempfile.TemporaryDirectory()`, calls `create_venv(venv_dir, venv_build_interpreter(options))`, and calls `check_packages_in_venv(options, record=..., venv_dir=venv_dir)` per import — all *after* the zero-import early return. A plain `Callable` parameter would force the caller to build the venv unconditionally, which builds one on every zero-import run and is a real behaviour change. A context manager preserves the structure exactly: `classify` does `with probe as is_importable:` at the same point in the function where `with tempfile.TemporaryDirectory()` sits today, so a zero-import run still never enters it.

`cli.py` supplies it:

```python
@contextlib.contextmanager
def _probe_venv(options: Options) -> Iterator[Callable[[str], bool]]:
    with tempfile.TemporaryDirectory() as venv_dir:
        environment.create_venv(
            venv_dir, environment.venv_build_interpreter(options.python_command)
        )

        def is_importable(import_name: str) -> bool:
            return check_packages_in_venv(
                options,
                record=ResolvedImport(import_name=import_name, pip_name=import_name),
                venv_dir=venv_dir,
            )

        yield is_importable
```

**The adapter in `cli.py`** replaces the moved `split_imports` body and is the *only* place `Requirements` is copied back onto `Options`:

```python
def split_imports(options: Options) -> None:
    """Adapter: run classification and copy its product back onto Options.

    The copy-back is total -- these five fields are the complete set the old
    split_imports wrote. See the plan's "Why the ImportScan bridge is not
    touched" section: classify reads the scan and writes nothing through it,
    so nothing here depends on in-place mutation.
    """
    scan = ImportScan(all_imports=options.all_imports, custom_modules=options.custom_modules, ...)
    result = classify.split_imports(scan, ..., probe=_probe_venv(options), ...)
    options.all_imports = set(result.all_imports)
    options.bad_imports = set(result.bad)
    options.installed_imports = set(result.installed)
    options.uninstalled_imports = set(result.uninstalled)
    options.total_imports = result.total_imports
```

The copy-back converts each `frozenset` back to a `set`, because downstream code mutates `options.uninstalled_imports` (`verify_and_repair_imports`, 3d's territory) and must keep working untouched.

**Test migration.** Move the classify-owned tests out of `tests/test_split_imports.py` into `tests/test_classify.py` and repoint them at the new interface: `test_python2_name_is_classified_bad`, `test_leading_underscore_name_is_classified_bad`, `test_ordinary_import_is_not_classified_bad`, `test_seaborn_tkinter_and_msvcrt_are_no_longer_blocked`, `test_split_imports_wires_python2_table_end_to_end`, `test_split_imports_stores_both_names_on_the_record`, `test_split_imports_falls_back_to_the_import_name_when_nothing_resolves`, `test_split_imports_probe_venv_is_given_the_classified_interpreter`, `test_only_genuinely_uninstalled_imports_are_resolved`. **Their assertions do not change** — only their call sites and, where a test asserted on `options.*`, the object those assertions read. Everything else in `tests/test_split_imports.py` stays where it is; it belongs to 3d.

`test_only_genuinely_uninstalled_imports_are_resolved` carries one of `test_split_imports.py`'s 22 mypy errors (line 531, `_CountingIndex` assigned to an `AliasIndex`-typed variable). Annotate it as it moves so `tests/test_classify.py` lands at zero.

**Acceptance Criteria:**
- [ ] `rg -n 'options\.' src/veny/classify.py src/veny/state.py` returns nothing
- [ ] Neither module imports `veny.cli`; `LAYERS` gains `frozenset({"state"})` and `classify` joins `environment`'s layer, in this commit
- [ ] **The copy-back is provably total.** Add an executable check, in the spirit of `test_analysis_never_rebinds_an_importscan_field`: walk `cli.split_imports`' AST and assert the set of `options.<attr>` store targets is exactly `{all_imports, bad_imports, installed_imports, uninstalled_imports, total_imports}`. This is the guard that would have caught `dbf013c`'s class of bug; a prose claim is not enough here.
- [ ] A zero-import run still builds no probe venv (the Task 3 test proves it, unchanged)
- [ ] `Requirements.total_imports` equals `len(all_imports)` (the Task 3 test proves it, unchanged)
- [ ] `pixi run typecheck` ≤ 37, with `classify.py`, `state.py` and `tests/test_classify.py` at zero, and `tests/test_split_imports.py` at 21
- [ ] Bodies moved verbatim apart from the parameter substitutions above — diff each against `git show dc1c3c4:src/veny/cli.py`
- [ ] **Mutation check:** delete one of the five copy-back assignments and confirm the AST guard fails. Restore it.

**Verify:** `pixi run test` (same count as end of Task 3 — tests move, none are added or dropped; if the count changes, stop and explain), `pixi run lint`, `pixi run python -m ruff format --check .`, `pixi run typecheck 2>&1 | tail -1`.

---

### Task 5: Differential corpus verification

**Goal:** Prove classification and the uv command surface are unchanged by comparing old and new code's *output*, not by observing that a suite is green. PROGRESS records this as the only technique in this program that caught a regression before a fix round rather than after; it is read-only, needs no worktree or checkout, and takes under a minute.

**Files:** none under `src/` or `tests/`. Scratch scripts live outside the repo (`/tmp/…`) and are not committed; their output goes in the task report.

**Method.**

```bash
rm -rf /tmp/veny-old && mkdir -p /tmp/veny-old
git archive dc1c3c4 src/veny | tar -x -C /tmp/veny-old
```

Note `dc1c3c4` is the branch point. Do **not** `git checkout` it — CLAUDE.md forbids investigative checkouts in the working tree, and PROGRESS records a session where that left a mixed tree.

Write one driver script that takes a `sys.path` root as its argument, imports `veny.cli` from it in a **fresh interpreter**, and for each corpus script:

1. Builds an `Options` with an **offline** `AliasIndex` (`build(offline=True)`, so no PyPI request makes the two runs differ for network reasons) and a fixed `python_command`.
2. Runs `list_packages(options)` — which is what calls `split_imports`.
3. Prints one JSON object with sorted, deterministic values: `all_imports`, `bad_imports`, `total_imports`, and `installed_imports`/`uninstalled_imports` as sorted `[import_name, pip_name]` pairs.

Run it twice — `PYTHONPATH` is not usable for this (`pixi.toml`'s `[activation.env]` overwrites it), so pass the root as an argument and `sys.path.insert(0, root)` inside the driver, and confirm which file was loaded by printing `veny.cli.__file__` on the first line of each run.

**Corpus** — at least eight scripts, and it must include one of each of these, because each exercises a branch the extraction touched:

- a script importing only third-party names
- a script importing only stdlib names (drives the empty-`all_imports` early return)
- a script importing a local module in the same directory (drives the custom-module branch)
- a script importing a name in `known_bad_imports` and one starting with `_`
- a script whose imports are reached only through a function call (drives the call graph into `all_imports`)
- a directory (not a single file), to drive `get_all_imports`' repeated scanner calls
- a run with `--reqs` against a fixture `extra_requirements.txt` carrying a bare name, a pinned name and a comment
- a script importing `test` — the one name the probe venv was measured to answer "installed" for, and therefore the single most likely place for a probe regression to show

Then diff:

```bash
diff <(pixi run python /tmp/diffdrive.py /tmp/veny-old/src) \
     <(pixi run python /tmp/diffdrive.py /workspace/src)
```

**Second differential, for `environment.py`:** with `subprocess.check_call` and `subprocess.run` captured (not executed), record every argv the two trees build for `create_venv`, `run_uv_pip`, `install_into_venv` and `uninstall_from_venv` over the same corpus, and diff those lists. This is what pins that the `--python` flag, its position, and the resolved interpreter path are unchanged.

**Acceptance Criteria:**
- [ ] Both diffs are empty, and the empty diff is shown in the task report alongside the two `veny.cli.__file__` lines proving the two runs loaded different files
- [ ] The corpus covers all eight cases above; the report lists them
- [ ] **The check is proven able to fail.** Introduce one deliberate one-line change in the new tree (for example, drop the `--reqs` union in `classify.split_imports`), re-run, show the non-empty diff, then revert it and show `git diff` empty and the diff empty again. A differential check nobody has seen fail is worth as little as a test that cannot fail.
- [ ] No file in the repository is modified by this task

**Verify:** `git status --short` shows no tracked-file changes; `pixi run test` unchanged.

---

### Task 6: Run the gates, update README and PROGRESS

**Goal:** Close the phase with measured gates and a ledger that records what was learned, including the things this phase deliberately did not do.

**Files:**
- Modify: `README.md`, `PROGRESS.md`

**Gates** — run all of them and record the actual output, not a prediction:

- [ ] `pixi run test`
- [ ] `pixi run lint` → zero
- [ ] `pixi run python -m ruff format --check .` → every file formatted
- [ ] `pixi run typecheck 2>&1 | tail -1` → ≤ 37 (36 predicted), with the per-file breakdown
- [ ] `pixi run smoke` → green, or explicitly recorded as skipped for lack of network
- [ ] `wc -l src/veny/cli.py src/veny/classify.py src/veny/environment.py src/veny/state.py`
- [ ] A live run: `pixi run veny --no-cache` against a throwaway script importing a real third-party package, printing the script's output — the acceptance criterion PROGRESS demands of any plan touching subprocess invocation

**README:** the project-structure block at `README.md:100-130` gains `classify.py`, `environment.py` and `state.py`, and `cli.py`'s comment is updated — it currently says cli.py "builds the ImportScan/Settings analysis/ works from and copies results back onto Options", which is still true but now also covers the classification copy-back.

**PROGRESS:** update **Current work** (phase-3 table: 3c executed, its modules and measured line counts; the "Next action" line pointing at 3d), and add to the other sections:

- **Gotchas / Deferred:** the measured fact that the probe venv's only reachable positive answers are names importable from a bare interpreter but absent from `sys.stdlib_module_names` — measured as `test` and `_virtualenv` on this machine — and that deleting it is therefore a small, user-visible behaviour change needing its own decision about `known_bad_imports`. Whoever removes the probe should remove it knowing this, not discover it.
- **Deferred:** `tests/test_split_imports.py` had 22 mypy errors before 3c and retains 21 after it (the twenty-second moved to `tests/test_classify.py` with its test and was annotated there). All 21 belong to `resolve_and_verify` / `check_packages_in_venv` / the `AliasIndex` fakes — i.e. 3d's `verify.py`. 3d is where they get cleaned up, alongside the tests being rewritten. This was a decision taken during 3c's planning, not an oversight found afterwards.
- **Deferred:** `Requirements.seen_stdlib` and `Requirements.extra_requirements` are pass-throughs that `classify` neither computes nor changes. 3e should decide whether they stay on `Requirements` or move once `pipeline.py` owns sequencing.
- **Design amendments 3c records** (a fourth, fifth and sixth, after 3b's three): `classify` needs `stdlib_index.PYTHON2_ONLY`, not a `StdlibIndex` instance; `Requirements` needs an `all_imports` field the design's list omits; and "`split_imports` stops needing a temporary virtual environment" is not delivered by 3c — the venv is injected rather than removed, and the reason is recorded above.
- **Gotcha, if it bit you:** a `monkeypatch.setattr(cli, "<moved symbol>", ...)` that silently patches nothing after a move, running the real subprocess instead of failing.
- Anything Task 5's differential check found. If it found nothing, record that too — the runs and the empty diff are the evidence.

**Acceptance Criteria:**
- [ ] Every gate above run and its real output recorded
- [ ] README's project-structure block matches the tree (check it against `fd -e py . src/veny`)
- [ ] PROGRESS's "Next action" points at plan 3d and states that no branch exists for it
- [ ] `.tasks.json` marked complete
- [ ] Nothing left uncommitted

**Verify:** `git status --short` clean apart from the untracked `.claude/` and `CLAUDE.md`; `git log --oneline` shows one commit per task.

---

## Rollback

Every task is one commit. Revert with `git revert <sha>` in reverse order; nothing in this plan writes outside the repository except the throwaway venvs and corpus scripts in `/tmp`, and nothing changes on-disk formats users depend on (`veny_manifest.json`, the alias cache and the custom-module pickles are untouched). If the branch is abandoned entirely, `main` @ `dc1c3c4` is unaffected — no task in this plan pushes or merges.
