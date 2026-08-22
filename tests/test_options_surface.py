"""Tests for which fields veny's Options class carries."""

import argparse

import emmykit as ek

from veny import cli as veny

RETIRED_FIELDS = {
    "univ_defs_path",
    "univ_defs_sys_path_script",
    "mydiff_path",
    "myaudit_path",
    "multireplace_path",
    "treeview_path",
    "printall_path",
    "read_files",
    "write_files",
    "download_urls",
    "upload_urls",
    "current_method_name",
    "packages_dir",
    "test_dir",
    "venv_pip",
    "download_script_path",
    "pip_list",
    "simultaneous_success",
    # Drained by phase 4a into the frozen values that replaced them. Listed
    # here so a field cannot creep back onto Options and be read from two
    # places at once, which is the failure this whole phase exists to remove.
    # Target (Task 2):
    "python_command",
    "script_args",
    "script_name",
    # Settings (Task 3), plus the three that turned out to have no readers:
    "venv_name",
    "stay_out_list",
    "search_above_this_dir",
    "known_bad_imports",
    "also_needs",
    "extra_requirements_file",
    "unusual_imports",
    "max_checks",
    "check_interval",
    # ImportScan (Task 4):
    "all_imports",
    "custom_modules",
    "loaded_custom_modules",
    "samedir_files",
    "subfolders",
    "sys_path_hints",
    "seen_stdlib_imports",
    "total_imports",
    # Requirements (Task 5):
    "uninstalled_imports",
    "bad_imports",
    "extra_requirements",
    # VenvHandle (Task 6). venv_dir and venv_python are NOT here: they came
    # back as persistence payload -- see SURVIVING_FIELDS.
    "requirements_file",
    "install_succeeded",
    # Dead since the uv migration (Task 7):
    "current_pip_version",
    "new_pip_version",
}

# What phase 4a deliberately left, and why. Phase 4b deletes the persistence
# group and the class with it; see run_options.py's module docstring.
# Fields veny's Options adds to ek.Options', beyond emmykit's own.
SURVIVING_FIELDS = {
    # Persistence: what ek.save_options_to_json and last_used read. The first
    # four name the file; venv_dir and venv_python ARE the payload the reader
    # recovers, which is why they survived the VenvHandle drain.
    "python_script",
    "script_dir",
    "timestamp",
    "my_name",
    "venv_dir",
    "venv_python",
    "options_json_filepath",
    "pathlibcutoff",
    # Construction inputs cli.main derives the run's Settings from. home and
    # log_mode come from ek.Options and so are not listed here.
    "cwd",
    # Passed as themselves; kept only because they are in the JSON payload,
    # and my_dir because alias_index.empty needs somewhere to put its cache.
    "stdlib",
    "aliases",
    "my_dir",
}


def test_options_no_longer_carries_helper_script_paths():
    options = veny.Options()
    present = RETIRED_FIELDS & set(vars(options))
    assert present == set(), f"retired fields still on Options: {sorted(present)}"


def test_options_carries_nothing_but_the_surviving_fields():
    """The drain is total: every field left is one phase 4a chose to leave.

    Behaviour under test: Options' whole surface, not a sampled subset.

    Concrete bug this catches: a field re-added to Options while its value
    also lives on a Settings, Target, Requirements or VenvHandle. Nothing
    raises when that happens -- the run simply carries the value twice, the
    two can drift, and only a test that happens to read the stale one
    notices. RETIRED_FIELDS alone cannot catch a *new* name; this can.

    Measured against a bare ek.Options rather than an absolute list, so that
    a field emmykit adds to the base class is not reported as one veny grew.
    """
    options = veny.Options()

    venys_own = set(vars(options)) - set(vars(ek.Options()))
    assert venys_own == SURVIVING_FIELDS


def test_options_still_carries_the_directories_veny_uses():
    # my_dir left Options in phase 4a -- Settings owns it -- but cli.main
    # still derives it from these two, so the relationship is pinned here.
    options = veny.Options()
    assert options.home / options.my_name == options.home / "veny"


def test_options_args_defaults_to_the_empty_namespace_emmykit_supplies():
    # veny used to re-declare `args: argparse.Namespace | None = None`, which
    # mypy reported as an incompatible override and which forced two
    # `assert options.args is not None` lines to appease it. emmykit chose the
    # empty-Namespace default deliberately (univ_defs commit 67e054a,
    # 2026-04-04, "Fixed various issues raised by mypy"), so veny now inherits
    # it. Catches: someone re-adding the `| None` re-declaration, which brings
    # the override error and the asserts back.
    options = veny.Options()
    assert isinstance(options.args, argparse.Namespace)
    assert vars(options.args) == {}


def test_a_flag_read_before_parsing_is_false_rather_than_raising():
    # The empty-Namespace default must not change how an unset flag reads.
    # Catches: a default that makes getattr raise, or one that pre-populates
    # flags with truthy values.
    options = veny.Options()
    assert getattr(options.args, "last_used", False) is False
    assert getattr(options.args, "justprint", False) is False


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
    from veny import cli, run_options

    assert cli.Options is run_options.Options
