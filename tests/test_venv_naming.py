"""Tests for veny's venv naming and interpreter selection."""

import sys

from veny import cache_search, environment, stdlib_index
from veny import cli as veny


def an_options() -> veny.Options:
    """Build an Options carrying only what these helpers read.

    It no longer takes a python_command: phase 4a moved that onto the Target,
    and interpreter_tag never read it -- which is exactly what the test below
    pins.
    """
    options = veny.Options()
    options.stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )
    return options


def test_venv_build_interpreter_prefers_the_classified_interpreter() -> None:
    """Building with sys.executable installs into a venv for the wrong Python."""
    assert (
        environment.venv_build_interpreter("/usr/bin/python3.12")
        == "/usr/bin/python3.12"
    )


def test_venv_build_interpreter_falls_back_when_no_preferred_python_was_found() -> None:
    """find_preferred_python_version() returns "" when the preferred Python is absent."""
    assert environment.venv_build_interpreter("") == sys.executable


def test_interpreter_tag_comes_from_the_stdlib_index() -> None:
    """A mutation reading the tag out of the run's interpreter must fail here.

    an_options() always builds stdlib for (3, 12), and carries no interpreter
    of its own at all since phase 4a moved python_command onto the Target --
    so "3.12" can only have come from options.stdlib.
    """
    options = an_options()
    assert options.stdlib.python_version == (
        3,
        12,
    )  # sanity: the two sources really disagree
    assert cache_search.interpreter_tag(options.stdlib) == "3.12"
