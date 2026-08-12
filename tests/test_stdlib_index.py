import json
import subprocess
import sys
from pathlib import Path

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


def test_probe_of_own_interpreter_matches_running_index():
    probed = stdlib_index.for_interpreter(sys.executable)
    assert probed.names == stdlib_index.for_running_interpreter().names
    assert probed.python_version == (sys.version_info.major, sys.version_info.minor)
    assert probed.source == "probe"


def test_missing_interpreter_degrades():
    index = stdlib_index.resolve(Path("/nonexistent/python"))
    assert index.source == "degraded"
    assert "os" in index


def test_probe_timeout_degrades(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="python", timeout=10.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    index = stdlib_index.for_interpreter("/opt/wedged/python")
    assert index.source == "degraded"
    assert "os" in index


def test_probe_garbage_output_degrades(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="Warning: banner\nnot json", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    index = stdlib_index.for_interpreter("/opt/chatty/python")
    assert index.source == "degraded"
    assert "os" in index


def test_probe_nonzero_exit_degrades(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr="AttributeError: module 'sys' has no attribute 'stdlib_module_names'",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    index = stdlib_index.for_interpreter("/opt/python3.9/bin/python")
    assert index.source == "degraded"
    assert "os" in index


def test_resolve_of_own_interpreter_spawns_no_subprocess(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError(
            "resolve() spawned a subprocess for the running interpreter"
        )

    monkeypatch.setattr(subprocess, "run", explode)
    index = stdlib_index.resolve(sys.executable)
    assert index.source == "running"


def test_resolve_of_other_interpreter_uses_that_interpreters_truth(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        payload = json.dumps({"version": [3, 11], "names": ["os", "sys", "asynchat"]})
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=payload, stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    index = stdlib_index.resolve("/opt/python3.11/bin/python")
    assert index.source == "probe"
    assert index.python_version == (3, 11)
    assert "asynchat" in index  # stdlib on 3.11, gone on 3.12 -- target truth wins
    assert len(calls) == 1


def test_resolve_of_none_uses_running_interpreter():
    assert stdlib_index.resolve(None).source == "running"
