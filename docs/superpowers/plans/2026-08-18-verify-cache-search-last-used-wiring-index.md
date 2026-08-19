# Wiring index — phase 3d (`verify.py`, `cache_search.py`, `last_used.py`)

This is the tracked index of the STANDING CHECK PROGRESS records in Gotchas:
*after moving a symbol out of `cli.py`, mutate every argument at the new call
site and confirm a test dies.* Extracting a symbol turns an implicit
`options.<field>` read inside the callee into an explicit argument built at the
call site — a value that could not be mis-wired before the move, and can be
after it, while the new module's own unit tests keep passing because they pass
the value directly. This table names, for every argument at every call site
phase 3d created, the test that fails when that argument is replaced with an
empty, default, or wrong-but-type-correct value. It is an index, not a report:
the substituted values, the before/after counts and the differential evidence
are in `.superpowers/sdd/2026-08-18-verify-cache-search-last-used/task-9-report.md`
(untracked).

Run of record: task 9, **2026-08-18**, against the branch
`verify-cache-search-last-used`, whose phase branch point is **`313e800`**.
**147 arguments across 40 call-site groups; every one of them kills a named
test.** 104 of the 147 did not before task 9. Method, per argument: copy the
file to a scratch directory, substitute in place, run `pixi run pytest -q`,
record the named failures, restore from the copy — never `git stash`, never
`git checkout -- <path>`. Re-run this whole check after any further extraction;
a row whose test no longer dies is a hole, not a stale row.

