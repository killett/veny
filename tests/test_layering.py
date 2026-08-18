"""Enforce the one-way import direction the re-architecture design fixes."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "veny"

# Module (relative to src/veny, without .py) -> names it may NOT import from veny.
FORBIDDEN = {
    "settings": {
        "cli",
        "alias_index",
        "venv_cache",
        "stdlib_index",
        "pypi_client",
        "json_types",
        "analysis",
    },
    # The package root. It carries only __version__ today and must stay that
    # way -- it runs at import time, before anything else, so anything it
    # imported from within veny would be a strong hint of a cycle. Forbid
    # everything, the same way settings.py (the bottom of the design's
    # layering stack) does.
    "__init__": {
        "cli",
        "analysis",
        "alias_index",
        "venv_cache",
        "stdlib_index",
        "pypi_client",
        "json_types",
        "settings",
    },
    "analysis/literals": {
        "cli",
        "alias_index",
        "venv_cache",
        "stdlib_index",
        "pypi_client",
        "json_types",
    },
    "analysis/custom_modules": {
        "cli",
        "alias_index",
        "venv_cache",
        "stdlib_index",
        "pypi_client",
        "json_types",
    },
    "analysis/call_graph": {
        "cli",
        "alias_index",
        "venv_cache",
        "stdlib_index",
        "pypi_client",
        "json_types",
        "settings",
    },
    # The analysis subpackage marker. Plan 3b re-exports its new leaf modules
    # from here, so this is exactly where a `from ..cli import Options`
    # convenience import would first appear -- give it the same forbidden set
    # as its leaf modules rather than leaving it uncovered.
    "analysis/__init__": {
        "cli",
        "alias_index",
        "venv_cache",
        "stdlib_index",
        "pypi_client",
        "json_types",
    },
    "alias_index": {"cli", "venv_cache", "stdlib_index", "json_types", "analysis"},
    # alias_index -> pypi_client is a real, sanctioned dependency (alias
    # resolution ranks candidates by confirming them against PyPI), so
    # pypi_client is deliberately absent from this forbidden set.
    "venv_cache": {
        "cli",
        "alias_index",
        "stdlib_index",
        "pypi_client",
        "json_types",
        "analysis",
    },
    "pypi_client": {
        "cli",
        "alias_index",
        "venv_cache",
        "stdlib_index",
        "json_types",
        "analysis",
    },
    "stdlib_index": {
        "cli",
        "alias_index",
        "venv_cache",
        "pypi_client",
        "json_types",
        "analysis",
    },
    # json_types -> alias_index and json_types -> stdlib_index are both real,
    # sanctioned dependencies (it registers their types for JSON
    # serialization), so both are deliberately absent from this forbidden set.
    "json_types": {"cli", "venv_cache", "pypi_client", "analysis"},
}


def veny_imports(path: Path) -> set[str]:
    """Return the veny module names a source file imports, at any nesting depth.

    Args:
        path: The source file to read.

    Returns:
        Top-level veny module names, e.g. {"cli", "analysis"}.
    """
    found: set[str] = set()
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # `from . import x` has module None; `from .analysis.literals import y`
            # has module "analysis.literals".
            if node.level and node.module:
                found.add(node.module.split(".")[0])
            elif node.level:
                found.update(alias.name for alias in node.names)
            elif node.module == "veny":
                found.update(alias.name for alias in node.names)
            elif node.module and node.module.startswith("veny."):
                found.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("veny."):
                    found.add(alias.name.split(".")[1])
    return found


def test_no_module_imports_above_its_layer() -> None:
    """A module reaching back up the stack cannot be tested in isolation."""
    violations = []
    for module, forbidden in FORBIDDEN.items():
        path = SRC / f"{module}.py"
        assert path.is_file(), f"{module}.py is missing; update FORBIDDEN"
        for imported in sorted(veny_imports(path) & forbidden):
            violations.append(f"{module} imports {imported}")
    assert violations == [], violations


def test_the_guard_covers_every_module_it_should() -> None:
    """A new module with no FORBIDDEN entry would be silently unguarded.

    `__init__.py` files are included -- a package `__init__` re-exporting a
    forbidden name is exactly as much of a layering violation as the module
    itself importing it, and this used to let `analysis/__init__.py` (and
    `src/veny/__init__.py`) import anything with neither test noticing.
    `__main__.py` stays exempt: it legitimately imports `cli` to invoke
    `main()`, and nothing else in the tree may.
    """
    on_disk = {
        str(p.relative_to(SRC).with_suffix("")).replace("\\", "/")
        for p in SRC.rglob("*.py")
        if p.name != "__main__.py"
    }
    unguarded = on_disk - set(FORBIDDEN) - {"cli"}
    assert unguarded == set(), f"add these to FORBIDDEN: {sorted(unguarded)}"


def test_veny_imports_recognizes_every_spelling_of_a_veny_import(
    tmp_path: Path,
) -> None:
    """The guard is only as good as the import forms this helper can see.

    Args:
        tmp_path: Pytest's per-test temporary directory fixture.
    """
    # Each spelling targets a distinct top-level name (alias_index / cli /
    # analysis / settings) so no two lines could contribute the same result
    # and mask one another -- "cli" comes only from `from veny import cli`,
    # so if that spelling were unrecognized this test would fail on "cli"
    # going missing rather than merely being redundantly present.
    source = (
        "import os\n"
        "import veny.alias_index\n"
        "from veny import cli\n"
        "from veny.analysis.literals import safe_eval\n"
        "from . import settings\n"
        "from ..settings import Settings\n"
    )
    path = tmp_path / "sample.py"
    path.write_text(source)
    # `from . import settings` and `from ..settings import Settings` both
    # contribute "settings" to the result; the set collapsing the two
    # spellings to one member is correct, not a missing case.
    assert veny_imports(path) == {"alias_index", "cli", "analysis", "settings"}
