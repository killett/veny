"""Characterize ImportFunctionCollector before phase 3b extracts it.

Everything here goes through _analyze_module rather than constructing
ImportFunctionCollector directly: the collector fills its own base_classes,
and only _analyze_module copies them onto the ModuleInfo. A test that skips
that step sees an empty base-class map and wrongly concludes inheritance is
broken (see tests/test_call_graph.py for the same rationale).

Note: ModuleInfo.aliases is never populated via this path. visit_Import and
visit_ImportFrom write to the collector's own self.aliases (a separate
attribute from ModuleInfo.aliases), and _analyze_module only copies
collector.base_classes onto module_info.base_classes -- it never copies
collector.aliases onto module_info.aliases. So module_info.aliases is always
{} for any module analyzed through _analyze_module. The alias test below
therefore asserts against top_level_imports, the only ModuleInfo field that
actually carries the resolved module name for an aliased import.
"""

from pathlib import Path

from veny.analysis.call_graph import ModuleInfo
from veny.cli import Options, _analyze_module


def _analyze(source: str, tmp_path: Path) -> tuple[str, dict[str, ModuleInfo]]:
    """Write source to a file and analyze it the way find_imports_in_script does.

    Args:
        source: Python source text to analyze.
        tmp_path: pytest's per-test temporary directory.

    Returns:
        The module key _analyze_module assigned, and the modules_info dict.
    """
    module_path = tmp_path / "mod.py"
    module_path.write_text(source)
    options = Options()
    options.rawlog = True
    modules_info: dict[str, ModuleInfo] = {}
    result = _analyze_module(options, module_path, modules_info, False)
    assert result is not None, "_analyze_module refused the fixture"
    return result[0], modules_info


def test_a_dotted_import_is_normalized_to_its_top_level_name(tmp_path: Path) -> None:
    """Losing the split(".")[0] normalization sends dotted stdlib names to PyPI."""
    source = "import xml.etree.ElementTree\n"
    key, modules_info = _analyze(source, tmp_path)
    assert modules_info[key].top_level_imports == {"xml"}


def test_from_import_records_the_module_not_the_symbol(tmp_path: Path) -> None:
    """Recording the imported symbol instead of its module tries to pip-install a function."""
    source = "from json import loads\n"
    key, modules_info = _analyze(source, tmp_path)
    assert modules_info[key].top_level_imports == {"json"}


def test_a_top_level_import_is_not_recorded_as_an_in_function_import(
    tmp_path: Path,
) -> None:
    """Collapsing the two collections makes the call-graph reachability filter meaningless."""
    source = """\
import os


def go():
    import csv
    return csv
"""
    key, modules_info = _analyze(source, tmp_path)
    info = modules_info[key]
    assert info.top_level_imports == {"os"}
    assert info.functions["go"].imports_in_function == {"csv"}


def test_a_dynamic_importlib_call_is_recorded(tmp_path: Path) -> None:
    """Dropping the dynamic-import branch silently loses a documented collector feature."""
    source = """\
import importlib


def go():
    return importlib.import_module("csv")
"""
    key, modules_info = _analyze(source, tmp_path)
    assert modules_info[key].functions["go"].imports_in_function == {"csv"}


def test_an_aliased_import_records_the_real_module_name(tmp_path: Path) -> None:
    """Recording the local binding instead of the real module name misses the package to install."""
    source = "import numpy as np\n"
    key, modules_info = _analyze(source, tmp_path)
    assert modules_info[key].top_level_imports == {"numpy"}
