import logging
import subprocess
import venv
from pathlib import Path

import alias_index
import stdlib_index
import univ_defs as ud
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


class _FakeVenv:
    """Models install-then-import: the importer answers from what is installed.

    This is the real contract: pip installs a *distribution* name (e.g.
    "opencv-python"); the importer is then asked whether an *import* name
    (e.g. "cv2") works. Those are frequently different strings, so a fake
    that can only answer by comparing its argument to a pip name (as a
    stateless `lambda name: name == "right"` would) models something the
    real system never does. This double instead tracks which pip names are
    currently installed and answers ``imports()`` by looking up what they
    provide.
    """

    def __init__(self, provides, install_failures=()):
        self.provides = provides  # pip_name -> the import name it supplies
        self.install_failures = set(install_failures)
        self.attempted = []  # pip names the installer was asked to install, in order
        self.installed = []  # pip names currently installed
        self.uninstalled = []  # pip names removed after a failed import

    def install(self, pip_name):
        self.attempted.append(pip_name)
        if pip_name in self.install_failures:
            return False
        self.installed.append(pip_name)
        return True

    def imports(self, import_name):
        return any(self.provides.get(p) == import_name for p in self.installed)

    def uninstall(self, pip_name):
        self.installed.remove(pip_name)
        self.uninstalled.append(pip_name)


def test_first_working_candidate_is_confirmed():
    index = _RecordingIndex()
    venv = _FakeVenv(provides={"wrong": "something-else", "right": "thing"})
    import_calls = []

    def importer(name):
        import_calls.append(name)
        return venv.imports(name)

    winner = veny.resolve_and_verify(
        _resolution("wrong", "right"),
        index,
        installer=venv.install,
        importer=importer,
        uninstaller=venv.uninstall,
    )
    assert winner.pip_name == "right"
    assert index.confirmed == [("thing", "right")]
    # Pins the real contract: the importer is always asked about the import
    # name ("thing"), never about a candidate's pip name ("wrong"/"right").
    assert import_calls == ["thing", "thing"]


def test_candidate_that_installs_but_does_not_import_is_uninstalled():
    # Leaving it behind pollutes the venv and can shadow the correct package.
    index = _RecordingIndex()
    venv = _FakeVenv(provides={"wrong": "something-else", "right": "thing"})
    veny.resolve_and_verify(
        _resolution("wrong", "right"),
        index,
        installer=venv.install,
        importer=venv.imports,
        uninstaller=venv.uninstall,
    )
    assert venv.uninstalled == ["wrong"]
    assert ("thing", "wrong", "import_failed") in index.rejected


def test_failed_install_is_recorded_but_not_uninstalled():
    # Nothing was installed, and the failure may be transient, so it must not
    # be persisted as a fact about the package.
    index = _RecordingIndex()
    venv = _FakeVenv(
        provides={"right": "thing"},
        install_failures={"broken"},
    )
    veny.resolve_and_verify(
        _resolution("broken", "right"),
        index,
        installer=venv.install,
        importer=venv.imports,
        uninstaller=venv.uninstall,
    )
    assert venv.uninstalled == []
    assert ("thing", "broken", "install_failed") in index.rejected


def test_attempts_are_bounded():
    # One obscure import must not stall a run behind unbounded pip attempts.
    # None of these candidates provide "thing", so every one that installs
    # is rejected and the loop must stop after max_attempts regardless.
    venv = _FakeVenv(provides={})

    result = veny.resolve_and_verify(
        _resolution("a", "b", "c", "d", "e"),
        _RecordingIndex(),
        installer=venv.install,
        importer=venv.imports,
        uninstaller=venv.uninstall,
        max_attempts=3,
    )
    assert result is None
    assert venv.attempted == ["a", "b", "c"]


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


def _index_with(overrides):
    """Build an AliasIndex that resolves only from the given overrides.

    Args:
        overrides: import name -> pip name mapping to seed the index with.

    Returns:
        An offline AliasIndex with an in-memory cache and no seed entries, so
        resolution is fully determined by the test rather than by whatever
        happens to sit in the developer's ~/veny directory.
    """
    return alias_index.AliasIndex(
        overrides=dict(overrides),
        cache=alias_index.AliasCache(
            path=Path("/nonexistent/alias_cache.json"),
            interpreter_tag="3.12",
            entries={},
            rejections={},
        ),
        installed={},
        pypi=None,
        seed={},
    )


