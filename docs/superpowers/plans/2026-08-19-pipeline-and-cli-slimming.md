# Phase 3e: `pipeline.py` and the `cli.py` Slimming — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract `pipeline.py` — the module that owns the run's sequencing —
out of `src/veny/cli.py`, leaving `cli.py` with argparse, the transitional
`Options` re-export and an exit-status-mapping `main()`; delete `--full`; take
back exit ownership from `environment.py`; and fix the two reachable
`AssertionError` crashes that die with the control flow that produced them.

**Architecture:** Two new top-level modules under `src/veny/`.
`run_options.py` is the transitional home of the `Options` class, moved out of
`cli.py` so that `pipeline.py` can be handed an `Options` without importing the
module above it; phase 4 deletes it outright when the frozen dataclasses land.
`pipeline.py` sits directly below `cli.py` and above every module 3a–3d
extracted: it owns the analysis driver (`list_packages` and everything under
it), the user-facing reporting block currently inlined in `main()`, venv
acquisition (`setup_virtualenv`, the cache search, the `failed-` rename, the
last-used JSON write) and the three script-launch sites. `cli.py` calls
`pipeline.run(options)` and turns what it returns — or what it raises — into an
exit status.

**Tech Stack:** Python 3.12/3.13, pixi, pytest, ruff, mypy, `uv` (through
`environment.py` only), emmykit ≥ 0.4.0.

**Global Constraints:**

1. **Behaviour-preserving, with exactly six sanctioned exceptions**, each
   listed under "What this plan settles that the design did not" and each
   landing in its own task: the `--full` deletion (Task 5), the no-script
   usage exit (Task 5), the in-virtualenv branch fix (Task 6), the
   `uv_binary` / `create_venv` exit-ownership change (Task 7), and the two
   tail-order deviations Task 4 records (`--justprint` and `--blank-slate`
   now reach `logging.shutdown()`; `--blank-slate` now reaches
   `ek.print_all_errors`). Everything else must be a move plus an argument
   list.
2. **Tests before moves.** Task 2 characterizes `main()`'s branches in
   process, at the interface they will have *after* the move, before any code
   moves. This is the root-cause fix for the finding that dominates 3d's
   ledger: 27 of that phase's 104 mis-wirable arguments were in `main()`, for
   the single reason that nothing in the suite ever called `main()`.
3. **Call through the module object** — `pipeline.run(...)`,
   `verify.foo(...)`, `environment.foo(...)`. Never `from .pipeline import
   run`. That is what keeps `monkeypatch.setattr` working, and it is the
   convention 3b, 3c and 3d all established.
