# Wiring index — phase 3e (`pipeline.py`, `cli.py`)

This is the tracked index of the STANDING CHECK the PROGRESS gotchas record:
*after moving a symbol out of `cli.py`, mutate every argument at the new call
site and confirm a **named** test dies.* Extracting a symbol turns an implicit
`options.<field>` read inside the callee into an explicit argument built at the
call site — a value that could not be mis-wired before the move, and can be
after it, while the new module's own unit tests keep passing because they pass
the value directly.

Phase 3e split the 1,064-line `cli.py` into `cli.py` (206 lines), `pipeline.py`
(940) and `run_options.py` (139). Every collaborator call in `pipeline.py` is a
call this phase created or moved, and so are the six left in `cli.py`. This
table names, for every argument at every one of them, the test that fails when
that argument is replaced.

`run_options.py` is not swept. Task 8's brief scoped the check to `cli.py` and
`pipeline.py`; `run_options.py` holds the `Options` class itself and five
argument-carrying call sites (all inside `set_venv_dir`), which remain
unmeasured and are **not** counted in any number below.

Run of record: task 8, **2026-08-19**, against the branch
`pipeline-and-cli-slimming`, whose phase branch point is **`183bdcc`**.

## What was measured, and under which substitution class

**The claim, stated with its qualifier — the qualifier phase 3d's index omitted,
which is what made its headline false.** Of **278 substitutions** covering
**238 distinct (call site, argument) pairs** across **99 call-site groups**,
**215 kill at least one named test**, **16 are identity substitutions** that
cannot kill anything, and **47 kill nothing** — of which **17 are DEAD
ARGUMENTS** (values the callee never reads, deletion candidates rather than
test gaps) and **30 are genuine OPEN HOLEs**. Every one of the 47 is named
below with its reason.

The substitution class each row was measured under is the value in its own
`Substituted with` column, and nothing else. The classes used are:

- **`bool` — both values, always.** Every boolean argument appears twice, once
  as `True` and once as `False`. Phase 3d learned this the hard way: `True`
  alone left 16 of 17 `rawlog` sites green because the pinning tests were
  argument spies asserting the value they were handed, and `False` alone is a
  no-op wherever the default is already `False`. 81 of the 278 rows are one
  half of such a pair.
- **empty value of the same type** — `set()`, `{}`, `[]`, `()`, `frozenset()`,
  `None`, `object()` (an attribute-less stand-in for a parsed `Namespace`).
- **wrong-but-type-correct**, where no natural empty value exists —
  `Path("/tmp/wrong-script.py")`, `Path("/nonexistent-state-dir")`,
  `"wrongname"`, `"wrongflag"`, `"9.9"`, `"20000101-000000"`,
  `run_options.Options()`, `stdlib_index.StdlibIndex(names=frozenset(), …)`,
  `alias_index.empty(Path("/tmp/wrong-index"))`, `contextlib.nullcontext(…)`,
  `lambda: None`, `dt.datetime(2000, 1, 1)`. Each is recorded in the table, so
  the evidence is auditable.
- **presence/absence**, for `run_script`'s `announce`: added as
  `announce=True` at the three sites that omit it, replaced with `False` at the
  one that sets it. These three are the only rows that probe an argument the
  source does not currently write.

**Rows marked *identity*** are the sixteen where the substituted literal is
textually what the call site already carries (`raise_on_empty=True`,
`ignore_errors=True`, `parents=True`, `exist_ok=True`, `announce=True` at
`pipeline.py:909`, and ten getattr defaults of `False`). They are listed
rather than dropped so the boolean pairs stay visibly complete; they are not
counted as pins and not counted as holes.

### Before and after

Three sweeps were run. Sweep 1 measured 250 rows at `183bdcc` before any test
was added. Sweep 2 re-measured the same 250 at `4033c75`, after four batches of
tests. Sweep 3 — the run of record for this table — measured all 278 against
the tree this file is committed with, after review finding 1 added the 28 rows
sweep 1 never reached and review finding 2 was closed with a test.

**No source file was touched by task 8**: `src/` is byte-identical to
`183bdcc`, so every line number in this document is stable across all three
sweeps and a re-run needs no re-derivation of the call-site list.

| | kills a named test | kills nothing | identity |
|---|---|---|---|
| Sweep 1, the 250 rows it covered | 136 | **106** | 8 |
| Sweep 3, those same 250 rows | 203 | **39** | 8 |
| Sweep 3, the 28 rows finding 1 added | 12 | **8** | 8 |
| **Sweep 3, all 278 rows** | **215** | **47** (17 dead + 30 open) | 16 |

**67 of sweep 1's 106 holes were closed.** Tests went from 388 to 408.

## Method

Per substitution: copy `pipeline.py` and `cli.py` to a scratch directory, patch
the one argument in place by AST offsets, run `pixi run python -m pytest -q
--tb=no -rfE`, record every named failure, restore from the copy. Never
`git stash`, never `git checkout -- <path>`. The mutation is applied to the real
file in the working tree, not to a copy on `PYTHONPATH`: pixi's
`[activation.env]` exports `PYTHONPATH=src`, which silently overrides a
prepended copy and would test the unmutated source.

**A substituted constant must be one no code path can create.** This bit the
first sweep. `Path("/tmp/wrong-venv")` was used as the wrong-path constant, but
`options.set_venv_dir` (`src/veny/run_options.py:135`, `:139`) calls
`ek.ensure_path` and then `p.mkdir(parents=True, exist_ok=True)` — so the moment
any substitution fed that path to `set_venv_dir`, `/tmp/wrong-venv` existed on
disk, and every later `ek.safe_is_dir` / `exists` check on it answered True. It
made `pipeline.py:757` look unpinnable; re-measured with
`Path("/nonexistent-state-dir")` it dies immediately. **`/tmp/wrong-venv` may
still exist on the machine this was run on, so the next sweep inherits the
contamination unless it changes the constant.** Rules for the next run: pick
substituted paths under a name nothing constructs, prefer a per-run unique
suffix, and before trusting any surviving row whose substitution is a path,
check whether something in the run created it. (Re-checked at the time: no row
in the tables below depends on that path.)

Re-run this whole check after any further extraction; a row whose test no
longer dies is a hole, not a stale row. **The 278-row table below is the
surviving evidence** — the sweep's working files are in a scratch directory that
does not outlive the session, and the task report is gitignored, so nothing else
records which test dies for which substitution.

## Scope: every one of the 458 arguments is accounted for

`pipeline.py` and `cli.py` together hold **221 call expressions with at least
one argument, carrying 458 arguments**. The three buckets below add to 458
exactly; sweep 1 did not add up, which is what review finding 1 caught.

**Measured: 236 arguments** at **99 call-site groups**, deduplicating to 238
distinct (site, argument) pairs — 235 of them existing arguments, plus the three
`announce` absence probes. These are the calls that cross a boundary: into
another veny module (`environment.*`, `verify.*`, `cache_search.*`,
`alias_index.*`, `last_used.*`, `venv_cache.*`, `stdlib_index.*`, `classify.*`,
`analysis_scan.*`, `custom_modules.*`, `pipeline.*`), into emmykit (`ek.*`),
into the process or filesystem (`subprocess.run`, `shutil.rmtree`, `mkdir`), a
value class that crosses a layer (`Settings`, `ImportScan`, `ResolvedImport`), a
function this phase moved into `pipeline.py` and now calls by name,
`options.set_venv_dir`, and every `getattr(options.args, …)` argv read —
receiver, flag name and default alike.

**Excluded: 222 arguments** at 121 calls, itemised in full, adding to 121:
**51** `logging.*` (48) and `print` (3) calls — message formatting, not wiring;
phase 3d excluded them too. **17** `parser.add_argument` calls — argparse spec,
untouched by this phase and covered by `tests/test_options_surface.py`. **6**
`getattr(options.args, …)` argv reads that appear as an argument of a call
already swept, where substituting the enclosing argument with `True`/`False`
subsumes a mis-read flag name. **17** pure conversions of a value swept at the
enclosing site or nested inside an excluded `logging` call —
`os.fspath`/`os.sep` (7), and `file.*`/`directory.*`/`sys.*`/`re.match`/
`shlex.quote`/`" ".join` (10). And **30** builtin (`len`, `set`, `str`,
`tuple`, `sorted`, `list`, `map`, `any`, `sum`, `isinstance`, `type`,
`hasattr`, `argparse.REMAINDER`) and exception-constructor (`SystemExit`,
`ValueError`, `FileNotFoundError`, `UsageError`, `VenvBuildFailed`) calls.

Two exceptions to the conversion exclusion are swept anyway, because they are
the wiring rather than a conversion of it: the two `os.fspath` calls at
`pipeline.py:383` that build `subprocess.run`'s argv, which is where the
interpreter/script order lives.

**Unmeasured: 0.** Sweep 1 left 20 unmeasured and did not disclose it — the 12
`getattr` receivers and 8 `getattr` defaults review finding 1 named. They are
measured here, and seven of the eight defaults behave exactly as the four
already-recorded siblings do (argparse always sets a store_true attribute, so
the default is unreachable). The eighth, `pipeline.py:483`, does **not**: it
kills a named test, because the `y`/`yes` dest bug below means its default is
the only part of that read anything ever consults.

## The five `rawlog` holes phase 3d left open

3d's index marked five sites OPEN HOLE in the `rawlog=True` direction. Four have
moved into `pipeline.py`; only `ek.configure_logging` is still in `cli.py`. All
five are now closed:

| 3d's site | Where it lives now | Closed by | How it is pinned |
|---|---|---|---|
| `cli.py:406` → `ek.configure_logging` | `cli.py:181` | `test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice`<br>`test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug` | **argument spy — not an equal pin.** See below. |
| `cli.py:503` → `environment.parse_extra_requirements` | `pipeline.py:777` | `test_main_lets_the_requirements_reader_explain_a_missing_file` | `caplog`: emmykit's `my_fopen` logs `File does not exist: …` at INFO when `rawlog=False`, and not when `True` |
| `cli.py:518` → `Settings` → `dict_of_custom_modules` | `pipeline.py:788`/`795` | `test_main_lets_the_custom_module_scan_explain_an_empty_cache` | `caplog`: the real scan logs `No existing custom modules pickle files found in the current directory.` The test runs the real `dict_of_custom_modules` with `sys.path` narrowed to a temporary directory |
| `cli.py:1038` → `verify.verify_and_repair_imports` | `pipeline.py:669` | `test_setup_virtualenv_lets_the_repair_pass_name_the_package_it_settled_on` | `caplog`: drives a real repair through `setup_virtualenv` and reads `repaired-pkg provides the import thing (…)` |
| `cli.py:1055` → `cache_search.record_venv_state` | `pipeline.py:684` | `test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename` | `caplog`: drives a real folder-name drift and reads `… renaming it to failed-wiredenv-…-repaired-pkg` |

