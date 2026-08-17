"""Pin the restricted expression evaluator veny reads sys.path with."""

import ast
import os

from veny.analysis.literals import collect_pathlib_aliases, safe_eval


def test_a_string_literal_evaluates_to_itself() -> None:
    """Every sys.path string reaches veny through this branch."""
    assert safe_eval('"hello"') == "hello"


def test_a_list_literal_evaluates_to_a_list() -> None:
    """sys.path += [...] is a real idiom; the sequence branch serves it."""
    assert safe_eval("[1, 2]") == [1, 2]


def test_os_path_join_is_evaluated() -> None:
    """os.path.join is the pre-pathlib way to build a sys.path entry."""
    assert safe_eval('os.path.join("a", "b")') == "a/b"


def test_os_getcwd_is_evaluated() -> None:
    """Compared against the live value, so the test is machine-independent."""
    assert safe_eval("os.getcwd()") == os.getcwd()


def test_pathlib_joinpath_is_evaluated() -> None:
    """The alias set is what makes a local name count as pathlib."""
    result = safe_eval('Path("a").joinpath("b", "c")', pathlib_aliases={"Path"})
    assert result == "a/b/c"


def test_an_arbitrary_call_is_refused() -> None:
    """safe_eval runs over untrusted source; it must never execute a call."""
    assert safe_eval('open("x")') is None


def test_collect_pathlib_aliases_finds_a_renamed_import() -> None:
    """Matching the literal name 'Path' would lose every renamed import."""
    tree = ast.parse("from pathlib import Path as P\n")
    assert collect_pathlib_aliases(tree) == {"P"}
