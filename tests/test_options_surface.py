"""Tests for which fields veny's Options class carries."""

import argparse

import veny

RETIRED_FIELDS = {
    "univ_defs_path",
    "univ_defs_sys_path_script",
    "mydiff_path",
    "myaudit_path",
    "multireplace_path",
    "treeview_path",
    "printall_path",
}


def test_options_no_longer_carries_helper_script_paths():
    options = veny.Options()
    present = RETIRED_FIELDS & set(vars(options))
    assert present == set(), f"retired fields still on Options: {sorted(present)}"


def test_options_still_carries_the_directories_veny_uses():
    options = veny.Options()
    assert options.my_dir == options.home / options.my_name
    assert options.packages_dir == options.my_dir / "packages"


def test_options_args_defaults_to_none_after_the_emmykit_swap():
    options = veny.Options()
    assert options.args is None
    assert not isinstance(options.args, argparse.Namespace)