| Call site | Arguments | Pinned by |
|---|---|---|
| `cli._probe_venv` -> `verify.check_packages_in_venv`, `environment.create_venv` | `check_packages_in_venv/venv_python`, `create_venv/target` | `tests/test_classify.py::test_the_probe_venv_is_asked_about_the_interpreter_it_just_built` |
| ↳ | `check_packages_in_venv/record` | `tests/test_classify.py::test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled` |
| ↳ | `create_venv/python` | `tests/test_classify.py::test_split_imports_probe_venv_is_given_the_classified_interpreter` |
| `cli.main` (already-in-a-virtualenv branch) -> `verify.check_packages_in_venv` | `check_packages_in_venv/venv_python`, `check_packages_in_venv/uninstalled`, `check_packages_in_venv/source_names` | `tests/test_cli_entry_point.py::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `cli.main` (same branch) -> `verify.source_import_names` | `all_imports`, `extra_requirements`, `use_reqs` | `tests/test_cli_entry_point.py::test_main_checks_the_surrounding_virtualenv_against_this_runs_imports` |
| `cli.main` -> `cache_search.find_match_dir_in_cache` | `args`, `my_dir`, `venv_name`, `uninstalled`, `source_names`, `tag`, `rawlog`, `load_last_used` | `tests/test_cli_entry_point.py::test_main_describes_the_run_to_the_cache_search` |
| ↳ | `extra_requirements` | `tests/test_cli_entry_point.py::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `cli.main` -> `verify.source_import_names` (nested in the call above) | `all_imports` | `tests/test_cli_entry_point.py::test_main_describes_the_run_to_the_cache_search` |
| ↳ | `extra_requirements`, `use_reqs` | `tests/test_cli_entry_point.py::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `cli.main` -> `cache_search.rename_venv` | `venv_dir`, `new_name` | `tests/test_cli_entry_point.py::test_main_drops_the_failed_prefix_from_the_venv_it_just_built` |
| `cli._load_last_used` -> `last_used.load_last_used_options` | `options`, `script_dir`, `python_script`, `pathlibcutoff`, `rawlog` | `tests/test_last_used.py::test_the_last_used_adapter_hands_over_this_runs_script_and_cutoff` |
| `cli.main` (--feeling-lucky) -> `last_used.load_last_used_venv_python` | `options`, `script_dir`, `python_script`, `pathlibcutoff`, `rawlog` | `tests/test_cli_entry_point.py::test_main_asks_the_last_used_loader_about_this_script` |
| `cli.main` (--reqs) -> `environment.parse_extra_requirements` | `path`, `rawlog` | `tests/test_cli_entry_point.py::test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check` |
| `cli.setup_virtualenv` -> `cache_search.interpreter_tag` | `result` | `tests/test_uv_backend.py::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `cli.setup_virtualenv` -> `venv_cache.build_folder_name` | `venv_name`, `interpreter_tag`, `timestamp`, `pip_names` | `tests/test_uv_backend.py::test_the_venv_folder_name_and_build_interpreter_come_from_this_run` |
| `cli.setup_virtualenv` -> `environment.create_venv` / `venv_build_interpreter` | `target` | `tests/test_uv_backend.py::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt` |
| ↳ | `python` | `tests/test_uv_backend.py::test_the_venv_folder_name_and_build_interpreter_come_from_this_run` |
| `cli.setup_virtualenv` -> `environment.write_requirements_file_with_extras` | `requirements_file`, `pip_names` | `tests/test_uv_backend.py::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt` |
| ↳ | `extra_requirements` | `tests/test_uv_backend.py::test_setup_virtualenv_writes_the_extra_requirements_version_specifiers` |
| `cli.setup_virtualenv` -> `environment.run_uv_pip` | `venv_python`, `requirements_file` | `tests/test_uv_backend.py::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `cli.setup_virtualenv` -> `verify.source_import_names` | `all_imports`, `extra_requirements`, `use_reqs` | `tests/test_uv_backend.py::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `cli.setup_virtualenv` -> `verify.verify_and_repair_imports` | `venv_python`, `requirements_file`, `uninstalled`, `extra_requirements`, `source_names`, `rawlog` | `tests/test_uv_backend.py::test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run` |
| ↳ | `index` | `tests/test_split_imports.py::test_setup_virtualenv_verifies_every_import_before_reporting_success` |
| `cli.setup_virtualenv` -> `cache_search.record_venv_state` | `venv_dir` | `tests/test_uv_backend.py::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt` |
| ↳ | `venv_python`, `venv_name`, `timestamp`, `run_tag`, `python_command`, `uninstalled`, `extra_requirements`, `rawlog` | `tests/test_uv_backend.py::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `cli.setup_virtualenv` -> `verify.check_packages_in_venv` (final) | `venv_python`, `uninstalled`, `source_names` | `tests/test_uv_backend.py::test_the_manifest_and_the_final_check_describe_the_venv_after_repair` |
| `cache_search.check_venv_dir` -> `verify.check_packages_in_venv` | `venv_python` | `tests/test_cache_search.py::test_check_venv_dir_probes_the_interpreter_inside_the_venv_it_was_given` |
| ↳ | `uninstalled`, `source_names` | `tests/test_cache_search.py::test_check_venv_dir_checks_the_name_the_user_wrote_not_the_distributions_others` |
| `cache_search.find_match_dir_in_cache` -> `check_venv_dir` (last-used branch) | `venv_dir`, `wanted`, `uninstalled`, `source_names`, `rawlog` | `tests/test_cache_search.py::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run` |
| ↳ | `tag`, `candidate_omitted` | `tests/test_cache_search.py::test_a_last_used_hit_still_reads_and_matches_its_own_manifest` |
| `cache_search.find_match_dir_in_cache` -> `check_venv_dir` (--latest branch) | `venv_dir`, `candidate` | `tests/test_cache_search.py::test_a_cache_hit_reads_and_matches_each_manifest_once` |
| ↳ | `wanted`, `tag`, `uninstalled`, `source_names`, `rawlog` | `tests/test_cache_search.py::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run` |
| `cache_search.find_match_dir_in_cache` -> `check_venv_dir` (--oldest branch) | `venv_dir`, `wanted`, `tag`, `uninstalled`, `source_names`, `rawlog`, `candidate` | `tests/test_cache_search.py::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run` |
| `cache_search.find_match_dir_in_cache` -> `check_venv_dir` (--smallest branch) | `venv_dir`, `wanted`, `tag`, `uninstalled`, `source_names`, `rawlog`, `candidate` | `tests/test_cache_search.py::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run` |
| `cache_search.find_match_dir_in_cache` -> `cache_candidates` | `folders`, `tag` | `tests/test_cache_search.py::test_a_cache_hit_reads_and_matches_each_manifest_once` |
| ↳ | `wanted` | `tests/test_cache_search.py::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run` |
| ↳ | `rawlog` | `tests/test_cache_search.py::test_the_cache_search_filters_the_folders_against_this_run_not_a_blank_one` |
| `cache_search.find_match_dir_in_cache` -> `wanted_packages` | `uninstalled`, `extra_requirements` | `tests/test_cache_search.py::test_every_branch_hands_check_venv_dir_the_same_description_of_the_run` |
| `cache_search.record_venv_state` -> `installed_state_in_venv` | `venv_python` | `tests/test_manifest_writing.py::test_record_venv_state_probes_the_given_venv_and_records_the_runs_own_fields` |
| `cache_search.record_venv_state` -> `venv_cache.build_folder_name` | `venv_name`, `interpreter_tag`, `interpreter_tag_fallback`, `timestamp`, `pip_names` | `tests/test_manifest_writing.py::test_record_venv_state_probes_the_given_venv_and_records_the_runs_own_fields` |
| `cache_search.record_venv_state` -> `rename_venv` | `venv_dir`, `new_name` | `tests/test_manifest_writing.py::test_record_venv_state_probes_the_given_venv_and_records_the_runs_own_fields` |
| `cache_search.record_venv_state` -> `venv_cache.write_manifest` | `venv_dir` | `tests/test_manifest_writing.py::test_record_venv_state_probes_the_given_venv_and_records_the_runs_own_fields` |
| `cache_search.record_venv_state` -> `manifest_for` | `uninstalled`, `extra_requirements`, `timestamp`, `python_command`, `run_tag` | `tests/test_manifest_writing.py::test_record_venv_state_probes_the_given_venv_and_records_the_runs_own_fields` |
| ↳ | `versions` | `tests/test_manifest_writing.py::test_record_venv_state_renames_before_writing_the_manifest` |
| ↳ | `venv_tag` | `tests/test_manifest_writing.py::test_record_venv_state_renames_into_agreement_when_the_venvs_tag_differs_from_the_runs` |
| `cache_search.manifest_for` -> `environment.venv_build_interpreter` | `python_command` | `tests/test_manifest_writing.py::test_manifest_for_records_versions_and_specs` |
| `verify.verify_and_repair_imports` -> `check_packages_in_venv` (bulk) | `venv_python` | `tests/test_verify.py::test_every_venv_facing_call_in_the_repair_pass_addresses_the_same_venv` |
| ↳ | `uninstalled`, `source_names` | `tests/test_verify.py::test_a_machine_scoped_failure_leaves_no_persisted_rejection` |
| `verify.verify_and_repair_imports` -> `alias_index.probe_interpreter` | `venv_python` | `tests/test_verify.py::test_every_venv_facing_call_in_the_repair_pass_addresses_the_same_venv` |
| `verify.verify_and_repair_imports` -> `import_outcome_in_venv` | `venv_python` | `tests/test_verify.py::test_every_venv_facing_call_in_the_repair_pass_addresses_the_same_venv` |
| ↳ | `import_name` | `tests/test_verify.py::test_a_machine_scoped_failure_leaves_no_persisted_rejection` |
| `verify.verify_and_repair_imports` -> `repair_unsatisfied_import` | `record`, `installed_distributions`, `outcome`, `index` | `tests/test_verify.py::test_a_machine_scoped_failure_leaves_no_persisted_rejection` |
| ↳ | `venv_python` | `tests/test_verify.py::test_every_venv_facing_call_in_the_repair_pass_addresses_the_same_venv` |
| ↳ | `rawlog` | `tests/test_verify.py::test_the_repair_pass_names_the_package_that_finally_provided_the_import` |
| `verify.verify_and_repair_imports` -> `confirm_if_attributable` | `bulk_branch` | `tests/test_verify.py::test_a_verified_import_is_written_to_the_alias_cache` |
| ↳ | `repair_branch` | `tests/test_verify.py::test_a_record_that_imports_on_the_repair_pass_is_still_credited_to_its_own_package` |
| `verify.verify_and_repair_imports` -> `environment.write_requirements_file_with_extras` | `requirements_file`, `pip_names`, `extra_requirements` | `tests/test_verify.py::test_a_repair_rewrites_requirements_txt_with_the_extra_requirements` |
| `verify.repair_unsatisfied_import` -> `environment.uninstall_from_venv` (eager) | `venv_python` | `tests/test_verify.py::test_every_venv_facing_call_in_the_repair_pass_addresses_the_same_venv` |
| ↳ | `pip_name` | `tests/test_verify.py::test_a_machine_scoped_failure_leaves_no_persisted_rejection` |
| `verify.repair_unsatisfied_import` -> `environment.install_into_venv` (installer closure) | `venv_python` | `tests/test_verify.py::test_every_venv_facing_call_in_the_repair_pass_addresses_the_same_venv` |
| ↳ | `pip_name` | `tests/test_verify.py::test_a_machine_scoped_failure_leaves_no_persisted_rejection` |
| `verify.repair_unsatisfied_import` -> `environment.uninstall_from_venv` (uninstaller closure) | `venv_python` | `tests/test_verify.py::test_every_venv_facing_call_in_the_repair_pass_addresses_the_same_venv` |
| ↳ | `pip_name` | `tests/test_verify.py::test_a_second_candidates_machine_scoped_failure_is_also_not_persisted` |
