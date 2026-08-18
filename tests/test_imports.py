"""Pin the AST walker that finds what a module imports and where from."""

import ast

from veny.analysis.imports import SysPathVisitor
from veny.analysis.literals import collect_pathlib_aliases


def test_sys_path_built_with_the_slash_operator_is_discovered() -> None:
    """The '/' gap silently hid whole sys.path directories from veny."""
    tree = ast.parse(
        "import sys\n"
        "from pathlib import Path\n"
        'sys.path.insert(0, Path("/opt/libs") / "extra")\n'
    )
    visitor = SysPathVisitor(collect_pathlib_aliases(tree))
    visitor.visit(tree)

    assert visitor.paths == {"/opt/libs/extra"}
