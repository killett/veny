# Phase 4a wiring index — every argument, measured

**What was swept.** Every argument at every call site in `src/veny/cli.py`,
`src/veny/pipeline.py` and `src/veny/state.py` that phase 4a created or
changed — 178 arguments across 39 distinct callees. The site list was
generated from the AST of the three files rather than written by hand: 3e's
Task 3 symbol sweep worked from a list and missed an entire spelling
(`veny.Options`), and this index exists partly so that cannot recur. The
harness is `scripts/wiring_sweep_4a.py`.

**`run_options.py`'s five sites are counted here for the first time.** 3e's
Task 8 scoped its sweep to `cli.py` and `pipeline.py`, so `Options.set_venv_dir`
and its five argument-carrying call sites were outside the 458-argument
accounting, outside the 278 substitutions and outside the "47 unpinned"
headline. Task 6 deleted `set_venv_dir`; its replacement,
`state.VenvHandle.for_dir`, is in the table below at all four of its sites.
**That closes PROGRESS.md's "`run_options.py` has never been through the
STANDING CHECK" item.**

**How each row was measured.** The argument's expression is replaced, in
place, with a type-correct but wrong value; the module is import-checked; then
the whole suite runs. The first test to fail is the named killer. Nothing
fails: **OPEN HOLE**. Callee never reads it: **DEAD ARGUMENT**, listed
separately from the holes so the headline cannot blur the two.

**One trap worth recording.** `pixi run` sets `PYTHONPATH=src`, and
`tests/test_import_guard.py` spawns its own subprocess that needs it. The
first run of this sweep invoked pytest without that variable, so that one test
failed under *every* mutation and reported 86 spurious kills — which would
have hidden every real hole behind it. Any future sweep must run pytest with
`PYTHONPATH=src`, or through `pixi run`.

## The headline

| | |
|---|---|
| Arguments swept | **178** |
| Killed by a named test | **162** |
| OPEN HOLE | **6** |
| DEAD ARGUMENT | **5** |
| Measured by driving rather than substitution | **5** |

The 162 include 24 that only a *second* substitution could kill: the first
pass's generic replacement happened to equal the real value at that site (an
empty alias index where the test's index is already empty, `True` where the
expression was already `True`). Those are recorded as killed, on the strength
of the second pass, and the weak substitution is not counted as evidence of
anything.

**24 holes were closed inside this task** by `tests/test_wiring_4a.py`, which
spies on each callee and asserts **identity** — the object must be the one the
run built, not an equal one. Equality is not enough: a fresh `Settings` with
the same field values passes an equality check and fails an identity one, and
"a fresh one of the same type" is exactly the substitution these rows failed
under.

## The 6 OPEN HOLEs, each with its reason

1. **`pipeline.py:755` `stdlib_index.resolve(python_command)`.** Substituting
   an unknown interpreter name changes nothing observable: `resolve` falls
   back to the running interpreter for any command it cannot probe, which is
   the same index the real value produces in a test environment with one
   Python. Closing it needs a second real interpreter on the machine, which
   the suite does not assume. **Not closable in-process.**
2. **`pipeline.py:780` `settings.my_dir.mkdir(parents=True)`** and
3. **`pipeline.py:780` `settings.my_dir.mkdir(exist_ok=True)`.** Flipping
   either to `False` changes nothing under test: every driver uses a `tmp_path`
   whose parent exists and whose `my_dir` does not. `parents=False` would only
   bite on a home directory that does not exist, and `exist_ok=False` only on a
   second run against the same directory in one process. Low value, and
   pinning them would mean asserting on `mkdir`'s arguments rather than on any
   behaviour.
4. **`pipeline.py:903` `_load_last_used(options)`.** The receiver is
   unpinnable for the reason 3e recorded about `getattr` receivers: emmykit's
   `load_last_used_options` fills the template it is handed, so a fresh
   `Options` behaves identically to the run's own. It stops being a hole in
   phase 4b, which replaces the template with a `LastUsed` record that carries
   real values.
5. **`pipeline.py:434` and 6. `pipeline.py:869` `run_script(rawlog=…)`** —
   see the DEAD ARGUMENT list; these two are the same finding, counted once
   there and once here because a reader looking for either heading should find
   them.

## The 5 DEAD ARGUMENTS

Passed and never read. Deletion candidates for phase 4c, not test gaps.

