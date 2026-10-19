"""The suite must never touch the developer's own veny state or working tree."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Read at import, i.e. during collection -- before any per-test fixture has
# had a chance to replace HOME -- so this is the developer's real home.
REAL_HOME = Path(os.path.expanduser("~")).resolve()


def test_each_test_runs_under_a_throwaway_home():
    """No test may resolve veny's state directory under the real home.

    A bug that would make this fail: cli.main derives my_dir from Path.home(),
    so without per-test isolation any test that drives a run creates ~/veny
    and reads the developer's real ~/veny/module_aliases.toml -- a malformed
    one fails tests that have nothing to do with it.
    """
    home = Path.home().resolve()

    assert home != REAL_HOME
    assert not home.is_relative_to(REAL_HOME)


def test_each_test_runs_outside_the_repository():
    """No test may run with the repository as its working directory.

    A bug that would make this fail: dict_of_custom_modules writes its
    .veny_custom_modules_*.pkl into the process's working directory, so a
    test that drives a run from the repository root leaves one there.
    """
    assert not Path.cwd().resolve().is_relative_to(REPO_ROOT)
