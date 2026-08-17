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
        "pypi_client",
        "json_types",
    },
    "alias_index": {"cli", "venv_cache", "json_types", "analysis"},
    "venv_cache": {"cli", "alias_index", "pypi_client", "json_types", "analysis"},
    "pypi_client": {"cli", "alias_index", "venv_cache", "json_types", "analysis"},
    "stdlib_index": {
        "cli",
        "alias_index",
        "venv_cache",
        "pypi_client",
        "json_types",
        "analysis",
    },
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
    assert violations == []


def test_the_guard_covers_every_module_it_should() -> None:
    """A new module with no FORBIDDEN entry would be silently unguarded."""
    on_disk = {
        str(p.relative_to(SRC).with_suffix("")).replace("\\", "/")
        for p in SRC.rglob("*.py")
        if p.name not in {"__init__.py", "__main__.py"}
    }
    unguarded = on_disk - set(FORBIDDEN) - {"cli"}
    assert unguarded == set(), f"add these to FORBIDDEN: {sorted(unguarded)}"
