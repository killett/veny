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

from veny.analysis.scan_state import ImportScan

from .module_analysis import analyze as _analyze


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


def test_a_dunder_import_is_recorded_where_it_is_called(tmp_path: Path) -> None:
    """Dropping the __import__ branch loses a module the script loads by name at runtime.

    The top-level call must land in top_level_imports and the one inside go()
    in go's imports_in_function, each under its top-level package name.
    """
    source = """\
__import__("json.decoder")


def go():
    return __import__("csv")
"""
    key, modules_info = _analyze(source, tmp_path)
    info = modules_info[key]
    assert info.top_level_imports == {"json"}
    assert info.functions["go"].imports_in_function == {"csv"}


def test_a_module_loaded_from_a_file_location_is_recorded_with_its_path(
    tmp_path: Path,
) -> None:
    """A spec_from_file_location load must register the name and map it to the file.

    Losing either half breaks a later stage: the name is what classification
    sees, and the custom_modules entry is what keeps it from being looked up
    on PyPI.
    """
    (tmp_path / "helper.py").write_text("")
    source = """\
import importlib

spec = importlib.util.spec_from_file_location("helper", "helper.py")
"""
    scan = ImportScan()
    key, modules_info = _analyze(source, tmp_path, scan)
    assert modules_info[key].top_level_imports == {"importlib", "helper"}
    assert scan.custom_modules == {"helper": (tmp_path / "helper.py").resolve()}


def test_a_module_loaded_by_sourcefileloader_is_recorded_with_its_path(
    tmp_path: Path,
) -> None:
    """A SourceFileLoader(...) construction registers the name and maps it to the file."""
    (tmp_path / "helper.py").write_text("")
    source = """\
import importlib

loader = importlib.machinery.SourceFileLoader("helper", "helper.py")
"""
    scan = ImportScan()
    key, modules_info = _analyze(source, tmp_path, scan)
    assert modules_info[key].top_level_imports == {"importlib", "helper"}
    assert scan.custom_modules == {"helper": (tmp_path / "helper.py").resolve()}


def test_a_chained_sourcefileloader_load_module_is_recorded_with_its_path(
    tmp_path: Path,
) -> None:
    """SourceFileLoader(...).load_module() inside a function registers like the constructor.

    The chained form has a branch of its own, matched on the .load_module
    attribute, but the constructor call nested inside it is visited on its own
    too and registers the same name and path (measured: dropping the chained
    branch's registration fails nothing). What this pins is the outcome --
    the module loaded this way inside go() shows up in go's
    imports_in_function with its path mapped -- against a visit_Call that
    stops descending into the callee of a chained call.
    """
    (tmp_path / "helper.py").write_text("")
    source = """\
import importlib


def go():
    return importlib.machinery.SourceFileLoader("helper", "helper.py").load_module()
"""
    scan = ImportScan()
    key, modules_info = _analyze(source, tmp_path, scan)
    assert modules_info[key].functions["go"].imports_in_function == {"helper"}
    assert scan.custom_modules == {"helper": (tmp_path / "helper.py").resolve()}