**`ek.configure_logging` is the one site in this phase pinned by an argument
spy, and it is not as strong as the other four.** The effect of `rawlog` there
is inside emmykit's handler configuration — the format string on records veny
never sees — so there is no veny-visible record to read. The two tests assert
the `(name, log_level, rawlog)` tuple the call site handed over, in both
directions. A spy proves a value arrived; only reading an effect proves the
right value arrived. This row is a spy, and the index says so rather than
letting it pass as an equal pin. The same two tests do read a real effect for
one thing: `--debug` reaching `log_level`, which also closes both the flag name
and the receiver of the argv read at `cli.py:156`.

## Findings the sweep produced beyond the pins

**17 of the 47 unpinned rows — 13 distinct arguments at six call sites — are not
test gaps at all.** They are **DEAD ARGUMENTS**: values built at a call site
that the callee never reads, or that have no effect there. No test can pin them,
and they should be deleted rather than tested. They are labelled **DEAD
ARGUMENT** in the table and rolled up in their own section, so the headline can
mean "30 genuine holes plus 17 findings" rather than blurring the two:

- `pipeline.py:125` `Settings(my_name=…, cwd=…, stay_out_list=…,
  search_above_this_dir=…)` — `analysis.scan` reads **only** `settings.rawlog`.
  Four of the five fields are dead at that call site.
- `pipeline.py:222` `ImportScan(loaded_custom_modules=…, samedir_files=…,
  subfolders=…, sys_path_hints=…, seen_stdlib_imports=…)` —
  `classify.split_imports` reads only `all_imports`, `custom_modules` and
  `seen_stdlib_imports`, and `pipeline.split_imports` copies back only four
  result fields, so even `seen_stdlib_imports` is unobservable here.
- `pipeline.py:201` `alias_index.ResolvedImport(pip_name=…)` — the single-record
  branch of `check_packages_in_venv` checks `record.import_name` and nothing else.
- `pipeline.py:451`/`821`/`844` `run_script(rawlog=…)` — `run_script` reads
  `rawlog` only to guard the announce line, and all three of those sites leave
  `announce` False. Six rows (three arguments × both boolean values), one cause.
  This one is a behaviour question as much as a finding: if any of those three
  launches is ever meant to announce itself, `rawlog` becomes live there.

The remaining **30 OPEN HOLEs** break down as, adding to 30: **11** argparse
defaults that argparse never lets a real command line reach; **6** where the
callee is stubbed in every run that reaches it because the real one is an
emmykit, subprocess or filesystem boundary (`ek.print_all_errors` ×3,
`ek.save_options_to_json`, `stdlib_index.resolve`, `build_alias_index`); **5**
branches no run can construct; **3** `use_reqs` positionals that are no-ops
wherever they are not identity; **2** at `pipeline.py:483` (the receiver and the
flag name) caused by the dest bug below; **1** identity-in-effect
(`pipeline.py:788` `search_above_this_dir=True`, which is the value every run
already carries because nothing in the suite sets it False); and **2** that are
**conditional, not permanent** — `pipeline.py:788` `stay_out_list` reopens as
soon as a test plants a `sys.path` entry matching a stay-out fragment, and
`pipeline.py:768` `blank_slate(Options())` reopens the moment the `y`/`yes`
dest bug is fixed. Both are labelled **Conditional** in the roll-up.

Two pre-existing defects the sweep surfaced rather than gaps, recorded not fixed
because this phase is behaviour-preserving:

- `pipeline.py:483` `getattr(options.args, "y", False)` — argparse gives
  `-y/--yes` the dest `yes`, so this read is **already always False**. The
  receiver and the flag name are therefore both unpinnable (an attribute-less
  `object()` behaves identically), while the *default* is pinned precisely
  because it is the only part anything consults. That asymmetry is the bug's
  signature, and it is why `blank_slate(Options())` is indistinguishable too.
- `pipeline.py:413` `.resolve(strict=True)` — with `strict=False` a missing
  script resolves silently. Today a missing script leaves `FileNotFoundError`
  travelling out of `main` uncaught, so pinning `strict=True` would mean
  asserting a traceback as the contract.

