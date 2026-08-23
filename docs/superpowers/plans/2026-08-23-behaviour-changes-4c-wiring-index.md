# Phase 4c wiring index — every argument, measured

**What was swept.** Every argument at every call site phase 4c created or
changed — **189 arguments across 55 distinct callees** in
`src/veny/last_used.py`, `src/veny/pipeline.py`, `src/veny/cache_search.py`
and `src/veny/cli.py`. The harness is `scripts/wiring_sweep_4c.py`, a
re-scope of phase 4b's onto the code phase 4c's four behaviour changes
touched: the in-virtualenv guard now reading `VIRTUAL_ENV` (Task 1), the
shared exit-status arithmetic in `cli._shell_status` (Task 2), `-y` reaching
`blank_slate` (Task 3), and `announce=True` at all four `run_script` call
sites (Task 4).

> **This table is keyed on `file:line`, and the harness rewrites expressions
> by source position. Any later edit to a swept module invalidates every row
> below the edit, and the sweep must be re-run before that edit's phase
> closes.** Re-running is cheap — one `pixi run python
> scripts/wiring_sweep_4c.py`, about twelve minutes — and reading a stale
> table is not. This is the same caveat 4b's index carried, restated for
> this phase's scope.

**Which code counts as "this phase".** Decided from the structure of the
modules, in `scoped_calls()`, not from a hand-written list of names — 3e's
symbol sweep worked from a list and missed a whole spelling, and this
convention exists so that cannot recur. The four rules, from
`scripts/wiring_sweep_4c.py`:

1. **`last_used.py` entire** — Task 1 rewrote its virtualenv answer
   (`active_virtualenv_dir` now reads `VIRTUAL_ENV` instead of veny's own
   interpreter prefix).
2. **`pipeline.feeling_lucky`, `pipeline.blank_slate` and `pipeline.run_script`
   entire**, plus every `run_script(...)` call inside `pipeline.run` (all
   four call sites Task 4 gave `announce=True`: one in `feeling_lucky`,
   three in `run`) and the whole of `run`'s rewritten middle branch — the
   `elif (active_venv := last_used.active_virtualenv_dir()) is not None:`
   clause Task 1 introduced, test and body, but **not** its `else` (the
   venv-build path, untouched by Task 1 and already covered by the
   "every `run_script(...)` call inside `run`" half of this rule).
3. **`cache_search.find_match_dir_in_cache`'s last-used pass**, from the top
   of the function down to the statement that spends it — unchanged from
   4b's rule; phase 4c did not touch this function above the cutoff, only
   the line numbers moved. Below that line is the
   `--latest`/`--oldest`/`--smallest` ranking, swept by phase 3d.
4. **`cli.main` entire, plus `cli._shell_status`.** Task 2 added
   `_shell_status` and routed both of `main`'s exit paths through it.

Within those scopes *every* call is swept, including `logging` and `print`
arguments, following 4b's convention that veny's own commentary is
behaviour, not decoration.

**How each row was measured.** The argument's expression is replaced, in
place, with a type-correct but wrong value; the four modules are
import-checked; then the whole suite runs. The first test to fail is the
named killer. Nothing fails: **OPEN HOLE**. No sensible substitute exists
(an `int`/local value the substitution table has no rule for): **NO
SUBSTITUTE**. A multi-line expression the harness cannot rewrite in place:
**MULTILINE**, measured by a driving test instead. `apply()` refuses to run
a substitution that reproduces the original text — such a row would score
as an OPEN HOLE with no signal in it at all.

**The trap, recorded again because it cost phase 4a a whole sweep.**
`pixi run` sets `PYTHONPATH=src`, and `tests/test_import_guard.py` spawns
its own subprocess that needs it; the harness sets it directly and
import-checks every mutated tree before believing a failure. Zero INVALID
and zero ERROR rows below, which is what that buys.

**A second trap, found and fixed while re-scoping this harness from 4b's,
before the full run: an `announce` no-op.** The substitution table mapped
the argument name `announce` unconditionally to the literal `"True"`. Before
phase 4c that was harmless — only one of the four `run_script` call sites
passed `announce=True` at all. Phase 4c's Task 4 made all four pass the
literal `announce=True`, so substituting the same literal `"True"` over
itself is a no-op — exactly what `apply()`'s guard exists to catch, and it
would have raised `RuntimeError` partway through the twelve-minute run.
Fixed by deleting the `"announce"` entry from `BY_NAME`: the generic
True/False literal flip already in `substitute_for` produces the correct,
non-no-op substitution (`announce=True` → `announce=False`), confirmed
against all 189 sites before the full run (`no-op risk sites: 0`).

## The headline

What the sweep printed: **189 rows — 155 KILLED, 14 OPEN HOLE, 2 MULTILINE,
18 NO SUBSTITUTE.** The harness itself never emits a `DEAD` verdict — it is
a disposition assigned here, during this index's writing, to the OPEN HOLE
rows that are unreachable by construction rather than merely untested. Of
the 189:

| | |
|---|---|
| Arguments swept | **189** |
| Killed by a named test | **155** |
| Measured by driving rather than substitution | **2** |
| NO SUBSTITUTE (no fabricable wrong value for a local int/name) | **18** |
| DEAD ARGUMENT | **1** |
| OPEN HOLE | **13** |

155 + 2 + 18 + 1 + 13 = 189.

**0 DEAD from the harness is itself a result, and it reconciles cleanly
against Task 5's list.** `docs/superpowers/plans/2026-08-23-behaviour-changes-4c-dead-arguments.md`
closed eight of the ten prior dead-argument rows by deleting or converting
the code they lived in (Tasks 4 and 5); none of that deleted code is in this
sweep's scope any more, so none of it can show up here as DEAD or as
anything else. The two rows that document left OPEN (the `ResolvedImport`
probe-indistinguishable-by-construction row and the mis-filed
`VenvHandle.for_dir` row) are both **outside this sweep's scope** — neither
lives in `feeling_lucky`, `blank_slate`, `run_script`, the swept part of
`run`, the swept part of `find_match_dir_in_cache`, `main`, or
`_shell_status` — so they correctly do not appear in the table below either.
That leaves the sweep free to find its own dead rows from scratch, and it
found exactly one.

## NEW FINDING: a dead argument default Task 5's list does not cover

**`pipeline.py:853` `getattr(args, "reqs", False)`'s third argument (the
default).** Inside `run`'s rewritten `elif` branch (the "already in an
activated virtualenv" path), `source_names` is computed as
`verify.source_import_names(set(requirements.all_imports),
requirements.extra_requirements, getattr(args, "reqs", False))`. Every one
of veny's flags is `action="store_true"`, so argparse always defines
`args.reqs` and no real command line can reach the `False` default — this is
exactly Task 5's reasoning for the sibling `getattr(args, "reqs", False)` in
`run`'s final `else` branch (closed by converting it to a direct
`args.reqs` read), but that conversion did not reach this second, elif-side
occurrence of the same construct. Substituting the outer `getattr(...)` call
as a whole (`not getattr(args, "reqs", False)`) is **KILLED** — the
`explicit`/`reqs`-derived value does reach a test — but substituting only
the innermost default (`False` → `True`) is **OPEN HOLE**, which is the
signature of a default nothing can reach. Reclassified `DEAD` in the table
below. Not deleted here — Task 6 is measurement only, and (per the
established convention) the argument and the `getattr` wrapper around it are
one unit; deleting one without the other would break a hand-built
`argparse.Namespace()` that omits `reqs`. Left for a future task to close
the same way Task 5 closed its sibling.

## The four `run_script` sites Task 4 changed

All four of `run_script`'s `announce=True` arguments — `pipeline.py:437`
(`feeling_lucky`), `:839`, `:862` and `:943` (the three call sites inside
`run`) — came back **KILLED**, all four by
`tests/test_cli_entry_point.py::test_every_launch_announces_the_command_it_is_about_to_run`,
exactly as expected: that test drives all four launch paths and asserts the
`Running command: …` log line at each.

## The 13 OPEN HOLEs, each with its reason

1. **`last_used.py:90` `path.write_text(encoding='utf-8')`.** The **writer**
   only. Everything `save` writes is ASCII (`json.dumps` escapes non-ASCII by
   default), and utf-8 and latin-1 agree on ASCII, so no payload `save` can
   produce distinguishes them. Unchanged from 4b's index (there at line 87);
   only the line number moved. The **read** side, `last_used.py:123`'s
   `encoding`, is a different question and is not open — it is KILLED by
   `test_wiring_4b::test_a_record_veny_did_not_write_is_decoded_as_utf_8`.
2. **`last_used.py:90` `json.dumps(indent=4)`.** Cosmetic; the only reader is
   `json.loads`, which does not care about whitespace. Unchanged from 4b's
   index (there at line 87).
3. **`pipeline.py:469` `logging.info('Exiting without deleting anything.')`**
   — the decline branch of `blank_slate`. Reachable (exercised by
   `test_declining_the_blank_slate_confirmation_deletes_nothing`), but that
   test asserts on the return status and the prompt text, not this
   informational log line's exact string.
4. **`pipeline.py:473`/`:474` `logging.info(..., settings.my_name,
   settings.my_name)`** — the confirmed-delete branch's announcement.
   Reachable on every `--blank-slate` run that deletes, but no test asserts
   on this log line's exact text or its two `%s` substitutions.
5. **`pipeline.py:479` `logging.debug('Checking %s', file)`.** Gated behind
   `isEnabledFor(logging.DEBUG)`; no test runs `blank_slate` with debug
   logging enabled, so this branch's content is never observed.
6. **`pipeline.py:487` `file.name.startswith(f'.{settings.my_name}-')`** and
   **`pipeline.py:491` `file.name.startswith(f'.{settings.my_name}_custom_modules_')`.**
   Two of the four OR'd filename filters `blank_slate` uses to decide what to
   delete (the `.out`/`.err` filter and the custom-modules `.pkl` filter,
   respectively). Both are reachable — real files of those shapes would
   engage them — but no test in the suite constructs a state directory
   containing a file that only one specific OR-branch matches, so flipping
   either literal to `"wiring-probe"` still leaves every existing test
   passing.