4. **STANDING CHECK (PROGRESS Gotchas, added by 3c's review, re-measured by
   3d's):** after moving a symbol, mutate *every argument* at *every* new call
   site and confirm a **named** test fails. Booleans get **both** values
   substituted — `rawlog=True` left 16 of 17 sites green on 3d's branch
   because the pinning tests were argument spies asserting the value they were
   handed. Arguments with no natural empty value get a wrong-but-type-correct
   value (`Path("/tmp/wrong-…")`, `"wrongname"`, `"9.9"`), recorded in the
   table. Task 8 runs this mechanically.
5. **Never `git stash`, never `git checkout -- <path>`, never `git checkout
   <sha>`.** To mutate a file for a mutation check, copy it into the scratch
   directory first and restore from the copy. `git checkout --` cost 3c's
   Task 4 an entire session of edits; `git stash` is unsafe here because a
   formatter pre-commit hook rewriting files mid-stash blocks the pop. To read
   another commit's file, use `git show <sha>:<path>`; to check one out, use
   `git worktree add`.
6. **`PYTHONHASHSEED=0` goes inside the differential driver script**, not in
   the invocation, and diagnostics go to **stderr** so they never become a
   third diff hunk.
7. **Explicit paths in `git add`.** Never `git add -u` — that is how 3d's
   `c0510da` swept an unrelated `tasks.json` edit into a refactor commit.
8. **Gates that must hold at the end of every task:** `pixi run test` green,
   `pixi run lint` zero, `pixi run python -m ruff format --check .` all files
   formatted, `pixi run typecheck` **≤ 33 errors** (the current ceiling — it
   may fall, it must not rise), and `pixi run smoke` green at the tasks that
   touch the uv boundary (Tasks 7 and 10).
9. **`pixi run pre-commit run --files <paths>` before every commit.**
   `pre-commit` exists only inside the pixi environment.

**User decisions (already made):**

- **3e is extraction only; `Options` survives it.** The frozen
  `Settings`/`Target`/`VenvHandle`/`LastUsed` dataclasses and the persistence
  change remain phase 4. 3e moves the class to its own module so `pipeline.py`
  can take it, and changes nothing about what it carries.
- **Exit ownership comes back to `cli.py` through a typed veny exception.**
  `environment.uv_binary` raises `environment.UvUnavailable` instead of
  `SystemExit`; `create_venv` returns `bool` instead of letting
  `CalledProcessError` escape; `pipeline` never catches either; `main()`
  catches and maps to exit 1 with the same message on the same stream.
- **Verification is all three gates:** the standing check over every new call
  site, in-process driver tests for `main()` and each `pipeline` entry point,
  and a committed `scripts/differential_3e.py` that — unlike 3d's — drives
  `main()` itself.
- **Both pre-existing `AssertionError` crashes are fixed in 3e:** the
  no-script fall-through becomes a usage error with exit 2, and the
  in-virtualenv branch reads the active environment instead of asserting an
  unset `options.venv_dir`.
- **No new design doc.** `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md`
  already covers 3e. The decisions above are recorded here and, on completion,
  as design amendments 12–14 in `PROGRESS.md`.

---

## Starting state (this plan may be executed in a different session — assume nothing)

Measured on `main` @ `08622a8`, 2026-08-19:

- `pixi run test` → **370 passed**.
- `pixi run lint` → `All checks passed!`.
- `pixi run python -m ruff format --check .` → **52 files** already formatted.
- `pixi run typecheck` → **33 errors in 6 files**: `tests/test_verify.py` 15,
  `src/veny/cli.py` 7, `tests/test_split_imports.py` 6,
  `src/veny/analysis/imports.py` 3, `src/veny/analysis/literals.py` 1,
  `src/veny/analysis/call_graph.py` 1.
- `wc -l src/veny/cli.py` → **1,064**.
- Working tree clean apart from untracked `.claude/` and `CLAUDE.md`.

Branch for this plan: `pipeline-and-cli-slimming`, cut from `main` @ `08622a8`.

```bash
git switch -c pipeline-and-cli-slimming
```

Read before starting, in this order:

1. `PROGRESS.md` — **all** of it, but the STANDING CHECK entries in Gotchas
   (the two consecutive entries beginning "STANDING CHECK for every extraction
   from here on" and "The standing check paid for itself at a scale nobody
   predicted") are the ones that shape this plan.
2. `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md` — phase 3
   module layout, the ownership list, the error-handling section, the exit
   status table, ledger item 3 (`--full`).
3. `docs/superpowers/plans/2026-08-18-verify-cache-search-last-used.md` — 3d's
   plan, for the shape of a call-site table and of a differential task.
4. `docs/superpowers/plans/2026-08-18-verify-cache-search-last-used-wiring-index.md`
   — the `rawlog` table, including the **five sites still marked OPEN HOLE**.

## What this plan settles that the design did not

Six behaviour-visible decisions. Each is deliberate, each has a task, and each
becomes a `PROGRESS.md` entry at Task 10.

**[EXECUTION]** **There were seven, not six.** A seventh sanctioned deviation
was added mid-phase by an explicit user ruling during Task 7's second fix
round (`183bdcc`): veny's last `ek.my_critical_error` call, on the
failed-venv-build path with `choose_breakpoint=True`. emmykit's helper calls
`breakpoint()` in that mode, so a refused `uv venv` dropped the user into a
`pdb` prompt — or died with a `BdbQuit` traceback under a non-tty — from an
ordinary operational outcome. It is now
`logging.critical("Failed to create a virtual environment.")`, with the
existing `script_exit_code = 1` carrying the status out through `cli.main`.
veny now has **no** `ek.my_critical_error` call anywhere. All seven are
recorded in `PROGRESS.md`.

1. **`Options` gets its own module before it dies.** The design goes straight
   from "`Options` carries everything" to "frozen dataclasses". It does not say
   where the class lives while `pipeline.py` exists and `Options` still does
   too. Leaving it in `cli.py` would make `pipeline.py` import the module above
   it, which `tests/test_layering.py` forbids and which would be a real import
   cycle. So the class moves to `src/veny/run_options.py`, unchanged, and
   `cli.py` keeps `Options = run_options.Options` as a re-export so the 42
   existing `cli.Options` references in the suite keep working. Phase 4 deletes
   both the module and the re-export. **This is design amendment 12.**

   **[EXECUTION]** **"42 `cli.Options` references" was both slightly wrong and
   substantially incomplete.** Measured at the branch point `08622a8`: there
   are **41** literal `cli.Options` references, not 42 — and a further **28**
   that reach the same class as `veny.Options`, through
   `from veny import cli as veny` in **seven** test files. The real figure is
   **69 across two spellings**. This list is the phase-4 hand-off, so it is
   given per file and re-measured rather than summarised:

   | File | `veny.Options` |
   |---|---|
   | `tests/test_split_imports.py` | 11 |
   | `tests/test_cache_search.py` | 6 |
   | `tests/test_options_surface.py` | 4 |
   | `tests/test_manifest_writing.py` | 3 |
   | `tests/test_venv_naming.py` | 2 |
   | `tests/test_rename_venv.py` | 1 |
   | `tests/test_json_types.py` | 1 |
   | **total** | **28** |

   Derive it, do not copy it: `rg -c '\bveny\.Options\b' tests/*.py`, and
   `rg -n 'import cli as (\w+)' tests/` first in case a file adopts a
   different alias. The re-export made the original miscount harmless, but
   this is the same blind spot that broke Task 3's symbol sweep — see the
   `[EXECUTION]` note there — and phase 4, which must repoint every one of
   these when it deletes the re-export, should start from 69, both spellings
   and all seven files. A sweep driven by a short list leaves a file broken.

2. **`blank_slate` is `pipeline.py`'s, not `cli.py`'s.** The design says
   `cli.py` owns "argparse and exit status and nothing else", and the
   blank-slate branch is 45 lines of `shutil.rmtree` and directory iteration.
   It is a mode of the run, so it lands in `pipeline.py` as its own function;
   `cli.py` parses the flag and maps the return to exit 0. **This is design
   amendment 13.**

3. **The in-virtualenv branch becomes reachable.** `main()`'s
   `elif last_used.is_virtualenv():` asserts `options.venv_dir is not None`,
   and nothing sets `venv_dir` before that point, so running veny from inside
   an active virtual environment raises `AssertionError` rather than checking
   the environment the user is already in. The branch reads the active
   environment instead (`VIRTUAL_ENV`, falling back to `sys.prefix`), which is
   what it was written to do. **This is design amendment 14**, and it closes
   the second of the two pre-existing crashes the design listed as out of
   scope but expected to be "addressed incidentally when `cli.py` and
   `pipeline.py` take ownership of control flow".

4. **The no-script path becomes a usage error.** Today `veny -y` with no
   script logs "You must specify either a script to run or one of these
   arguments: `--full`, `--blank-slate` …" and then falls through to
   `list_packages`, which dies on `assert options.python_script is not None`.
   `--full` is being deleted, so that message has to be rewritten regardless.
   It becomes `pipeline.UsageError`, caught in `main()`, logged at the same
   level as today and returned as **exit 2** — the design's usage status.
   First of the two pre-existing crashes.

5. **`environment.py` stops exiting** (the design's amendment 4, which 3d
   declined and named 3e's). `uv_binary` raises `environment.UvUnavailable`
   carrying today's message verbatim; `create_venv` returns `bool`. `main()`
   catches. See Task 7 for what each caller does with the new return value.

6. **Two tail-order deviations, accepted and recorded.** Today `--justprint`
   calls `ek.print_all_errors(...)` then `sys.exit(0)`, and `--blank-slate`
   calls `sys.exit(0)` with neither. Under the new shape both return a status
   through `main()`, so both now also reach `logging.shutdown()`, and
   `--blank-slate` additionally reaches `ek.print_all_errors`. The visible
   consequence is that a warning buffered before `--blank-slate` ran (the
   PATH-`uv` warning is the realistic one) is now printed instead of
   discarded. That is an improvement, but it *is* a difference, and the
   differential in Task 9 will show it.

## Deferred items this plan picks up

- **The five OPEN HOLE `rawlog` sites** from 3d's wiring index — `cli.py`
  `406` (`ek.configure_logging`), `503` (`parse_extra_requirements`), `518`
  (`Settings` → `dict_of_custom_modules`), `1038` (`verify_and_repair_imports`)
  and `1055` (`record_venv_state`). Four of the five move into `pipeline.py`
  in Tasks 3 and 4; the `configure_logging` site stays in `cli.py`. All five
  get pinned by an effect-reading test in Task 8, not by an argument spy.
- **Design ledger item 3** (`--full` has never worked) — closed by Task 5.
- **Design ledger item 4** (exit statuses were never designed as a set) —
  closed by Task 7, which is where `cli.py` finally becomes their sole owner.
- **Design amendment 4** (`environment.py` raises and exits) — closed by
  Task 7.
- **`assert options.requirements_file is not None` appears twice in
  `setup_virtualenv`** (3d's deferred minors): the second occurrence gets the
  one-line comment saying why, in Task 4, since the function is being touched
  anyway. The comment already exists on the second site in the current tree —
  verify it survived the move rather than re-adding it.
- **The redundant `# noqa: S603` at `src/veny/environment.py:245`**, with
  `pyproject.toml:61` already granting `"src/veny/environment.py" = ["S603"]`.
  Task 7 touches that file; delete the comment there and confirm `pixi run
  lint` still reports `All checks passed!`. Do **not** touch the two
  load-bearing ones in `alias_index.py:523` and `stdlib_index.py:117`.

## Deferred items this plan explicitly declines

- **Design amendment 9** — `cache_search.find_match_dir_in_cache` keeps taking
  and mutating the `argparse.Namespace`. Its selection-policy writes
  (`args.last_used = True`, `args.latest = True`) reach disk through
  `ek.save_options_to_json`, so dropping them changes the bytes of a
  user-visible artifact. That is the persistence change, which is phase 4's.
  **Owner: phase 4.**
- **The `Options` drain itself** — no frozen dataclass is introduced here. The
  `Settings` that already exists is constructed twice in the moved code; it
  stays constructed twice. **Owner: phase 4.**
- **`pathlibcutoff`'s two readers** (`analysis/custom_modules.PATHLIB_CUTOFF`
  and `Options.pathlibcutoff` for the JSON loader). Both survive 3e untouched.
  **Owner: phase 4**, which must account for both.
- **Removing the probe venv from classification** (design amendment 3). It
  moves into `pipeline.py` as `_probe_venv`, still injected, still building a
  real environment. **Owner: whichever phase owns that user-visible change.**
- **The single-file reachability gap** (imports inside a submodule reached via
  `from package import submodule`). **Owner: a later `analysis/` plan.**
- **The third pre-existing `AssertionError`** — `veny -y` with no script is
  fixed here (item 4 above), but nothing else in the crash ledger is.

## File Structure

### Symbols moving to `src/veny/run_options.py` (measured span, 120 lines)

| Symbol | Current span | Lines |
|---|---|---|
| `class Options(ek.Options)` incl. `set_venv_dir` | `cli.py:62-181` | 120 |

Moves verbatim. Its imports — `datetime as dt`, `logging`, `os`, `Path`,
`emmykit as ek`, `alias_index`, `stdlib_index` — all sit below it in the
layering, so nothing about the class body changes.

### Symbols moving to `src/veny/pipeline.py` (measured spans, 653 lines of body)

| Symbol | Current span | Lines |
|---|---|---|
| `build_alias_index` | `cli.py:300-324` | 25 |
| `_load_last_used` | `cli.py:325-352` | 28 |
| the body of `main()` minus the CLI surface | `cli.py:353-698` | 346 |
| `find_imports_in_script` | `cli.py:699-746` | 48 |
| `warn_about_system_packages` | `cli.py:747-763` | 17 |
| `_probe_venv` (with its decorator line) | `cli.py:764-799` | 36 |
| `split_imports` | `cli.py:800-837` | 38 |
| `list_packages` | `cli.py:838-911` | 74 |
| `stayed_out_dir` | `cli.py:912-918` | 7 |
| `get_all_imports` | `cli.py:919-955` | 37 |
| `setup_virtualenv` | `cli.py:956-1064` | 109 |

The `main()` body does not move whole: Task 4 splits it into
`pipeline.run`, `pipeline.blank_slate`, `pipeline.feeling_lucky`,
`pipeline.resolve_target`, `pipeline.report` and `pipeline.run_script`, and
leaves roughly 90 lines of CLI surface behind in `cli.main`.

**On size:** `pipeline.py` lands at roughly 700 lines against the design's
~300 estimate. About 260 of those are the transitional `Options` bridge —
`find_imports_in_script`'s seven-field `ImportScan` seeding, `split_imports`'
four-field copy-back, and the `options.<field>` reads inside `list_packages`
and `setup_virtualenv`. Phase 4 deletes all of it, at which point the module
lands where the design put it. Do **not** pre-emptively split the module to
hit the estimate.

**[EXECUTION]** Measured at `a874f3d`: `pipeline.py` is **940** lines, not
"roughly 700" — a 34% under-prediction. The guidance stands and was followed
(nothing was split to hit the number), but the estimate was not close. The
overshoot is not the `Options` bridge alone; the moved code also gained
docstrings and explicit argument lists, the same effect 3d measured when its
1,232 removed lines became 1,530 new ones.

### Staying in `cli.py` (about 300 lines when this plan is done)

**[EXECUTION]** `cli.py` finished at **206** lines, comfortably under the
~300 estimate, and `cli.main`'s CLI surface is close to the predicted ~90.
`run_options.py` is **139** lines against the "measured span, 120 lines"
below — the 19-line difference is the new module docstring and import block,
which the span could not include. The phase's own total, `pipeline.py` +
`run_options.py` = **1,079** lines, is well over the ~450 that `PROGRESS.md`
carried for 3e before the plan was written.

| Symbol | Current span | Notes |
|---|---|---|
| module docstring, imports, `ResolvedImport` re-export, `json_types.register_types()` | `cli.py:1-61` | `register_types()` stays at module scope — moving it into `main()` would make `save_options_to_json` write repr strings for any consumer not going through `main()` |
| `Options = run_options.Options` | new | transitional re-export, deleted in phase 4 |
| `parse_arguments` | `cli.py:182-299` | minus the `--full` block (Task 5) |
| `main` | rewritten | argparse, logging setup/teardown, exception → exit status |

### Layering

`tests/test_layering.py`'s `LAYERS` gains two entries. `run_options` joins the
`state` layer: it imports `alias_index` and `stdlib_index` (both one layer
below) and nothing else of veny's, and no module in or below that layer imports
it, so the strictest honest placement is as `state`'s peer. `pipeline` gets its
own layer between `cache_search` and `cli`.

```python
    frozenset({"state", "run_options"}),
    ...
    frozenset({"cache_search"}),
    # pipeline.py owns the run's sequencing and is the only module that knows
    # the order: analyze -> classify -> acquire an environment -> run the
    # script. It sits directly below cli because it is handed the Options
    # object cli builds and hands back an exit status, and above everything
    # 3a-3d extracted because it drives all of them. Phase 4 removes the
    # Options carrier; the layer position does not change with it.
    frozenset({"pipeline"}),
    frozenset({"cli"}),
```

**No new `SANCTIONED_EXCEPTIONS` entry is permitted.** If one appears to be
needed, the placement is wrong — stop and re-derive it rather than adding the
exception. Verify by running the suite, not by reading this plan.

### Complete call-site table (predicted — Task 8 must re-derive it mechanically)

3e creates far fewer mis-wirable arguments than 3d did, and for a structural
reason worth stating: `pipeline`'s entry points take the `Options` object
itself, so the argument lists inside the moved code move *with* their call
sites and are not re-wired. The new explicit arguments are only these:

| # | Call site (after the move) | Arguments introduced | Task |
|---|---|---|---|
| 1 | `cli.main` → `pipeline.resolve_target(options)` | `options` | 4 |
| 2 | `cli.main` → `pipeline.feeling_lucky(options)` | `options` | 4 |
| 3 | `cli.main` → `pipeline.run(options)` | `options` | 4 |
| 4 | `pipeline.run` → `pipeline.blank_slate(options)` | `options` | 4 |
| 5 | `pipeline.run` → `pipeline.report(options)` | `options` | 4 |
| 6 | `pipeline.run` → `pipeline.run_script(...)` ×3 | `interpreter`, `script`, `script_args`, `rawlog` | 4 |
| 7 | `pipeline.run` → `last_used.active_virtualenv_dir()` | none | 6 |
| 8 | `pipeline.feeling_lucky` → `pipeline.run_script(...)` | `interpreter`, `script`, `script_args`, `rawlog` | 6 |
| 9 | `cli.main` → `ek.configure_logging(...)` | `rawlog` (OPEN HOLE from 3d) | 8 |
| 10 | `pipeline.run` → `environment.parse_extra_requirements(...)` | `rawlog` (OPEN HOLE from 3d) | 8 |
| 11 | `pipeline.run` → `Settings(...)` → `dict_of_custom_modules` | `rawlog` (OPEN HOLE from 3d) | 8 |
| 12 | `pipeline.setup_virtualenv` → `verify.verify_and_repair_imports(...)` | `rawlog` (OPEN HOLE from 3d) | 8 |
| 13 | `pipeline.setup_virtualenv` → `cache_search.record_venv_state(...)` | `rawlog` (OPEN HOLE from 3d) | 8 |
| 14 | `pipeline.setup_virtualenv` → `environment.create_venv(...)` | return value now consumed | 7 |
| 15 | `pipeline._probe_venv` → `environment.create_venv(...)` | return value now consumed | 7 |

**This table is a floor, not the list.** 3d's plan carried 14 rows and the
mechanical sweep found 40 sites. Task 8 derives the real list with `rg` over
the finished `pipeline.py` and `cli.py` and records every row it finds in the
wiring index, including the ones this table missed.

**[EXECUTION]** **The warning was right and still understated the gap by an
order of magnitude.** The mechanical sweep found **99 call-site groups**
carrying **236 measured arguments**, inside a file total of **221 call
expressions with at least one argument, carrying 458 arguments** — against
this table's **15** rows. That is a 6.6× miss on sites, after 3d's 2.9× miss
on the same prediction. The structural claim above ("`pipeline`'s entry points
take the `Options` object itself, so argument lists move *with* their call
sites") did hold and is worth keeping — it is why 3e's *hole rate* was 42%
where 3d's was 71% — but it says nothing about the number of sites, and it was
read as though it did. **Rule for the next plan: do not put a predicted
call-site table in a plan at all. Put the derivation command and a budget for
a whole task.**

---

## Task 1: Move `Options` into `src/veny/run_options.py`

**Goal:** `Options` lives in a module `pipeline.py` is allowed to import, with
every existing `cli.Options` reference still working.

**Files:**
- Create: `src/veny/run_options.py`
- Modify: `src/veny/cli.py:62-181` (delete the class, add the re-export)
- Modify: `tests/test_layering.py` (add `run_options` to the `state` layer)
- Test: `tests/test_layering.py`, `tests/test_options_surface.py`

**Acceptance Criteria:**
- [x] `src/veny/run_options.py` holds the `Options` class, byte-identical in
      body to `cli.py:62-181` apart from its new module docstring and imports.
- [x] `cli.Options is run_options.Options` — a re-export, not a subclass or a
      copy.
- [x] `tests/test_layering.py` passes with `run_options` in the `state` layer
      and **no** new `SANCTIONED_EXCEPTIONS` entry.
- [x] All 370 existing tests still pass, with no test file repointed.

**Verify:** `pixi run test` → 370 passed (plus the new test below → 371)

**Steps:**

- [x] **Step 1: Write the failing test**

Add to `tests/test_options_surface.py`:

```python
def test_options_lives_in_run_options_and_cli_only_re_exports_it():
    """cli.Options must be the same class object run_options defines.

    Behaviour under test: the phase-3e move is a re-export, not a copy or a
    subclass. Concrete bug this catches: defining `class Options(run_options.Options)`
    in cli.py instead of aliasing it would give the suite and production two
    different classes -- `isinstance` checks and `ek.save_options_to_json`'s
    registered-type lookups would then depend on which one built the instance.
    Expected value obtained from the design decision, not from the code: there
    is one Options class in this program and phase 4 deletes it.
    """
    from veny import run_options

    assert cli.Options is run_options.Options
```

- [x] **Step 2: Run it and watch it fail**

Run: `pixi run python -m pytest tests/test_options_surface.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'veny.run_options'`

- [x] **Step 3: Create the module**

`src/veny/run_options.py`:

```python
"""The per-run state object, on its way out.

`Options` is the 48-attribute god object the re-architecture retires. It lives
here rather than in `cli.py` for one reason: `pipeline.py` is handed one, and a
module may not import the module above it. Phase 4 deletes this file when the
frozen `Settings`, `Target`, `VenvHandle` and `LastUsed` dataclasses replace it;
nothing new should be added here in the meantime.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from pathlib import Path

import emmykit as ek

from . import alias_index, stdlib_index
```

Then move `cli.py:62-181` — the whole `class Options(ek.Options):` block
including `set_venv_dir` — under those imports **verbatim**. Do not reformat,
do not re-word a comment, do not reorder an attribute. A diff of the class body
against `git show HEAD:src/veny/cli.py` must be empty.

- [x] **Step 4: Re-export from `cli.py`**

Delete `cli.py:62-181` and put this in its place (after the existing
`json_types.register_types()` call):

```python
# Phase 3e moved the class itself to run_options.py so pipeline.py can be
# handed one without importing the module above it. This name stays for the
# suite's 42 `cli.Options` references and dies with the class in phase 4.
Options = run_options.Options
```

Add `run_options` to the existing `from . import (...)` block in `cli.py`.

- [x] **Step 5: Add the layer entry**

In `tests/test_layering.py`, change the `state` layer to:

```python
    # state.py carries the products one stage hands to the next. It sits
    # above the index layer because Requirements annotates its members with
    # alias_index.ResolvedImport, and in a layer of its own below classify
    # because classify -- and, later, verify and cache_search -- all need to
    # import it without a same-layer exception. run_options.py joins it as a
    # peer: it is the transitional per-run state object, it imports only
    # alias_index and stdlib_index from the layer below, and nothing at or
    # below this layer imports it. Phase 4 deletes it.
    frozenset({"state", "run_options"}),
```

- [x] **Step 6: Run the gates**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
```

Expected: 371 passed; lint clean; 53 files formatted; **≤ 33** mypy errors.
`cli.py`'s 7 mypy errors may move to `run_options.py` — that is fine, the
ceiling is a total.

- [x] **Step 7: Commit**

```bash
pixi run pre-commit run --files src/veny/run_options.py \
  src/veny/cli.py tests/test_layering.py tests/test_options_surface.py
git add src/veny/run_options.py src/veny/cli.py \
  tests/test_layering.py tests/test_options_surface.py
git commit -m "refactor: move Options to run_options.py so pipeline can take one"
```

---

## Task 2: Characterize `main()`'s branches in process, before anything moves

**Goal:** Every branch `main()` can take is driven in process and asserted
against an **effect**, so the move in Tasks 3–4 has something that can fail.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in
> the current conversation. It MUST NOT be closed by walking around it, by
> declaring it "verified inline", or by substituting a cheaper check. Close only
> after every item in `acceptanceCriteria` has been re-validated independently,
> with output captured.

**Files:**
- Modify: `tests/test_cli_entry_point.py` (extend `_drive_main`, add six tests)
- Test: `tests/test_cli_entry_point.py`

**Acceptance Criteria:**
- [x] `main()`'s four post-classification branches are each driven in process:
      all-installed, in-virtualenv, cache-hit, cache-miss-then-build.
- [x] `--justprint` and `--blank-slate` are each driven in process and asserted
      on their effect (no script subprocess ran; the directory tree was
      removed), not on a spy's own argument.
- [x] Every new test names, in its docstring, the concrete bug that makes it
      fail — per the `test-design` skill and the design's per-test protocol.
- [x] The tests pass **before** any code moves, and are what Tasks 3–4 are
      judged against.

**Verify:** `pixi run python -m pytest tests/test_cli_entry_point.py -v` → all
pass, 6 added

**Steps:**

- [x] **Step 1: Read the existing harness**

`tests/test_cli_entry_point.py:121-176` defines `_drive_main`, which stubs the
interpreter probe, the custom-module scan, the alias index, `subprocess.run`,
emmykit's logging and options-file side effects, and `cli.list_packages`. Six
of the eleven existing tests use it. Every new test below extends it rather
than building a second harness.

- [x] **Step 2: Add a script-launch recorder to `_drive_main`**

The existing harness stubs `subprocess.run` with a lambda that discards its
arguments, so no current test can see *which interpreter ran the script*.
Replace that stub with a recorder and return it alongside `captured`:

```python
    launched: list[list[str]] = []

    def record_run(command, *args, **kwargs):
        launched.append([os.fspath(part) for part in command])
        return subprocess.CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr(subprocess, "run", record_run)
```

Return `(captured, launched)` and update the six existing call sites to unpack
two values. This is the change that makes the branch tests below able to
distinguish "ran under the venv's interpreter" from "ran under `sys.executable`",
which is the whole difference between two of `main()`'s branches.

- [x] **Step 3: Write the four branch tests**

```python
def test_main_runs_the_script_under_the_running_interpreter_when_nothing_is_missing(
    monkeypatch, tmp_path
):
    """With no uninstalled imports, main() runs the script under sys.executable.

    Behaviour under test: the first of main()'s four branches. Concrete bug
    this catches: routing this branch through the venv interpreter instead --
    which the cached-venv branch below legitimately does -- would make a run
    that needs no environment build a venv anyway, or crash on a venv_python
    that is None. Expected value obtained from the branch's own contract: no
    environment was acquired, so the only interpreter available is the one
    veny is running under.
    """
    captured, launched = _drive_main(
        monkeypatch, tmp_path, ["--rawlog"], uninstalled=set(), all_imports={"os"}
    )

    status = cli.main()

    assert status == 0
    assert launched == [[sys.executable, os.fspath(tmp_path / "script.py")]]


def test_main_runs_the_script_under_the_cached_venvs_interpreter_on_a_cache_hit(
    monkeypatch, tmp_path
):
    """A cache hit runs the script under that venv's python, not sys.executable.

    Behaviour under test: the fourth branch, on the path where
    find_match_dir_in_cache returns a folder. Concrete bug this catches:
    launching with sys.executable after a cache hit would run the user's
    script in whatever environment veny itself is in -- the packages just
    matched would not be importable, and the failure would look like a bad
    cache match rather than a bad launch. Expected value obtained by
    construction: set_venv_dir puts the interpreter at <venv>/bin/python.
    """
    venv_dir = tmp_path / "home" / "veny" / "myenv-py3.12-20260819-000000-thing"
    venv_dir.mkdir(parents=True)
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(
        cache_search, "find_match_dir_in_cache", lambda *a, **k: venv_dir
    )

    status = cli.main()

    assert status == 0
    assert launched == [
        [
            os.fspath(venv_dir / "bin" / "python"),
            os.fspath(tmp_path / "script.py"),
        ]
    ]


def test_main_builds_an_environment_when_the_cache_misses(monkeypatch, tmp_path):
    """A cache miss calls setup_virtualenv and runs under what it built.

    Behaviour under test: the same branch's other side. Concrete bug this
    catches: taking options.venv_dir instead of the builder's result would
    silently run the script under a stale directory from an earlier run of
    the same process. Expected value obtained by construction: the fake
    builder is the only thing that sets venv_dir, and it sets it to built_dir.
    """
    built_dir = tmp_path / "home" / "veny" / "myenv-py3.12-20260819-111111-thing"
    built_dir.mkdir(parents=True)
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", lambda *a, **k: None)

    def fake_setup(options):
        options.set_venv_dir(built_dir)
        return True

    monkeypatch.setattr(cli, "setup_virtualenv", fake_setup)

    status = cli.main()

    assert status == 0
    assert launched == [
        [os.fspath(built_dir / "bin" / "python"), os.fspath(tmp_path / "script.py")]
    ]


def test_main_reports_failure_when_the_surrounding_virtualenv_is_short_a_package(
    monkeypatch, tmp_path
):
    """Inside a virtualenv that cannot satisfy the imports, main() returns 1.

    Behaviour under test: the third branch's failure side. Concrete bug this
    catches: returning 0 here would tell a shell script that the run
    succeeded when veny never ran anything. Expected value obtained from the
    design's exit table: 1 means veny could not build or find an environment.
    """
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
        venv_dir=tmp_path / "active",
    )
    monkeypatch.setattr(last_used, "is_virtualenv", lambda: True)
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: False)

    status = cli.main()

    assert status == 1
    assert launched == []
```

**Note on the fourth test:** it passes `venv_dir=` to `_drive_main`, which is
what today's branch needs to get past its `assert options.venv_dir is not None`.
Task 6 deletes that assert and this test changes with it — that is expected and
called out there. Write it against today's behaviour now, so that Task 6's
change is visible as a diff rather than as a new test appearing from nowhere.

- [x] **Step 4: Write the two mode tests**

```python
def test_justprint_runs_no_script_and_exits_zero(monkeypatch, tmp_path):
    """--justprint reports and stops. Nothing is launched, status is 0.

    Behaviour under test: the flag's entire contract. Concrete bug this
    catches: a reordering that puts the justprint check after the
    all-installed branch would run the user's script on a flag that promises
    not to. Expected value obtained from --help's own wording: "Don't run the
    script, just print its package requirements."
    """
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--justprint", "--rawlog"],
        uninstalled=set(),
        all_imports={"os"},
    )

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 0
    assert launched == []


def test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone(
    monkeypatch, tmp_path
):
    """--blank-slate removes ~/veny and veny's own dotfiles, nothing else.

    Behaviour under test: the destructive mode, driven in process for the
    first time. Concrete bug this catches: a widened glob deleting the user's
    own .json files in the working directory -- the branch's filter is four
    OR'd name tests and nothing pinned any of them. Expected values obtained
    by construction: keep.json does not start with a dot and so matches none
    of the four; the .veny-run.out file matches the first.
    """
    home = tmp_path / "home"
    state_dir = home / "veny"
    state_dir.mkdir(parents=True)
    (state_dir / "myenv-py3.12-000000-thing").mkdir()
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / ".veny-run.out").write_text("log\n")
    (workdir / "keep.json").write_text("{}\n")
    monkeypatch.chdir(workdir)
    captured, launched = _drive_main(
        monkeypatch, tmp_path, ["--blank-slate", "-y"], uninstalled=set(),
        all_imports=set(),
    )
    monkeypatch.setattr(sys, "argv", ["veny", "--blank-slate", "-y"])

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 0
    assert not state_dir.exists()
    assert not (workdir / ".veny-run.out").exists()
    assert (workdir / "keep.json").exists()
