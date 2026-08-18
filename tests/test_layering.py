"""Enforce the one-way import direction the re-architecture design fixes."""

import ast
import dataclasses
from pathlib import Path

from veny.analysis.scan_state import ImportScan

SRC = Path(__file__).resolve().parent.parent / "src" / "veny"

# The design's layering stack, bottom to top. A module may import from any
# layer strictly below its own, but never from its own layer's peers (unless
# named in SANCTIONED_EXCEPTIONS below) or from any layer above it.
#
# `analysis` names the whole subpackage as one entry: its submodules
# (`analysis/literals`, `analysis/call_graph`, etc.) share this single layer
# membership and are therefore never forbidden from importing each other,
# the same way a package's internals normally are not layered against
# themselves. Every other entry here is a real top-level module name.
#
# Adding a new module only requires adding its group name to the layer it
# belongs to -- the forbidden set for every module is derived below, not
# hand-written.
LAYERS: list[frozenset[str]] = [
    # The package root. It carries only __version__ today and must stay
    # that way -- it runs at import time, before anything else, so
    # anything it imported from within veny would be a strong hint of a
    # cycle. It sits below even settings.py, so it forbids everything.
    frozenset({"__init__"}),
    frozenset({"settings"}),
    # analysis/* and the index/client modules are peers: neither depends on
    # the other in either direction (analysis takes an injected `is_stdlib`
    # predicate instead of reaching for stdlib_index, and the index/client
    # modules have no reason to read scan results). They sit in the same
    # layer so each forbids the other by default.
    frozenset(
        {
            "analysis",
            "alias_index",
            "venv_cache",
            "stdlib_index",
            "pypi_client",
            "json_types",
        }
    ),
    # state.py carries the products one stage hands to the next. It sits
    # above the index layer because Requirements annotates its members with
    # alias_index.ResolvedImport, and in a layer of its own below classify
    # because classify -- and, later, verify and cache_search -- all need to
    # import it without a same-layer exception.
    frozenset({"state"}),
    # environment.py is the only module that invokes uv; classify.py decides
    # which imports are installed, missing or unusable. They are peers: neither
    # imports the other (classify takes its probe environment as an injected
    # context manager rather than building one), so each forbids the other by
    # default. Both sit above the index layer because they need nothing from
    # each other, and below cli because cli drives them -- and neither has ever
    # heard of Options, so both can be exercised without building the CLI's
    # state object.
    frozenset({"classify", "environment"}),
    frozenset({"cli"}),
]

# Real, sanctioned same-layer dependencies that would otherwise be forbidden
# by the peer rule above. Checked against the actual imports
# (`rg -n '^from \.' src/veny/*.py`) rather than trusted from memory.
SANCTIONED_EXCEPTIONS: dict[str, frozenset[str]] = {
    # alias_index -> pypi_client: alias resolution ranks candidates by
    # confirming them against PyPI.
    "alias_index": frozenset({"pypi_client"}),
    # json_types -> alias_index and json_types -> stdlib_index: it registers
    # both modules' types for JSON serialization.
    "json_types": frozenset({"alias_index", "stdlib_index"}),
}


def _group(module: str) -> str:
    """The layer-group name an on-disk module path belongs to.

    Args:
        module: A module path relative to `src/veny`, without `.py`
            (e.g. "analysis/call_graph").

    Returns:
        The group name used as a LAYERS/SANCTIONED_EXCEPTIONS key
        (e.g. "analysis").
    """
    return module.split("/")[0]


def _layer_index(group: str) -> int | None:
    """The index of `group`'s layer in LAYERS, or None if it is unassigned.

    Args:
        group: A layer-group name, as returned by `_group`.

    Returns:
        The layer's position in LAYERS (0 = bottom), or None if no layer
        names this group.
    """
    for index, layer in enumerate(LAYERS):
        if group in layer:
            return index
    return None


def _forbidden_for(module: str) -> set[str] | None:
    """The set of veny module names `module` may not import.

    Args:
        module: A module path relative to `src/veny`, without `.py`.

    Returns:
        Every name at or above `module`'s own layer, minus its own group
        and any sanctioned exception -- or None if `module`'s group has no
        LAYERS entry (a coverage gap `test_the_guard_covers_every_module_it_should`
        reports).
    """
    group = _group(module)
    index = _layer_index(group)
    if index is None:
        return None
    forbidden: set[str] = set()
    for layer in LAYERS[index:]:
        forbidden |= layer
    forbidden -= {group}
    forbidden -= SANCTIONED_EXCEPTIONS.get(group, frozenset())
    return forbidden