def test_options_no_longer_carries_an_alias_table():
    # The whole point of the change: the 1,219-line literal is gone, and with
    # it the reverse map whose {v: k} inversion silently dropped every import
    # name that shared a pip name with another.
    options = veny.Options()
    assert not hasattr(options, "module_aliases")
    assert not hasattr(options, "reversed_module_aliases")


def test_options_alias_index_is_offline_and_unprobed():
    # Options() is built in every test and on every --help run, before the
    # target interpreter is even known. If this were alias_index.build(), each
    # construction would fork a probe subprocess and open PyPI sockets.
    options = veny.Options()
    assert isinstance(options.aliases, alias_index.AliasIndex)
    assert options.aliases.pypi is None
    assert options.aliases.installed == {}


def test_resolved_import_record_carries_both_names():
    # The old code put pip names in one set and import names in another, so
    # every consumer had to guess which kind of string it held.
    record = veny.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    assert record.import_name == "cv2"
    assert record.pip_name == "opencv-python"


def test_split_imports_stores_both_names_on_the_record(monkeypatch):
    # The bug this retires: split_imports used to add the *pip* name to
    # uninstalled_imports, so downstream import checks were handed
    # "widget-lib-pypi" when they needed "widgetlib".
    options = veny.Options()
    options.aliases = _index_with({"widgetlib": "widget-lib-pypi"})
    options.all_imports = {"widgetlib"}
    monkeypatch.setattr(venv, "create", lambda *a, **k: None)
    monkeypatch.setattr(veny, "check_packages_in_venv", lambda *a, **k: False)

    veny.split_imports(options)

    assert options.uninstalled_imports == {
        veny.ResolvedImport(import_name="widgetlib", pip_name="widget-lib-pypi")
    }
    assert options.installed_imports == set()


def test_split_imports_falls_back_to_the_import_name_when_nothing_resolves(monkeypatch):
    # An unresolvable import must still be recorded, not crash on
    # candidates[0] and not vanish from the install list.
    options = veny.Options()
    options.aliases = _index_with({})
    options.all_imports = {"mysterylib"}
    monkeypatch.setattr(venv, "create", lambda *a, **k: None)
    monkeypatch.setattr(veny, "check_packages_in_venv", lambda *a, **k: False)

    veny.split_imports(options)

    assert options.uninstalled_imports == {
        veny.ResolvedImport(import_name="mysterylib", pip_name="mysterylib")
    }


def _captured_venv_check_code(monkeypatch):
    """Capture the source that check_packages_in_venv runs inside the venv.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        A one-element list that will hold the generated source after
        check_packages_in_venv is called.
    """
    captured: list[str] = []

    def fake_run(command, *args, **kwargs):
        captured.append(command[-1])
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="All 1 (out of 1) packages imported successfully.\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


def test_check_packages_in_venv_import_checks_the_import_name(monkeypatch, tmp_path):
    # It runs `import_module(...)` inside a venv, so it needs "cv2". Handing
    # it "opencv-python" -- which is what the old reversed_module_aliases
    # inversion returned for anything it did not know -- makes the import
    # always fail and reports every package as uninstalled.
    options = veny.Options()
    captured = _captured_venv_check_code(monkeypatch)

    veny.check_packages_in_venv(
        options,
        record=veny.ResolvedImport(import_name="cv2", pip_name="opencv-python"),
        venv_dir=tmp_path,
    )

    assert "'cv2'" in captured[0]
    assert "opencv-python" not in captured[0]


def test_check_packages_in_venv_without_a_record_checks_every_import_name(
    monkeypatch, tmp_path
):
    # The bulk branch had the same inversion bug, and it is the branch the
    # cached-venv validation path uses. With a degraded probe (no venv
    # metadata available) it must fall back to today's behaviour: the
    # import_name from the record, never the pip_name.
    options = veny.Options()
    options.uninstalled_imports = {
        veny.ResolvedImport(import_name="cv2", pip_name="opencv-python"),
        veny.ResolvedImport(import_name="yaml", pip_name="PyYAML"),
    }
    monkeypatch.setattr(veny, "use_pip_list", lambda opts: None)
    monkeypatch.setattr(
        alias_index, "probe_interpreter", lambda python, timeout=30.0: ("3.12", {})
    )
    captured = _captured_venv_check_code(monkeypatch)

    veny.check_packages_in_venv(options, venv_dir=tmp_path)

    assert "'cv2'" in captured[0]
    assert "'yaml'" in captured[0]
    assert "opencv-python" not in captured[0]
    assert "PyYAML" not in captured[0]


