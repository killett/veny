"""Tests for veny's venv naming and interpreter selection."""

import sys

from veny import cli as veny
from veny import stdlib_index


def an_options(python_command: str) -> veny.Options:
    """Build an Options carrying only what these helpers read."""
    options = veny.Options()
    options.python_command = python_command
    options.stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )
    return options


def test_venv_build_interpreter_prefers_the_classified_interpreter() -> None:
    """Building with sys.executable installs into a venv for the wrong Python."""
    assert (
        veny.venv_build_interpreter(an_options("/usr/bin/python3.12"))
        == "/usr/bin/python3.12"
    )


def test_venv_build_interpreter_falls_back_when_no_preferred_python_was_found() -> None:
    """find_preferred_python_version() returns "" when the preferred Python is absent."""
    assert veny.venv_build_interpreter(an_options("")) == sys.executable


def test_interpreter_tag_comes_from_the_stdlib_index() -> None:
    """A mutation reading the tag out of python_command must fail here: the two sources disagree.

    an_options() always builds stdlib for (3, 12); giving python_command a
    different minor version means "3.12" can only come from options.stdlib.
    """
    options = an_options("/usr/bin/python3.9")
    assert options.stdlib.python_version == (
        3,
        12,
    )  # sanity: the two sources really disagree
    assert veny.interpreter_tag(options) == "3.12"