```

**[NOTE FOR THE IMPLEMENTER]** `_drive_main` always appends a script path to
`argv`; the blank-slate test overrides `sys.argv` afterwards to remove it,
because `--blank-slate` with a script argument takes the script branch
instead. If `Options.cwd` (resolved at construction time) does not follow
`monkeypatch.chdir`, set it on the captured options object inside a
`fake_list_packages` that is never reached, or construct the working directory
before `_drive_main` runs and chdir there first. Measure which is needed —
do not guess.

- [x] **Step 5: Run the tests, then prove each can fail**

Run: `pixi run python -m pytest tests/test_cli_entry_point.py -v`
Expected: all pass, including the six new ones.

Then, one at a time and restoring from a scratch copy each time (constraint 5):

```bash
cp src/veny/cli.py /tmp/claude-1000/-workspace/*/scratchpad/cli.py.bak
```

- swap `sys.executable` for `options.venv_python` in the all-installed branch
  → `test_main_runs_the_script_under_the_running_interpreter…` must fail
- make the justprint check return instead of exiting → the justprint test must
  fail
- narrow the blank-slate filter to `.out` only → the blank-slate test must fail

Record which test died for each mutation in the commit message. A mutation
that leaves the suite green means the test is decorative and must be fixed
before this task closes.

- [x] **Step 6: Commit**

```bash
pixi run pre-commit run --files tests/test_cli_entry_point.py
git add tests/test_cli_entry_point.py
git commit -m "test: drive every branch of main() in process before it moves"
```

---

## Task 3: Extract the analysis driver into `src/veny/pipeline.py`

**Goal:** `pipeline.py` exists and owns everything from `list_packages` down;
`cli.py` no longer knows how a script is scanned or classified.

**Files:**
- Create: `src/veny/pipeline.py`
- Modify: `src/veny/cli.py` (delete `cli.py:699-955` and `cli.py:300-324`)
- Modify: `tests/test_layering.py` (add the `pipeline` layer)
- Modify: `tests/test_classify.py`, `tests/test_import_discovery.py`,
  `tests/test_cli_entry_point.py` (repoint moved symbols)
- Test: the repointed files, plus `tests/test_layering.py`

**Acceptance Criteria:**
- [x] `pipeline.py` holds `build_alias_index`, `find_imports_in_script`,
      `warn_about_system_packages`, `_probe_venv`, `split_imports`,
      `list_packages`, `stayed_out_dir` and `get_all_imports`, with bodies
      unchanged apart from the `Options` annotation now reading
      `run_options.Options`.
- [x] `cli.py` contains none of those names.
- [x] The 25 `cli.split_imports`, 4 `cli.find_imports_in_script`, 2
      `cli._probe_venv` and 1 `cli.list_packages` references in the suite and
      in `scripts/differential_3d.py` are accounted for: test references
      repointed to `pipeline.*`; `scripts/differential_3d.py` is **not**
      updated (Task 9 explains why).
- [x] `tests/test_layering.py` passes with `pipeline` between `cache_search`
      and `cli`, no new sanctioned exception.

**Verify:** `pixi run test` → 371 passed

**Steps:**

- [x] **Step 1: Create the module with its docstring**

`src/veny/pipeline.py`:

```python
"""The run: analyze, classify, acquire an environment, run the script.

This module owns sequencing and is the only one that knows the order. Every
module below it does one thing and is handed what it needs; `cli.py` above it
parses argv and maps what happens here onto an exit status.

It is handed the run's `Options` object and hands back a status. That is
transitional: `Options` is the god object the re-architecture retires, and
phase 4 replaces it with the frozen `Settings`, `Target`, `VenvHandle` and
`Requirements` values each stage actually needs. Until then this module is
where the bridge code lives -- the `ImportScan` seeding, the classification
copy-back -- rather than in `cli.py`, so that the modules under it never see
an `Options` at all.

Everything here calls its collaborators through the module object
(`verify.check_packages_in_venv(...)`, never `from .verify import ...`), which
is what lets a test replace one boundary without rebuilding the world.
"""
```

- [x] **Step 2: Move the eight symbols verbatim**

Move `cli.py:300-324` (`build_alias_index`) and `cli.py:699-955`
(`find_imports_in_script` through `get_all_imports`, which is contiguous) into
`pipeline.py`, in that order, followed by `setup_virtualenv` in Task 4. The
only edits permitted in this step:

- the `options: Options` annotations become `options: run_options.Options`
- the module's own import block is written fresh (it needs `contextlib`,
  `logging`, `os`, `re`, `tempfile`, `Callable`/`Iterator`, `Path`, `ek`, and
  from veny: `alias_index`, `cache_search`, `classify`, `environment`,
  `last_used`, `run_options`, `stdlib_index`, `venv_cache`, `verify`,
  `Settings`, `analysis.scan as analysis_scan`,
  `analysis.custom_modules.dict_of_custom_modules`,
  `analysis.scan_state.ImportScan`)
- `ResolvedImport` is read as `alias_index.ResolvedImport` here rather than
  through `cli`'s re-export

Nothing else. Docstrings, comments and blank lines move as they are — in
particular the 20-line comment in `find_imports_in_script` explaining why the
seven scan fields are passed by reference, which is the only written record of
why that bridge works.

- [x] **Step 3: Delete the moved spans from `cli.py`**

After the deletions `cli.py` still imports `cache_search`, `classify`,
`environment`, `last_used`, `venv_cache`, `verify`, `analysis_scan`,
`dict_of_custom_modules`, `ImportScan`, `contextlib`, `re`, `tempfile`,
`Callable`, `Iterator` for code that is now gone. Delete the imports that
`ruff` reports as unused; **run `pixi run lint` and let it tell you which** —
do not delete by eye.

- [x] **Step 4: Add the layer entry**

In `tests/test_layering.py`, insert between the `cache_search` and `cli`
entries the `frozenset({"pipeline"})` block given in the File Structure
section above, comment included.

- [x] **Step 5: Repoint the tests**

```bash
rg -n 'cli\.(split_imports|find_imports_in_script|_probe_venv|list_packages|build_alias_index|stayed_out_dir|get_all_imports|warn_about_system_packages)' tests/
```

Repoint each hit to `pipeline.` and add `from veny import pipeline` to the
files that gain one. Expected counts, measured on `08622a8`:
`tests/test_classify.py` 25 (23 `split_imports` + 2 `_probe_venv`),
`tests/test_import_discovery.py` 4, `tests/test_layering.py` 2,
`tests/test_cli_entry_point.py` 1 (`build_alias_index`, inside `_drive_main`).
If a count differs, find out why before changing anything — a count that moved
means the tree moved.

**[EXECUTION]** **This sweep names one spelling; the suite uses three, and the
third was found by the tests failing rather than by `rg`.** The counts above
all matched (32 hits, 31 repointed, 1 deliberately left in
`scripts/differential_3d.py`, which is pinned to two historical trees). But
`cli.<name>` is only the first form. The second is
`monkeypatch.setattr(cli, "<name>", …)` — 13 hits at `f98a775`, 2 of them
naming symbols this task moved. The third is `from veny import cli as veny`,
which spells references as `veny.<name>` and matches **neither** pattern: four
hits in `tests/test_split_imports.py` (`veny.warn_about_system_packages` ×2,
`veny.build_alias_index` ×2), caught only by four test failures. Task 3 also
had to touch `tests/test_split_imports.py`, which the brief's file list did not
mention, for exactly this reason. **Any future sweep over a moved symbol must
run all three:**

```bash
rg -n 'cli\.(<names>)' tests/
rg -n 'setattr\(\s*cli\s*,' tests/
rg -n 'import cli as (\w+)' tests/     # then sweep <alias>.<names> too
```

- [x] **Step 6: Run the gates**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
```

Expected: 371 passed; lint clean; 54 files formatted; ≤ 33 mypy errors.

- [x] **Step 7: Commit**

```bash
pixi run pre-commit run --files src/veny/pipeline.py src/veny/cli.py \
  tests/test_layering.py tests/test_classify.py \
  tests/test_import_discovery.py tests/test_cli_entry_point.py
git add src/veny/pipeline.py src/veny/cli.py tests/test_layering.py \
  tests/test_classify.py tests/test_import_discovery.py \
  tests/test_cli_entry_point.py
git commit -m "refactor: move the analysis driver into pipeline.py"
```

---

## Task 4: Move the run itself into `pipeline.py`

**Goal:** `main()` becomes argparse plus exit-status mapping; `pipeline.run`
owns the sequence.

**Files:**
- Modify: `src/veny/pipeline.py` (gains `setup_virtualenv`, `_load_last_used`,
  `resolve_target`, `feeling_lucky`, `blank_slate`, `report`, `run_script`,
  `run`, `UsageError`, `VenvBuildFailed`)
- Modify: `src/veny/cli.py:325-698` (delete `_load_last_used`, rewrite `main`)
- Modify: `tests/test_cli_entry_point.py`, `tests/test_uv_backend.py`,
  `tests/test_verify.py`, `tests/test_last_used.py` (repoint)
- Test: all of the above

**Acceptance Criteria:**
- [x] `cli.main` is under 100 lines and contains no `logging.info` about the
      run, no `subprocess.run`, no cache search and no venv handling.
- [x] `pipeline.run(options) -> int` returns the status; the three
      `subprocess.run` script launches are one function, `run_script`.
- [x] `--justprint` and `--blank-slate` return 0 through `main()` rather than
      calling `sys.exit(0)` inside the run.
- [x] The six tests from Task 2 pass unchanged except for the stub targets
      moving from `cli.*` to `pipeline.*`.
- [x] The negative-status normalization (`128 - status` for a signal-killed
      child) stays in `cli.main`.

**Verify:** `pixi run test` → 371 passed

**Steps:**

- [x] **Step 1: Move `setup_virtualenv` and `_load_last_used`**

Move `cli.py:956-1064` and `cli.py:325-352` into `pipeline.py` verbatim, with
the same annotation change as Task 3. While `setup_virtualenv` is open,
confirm the comment on the **second** `assert options.requirements_file is not
None` survived the move — it is the "Re-narrows: mypy loses the narrowing
established above" block, and 3d's ledger listed its absence as a deferred
minor before it was added.

- [x] **Step 2: Add the two exception types**

At the top of `pipeline.py`, under the imports:

```python
class UsageError(Exception):
    """The command line asked for something veny cannot act on.

    Raised where the old code logged a message and then fell through into an
    assert. `cli.main` catches it, logs the message and returns 2 -- the
    design's usage status.
    """


class VenvBuildFailed(Exception):
    """A virtual environment veny needed could not be created.

    `environment.create_venv` reports failure rather than raising (phase 3e
    took exit ownership back into `cli.py`), and the probe environment has no
    fallback: without it, classification cannot answer "is this importable
    already?" at all. `cli.main` catches this and returns 1.
    """
```

- [x] **Step 3: Write `run_script`, the one script launch**

`main()` launches the user's script in four places today — `cli.py:392-397`
(`--feeling-lucky`), `cli.py:561-568` (nothing missing), `cli.py:582-589`
(inside a virtualenv) and `cli.py:643-662` (under an acquired venv). They differ
only in interpreter and in what they log:

```python
def run_script(
    interpreter: str | os.PathLike[str],
    script: str | os.PathLike[str],
    script_args: list[str],
    *,
    rawlog: bool,
    announce: bool = False,
) -> int:
    """Run the user's script and return its exit status.

    Args:
        interpreter: The python to run it with.
        script: The script itself.
        script_args: Everything after the script on veny's command line.
        rawlog: True suppresses veny's own commentary, so the output is what
            the user would have seen without veny.
        announce: True logs the command before running it, as the venv path
            has always done and the bare-interpreter paths never have.

    Returns:
        The child's returncode, negative if it was killed by a signal.
    """
    command_list = [os.fspath(interpreter), os.fspath(script)] + [
        str(arg) for arg in script_args
    ]
    if announce and not rawlog:
        logging.info(
            "Running command: %s", " ".join(shlex.quote(arg) for arg in command_list)
        )
    result = subprocess.run(command_list)
    return result.returncode
```

The `announce=True` default belongs **only** to the acquired-venv launch, which
is the one that logs `Running command:` today. Do not add the announcement to
the other two — that would be a visible output change nobody asked for.

- [x] **Step 4: Write `resolve_target`, `feeling_lucky`, `blank_slate`, `report`**

Each is a lift of a contiguous block of `main()`, with its `sys.exit(...)`
turned into a return value:

```python
def resolve_target(options: run_options.Options) -> None:
    """Resolve the script argument onto options, or raise UsageError.

    Lifted from main(). The one behaviour change phase 3e makes here: a run
    with no script and no --blank-slate used to log a message and fall
    through into `assert options.python_script is not None` inside
    list_packages. It raises UsageError now.
    """
```

- `resolve_target` holds `cli.py:365` and `cli.py:368-379` (the
  `script_string` read and the `ek.ensure_file` / `script_dir` block).
  `cli.py:366-367` — `script_args` and `rawlog` — stay in `cli.main`.
- `feeling_lucky` holds `cli.py:381-405`, returning `int | None` instead of
  `sys.exit(result.returncode)`; `None` means "no luck, carry on".
- `blank_slate` holds `cli.py:449-491` (the prompt, the `rmtree`, the
  four-way filename filter), returning `int`: 0 whether the user confirmed or
  declined, because both exit 0 today.
- `report` holds `cli.py:537-552` — the uninstalled/bad/samedir/subfolder
  logging plus the `warn_about_system_packages` call, the whole block already
  guarded by `if not options.rawlog:`.

- [x] **Step 5: Write `run`**

`pipeline.run(options)` is `main()`'s remaining body in order:
`find_preferred_python_version` → `stdlib_index.resolve` → `build_alias_index`
→ `my_dir` creation → the mode branch (`blank_slate` or the script path) →
`--reqs` → `Settings` + `dict_of_custom_modules` → `list_packages` →
`report` → `--justprint` → the four-branch tail. Preserve every
`logging.info`, every elapsed-time measurement and the exact order. The
signature:

```python
def run(options: run_options.Options) -> int:
    """Execute the run described by options and return the script's status.

    Args:
        options: The run's state, with argv already parsed onto it.

    Returns:
        The wrapped script's exit status, or 0 when nothing was meant to run,
        or 1 when veny could not find or build an environment.

    Raises:
        UsageError: The command line asked for something veny cannot act on.
        VenvBuildFailed: A virtual environment could not be created.
        environment.UvUnavailable: uv is not installed and not on PATH.
    """
```

`--justprint` returns 0 from inside `run` — `ek.print_all_errors` moves to
`cli.main`, which is why the deviation in "What this plan settles" item 6
exists.

- [x] **Step 6: Rewrite `cli.main`**

```python
def main() -> int:
    """Parse the command line, run veny, and map the result to an exit status.

    Returns:
        The wrapped script's exit status; 0 when nothing was meant to run
        (--justprint, --blank-slate); 1 when veny could not find or build an
        environment; 2 for a usage error. A child killed by a signal is
        reported as 128 + signal rather than as a negative status, which the
        shell would wrap around to the wrong number.
    """
    options = Options()
    parse_arguments(options)
    options.script_args = getattr(options.args, "script_args", [])
    options.rawlog = getattr(options.args, "rawlog", False)
    memory_handler = None
    try:
        pipeline.resolve_target(options)
        lucky_status = pipeline.feeling_lucky(options)
        if lucky_status is not None:
            return lucky_status
        memory_handler = ek.configure_logging(
            options.my_name, log_level=options.log_mode, rawlog=options.rawlog
        )
        script_exit_code = pipeline.run(options)
    except pipeline.UsageError as exc:
        logging.info("%s", exc)
        return 2
    except pipeline.VenvBuildFailed as exc:
        logging.error("%s", exc)
        return 1
    except environment.UvUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1
    ek.print_all_errors(memory_handler, options.rawlog)
    logging.shutdown()
    # A script killed by a signal yields a negative returncode (e.g. -9 for
    # SIGKILL). Exiting a process with a negative status wraps around to the
    # wrong shell status (-9 becomes 247), so normalize to the conventional
    # 128 + signal number (-9 becomes 137) instead.
    if script_exit_code < 0:
        script_exit_code = 128 - script_exit_code
    return script_exit_code
```

**[EXECUTION]** **Two errors in the "verbatim" body above. Do not copy it.**

1. **It omits `start_time`.** The real `main()` at `08622a8` takes its elapsed-
   time baseline *before* `parse_arguments`, and `pipeline.run` needs it. The
   body above has no `start_time = …` line and calls `pipeline.run(options)`
   with one argument. Task 4 followed it, which silently moved the baseline;
   it took a **user ruling** and a fix round (`6b35844`, "fix: time the run
   from before argparse …") to restore it. The correct shape is
   `start_time = dt.datetime.now()` as the first statement of `main`, and
   `pipeline.run(options, start_time)`. This is now pinned by
   `test_the_run_is_timed_from_the_moment_veny_started`, and the wiring index
   confirms the `start_time` argument kills exactly that test.
2. **It names `environment.UvUnavailable` three tasks before that class
   exists.** The `except environment.UvUnavailable as exc:` clause above is
   Task 7's work; at Task 4 the class is not defined and `environment.py` still
   calls `sys.exit`. Transcribing the body as written makes Task 4 fail to
   import. Task 4 must omit that clause and Task 7 must add it.

**Ordering note that matters:** `feeling_lucky` runs *before*
`ek.configure_logging`, exactly as today — that branch prints with `print()`
rather than logging, and moving the logging setup earlier would change what a
`--feeling-lucky` run emits.

- [x] **Step 7: Repoint the tests and adjust the two mode tests**

The Task 2 tests for `--justprint` and `--blank-slate` used
`pytest.raises(SystemExit)`. Both now return through `main()`:

```python
    status = cli.main()

    assert status == 0
```

Repoint stub targets: `cli.list_packages` → `pipeline.list_packages`,
`cli.setup_virtualenv` → `pipeline.setup_virtualenv`, `cli._load_last_used` →
`pipeline._load_last_used`, in `tests/test_cli_entry_point.py` (12 sites),
`tests/test_uv_backend.py` (5), `tests/test_verify.py` (1),
`tests/test_last_used.py` (5).

- [x] **Step 8: Run the gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --files src/veny/pipeline.py src/veny/cli.py \
  tests/test_cli_entry_point.py tests/test_uv_backend.py \
  tests/test_verify.py tests/test_last_used.py
git add src/veny/pipeline.py src/veny/cli.py tests/test_cli_entry_point.py \
  tests/test_uv_backend.py tests/test_verify.py tests/test_last_used.py
git commit -m "refactor: give pipeline.py the run, leaving cli.py argv and exit status"
```

---

## Task 5: Delete `--full`, and make the no-script path a usage error

**Goal:** Ledger item 3 is closed — the flag, its help text, its README
mention and all five of its branches are gone — and the fall-through it left
behind is a clean exit 2.

**[EXECUTION]** **Two errors in this task, both about counting and citing.**

1. **There are six branches, not five.** This goal says five; Step 2 below
   lists six numbered items and all six were deleted or replaced. Task 9's
   differential likewise reports "the six deleted branches". Read "six"
   everywhere in this task.
2. **Every `cli.py:NNN` citation in this task is stale, because Task 4 already
   moved the code.** The file list names `cli.py:220-224` for the
   `--full` argparse block and Step 2 cites `cli.py:445-446`, `492-495`,
   `496-499`, `642`, `678-686` and `864-870` for the branches. By the time
   Task 5 runs, `cli.py` is **202 lines** and five of those six branches live
   in `src/veny/pipeline.py`; only the `parser.add_argument("--full", …)` call
   is still in `cli.py`, and not at line 220. The spans are taken from
   `08622a8`, which was correct when the plan was written and wrong by Task 5.
   Task 5 located them with `rg -n 'full' src/veny/` instead — **which is what
   any task after a move must do.** The same rot applies to Task 6 and Task 7,
   which avoided it only by citing symbols rather than lines. **Rule: a plan
   whose early tasks move code must cite the later tasks' targets by symbol,
   never by line.**

**Files:**
- Modify: `src/veny/cli.py` (the `--full` argument, `cli.py:220-224`)
- Modify: `src/veny/pipeline.py` (five `getattr(options.args, "full", False)`
  branches)
- Modify: `README.md:77`
- Test: `tests/test_cli_entry_point.py`

**Acceptance Criteria:**
- [x] `rg -n -- '--full|"full"' src/ tests/ README.md` returns nothing.
- [x] `veny --full` exits 2 with argparse's own "unrecognized arguments"
      error — the flag is gone, not merely ignored.
- [x] `veny` with no script and no `--blank-slate` logs a message naming only
      flags that exist, and returns 2.
- [x] `get_all_imports` and the directory branch of `list_packages` **stay** —
      a directory is still reachable as a positional argument.

      **[EXECUTION]** **The code stayed, but the justification is false: a
      directory is NOT reachable as a positional argument, and deleting
      `--full` is what made the branch dead.** Found by the whole-branch
      review, 2026-08-20. `options.python_script` is written in exactly one
      production place, `pipeline.resolve_target`, and that write goes through
      `ek.ensure_file(...)` — emmykit's `ensure_file` **raises
      `IsADirectoryError`** when the path is a directory (verified against the
      installed emmykit: `if safe_is_dir(p): raise IsADirectoryError(f"Expected
      a file, got directory: …")`). At `08622a8` the directory branch was
      reachable only because the `--full` arm assigned
      `options.python_script = options.cwd` (`cli.py:495` at that commit).
      This task deleted that arm, so the `elif ek.safe_is_dir(...)` branch, the
      `else: raise FileNotFoundError` arm, `stayed_out_dir` and
      `get_all_imports` — about 55 lines — are now unreachable from any
      production entry point. **Keeping the code was still the right call for
      this phase** (deleting it is a behaviour change, and 3e is
      behaviour-preserving), but the criterion must not be read as evidence
      that folder scanning still works. Phase 4 owes the decision: either make
      `resolve_target` accept a directory, restoring folder scanning as a real
      feature, or delete the branch. Recorded in `PROGRESS.md`'s deferred
      items, and in the wiring index, where 16 kill rows cite a test that
      reaches this code only by assigning `options.python_script` directly.

**Verify:** `pixi run python -m pytest tests/test_cli_entry_point.py -v`

**Steps:**

- [x] **Step 1: Write the two failing tests**

```python
def test_the_full_flag_is_gone(monkeypatch, tmp_path):
    """--full is rejected by argparse, not silently accepted.

    Behaviour under test: ledger item 3's resolution. Concrete bug this
    catches: deleting the branches but leaving the parser.add_argument call
    would leave a flag that parses, does nothing, and reports success -- worse
    than the broken flag it replaced. Expected value obtained from argparse's
    documented behaviour: an unrecognized option is a usage error, status 2.
    """
    script = tmp_path / "script.py"
    script.write_text("import os\n")
    monkeypatch.setattr(sys, "argv", ["veny", "--full", os.fspath(script)])

    with pytest.raises(SystemExit) as exit_info:
        cli.parse_arguments(cli.Options())

    assert exit_info.value.code == 2


def test_a_run_with_no_script_is_a_usage_error(monkeypatch, tmp_path, caplog):
    """No script and no --blank-slate returns 2 and says what is missing.

    Behaviour under test: the first of the two pre-existing AssertionError
    crashes. Concrete bug this catches: the old fall-through reached
    `assert options.python_script is not None` inside list_packages and died
    with a traceback, so `veny -y` looked like a veny bug rather than a
    mistyped command. Expected value obtained from the design's exit table:
    2 is a usage error.
    """
    # _drive_main stubs the interpreter probe, the alias index and the scan,
    # then appends a script path to argv; this run must have no script, so
    # argv is replaced afterwards. Everything else it stubs is still needed --
    # the usage check sits after the alias index build, not before it.
    _drive_main(
        monkeypatch, tmp_path, ["-y"], uninstalled=set(), all_imports=set()
    )
    monkeypatch.setattr(sys, "argv", ["veny", "-y"])

    with caplog.at_level(logging.INFO):
        status = cli.main()

    assert status == 2
    assert "--blank-slate" in caplog.text
    assert "--full" not in caplog.text
```

- [x] **Step 2: Run them and watch them fail**

Run: `pixi run python -m pytest tests/test_cli_entry_point.py -k "full or usage" -v`
Expected: the first FAILs (argparse accepts `--full` today, so no `SystemExit`);
the second FAILs with `AssertionError: options.python_script must be set`.

- [x] **Step 3: Delete the flag**

Remove `cli.py:220-224` — the whole `parser.add_argument("--full", …)` call.

- [x] **Step 4: Delete the five branches in `pipeline.py`**

By their original `cli.py` line numbers, so they can be found after the move:

1. `cli.py:445-446` — `if getattr(options.args, "full", False) and options.python_script: ek.my_critical_error("Full mode is not supported with a script argument.")`. Delete the branch; the `elif options.python_script: pass` becomes the leading `if`.
2. `cli.py:492-495` — the `elif getattr(options.args, "full", False):` that assigns `options.python_script = options.cwd`. Delete.
3. `cli.py:496-499` — the `else:` logging the "You must specify either…" message. **Replace**, do not delete:

```python
    else:
        raise UsageError(
            "You must specify either a script to run or --blank-slate (be "
            "careful using --blank-slate because it deletes all cached virtual "
            "environments, among other things!)."
        )
```

4. `cli.py:642` — `if not getattr(options.args, "full", False):` guarding the
   script launch. The guard goes; the launch is unconditional.
5. `cli.py:678-686` — the "Successfully built/found a virtual environment that
   can run all python scripts in …" report. Delete, along with the
   `created_new_venv` variable that exists only to feed it — check with
   `rg -n 'created_new_venv' src/veny/` and delete every remaining assignment.
6. `cli.py:864-870` — inside `list_packages`, the `if getattr(options.args,
   "full", False):` logging "Building a virtual environment that can run every
   python script in …". Delete the branch, keep the directory-scan path under
   it.

- [x] **Step 5: Update the README**

`README.md:77` reads:

> `--help` for the full flag set (`--full`, `--no-cache`, `--latest`,

Drop `--full` from that list. Check the surrounding sentence still reads
correctly — `rg -n -B3 -A3 -- '--no-cache' README.md`.

- [x] **Step 6: Run the gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --files src/veny/cli.py src/veny/pipeline.py \
  README.md tests/test_cli_entry_point.py
git add src/veny/cli.py src/veny/pipeline.py README.md \
  tests/test_cli_entry_point.py
git commit -m "feat: delete --full and make a scriptless run a usage error"
```

---

## Task 6: Make the in-virtualenv branch check the environment it is in

**Goal:** Running veny from inside an active virtual environment checks that
environment instead of raising `AssertionError`.

**Files:**
- Modify: `src/veny/last_used.py` (add `active_virtualenv_dir`)
- Modify: `src/veny/pipeline.py` (the `elif last_used.is_virtualenv():` branch)
- Test: `tests/test_last_used.py`, `tests/test_cli_entry_point.py`

**Acceptance Criteria:**
- [x] `last_used.active_virtualenv_dir()` returns `$VIRTUAL_ENV` when set and
      `sys.prefix` otherwise, as a `Path`.
- [x] The branch no longer contains `assert options.venv_dir is not None`.
- [x] A run inside a virtualenv that satisfies the imports runs the script and
      returns its status; one that does not returns 1 with today's two log
      lines unchanged.

**Verify:** `pixi run python -m pytest tests/test_last_used.py tests/test_cli_entry_point.py -v`

**Steps:**

- [x] **Step 1: Write the failing tests**

In `tests/test_last_used.py`:

```python
def test_active_virtualenv_dir_prefers_the_environment_variable(monkeypatch, tmp_path):
    """VIRTUAL_ENV names the environment the user activated.

    Behaviour under test: which directory veny checks when it is run from
    inside a virtualenv. Concrete bug this catches: reading sys.prefix first
    would report veny's *own* environment when veny is installed as a uv tool
    and invoked from inside a different activated venv -- veny would then
    check the wrong environment's packages and report a confident, wrong
    answer. Expected value obtained from the virtualenv activation contract:
    the activate script exports VIRTUAL_ENV.
    """
    monkeypatch.setenv("VIRTUAL_ENV", os.fspath(tmp_path / "activated"))

    assert last_used.active_virtualenv_dir() == tmp_path / "activated"


def test_active_virtualenv_dir_falls_back_to_sys_prefix(monkeypatch):
    """With no VIRTUAL_ENV, sys.prefix is the environment in use.

    Concrete bug this catches: returning None (or raising) here would put the
    branch straight back to the crash phase 3e is removing -- is_virtualenv()
    is true whenever sys.prefix differs from sys.base_prefix, including for
    environments activated without the activate script.
    """
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)

    assert last_used.active_virtualenv_dir() == Path(sys.prefix)
```

In `tests/test_cli_entry_point.py`, rewrite Task 2's
`test_main_reports_failure_when_the_surrounding_virtualenv_is_short_a_package`
to stop passing `venv_dir=` and to assert the checked interpreter:

```python
def test_main_checks_the_virtualenv_it_is_running_inside(monkeypatch, tmp_path):
    """Inside a virtualenv, main() import-checks that environment's python.

    Behaviour under test: the branch phase 3e made reachable. Concrete bug
    this catches: the old code asserted options.venv_dir, which nothing sets
    on this path, so the branch could only ever raise AssertionError --
    veny was unusable from inside an activated environment. Expected value
    obtained by construction: environment.venv_python_for puts the
    interpreter at <venv>/bin/python.
    """
    active = tmp_path / "activated"
    active.mkdir()
    monkeypatch.setenv("VIRTUAL_ENV", os.fspath(active))
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(last_used, "is_virtualenv", lambda: True)
    checked: list[object] = []

    def check_spy(interpreter, **kwargs):
        checked.append(os.fspath(interpreter))
        return False

    monkeypatch.setattr(verify, "check_packages_in_venv", check_spy)

    status = cli.main()

    assert status == 1
    assert checked == [os.fspath(active / "bin" / "python")]
    assert launched == []
```

- [x] **Step 2: Run them and watch them fail**

Expected: the two `last_used` tests fail with
`AttributeError: module 'veny.last_used' has no attribute 'active_virtualenv_dir'`;
the `main()` test fails with `AssertionError: options.venv_dir must be set`.

- [x] **Step 3: Add `active_virtualenv_dir`**

In `src/veny/last_used.py`, directly under `is_virtualenv`:

```python
def active_virtualenv_dir() -> Path:
    """Return the virtual environment this process is running inside.

    is_virtualenv() answers *whether*; this answers *which*. VIRTUAL_ENV is
    what an activate script exports and is the user's own statement of which
    environment they meant; sys.prefix is the fallback for an environment
    entered by running its interpreter directly, where no activation happened.

    Returns:
        The environment's root directory. Meaningful only when
        is_virtualenv() is true.
    """
    declared = os.environ.get("VIRTUAL_ENV")
    if declared:
        return ek.ensure_path(declared)
    return Path(sys.prefix)
```

- [x] **Step 4: Rewrite the branch in `pipeline.run`**

```python
    elif last_used.is_virtualenv():
        if not options.rawlog:
            logging.info("Already in a virtual environment.")
        active_venv = last_used.active_virtualenv_dir()
        if verify.check_packages_in_venv(
            environment.venv_python_for(active_venv),
            uninstalled=options.uninstalled_imports,
            source_names=verify.source_import_names(
                options.all_imports,
                options.extra_requirements,
                getattr(options.args, "reqs", False),
            ),
        ):
```

Everything below that — the script launch under `sys.executable`, the runtime
logging, the two error lines and `script_exit_code = 1` — is unchanged.

- [x] **Step 5: Run the gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --files src/veny/last_used.py src/veny/pipeline.py \
  tests/test_last_used.py tests/test_cli_entry_point.py
git add src/veny/last_used.py src/veny/pipeline.py tests/test_last_used.py \
  tests/test_cli_entry_point.py
git commit -m "fix: check the active virtualenv instead of asserting an unset venv_dir"
```

---

## Task 7: Take exit ownership back into `cli.py`

**Goal:** No module below `cli.py` raises `SystemExit` or lets a subprocess
exception escape; design amendment 4 and ledger item 4 are closed.

**Files:**
- Modify: `src/veny/environment.py` (`UvUnavailable`, `uv_binary`,
  `create_venv`, and the redundant `# noqa: S603` at line 245)
- Modify: `src/veny/pipeline.py` (`setup_virtualenv`, `_probe_venv`)
- Test: `tests/test_environment.py`, `tests/test_uv_backend.py`,
  `tests/test_cli_entry_point.py`

**Acceptance Criteria:**
- [x] `rg -n 'SystemExit|sys\.exit|my_critical_error' src/veny/ --glob '!cli.py'`
      returns nothing outside `__main__.py`'s `sys.exit(main())`.

      **[EXECUTION]** **This criterion is unsatisfiable as literally written,
      and was met in substance rather than by the grep.** Re-run at
      `a874f3d` it returns four hits: `__main__.py:10` (sanctioned) and
      `verify.py:327`, `:330`, `:333`. The three in `verify.py` are inside a
      **Python source string literal** that veny hands to the *target*
      interpreter as `-c` — they are the probe script's own exit statuses,
      executed in the venv being checked, and have nothing to do with veny's
      process. Substantively the criterion passed: `rg -n 'my_critical_error'
      src/` returns nothing (the last call went in `183bdcc`, the seventh
      sanctioned deviation), and veny's own process exits only through
      `cli.main`'s return value. A text search cannot distinguish code from a
      string that looks like code; state the criterion as "veny's own process
      exits only through `cli.main`" and use the grep as a hint.
- [x] `environment.create_venv` returns `bool` and its docstring no longer has
      a `Raises:` section.
- [x] A missing uv exits 1 with the current message text, on stderr.
- [x] A failed venv creation on the build path exits 1 with a logged message,
      not a `CalledProcessError` traceback.
- [x] `src/veny/environment.py:245`'s redundant `# noqa: S603` is gone and
      `pixi run lint` still reports `All checks passed!`.

**Verify:** `pixi run python -m pytest tests/test_environment.py tests/test_uv_backend.py -v`
and `pixi run smoke`

**Steps:**

- [x] **Step 1: Write the failing tests**

In `tests/test_environment.py`:

```python
def test_uv_binary_raises_a_veny_error_rather_than_exiting(monkeypatch):
    """With no uv anywhere, uv_binary raises UvUnavailable, not SystemExit.

    Behaviour under test: design amendment 4's resolution. Concrete bug this
    catches: SystemExit from a library module cannot be handled by a caller
    that wants to report and continue, and it bypasses cli.main's status
    mapping entirely -- the design's exit table is unenforceable while any
    module below cli can exit on its own. Expected message obtained from the
    current text, which must not change: users have it in their shell history.
    """
    environment.uv_binary.cache_clear()
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(environment.UvUnavailable) as error:
        environment.uv_binary()

    assert "uv tool install veny" in str(error.value)


def test_create_venv_reports_failure_instead_of_raising(monkeypatch, tmp_path):
    """A uv that exits non-zero makes create_venv return False.

    Concrete bug this catches: letting CalledProcessError escape means a
    failed build reaches the user as a traceback, and setup_virtualenv's
    "Failed to create a virtual environment" path -- which exists and is
    tested -- is unreachable. Expected value obtained from the new contract:
    False means "no environment", the same shape run_uv_pip already uses.
    """
    monkeypatch.setattr(environment, "uv_binary", lambda: "uv")

    def failing_check_call(command):
        raise subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(subprocess, "check_call", failing_check_call)

    assert environment.create_venv(tmp_path / "venv") is False
```

In `tests/test_cli_entry_point.py`:

```python
def test_main_maps_a_missing_uv_to_status_one(monkeypatch, tmp_path, capsys):
    """UvUnavailable reaches cli.main and becomes exit 1 with its message.

    Behaviour under test: the other half of exit ownership -- raising is only
    correct if someone catches. Concrete bug this catches: an uncaught
    UvUnavailable would surface as a traceback and a status of 1 anyway,
    making the failure look like a veny crash rather than a missing
    dependency. Expected value obtained from the design's exit table: 1 means
    veny could not build or find an environment.
    """
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
    )

    def unavailable(options):
        raise environment.UvUnavailable("veny requires uv... uv tool install veny")

    monkeypatch.setattr(pipeline, "run", unavailable)

    status = cli.main()

    assert status == 1
    assert "uv tool install veny" in capsys.readouterr().err
```

- [x] **Step 2: Run them and watch them fail**

Expected: `AttributeError: module 'veny.environment' has no attribute
'UvUnavailable'` for the first and third; `CalledProcessError` propagating out
of the second.

- [x] **Step 3: Change `environment.py`**

Add above `uv_binary`:

```python
class UvUnavailable(Exception):
    """veny cannot find a uv to drive its environment layer with.

    Raised rather than exited: `cli.py` owns every exit status (see the
    re-architecture design's error-handling section), so the module that
    discovers the problem reports it and the module that owns the process
    decides what it costs.
    """
```

Replace the `raise SystemExit(...)` at the end of `uv_binary` with
`raise UvUnavailable(` and the identical two-line message string. Then change
`create_venv`:

```python
def create_venv(target: str | os.PathLike[str], python: str = "") -> bool:
    """Create a virtual environment at target using uv.

    No pip is seeded: veny drives installs through uv, and a script that
    installs into the environment veny built for it is working against veny.

    Args:
        target: Directory to create the environment in.
        python: Interpreter for uv to build against. Empty means uv chooses.

    Returns:
        True if the environment was created. False means uv refused, and uv
        has already said why on stderr.
    """
    command = [uv_binary(), "venv", os.fspath(target)]
    if python:
        command += ["--python", python]
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Creating venv: %s", " ".join(shlex.quote(str(arg)) for arg in command)
        )
    try:
        subprocess.check_call(command)
    except subprocess.CalledProcessError:
        return False
    return True
```

Delete the redundant `# noqa: S603` at `src/veny/environment.py:245`
(`pyproject.toml:61` already grants the per-file ignore). Confirm with
`pixi run lint` before committing, and leave the ones in `alias_index.py:523`
and `stdlib_index.py:117` alone — neither module has a per-file ignore.

- [x] **Step 4: Consume the return value at both call sites**

In `pipeline.setup_virtualenv`:

```python
    if not environment.create_venv(
        options.venv_dir, environment.venv_build_interpreter(options.python_command)
    ):
        logging.error("uv could not create the virtual environment at %s.", options.venv_dir)
        return False
```

In `pipeline._probe_venv`:

```python
        if not environment.create_venv(
            venv_dir, environment.venv_build_interpreter(options.python_command)
        ):
            raise VenvBuildFailed(
                "Could not build the throwaway environment used to check which "
                "imports are already available."
            )
```

`setup_virtualenv` returning `False` reaches the existing
`ek.my_critical_error("Failed to create a virtual environment.", …)` path in
`pipeline.run`, which already sets `script_exit_code = 1`. Leave that call
where it is: `my_critical_error` reports, and `cli.main` still owns the status.

- [x] **Step 5: Run the gates, including smoke**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run smoke
```

`pixi run smoke` needs the network. If it is unavailable, **say so explicitly
in the task report** rather than recording the task as verified — 3d's ledger
records network availability for exactly this reason.

- [x] **Step 6: Commit**

```bash
pixi run pre-commit run --files src/veny/environment.py src/veny/pipeline.py \
  tests/test_environment.py tests/test_uv_backend.py \
  tests/test_cli_entry_point.py
git add src/veny/environment.py src/veny/pipeline.py \
  tests/test_environment.py tests/test_uv_backend.py \
  tests/test_cli_entry_point.py
git commit -m "refactor: give cli.py sole ownership of veny's exit statuses"
```

---

## Task 8: The STANDING CHECK and the wiring index

**Goal:** Every argument at every call site this phase created kills a named
test, measured mechanically — including the five `rawlog` holes 3d left open.

**[EXECUTION]** **The goal as stated is unreachable, and saying so is the
task's most useful output.** Of 278 substitutions, **215 kill a named test, 16
are identity substitutions that cannot kill anything, and 47 kill nothing** —
of which **17 are DEAD ARGUMENTS** (values the callee never reads: unpinnable
by construction, deletion candidates for phase 4) and **30 are genuine OPEN
HOLEs**, each named with its reason in the index. The acceptance criteria below
anticipated this with their "or each remaining one is marked **OPEN HOLE**"
escape hatch, and that is the honest form; the goal line is not. 3d's index
claimed the strong form and its whole-branch review falsified it. **State the
headline with its qualifier, and split findings out from gaps.** All five
`rawlog` holes were closed, four by `caplog` effect-reading tests as required;
the fifth (`ek.configure_logging`) has no veny-visible effect and is pinned by
an argument spy, which the index labels as the weaker pin rather than letting
it pass as an equal one.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in
> the current conversation. It MUST NOT be closed by walking around it, by
> declaring it "verified inline", or by substituting a cheaper check. Close only
> after every item in `acceptanceCriteria` has been re-validated independently,
> with output captured.

**Files:**
- Create: `docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming-wiring-index.md`
- Modify: whichever test files the holes require

**Acceptance Criteria:**
- [x] The wiring index lists **every** call site in `pipeline.py` and `cli.py`
      that this phase created or moved, derived with `rg`, not from the
      predicted table in this plan.
- [x] For each argument: the substitution used, whether a named test died, and
      that test's name. Booleans appear **twice**, once per value.
- [x] Zero open holes at the end, or each remaining one is marked **OPEN HOLE**
      with the reason it cannot be closed.
- [x] The five `rawlog` sites 3d marked OPEN HOLE are closed by tests that read
      an **effect** (a `caplog` record present or absent), never by a spy
      asserting the value it was handed.

**Verify:** `pixi run test` → green after every hole is closed

**Steps:**

- [x] **Step 1: Derive the real call-site list**

```bash
rg -n '^\s+\w+\.\w+\(' src/veny/pipeline.py src/veny/cli.py
rg -n 'rawlog=' src/veny/pipeline.py src/veny/cli.py
```

Count every call site with at least one argument, and count the arguments.
Record both numbers in the index's header — 3d's plan predicted 14 sites and
the sweep found 40, so a prediction that matches exactly is itself suspicious
and should be re-derived.

- [x] **Step 2: Substitute, one argument at a time**

For each argument: copy the file to the scratch directory, substitute in
place, run `pixi run test`, record which named test failed, restore from the
copy. Substitution rules, both learned the hard way and both mandatory:

- a `bool` gets **both** `False` and `True` — the class default alone is a
  no-op on a run that already defaults to it, and the opposite alone is
  satisfied by any spy that asserts what it received
- an argument with no natural empty value gets a wrong-but-type-correct one:
  `Path("/tmp/wrong-venv")`, `"wrongname"`, `"9.9"`, `frozenset()`
- an argument whose substitution leaves the suite green is an **open hole**,
  and closing it means adding a test that reads the effect

- [x] **Step 3: Close the five inherited `rawlog` holes**

Each of these is pinned by asserting on log records, in both directions —
a specific `logging.INFO` record present when `rawlog=False`, absent when
`rawlog=True`. One test per site covers both directions:

```python
def test_configure_logging_is_told_whether_the_user_asked_for_raw_output(
    monkeypatch, tmp_path
):
    """cli.main hands ek.configure_logging this run's own rawlog value.

    Behaviour under test: the last of 3d's five open rawlog holes, and the
    one that stays in cli.py. Concrete bug this catches: a hardcoded
    rawlog=False here would restore timestamps and INFO prefixes to every
    --rawlog run, which is the entire point of the flag -- and no existing
    test could see it, because the effect is in emmykit's handler
    configuration rather than in veny's own output. Expected value obtained
    from the flag's contract: --rawlog means rawlog=True reaches the logger
    setup.
    """
    seen: list[bool] = []
    monkeypatch.setattr(
        ek,
        "configure_logging",
        lambda name, log_level, rawlog: seen.append(rawlog) or None,
    )
    _drive_main(
        monkeypatch, tmp_path, ["--rawlog"], uninstalled=set(), all_imports={"os"}
    )

    cli.main()

    assert seen == [True]


def test_configure_logging_is_told_when_the_user_did_not_ask_for_raw_output(
    monkeypatch, tmp_path
):
    """The same site, driven the other way: no --rawlog means rawlog=False.

    Behaviour under test: the second half of the substitution pair. Concrete
    bug this catches: a hardcoded rawlog=True would strip timestamps and INFO
    prefixes from every ordinary run and suppress veny's own commentary --
    the exact inverse failure, invisible to a test that only ever drives
    --rawlog. Expected value obtained from Options.rawlog's default, which is
    False.
    """
    seen: list[bool] = []
    monkeypatch.setattr(
        ek,
        "configure_logging",
        lambda name, log_level, rawlog: seen.append(rawlog) or None,
    )
    _drive_main(monkeypatch, tmp_path, [], uninstalled=set(), all_imports={"os"})

    cli.main()

    assert seen == [False]
```

**[NOTE FOR THE IMPLEMENTER]** the `configure_logging` site is the one place
where an argument spy is unavoidable — the effect lives inside emmykit, not in
veny. Say so in the index rather than pretending the pin is as strong as the
other four. For the other four (`parse_extra_requirements`, `Settings` →
`dict_of_custom_modules`, `verify_and_repair_imports`, `record_venv_state`),
drive the path with `caplog` and assert a specific record.

- [x] **Step 4: Write the index**

Same shape as
`docs/superpowers/plans/2026-08-18-verify-cache-search-last-used-wiring-index.md`:
a table of `site | argument | substitution | test that died`, a header with the
measured before/after counts, and an explicit statement of the substitution
class the claim was measured under. That qualifier is what made 3d's headline
claim false when it was omitted.

- [x] **Step 5: Commit**

```bash
pixi run pre-commit run --files <every test file touched> \
  docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming-wiring-index.md
git add <every test file touched> \
  docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming-wiring-index.md
git commit -m "test: pin every argument at every call site 3e created"
```

---

## Task 9: `scripts/differential_3e.py`

**Goal:** An old-vs-new comparison that drives `main()` itself — the one thing
3d's differential never did, and the blind spot that let 27 arguments go
unpinned.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in
> the current conversation. It MUST NOT be closed by walking around it, by
> declaring it "verified inline", or by substituting a cheaper check. Close only
> after every item in `acceptanceCriteria` has been re-validated independently,
> with output captured.

**Files:**
- Create: `scripts/differential_3e.py`
- Modify: `scripts/differential_3d.py` (a historical-scope banner only)
- Modify: `pyproject.toml` (per-file ignores, if the new script needs them)

**Acceptance Criteria:**
- [x] The driver takes a tree root as an argument, sets `PYTHONHASHSEED=0`
      inside itself, sets `sys.dont_write_bytecode`, purges `__pycache__`
      before the first import, redirects `HOME`, and prints
      `veny.cli.__file__` first.
- [x] Diagnostics go to **stderr**; only compared state goes to stdout.
- [x] It drives `cli.main()` end to end for at least three argv shapes:
      a run with nothing missing, a run that hits the cache, and
      `--justprint`.
- [x] The comparison is empty apart from the deviations this plan sanctioned,
      each named in the script's docstring.
- [x] The check is proved able to fail — at least four deliberate mutations,
      each recorded with the diff it produced.

**Verify:**
```bash
git archive 08622a8 src/veny | tar -x -C /tmp/old-veny
pixi run python scripts/differential_3e.py /tmp/old-veny > /tmp/old.txt
pixi run python scripts/differential_3e.py /workspace   > /tmp/new.txt
diff /tmp/old.txt /tmp/new.txt
```

**Steps:**

- [x] **Step 1: Copy the scaffolding, not the layers**

`scripts/differential_3d.py:83-152` holds `reexec_with_fixed_hash_seed`,
`purge_pycache` and the `Tree` loader. Reuse them verbatim. The three *layers*
are 3d's and do not carry over — 3e's comparison is at `main()`.

- [x] **Step 2: Write the three layers**

1. **A run with nothing missing.** Corpus: one script importing only `os`.
   Capture: `main()`'s return value, the argv of every `subprocess.run`, and
   the sorted `logging` records at INFO and above.
2. **A cache hit.** Build the same four-folder fake cache
   `differential_3d.py:506` builds — two matching candidates at different
   timestamps, one for the wrong interpreter, one whose manifest is missing a
   package — and give the two survivors **different package counts**, which
   3d's could not distinguish. Capture: the chosen folder, the ordered
   `read_manifest`/`satisfies` sequence, the final state of the four `args`
   flags, and the argv the script was launched with.
3. **`--justprint`.** Capture: the return value and the full log output.
   This is the layer that shows the sanctioned tail-order deviation.

- [x] **Step 3: Name the expected diff in the docstring**

The comparison is **not** expected to be empty. State, in the module
docstring, exactly which hunks are sanctioned:

- layer 3 gains a `logging.shutdown()` call in the new tree (deviation 6)
- any `--blank-slate` layer would gain an `ek.print_all_errors` call
- everything else must be identical

An unexplained hunk is a regression, and the docstring is what lets the next
reader tell the difference.

- [x] **Step 4: Prove it can fail**

Four mutations, minimum, each applied to the new tree only, each restored from
a scratch copy:

- swap `sys.executable` for the venv interpreter in the all-installed branch
- return `0` instead of the child's status from `run_script`
- drop `announce=True` at the acquired-venv launch
- reverse the cache ranking (`latest` → `oldest`)

Record the diff each one produced. A mutation that produces no diff means the
layer does not reach that code and must be said so in the report.

- [x] **Step 5: Add the banner to 3d's driver**

`scripts/differential_3d.py` reads `cli.Options`, `cli.list_packages`,
`cli.setup_virtualenv` and `cli._load_last_used`, three of which moved to
`pipeline.py` in this phase. It is **not** updated — it is the evidence for a
comparison between two specific historical trees, and rewriting it would
destroy that. Add one line under its docstring's first paragraph:

```python
    HISTORICAL: this driver compares trees at or before 08622a8. Phase 3e
    moved list_packages, setup_virtualenv and _load_last_used to pipeline.py,
    so it does not run against a tree after that commit. scripts/differential_3e.py
    supersedes it.
```

- [x] **Step 6: Commit**

```bash
pixi run pre-commit run --files scripts/differential_3e.py \
  scripts/differential_3d.py pyproject.toml
git add scripts/differential_3e.py scripts/differential_3d.py pyproject.toml
git commit -m "test: add the committed 3e differential and prove it can fail"
```

---

## Task 10: Close the phase — gates, README, PROGRESS, live runs

**Goal:** The phase's evidence is recorded where the next session will find it,
and nothing about it is inferred.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in
> the current conversation. It MUST NOT be closed by walking around it, by
> declaring it "verified inline", or by substituting a cheaper check. Close only
> after every item in `acceptanceCriteria` has been re-validated independently,
> with output captured.

**Files:**
- Modify: `README.md` (project structure)
- Modify: `PROGRESS.md` (Current work, Deferred items, Gotchas)
- Modify: `docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming.md`
  (annotate in place)

**Acceptance Criteria:**
- [x] `README.md`'s project structure lists `pipeline.py` and
      `run_options.py`, and `cli.py`'s description is rewritten — it currently
      claims `cli.py` builds the `ImportScan` and the probe venv, which after
      this phase it does not.
- [x] Every gate is **measured** and the number recorded: test count, lint,
      format file count, mypy errors *with the per-file breakdown*, smoke.
- [x] `wc -l` line counts recorded for every module.
- [x] Two live runs, as 3d did: `pixi run veny --no-cache` on a throwaway
      script importing a real third-party package, then the same script with
      no flag, which must reuse the folder the first run built.
- [x] `PROGRESS.md` records design amendments 12, 13 and 14, the six
      sanctioned deviations, what 3e declined and who owns it, and the
      residual risks this phase's differential still cannot see.

      **[EXECUTION]** Recorded as **seven** deviations — see the `[EXECUTION]`
      note under "What this plan settles that the design did not" — and as
      **twenty-one** residual risks: Task 9's report listed twenty and its
      review added a twenty-first (layers 1 and 7 sort their log records, so
      message ordering is uncompared there).
- [x] This plan is annotated in place with `**[EXECUTION]**` blocks wherever
      its own text was wrong. 3b, 3c and 3d each found real errors this way;
      assume this one has some too.

**Verify:** `pixi run test && pixi run lint && pixi run typecheck && pixi run smoke`

**Steps:**

- [x] **Step 1: Measure every gate and write the numbers down**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run smoke
wc -l src/veny/*.py src/veny/analysis/*.py
```

Record the mypy per-file breakdown, not just the total. The ceiling is 33 and
has fallen twice unplanned before; if it falls again, say by how much and
where.

**[EXECUTION]** It fell again, by **4**: 33 → **29**, the third unplanned fall
and the lowest it has ever been. All four came out of one file: `cli.py`
carried **7** on `main` at `08622a8` and carries **1** at `a874f3d`, with
`pipeline.py` picking up **2** — so the extraction net-deleted four rather than
relocating them. Per the ledger, Task 4 dropped one and Task 5 dropped three.
The file count rose 6 → 7 only because `cli.py` split in two. Full breakdown in
`PROGRESS.md`.

- [x] **Step 2: The two live runs**

```bash
cat > /tmp/veny-3e-check.py <<'PY'
import yaml
print(yaml.safe_load("{phase: 3e, closed: true}"))
PY
pixi run veny --no-cache /tmp/veny-3e-check.py
pixi run veny /tmp/veny-3e-check.py
```

The first must build a `~/veny/myenv-py…-pyyaml` folder with no `failed-`
prefix and print the dict.

**[EXECUTION]** **"No `failed-` prefix" is a statement about the folder on disk
when the run ends, not about the log — the log shows the prefix and that is
correct.** `uv venv` creates the folder as
`failed-myenv-py…-pyyaml` and the script is launched from that path; the
prefix is stripped by the rename only *after* verification succeeds. Verify
with `ls ~/veny/` after the run. Measured 2026-08-19: run 1's build log names
`failed-myenv-py3.13-20260819-220857-pyyaml` and the folder on disk afterwards
is `myenv-py3.13-20260819-220857-pyyaml`. Run 2 logged
`Using existing virtual environment:
/home/claudeuser/veny/myenv-py3.13-20260819-220857-pyyaml` — the identical
folder — and both runs printed `{'phase': '3e', 'closed': True}` and exited 0. The second must log `Using existing virtual
environment:` naming **the same folder** and print the same dict. Record both
folder names verbatim — if they differ, the cache path regressed and the phase
is not closed.

- [x] **Step 3: Rewrite the README structure block**

`README.md:106-109` currently describes `cli.py` as doing the analysis
bridging. Replace with:

```
    cli.py          # Argument parsing and exit-status policy. Nothing else:
                    # the run itself belongs to pipeline.py.
    pipeline.py     # The run: analyze -> classify -> acquire an environment
                    # -> run the script. The only module that knows the order.
    run_options.py  # The transitional per-run state object, on its way out.
```

and add `differential_3e.py` to the `scripts/` line.

- [x] **Step 4: Update `PROGRESS.md`**

- **Current work**: rewrite the phase-3 table's 3e row as executed, with the
  branch, the commit range, the measured gates and the line counts. Set the
  **Next action** line to phase 4 — the state model — naming what it inherits
  from this plan's "explicitly declines" section.
- **Deferred items**: add design amendments 12, 13 and 14, each with the
  reasoning; record the six sanctioned deviations; record what this
  differential could not see (each is a residual risk phase 4 inherits, in the
  same numbered form 3d used).
- **Gotchas**: add whatever this phase learned that is not derivable from the
  code. If the standing check found holes at a different rate than 3d's did,
  that number is worth recording — 3d's 104-of-147 is the most quoted line in
  the ledger precisely because it was measured rather than estimated.

- [x] **Step 5: Annotate this plan in place**

Add `**[EXECUTION]**` blocks wherever the plan's own text was wrong — a
measured span that was off, a call-site count that did not match, a test that
could not be written as specified. Then mark every checkbox.

- [x] **Step 6: Commit and merge**

```bash
pixi run pre-commit run --files README.md PROGRESS.md \
  docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming.md
git add README.md PROGRESS.md \
  docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming.md
git commit -m "docs: close phase 3e with measured gates and its ledger"
git switch main
git merge --no-ff pipeline-and-cli-slimming
```

**[EXECUTION]** **The merge was NOT performed, by explicit user instruction.**
Task 10 stops at the commit. The whole-branch review runs first and its
findings are settled before `pipeline-and-cli-slimming` reaches `main` —
merging here would merge unreviewed work, which is the opposite of what the
paragraph below asks for. The two commands after `git commit` are deferred to
whoever closes the review.

Then request a whole-branch review before deleting the branch. 3b, 3c and 3d
each had one and each found Important issues that per-task review had missed —
in 3c's case a defect living in the *seam between two individually correct
tasks*, which is exactly the failure mode a sequencing extraction invites.

---

## Rollback

Every task is a single commit against a branch that does not touch `main`
until Task 10. To abandon the phase: `git switch main && git branch -D
pipeline-and-cli-slimming`. To abandon one task: `git revert <sha>` — no task
after Task 4 depends on an earlier task's *file layout* beyond what the imports
express, so a revert of Tasks 5–9 is mechanical. Tasks 1, 3 and 4 are the
structural ones and must be reverted in reverse order if at all.