7. **`pipeline.py:504` `logging.exception('Error deleting %s', file)`** —
   inside the `except BaseException` around `file.unlink()`. Reachable only
   when a delete fails (e.g. a permission error), which no test constructs.
8. **`pipeline.py:846` `logging.info('Already in a virtual environment.')`**
   — the elif branch's opening announcement. Reachable on every run that
   takes this branch (several tests do, including
   `test_main_checks_the_surrounding_virtualenv_against_this_runs_imports`),
   but nothing asserts on this exact log text.
9. **`pipeline.py:869` `logging.error('The current virtual environment does
   not have all the required packages.')`** and **`pipeline.py:873`
   `logging.info('Please deactivate the current virtual environment and run
   the script again.')`** — the mismatch branch, reached when the activated
   virtualenv fails the package check. No test in scope drives this specific
   sub-branch (every test that reaches the elif stubs `check_packages_in_venv`
   to return `True`), so these two lines' exact text is unobserved.
10. **`cli.py:221` `Path.cwd().expanduser().resolve(strict=True)`.** `strict`
    only bites on a working directory deleted out from under the process; no
    portable way to construct that in a test, and the failure it would
    produce (`FileNotFoundError`) is the desired one regardless. Unchanged
    from 4b's index (there at `cli.py:201`).

## Measured by driving rather than substitution (2)

Multi-line expressions the harness cannot rewrite in place. Each is measured
by a test that drives it instead:

| Expression | Site | How it is measured |
|---|---|---|
| `ek.prompt_then_confirm(f'Are you sure you want to delete everything in ~/{settings.my_name}/…')` | `pipeline.py:466` | `test_declining_the_blank_slate_confirmation_deletes_nothing`, which asserts the exact prompt text `ek.prompt_then_confirm` was called with |
| `verify.source_import_names(set(requirements.all_imports), requirements.extra_requirements, getattr(args, "reqs", False))` passed as `check_packages_in_venv`'s `source_names` | `pipeline.py:850` | `test_main_checks_the_surrounding_virtualenv_against_this_runs_imports`, which spies on `check_packages_in_venv` and asserts `source_names == {"thing"}` end to end |

## The 18 NO SUBSTITUTE rows

