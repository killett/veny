# Phase 4b wiring index — every argument, measured

**What was swept.** Every argument at every call site phase 4b created or
changed — **172 arguments across 39 distinct callees** in
`src/veny/last_used.py`, `src/veny/pipeline.py`, `src/veny/cache_search.py`
and `src/veny/cli.py`. The harness is `scripts/wiring_sweep_4b.py`, a retarget
of phase 4a's.

> **If Task 9 (the differential) changes any line in those four modules, every
> line number below goes stale and this sweep must be re-run before the phase
> closes.** The table is keyed on `file:line`, and the harness rewrites
> expressions by source position. Re-running is cheap — one `pixi run python
> scripts/wiring_sweep_4b.py`, about twelve minutes — and reading a stale
> table is not.

**Which code counts as "this phase".** Decided from the structure of the
modules, in `scoped_calls()`, not from a hand-written list of names — 3e's
symbol sweep worked from a list and missed a whole spelling, and 4a's index
exists partly so that cannot recur. The four rules are:

1. **`last_used.py` entire** — the module is new this phase.
2. **`pipeline.feeling_lucky` and `pipeline._load_last_used` entire**, plus
   the two call sites inside `pipeline.run` this phase rewrote:
   `cache_search.find_match_dir_in_cache(...)` (which now carries the injected
   `load_last_used`) and `last_used.save(...)` (which replaced the five
   copy-backs onto `Options` and `ek.save_options_to_json`).