def _on_disk_modules() -> set[str]:
    """Every module path under `src/veny`, relative and without `.py`.

    `__main__.py` is excluded -- it legitimately imports `cli` to invoke
    `main()`, and nothing else in the tree may.
    """
    return {
        str(p.relative_to(SRC).with_suffix("")).replace("\\", "/")
        for p in SRC.rglob("*.py")
        if p.name != "__main__.py"
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
    for module in sorted(_on_disk_modules()):
        forbidden = _forbidden_for(module)
        if forbidden is None:
            # Reported by test_the_guard_covers_every_module_it_should
            # instead -- this module's group has no LAYERS entry at all.
            continue
        path = SRC / f"{module}.py"
        for imported in sorted(veny_imports(path) & forbidden):
            violations.append(f"{module} imports {imported}")
    assert violations == [], violations


def test_the_guard_covers_every_module_it_should() -> None:
    """A new module whose group has no LAYERS entry would be silently unguarded.

    `__init__.py` files are included -- a package `__init__` re-exporting a
    forbidden name is exactly as much of a layering violation as the module
    itself importing it, and this used to let `analysis/__init__.py` (and
    `src/veny/__init__.py`) import anything with neither test noticing.
    `__main__.py` stays exempt: it legitimately imports `cli` to invoke
    `main()`, and nothing else in the tree may.

    Unlike a hand-maintained forbidden-set table, a new module only needs
    its group added to LAYERS (one name) for both this test and
    `test_no_module_imports_above_its_layer` to cover it -- neither test
    needs a bespoke forbidden set written out for it.
    """
    unguarded = sorted(
        module for module in _on_disk_modules() if _layer_index(_group(module)) is None
    )
    assert unguarded == [], f"assign a LAYERS group for: {unguarded}"


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


def test_analysis_never_rebinds_an_importscan_field() -> None:
    """The cli.py bridge hands scan.py the seven live objects options holds
    and relies on them being mutated in place, with no copy-back. A rebind
    of one of ImportScan's fields anywhere under analysis/ would silently
    detach the caller's object mid-scan -- a rebind of `all_imports`,
    `custom_modules`, `loaded_custom_modules` or `seen_stdlib_imports` would
    be caught by existing tests, but a rebind of `samedir_files`,
    `subfolders` or `sys_path_hints` would not be, so this walks the AST
    directly rather than relying on behavioural coverage.

    Field names are read from `ImportScan` itself so a future field is
    covered automatically. Only `ast.Attribute` targets count -- the local
    `scan = scan if scan is not None else ImportScan()` in
    `find_imports_in_script` rebinds a local *name*, not an attribute, and
    must not trip this guard.
    """
    field_names = {f.name for f in dataclasses.fields(ImportScan)}
    violations = []
    for path in sorted((SRC / "analysis").rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            targets: list[ast.expr]
            if isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            elif isinstance(node, ast.Assign):
                targets = node.targets
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr in field_names:
                    violations.append(
                        f"{path.relative_to(SRC)}:{node.lineno} rebinds .{target.attr}"
                    )
    assert violations == [], violations


def test_split_imports_copies_back_every_field_it_owns() -> None:
    """cli.split_imports' copy-back must be total, and only the AST can say so.

    The adapter is the single place a Requirements is written back onto
    Options, and a copy-back that silently drops one field is exactly
    dbf013c's class of bug: the run keeps whatever stale value Options was
    already carrying, so nothing raises, nothing logs, and the whole suite
    stays green while the dropped field is wrong. Only the tests that happen
    to read that one field could ever notice, and a field with no such test
    -- which is how dbf013c survived -- is invisible. So this reads the
    assignments themselves rather than any behaviour.

    The five names are written out rather than derived from Requirements'
    fields: the mapping is deliberately not one-to-one (`total_imports` is a
    property, `seen_stdlib` and `extra_requirements` are pass-throughs that
    Options already holds and must not be re-written), so deriving them would
    only restate whatever state.py currently says. Only `ast.Attribute`
    targets whose value is the name `options` count -- the local `scan = ...`
    and `result = ...` bindings are names, not attributes, and must not trip
    this guard.
    """
    tree = ast.parse((SRC / "cli.py").read_text())
    adapters = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "split_imports"
    ]
    assert len(adapters) == 1, "expected exactly one cli.split_imports"
    written = set()
    for node in ast.walk(adapters[0]):
        targets: list[ast.expr]
        if isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        else:
            continue
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "options"
            ):
                written.add(target.attr)
    assert written == {
        "all_imports",
        "bad_imports",
        "installed_imports",
        "uninstalled_imports",
        "total_imports",
    }