Arguments the substitution table has no rule for: local variable names
(`file`, `arg`, `interpreter`, `script`, `command_list`, `active_venv`,
`elapsed_raw_time`, `lucky_status`, `script_exit_code`), a generator
expression, and `logging.DEBUG` itself. All are either plain local
references the table's by-name/by-expression rules do not cover, or (for
`cli.py:240`/`:262`'s `_shell_status(...)` calls) an `int` for which no
"type-correct but wrong" value is fabricated by this harness. This is an
allowed verdict per the task brief, not a gap: the two `_shell_status`
call sites' behaviour (does a killed-by-signal return code map to `128 +
signal` on both exit paths) is exercised by
`test_a_lucky_run_killed_by_a_signal_reports_the_shell_status` and
`test_an_ordinary_run_killed_by_a_signal_reports_the_shell_status` directly,
just not through this harness's substitution mechanism.

## Every argument, measured

| Site | Argument | Expression | Substitute | Verdict | Killed by |
|---|---|---|---|---|---|
| `last_used.py:37` (os.environ.get) | `positional 0` | `'VIRTUAL_ENV'` | `"WIRING_PROBE_ENV"` | KILLED | test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports |
| `last_used.py:40` (ek.ensure_path) | `positional 0` | `declared` | `"/tmp/veny-wiring-probe"` | KILLED | test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports |
| `last_used.py:84` (record_path) | `positional 0` | `script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built |
| `last_used.py:84` (record_path) | `positional 1` | `python_script` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:84` (record_path) | `positional 2` | `my_name` | `"wiring-probe"` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:86` (os.fspath) | `positional 0` | `record.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:87` (os.fspath) | `positional 0` | `record.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/b…` | KILLED | test_last_used::test_a_saved_record_is_read_back_as_the_same_paths |
| `last_used.py:90` (path.write_text) | `positional 0` | `json.dumps(payload, indent=4) + '\n'` | `"{}\n"` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:90` (path.write_text) | `encoding` | `'utf-8'` | `"latin-1"` | OPEN HOLE | **see below** |
| `last_used.py:90` (json.dumps) | `positional 0` | `payload` | `{}` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:90` (json.dumps) | `indent` | `4` | `0` | OPEN HOLE | **see below** |
| `last_used.py:121` (record_path) | `positional 0` | `script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:121` (record_path) | `positional 1` | `python_script` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:121` (record_path) | `positional 2` | `my_name` | `"wiring-probe"` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:123` (json.loads) | `positional 0` | `path.read_text(encoding='utf-8')` | `"{}"` | KILLED | test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs |
| `last_used.py:123` (path.read_text) | `encoding` | `'utf-8'` | `"latin-1"` | KILLED | test_wiring_4b::test_a_record_veny_did_not_write_is_decoded_as_utf_8 |
| `last_used.py:126` (logging.info) | `positional 0` | `'No usable last-used record for %s.'` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs |
| `last_used.py:126` (logging.info) | `positional 1` | `os.fspath(python_script)` | `"/tmp/veny-wiring-probe"` | KILLED | test_last_used::test_the_venv_python_loader_lets_the_record_search_explain_itself |
| `last_used.py:126` (os.fspath) | `positional 0` | `python_script` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_last_used::test_the_venv_python_loader_lets_the_record_search_explain_itself |
| `last_used.py:128` (isinstance) | `positional 0` | `payload` | `{}` | KILLED | test_last_used::test_a_damaged_record_is_none_and_not_a_crash[not-an-object] |
| `last_used.py:128` (isinstance) | `positional 1` | `dict` | `object` | KILLED | test_last_used::test_a_damaged_record_is_none_and_not_a_crash[not-an-object] |
| `last_used.py:130` (logging.info) | `positional 0` | `'Last-used record %s is not an object.'` | `"wiring-probe"` | KILLED | test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[not-an-object] |
| `last_used.py:130` (logging.info) | `positional 1` | `os.fspath(path)` | `"/tmp/veny-wiring-probe"` | KILLED | test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[not-an-object] |
| `last_used.py:130` (os.fspath) | `positional 0` | `path` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[not-an-object] |
| `last_used.py:132` (payload.get) | `positional 0` | `'venv_dir'` | `"wiring_probe_venv_dir"` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:133` (payload.get) | `positional 0` | `'venv_python'` | `"wiring_probe_venv_python"` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:134` (isinstance) | `positional 0` | `venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:134` (isinstance) | `positional 1` | `str` | `object` | KILLED | test_wiring_4b::test_a_record_whose_path_is_not_a_string_is_refused[venv_dir-a-number] |
| `last_used.py:134` (isinstance) | `positional 0` | `venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/b…` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:134` (isinstance) | `positional 1` | `str` | `object` | KILLED | test_wiring_4b::test_a_record_whose_path_is_not_a_string_is_refused[venv_python-a-list] |
| `last_used.py:136` (logging.info) | `positional 0` | `'Last-used record %s names no environment.'` | `"wiring-probe"` | KILLED | test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[no-environment] |
| `last_used.py:136` (logging.info) | `positional 1` | `os.fspath(path)` | `"/tmp/veny-wiring-probe"` | KILLED | test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[no-environment] |
| `last_used.py:136` (os.fspath) | `positional 0` | `path` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[no-environment] |
| `last_used.py:140` (logging.info) | `positional 0` | `'Last-used record %s names an empty path.'` | `"wiring-probe"` | KILLED | test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[empty-path] |
| `last_used.py:140` (logging.info) | `positional 1` | `os.fspath(path)` | `"/tmp/veny-wiring-probe"` | KILLED | test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[empty-path] |
| `last_used.py:140` (os.fspath) | `positional 0` | `path` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[empty-path] |
| `last_used.py:142` (payload.get) | `positional 0` | `'timestamp'` | `"wiring_probe_timestamp"` | KILLED | test_last_used::test_a_saved_record_is_read_back_as_the_same_paths |
| `last_used.py:144` (state.LastUsed) | `venv_dir` | `ek.ensure_path(venv_dir)` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:145` (state.LastUsed) | `venv_python` | `ek.ensure_path(venv_python)` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/b…` | KILLED | test_last_used::test_a_saved_record_is_read_back_as_the_same_paths |
| `last_used.py:146` (state.LastUsed) | `timestamp` | `timestamp if isinstance(timestamp, str) else ''` | `"20000101-000000"` | KILLED | test_last_used::test_a_saved_record_is_read_back_as_the_same_paths |
| `last_used.py:144` (ek.ensure_path) | `positional 0` | `venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to |
| `last_used.py:145` (ek.ensure_path) | `positional 0` | `venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/b…` | KILLED | test_last_used::test_a_saved_record_is_read_back_as_the_same_paths |
| `last_used.py:146` (isinstance) | `positional 0` | `timestamp` | `"20000101-000000"` | KILLED | test_wiring_4b::test_a_record_whose_timestamp_is_not_a_string_still_loads |
| `last_used.py:146` (isinstance) | `positional 1` | `str` | `object` | KILLED | test_wiring_4b::test_a_record_whose_timestamp_is_not_a_string_still_loads |
| `last_used.py:170` (load) | `script_dir` | `script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_last_used::test_load_venv_python_returns_the_recorded_interpreter |
| `last_used.py:171` (load) | `python_script` | `python_script` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_last_used::test_the_venv_python_loader_lets_the_record_search_explain_itself |
| `last_used.py:172` (load) | `my_name` | `my_name` | `"wiring-probe"` | KILLED | test_last_used::test_load_venv_python_returns_the_recorded_interpreter |
| `last_used.py:173` (load) | `rawlog` | `rawlog` | `True` | KILLED | test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs |
| `last_used.py:177` (logging.info) | `positional 0` | `'No last used record found, so no venv_python to return.'` | `"wiring-probe"` | KILLED | test_wiring_4b::test_the_lucky_reader_says_when_there_is_no_record_at_all |
| `last_used.py:179` (ek.safe_is_file) | `positional 0` | `record.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/b…` | KILLED | test_last_used::test_load_venv_python_returns_the_recorded_interpreter |
| `last_used.py:182` (logging.warning) | `positional 0` | `'Last used venv_python %s is no longer valid.'` | `"wiring-probe"` | KILLED | test_last_used::test_load_venv_python_is_none_when_the_interpreter_is_gone |
| `last_used.py:183` (logging.warning) | `positional 1` | `os.fspath(record.venv_python)` | `"/tmp/veny-wiring-probe"` | KILLED | test_wiring_4b::test_the_lucky_reader_names_the_interpreter_it_will_not_use |
| `last_used.py:183` (os.fspath) | `positional 0` | `record.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/b…` | KILLED | test_wiring_4b::test_the_lucky_reader_names_the_interpreter_it_will_not_use |
| `last_used.py:187` (logging.info) | `positional 0` | `'Last used venv_python found: %s'` | `"wiring-probe"` | KILLED | test_wiring_4b::test_the_lucky_reader_names_the_interpreter_it_found |
| `last_used.py:187` (logging.info) | `positional 1` | `os.fspath(record.venv_python)` | `"/tmp/veny-wiring-probe"` | KILLED | test_wiring_4b::test_the_lucky_reader_names_the_interpreter_it_found |
| `last_used.py:187` (os.fspath) | `positional 0` | `record.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/b…` | KILLED | test_wiring_4b::test_the_lucky_reader_names_the_interpreter_it_found |
| `pipeline.py:426` (last_used.load_venv_python) | `script_dir` | `target.script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script |
| `pipeline.py:427` (last_used.load_venv_python) | `python_script` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script |
| `pipeline.py:428` (last_used.load_venv_python) | `my_name` | `my_name` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script |
| `pipeline.py:429` (last_used.load_venv_python) | `rawlog` | `rawlog` | `True` | KILLED | test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs |
| `pipeline.py:433` (run_script) | `positional 0` | `last_used_venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/b…` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:434` (run_script) | `positional 1` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:435` (run_script) | `positional 2` | `list(target.script_args)` | `[]` | KILLED | test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through |
| `pipeline.py:436` (run_script) | `rawlog` | `rawlog` | `True` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:437` (run_script) | `announce` | `True` | `False` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:435` (list) | `positional 0` | `target.script_args` | `()` | KILLED | test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through |
| `pipeline.py:440` (print) | `positional 0` | `f'Script exited with status {returncode}'` | `"wiring-probe"` | KILLED | test_wiring_4b::test_feeling_lucky_reports_a_script_that_failed |
| `pipeline.py:444` (print) | `positional 0` | `'No luck: no last used virtual environment found. Running…` | `"wiring-probe"` | KILLED | test_wiring_4b::test_feeling_lucky_says_so_when_there_is_no_record |
| `pipeline.py:466` (ek.prompt_then_confirm) | `positional 0` | `f'Are you sure you want to delete everything in ~/{settin…` | `"wiring-probe"` | MULTILINE | **see below** |
| `pipeline.py:469` (logging.info) | `positional 0` | `'Exiting without deleting anything.'` | `"wiring-probe"` | OPEN HOLE | **see below** |
| `pipeline.py:472` (logging.info) | `positional 0` | `'Deleting everything in ~/%s/ and all %s .out and .err an…` | `"wiring-probe"` | KILLED | test_last_used::test_blank_slate_deletes_the_new_last_used_record |
| `pipeline.py:473` (logging.info) | `positional 1` | `settings.my_name` | `"wiring-probe"` | OPEN HOLE | **see below** |
| `pipeline.py:474` (logging.info) | `positional 2` | `settings.my_name` | `"wiring-probe"` | OPEN HOLE | **see below** |
| `pipeline.py:476` (shutil.rmtree) | `positional 0` | `settings.my_dir` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone |
| `pipeline.py:476` (shutil.rmtree) | `ignore_errors` | `True` | `False` | KILLED | test_last_used::test_blank_slate_deletes_the_new_last_used_record |
| `pipeline.py:478` (logging.getLogger().isEnabledFor) | `positional 0` | `logging.DEBUG` | `` | NO SUBSTITUTE |  |
| `pipeline.py:479` (logging.debug) | `positional 0` | `'Checking %s'` | `"wiring-probe"` | OPEN HOLE | **see below** |
| `pipeline.py:479` (logging.debug) | `positional 1` | `file` | `` | NO SUBSTITUTE |  |
| `pipeline.py:480` (ek.safe_is_file) | `positional 0` | `file` | `` | NO SUBSTITUTE |  |
| `pipeline.py:483` (file.name.startswith) | `positional 0` | `f'.{settings.my_name}-'` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone |
| `pipeline.py:487` (file.name.startswith) | `positional 0` | `f'.{settings.my_name}-'` | `"wiring-probe"` | OPEN HOLE | **see below** |
| `pipeline.py:491` (file.name.startswith) | `positional 0` | `f'.{settings.my_name}_custom_modules_'` | `"wiring-probe"` | OPEN HOLE | **see below** |
| `pipeline.py:495` (file.name.startswith) | `positional 0` | `'.'` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone |
| `pipeline.py:501` (logging.info) | `positional 0` | `'Deleting %s'` | `"wiring-probe"` | KILLED | test_last_used::test_blank_slate_deletes_the_new_last_used_record |
| `pipeline.py:501` (logging.info) | `positional 1` | `file` | `` | NO SUBSTITUTE |  |
| `pipeline.py:504` (logging.exception) | `positional 0` | `'Error deleting %s'` | `"wiring-probe"` | OPEN HOLE | **see below** |
| `pipeline.py:504` (logging.exception) | `positional 1` | `file` | `` | NO SUBSTITUTE |  |
| `pipeline.py:334` (os.fspath) | `positional 0` | `interpreter` | `` | NO SUBSTITUTE |  |
| `pipeline.py:334` (os.fspath) | `positional 0` | `script` | `` | NO SUBSTITUTE |  |
| `pipeline.py:335` (str) | `positional 0` | `arg` | `` | NO SUBSTITUTE |  |
| `pipeline.py:339` (logging.info) | `positional 0` | `'Running command: %s'` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_main_lets_the_requirements_reader_explain_a_missing_file |
| `pipeline.py:339` (logging.info) | `positional 1` | `' '.join((shlex.quote(arg) for arg in command_list))` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:339` (' '.join) | `positional 0` | `(shlex.quote(arg) for arg in command_list)` | `` | NO SUBSTITUTE |  |
| `pipeline.py:339` (shlex.quote) | `positional 0` | `arg` | `` | NO SUBSTITUTE |  |
| `pipeline.py:341` (subprocess.run) | `positional 0` | `command_list` | `` | NO SUBSTITUTE |  |
| `pipeline.py:835` (run_script) | `positional 0` | `sys.executable` | `` | NO SUBSTITUTE |  |
| `pipeline.py:836` (run_script) | `positional 1` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_cli_entry_point::test_main_runs_the_script_under_the_running_interpreter_when_nothing_is_missing |
| `pipeline.py:837` (run_script) | `positional 2` | `list(target.script_args)` | `[]` | KILLED | test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through |
| `pipeline.py:838` (run_script) | `rawlog` | `settings.rawlog` | `True` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:839` (run_script) | `announce` | `True` | `False` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:837` (list) | `positional 0` | `target.script_args` | `()` | KILLED | test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through |
| `pipeline.py:858` (run_script) | `positional 0` | `sys.executable` | `` | NO SUBSTITUTE |  |
| `pipeline.py:859` (run_script) | `positional 1` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:860` (run_script) | `positional 2` | `list(target.script_args)` | `[]` | KILLED | test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through |
| `pipeline.py:861` (run_script) | `rawlog` | `settings.rawlog` | `True` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:862` (run_script) | `announce` | `True` | `False` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:860` (list) | `positional 0` | `target.script_args` | `()` | KILLED | test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through |
| `pipeline.py:939` (run_script) | `positional 0` | `handle.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/b…` | KILLED | test_cli_entry_point::test_main_runs_the_script_under_the_cached_venvs_interpreter_on_a_cache_hit |
| `pipeline.py:940` (run_script) | `positional 1` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring-probe/s…` | KILLED | test_cli_entry_point::test_main_runs_the_script_under_the_cached_venvs_interpreter_on_a_cache_hit |
| `pipeline.py:941` (run_script) | `positional 2` | `list(target.script_args)` | `[]` | KILLED | test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through |
| `pipeline.py:942` (run_script) | `rawlog` | `settings.rawlog` | `True` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:943` (run_script) | `announce` | `True` | `False` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:941` (list) | `positional 0` | `target.script_args` | `()` | KILLED | test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through |
| `pipeline.py:846` (logging.info) | `positional 0` | `'Already in a virtual environment.'` | `"wiring-probe"` | OPEN HOLE | **see below** |
| `pipeline.py:848` (verify.check_packages_in_venv) | `positional 0` | `environment.venv_python_for(active_venv)` | `` | NO SUBSTITUTE |  |
| `pipeline.py:849` (verify.check_packages_in_venv) | `uninstalled` | `set(requirements.uninstalled)` | `set()` | KILLED | test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports |
| `pipeline.py:850` (verify.check_packages_in_venv) | `source_names` | `verify.source_import_names(set(requirements.all_imports),…` | `frozenset()` | MULTILINE | **see below** |
| `pipeline.py:848` (environment.venv_python_for) | `positional 0` | `active_venv` | `` | NO SUBSTITUTE |  |
| `pipeline.py:849` (set) | `positional 0` | `requirements.uninstalled` | `set()` | KILLED | test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports |
| `pipeline.py:851` (verify.source_import_names) | `positional 0` | `set(requirements.all_imports)` | `frozenset()` | KILLED | test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports |
| `pipeline.py:852` (verify.source_import_names) | `positional 1` | `requirements.extra_requirements` | `{}` | KILLED | test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports |
| `pipeline.py:853` (verify.source_import_names) | `positional 2` | `getattr(args, 'reqs', False)` | `not getattr(args, 'reqs', False)` | KILLED | test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports |
| `pipeline.py:851` (set) | `positional 0` | `requirements.all_imports` | `frozenset()` | KILLED | test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports |
| `pipeline.py:853` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports |
| `pipeline.py:853` (getattr) | `positional 1` | `'reqs'` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports |
| `pipeline.py:853` (getattr) | `positional 2` | `False` | `True` | DEAD | **see below** |
| `pipeline.py:866` (logging.info) | `positional 0` | `'Runtime: %s'` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_every_launch_announces_the_command_it_is_about_to_run |
| `pipeline.py:866` (logging.info) | `positional 1` | `elapsed_raw_time` | `` | NO SUBSTITUTE |  |
| `pipeline.py:869` (logging.error) | `positional 0` | `'The current virtual environment does not have all the re…` | `"wiring-probe"` | OPEN HOLE | **see below** |
| `pipeline.py:873` (logging.info) | `positional 0` | `'Please deactivate the current virtual environment and ru…` | `"wiring-probe"` | OPEN HOLE | **see below** |
| `cache_search.py:592` (wanted_packages) | `positional 0` | `uninstalled` | `set()` | KILLED | test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[last_used] |
| `cache_search.py:592` (wanted_packages) | `positional 1` | `extra_requirements` | `{}` | KILLED | test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[last_used] |
| `cache_search.py:594` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | test_cache_search::test_find_match_dir_in_cache_returns_a_manifest_match |
| `cache_search.py:594` (getattr) | `positional 1` | `'latest'` | `"wiring-probe"` | KILLED | test_cache_search::test_find_match_dir_in_cache_returns_a_manifest_match |
| `cache_search.py:594` (getattr) | `positional 2` | `False` | `True` | KILLED | test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv |
| `cache_search.py:595` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | test_cache_search::test_the_last_used_pass_is_tried_for_exactly_the_same_flag_combinations[flags4] |
| `cache_search.py:595` (getattr) | `positional 1` | `'oldest'` | `"wiring-probe"` | KILLED | test_cache_search::test_the_last_used_pass_is_tried_for_exactly_the_same_flag_combinations[flags4] |
| `cache_search.py:595` (getattr) | `positional 2` | `False` | `True` | KILLED | test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv |
| `cache_search.py:596` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[smallest] |
| `cache_search.py:596` (getattr) | `positional 1` | `'smallest'` | `"wiring-probe"` | KILLED | test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[smallest] |
| `cache_search.py:596` (getattr) | `positional 2` | `False` | `True` | KILLED | test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv |
| `cache_search.py:604` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | test_cache_search::test_find_match_dir_in_cache_returns_a_manifest_match |
| `cache_search.py:604` (getattr) | `positional 1` | `'latest'` | `"wiring-probe"` | KILLED | test_cache_search::test_find_match_dir_in_cache_returns_a_manifest_match |
| `cache_search.py:604` (getattr) | `positional 2` | `False` | `True` | KILLED | test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv |
| `cache_search.py:605` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | test_cache_search::test_the_last_used_pass_is_tried_for_exactly_the_same_flag_combinations[flags3] |
| `cache_search.py:605` (getattr) | `positional 1` | `'smallest'` | `"wiring-probe"` | KILLED | test_cache_search::test_the_last_used_pass_is_tried_for_exactly_the_same_flag_combinations[flags3] |
| `cache_search.py:605` (getattr) | `positional 2` | `False` | `True` | KILLED | test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv |
| `cache_search.py:608` (check_venv_dir) | `positional 0` | `record.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv |
| `cache_search.py:609` (check_venv_dir) | `wanted` | `wanted` | `[]` | KILLED | test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[last_used] |
| `cache_search.py:610` (check_venv_dir) | `tag` | `tag` | `"0.0"` | KILLED | test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv |
| `cache_search.py:611` (check_venv_dir) | `uninstalled` | `uninstalled` | `set()` | KILLED | test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[last_used] |
| `cache_search.py:612` (check_venv_dir) | `source_names` | `source_names` | `frozenset()` | KILLED | test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[last_used] |
| `cache_search.py:613` (check_venv_dir) | `rawlog` | `rawlog` | `True` | KILLED | test_cache_search::test_every_branch_lets_check_venv_dir_report_a_venv_that_vanished[last_used] |
| `cache_search.py:615` (ek.ensure_path) | `positional 0` | `record.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv |
| `cache_search.py:617` (logging.info) | `positional 0` | `'Trying to load the latest matching venv now.'` | `"wiring-probe"` | KILLED | test_wiring_4b::test_a_pointer_that_does_not_match_says_it_is_trying_the_latest |
| `cli.py:219` (settings.Settings) | `my_name` | `MY_NAME` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_state_directory_ignores_argv0 |
| `cli.py:220` (settings.Settings) | `my_dir` | `Path.home() / MY_NAME` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_cli_entry_point::test_state_directory_ignores_argv0 |
| `cli.py:221` (settings.Settings) | `cwd` | `Path.cwd().expanduser().resolve(strict=True)` | `__import__("pathlib").Path("/tmp/veny-wiring-probe")` | KILLED | test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone |
| `cli.py:222` (settings.Settings) | `venv_name` | `'myenv'` | `"wiringprobe"` | KILLED | test_cli_entry_point::test_main_describes_the_run_to_the_cache_search |
| `cli.py:223` (settings.Settings) | `stay_out_list` | `settings.DEFAULT_STAY_OUT_LIST` | `()` | KILLED | test_wiring_4a::test_cli_builds_the_settings_from_the_shipped_defaults |
| `cli.py:224` (settings.Settings) | `search_above_this_dir` | `True` | `False` | KILLED | test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache |
| `cli.py:225` (settings.Settings) | `rawlog` | `rawlog` | `True` | KILLED | test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs |
| `cli.py:226` (settings.Settings) | `known_bad_imports` | `settings.DEFAULT_KNOWN_BAD_IMPORTS` | `frozenset()` | KILLED | test_wiring_4a::test_cli_builds_the_settings_from_the_shipped_defaults |
| `cli.py:227` (settings.Settings) | `also_needs` | `settings.DEFAULT_ALSO_NEEDS` | `{}` | KILLED | test_wiring_4a::test_cli_builds_the_settings_from_the_shipped_defaults |
| `cli.py:228` (settings.Settings) | `extra_requirements_file` | `'extra_requirements.txt'` | `"wiring_probe.txt"` | KILLED | test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check |
| `cli.py:221` (Path.cwd().expanduser().resolve) | `strict` | `True` | `False` | OPEN HOLE | **see below** |
| `cli.py:232` (pipeline.resolve_target) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | test_cli_entry_point::test_main_describes_the_run_to_the_cache_search |
| `cli.py:234` (pipeline.feeling_lucky) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | test_cli_entry_point::test_state_directory_ignores_argv0 |
| `cli.py:235` (pipeline.feeling_lucky) | `positional 1` | `target` | `__import__("veny.state", fromlist=["Target"]).Target…` | KILLED | test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script |
| `cli.py:236` (pipeline.feeling_lucky) | `my_name` | `MY_NAME` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script |
| `cli.py:237` (pipeline.feeling_lucky) | `rawlog` | `rawlog` | `True` | KILLED | test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs |
| `cli.py:240` (_shell_status) | `positional 0` | `lucky_status` | `` | NO SUBSTITUTE |  |
| `cli.py:242` (ek.configure_logging) | `positional 0` | `MY_NAME` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice |
| `cli.py:242` (ek.configure_logging) | `log_level` | `log_mode` | `logging.CRITICAL` | KILLED | test_cli_entry_point::test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice |
| `cli.py:242` (ek.configure_logging) | `rawlog` | `rawlog` | `True` | KILLED | test_cli_entry_point::test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug |
| `cli.py:245` (pipeline.run) | `positional 0` | `run_settings` | `__import__("veny.settings", fromlist=["Settings"]).S…` | KILLED | test_cli_entry_point::test_state_directory_ignores_argv0 |
| `cli.py:245` (pipeline.run) | `positional 1` | `args` | `argparse.Namespace()` | KILLED | test_cli_entry_point::test_main_describes_the_run_to_the_cache_search |
| `cli.py:245` (pipeline.run) | `positional 2` | `target` | `__import__("veny.state", fromlist=["Target"]).Target…` | KILLED | test_cli_entry_point::test_main_describes_the_run_to_the_cache_search |
| `cli.py:245` (pipeline.run) | `start_time` | `start_time` | `__import__("datetime").datetime(2000, 1, 1)` | KILLED | test_cli_entry_point::test_the_run_is_timed_from_the_moment_veny_started |
| `cli.py:248` (logging.info) | `positional 0` | `'%s'` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_a_run_with_no_script_is_a_usage_error |
| `cli.py:248` (logging.info) | `positional 1` | `exc` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_a_run_with_no_script_is_a_usage_error |
| `cli.py:251` (logging.error) | `positional 0` | `'%s'` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_main_maps_a_failed_venv_build_to_status_one |
| `cli.py:251` (logging.error) | `positional 1` | `exc` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_main_maps_a_failed_venv_build_to_status_one |
| `cli.py:258` (print) | `positional 0` | `str(exc)` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_main_maps_a_missing_uv_to_status_one |
| `cli.py:258` (print) | `file` | `sys.stderr` | `sys.stdout` | KILLED | test_cli_entry_point::test_main_maps_a_missing_uv_to_status_one |
| `cli.py:258` (str) | `positional 0` | `exc` | `"wiring-probe"` | KILLED | test_cli_entry_point::test_main_maps_a_missing_uv_to_status_one |
| `cli.py:260` (ek.print_all_errors) | `positional 0` | `memory_handler` | `None` | KILLED | test_wiring_4b::test_the_error_dump_gets_this_runs_handler_and_this_runs_rawlog[rawlog] |
| `cli.py:260` (ek.print_all_errors) | `positional 1` | `rawlog` | `True` | KILLED | test_wiring_4b::test_the_error_dump_gets_this_runs_handler_and_this_runs_rawlog[normal] |
| `cli.py:262` (_shell_status) | `positional 0` | `script_exit_code` | `` | NO SUBSTITUTE |  |
