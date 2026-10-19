# Audit bug fixes — implementation plan

The eight bugs the 2026-10-19 hygiene audit found and recorded (they were
PROGRESS.md's first Deferred item; migrated here). Branch `audit-bug-fixes`
off `main` @ `d3e5883`. User ruling, 2026-10-19: work through them
autonomously.

**Rules for every task.** Red/green TDD: the test that names the bug is
written first and seen to fail for the stated reason, then the minimum fix,
then the whole CI gate (`ruff check .`, `ruff format --check .`,
`python -m pytest` exactly as `test.yml` runs it, mypy held at <= 23). One
commit per fix, test and fix together, Conventional Commits. Mutations for
proof are made in place from a scratch copy and restored from it -- never
`git checkout -- <path>`, never `git stash`. Expected values come from what
the user's script would do when run, not from reading the code under test.
A lone failure of the two live interpreter-probe tests with "timed out after
10.0 seconds" in the log is host load (see `docs/hygiene-notes.md`); re-run.

Order: the test-isolation bug first, so every later run stops writing into
`~` and the repository; then the product bugs by blast radius; the two
tooling/text bugs last.

## Task 1 — the suite writes into the real home and the repository (bug 6)

`cli.main` derives `my_dir` from `Path.home()`, and `dict_of_custom_modules`
writes `.veny_custom_modules_*.pkl` into the process cwd. Tests that drive
`cli.main` without their own `HOME`/`chdir` (e.g.
`test_state_values::test_the_run_builds_exactly_one_settings`) create
`~/veny`, read the user's real `module_aliases.toml`, and leave a pickle in
the repo root.

- Red: `tests/test_suite_isolation.py` asserts every test sees a home other
  than the real one and a cwd outside the repository.
- Fix: an autouse fixture in a new `tests/conftest.py` giving each test a
  throwaway `HOME` and cwd. Tests that set their own still override it.
- Acceptance: with `~/veny` and the repo-root pickle removed first, a full
  run recreates neither.

## Task 2 — the alias probe is handed `""` when the preferred Python is absent (bug 4)

`pipeline.run` passes `python_command or ""` to `build_alias_index`;
`alias_index.probe_interpreter` short-circuits only on `None`, so it tries to
execute `""`, warns "Could not run  to list its installed distributions", and
returns tag `None`, leaving the alias cache inert for the run. Introduced by
`71d27d3`.

- Red: `probe_interpreter("")` must answer with the running interpreter's tag
  and spawn nothing; and a run whose preferred Python is absent must build its
  alias index for the running interpreter, with no "Could not run" warning.
- Fix: treat an empty interpreter the same as `None` in `probe_interpreter`
  (the documented "no target" case). Correct the comments that claim emmykit
  returns `""` (listed in `docs/hygiene-notes.md`).

## Task 3 — a cached venv whose interpreter is gone crashes the run (bug 5)

`verify.run_import_check_in_venv` lets `OSError` out of `subprocess.run`;
`check_packages_in_venv` (the cache-hit check) and `import_outcome_in_venv`
(the repair path) both pass it on, so a cached venv whose `bin/python` points
at an uninstalled base interpreter is a traceback, not a cache miss.

- Red: `check_packages_in_venv` on a venv with a dangling interpreter returns
  `False` and warns; `find_match_dir_in_cache` treats that venv as a miss;
  `import_outcome_in_venv` reports a machine-scoped `import_unavailable`
  outcome rather than raising -- never `import_failed`, which would be
  persisted against a package that did nothing wrong.
- Fix: catch `OSError` at those two callers, not inside
  `run_import_check_in_venv`, where a bare `False` would be misread as the
  package's fault.

## Task 4 — `from . import x` records an empty import name (bug 3)

`ImportFunctionCollector.visit_ImportFrom` takes the top-level package from
`node.module`, which is `None` for `from . import x`, and records `""`; it
flows through classification to a record with an empty pip name.

- Red: scanning a script containing `from . import x` yields no `""` import.
- Fix: skip an empty top-level name, as `_register_import_name` already does.

## Task 5 — a local module reached only from inside a function is never followed (bug 1)

The scan's second pass analyses a newly reached module, enqueues its top-level
imports onto the first pass's queue -- already drained, never read again --
and later mistakes "queued" for "already parsed", so that module's own local
imports are never analysed.

- Red: `main.py` calls `f()`, which does `import helper`; `helper.py` imports
  `inner`; `inner.py` imports `requests` -> the scan must report `requests`.
- Fix: the second pass runs newly reached modules through the same queue
  processing as the first pass, so their local imports are followed too.

## Task 6 — a local package's imports are never scanned (bug 2)

`_enqueue_top_level_imports` and the second pass accept files only, so a local
package (a directory with `__init__.py`) is never analysed, and the second
pass logs a false ERROR ("Custom module path for pkg is not a file"). The
first pass's package-directory branch is unreachable for the same reason.

- Red: `import pkg` with `pkg/__init__.py` importing `requests` -> `requests`
  found, no ERROR. A second test: `from pkg import sub`, `sub.py` importing
  `requests` -> found (this is the single-file reachability gap PROGRESS.md
  records).
- Fix: enqueue package directories in both passes; the first pass's existing
  package branch then parses `__init__.py` and the package's modules.

## Task 7 — `--blank-slate`'s prompt understates what it deletes (bug 8)

The prompt asks about "all veny .json files", then also deletes `.veny-*.out`,
`.err` and `.veny_custom_modules_*.pkl`. User-facing text: the prompt will
name every kind it deletes, matching the log line and `--help`.

- Red: the prompt test asserts the full list.

## Task 8 — the wiring sweeps can leave `src/` mutated (bug 7)

`scripts/wiring_sweep_4{a,b,c}.py` rewrite a real source file, run the suite,
and restore it in a `finally`; `write_text(mutated)` runs before the `try`,
and a killed process leaves the mutation in place, where a green suite cannot
see it.

- Fix: write the mutation inside the `try`, and keep a crash-recovery copy of
  the original beside the run that the next run restores from (and refuses
  to sweep over) before doing anything else.
- Red: a test that drives the recovery path against a scratch file.

## Execution record (2026-10-19)

**Merged to `main` at `6026948` (`--no-ff`) and pushed; CI green on all
four jobs (lint; ubuntu 3.12 and 3.13; macos 3.13).**

All eight tasks done on `audit-bug-fixes`, one `fix:` commit each, red
first in every case (each commit message names its failing test and the
failure it showed). Suite 478 -> 493; mypy held at 23; the CI gate green on
every commit.

| Task | Commit | Note |
|---|---|---|
| 1 | `78d211d` | `tests/conftest.py` autouse fixture: throwaway HOME and cwd per test |
| 2 | `1c17dd9` | `probe_interpreter("")` means "no target", like `None` |
| 3 | `f8ea2a3` | `OSError` caught at the two callers; repair path reports `import_unavailable` |
| 4 | `101f5d8` | empty top-level name skipped, module level and inside functions |
| 5 | `c0d6c7a` | first-pass queue loop extracted as `_process_queue`; the second pass uses it |
| 6 | `1ac177f` | `_module_file`: packages queued as directories, keyed by `__init__.py`; closes the recorded single-file reachability gap |
| 7 | `7ecfd06` | prompt names `.out`, `.err`, `.json` and `.pkl`, as the log line and `--help` do |
| 8 | `b4e30e1` | mutations go into a copy (`scripts/sweep_sandbox.py`), not a journal as first planned |

**Deviation from the plan, Task 8:** the plan proposed a crash-recovery
journal beside the repository; a throwaway copy was chosen instead, because
it removes the hazard rather than repairing after it. The copy must hold
everything the suite reads -- the first version left out `scripts/`, and the
new sweep test failed inside it, which would have scored as a kill for every
substitution. Verified by running the whole suite in an unmutated copy (493
passed) and one real 4c substitution there while `git status -- src` stayed
clean.

**Live end-to-end, 2026-10-19** (the environment's own interpreter, a
throwaway HOME, PyPI reachable; `python3.12`, the preferred version, absent
from PATH). A scratch project whose `main.py` imports a local package `pkg`
(whose `__init__.py` imports `six`), does a guarded `from . import sibling`,
and calls a function that imports `helper`, which imports `inner`, which
imports `six`:
- run 1: the scan processed `main.py`, `pkg`, `helper.py` and `inner.py`;
  no "Could not run" warning and no false ERROR; the alias cache recorded
  `six` under `3.13`; the venv was built and the script printed
  `six is 1.17.0`, exit 0.
- run 2, with the cached venv's `bin/python` replaced by a dangling link:
  "Could not run ... to check its imports" warnings, the cached venv
  treated as invalid, a fresh venv built, the script ran, exit 0 -- where
  the same input used to end in a `FileNotFoundError` traceback.

## Status

- [x] Task 1 — test isolation (bug 6)
- [x] Task 2 — empty interpreter to the alias probe (bug 4)
- [x] Task 3 — dangling venv interpreter (bug 5)
- [x] Task 4 — empty relative-import name (bug 3)
- [x] Task 5 — function-local module imports (bug 1)
- [x] Task 6 — local packages (bug 2)
- [x] Task 7 — `--blank-slate` prompt (bug 8)
- [x] Task 8 — wiring-sweep crash safety (bug 7)
