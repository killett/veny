"""Suite-wide fixtures."""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_home_and_working_directory(tmp_path_factory, monkeypatch):
    """Give every test a throwaway HOME and working directory.

    veny keeps its state under Path.home() / "veny" -- venvs, the alias cache,
    the user's module_aliases.toml -- and dict_of_custom_modules writes its
    pickle into the working directory. Any test that drives a run without
    isolating both would read and write the developer's real state and leave
    files in the repository. A test that sets its own HOME or cwd still does;
    monkeypatch applies the later setting.

    Separate directories, not tmp_path itself, so a test's own tmp_path holds
    only what that test put there.
    """
    monkeypatch.setenv("HOME", os.fspath(tmp_path_factory.mktemp("home")))
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))