def test_check_packages_in_venv_bulk_branch_resolves_requirement_via_venv_metadata(
    monkeypatch, tmp_path
):
    # requirement_records() sets import_name == pip_name for --reqs entries
    # (e.g. "opencv-python" for both), because a requirements line is a pip
    # name and nothing maps it backwards. Feeding "opencv-python" straight to
    # import_module() always fails even when cv2 really is installed. The
    # venv's own metadata should be consulted to recover "cv2".
    options = veny.Options()
    options.uninstalled_imports = {
        veny.ResolvedImport(import_name="opencv-python", pip_name="opencv-python"),
    }
    monkeypatch.setattr(veny, "use_pip_list", lambda opts: None)
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"cv2": ["opencv-python"]}),
    )
    captured = _captured_venv_check_code(monkeypatch)

    veny.check_packages_in_venv(options, venv_dir=tmp_path)

    assert "'cv2'" in captured[0]
    assert "'opencv-python'" not in captured[0]


def test_check_packages_in_venv_bulk_branch_matches_pep503_spelling(
    monkeypatch, tmp_path
):
    # The venv metadata may report a distribution name spelled differently
    # (underscores vs hyphens) than the record's pip_name. The lookup must
    # normalize both sides, per PEP 503, or a genuinely installed package
    # gets checked under the wrong name and rejected.
    options = veny.Options()
    options.uninstalled_imports = {
        veny.ResolvedImport(import_name="opencv_python", pip_name="opencv_python"),
    }
    monkeypatch.setattr(veny, "use_pip_list", lambda opts: None)
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        # Metadata reports the hyphenated spelling; the record uses underscores.
        lambda python, timeout=30.0: ("3.12", {"cv2": ["opencv-python"]}),
    )
    captured = _captured_venv_check_code(monkeypatch)

    veny.check_packages_in_venv(options, venv_dir=tmp_path)

    assert "'cv2'" in captured[0]


def test_check_packages_in_venv_bulk_branch_falls_back_when_distribution_unknown(
    monkeypatch, tmp_path
):
    # A record whose pip_name is not in the venv's metadata (e.g. it was
    # never actually installed, or metadata is incomplete) must still be
    # checked -- under its import_name, exactly as before -- never skipped.
    options = veny.Options()
    options.uninstalled_imports = {
        veny.ResolvedImport(import_name="numpy", pip_name="numpy"),
    }
    monkeypatch.setattr(veny, "use_pip_list", lambda opts: None)
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"some_other_thing": ["unrelated-pkg"]}),
    )
    captured = _captured_venv_check_code(monkeypatch)

    veny.check_packages_in_venv(options, venv_dir=tmp_path)

    assert "'numpy'" in captured[0]


def test_check_packages_in_venv_probes_the_venv_once_per_call(monkeypatch, tmp_path):
    # Each probe is a subprocess; probing per record instead of per call would
    # multiply that cost by the number of uninstalled imports.
    options = veny.Options()
    options.uninstalled_imports = {
        veny.ResolvedImport(import_name="cv2", pip_name="opencv-python"),
        veny.ResolvedImport(import_name="yaml", pip_name="PyYAML"),
        veny.ResolvedImport(import_name="numpy", pip_name="numpy"),
    }
    monkeypatch.setattr(veny, "use_pip_list", lambda opts: None)
    probe_calls = []

    def fake_probe(python, timeout=30.0):
        probe_calls.append(python)
        return "3.12", {}

    monkeypatch.setattr(alias_index, "probe_interpreter", fake_probe)
    _captured_venv_check_code(monkeypatch)

    veny.check_packages_in_venv(options, venv_dir=tmp_path)

    assert len(probe_calls) == 1


