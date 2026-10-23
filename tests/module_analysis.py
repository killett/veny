"""Analyze a source string the way the scanner does, for the collector and call-graph tests.

Everything goes through _analyze_module rather than constructing
ImportFunctionCollector directly: the collector fills its own base_classes,
and only _analyze_module copies them onto the ModuleInfo. A test that skips
that step sees an empty base-class map and wrongly concludes inheritance is
broken.
"""

from pathlib import Path

from veny.analysis.call_graph import ModuleInfo
from veny.analysis.scan import _analyze_module
from veny.analysis.scan_state import ImportScan

from .test_state_values import a_settings as _a_settings


def analyze(source: str, tmp_path: Path) -> tuple[str, dict[str, ModuleInfo]]:
    """Write source to a file and analyze it the way find_imports_in_script does.

    Args:
        source: Python source text to analyze.
        tmp_path: pytest's per-test temporary directory.

    Returns:
        The module key _analyze_module assigned, and the modules_info dict.
    """
    module_path = tmp_path / "mod.py"
    module_path.write_text(source)
    settings = _a_settings(cwd=tmp_path, stay_out_list=())
    scan = ImportScan()
    modules_info: dict[str, ModuleInfo] = {}
    result = _analyze_module(settings, scan, module_path, modules_info, False)
    assert result is not None, "_analyze_module refused the fixture"
    return result[0], modules_info
