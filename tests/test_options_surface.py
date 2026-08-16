"""Tests for which fields veny's Options class carries."""

import argparse

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
}


def test_options_no_longer_carries_helper_script_paths():
    options = veny.Options()
    present = RETIRED_FIELDS & set(vars(options))
    assert present == set(), f"retired fields still on Options: {sorted(present)}"


def test_options_still_carries_the_directories_veny_uses():
    options = veny.Options()
    assert options.my_dir == options.home / options.my_name
    assert options.packages_dir == options.my_dir / "packages"


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