def _run_check_against_fake_venv(monkeypatch, importable: set[str]):
    """Simulate a real venv by executing the generated script for real.

    The generated script's own pass/fail logic (including the "any
    alternative may import" branching) runs unmodified; only
    ``importlib.import_module`` is stubbed, succeeding exactly for names in
    ``importable``. This exercises the actual boolean outcome, not just the
    names embedded in the source.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
        importable: Names that "import" successfully in the fake venv.
    """
    import contextlib
    import importlib
    import io

    def fake_import_module(name: str) -> None:
        if name not in importable:
            raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    def fake_run(command, *args, **kwargs):
        source = command[-1]
        buf = io.StringIO()
        exit_code = 0
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(source, "<fake-venv-check>", "exec"), {})
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        return subprocess.CompletedProcess(
            command, exit_code, stdout=buf.getvalue(), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_check_packages_in_venv_passes_when_any_top_level_name_imports(
    monkeypatch, tmp_path
):
    # A distribution declaring several top-level names (per venv metadata)
    # must pass the check if any one of them imports -- requiring all of
    # them would fail correct installs that only use part of a distribution.
    options = veny.Options()
    options.uninstalled_imports = {
        veny.ResolvedImport(import_name="opencv-python", pip_name="opencv-python"),
    }
    monkeypatch.setattr(veny, "use_pip_list", lambda opts: None)
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: (
            "3.12",
            {"cv2": ["opencv-python"], "cv2_other": ["opencv-python"]},
        ),
    )
    # Only one of the two top-level names actually imports.
    _run_check_against_fake_venv(monkeypatch, importable={"cv2_other"})

    assert veny.check_packages_in_venv(options, venv_dir=tmp_path) is True


def test_check_packages_in_venv_bulk_branch_checks_the_records_own_import_name(
    monkeypatch, tmp_path
):
    # When the record's import_name is one the distribution declares, it came
    # from the user's source and is the name that must actually import.
    # Widening the check to the distribution's whole top-level list makes it
    # fail-open: setuptools declares ['_distutils_hack', 'pkg_resources',
    # 'setuptools'] and, sorted, '_distutils_hack' is tried first and
    # short-circuits, so the name the user wrote is never tested. This is the
    # final gate -- it drops the venv's 'failed-' prefix and decides whether a
    # cached venv is reusable -- so a false pass hands over a venv that cannot
    # run the script.
    options = veny.Options()
    options.uninstalled_imports = {
        veny.ResolvedImport(import_name="setuptools", pip_name="setuptools"),
    }
    monkeypatch.setattr(veny, "use_pip_list", lambda opts: None)
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: (
            "3.12",
            {
                "_distutils_hack": ["setuptools"],
                "pkg_resources": ["setuptools"],
                "setuptools": ["setuptools"],
            },
        ),
    )
    # The broken half-install the user would be handed: the sibling top-level
    # names import, the one that was asked for does not.
    _run_check_against_fake_venv(
        monkeypatch, importable={"_distutils_hack", "pkg_resources"}
    )

    assert veny.check_packages_in_venv(options, venv_dir=tmp_path) is False


def test_check_packages_in_venv_still_fails_a_genuinely_missing_package(
    monkeypatch, tmp_path
):
    # This must not become a way for everything to pass: when the package
    # really is missing -- whether or not metadata knows about it -- the
    # check must still fail.
    options = veny.Options()
    options.uninstalled_imports = {
        veny.ResolvedImport(import_name="cv2", pip_name="opencv-python"),
    }
    monkeypatch.setattr(veny, "use_pip_list", lambda opts: None)
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"cv2": ["opencv-python"]}),
    )
    _run_check_against_fake_venv(monkeypatch, importable=set())

    assert veny.check_packages_in_venv(options, venv_dir=tmp_path) is False


def test_alias_index_is_serialized_as_structured_data():
    # Serializing via str()/repr() turns lookups into substring matching, which
    # silently returns wrong answers instead of raising.
    index = alias_index.AliasIndex(
        overrides={"cv2": "my-opencv"},
        cache=alias_index.AliasCache(
            path=Path("/tmp/none.json"),
            interpreter_tag="3.12",
            entries={},
            rejections={},
        ),
        installed={},
        pypi=None,
    )
    payload = ud.to_jsonable(index)
    assert isinstance(payload, dict)
    assert payload["overrides"] == {"cv2": "my-opencv"}
    assert payload["interpreter_tag"] == "3.12"
    assert payload["cache_path"] == "/tmp/none.json"
    assert payload["offline"] is True


def test_resolved_import_round_trips_through_json():
    # uninstalled_imports is written to the last-used options file and read
    # back by check_venv_dir. Without a handler each record stringifies to
    # "ResolvedImport(import_name='cv2', ...)", so the issubset() check against
    # the cached set can never match and veny rebuilds a venv every run.
    record = veny.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    restored = ud.from_jsonable(ud.to_jsonable({record}))
    assert restored == {record}