**Sixteen kill rows pin code no production run reaches** — added by the
whole-branch review of phase 3e, 2026-08-20, and stated here because a kill row
looks like coverage. The rows are the sixteen whose *only* named killing test is
`test_import_discovery::test_list_packages_walks_a_folder_and_stays_out_of_the_named_directories`:
every row for `pipeline.py:291` (`ek.safe_is_dir`), `:297` (`get_all_imports`),
`:317`/`:318` (`stayed_out_dir`) and `:326`–`:346` (`get_all_imports`' body).
They are genuine kills — the substitutions really do fail that test — but the
directory branch of `list_packages` is **dead in production**:
`options.python_script` is written in exactly one production place,
`pipeline.resolve_target`, through `ek.ensure_file(...)`, and emmykit's
`ensure_file` raises `IsADirectoryError` for a directory. Before phase 3e's Task
5 the branch was reachable only via `--full`, which assigned
`options.python_script = options.cwd`; deleting `--full` deleted the only
producer of a directory. The killing test (`tests/test_import_discovery.py:224`) reaches the
code by assigning `options.python_script` directly — `options.python_script =
project` at `tests/test_import_discovery.py:254` — which bypasses
`resolve_target` entirely. So these sixteen rows pin a *move*, not a live path.
Phase 4 owes the decision — teach `resolve_target` to accept a directory, or
delete the branch — and whichever it picks, these rows go with it. Not counted
among the 47 unpinned rows: they are pinned, just not by anything a user can
run. Recorded in `PROGRESS.md`'s deferred items and as an `[EXECUTION]` block on
Task 5's fourth acceptance criterion.

> **DECIDED AND EXECUTED 2026-08-21, phase 4a Task 1.** User ruling: delete the
> branch, do not revive it. `get_all_imports`, `stayed_out_dir` and the
> directory arms of `list_packages` are gone; so is the bypassing test. All
> sixteen rows are struck from the table below, replaced by a single retirement
> row at the point where they stood. Three further rows (`pipeline.py:275`,
> `:286`, `:312`) named that test as *one* of several killers and keep their
> other killers; only the dead citation was trimmed. `resolve_target` now
> raises `UsageError` for a directory — and for a missing, empty or symlinked
> path, which closes latent defect 2 in the same stroke — so `veny somedir/`
> is exit status 2 rather than a traceback.

## Every argument, measured

`Sweep 1` marks the rows that were holes at `183bdcc`, and `*not reached*` the
28 rows sweep 1 never measured. Test names are abbreviated:
`test_cli_entry_point::x` means `tests/test_cli_entry_point.py::x`. Where more
than three named tests die, the first three are listed with a count of the rest.
Line numbers are as of `183bdcc`. They did not move through task 10 — task 8
added tests only — but **`cli.py`'s did move by `+5` after that**, in
`0691352` (the whole-branch review's fix wave, 2026-08-20), which lengthened
`main`'s docstring by five lines and shifted every statement in `main` down.
So the eight `cli.py` rows below that sit inside `main` — `:172`, `:173`,
`:174`, `:177`, `:178`, `:181`, `:184` and `:198` — are at `:177`, `:178`,
`:179`, `:182`, `:183`, `:186`, `:189` and `:203` in any tree at `0691352` or
later. The rows are **deliberately left at their measured numbers**, because
this table is the record of a sweep run at `183bdcc` and renumbering it would
detach it from the measurement it documents; the function name in each row's
`Site` column is the durable half of the citation. `cli.py:156`
(`parse_arguments`) and every `pipeline.py` row are unaffected —
`pipeline.py` has not been touched since the sweep.

| Site | Argument | Substituted with | Test that died | Sweep 1 |
|---|---|---|---|---|
| `cli.py:172` (main) -> `parse_arguments` | `positional 0` | `Options()` | `test_cli_entry_point::test_a_failed_build_reports_at_critical_and_returns_one_without_a_debugger`<br>`test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone`<br>(+22 more) |  |
| `cli.py:173` (main) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` | was a hole |
| `cli.py:173` (main) -> `getattr` | `positional 2` | `["wrongarg"]` | **OPEN HOLE** -- argparse's REMAINDER always sets `script_args`, so this getattr default is unreachable from any real command line; only a hand-built Namespace could ever see it. | was a hole |
| `cli.py:173` (main) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` | *not reached* |
| `cli.py:174` (main) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice`<br>`test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script`<br>`test_cli_entry_point::test_main_describes_the_run_to_the_cache_search`<br>(+6 more) |  |
| `cli.py:174` (main) -> `getattr` | `positional 2` | `True` | **OPEN HOLE** -- `--rawlog` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. | was a hole |
| `cli.py:174` (main) -> `getattr` | `positional 2` | `False` | *identity -- the call site already carries this value* |  |
| `cli.py:174` (main) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice`<br>`test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script`<br>`test_cli_entry_point::test_main_describes_the_run_to_the_cache_search`<br>(+6 more) | *not reached* |
| `cli.py:177` (main) -> `pipeline.resolve_target` | `positional 0` | `Options()` | `test_cli_entry_point::test_a_failed_build_reports_at_critical_and_returns_one_without_a_debugger`<br>`test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>(+18 more) |  |
| `cli.py:178` (main) -> `pipeline.feeling_lucky` | `positional 0` | `Options()` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_feeling_lucky_launches_the_interpreter_the_loader_named`<br>`test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script`<br>(+1 more) |  |
| `cli.py:181` (main) -> `ek.configure_logging` | `positional 0` | `"wrongname"` | `test_cli_entry_point::test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice`<br>`test_cli_entry_point::test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug` | was a hole |
| `cli.py:181` (main) -> `ek.configure_logging` | `log_level` | `logging.CRITICAL` | `test_cli_entry_point::test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice`<br>`test_cli_entry_point::test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug` | was a hole |
| `cli.py:181` (main) -> `ek.configure_logging` | `rawlog` | `True` | `test_cli_entry_point::test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug` | was a hole |
| `cli.py:181` (main) -> `ek.configure_logging` | `rawlog` | `False` | `test_cli_entry_point::test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice` | was a hole |
| `cli.py:184` (main) -> `pipeline.run` | `positional 0` | `Options()` | `test_cli_entry_point::test_a_failed_build_reports_at_critical_and_returns_one_without_a_debugger`<br>`test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone`<br>(+17 more) |  |
| `cli.py:184` (main) -> `pipeline.run` | `start_time` | `dt.datetime(2000, 1, 1)` | `test_cli_entry_point::test_the_run_is_timed_from_the_moment_veny_started` | was a hole |
| `cli.py:198` (main) -> `ek.print_all_errors` | `positional 0` | `None` | **OPEN HOLE** -- emmykit owns `print_all_errors`, and every in-process run stubs `ek.configure_logging`, so the handler really is None on those runs: `None` is the value the site already carries under test. | was a hole |
| `cli.py:198` (main) -> `ek.print_all_errors` | `positional 1` | `True` | **OPEN HOLE** -- emmykit owns the effect -- which buffered ERROR records get replayed, and in what format. No veny-visible record changes either way. | was a hole |
| `cli.py:198` (main) -> `ek.print_all_errors` | `positional 1` | `False` | **OPEN HOLE** -- emmykit owns the effect -- which buffered ERROR records get replayed, and in what format. No veny-visible record changes either way. | was a hole |
| `cli.py:156` (parse_arguments) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug` | was a hole |
| `cli.py:156` (parse_arguments) -> `getattr` | `positional 2` | `True` | **OPEN HOLE** -- `-d/--debug` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. | was a hole |
| `cli.py:156` (parse_arguments) -> `getattr` | `positional 2` | `False` | *identity -- the call site already carries this value* |  |
| `cli.py:156` (parse_arguments) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug` | *not reached* |
| `pipeline.py:91` (build_alias_index) -> `alias_index.build` | `positional 0` | `"wrongname"` | `test_cli_entry_point::test_build_alias_index_reads_this_runs_own_directory_and_interpreter` | was a hole |
| `pipeline.py:91` (build_alias_index) -> `alias_index.build` | `positional 1` | `Path("/tmp/wrong-venv")` | `test_cli_entry_point::test_build_alias_index_reads_this_runs_own_directory_and_interpreter` | was a hole |
| `pipeline.py:91` (build_alias_index) -> `alias_index.build` | `offline` | `True` | `test_split_imports::test_the_index_reaches_pypi_by_default` |  |
| `pipeline.py:91` (build_alias_index) -> `alias_index.build` | `offline` | `False` | `test_split_imports::test_the_offline_argument_keeps_the_index_off_the_network` |  |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `my_name` | `"wrongname"` | **DEAD ARGUMENT** -- Dead argument: `analysis.scan` reads only `settings.rawlog` off the Settings it is handed. `my_name` is never read at this call site. | was a hole |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `cwd` | `Path("/tmp/wrong-dir")` | **DEAD ARGUMENT** -- Dead argument: `analysis.scan` reads only `settings.rawlog`. `cwd` is never read at this call site. | was a hole |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `stay_out_list` | `()` | **DEAD ARGUMENT** -- Dead argument: `analysis.scan` reads only `settings.rawlog`. `stay_out_list` is never read at this call site. | was a hole |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `search_above_this_dir` | `True` | **DEAD ARGUMENT** -- Dead argument: `analysis.scan` reads only `settings.rawlog`. `search_above_this_dir` is never read at this call site. | was a hole |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `search_above_this_dir` | `False` | **DEAD ARGUMENT** -- Dead argument: `analysis.scan` reads only `settings.rawlog`. `search_above_this_dir` is never read at this call site. | was a hole |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `rawlog` | `True` | `test_import_discovery::test_the_scan_adapter_lets_the_scanner_name_the_files_it_opens` |  |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `rawlog` | `False` | `test_import_discovery::test_the_scan_adapter_lets_the_scanner_name_the_files_it_opens` |  |
| `pipeline.py:132` (find_imports_in_script) -> `ImportScan` | `all_imports` | `set()` | `test_import_discovery::test_function_body_import_in_a_custom_module_is_discovered`<br>`test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found`<br>(+2 more) |  |
| `pipeline.py:132` (find_imports_in_script) -> `ImportScan` | `custom_modules` | `{}` | `test_import_discovery::test_a_prepopulated_custom_module_outside_the_script_dir_is_recognized` |  |
| `pipeline.py:132` (find_imports_in_script) -> `ImportScan` | `loaded_custom_modules` | `set()` | `test_import_discovery::test_a_prepopulated_custom_module_outside_the_script_dir_is_recognized`<br>`test_import_discovery::test_function_body_import_in_a_custom_module_is_discovered` |  |
| `pipeline.py:132` (find_imports_in_script) -> `ImportScan` | `samedir_files` | `[]` | `test_import_discovery::test_the_scan_records_the_local_files_folders_and_sys_path_it_followed` | was a hole |
| `pipeline.py:132` (find_imports_in_script) -> `ImportScan` | `subfolders` | `[]` | `test_import_discovery::test_the_scan_records_the_local_files_folders_and_sys_path_it_followed` | was a hole |
| `pipeline.py:132` (find_imports_in_script) -> `ImportScan` | `sys_path_hints` | `set()` | `test_import_discovery::test_the_scan_records_the_local_files_folders_and_sys_path_it_followed` | was a hole |
| `pipeline.py:132` (find_imports_in_script) -> `ImportScan` | `seen_stdlib_imports` | `set()` | `test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package`<br>`test_import_discovery::test_standard_library_imports_are_not_reported_as_needing_install` |  |
| `pipeline.py:141` (find_imports_in_script) -> `analysis_scan.find_imports_in_script` | `positional 0` | `Settings(my_name="wrongname", cwd=Path("/tmp"), stay_out_list=(), search_above_this_dir=False, rawlog=False)` | `test_import_discovery::test_the_scan_adapter_lets_the_scanner_name_the_files_it_opens` |  |
| `pipeline.py:141` (find_imports_in_script) -> `analysis_scan.find_imports_in_script` | `positional 1` | `Path("/tmp/wrong-script.py")` | `test_import_discovery::test_a_prepopulated_custom_module_outside_the_script_dir_is_recognized`<br>`test_import_discovery::test_a_script_with_no_third_party_imports_yields_an_empty_import_set`<br>`test_import_discovery::test_function_body_import_in_a_custom_module_is_discovered`<br>(+6 more) |  |
| `pipeline.py:141` (find_imports_in_script) -> `analysis_scan.find_imports_in_script` | `is_stdlib` | `(lambda name: False)` | `test_import_discovery::test_a_script_with_no_third_party_imports_yields_an_empty_import_set`<br>`test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package`<br>`test_import_discovery::test_standard_library_imports_are_not_reported_as_needing_install` |  |
| `pipeline.py:141` (find_imports_in_script) -> `analysis_scan.find_imports_in_script` | `scan` | `ImportScan()` | `test_import_discovery::test_a_prepopulated_custom_module_outside_the_script_dir_is_recognized`<br>`test_import_discovery::test_function_body_import_in_a_custom_module_is_discovered`<br>`test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found`<br>(+5 more) |  |
| `pipeline.py:152` (warn_about_system_packages) -> `stdlib_index.hints_for` | `positional 0` | `set()` | `test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package`<br>`test_split_imports::test_tkinter_produces_one_system_package_warning` |  |
| `pipeline.py:182` (_probe_venv) -> `environment.create_venv` | `positional 0` | `"/tmp/wrong-venv"` | `test_classify::test_the_probe_venv_is_asked_about_the_interpreter_it_just_built` |  |
| `pipeline.py:182` (_probe_venv) -> `environment.create_venv` | `positional 1` | `"wrongname"` | `test_classify::test_split_imports_probe_venv_is_given_the_classified_interpreter` |  |
| `pipeline.py:183` (_probe_venv) -> `environment.venv_build_interpreter` | `positional 0` | `"wrongname"` | `test_classify::test_split_imports_probe_venv_is_given_the_classified_interpreter` |  |
| `pipeline.py:199` (is_importable) -> `verify.check_packages_in_venv` | `positional 0` | `Path("/tmp/wrong-venv/bin/python")` | `test_classify::test_the_probe_venv_is_asked_about_the_interpreter_it_just_built` |  |
| `pipeline.py:199` (is_importable) -> `verify.check_packages_in_venv` | `record` | `alias_index.ResolvedImport(import_name="wrongname", pip_name="wrongname")` | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled`<br>`test_classify::test_a_requirement_already_importable_in_the_probe_is_recorded_in_both_sets`<br>`test_classify::test_bad_imports_never_reach_the_probe_venv_or_the_resolver`<br>(+2 more) |  |
| `pipeline.py:200` (is_importable) -> `environment.venv_python_for` | `positional 0` | `"/tmp/wrong-venv"` | `test_classify::test_the_probe_venv_is_asked_about_the_interpreter_it_just_built` |  |
| `pipeline.py:201` (is_importable) -> `alias_index.ResolvedImport` | `import_name` | `"wrongname"` | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled`<br>`test_classify::test_a_requirement_already_importable_in_the_probe_is_recorded_in_both_sets`<br>`test_classify::test_bad_imports_never_reach_the_probe_venv_or_the_resolver`<br>(+2 more) |  |
| `pipeline.py:201` (is_importable) -> `alias_index.ResolvedImport` | `pip_name` | `"wrongname"` | **DEAD ARGUMENT** -- Dead argument: `check_packages_in_venv`'s single-record branch checks `record.import_name` and nothing else. The probe supplies `pip_name=import_name` only because ResolvedImport requires both. | was a hole |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `all_imports` | `set()` | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled`<br>`test_classify::test_a_refused_probe_venv_stops_classification_instead_of_probing_nothing`<br>`test_classify::test_a_run_whose_every_import_is_bad_builds_no_probe_venv`<br>(+12 more) |  |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `custom_modules` | `{}` | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled`<br>`test_classify::test_only_genuinely_uninstalled_imports_are_resolved`<br>`test_classify::test_total_imports_equals_the_size_of_all_imports_when_split_imports_returns` |  |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `loaded_custom_modules` | `set()` | **DEAD ARGUMENT** -- Dead argument: `classify.split_imports` reads only `scan.all_imports`, `scan.custom_modules` and `scan.seen_stdlib_imports`. | was a hole |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `samedir_files` | `[]` | **DEAD ARGUMENT** -- Dead argument: `classify.split_imports` reads only `scan.all_imports`, `scan.custom_modules` and `scan.seen_stdlib_imports`. | was a hole |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `subfolders` | `[]` | **DEAD ARGUMENT** -- Dead argument: `classify.split_imports` reads only `scan.all_imports`, `scan.custom_modules` and `scan.seen_stdlib_imports`. | was a hole |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `sys_path_hints` | `set()` | **DEAD ARGUMENT** -- Dead argument: `classify.split_imports` reads only `scan.all_imports`, `scan.custom_modules` and `scan.seen_stdlib_imports`. | was a hole |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `seen_stdlib_imports` | `set()` | **DEAD ARGUMENT** -- Effectively dead: `classify.split_imports` returns it as `Requirements.seen_stdlib`, but `pipeline.split_imports` copies back only all_imports, bad, uninstalled and total_imports, so nothing downstream can observe it. | was a hole |
| `pipeline.py:231` (split_imports) -> `classify.split_imports` | `positional 0` | `ImportScan()` | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled`<br>`test_classify::test_a_refused_probe_venv_stops_classification_instead_of_probing_nothing`<br>`test_classify::test_a_run_whose_every_import_is_bad_builds_no_probe_venv`<br>(+12 more) |  |
| `pipeline.py:231` (split_imports) -> `classify.split_imports` | `aliases` | `alias_index.empty(Path("/tmp/wrong-index"))` | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled`<br>`test_classify::test_bad_imports_never_reach_the_probe_venv_or_the_resolver`<br>`test_classify::test_only_genuinely_uninstalled_imports_are_resolved`<br>(+3 more) |  |
| `pipeline.py:231` (split_imports) -> `classify.split_imports` | `known_bad_imports` | `set()` | `test_classify::test_a_run_whose_every_import_is_bad_builds_no_probe_venv`<br>`test_classify::test_bad_imports_never_reach_the_probe_venv_or_the_resolver` |  |
| `pipeline.py:231` (split_imports) -> `classify.split_imports` | `also_needs` | `{}` | `test_classify::test_split_imports_expands_also_needs_onto_the_uninstalled_records` |  |
| `pipeline.py:231` (split_imports) -> `classify.split_imports` | `extra_requirements` | `{}` | `test_classify::test_a_requirement_already_importable_in_the_probe_is_recorded_in_both_sets`<br>`test_classify::test_reqs_records_are_unioned_in_after_the_loop_with_import_name_as_pip_name`<br>`test_classify::test_reqs_requirements_are_counted_before_the_zero_import_early_return`<br>(+1 more) |  |
| `pipeline.py:231` (split_imports) -> `classify.split_imports` | `use_reqs` | `True` | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found` | was a hole |
| `pipeline.py:231` (split_imports) -> `classify.split_imports` | `use_reqs` | `False` | `test_classify::test_a_requirement_already_importable_in_the_probe_is_recorded_in_both_sets`<br>`test_classify::test_reqs_records_are_unioned_in_after_the_loop_with_import_name_as_pip_name`<br>`test_classify::test_reqs_requirements_are_counted_before_the_zero_import_early_return`<br>(+1 more) |  |
| `pipeline.py:231` (split_imports) -> `classify.split_imports` | `probe` | `contextlib.nullcontext(lambda name: False)` | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled`<br>`test_classify::test_a_refused_probe_venv_stops_classification_instead_of_probing_nothing`<br>`test_classify::test_a_requirement_already_importable_in_the_probe_is_recorded_in_both_sets`<br>(+5 more) |  |
| `pipeline.py:231` (split_imports) -> `classify.split_imports` | `rawlog` | `True` | `test_classify::test_the_classification_adapter_lets_classify_report_each_import` |  |
| `pipeline.py:231` (split_imports) -> `classify.split_imports` | `rawlog` | `False` | `test_classify::test_the_classification_adapter_lets_classify_report_each_import` |  |
| `pipeline.py:238` (split_imports) -> `_probe_venv` | `positional 0` | `run_options.Options()` | `test_classify::test_split_imports_probe_venv_is_given_the_classified_interpreter` |  |
| `pipeline.py:275` (list_packages) -> `ek.ensure_path` | `positional 0` | `Path("/tmp/wrong-script.py")` | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found`<br>`test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package` | was a hole |
| `pipeline.py:277` (list_packages) -> `ek.safe_is_file` | `positional 0` | `Path("/tmp/wrong-script.py")` | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found`<br>`test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package` | was a hole |
| `pipeline.py:278` (list_packages) -> `ek.is_python_script` | `positional 0` | `Path("/tmp/wrong-script.py")` | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found`<br>`test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package` | was a hole |
| `pipeline.py:286` (list_packages) -> `find_imports_in_script` | `positional 0` | `run_options.Options()` | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found`<br>`test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package` | was a hole |
| `pipeline.py:286` (list_packages) -> `find_imports_in_script` | `positional 1` | `Path("/tmp/wrong-script.py")` | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found`<br>`test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package` | was a hole |
| _(16 rows retired)_ | | | **RETIRED 2026-08-21 by phase 4a Task 1.** These rows measured arguments to `list_packages`' directory arms and the two folder-scanning helpers. Their only named killer reached them by assigning `options.python_script` directly, bypassing `resolve_target`; no production run could. The code and that test are deleted (user ruling, 2026-08-21). Retired, not closed -- nothing pinned them, and nothing needed to. | |
| `pipeline.py:312` (list_packages) -> `split_imports` | `positional 0` | `run_options.Options()` | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found` | was a hole |
| `pipeline.py:383` (run_script) -> `os.fspath` | `positional 0` | `"/tmp/wrong-python"` | `test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_feeling_lucky_launches_the_interpreter_the_loader_named`<br>(+4 more) |  |
| `pipeline.py:383` (run_script) -> `os.fspath` | `positional 0` | `'/tmp/wrong-script.py'` | `test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_feeling_lucky_launches_the_interpreter_the_loader_named`<br>(+4 more) |  |
| `pipeline.py:390` (run_script) -> `subprocess.run` | `positional 0` | `[sys.executable, "-c", ""]` | `test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_feeling_lucky_launches_the_interpreter_the_loader_named`<br>(+3 more) |  |
| `pipeline.py:409` (resolve_target) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_a_failed_build_reports_at_critical_and_returns_one_without_a_debugger`<br>`test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>(+18 more) |  |
| `pipeline.py:409` (resolve_target) -> `getattr` | `positional 2` | `"/tmp/wrong-script.py"` | **OPEN HOLE** -- argparse's `nargs="?"` always sets `script` (to None when absent), so this getattr default is unreachable from any real command line. | was a hole |
| `pipeline.py:409` (resolve_target) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_a_failed_build_reports_at_critical_and_returns_one_without_a_debugger`<br>`test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>(+19 more) | *not reached* |
| `pipeline.py:413` (resolve_target) -> `ek.ensure_file` | `positional 0` | `"wrongname"` | `test_cli_entry_point::test_a_failed_build_reports_at_critical_and_returns_one_without_a_debugger`<br>`test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice`<br>(+23 more) |  |
| `pipeline.py:413` (resolve_target) -> `ek.ensure_file` | `raise_on_empty` | `True` | *identity -- the call site already carries this value* |  |
| `pipeline.py:413` (resolve_target) -> `ek.ensure_file` | `raise_on_empty` | `False` | **OPEN HOLE** -- Distinguishable only when the script argument is an empty string. argparse never produces one from a real command line, and no test builds that Namespace by hand. | was a hole |
| `pipeline.py:413` (resolve_target) -> `ek.ensure_file(script_string, raise_on_empty=True).resolve` | `strict` | `True` | *identity -- the call site already carries this value* |  |
| `pipeline.py:413` (resolve_target) -> `ek.ensure_file(script_string, raise_on_empty=True).resolve` | `strict` | `False` | **OPEN HOLE** -- With `strict=False` a nonexistent script resolves silently and the run fails later. Today a missing script leaves `FileNotFoundError` to travel out of `main` uncaught; asserting that as the contract would pin a defect rather than a behaviour, so this is left open for the exit-status work rather than nailed down here. | was a hole |
| `pipeline.py:441` (feeling_lucky) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_feeling_lucky_launches_the_interpreter_the_loader_named`<br>`test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script`<br>(+1 more) |  |
| `pipeline.py:441` (feeling_lucky) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_feeling_lucky_launches_the_interpreter_the_loader_named`<br>`test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script`<br>(+1 more) | *not reached* |
| `pipeline.py:441` (feeling_lucky) -> `getattr` | `positional 2` | `True` | **OPEN HOLE** -- `--feeling-lucky` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. | *not reached* |
| `pipeline.py:441` (feeling_lucky) -> `getattr` | `positional 2` | `False` | *identity -- the call site already carries this value* | *not reached* |
| `pipeline.py:443` (feeling_lucky) -> `last_used.load_last_used_venv_python` | `positional 0` | `run_options.Options()` | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |  |
| `pipeline.py:443` (feeling_lucky) -> `last_used.load_last_used_venv_python` | `script_dir` | `Path("/tmp/wrong-dir")` | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script`<br>`test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |  |
| `pipeline.py:443` (feeling_lucky) -> `last_used.load_last_used_venv_python` | `python_script` | `Path("/tmp/wrong-script.py")` | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |  |
| `pipeline.py:443` (feeling_lucky) -> `last_used.load_last_used_venv_python` | `pathlibcutoff` | `"20000101-000000"` | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |  |
| `pipeline.py:443` (feeling_lucky) -> `last_used.load_last_used_venv_python` | `rawlog` | `True` | `test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |  |
| `pipeline.py:443` (feeling_lucky) -> `last_used.load_last_used_venv_python` | `rawlog` | `False` | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script`<br>`test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |  |
| `pipeline.py:451` (feeling_lucky) -> `run_script` | `positional 0` | `"/tmp/wrong-python"` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_feeling_lucky_launches_the_interpreter_the_loader_named` | was a hole |
| `pipeline.py:451` (feeling_lucky) -> `run_script` | `positional 1` | `Path("/tmp/wrong-script.py")` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_feeling_lucky_launches_the_interpreter_the_loader_named` | was a hole |
| `pipeline.py:451` (feeling_lucky) -> `run_script` | `positional 2` | `[]` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` | was a hole |
| `pipeline.py:451` (feeling_lucky) -> `run_script` | `rawlog` | `True` | **DEAD ARGUMENT** -- No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site passes `announce=False`. | was a hole |
| `pipeline.py:451` (feeling_lucky) -> `run_script` | `rawlog` | `False` | **DEAD ARGUMENT** -- No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site passes `announce=False`. | was a hole |
| `pipeline.py:451` (feeling_lucky) -> `run_script` | `announce` | `True` | `test_cli_entry_point::test_only_the_venv_launch_announces_the_command_it_is_about_to_run` | was a hole |
| `pipeline.py:483` (blank_slate) -> `getattr` | `positional 1` | `"wrongflag"` | **OPEN HOLE** -- The site is already misspelled: argparse gives `-y/--yes` the dest `yes`, so `getattr(options.args, "y", False)` is always False and `"y"` and `"wrongflag"` are indistinguishable. Recorded, not fixed -- this phase is behaviour-preserving; see test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone. | was a hole |
| `pipeline.py:483` (blank_slate) -> `getattr` | `positional 0` | `object()` | **OPEN HOLE** -- Same root cause as the flag name below: argparse's dest for `-y/--yes` is `yes`, so `options.args` never carries a `y` attribute and a receiver with no attributes at all behaves identically. The *default* at this site is pinned, precisely because the dest bug makes it the only part that is read. | *not reached* |
| `pipeline.py:483` (blank_slate) -> `getattr` | `positional 2` | `True` | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone` | *not reached* |
| `pipeline.py:483` (blank_slate) -> `getattr` | `positional 2` | `False` | *identity -- the call site already carries this value* | *not reached* |
| `pipeline.py:484` (blank_slate) -> `ek.prompt_then_confirm` | `positional 0` | `"wrongname"` | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone` | was a hole |
| `pipeline.py:495` (blank_slate) -> `shutil.rmtree` | `positional 0` | `Path("/tmp/wrong-venv")` | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone` |  |
| `pipeline.py:495` (blank_slate) -> `shutil.rmtree` | `ignore_errors` | `True` | *identity -- the call site already carries this value* |  |
| `pipeline.py:495` (blank_slate) -> `shutil.rmtree` | `ignore_errors` | `False` | **OPEN HOLE** -- `pipeline.run` creates `options.my_dir` a few lines before it reaches the --blank-slate branch, so `shutil.rmtree` never sees a missing directory on any path a run can take. | was a hole |
| `pipeline.py:499` (blank_slate) -> `ek.safe_is_file` | `positional 0` | `Path("/tmp/wrong-script.py")` | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone` |  |
| `pipeline.py:543` (report) -> `warn_about_system_packages` | `positional 0` | `run_options.Options()` | `test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package` | was a hole |
| `pipeline.py:572` (_load_last_used) -> `last_used.load_last_used_options` | `positional 0` | `run_options.Options()` | `test_last_used::test_the_last_used_adapter_hands_over_this_runs_script_and_cutoff` |  |
| `pipeline.py:572` (_load_last_used) -> `last_used.load_last_used_options` | `script_dir` | `Path("/tmp/wrong-dir")` | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs`<br>`test_last_used::test_the_last_used_adapter_hands_over_this_runs_script_and_cutoff`<br>`test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |  |
| `pipeline.py:572` (_load_last_used) -> `last_used.load_last_used_options` | `python_script` | `Path("/tmp/wrong-script.py")` | `test_last_used::test_the_last_used_adapter_hands_over_this_runs_script_and_cutoff`<br>`test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |  |
| `pipeline.py:572` (_load_last_used) -> `last_used.load_last_used_options` | `pathlibcutoff` | `"20000101-000000"` | `test_last_used::test_the_last_used_adapter_hands_over_this_runs_script_and_cutoff`<br>`test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |  |
| `pipeline.py:572` (_load_last_used) -> `last_used.load_last_used_options` | `rawlog` | `True` | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |  |
| `pipeline.py:572` (_load_last_used) -> `last_used.load_last_used_options` | `rawlog` | `False` | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs`<br>`test_last_used::test_the_last_used_adapter_hands_over_this_runs_script_and_cutoff` |  |
| `pipeline.py:595` (setup_virtualenv) -> `cache_search.interpreter_tag` | `positional 0` | `stdlib_index.StdlibIndex(names=frozenset(), python_version=(9, 9), source="wrong")` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair`<br>`test_uv_backend::test_the_venv_folder_name_and_build_interpreter_come_from_this_run`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:596` (setup_virtualenv) -> `venv_cache.build_folder_name` | `venv_name` | `"wrongname"` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair`<br>`test_uv_backend::test_the_venv_folder_name_and_build_interpreter_come_from_this_run`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:596` (setup_virtualenv) -> `venv_cache.build_folder_name` | `interpreter_tag` | `"9.9"` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair`<br>`test_uv_backend::test_the_venv_folder_name_and_build_interpreter_come_from_this_run`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:596` (setup_virtualenv) -> `venv_cache.build_folder_name` | `timestamp` | `"20000101-000000"` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair`<br>`test_uv_backend::test_the_venv_folder_name_and_build_interpreter_come_from_this_run`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:596` (setup_virtualenv) -> `venv_cache.build_folder_name` | `pip_names` | `[]` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair`<br>`test_uv_backend::test_the_venv_folder_name_and_build_interpreter_come_from_this_run`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:603` (setup_virtualenv) -> `options.set_venv_dir` | `positional 0` | `Path("/tmp/wrong-venv")` | `test_uv_backend::test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename`<br>`test_uv_backend::test_setup_virtualenv_reports_failure_when_uv_refuses_to_build`<br>`test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair`<br>(+2 more) |  |
| `pipeline.py:608` (setup_virtualenv) -> `environment.create_venv` | `positional 0` | `Path("/tmp/wrong-venv")` | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt`<br>`test_uv_backend::test_the_venv_folder_name_and_build_interpreter_come_from_this_run` |  |
| `pipeline.py:608` (setup_virtualenv) -> `environment.create_venv` | `positional 1` | `"wrongname"` | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt`<br>`test_uv_backend::test_the_venv_folder_name_and_build_interpreter_come_from_this_run` |  |
| `pipeline.py:609` (setup_virtualenv) -> `environment.venv_build_interpreter` | `positional 0` | `"wrongname"` | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt`<br>`test_uv_backend::test_the_venv_folder_name_and_build_interpreter_come_from_this_run` |  |
| `pipeline.py:632` (setup_virtualenv) -> `environment.write_requirements_file_with_extras` | `positional 0` | `Path("/tmp/wrong-req.txt")` | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt`<br>`test_uv_backend::test_setup_virtualenv_writes_the_extra_requirements_version_specifiers` |  |
| `pipeline.py:632` (setup_virtualenv) -> `environment.write_requirements_file_with_extras` | `positional 1` | `[]` | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt`<br>`test_uv_backend::test_setup_virtualenv_writes_the_extra_requirements_version_specifiers` |  |
| `pipeline.py:632` (setup_virtualenv) -> `environment.write_requirements_file_with_extras` | `positional 2` | `{}` | `test_uv_backend::test_setup_virtualenv_writes_the_extra_requirements_version_specifiers` |  |
| `pipeline.py:638` (setup_virtualenv) -> `environment.run_uv_pip` | `positional 0` | `Path("/tmp/wrong-venv/bin/python")` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:638` (setup_virtualenv) -> `environment.run_uv_pip` | `positional 1` | `"wrongname"` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:638` (setup_virtualenv) -> `environment.run_uv_pip` | `positional 2` | `"wrongname"` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:638` (setup_virtualenv) -> `environment.run_uv_pip` | `positional 3` | `"/tmp/wrong-req.txt"` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:656` (setup_virtualenv) -> `verify.source_import_names` | `positional 0` | `set()` | `test_uv_backend::test_setup_virtualenv_lets_the_repair_pass_name_the_package_it_settled_on`<br>`test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:656` (setup_virtualenv) -> `verify.source_import_names` | `positional 1` | `{}` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:656` (setup_virtualenv) -> `verify.source_import_names` | `positional 2` | `True` | **OPEN HOLE** -- `source_import_names` drops extra_requirements keys only when use_reqs is true, and `options.extra_requirements` is populated only on a --reqs run -- where the real value is already True. Substituting True is a no-op everywhere it is not identity. | was a hole |
| `pipeline.py:656` (setup_virtualenv) -> `verify.source_import_names` | `positional 2` | `False` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:669` (setup_virtualenv) -> `verify.verify_and_repair_imports` | `venv_python` | `Path("/tmp/wrong-venv/bin/python")` | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:669` (setup_virtualenv) -> `verify.verify_and_repair_imports` | `requirements_file` | `Path("/tmp/wrong-req.txt")` | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:669` (setup_virtualenv) -> `verify.verify_and_repair_imports` | `uninstalled` | `set()` | `test_uv_backend::test_setup_virtualenv_lets_the_repair_pass_name_the_package_it_settled_on`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:669` (setup_virtualenv) -> `verify.verify_and_repair_imports` | `extra_requirements` | `{}` | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:669` (setup_virtualenv) -> `verify.verify_and_repair_imports` | `source_names` | `frozenset()` | `test_uv_backend::test_setup_virtualenv_lets_the_repair_pass_name_the_package_it_settled_on`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:669` (setup_virtualenv) -> `verify.verify_and_repair_imports` | `index` | `alias_index.empty(Path("/tmp/wrong-index"))` | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:669` (setup_virtualenv) -> `verify.verify_and_repair_imports` | `rawlog` | `True` | `test_uv_backend::test_setup_virtualenv_lets_the_repair_pass_name_the_package_it_settled_on` | was a hole |
| `pipeline.py:669` (setup_virtualenv) -> `verify.verify_and_repair_imports` | `rawlog` | `False` | `test_uv_backend::test_setup_virtualenv_lets_the_repair_pass_name_the_package_it_settled_on`<br>`test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |  |
| `pipeline.py:683` (setup_virtualenv) -> `options.set_venv_dir` | `positional 0` | `Path("/tmp/wrong-venv")` | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt`<br>`test_uv_backend::test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename`<br>`test_uv_backend::test_setup_virtualenv_writes_the_extra_requirements_version_specifiers`<br>(+2 more) |  |
| `pipeline.py:684` (setup_virtualenv) -> `cache_search.record_venv_state` | `positional 0` | `Path("/tmp/wrong-venv")` | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt`<br>`test_uv_backend::test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename`<br>`test_uv_backend::test_setup_virtualenv_writes_the_extra_requirements_version_specifiers`<br>(+2 more) |  |
| `pipeline.py:684` (setup_virtualenv) -> `cache_search.record_venv_state` | `venv_python` | `Path("/tmp/wrong-venv/bin/python")` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:684` (setup_virtualenv) -> `cache_search.record_venv_state` | `venv_name` | `"wrongname"` | `test_uv_backend::test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename`<br>`test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:684` (setup_virtualenv) -> `cache_search.record_venv_state` | `timestamp` | `"20000101-000000"` | `test_uv_backend::test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename`<br>`test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:684` (setup_virtualenv) -> `cache_search.record_venv_state` | `run_tag` | `"9.9"` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:684` (setup_virtualenv) -> `cache_search.record_venv_state` | `python_command` | `"wrongname"` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:684` (setup_virtualenv) -> `cache_search.record_venv_state` | `uninstalled` | `set()` | `test_uv_backend::test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename`<br>`test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:684` (setup_virtualenv) -> `cache_search.record_venv_state` | `extra_requirements` | `{}` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:684` (setup_virtualenv) -> `cache_search.record_venv_state` | `rawlog` | `True` | `test_uv_backend::test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename` | was a hole |
| `pipeline.py:684` (setup_virtualenv) -> `cache_search.record_venv_state` | `rawlog` | `False` | `test_uv_backend::test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename`<br>`test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:698` (setup_virtualenv) -> `verify.check_packages_in_venv` | `positional 0` | `Path("/tmp/wrong-venv/bin/python")` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:698` (setup_virtualenv) -> `verify.check_packages_in_venv` | `uninstalled` | `set()` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:698` (setup_virtualenv) -> `verify.check_packages_in_venv` | `source_names` | `frozenset()` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:699` (setup_virtualenv) -> `environment.venv_python_for` | `positional 0` | `Path("/tmp/wrong-venv")` | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |  |
| `pipeline.py:738` (run) -> `stdlib_index.resolve` | `positional 0` | `"wrongname"` | **OPEN HOLE** -- Every test that reaches `pipeline.run` replaces `stdlib_index.resolve`: the real one spawns an interpreter probe subprocess, which the in-process driver exists to avoid. | was a hole |
| `pipeline.py:748` (run) -> `build_alias_index` | `positional 0` | `run_options.Options()` | **OPEN HOLE** -- Every test that reaches `pipeline.run` replaces `build_alias_index` wholesale (the real one probes an interpreter and may reach PyPI), so the Options it is handed is never read. Its own two arguments are pinned at `pipeline.py:91`. | was a hole |
| `pipeline.py:757` (run) -> `ek.safe_is_dir` | `positional 0` | `Path("/nonexistent-state-dir")` | `test_cli_entry_point::test_the_state_directory_is_only_announced_when_it_has_to_be_created` | was a hole |
| `pipeline.py:763` (run) -> `options.my_dir.mkdir` | `parents` | `True` | *identity -- the call site already carries this value* |  |
| `pipeline.py:763` (run) -> `options.my_dir.mkdir` | `parents` | `False` | **OPEN HOLE** -- `parents` matters only when my_dir's parent is missing, and my_dir is `Path.home() / "veny"` -- no run can produce a missing home directory. | was a hole |
| `pipeline.py:763` (run) -> `options.my_dir.mkdir` | `exist_ok` | `True` | *identity -- the call site already carries this value* |  |
| `pipeline.py:763` (run) -> `options.my_dir.mkdir` | `exist_ok` | `False` | **OPEN HOLE** -- Unreachable: the mkdir runs only on the branch where `ek.safe_is_dir(options.my_dir)` has just said the directory is absent. | was a hole |
| `pipeline.py:767` (run) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone`<br>`test_cli_entry_point::test_blank_slate_with_no_state_directory_still_completes` |  |
| `pipeline.py:767` (run) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone`<br>`test_cli_entry_point::test_blank_slate_with_no_state_directory_still_completes` | *not reached* |
| `pipeline.py:767` (run) -> `getattr` | `positional 2` | `True` | **OPEN HOLE** -- `--blank-slate` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. | *not reached* |
| `pipeline.py:767` (run) -> `getattr` | `positional 2` | `False` | *identity -- the call site already carries this value* | *not reached* |
| `pipeline.py:768` (run) -> `blank_slate` | `positional 0` | `run_options.Options()` | **OPEN HOLE** -- **Conditional, not permanent.** A fresh Options built under the same HOME and working directory carries the same my_dir, my_name and cwd, and its empty args Namespace makes the -y read False exactly as the real one does -- but only because of the `y`/`yes` dest bug recorded above. Fix that dest and this row reopens: the real Options would then answer True to `-y` and the fresh one False. A distinguishing substitution today would need an Options whose my_dir differs, which main() gives a test no way to inject. | was a hole |
| `pipeline.py:776` (run) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports`<br>`test_cli_entry_point::test_main_lets_the_requirements_reader_explain_a_missing_file`<br>`test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |  |
| `pipeline.py:776` (run) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports`<br>`test_cli_entry_point::test_main_lets_the_requirements_reader_explain_a_missing_file`<br>`test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` | *not reached* |
| `pipeline.py:776` (run) -> `getattr` | `positional 2` | `True` | **OPEN HOLE** -- `--reqs` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. | *not reached* |
| `pipeline.py:776` (run) -> `getattr` | `positional 2` | `False` | *identity -- the call site already carries this value* | *not reached* |
| `pipeline.py:777` (run) -> `environment.parse_extra_requirements` | `positional 0` | `"wrongname"` | `test_cli_entry_point::test_main_lets_the_requirements_reader_explain_a_missing_file`<br>`test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |  |
| `pipeline.py:777` (run) -> `environment.parse_extra_requirements` | `rawlog` | `True` | `test_cli_entry_point::test_main_lets_the_requirements_reader_explain_a_missing_file` | was a hole |
| `pipeline.py:777` (run) -> `environment.parse_extra_requirements` | `rawlog` | `False` | `test_cli_entry_point::test_main_lets_the_requirements_reader_explain_a_missing_file`<br>`test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |  |
| `pipeline.py:788` (run) -> `Settings` | `my_name` | `"wrongname"` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | was a hole |
| `pipeline.py:788` (run) -> `Settings` | `cwd` | `Path("/tmp/wrong-dir")` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | was a hole |
| `pipeline.py:788` (run) -> `Settings` | `stay_out_list` | `()` | **OPEN HOLE** -- **Conditional, not permanent.** `dict_of_custom_modules` consults stay_out_list only through `is_standard_path`, and the test that drives the real scan narrows sys.path to a temporary directory that matches no entry either way. It becomes measurable the moment that test plants a sys.path entry whose name matches a stay-out fragment (see `src/veny/analysis/custom_modules.py:39`). | was a hole |
| `pipeline.py:788` (run) -> `Settings` | `search_above_this_dir` | `True` | **OPEN HOLE** -- Identity in effect: `Options.search_above_this_dir` defaults to True and nothing in the suite sets it False, so this direction substitutes the value the run already carries. | was a hole |
| `pipeline.py:788` (run) -> `Settings` | `search_above_this_dir` | `False` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | was a hole |
| `pipeline.py:788` (run) -> `Settings` | `rawlog` | `True` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | was a hole |
| `pipeline.py:788` (run) -> `Settings` | `rawlog` | `False` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | was a hole |
| `pipeline.py:795` (run) -> `custom_modules.dict_of_custom_modules` | `positional 0` | `Settings(my_name="wrongname", cwd=Path("/tmp"), stay_out_list=(), search_above_this_dir=False, rawlog=False)` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | was a hole |
| `pipeline.py:795` (run) -> `custom_modules.dict_of_custom_modules` | `use_cache` | `True` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | was a hole |
| `pipeline.py:795` (run) -> `custom_modules.dict_of_custom_modules` | `use_cache` | `False` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | was a hole |
| `pipeline.py:797` (run) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | was a hole |
| `pipeline.py:797` (run) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | *not reached* |
| `pipeline.py:797` (run) -> `getattr` | `positional 2` | `True` | **OPEN HOLE** -- `--rc` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. | *not reached* |
| `pipeline.py:797` (run) -> `getattr` | `positional 2` | `False` | *identity -- the call site already carries this value* | *not reached* |
| `pipeline.py:798` (run) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | was a hole |
| `pipeline.py:798` (run) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` | *not reached* |
| `pipeline.py:798` (run) -> `getattr` | `positional 2` | `True` | **OPEN HOLE** -- `--no-cache` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. | *not reached* |
| `pipeline.py:798` (run) -> `getattr` | `positional 2` | `False` | *identity -- the call site already carries this value* | *not reached* |
| `pipeline.py:810` (run) -> `list_packages` | `positional 0` | `run_options.Options()` | `test_cli_entry_point::test_a_failed_build_reports_at_critical_and_returns_one_without_a_debugger`<br>`test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_main_builds_an_environment_when_the_cache_misses`<br>(+9 more) |  |
| `pipeline.py:812` (run) -> `report` | `positional 0` | `run_options.Options()` | `test_cli_entry_point::test_the_run_reports_the_imports_it_decided_are_missing` | was a hole |
| `pipeline.py:814` (run) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_justprint_runs_no_script_and_exits_zero` |  |
| `pipeline.py:814` (run) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_justprint_runs_no_script_and_exits_zero` | *not reached* |
| `pipeline.py:814` (run) -> `getattr` | `positional 2` | `True` | **OPEN HOLE** -- `--justprint` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. | *not reached* |
| `pipeline.py:814` (run) -> `getattr` | `positional 2` | `False` | *identity -- the call site already carries this value* | *not reached* |
| `pipeline.py:821` (run) -> `run_script` | `positional 0` | `"/tmp/wrong-python"` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_main_runs_the_script_under_the_running_interpreter_when_nothing_is_missing` |  |
| `pipeline.py:821` (run) -> `run_script` | `positional 1` | `Path("/tmp/wrong-script.py")` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_main_runs_the_script_under_the_running_interpreter_when_nothing_is_missing` |  |
| `pipeline.py:821` (run) -> `run_script` | `positional 2` | `[]` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` | was a hole |
| `pipeline.py:821` (run) -> `run_script` | `rawlog` | `True` | **DEAD ARGUMENT** -- No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site leaves `announce` at its False default. | was a hole |
| `pipeline.py:821` (run) -> `run_script` | `rawlog` | `False` | **DEAD ARGUMENT** -- No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site leaves `announce` at its False default. | was a hole |
| `pipeline.py:821` (run) -> `run_script` | `announce` | `True` | `test_cli_entry_point::test_only_the_venv_launch_announces_the_command_it_is_about_to_run` | was a hole |
| `pipeline.py:834` (run) -> `verify.check_packages_in_venv` | `positional 0` | `Path("/tmp/wrong-venv/bin/python")` | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports`<br>`test_cli_entry_point::test_main_checks_the_virtualenv_it_is_running_inside` |  |
| `pipeline.py:834` (run) -> `verify.check_packages_in_venv` | `uninstalled` | `set()` | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |  |
| `pipeline.py:834` (run) -> `verify.check_packages_in_venv` | `source_names` | `frozenset()` | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |  |
| `pipeline.py:835` (run) -> `environment.venv_python_for` | `positional 0` | `Path("/tmp/wrong-venv")` | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports`<br>`test_cli_entry_point::test_main_checks_the_virtualenv_it_is_running_inside` |  |
| `pipeline.py:837` (run) -> `verify.source_import_names` | `positional 0` | `set()` | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |  |
| `pipeline.py:837` (run) -> `verify.source_import_names` | `positional 1` | `{}` | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |  |
| `pipeline.py:837` (run) -> `verify.source_import_names` | `positional 2` | `True` | **OPEN HOLE** -- `source_import_names` drops extra_requirements keys only when use_reqs is true, and `options.extra_requirements` is populated only on a --reqs run -- where the real value is already True. Substituting True is a no-op everywhere it is not identity. | was a hole |
| `pipeline.py:837` (run) -> `verify.source_import_names` | `positional 2` | `False` | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |  |
| `pipeline.py:844` (run) -> `run_script` | `positional 0` | `"/tmp/wrong-python"` | `test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` | was a hole |
| `pipeline.py:844` (run) -> `run_script` | `positional 1` | `Path("/tmp/wrong-script.py")` | `test_cli_entry_point::test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`<br>`test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` | was a hole |
| `pipeline.py:844` (run) -> `run_script` | `positional 2` | `[]` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` | was a hole |
| `pipeline.py:844` (run) -> `run_script` | `rawlog` | `True` | **DEAD ARGUMENT** -- No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site leaves `announce` at its False default. | was a hole |
| `pipeline.py:844` (run) -> `run_script` | `rawlog` | `False` | **DEAD ARGUMENT** -- No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site leaves `announce` at its False default. | was a hole |
| `pipeline.py:844` (run) -> `run_script` | `announce` | `True` | `test_cli_entry_point::test_only_the_venv_launch_announces_the_command_it_is_about_to_run` | was a hole |
| `pipeline.py:863` (run) -> `getattr` | `positional 1` | `"wrongflag"` | `test_cli_entry_point::test_no_cache_skips_the_cache_search_entirely` | was a hole |
| `pipeline.py:863` (run) -> `getattr` | `positional 0` | `object()` | `test_cli_entry_point::test_no_cache_skips_the_cache_search_entirely` | *not reached* |
| `pipeline.py:863` (run) -> `getattr` | `positional 2` | `True` | **OPEN HOLE** -- `--no-cache` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. | *not reached* |
| `pipeline.py:863` (run) -> `getattr` | `positional 2` | `False` | *identity -- the call site already carries this value* | *not reached* |
| `pipeline.py:866` (run) -> `cache_search.find_match_dir_in_cache` | `positional 0` | `object()` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search`<br>`test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |  |
| `pipeline.py:866` (run) -> `cache_search.find_match_dir_in_cache` | `my_dir` | `Path("/tmp/wrong-venv")` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |  |
| `pipeline.py:866` (run) -> `cache_search.find_match_dir_in_cache` | `venv_name` | `"wrongname"` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |  |
| `pipeline.py:866` (run) -> `cache_search.find_match_dir_in_cache` | `uninstalled` | `set()` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |  |
| `pipeline.py:866` (run) -> `cache_search.find_match_dir_in_cache` | `extra_requirements` | `{}` | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |  |
| `pipeline.py:866` (run) -> `cache_search.find_match_dir_in_cache` | `source_names` | `frozenset()` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search`<br>`test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |  |
| `pipeline.py:866` (run) -> `cache_search.find_match_dir_in_cache` | `tag` | `"9.9"` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |  |
| `pipeline.py:866` (run) -> `cache_search.find_match_dir_in_cache` | `rawlog` | `True` | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |  |
| `pipeline.py:866` (run) -> `cache_search.find_match_dir_in_cache` | `rawlog` | `False` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search`<br>`test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |  |
| `pipeline.py:866` (run) -> `cache_search.find_match_dir_in_cache` | `load_last_used` | `lambda: None` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search`<br>`test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |  |
| `pipeline.py:872` (run) -> `verify.source_import_names` | `positional 0` | `set()` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search`<br>`test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |  |
| `pipeline.py:872` (run) -> `verify.source_import_names` | `positional 1` | `{}` | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |  |
| `pipeline.py:872` (run) -> `verify.source_import_names` | `positional 2` | `True` | **OPEN HOLE** -- `source_import_names` drops extra_requirements keys only when use_reqs is true, and `options.extra_requirements` is populated only on a --reqs run -- where the real value is already True. Substituting True is a no-op everywhere it is not identity. | was a hole |
| `pipeline.py:872` (run) -> `verify.source_import_names` | `positional 2` | `False` | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |  |
| `pipeline.py:877` (run) -> `cache_search.interpreter_tag` | `positional 0` | `stdlib_index.StdlibIndex(names=frozenset(), python_version=(9, 9), source="wrong")` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |  |
| `pipeline.py:879` (run) -> `_load_last_used` | `positional 0` | `run_options.Options()` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search`<br>`test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |  |
| `pipeline.py:886` (run) -> `setup_virtualenv` | `positional 0` | `run_options.Options()` | `test_cli_entry_point::test_main_builds_an_environment_when_the_cache_misses`<br>`test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built` |  |
| `pipeline.py:904` (run) -> `options.set_venv_dir` | `positional 0` | `Path("/tmp/wrong-venv")` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_main_builds_an_environment_when_the_cache_misses`<br>`test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built`<br>(+2 more) |  |
| `pipeline.py:909` (run) -> `run_script` | `positional 0` | `"/tmp/wrong-python"` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_main_builds_an_environment_when_the_cache_misses`<br>`test_cli_entry_point::test_main_runs_the_script_under_the_cached_venvs_interpreter_on_a_cache_hit`<br>(+1 more) |  |
| `pipeline.py:909` (run) -> `run_script` | `positional 1` | `Path("/tmp/wrong-script.py")` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through`<br>`test_cli_entry_point::test_main_builds_an_environment_when_the_cache_misses`<br>`test_cli_entry_point::test_main_runs_the_script_under_the_cached_venvs_interpreter_on_a_cache_hit`<br>(+1 more) |  |
| `pipeline.py:909` (run) -> `run_script` | `positional 2` | `[]` | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` | was a hole |
| `pipeline.py:909` (run) -> `run_script` | `rawlog` | `True` | `test_cli_entry_point::test_only_the_venv_launch_announces_the_command_it_is_about_to_run` | was a hole |
| `pipeline.py:909` (run) -> `run_script` | `rawlog` | `False` | `test_cli_entry_point::test_only_the_venv_launch_announces_the_command_it_is_about_to_run` | was a hole |
| `pipeline.py:909` (run) -> `run_script` | `announce` | `True` | *identity -- the call site already carries this value* |  |
| `pipeline.py:909` (run) -> `run_script` | `announce` | `False` | `test_cli_entry_point::test_only_the_venv_launch_announces_the_command_it_is_about_to_run` | was a hole |
| `pipeline.py:927` (run) -> `options.venv_dir.name.startswith` | `positional 0` | `"wrongname"` | `test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built` |  |
| `pipeline.py:931` (run) -> `options.set_venv_dir` | `positional 0` | `Path("/tmp/wrong-venv")` | `test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built` |  |
| `pipeline.py:932` (run) -> `cache_search.rename_venv` | `positional 0` | `Path("/tmp/wrong-venv")` | `test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built` |  |
| `pipeline.py:932` (run) -> `cache_search.rename_venv` | `positional 1` | `"wrongname"` | `test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built` |  |
| `pipeline.py:934` (run) -> `options.venv_dir.name.removeprefix` | `positional 0` | `"wrongname"` | `test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built` |  |
| `pipeline.py:938` (run) -> `ek.save_options_to_json` | `positional 0` | `run_options.Options()` | **OPEN HOLE** -- `ek.save_options_to_json` is stubbed in every in-process run because the real one writes a JSON file into the working directory; emmykit owns both its name and its contents. | was a hole |

## Every DEAD ARGUMENT, in one place (17 rows)

These are not test gaps and no test can close them: the callee never reads
the value, or the value has no effect at this call site. They are deletion
candidates for phase 4, counted separately from the open holes so the two
are not blurred together.

| Site | Argument | Substituted with | Why |
|---|---|---|---|
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `my_name` | `"wrongname"` | Dead argument: `analysis.scan` reads only `settings.rawlog` off the Settings it is handed. `my_name` is never read at this call site. |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `cwd` | `Path("/tmp/wrong-dir")` | Dead argument: `analysis.scan` reads only `settings.rawlog`. `cwd` is never read at this call site. |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `stay_out_list` | `()` | Dead argument: `analysis.scan` reads only `settings.rawlog`. `stay_out_list` is never read at this call site. |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `search_above_this_dir` | `True` | Dead argument: `analysis.scan` reads only `settings.rawlog`. `search_above_this_dir` is never read at this call site. |
| `pipeline.py:125` (find_imports_in_script) -> `Settings` | `search_above_this_dir` | `False` | Dead argument: `analysis.scan` reads only `settings.rawlog`. `search_above_this_dir` is never read at this call site. |
| `pipeline.py:201` (is_importable) -> `alias_index.ResolvedImport` | `pip_name` | `"wrongname"` | Dead argument: `check_packages_in_venv`'s single-record branch checks `record.import_name` and nothing else. The probe supplies `pip_name=import_name` only because ResolvedImport requires both. |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `loaded_custom_modules` | `set()` | Dead argument: `classify.split_imports` reads only `scan.all_imports`, `scan.custom_modules` and `scan.seen_stdlib_imports`. |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `samedir_files` | `[]` | Dead argument: `classify.split_imports` reads only `scan.all_imports`, `scan.custom_modules` and `scan.seen_stdlib_imports`. |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `subfolders` | `[]` | Dead argument: `classify.split_imports` reads only `scan.all_imports`, `scan.custom_modules` and `scan.seen_stdlib_imports`. |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `sys_path_hints` | `set()` | Dead argument: `classify.split_imports` reads only `scan.all_imports`, `scan.custom_modules` and `scan.seen_stdlib_imports`. |
| `pipeline.py:222` (split_imports) -> `ImportScan` | `seen_stdlib_imports` | `set()` | Effectively dead: `classify.split_imports` returns it as `Requirements.seen_stdlib`, but `pipeline.split_imports` copies back only all_imports, bad, uninstalled and total_imports, so nothing downstream can observe it. |
| `pipeline.py:451` (feeling_lucky) -> `run_script` | `rawlog` | `True` | No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site passes `announce=False`. |
| `pipeline.py:451` (feeling_lucky) -> `run_script` | `rawlog` | `False` | No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site passes `announce=False`. |
| `pipeline.py:821` (run) -> `run_script` | `rawlog` | `True` | No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site leaves `announce` at its False default. |
| `pipeline.py:821` (run) -> `run_script` | `rawlog` | `False` | No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site leaves `announce` at its False default. |
| `pipeline.py:844` (run) -> `run_script` | `rawlog` | `True` | No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site leaves `announce` at its False default. |
| `pipeline.py:844` (run) -> `run_script` | `rawlog` | `False` | No effect at this call site: `run_script` reads `rawlog` only to guard the announce line, and this site leaves `announce` at its False default. |

## Every OPEN HOLE, in one place (30 rows)

The roll-up, so the count can be audited without reading 278 rows. None is a
case of "a test could see this and none does" left unwritten out of
convenience: each is an argparse default a real command line cannot reach, an
effect emmykit owns, a callee stubbed at a subprocess or filesystem boundary,
a branch no run can construct, or a substitution the code makes
indistinguishable from the real value. Two are marked **Conditional** --
they reopen once a named change lands.

| Site | Argument | Substituted with | Why |
|---|---|---|---|
| `cli.py:173` (main) -> `getattr` | `positional 2` | `["wrongarg"]` | argparse's REMAINDER always sets `script_args`, so this getattr default is unreachable from any real command line; only a hand-built Namespace could ever see it. |
| `cli.py:174` (main) -> `getattr` | `positional 2` | `True` | `--rawlog` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. |
| `cli.py:198` (main) -> `ek.print_all_errors` | `positional 0` | `None` | emmykit owns `print_all_errors`, and every in-process run stubs `ek.configure_logging`, so the handler really is None on those runs: `None` is the value the site already carries under test. |
| `cli.py:198` (main) -> `ek.print_all_errors` | `positional 1` | `True` | emmykit owns the effect -- which buffered ERROR records get replayed, and in what format. No veny-visible record changes either way. |
| `cli.py:198` (main) -> `ek.print_all_errors` | `positional 1` | `False` | emmykit owns the effect -- which buffered ERROR records get replayed, and in what format. No veny-visible record changes either way. |
| `cli.py:156` (parse_arguments) -> `getattr` | `positional 2` | `True` | `-d/--debug` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. |
| `pipeline.py:409` (resolve_target) -> `getattr` | `positional 2` | `"/tmp/wrong-script.py"` | argparse's `nargs="?"` always sets `script` (to None when absent), so this getattr default is unreachable from any real command line. |
| `pipeline.py:413` (resolve_target) -> `ek.ensure_file` | `raise_on_empty` | `False` | Distinguishable only when the script argument is an empty string. argparse never produces one from a real command line, and no test builds that Namespace by hand. |
| `pipeline.py:413` (resolve_target) -> `ek.ensure_file(script_string, raise_on_empty=True).resolve` | `strict` | `False` | With `strict=False` a nonexistent script resolves silently and the run fails later. Today a missing script leaves `FileNotFoundError` to travel out of `main` uncaught; asserting that as the contract would pin a defect rather than a behaviour, so this is left open for the exit-status work rather than nailed down here. |
| `pipeline.py:483` (blank_slate) -> `getattr` | `positional 1` | `"wrongflag"` | The site is already misspelled: argparse gives `-y/--yes` the dest `yes`, so `getattr(options.args, "y", False)` is always False and `"y"` and `"wrongflag"` are indistinguishable. Recorded, not fixed -- this phase is behaviour-preserving; see test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone. |
| `pipeline.py:495` (blank_slate) -> `shutil.rmtree` | `ignore_errors` | `False` | `pipeline.run` creates `options.my_dir` a few lines before it reaches the --blank-slate branch, so `shutil.rmtree` never sees a missing directory on any path a run can take. |
| `pipeline.py:656` (setup_virtualenv) -> `verify.source_import_names` | `positional 2` | `True` | `source_import_names` drops extra_requirements keys only when use_reqs is true, and `options.extra_requirements` is populated only on a --reqs run -- where the real value is already True. Substituting True is a no-op everywhere it is not identity. |
| `pipeline.py:738` (run) -> `stdlib_index.resolve` | `positional 0` | `"wrongname"` | Every test that reaches `pipeline.run` replaces `stdlib_index.resolve`: the real one spawns an interpreter probe subprocess, which the in-process driver exists to avoid. |
| `pipeline.py:748` (run) -> `build_alias_index` | `positional 0` | `run_options.Options()` | Every test that reaches `pipeline.run` replaces `build_alias_index` wholesale (the real one probes an interpreter and may reach PyPI), so the Options it is handed is never read. Its own two arguments are pinned at `pipeline.py:91`. |
| `pipeline.py:763` (run) -> `options.my_dir.mkdir` | `parents` | `False` | `parents` matters only when my_dir's parent is missing, and my_dir is `Path.home() / "veny"` -- no run can produce a missing home directory. |
| `pipeline.py:763` (run) -> `options.my_dir.mkdir` | `exist_ok` | `False` | Unreachable: the mkdir runs only on the branch where `ek.safe_is_dir(options.my_dir)` has just said the directory is absent. |
| `pipeline.py:768` (run) -> `blank_slate` | `positional 0` | `run_options.Options()` | **Conditional, not permanent.** A fresh Options built under the same HOME and working directory carries the same my_dir, my_name and cwd, and its empty args Namespace makes the -y read False exactly as the real one does -- but only because of the `y`/`yes` dest bug recorded above. Fix that dest and this row reopens: the real Options would then answer True to `-y` and the fresh one False. A distinguishing substitution today would need an Options whose my_dir differs, which main() gives a test no way to inject. |
| `pipeline.py:788` (run) -> `Settings` | `stay_out_list` | `()` | **Conditional, not permanent.** `dict_of_custom_modules` consults stay_out_list only through `is_standard_path`, and the test that drives the real scan narrows sys.path to a temporary directory that matches no entry either way. It becomes measurable the moment that test plants a sys.path entry whose name matches a stay-out fragment (see `src/veny/analysis/custom_modules.py:39`). |
| `pipeline.py:788` (run) -> `Settings` | `search_above_this_dir` | `True` | Identity in effect: `Options.search_above_this_dir` defaults to True and nothing in the suite sets it False, so this direction substitutes the value the run already carries. |
| `pipeline.py:837` (run) -> `verify.source_import_names` | `positional 2` | `True` | `source_import_names` drops extra_requirements keys only when use_reqs is true, and `options.extra_requirements` is populated only on a --reqs run -- where the real value is already True. Substituting True is a no-op everywhere it is not identity. |
| `pipeline.py:872` (run) -> `verify.source_import_names` | `positional 2` | `True` | `source_import_names` drops extra_requirements keys only when use_reqs is true, and `options.extra_requirements` is populated only on a --reqs run -- where the real value is already True. Substituting True is a no-op everywhere it is not identity. |
| `pipeline.py:938` (run) -> `ek.save_options_to_json` | `positional 0` | `run_options.Options()` | `ek.save_options_to_json` is stubbed in every in-process run because the real one writes a JSON file into the working directory; emmykit owns both its name and its contents. |
| `pipeline.py:483` (blank_slate) -> `getattr` | `positional 0` | `object()` | Same root cause as the flag name below: argparse's dest for `-y/--yes` is `yes`, so `options.args` never carries a `y` attribute and a receiver with no attributes at all behaves identically. The *default* at this site is pinned, precisely because the dest bug makes it the only part that is read. |
| `pipeline.py:441` (feeling_lucky) -> `getattr` | `positional 2` | `True` | `--feeling-lucky` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. |
| `pipeline.py:767` (run) -> `getattr` | `positional 2` | `True` | `--blank-slate` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. |
| `pipeline.py:776` (run) -> `getattr` | `positional 2` | `True` | `--reqs` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. |
| `pipeline.py:797` (run) -> `getattr` | `positional 2` | `True` | `--rc` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. |
| `pipeline.py:798` (run) -> `getattr` | `positional 2` | `True` | `--no-cache` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. |
| `pipeline.py:814` (run) -> `getattr` | `positional 2` | `True` | `--justprint` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. |
| `pipeline.py:863` (run) -> `getattr` | `positional 2` | `True` | `--no-cache` is a store_true, so argparse always sets the attribute and this getattr default is unreachable from any real command line. |
