import sys

import pytest

import stdlib_index
from stdlib_index import StdlibIndex


@pytest.fixture(autouse=True)
def clear_probe_cache():
    """Keep lru_cache state from leaking between tests (used from Task 2 onward)."""
    yield
    if hasattr(stdlib_index, "for_interpreter") and hasattr(
        stdlib_index.for_interpreter, "cache_clear"
    ):
        stdlib_index.for_interpreter.cache_clear()


def _index(*names):
    return StdlibIndex(names=frozenset(names), python_version=(3, 12), source="running")


def test_dotted_import_resolves_by_first_component():
    assert "xml.etree.ElementTree" in _index("xml")


def test_prefix_match_is_not_enough():
    assert "osquery" not in _index("os")


def test_last_component_is_not_used():
    assert "mypackage.os" not in _index("os")


def test_empty_import_name_is_never_stdlib():
    assert "" not in _index("os", "")


def test_running_interpreter_index_has_real_stdlib_contents():
    index = stdlib_index.for_running_interpreter()
    assert "os" in index
    assert "asyncio" in index
    assert "numpy" not in index
    assert index.python_version == (sys.version_info.major, sys.version_info.minor)
    assert index.source == "running"