- **`pipeline.py:434`, `:846`, `:869` `run_script(rawlog=…)`** — 3e's latent
  defect 3, **re-confirmed on 2026-08-21 and unchanged**. `run_script` reads
  `rawlog` only to guard its announce line, and all three of those sites leave
  `announce` False, so the value cannot reach anything. The fourth site
  (`:953`, the venv launch) passes `announce=True` and *is* killed, by
  `test_cli_entry_point::test_only_the_venv_launch_announces_the_command_it_is_about_to_run`.
  This is a behaviour question as much as a finding: if any of those three
  launches is ever meant to announce itself, `rawlog` becomes live there and
  the rows close on their own.
- **`pipeline.py:195` `alias_index.ResolvedImport(pip_name=import_name)`** —
  the probe environment builds a record whose two fields are the same string
  by construction, and `verify.check_packages_in_venv`, given a `record`,
  reads only `import_name`. No substitution can distinguish them.
- **`pipeline.py:682` `state.VenvHandle.for_dir(record_venv_state(...))`** —
  not dead, but not substitutable either: replacing the whole expression
  removes the call whose effect is under test. Measured by driving instead —
  `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair`
  kills every one of `record_venv_state`'s nine arguments.

## Measured by driving rather than substitution (5)

Multi-line expressions the harness could not rewrite in place. Each is
measured by a test that drives both directions instead:

| Expression | Site | How it is measured |
|---|---|---|
| `not getattr(args, 'rc', …) and not getattr(args, 'no_cache', …)` | `pipeline.py:809` | `test_wiring_4a::test_either_refresh_flag_turns_the_custom_module_cache_off` (both flags, parametrized) and `…_is_on_when_neither_flag_is_given` |
| `verify.source_import_names(…)` inside `check_packages_in_venv` | `pipeline.py:858` | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `verify.source_import_names(…)` inside `find_match_dir_in_cache` | `pipeline.py:895` | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `lambda: _load_last_used(…)` | `pipeline.py:902` | `test_wiring_4a::test_the_last_used_callback_carries_this_runs_target_and_cutoff` |
| `frozenset(verify.verify_and_repair_imports(…))` | `pipeline.py:666` | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run`, which kills all seven of its arguments |
| `cache_search.rename_venv(…)` | `pipeline.py:967` | `test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built` |

## Every argument, measured

`Substitute` is the value the expression was replaced with. A row whose
substitute reads `-` was measured by driving, per the table above.

| Site | Argument | Expression | Substitute | Verdict | Killed by |
|---|---|---|---|---|---|
| `cli.py:184` (settings.Settings) | `my_name` | `options.my_name` | `"wiring-probe"` | KILLED | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone` |
| `cli.py:185` (settings.Settings) | `my_dir` | `options.home / options.my_name` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `cli.py:186` (settings.Settings) | `cwd` | `options.cwd` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone` |
| `cli.py:187` (settings.Settings) | `venv_name` | `'myenv'` | `"wiringprobe"` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `cli.py:188` (settings.Settings) | `stay_out_list` | `settings.DEFAULT_STAY_OUT_LIST` | `()` | KILLED | `test_wiring_4a::test_cli_builds_the_settings_from_the_shipped_defaults` |
| `cli.py:189` (settings.Settings) | `search_above_this_dir` | `True` | `False` | KILLED | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` |
| `cli.py:190` (settings.Settings) | `rawlog` | `options.rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `cli.py:191` (settings.Settings) | `known_bad_imports` | `settings.DEFAULT_KNOWN_BAD_IMPORTS` | `frozenset()` | KILLED | `test_wiring_4a::test_cli_builds_the_settings_from_the_shipped_defaults` |
| `cli.py:192` (settings.Settings) | `also_needs` | `settings.DEFAULT_ALSO_NEEDS` | `{}` | KILLED | `test_wiring_4a::test_cli_builds_the_settings_from_the_shipped_defaults` |
| `cli.py:193` (settings.Settings) | `extra_requirements_file` | `'extra_requirements.txt'` | `"wiring_probe.txt"` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:98` (alias_index.build) | `positional 0` | `python_command` | `"wiring-probe-python"` | KILLED | `test_cli_entry_point::test_build_alias_index_reads_this_runs_own_directory_and_interpreter` |
| `pipeline.py:99` (alias_index.build) | `positional 1` | `settings.my_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_build_alias_index_reads_this_runs_own_directory_and_interpreter` |
| `pipeline.py:100` (alias_index.build) | `offline` | `getattr(args, 'offline', False)` | `True` | KILLED | `test_split_imports::test_the_index_reaches_pypi_by_default` |
| `pipeline.py:135` (analysis_scan.find_imports_in_script) | `is_stdlib` | `is_stdlib` | `(lambda name: True)` | KILLED | `test_import_discovery::test_the_scan_adapter_lets_the_scanner_name_the_files_it_opens` |
| `pipeline.py:135` (analysis_scan.find_imports_in_script) | `positional 0` | `settings` | `_WIRING_SETTINGS` | KILLED | `test_import_discovery::test_the_scan_adapter_lets_the_scanner_name_the_files_it_opens` |
| `pipeline.py:135` (analysis_scan.find_imports_in_script) | `positional 1` | `first_path` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_import_discovery::test_the_scan_adapter_lets_the_scanner_name_the_files_it_opens` |
| `pipeline.py:135` (analysis_scan.find_imports_in_script) | `scan` | `scan` | `ImportScan()` | KILLED | `test_import_discovery::test_the_scan_adapter_lets_the_scanner_name_the_files_it_opens` |
| `pipeline.py:146` (stdlib_index.hints_for) | `positional 0` | `scan.seen_stdlib_imports` | `set()` | KILLED | `test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package` |
| `pipeline.py:176` (environment.create_venv) | `positional 0` | `venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_classify::test_the_probe_venv_is_asked_about_the_interpreter_it_just_built` |
| `pipeline.py:176` (environment.venv_build_interpreter) | `positional 0` | `target.python_command` | `"wiring-probe-python"` | KILLED | `test_classify::test_split_imports_probe_venv_is_given_the_classified_interpreter` |
| `pipeline.py:176` (environment.create_venv) | `positional 1` | `environment.venv_build_interpreter(target.python_command)` | `"/tmp/veny-wiring-probe/bin/python"` | KILLED | `test_classify::test_split_imports_probe_venv_is_given_the_classified_interpreter` |
| `pipeline.py:193` (verify.check_packages_in_venv) | `positional 0` | `environment.venv_python_for(venv_dir)` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_classify::test_the_probe_venv_is_asked_about_the_interpreter_it_just_built` |
| `pipeline.py:193` (environment.venv_python_for) | `positional 0` | `venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled` |
| `pipeline.py:194` (verify.check_packages_in_venv) | `record` | `alias_index.ResolvedImport(import_name=import_name, pip_na` | `alias_index.ResolvedImport(import_name="wiri` | MULTILINE | **see below** |
| `pipeline.py:195` (alias_index.ResolvedImport) | `import_name` | `import_name` | `"wiringprobe"` | KILLED | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled` |
| `pipeline.py:195` (alias_index.ResolvedImport) | `pip_name` | `import_name` | `"wiringprobe"` | OPEN HOLE | **see below** |
| `pipeline.py:234` (classify.split_imports) | `positional 0` | `scan` | `ImportScan()` | KILLED | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled` |
| `pipeline.py:235` (classify.split_imports) | `aliases` | `aliases` | `alias_index.empty(__import__('pathlib').Path` | KILLED | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled` |
| `pipeline.py:236` (classify.split_imports) | `known_bad_imports` | `settings.known_bad_imports` | `frozenset()` | KILLED | `test_classify::test_a_run_whose_every_import_is_bad_builds_no_probe_venv` |
| `pipeline.py:237` (classify.split_imports) | `also_needs` | `settings.also_needs` | `{}` | KILLED | `test_classify::test_split_imports_expands_also_needs_onto_the_uninstalled_records` |
| `pipeline.py:238` (classify.split_imports) | `extra_requirements` | `extra_requirements` | `{}` | KILLED | `test_classify::test_reqs_requirements_are_counted_before_the_zero_import_early_return` |
| `pipeline.py:239` (classify.split_imports) | `use_reqs` | `getattr(args, 'reqs', False)` | `True` | KILLED | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found` |
| `pipeline.py:240` (_probe_venv) | `positional 0` | `target` | `_WIRING_TARGET` | KILLED | `test_classify::test_split_imports_probe_venv_is_given_the_classified_interpreter` |
| `pipeline.py:240` (classify.split_imports) | `probe` | `_probe_venv(target)` | `contextlib.nullcontext(lambda name: True)` | KILLED | `test_classify::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled` |
| `pipeline.py:241` (classify.split_imports) | `rawlog` | `settings.rawlog` | `True` | KILLED | `test_classify::test_the_classification_adapter_lets_classify_report_each_import` |
| `pipeline.py:285` (find_imports_in_script) | `is_stdlib` | `is_stdlib` | `(lambda name: True)` | KILLED | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found` |
| `pipeline.py:285` (find_imports_in_script) | `positional 0` | `settings` | `_WIRING_SETTINGS` | KILLED | `test_state_values::test_the_run_builds_exactly_one_settings` |
| `pipeline.py:285` (find_imports_in_script) | `positional 1` | `scan` | `ImportScan()` | KILLED | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found` |
| `pipeline.py:285` (find_imports_in_script) | `positional 2` | `python_file` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found` |
| `pipeline.py:295` (split_imports) | `positional 0` | `settings` | `_WIRING_SETTINGS` | KILLED | `test_wiring_4a::test_split_imports_gets_this_runs_index_flags_and_pins` |
| `pipeline.py:296` (split_imports) | `positional 1` | `scan` | `ImportScan()` | KILLED | `test_import_discovery::test_list_packages_scans_one_script_and_classifies_what_it_found` |
| `pipeline.py:297` (split_imports) | `positional 2` | `target` | `_WIRING_TARGET` | KILLED | `test_wiring_4a::test_split_imports_gets_this_runs_index_flags_and_pins` |
| `pipeline.py:298` (split_imports) | `args` | `args` | `argparse.Namespace()` | KILLED | `test_wiring_4a::test_split_imports_gets_this_runs_index_flags_and_pins` |
| `pipeline.py:299` (split_imports) | `aliases` | `aliases` | `alias_index.empty(__import__('pathlib').Path` | KILLED | `test_wiring_4a::test_split_imports_gets_this_runs_index_flags_and_pins` |
| `pipeline.py:300` (split_imports) | `extra_requirements` | `extra_requirements` | `{}` | KILLED | `test_wiring_4a::test_split_imports_gets_this_runs_index_flags_and_pins` |
| `pipeline.py:385` (state.Target) | `python_script` | `python_script` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |
| `pipeline.py:386` (state.Target) | `script_dir` | `script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |
| `pipeline.py:387` (state.Target) | `script_args` | `tuple(getattr(args, 'script_args', []) or [])` | `[]` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:388` (state.Target) | `python_command` | `''` | `"wiring-probe-python"` | KILLED | `test_state_values::test_resolve_target_returns_a_target_built_from_the_namespace` |
| `pipeline.py:389` (state.Target) | `timestamp` | `dt.datetime.now().strftime('%Y%m%d-%H%M%S')` | `"20000101-000000"` | KILLED | `test_wiring_4a::test_the_run_stamps_its_target_with_the_time_it_started` |
| `pipeline.py:423` (last_used.load_last_used_venv_python) | `positional 0` | `options` | `run_options.Options()` | KILLED | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |
| `pipeline.py:424` (last_used.load_last_used_venv_python) | `script_dir` | `target.script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |
| `pipeline.py:425` (last_used.load_last_used_venv_python) | `python_script` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |
| `pipeline.py:426` (last_used.load_last_used_venv_python) | `pathlibcutoff` | `pathlibcutoff` | `"00000000-000000"` | KILLED | `test_cli_entry_point::test_main_asks_the_last_used_loader_about_this_script` |
| `pipeline.py:427` (last_used.load_last_used_venv_python) | `rawlog` | `rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:431` (run_script) | `positional 0` | `last_used_venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:432` (run_script) | `positional 1` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:433` (run_script) | `positional 2` | `list(target.script_args)` | `[]` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:434` (run_script) | `rawlog` | `rawlog` | `True` | OPEN HOLE | **see below** |
| `pipeline.py:523` (warn_about_system_packages) | `positional 0` | `scan` | `ImportScan()` | KILLED | `test_import_discovery::test_report_warns_about_a_standard_library_import_that_needs_a_system_package` |
| `pipeline.py:561` (last_used.load_last_used_options) | `positional 0` | `options` | `run_options.Options()` | KILLED | `test_last_used::test_the_last_used_adapter_hands_over_this_runs_script_and_cutoff` |
| `pipeline.py:562` (last_used.load_last_used_options) | `script_dir` | `target.script_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `pipeline.py:563` (last_used.load_last_used_options) | `python_script` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `pipeline.py:564` (last_used.load_last_used_options) | `pathlibcutoff` | `pathlibcutoff` | `"00000000-000000"` | KILLED | `test_last_used::test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to` |
| `pipeline.py:565` (last_used.load_last_used_options) | `rawlog` | `rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:601` (cache_search.interpreter_tag) | `positional 0` | `stdlib` | `stdlib_index.for_running_interpreter()` | KILLED | `test_uv_backend::test_setup_virtualenv_reports_failure_when_uv_refuses_to_build` |
| `pipeline.py:603` (venv_cache.build_folder_name) | `venv_name` | `settings.venv_name` | `"wiringprobe"` | KILLED | `test_uv_backend::test_setup_virtualenv_reports_failure_when_uv_refuses_to_build` |
| `pipeline.py:604` (venv_cache.build_folder_name) | `interpreter_tag` | `run_tag` | `"0.0"` | KILLED | `test_uv_backend::test_setup_virtualenv_reports_failure_when_uv_refuses_to_build` |
| `pipeline.py:605` (venv_cache.build_folder_name) | `timestamp` | `target.timestamp` | `"20000101-000000"` | KILLED | `test_uv_backend::test_setup_virtualenv_reports_failure_when_uv_refuses_to_build` |
| `pipeline.py:606` (venv_cache.build_folder_name) | `pip_names` | `[record.pip_name for record in requirements.uninstalled]` | `[]` | KILLED | `test_uv_backend::test_setup_virtualenv_reports_failure_when_uv_refuses_to_build` |
| `pipeline.py:609` (state.VenvHandle.for_dir) | `positional 0` | `settings.my_dir / f'failed-{folder_name}'` | `"/tmp/veny-wiring-probe"` | KILLED | `test_uv_backend::test_setup_virtualenv_reports_failure_when_uv_refuses_to_build` |
| `pipeline.py:614` (environment.create_venv) | `positional 0` | `handle.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt` |
| `pipeline.py:614` (environment.venv_build_interpreter) | `positional 0` | `target.python_command` | `"wiring-probe-python"` | KILLED | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt` |
| `pipeline.py:614` (environment.create_venv) | `positional 1` | `environment.venv_build_interpreter(target.python_command)` | `"/tmp/veny-wiring-probe/bin/python"` | KILLED | `test_uv_backend::test_the_venv_folder_name_and_build_interpreter_come_from_this_run` |
| `pipeline.py:629` (environment.write_requirements_file_with_extras) | `positional 0` | `handle.requirements_file` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt` |
| `pipeline.py:630` (environment.write_requirements_file_with_extras) | `positional 1` | `(record.pip_name for record in requirements.uninstalled)` | `iter(())` | KILLED | `test_uv_backend::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt` |
| `pipeline.py:631` (environment.write_requirements_file_with_extras) | `positional 2` | `requirements.extra_requirements` | `{}` | KILLED | `test_uv_backend::test_setup_virtualenv_writes_the_extra_requirements_version_specifiers` |
| `pipeline.py:635` (environment.run_uv_pip) | `positional 0` | `handle.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:635` (environment.run_uv_pip) | `positional 1` | `'install'` | `"uninstall"` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:635` (environment.run_uv_pip) | `positional 2` | `'-r'` | `"-e"` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:635` (environment.run_uv_pip) | `positional 3` | `os.fspath(handle.requirements_file)` | `"/tmp/veny-wiring-probe/requirements.txt"` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:653` (verify.source_import_names) | `positional 0` | `set(requirements.all_imports)` | `frozenset()` | KILLED | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |
| `pipeline.py:654` (verify.source_import_names) | `positional 1` | `requirements.extra_requirements` | `{}` | KILLED | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |
| `pipeline.py:655` (verify.source_import_names) | `positional 2` | `getattr(args, 'reqs', False)` | `not getattr(args, 'reqs', False)` | KILLED | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |
| `pipeline.py:665` (dataclasses.replace) | `positional 0` | `requirements` | `_WIRING_REQUIREMENTS` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:666` (dataclasses.replace) | `uninstalled` | `frozenset(verify.verify_and_repair_imports(venv_python=han` | `set()` | MULTILINE | **see below** |
| `pipeline.py:668` (verify.verify_and_repair_imports) | `venv_python` | `handle.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |
| `pipeline.py:669` (verify.verify_and_repair_imports) | `requirements_file` | `handle.requirements_file` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |
| `pipeline.py:670` (verify.verify_and_repair_imports) | `uninstalled` | `set(requirements.uninstalled)` | `set()` | KILLED | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |
| `pipeline.py:671` (verify.verify_and_repair_imports) | `extra_requirements` | `requirements.extra_requirements` | `{}` | KILLED | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |
| `pipeline.py:672` (verify.verify_and_repair_imports) | `source_names` | `source_names` | `frozenset()` | KILLED | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |
| `pipeline.py:673` (verify.verify_and_repair_imports) | `index` | `aliases` | `alias_index.empty(__import__('pathlib').Path` | KILLED | `test_uv_backend::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |
| `pipeline.py:674` (verify.verify_and_repair_imports) | `rawlog` | `settings.rawlog` | `True` | KILLED | `test_uv_backend::test_setup_virtualenv_lets_the_repair_pass_name_the_package_it_settled_on` |
| `pipeline.py:682` (state.VenvHandle.for_dir) | `positional 0` | `cache_search.record_venv_state(handle.venv_dir, venv_pytho` | `-` | NO SUBSTITUTE | **see below** |
| `pipeline.py:683` (cache_search.record_venv_state) | `positional 0` | `handle.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_uv_backend::test_setup_virtualenv_writes_the_extra_requirements_version_specifiers` |
| `pipeline.py:684` (cache_search.record_venv_state) | `venv_python` | `handle.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:685` (cache_search.record_venv_state) | `venv_name` | `settings.venv_name` | `"wiringprobe"` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:686` (cache_search.record_venv_state) | `timestamp` | `target.timestamp` | `"20000101-000000"` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:687` (cache_search.record_venv_state) | `run_tag` | `run_tag` | `"0.0"` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:688` (cache_search.record_venv_state) | `python_command` | `target.python_command` | `"wiring-probe-python"` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:689` (cache_search.record_venv_state) | `uninstalled` | `set(requirements.uninstalled)` | `set()` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:690` (cache_search.record_venv_state) | `extra_requirements` | `requirements.extra_requirements` | `{}` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:691` (cache_search.record_venv_state) | `rawlog` | `settings.rawlog` | `True` | KILLED | `test_uv_backend::test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename` |
| `pipeline.py:696` (verify.check_packages_in_venv) | `positional 0` | `environment.venv_python_for(handle.venv_dir)` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:696` (environment.venv_python_for) | `positional 0` | `handle.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:697` (verify.check_packages_in_venv) | `uninstalled` | `set(requirements.uninstalled)` | `set()` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:698` (verify.check_packages_in_venv) | `source_names` | `source_names` | `frozenset()` | KILLED | `test_uv_backend::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `pipeline.py:746` (dataclasses.replace) | `positional 0` | `target` | `_WIRING_TARGET` | KILLED | `test_cli_entry_point::test_main_runs_the_script_under_the_running_interpreter_when_nothing_is_missing` |
| `pipeline.py:746` (dataclasses.replace) | `python_command` | `python_command or ''` | `"wiring-probe-python"` | KILLED | `test_wiring_4a::test_the_run_hands_setup_virtualenv_its_own_six_values` |
| `pipeline.py:755` (stdlib_index.resolve) | `positional 0` | `python_command` | `"wiring-probe-python"` | OPEN HOLE | **see below** |
| `pipeline.py:765` (build_alias_index) | `positional 0` | `settings` | `_WIRING_SETTINGS` | KILLED | `test_wiring_4a::test_the_run_builds_its_alias_index_from_its_own_settings` |
| `pipeline.py:765` (build_alias_index) | `positional 1` | `args` | `argparse.Namespace()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:765` (build_alias_index) | `positional 2` | `python_command or ''` | `"wiring-probe-python"` | KILLED | `test_wiring_4a::test_the_run_builds_its_alias_index_from_its_own_settings` |
| `pipeline.py:780` (settings.my_dir.mkdir) | `exist_ok` | `True` | `False` | OPEN HOLE | **see below** |
| `pipeline.py:780` (settings.my_dir.mkdir) | `parents` | `True` | `False` | OPEN HOLE | **see below** |
| `pipeline.py:785` (blank_slate) | `positional 0` | `settings` | `_WIRING_SETTINGS` | KILLED | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone` |
| `pipeline.py:785` (blank_slate) | `positional 1` | `args` | `_WIRING_ARGS` | KILLED | `test_cli_entry_point::test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone` |
| `pipeline.py:796` (environment.parse_extra_requirements) | `positional 0` | `settings.extra_requirements_file` | `"wiring_probe.txt"` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:796` (environment.parse_extra_requirements) | `rawlog` | `settings.rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_requirements_reader_explain_a_missing_file` |
| `pipeline.py:808` (custom_modules.dict_of_custom_modules) | `positional 0` | `settings` | `_WIRING_SETTINGS` | KILLED | `test_cli_entry_point::test_main_lets_the_custom_module_scan_explain_an_empty_cache` |
| `pipeline.py:809` (custom_modules.dict_of_custom_modules) | `use_cache` | `not getattr(args, 'rc', False) and (not getattr(args, 'no_` | `True` | MULTILINE | **see below** |
| `pipeline.py:824` (list_packages) | `positional 0` | `settings` | `_WIRING_SETTINGS` | KILLED | `test_state_values::test_the_run_builds_exactly_one_settings` |
| `pipeline.py:825` (list_packages) | `positional 1` | `scan` | `ImportScan()` | KILLED | `test_wiring_4a::test_the_run_hands_list_packages_the_scan_it_seeded` |
| `pipeline.py:826` (list_packages) | `positional 2` | `target` | `_WIRING_TARGET` | KILLED | `test_state_values::test_the_run_builds_exactly_one_settings` |
| `pipeline.py:827` (list_packages) | `args` | `args` | `argparse.Namespace()` | KILLED | `test_wiring_4a::test_the_run_hands_list_packages_the_scan_it_seeded` |
| `pipeline.py:828` (list_packages) | `aliases` | `aliases` | `alias_index.empty(__import__('pathlib').Path` | KILLED | `test_wiring_4a::test_the_run_hands_list_packages_the_scan_it_seeded` |
| `pipeline.py:829` (list_packages) | `extra_requirements` | `extra_requirements` | `{}` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:830` (list_packages) | `is_stdlib` | `stdlib.__contains__` | `(lambda name: True)` | KILLED | `test_wiring_4a::test_the_run_hands_list_packages_the_scan_it_seeded` |
| `pipeline.py:833` (report) | `positional 0` | `settings` | `_WIRING_SETTINGS` | KILLED | `test_cli_entry_point::test_the_run_reports_the_imports_it_decided_are_missing` |
| `pipeline.py:833` (report) | `positional 1` | `scan` | `ImportScan()` | KILLED | `test_wiring_4a::test_the_run_reports_the_scan_it_filled` |
| `pipeline.py:833` (report) | `positional 2` | `requirements` | `_WIRING_REQUIREMENTS` | KILLED | `test_cli_entry_point::test_the_run_reports_the_imports_it_decided_are_missing` |
| `pipeline.py:843` (run_script) | `positional 0` | `sys.executable` | `"/tmp/veny-wiring-probe/bin/python"` | KILLED | `test_cli_entry_point::test_main_runs_the_script_under_the_running_interpreter_when_nothing_is_missing` |
| `pipeline.py:844` (run_script) | `positional 1` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_runs_the_script_under_the_running_interpreter_when_nothing_is_missing` |
| `pipeline.py:845` (run_script) | `positional 2` | `list(target.script_args)` | `[]` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:846` (run_script) | `rawlog` | `settings.rawlog` | `True` | OPEN HOLE | **see below** |
| `pipeline.py:856` (verify.check_packages_in_venv) | `positional 0` | `environment.venv_python_for(active_venv)` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `pipeline.py:856` (environment.venv_python_for) | `positional 0` | `active_venv` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `pipeline.py:857` (verify.check_packages_in_venv) | `uninstalled` | `set(requirements.uninstalled)` | `set()` | KILLED | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `pipeline.py:858` (verify.check_packages_in_venv) | `source_names` | `verify.source_import_names(set(requirements.all_imports), ` | `frozenset()` | MULTILINE | **see below** |
| `pipeline.py:859` (verify.source_import_names) | `positional 0` | `set(requirements.all_imports)` | `frozenset()` | KILLED | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `pipeline.py:860` (verify.source_import_names) | `positional 1` | `requirements.extra_requirements` | `{}` | KILLED | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `pipeline.py:861` (verify.source_import_names) | `positional 2` | `getattr(args, 'reqs', False)` | `not getattr(args, 'reqs', False)` | KILLED | `test_cli_entry_point::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `pipeline.py:866` (run_script) | `positional 0` | `sys.executable` | `"/tmp/veny-wiring-probe/bin/python"` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:867` (run_script) | `positional 1` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:868` (run_script) | `positional 2` | `list(target.script_args)` | `[]` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:869` (run_script) | `rawlog` | `settings.rawlog` | `True` | OPEN HOLE | **see below** |
| `pipeline.py:890` (cache_search.find_match_dir_in_cache) | `positional 0` | `args` | `argparse.Namespace()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:891` (cache_search.find_match_dir_in_cache) | `my_dir` | `settings.my_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:892` (cache_search.find_match_dir_in_cache) | `venv_name` | `settings.venv_name` | `"wiringprobe"` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:893` (cache_search.find_match_dir_in_cache) | `uninstalled` | `set(requirements.uninstalled)` | `set()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:894` (cache_search.find_match_dir_in_cache) | `extra_requirements` | `requirements.extra_requirements` | `{}` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:895` (cache_search.find_match_dir_in_cache) | `source_names` | `verify.source_import_names(set(requirements.all_imports), ` | `frozenset()` | MULTILINE | **see below** |
| `pipeline.py:896` (verify.source_import_names) | `positional 0` | `set(requirements.all_imports)` | `frozenset()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:897` (verify.source_import_names) | `positional 1` | `requirements.extra_requirements` | `{}` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:898` (verify.source_import_names) | `positional 2` | `getattr(args, 'reqs', False)` | `not getattr(args, 'reqs', False)` | KILLED | `test_cli_entry_point::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `pipeline.py:900` (cache_search.interpreter_tag) | `positional 0` | `stdlib` | `stdlib_index.for_running_interpreter()` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:900` (cache_search.find_match_dir_in_cache) | `tag` | `cache_search.interpreter_tag(stdlib)` | `"0.0"` | KILLED | `test_cli_entry_point::test_main_describes_the_run_to_the_cache_search` |
| `pipeline.py:901` (cache_search.find_match_dir_in_cache) | `rawlog` | `settings.rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:902` (cache_search.find_match_dir_in_cache) | `load_last_used` | `lambda: _load_last_used(options, target, pathlibcutoff=opt` | `(lambda: None)` | MULTILINE | **see below** |
| `pipeline.py:903` (_load_last_used) | `positional 0` | `options` | `run_options.Options()` | OPEN HOLE | **see below** |
| `pipeline.py:904` (_load_last_used) | `positional 1` | `target` | `_WIRING_TARGET` | KILLED | `test_wiring_4a::test_the_last_used_callback_carries_this_runs_target_and_cutoff` |
| `pipeline.py:905` (_load_last_used) | `pathlibcutoff` | `options.pathlibcutoff` | `"00000000-000000"` | KILLED | `test_wiring_4a::test_the_last_used_callback_carries_this_runs_target_and_cutoff` |
| `pipeline.py:906` (_load_last_used) | `rawlog` | `settings.rawlog` | `True` | KILLED | `test_cli_entry_point::test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs` |
| `pipeline.py:915` (setup_virtualenv) | `positional 0` | `settings` | `_WIRING_SETTINGS` | KILLED | `test_wiring_4a::test_the_run_hands_setup_virtualenv_its_own_six_values` |
| `pipeline.py:916` (setup_virtualenv) | `positional 1` | `target` | `_WIRING_TARGET` | KILLED | `test_wiring_4a::test_the_run_hands_setup_virtualenv_its_own_six_values` |
| `pipeline.py:917` (setup_virtualenv) | `positional 2` | `requirements` | `_WIRING_REQUIREMENTS` | KILLED | `test_wiring_4a::test_the_run_hands_setup_virtualenv_its_own_six_values` |
| `pipeline.py:918` (setup_virtualenv) | `args` | `args` | `argparse.Namespace()` | KILLED | `test_wiring_4a::test_the_run_hands_setup_virtualenv_its_own_six_values` |
| `pipeline.py:919` (setup_virtualenv) | `aliases` | `aliases` | `alias_index.empty(__import__('pathlib').Path` | KILLED | `test_wiring_4a::test_the_run_hands_setup_virtualenv_its_own_six_values` |
| `pipeline.py:920` (setup_virtualenv) | `stdlib` | `stdlib` | `stdlib_index.for_running_interpreter()` | KILLED | `test_wiring_4a::test_the_run_hands_setup_virtualenv_its_own_six_values` |
| `pipeline.py:936` (state.VenvHandle.for_dir) | `positional 0` | `match_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_runs_the_script_under_the_cached_venvs_interpreter_on_a_cache_hit` |
| `pipeline.py:949` (run_script) | `positional 0` | `handle.venv_python` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_runs_the_script_under_the_cached_venvs_interpreter_on_a_cache_hit` |
| `pipeline.py:950` (run_script) | `positional 1` | `target.python_script` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_runs_the_script_under_the_cached_venvs_interpreter_on_a_cache_hit` |
| `pipeline.py:951` (run_script) | `positional 2` | `list(target.script_args)` | `[]` | KILLED | `test_cli_entry_point::test_every_launch_path_passes_the_scripts_own_arguments_through` |
| `pipeline.py:952` (run_script) | `rawlog` | `settings.rawlog` | `True` | KILLED | `test_cli_entry_point::test_only_the_venv_launch_announces_the_command_it_is_about_to_run` |
| `pipeline.py:953` (run_script) | `announce` | `True` | `False` | KILLED | `test_cli_entry_point::test_only_the_venv_launch_announces_the_command_it_is_about_to_run` |
| `pipeline.py:967` (state.VenvHandle.for_dir) | `positional 0` | `cache_search.rename_venv(handle.venv_dir, handle.venv_dir.` | `"/tmp/veny-wiring-probe"` | MULTILINE | **see below** |
| `pipeline.py:968` (cache_search.rename_venv) | `positional 0` | `handle.venv_dir` | `__import__("pathlib").Path("/tmp/veny-wiring` | KILLED | `test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built` |
| `pipeline.py:969` (cache_search.rename_venv) | `positional 1` | `handle.venv_dir.name.removeprefix('failed-')` | `"wiring-probe-name"` | KILLED | `test_cli_entry_point::test_main_drops_the_failed_prefix_from_the_venv_it_just_built` |