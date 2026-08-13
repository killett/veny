import logging

import stdlib_index
import veny
from alias_index import Candidate, Resolution, Source


def test_python2_name_is_classified_bad():
    bad = veny._compute_bad_imports(
        {"httplib", "numpy"}, set(), stdlib_index.PYTHON2_ONLY
    )
    assert bad == {"httplib"}


def test_leading_underscore_name_is_classified_bad():
    bad = veny._compute_bad_imports({"_private_thing", "numpy"}, set(), frozenset())
    assert bad == {"_private_thing"}


def test_ordinary_import_is_not_classified_bad():
    bad = veny._compute_bad_imports(
        {"numpy", "xarray"}, {"DQN"}, stdlib_index.PYTHON2_ONLY
    )
    assert bad == set()


def test_seaborn_tkinter_and_msvcrt_are_no_longer_blocked():
    blocked = veny.Options().known_bad_imports
    assert blocked == {
        "snakeClass",
        "GPUampcor",
        "pathfinding_salvo_rework",
        "DQN",
        "bayesOpt",
        "non_existent_module",
    }


def test_split_imports_wires_python2_table_end_to_end():
    options = veny.Options()
    options.all_imports = {"httplib", "_private_thing"}
    veny.split_imports(options)
    assert options.bad_imports == {"httplib", "_private_thing"}
    assert options.all_imports == set()


def test_tkinter_produces_one_system_package_warning(caplog):
    options = veny.Options()
    options.seen_stdlib_imports = {"tkinter", "os"}
    with caplog.at_level(logging.WARNING):
        veny.warn_about_system_packages(options)
    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 1
    assert "tkinter" in messages[0]
    assert "python3-tk" in messages[0]


def test_no_warning_when_no_hint_module_was_seen(caplog):
    options = veny.Options()
    options.seen_stdlib_imports = {"os", "sys"}
    with caplog.at_level(logging.WARNING):
        veny.warn_about_system_packages(options)
    assert caplog.records == []


def test_process_import_records_a_stdlib_skip(tmp_path):
    options = veny.Options()
    script = tmp_path / "user_script.py"
    script.write_text("import tkinter\n")
    assert veny.process_import(options, "tkinter", script) is False
    assert "tkinter" in options.seen_stdlib_imports


def test_enqueue_top_level_imports_records_stdlib_and_skips_enqueue(tmp_path):
    from collections import deque

    options = veny.Options()
    module_path = tmp_path / "user_script.py"
    module_path.write_text("import tkinter\n")
    processed_paths: set = set()
    modules_to_process: deque = deque()

    veny._enqueue_top_level_imports(
        options, module_path, {"tkinter"}, processed_paths, modules_to_process
    )

    assert "tkinter" in options.seen_stdlib_imports
    assert len(modules_to_process) == 0


class _RecordingIndex:
    def __init__(self):
        self.confirmed = []
        self.rejected = []

    def confirm(self, import_name, pip_name):
        self.confirmed.append((import_name, pip_name))

    def reject(self, import_name, pip_name, kind):
        self.rejected.append((import_name, pip_name, kind))


def _resolution(*pip_names):
    return Resolution(
        import_name="thing",
        candidates=tuple(
            Candidate(pip_name=name, source=Source.PYPI_CONFIRMED, evidence="test")
            for name in pip_names
        ),
    )


def test_first_working_candidate_is_confirmed():
    index = _RecordingIndex()
    winner = veny.resolve_and_verify(
        _resolution("wrong", "right"),
        index,
        installer=lambda name: True,
        importer=lambda name: name == "right",
        uninstaller=lambda name: None,
    )
    assert winner.pip_name == "right"
    assert index.confirmed == [("thing", "right")]


def test_candidate_that_installs_but_does_not_import_is_uninstalled():
    # Leaving it behind pollutes the venv and can shadow the correct package.
    removed = []
    index = _RecordingIndex()
    veny.resolve_and_verify(
        _resolution("wrong", "right"),
        index,
        installer=lambda name: True,
        importer=lambda name: name == "right",
        uninstaller=removed.append,
    )
    assert removed == ["wrong"]
    assert ("thing", "wrong", "import_failed") in index.rejected


def test_failed_install_is_recorded_but_not_uninstalled():
    # Nothing was installed, and the failure may be transient, so it must not
    # be persisted as a fact about the package.
    removed = []
    index = _RecordingIndex()
    veny.resolve_and_verify(
        _resolution("broken", "right"),
        index,
        installer=lambda name: name != "broken",
        importer=lambda name: True,
        uninstaller=removed.append,
    )
    assert removed == []
    assert ("thing", "broken", "install_failed") in index.rejected


def test_attempts_are_bounded():
    # One obscure import must not stall a run behind unbounded pip attempts.
    tried = []

    def installer(name):
        tried.append(name)
        return True

    result = veny.resolve_and_verify(
        _resolution("a", "b", "c", "d", "e"),
        _RecordingIndex(),
        installer=installer,
        importer=lambda name: False,
        uninstaller=lambda name: None,
        max_attempts=3,
    )
    assert result is None
    assert tried == ["a", "b", "c"]


def test_empty_resolution_never_touches_the_installer():
    tried = []
    result = veny.resolve_and_verify(
        Resolution("thing", ()),
        _RecordingIndex(),
        installer=tried.append,
        importer=lambda name: True,
        uninstaller=lambda name: None,
    )
    assert result is None
    assert tried == []
