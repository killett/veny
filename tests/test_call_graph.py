"""Characterize the call graph before phase 3b moves it out of cli.py.

Everything here goes through _analyze_module rather than constructing
ImportFunctionCollector directly: the collector fills its own base_classes,
and only _analyze_module copies them onto the ModuleInfo. A test that skips
that step sees an empty base-class map and wrongly concludes inheritance is
broken.
"""

from pathlib import Path

from veny.analysis.call_graph import ModuleInfo, build_call_graph, collect_used_imports
from veny.cli import Options, _analyze_module

INHERITANCE_SOURCE = """\
class Base:
    def helper(self):
        import base64
        return base64


class Child(Base):
    def run(self):
        return self.helper()


def top():
    return Child().run()
"""


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


def test_functions_are_collected_with_their_class_prefix(tmp_path: Path) -> None:
    """Losing the Class.method prefix makes every method unreachable."""
    key, modules_info = _analyze(INHERITANCE_SOURCE, tmp_path)
    assert sorted(modules_info[key].functions) == ["Base.helper", "Child.run", "top"]


def test_a_function_records_the_imports_inside_it(tmp_path: Path) -> None:
    """In-function imports are the entire reason the call graph exists."""
    key, modules_info = _analyze(INHERITANCE_SOURCE, tmp_path)
    helper = modules_info[key].functions["Base.helper"]
    assert helper.imports_in_function == {"base64"}


def test_a_graph_key_is_the_file_path_and_the_function(tmp_path: Path) -> None:
    """The '::' key format is what keeps a dotted module name unambiguous."""
    key, modules_info = _analyze(INHERITANCE_SOURCE, tmp_path)
    graph = build_call_graph(modules_info)
    assert f"{key}::top" in graph


def test_an_inherited_method_call_resolves_to_the_base_class(tmp_path: Path) -> None:
    """self.helper() on a subclass must find Base.helper, not Child.helper."""
    key, modules_info = _analyze(INHERITANCE_SOURCE, tmp_path)
    graph = build_call_graph(modules_info)
    assert graph[f"{key}::Child.run"] == {f"{key}::Base.helper"}


def test_an_import_inside_an_inherited_method_is_reachable(tmp_path: Path) -> None:
    """A missed import here means veny skips an install the script needs."""
    key, modules_info = _analyze(INHERITANCE_SOURCE, tmp_path)
    graph = build_call_graph(modules_info)
    assert collect_used_imports(key, "top", graph, modules_info) == {"base64"}


def test_recursion_does_not_hang_the_traversal(tmp_path: Path) -> None:
    """Without the visited guard, mutual recursion never terminates."""
    source = """\
def ping():
    import base64
    return pong()


def pong():
    import csv
    return ping()
"""
    key, modules_info = _analyze(source, tmp_path)
    graph = build_call_graph(modules_info)
    assert collect_used_imports(key, "ping", graph, modules_info) == {"base64", "csv"}