3. **`cache_search.find_match_dir_in_cache`'s last-used pass** — from the top
   of the function down to the statement that spends the pass. Below that is
   the `--latest`/`--oldest`/`--smallest` ranking, swept by **phase 3d**:
   `docs/superpowers/plans/2026-08-18-verify-cache-search-last-used-wiring-index.md`.
   (Not phase 4a — 4a's index has no `cache_search.py` rows at all.)
4. **`cli.main` entire.** This rule originally admitted only
   `settings.Settings` and the `pipeline.*` calls, and measured 154 arguments.
   That dropped four sites this phase rewired — `ek.configure_logging` (all
   three arguments moved off `options.*`), `ek.print_all_errors` (both), and
   the two `getattr(args, …)` reads introduced at the top of `main` — and
   **both of `print_all_errors`' arguments turned out to be open holes**. The
   rule is now "every call in `main`", with no name filter.

Within those four scopes *every* call is swept, including `logging` and
`print` arguments. Veny's commentary on a record it decided to ignore is the
only thing standing between "the pointer was stale" and "--feeling-lucky
silently stopped working", so it is behaviour, not decoration — and eighteen
of the twenty-eight holes closed in this task are exactly that.

**How each row was measured.** The argument's expression is replaced, in
place, with a type-correct but wrong value; the four modules are
import-checked; then the whole suite runs. The first test to fail is the named
killer. Nothing fails: **OPEN HOLE**. The callee cannot read it, or no input
can reach it: **DEAD ARGUMENT**, listed separately from the holes so the
headline cannot blur the two. `apply()` refuses to run a substitution that
reproduces the original text — such a row would score as an OPEN HOLE with no
signal in it at all.

**The trap, recorded again because it cost phase 4a a whole sweep.**
`pixi run` sets `PYTHONPATH=src`, and `tests/test_import_guard.py` spawns its
own subprocess that needs it. 4a's first sweep invoked pytest without that
variable, so that one test failed under *every* mutation and reported 86
spurious kills — which would have hidden every real hole behind them. This
harness sets `PYTHONPATH=src` itself and import-checks each mutated tree
before believing any failure. Zero INVALID and zero ERROR rows in the run
below, which is what that check buys.

**One stale row deliberately not carried over.** `scripts/wiring_sweep_4a.py:148`
still holds the call-site string
`lambda: _load_last_used(options, target, pathlibcutoff=options.pathlibcutoff, …)`,
naming a parameter `_load_last_used` no longer has and an `Options` that no
longer exists. 4a's script is history and is left alone; 4b's substitution
table spells the current signature instead.

## The headline

What the sweep printed on 2026-08-22: **172 rows — 157 KILLED, 12 OPEN HOLE,
3 MULTILINE.** Classified:

| | |
|---|---|
| Arguments swept | **172** |
| Killed by a named test | **158** (157 on the first substitution, 1 on a second) |
| Measured by driving rather than substitution | **3** |
| DEAD ARGUMENT | **6 + 2** = **8** |
| OPEN HOLE | **3** |

157 + 1 + 3 + 8 + 3 = 172.

The one row that needed a *second* substitution is `pipeline.py:971`, marked
`KILLED*` in the table: the first pass's probe script is also called
`script.py`, and `record_path` reads only `python_script.name`, so the
substitution produced the same filename. Measured again with a probe named
`other_name.py`, it dies at
`test_wiring_4a::test_the_saved_record_carries_the_venv_the_run_actually_used`.
The weak substitution is not counted as evidence of anything.

**28 rows that were OPEN HOLE under some measurement are now killed by tests
written in this task** — count them in the table by their `test_wiring_4b`
killers. The history: the first full sweep (narrow rule 4, 154 arguments, with
this task's three required tests already in place) reported **36 OPEN HOLE**;
eleven further test functions took that to 4 open, 6 dead and 1 weak. The
review then widened rule 4, adding 18 rows and 5 more open ones; one further
test closed 2 of those. Final: 3 open, 8 dead, 1 weak.

## The three tests the brief required, and what they cover

They kill few rows *as first killer* (pytest stops at the first failure, and
the cheap unit tests in the same file get there first), so each was measured
by a hand mutation of the site it exists for. Recorded here because the table
cannot show it:

| Test | Mutation it was measured against | Sites it covers |
|---|---|---|
| `test_the_saved_record_names_the_folder_the_run_ended_with` | `state.LastUsed(venv_dir=settings.my_dir / settings.venv_name, …)` — the record built from the name a fresh build *would* have used | `pipeline.py:965–968`, on the cache-**hit** branch, which no other test reads the record after; named killer for `:968` (`timestamp`) |
| `test_the_cache_search_is_handed_the_record_for_this_script` | `_load_last_used`'s `script_dir=Path.cwd()` | `pipeline.py:892` (the lambda) and `pipeline.py:555–556`, end to end through `last_used.record_path`; a decoy record in the working directory makes the wrong reader return the wrong environment rather than `None` |
| `test_feeling_lucky_reads_the_same_record_the_run_writes` | `record_path(script_dir, python_script, my_name + "-v2")` inside `save` only | `last_used.py:81` against `last_used.py:118` — the writer and the lucky reader agreeing on one filename, which nothing else in the suite compares |

The phase's other two record tests live in `tests/test_wiring_4a.py`, where
Task 2 wrote them next to the 4a rows they also cover:
`test_the_saved_record_carries_the_venv_the_run_actually_used` (4 rows) and
`test_the_saved_record_names_the_post_rename_venv_dir`. They are cited in the
table rather than duplicated.

## The 3 OPEN HOLEs, each with its reason

1. **`last_used.py:87` `path.write_text(encoding='utf-8')`** — the **writer**
   only. Everything `save` writes is ASCII, because `json.dumps` escapes
   non-ASCII by default, and utf-8 and latin-1 agree on ASCII. No payload
   `save` can produce distinguishes them, so no test can kill this row.
   The argument is still right and must stay: it is what keeps the file
   independent of the platform default should `ensure_ascii=False` ever be
   set for readability.
   **The read side is a different question and is not open.** `load` reads
   files veny did not necessarily write — a hand-edited record, one copied
   between machines, one written by a later veny that stopped escaping — so
   `last_used.py:120`'s encoding *is* observable and *is* killed, by
   `test_wiring_4b::test_a_record_veny_did_not_write_is_decoded_as_utf_8`,
   which plants a UTF-8 record with a non-ASCII `venv_dir`. Decoded as
   latin-1 it comes back as mojibake naming a directory that does not exist:
   a permanent silent cache miss, no rejection and no log line.
2. **`last_used.py:87` `json.dumps(indent=4)`.** Cosmetics. The only reader is
   `json.loads`, which does not care. Pinning it would assert on the file's
   whitespace.
3. **`cli.py:201` `Path.cwd().expanduser().resolve(strict=True)`.** `strict`
   only bites on a working directory that does not exist — a process whose
   cwd was deleted under it. No portable way to create that state in a test,
   and the failure it produces is the desired one either way.

## The 8 DEAD ARGUMENTS

Passed and never readable. Deletion candidates for phase 4c, not test gaps.
**None should be deleted on its own** — in every case what is dead is the
argument *together with* the construct around it, and deleting only the
argument would break the hand-built `argparse.Namespace()` objects the unit
tests pass.

- **`pipeline.py:422` `getattr(args, 'feeling_lucky', False)`**,
  **`pipeline.py:888` `getattr(args, 'reqs', False)`**,
  **`cache_search.py:602` `getattr(args, 'last_used', False)`**,
  **`cli.py:191` `getattr(args, 'rawlog', False)`** and
  **`cli.py:194` `getattr(args, 'debug', False)`** — the third argument, the
  default. All of veny's flags are `action="store_true"`, so argparse always
  defines the dest and no real run can reach the default. It is reachable
  only from a hand-built Namespace, which pins the `getattr` rather than any
  behaviour.
- **`cache_search.py:596` `getattr(args, 'last_used', False)`** — both
  arguments, and the whole term. `explicit` is used at exactly one place,
  `try_last_used = not explicit or getattr(args, 'last_used', False)`. If
  `last_used` is true the second disjunct decides on its own; if it is false
  the term contributes nothing to `explicit`. The `last_used` term inside
  `explicit` therefore cannot change any outcome, for any command line —
  confirmed exhaustively across all 16 flag combinations in review. Deleting
  it would leave `explicit = latest or oldest or smallest`, which is also what
  the comment above it describes.
- **`pipeline.py:435` `run_script(rawlog=rawlog)`** — 3e's latent defect 3,
  found again at a fourth site. `run_script` reads `rawlog` only to guard its
  announce line, and this call leaves `announce` False, so the value cannot
  reach anything. 4a re-confirmed the same finding at three sibling sites
  (now `:832` and `:855`, plus this one). As 4a's index says, this is a
  behaviour question as much as a finding: if the lucky launch is ever meant
  to announce itself, `rawlog` becomes live and the row closes on its own.

## Measured by driving rather than substitution (3)

Multi-line expressions the harness cannot rewrite in place. Each is measured
by a test that drives it instead:

| Expression | Site | How it is measured |
|---|---|---|
| `verify.source_import_names(…)` inside `find_match_dir_in_cache` | `pipeline.py:885` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` (unchanged from 4a's index, where this site was `pipeline.py:895`) |
| `lambda: _load_last_used(target, my_name=…, rawlog=…)` | `pipeline.py:892` | `test_wiring_4b::test_the_cache_search_is_handed_the_record_for_this_script` and `test_wiring_4a::test_the_last_used_callback_carries_this_runs_target_and_name` — measured against `script_dir=Path.cwd()`, which fails both |
| `state.LastUsed(venv_dir=…, venv_python=…, timestamp=…)` | `pipeline.py:965` | `test_wiring_4a::test_the_saved_record_carries_the_venv_the_run_actually_used`, `…::test_the_saved_record_names_the_post_rename_venv_dir` and `test_wiring_4b::test_the_saved_record_names_the_folder_the_run_ended_with` — measured against a record built from `settings.my_dir / settings.venv_name`, which fails all three |

## Every argument, measured

`Substitute` is the value the expression was replaced with. `KILLED*` marks
the one row that needed a second substitution; see the headline.

| Site | Argument | Expression | Substitute | Verdict | Killed by |
|---|---|---|---|---|---|
| `last_used.py:34` (os.environ.get) | `positional 0` | `'VIRTUAL_ENV'` | `"WIRING_PROBE_ENV"` | KILLED | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `last_used.py:36` (ek.ensure_path) | `positional 0` | `declared` | `"/tmp/veny-wiring-probe"` | KILLED | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `last_used.py:37` (Path) | `positional 0` | `sys.prefix` | `"/tmp/veny-wiring-probe"` | KILLED | `test_last_used::test_active_virtualenv_dir_falls_back_to_sys_prefix` |
| `last_used.py:81` (record_path) | `positional 0` | `script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:81` (record_path) | `positional 1` | `python_script` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:81` (record_path) | `positional 2` | `my_name` | `"wiring-probe"` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:83` (os.fspath) | `positional 0` | `record.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:84` (os.fspath) | `positional 0` | `record.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_a_saved_record_is_read_back_as_the_same_paths` |
| `last_used.py:87` (path.write_text) | `positional 0` | `json.dumps(payload, indent=4) + '\n'` | `"{}\n"` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:87` (path.write_text) | `encoding` | `'utf-8'` | `"latin-1"` | OPEN HOLE | **see below** |
| `last_used.py:87` (json.dumps) | `positional 0` | `payload` | `{}` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:87` (json.dumps) | `indent` | `4` | `0` | OPEN HOLE | **see below** |
| `last_used.py:118` (record_path) | `positional 0` | `script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `last_used.py:118` (record_path) | `positional 1` | `python_script` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:118` (record_path) | `positional 2` | `my_name` | `"wiring-probe"` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:120` (json.loads) | `positional 0` | `path.read_text(encoding='utf-8')` | `"{}"` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `last_used.py:120` (path.read_text) | `encoding` | `'utf-8'` | `"latin-1"` | KILLED | `test_wiring_4b::test_a_record_veny_did_not_write_is_decoded_as_utf_8` |
| `last_used.py:123` (logging.info) | `positional 0` | `'No usable last-used record for %s.'` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `last_used.py:123` (logging.info) | `positional 1` | `os.fspath(python_script)` | `"/tmp/veny-wiring-probe"` | KILLED | `test_last_used::test_the_venv_python_loader_lets_the_record_search_explain_itself` |
| `last_used.py:123` (os.fspath) | `positional 0` | `python_script` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_venv_python_loader_lets_the_record_search_explain_itself` |
| `last_used.py:125` (isinstance) | `positional 0` | `payload` | `{}` | KILLED | `test_last_used::test_a_damaged_record_is_none_and_not_a_crash[not-an-object]` |
| `last_used.py:125` (isinstance) | `positional 1` | `dict` | `object` | KILLED | `test_last_used::test_a_damaged_record_is_none_and_not_a_crash[not-an-object]` |
| `last_used.py:127` (logging.info) | `positional 0` | `'Last-used record %s is not an object.'` | `"wiring-probe"` | KILLED | `test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[not-an-object]` |
| `last_used.py:127` (logging.info) | `positional 1` | `os.fspath(path)` | `"/tmp/veny-wiring-probe"` | KILLED | `test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[not-an-object]` |
| `last_used.py:127` (os.fspath) | `positional 0` | `path` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[not-an-object]` |
| `last_used.py:129` (payload.get) | `positional 0` | `'venv_dir'` | `"wiring_probe_venv_dir"` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:130` (payload.get) | `positional 0` | `'venv_python'` | `"wiring_probe_venv_python"` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:131` (isinstance) | `positional 0` | `venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:131` (isinstance) | `positional 1` | `str` | `object` | KILLED | `test_wiring_4b::test_a_record_whose_path_is_not_a_string_is_refused[venv_dir-a-number]` |
| `last_used.py:131` (isinstance) | `positional 0` | `venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:131` (isinstance) | `positional 1` | `str` | `object` | KILLED | `test_wiring_4b::test_a_record_whose_path_is_not_a_string_is_refused[venv_python-a-list]` |
| `last_used.py:133` (logging.info) | `positional 0` | `'Last-used record %s names no environment.'` | `"wiring-probe"` | KILLED | `test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[no-environment]` |
| `last_used.py:133` (logging.info) | `positional 1` | `os.fspath(path)` | `"/tmp/veny-wiring-probe"` | KILLED | `test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[no-environment]` |
| `last_used.py:133` (os.fspath) | `positional 0` | `path` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[no-environment]` |
| `last_used.py:137` (logging.info) | `positional 0` | `'Last-used record %s names an empty path.'` | `"wiring-probe"` | KILLED | `test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[empty-path]` |
| `last_used.py:137` (logging.info) | `positional 1` | `os.fspath(path)` | `"/tmp/veny-wiring-probe"` | KILLED | `test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[empty-path]` |
| `last_used.py:137` (os.fspath) | `positional 0` | `path` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_wiring_4b::test_a_degraded_record_says_what_is_wrong_and_names_the_file[empty-path]` |
| `last_used.py:139` (payload.get) | `positional 0` | `'timestamp'` | `"wiring_probe_timestamp"` | KILLED | `test_last_used::test_a_saved_record_is_read_back_as_the_same_paths` |
| `last_used.py:141` (state.LastUsed) | `venv_dir` | `ek.ensure_path(venv_dir)` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:142` (state.LastUsed) | `venv_python` | `ek.ensure_path(venv_python)` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_a_saved_record_is_read_back_as_the_same_paths` |
| `last_used.py:143` (state.LastUsed) | `timestamp` | `timestamp if isinstance(timestamp, str) else ''` | `"20000101-000000"` | KILLED | `test_last_used::test_a_saved_record_is_read_back_as_the_same_paths` |
| `last_used.py:141` (ek.ensure_path) | `positional 0` | `venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `last_used.py:142` (ek.ensure_path) | `positional 0` | `venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_a_saved_record_is_read_back_as_the_same_paths` |
| `last_used.py:143` (isinstance) | `positional 0` | `timestamp` | `"20000101-000000"` | KILLED | `test_wiring_4b::test_a_record_whose_timestamp_is_not_a_string_still_loads` |
| `last_used.py:143` (isinstance) | `positional 1` | `str` | `object` | KILLED | `test_wiring_4b::test_a_record_whose_timestamp_is_not_a_string_still_loads` |
| `last_used.py:167` (load) | `script_dir` | `script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `last_used.py:168` (load) | `python_script` | `python_script` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_venv_python_loader_lets_the_record_search_explain_itself` |
| `last_used.py:169` (load) | `my_name` | `my_name` | `"wiring-probe"` | KILLED | `test_last_used::test_load_venv_python_returns_the_recorded_interpreter` |
| `last_used.py:170` (load) | `rawlog` | `rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `last_used.py:174` (logging.info) | `positional 0` | `'No last used record found, so no venv_python to return.'` | `"wiring-probe"` | KILLED | `test_wiring_4b::test_the_lucky_reader_says_when_there_is_no_record_at_all` |
| `last_used.py:176` (ek.safe_is_file) | `positional 0` | `record.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_load_venv_python_returns_the_recorded_interpreter` |
| `last_used.py:179` (logging.warning) | `positional 0` | `'Last used venv_python %s is no longer valid.'` | `"wiring-probe"` | KILLED | `test_last_used::test_load_venv_python_is_none_when_the_interpreter_is_gone` |
| `last_used.py:180` (logging.warning) | `positional 1` | `os.fspath(record.venv_python)` | `"/tmp/veny-wiring-probe"` | KILLED | `test_wiring_4b::test_the_lucky_reader_names_the_interpreter_it_will_not_use` |
| `last_used.py:180` (os.fspath) | `positional 0` | `record.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_wiring_4b::test_the_lucky_reader_names_the_interpreter_it_will_not_use` |
| `last_used.py:184` (logging.info) | `positional 0` | `'Last used venv_python found: %s'` | `"wiring-probe"` | KILLED | `test_wiring_4b::test_the_lucky_reader_names_the_interpreter_it_found` |
| `last_used.py:184` (logging.info) | `positional 1` | `os.fspath(record.venv_python)` | `"/tmp/veny-wiring-probe"` | KILLED | `test_wiring_4b::test_the_lucky_reader_names_the_interpreter_it_found` |
| `last_used.py:184` (os.fspath) | `positional 0` | `record.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_wiring_4b::test_the_lucky_reader_names_the_interpreter_it_found` |
| `pipeline.py:422` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:422` (getattr) | `positional 1` | `'feeling_lucky'` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:422` (getattr) | `positional 2` | `False` | `True` | DEAD | **see below** |
| `pipeline.py:425` (last_used.load_venv_python) | `script_dir` | `target.script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:426` (last_used.load_venv_python) | `python_script` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |
| `pipeline.py:427` (last_used.load_venv_python) | `my_name` | `my_name` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |
| `pipeline.py:428` (last_used.load_venv_python) | `rawlog` | `rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:432` (run_script) | `positional 0` | `last_used_venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:433` (run_script) | `positional 1` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:434` (run_script) | `positional 2` | `list(target.script_args)` | `[]` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:435` (run_script) | `rawlog` | `rawlog` | `True` | DEAD | **see below** |
| `pipeline.py:434` (list) | `positional 0` | `target.script_args` | `()` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:438` (print) | `positional 0` | `f'Script exited with status {returncode}'` | `"wiring-probe"` | KILLED | `test_wiring_4b::test_feeling_lucky_reports_a_script_that_failed` |
| `pipeline.py:442` (print) | `positional 0` | `'No luck: no last used virtual environment found. Running th…` | `"wiring-probe"` | KILLED | `test_wiring_4b::test_feeling_lucky_says_so_when_there_is_no_record` |
| `pipeline.py:555` (last_used.load) | `script_dir` | `target.script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:556` (last_used.load) | `python_script` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `pipeline.py:557` (last_used.load) | `my_name` | `my_name` | `"wiring-probe"` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `pipeline.py:558` (last_used.load) | `rawlog` | `rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:880` (cache_search.find_match_dir_in_cache) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:881` (cache_search.find_match_dir_in_cache) | `my_dir` | `settings.my_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:882` (cache_search.find_match_dir_in_cache) | `venv_name` | `settings.venv_name` | `"wiringprobe"` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:883` (cache_search.find_match_dir_in_cache) | `uninstalled` | `set(requirements.uninstalled)` | `set()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:884` (cache_search.find_match_dir_in_cache) | `extra_requirements` | `requirements.extra_requirements` | `{}` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:885` (cache_search.find_match_dir_in_cache) | `source_names` | `verify.source_import_names(set(requirements.all_imports), re…` | `frozenset()` | MULTILINE | **see below** |
| `pipeline.py:890` (cache_search.find_match_dir_in_cache) | `tag` | `cache_search.interpreter_tag(stdlib)` | `"0.0"` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:891` (cache_search.find_match_dir_in_cache) | `rawlog` | `settings.rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:892` (cache_search.find_match_dir_in_cache) | `load_last_used` | `lambda: _load_last_used(target, my_name=settings.my_name, ra…` | `(lambda: None)` | MULTILINE | **see below** |
| `pipeline.py:883` (set) | `positional 0` | `requirements.uninstalled` | `set()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:886` (verify.source_import_names) | `positional 0` | `set(requirements.all_imports)` | `frozenset()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:887` (verify.source_import_names) | `positional 1` | `requirements.extra_requirements` | `{}` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:888` (verify.source_import_names) | `positional 2` | `getattr(args, 'reqs', False)` | `not getattr(args, 'reqs', False)` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:886` (set) | `positional 0` | `requirements.all_imports` | `frozenset()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:888` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:888` (getattr) | `positional 1` | `'reqs'` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:888` (getattr) | `positional 2` | `False` | `True` | DEAD | **see below** |
| `pipeline.py:890` (cache_search.interpreter_tag) | `positional 0` | `stdlib` | `stdlib_index.for_running_interpreter()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:893` (_load_last_used) | `positional 0` | `target` | `__import__("veny.state", fromlist=["Target"]…` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:893` (_load_last_used) | `my_name` | `settings.my_name` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:893` (_load_last_used) | `rawlog` | `settings.rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:965` (last_used.save) | `positional 0` | `state.LastUsed(venv_dir=handle.venv_dir, venv_python=handle.…` | `__import__("veny.state", fromlist=["LastUsed…` | MULTILINE | **see below** |
| `pipeline.py:970` (last_used.save) | `script_dir` | `target.script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_wiring_4a::test_the_saved_record_carries_the_venv_the_run_actually_used` |
| `pipeline.py:971` (last_used.save) | `python_script` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED* | `test_wiring_4a::test_the_saved_record_carries_the_venv_the_run_actually_used` |
| `pipeline.py:972` (last_used.save) | `my_name` | `settings.my_name` | `"wiring-probe"` | KILLED | `test_wiring_4a::test_the_saved_record_carries_the_venv_the_run_actually_used` |
| `pipeline.py:966` (state.LastUsed) | `venv_dir` | `handle.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_wiring_4a::test_the_saved_record_carries_the_venv_the_run_actually_used` |
| `pipeline.py:967` (state.LastUsed) | `venv_python` | `handle.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_wiring_4a::test_the_saved_record_carries_the_venv_the_run_actually_used` |
| `pipeline.py:968` (state.LastUsed) | `timestamp` | `target.timestamp` | `"20000101-000000"` | KILLED | `test_wiring_4b::test_the_saved_record_names_the_folder_the_run_ended_with` |
| `cache_search.py:592` (wanted_packages) | `positional 0` | `uninstalled` | `set()` | KILLED | `test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[last_used]` |
| `cache_search.py:592` (wanted_packages) | `positional 1` | `extra_requirements` | `{}` | KILLED | `test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[last_used]` |
| `cache_search.py:594` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cache_search::test_find_match_dir_in_cache_returns_a_manifest_match` |
| `cache_search.py:594` (getattr) | `positional 1` | `'latest'` | `"wiring-probe"` | KILLED | `test_cache_search::test_find_match_dir_in_cache_returns_a_manifest_match` |
| `cache_search.py:594` (getattr) | `positional 2` | `False` | `True` | KILLED | `test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv` |
| `cache_search.py:595` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[oldest]` |
| `cache_search.py:595` (getattr) | `positional 1` | `'oldest'` | `"wiring-probe"` | KILLED | `test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[oldest]` |
| `cache_search.py:595` (getattr) | `positional 2` | `False` | `True` | KILLED | `test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv` |
| `cache_search.py:596` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | DEAD | **see below** |
| `cache_search.py:596` (getattr) | `positional 1` | `'last_used'` | `"wiring-probe"` | DEAD | **see below** |
| `cache_search.py:596` (getattr) | `positional 2` | `False` | `True` | KILLED | `test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv` |
| `cache_search.py:597` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[smallest]` |
| `cache_search.py:597` (getattr) | `positional 1` | `'smallest'` | `"wiring-probe"` | KILLED | `test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[smallest]` |
| `cache_search.py:597` (getattr) | `positional 2` | `False` | `True` | KILLED | `test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv` |
| `cache_search.py:602` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cache_search::test_asking_for_both_the_latest_and_the_last_used_venv_selects_nothing` |
| `cache_search.py:602` (getattr) | `positional 1` | `'last_used'` | `"wiring-probe"` | KILLED | `test_cache_search::test_asking_for_both_the_latest_and_the_last_used_venv_selects_nothing` |
| `cache_search.py:602` (getattr) | `positional 2` | `False` | `True` | DEAD | **see below** |
| `cache_search.py:603` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cache_search::test_find_match_dir_in_cache_returns_a_manifest_match` |
| `cache_search.py:603` (getattr) | `positional 1` | `'latest'` | `"wiring-probe"` | KILLED | `test_cache_search::test_find_match_dir_in_cache_returns_a_manifest_match` |
| `cache_search.py:603` (getattr) | `positional 2` | `False` | `True` | KILLED | `test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv` |
| `cache_search.py:604` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_wiring_4b::test_the_last_used_pass_is_skipped_when_smallest_is_asked_for_too` |
| `cache_search.py:604` (getattr) | `positional 1` | `'smallest'` | `"wiring-probe"` | KILLED | `test_wiring_4b::test_the_last_used_pass_is_skipped_when_smallest_is_asked_for_too` |
| `cache_search.py:604` (getattr) | `positional 2` | `False` | `True` | KILLED | `test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv` |
| `cache_search.py:607` (check_venv_dir) | `positional 0` | `record.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv` |
| `cache_search.py:608` (check_venv_dir) | `wanted` | `wanted` | `[]` | KILLED | `test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[last_used]` |
| `cache_search.py:609` (check_venv_dir) | `tag` | `tag` | `"0.0"` | KILLED | `test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv` |
| `cache_search.py:610` (check_venv_dir) | `uninstalled` | `uninstalled` | `set()` | KILLED | `test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[last_used]` |
| `cache_search.py:611` (check_venv_dir) | `source_names` | `source_names` | `frozenset()` | KILLED | `test_cache_search::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run[last_used]` |
| `cache_search.py:612` (check_venv_dir) | `rawlog` | `rawlog` | `True` | KILLED | `test_cache_search::test_every_branch_lets_check_venv_dir_report_a_venv_that_vanished[last_used]` |
| `cache_search.py:614` (ek.ensure_path) | `positional 0` | `record.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cache_search::test_the_last_used_pointer_selects_the_recorded_venv` |
| `cache_search.py:616` (logging.info) | `positional 0` | `'Trying to load the latest matching venv now.'` | `"wiring-probe"` | KILLED | `test_wiring_4b::test_a_pointer_that_does_not_match_says_it_is_trying_the_latest` |
| `cli.py:191` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `cli.py:191` (getattr) | `positional 1` | `'rawlog'` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `cli.py:191` (getattr) | `positional 2` | `False` | `True` | DEAD | **see below** |
| `cli.py:194` (getattr) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cli_entry_point::test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug` |
| `cli.py:194` (getattr) | `positional 1` | `'debug'` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug` |
| `cli.py:194` (getattr) | `positional 2` | `False` | `True` | DEAD | **see below** |
| `cli.py:199` (settings.Settings) | `my_name` | `MY_NAME` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_state_directory_ignores_argv0` |
| `cli.py:200` (settings.Settings) | `my_dir` | `Path.home() / MY_NAME` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cli_entry_point::test_state_directory_ignores_argv0` |
| `cli.py:201` (settings.Settings) | `cwd` | `Path.cwd().expanduser().resolve(strict=True)` | `__import__("pathlib").Path("/tmp/veny-wiring…` | KILLED | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone` |
| `cli.py:202` (settings.Settings) | `venv_name` | `'myenv'` | `"wiringprobe"` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `cli.py:203` (settings.Settings) | `stay_out_list` | `settings.DEFAULT_STAY_OUT_LIST` | `()` | KILLED | `test_wiring_4a::test_cli_builds_the_settings_from_the_shipped_defaults` |
| `cli.py:204` (settings.Settings) | `search_above_this_dir` | `True` | `False` | KILLED | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` |
| `cli.py:205` (settings.Settings) | `rawlog` | `rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `cli.py:206` (settings.Settings) | `known_bad_imports` | `settings.DEFAULT_KNOWN_BAD_IMPORTS` | `frozenset()` | KILLED | `test_wiring_4a::test_cli_builds_the_settings_from_the_shipped_defaults` |
| `cli.py:207` (settings.Settings) | `also_needs` | `settings.DEFAULT_ALSO_NEEDS` | `{}` | KILLED | `test_wiring_4a::test_cli_builds_the_settings_from_the_shipped_defaults` |
| `cli.py:208` (settings.Settings) | `extra_requirements_file` | `'extra_requirements.txt'` | `"wiring_probe.txt"` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `cli.py:201` (Path.cwd().expanduser().resolve) | `strict` | `True` | `False` | OPEN HOLE | **see below** |
| `cli.py:212` (pipeline.resolve_target) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `cli.py:214` (pipeline.feeling_lucky) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `cli.py:215` (pipeline.feeling_lucky) | `positional 1` | `target` | `__import__("veny.state", fromlist=["Target"]…` | KILLED | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |
| `cli.py:216` (pipeline.feeling_lucky) | `my_name` | `MY_NAME` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |
| `cli.py:217` (pipeline.feeling_lucky) | `rawlog` | `rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `cli.py:222` (ek.configure_logging) | `positional 0` | `MY_NAME` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice` |
| `cli.py:222` (ek.configure_logging) | `log_level` | `log_mode` | `logging.CRITICAL` | KILLED | `test_cli_entry_point::test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice` |
| `cli.py:222` (ek.configure_logging) | `rawlog` | `rawlog` | `True` | KILLED | `test_cli_entry_point::test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug` |
| `cli.py:225` (pipeline.run) | `positional 0` | `run_settings` | `__import__("veny.settings", fromlist=["Setti…` | KILLED | `test_cli_entry_point::test_state_directory_ignores_argv0` |
| `cli.py:225` (pipeline.run) | `positional 1` | `args` | `argparse.Namespace()` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `cli.py:225` (pipeline.run) | `positional 2` | `target` | `__import__("veny.state", fromlist=["Target"]…` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `cli.py:225` (pipeline.run) | `start_time` | `start_time` | `__import__("datetime").datetime(2000, 1, 1)` | KILLED | `test_cli_entry_point::test_the_run_is_timed_from_the_moment_veny_started` |
| `cli.py:228` (logging.info) | `positional 0` | `'%s'` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_a_run_with_no_script_is_a_usage_error` |
| `cli.py:228` (logging.info) | `positional 1` | `exc` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_a_run_with_no_script_is_a_usage_error` |
| `cli.py:231` (logging.error) | `positional 0` | `'%s'` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_maps_a_failed_venv_build_to_status_one` |
| `cli.py:231` (logging.error) | `positional 1` | `exc` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_maps_a_failed_venv_build_to_status_one` |
| `cli.py:238` (print) | `positional 0` | `str(exc)` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_maps_a_missing_uv_to_status_one` |
| `cli.py:238` (print) | `file` | `sys.stderr` | `sys.stdout` | KILLED | `test_cli_entry_point::test_main_maps_a_missing_uv_to_status_one` |
| `cli.py:238` (str) | `positional 0` | `exc` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_main_maps_a_missing_uv_to_status_one` |
| `cli.py:240` (ek.print_all_errors) | `positional 0` | `memory_handler` | `None` | KILLED | `test_wiring_4b::test_the_error_dump_gets_this_runs_handler_and_this_runs_rawlog[rawlog]` |
| `cli.py:240` (ek.print_all_errors) | `positional 1` | `rawlog` | `True` | KILLED | `test_wiring_4b::test_the_error_dump_gets_this_runs_handler_and_this_runs_rawlog[normal]` |
