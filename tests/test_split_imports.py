import logging
import subprocess
import sys
from pathlib import Path

import emmykit as ek

from veny import alias_index, environment, venv_cache
from veny import cli as veny
from veny.alias_index import Candidate, Resolution, Source
from veny.analysis.imports import process_import
from veny.analysis.scan import _enqueue_top_level_imports
from veny.analysis.scan_state import ImportScan


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
    # process_import now takes an ImportScan and an injected is_stdlib
    # predicate instead of Options. scan holds the same objects options
    # does (not copies), so asserting on options.seen_stdlib_imports below
    # still observes what process_import wrote.
    scan = ImportScan(
        all_imports=options.all_imports,
        custom_modules=options.custom_modules,
        loaded_custom_modules=options.loaded_custom_modules,
        samedir_files=options.samedir_files,
        subfolders=options.subfolders,
        sys_path_hints=options.sys_path_hints,
        seen_stdlib_imports=options.seen_stdlib_imports,
    )
    assert (
        process_import(scan, "tkinter", script, is_stdlib=options.stdlib.__contains__)
        is False
    )
    assert "tkinter" in options.seen_stdlib_imports


def test_enqueue_top_level_imports_records_stdlib_and_skips_enqueue(tmp_path):
    from collections import deque

    options = veny.Options()
    module_path = tmp_path / "user_script.py"
    module_path.write_text("import tkinter\n")
    processed_paths: set = set()
    modules_to_process: deque = deque()
    scan = ImportScan(
        all_imports=options.all_imports,
        custom_modules=options.custom_modules,
        loaded_custom_modules=options.loaded_custom_modules,
        samedir_files=options.samedir_files,
        subfolders=options.subfolders,
        sys_path_hints=options.sys_path_hints,
        seen_stdlib_imports=options.seen_stdlib_imports,
    )

    _enqueue_top_level_imports(
        scan,
        module_path,
        {"tkinter"},
        processed_paths,
        modules_to_process,
        is_stdlib=options.stdlib.__contains__,
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


def test_a_candidate_credited_to_another_distribution_is_not_confirmed():
    # The last unattributed confirm() in the branch. A repair candidate can drag
    # in a transitive dependency that satisfies the import -- sklearn repaired to
    # scikit-learn-extra, satisfied by its own scikit-learn dependency -- and the
    # cache would then claim scikit-learn-extra provides sklearn, outranking
    # every tier except OVERRIDE on every later run.
    index = _RecordingIndex()
    venv = _FakeVenv(provides={"scikit-learn-extra": "sklearn"})

    def importer(name):
        # It imports -- but the venv credits a different distribution for it.
        return veny.ImportOutcome(
            imported=True,
            rejection_kind="",
            detail="",
            providers=frozenset({"scikit-learn"}),
        )

    winner = veny.resolve_and_verify(
        Resolution(
            "sklearn",
            (
                Candidate(
                    pip_name="scikit-learn-extra",
                    source=Source.PYPI_CONFIRMED,
                    evidence="test",
                ),
            ),
        ),
        index,
        installer=venv.install,
        importer=importer,
        uninstaller=venv.uninstall,
    )

    # The import works now, so the repair did succeed and the venv is usable:
    # the candidate must still be returned, and must not be uninstalled.
    assert winner.pip_name == "scikit-learn-extra"
    assert venv.uninstalled == []
    # But the attribution was never established, so nothing may be written down.
    assert index.confirmed == []


def test_a_candidate_credited_with_the_import_is_confirmed():
    # The guard against over-tightening: attribution must not stop the ordinary
    # repair from being cached, or the CACHE tier is dead on this path.
    # The spelling is deliberately not identical -- PyPI treats runs of -, _ and
    # . as equivalent, and the venv's metadata may report either.
    index = _RecordingIndex()
    venv = _FakeVenv(provides={"skill-metrics": "skill_metrics"})

    def importer(name):
        return veny.ImportOutcome(
            imported=True,
            rejection_kind="",
            detail="",
            providers=frozenset({"skill_metrics"}),
        )

    veny.resolve_and_verify(
        Resolution(
            "skill_metrics",
            (
                Candidate(
                    pip_name="skill-metrics",
                    source=Source.PYPI_CONFIRMED,
                    evidence="test",
                ),
            ),
        ),
        index,
        installer=venv.install,
        importer=importer,
        uninstaller=venv.uninstall,
    )

    assert index.confirmed == [("skill_metrics", "skill-metrics")]


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


def test_the_offline_argument_keeps_the_index_off_the_network(monkeypatch, tmp_path):
    # build() has taken an offline flag since it was written and nothing ever
    # passed True, so there was no way to stop veny opening PyPI sockets --
    # on a plane, behind a blocked index, or in a sandbox without egress.
    options = veny.Options()
    options.my_dir = tmp_path
    options.python_command = None
    monkeypatch.setattr(sys, "argv", ["veny.py", "--offline", "script.py"])

    veny.parse_arguments(options)

    assert options.args.offline is True
    assert veny.build_alias_index(options).pypi is None


def test_the_index_reaches_pypi_by_default(monkeypatch, tmp_path):
    # The flag must be opt-in: defaulting to offline would silently drop the
    # only tier that can resolve a name veny has never seen before.
    options = veny.Options()
    options.my_dir = tmp_path
    options.python_command = None
    monkeypatch.setattr(sys, "argv", ["veny.py", "script.py"])

    veny.parse_arguments(options)

    assert options.args.offline is False
    assert veny.build_alias_index(options).pypi is not None


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
    probe_calls = []

    def fake_probe(python, timeout=30.0):
        probe_calls.append(python)
        return "3.12", {}

    monkeypatch.setattr(alias_index, "probe_interpreter", fake_probe)
    _captured_venv_check_code(monkeypatch)

    veny.check_packages_in_venv(options, venv_dir=tmp_path)

    assert len(probe_calls) == 1


def _run_check_against_fake_venv(monkeypatch, importable: set[str], errors=None):
    """Simulate a real venv by executing the generated script for real.

    The generated script's own pass/fail logic (including the "any
    alternative may import" branching) runs unmodified; only
    ``importlib.import_module`` is stubbed, succeeding exactly for names in
    ``importable``. This exercises the actual boolean outcome, not just the
    names embedded in the source.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
        importable: Names that "import" successfully in the fake venv.
        errors: Optional import name -> ImportError message, for the cases where
            *why* an import failed is what is under test.
    """
    import contextlib
    import importlib
    import io

    def fake_import_module(name: str) -> None:
        if name not in importable:
            raise ImportError((errors or {}).get(name, name))

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


def test_check_packages_in_venv_bulk_branch_fails_an_unprovided_source_import(
    monkeypatch, tmp_path
):
    # The other half of the fail-open hole, and the exact case the repair pass
    # exists for: the record's pip_name resolved *wrongly*, so it installed a
    # distribution that declares some other top-level name. Judging the record
    # by that distribution's metadata passes it -- the wrong package imports
    # fine, it just is not what the user wrote. The name in the user's source
    # is the one that has to import.
    options = veny.Options()
    options.all_imports = {"thing"}
    options.uninstalled_imports = {
        veny.ResolvedImport(import_name="thing", pip_name="wrong-pkg"),
    }
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"something_else": ["wrong-pkg"]}),
    )
    _run_check_against_fake_venv(monkeypatch, importable={"something_else"})

    assert veny.check_packages_in_venv(options, venv_dir=tmp_path) is False


def test_check_venv_dir_rejects_a_manifest_match_whose_import_does_not_actually_import(
    monkeypatch, tmp_path
):
    # The manifest can say a package is there while the venv is actually
    # broken (a half-finished install, a corrupted site-packages). check_venv_dir
    # must not stop at the manifest match -- it has to run the same import-level
    # confirmation check_packages_in_venv performs, and reject the venv when
    # that fails, even though venv_cache.satisfies() alone would have accepted it.
    cached_dir = tmp_path / "cached-venv"
    cached_dir.mkdir()
    record = veny.ResolvedImport(import_name="thing", pip_name="thing-pkg")
    options = veny.Options()
    options.all_imports = {"thing"}
    options.uninstalled_imports = {record}
    venv_cache.write_manifest(
        cached_dir,
        venv_cache.Manifest(
            schema_version=venv_cache.SCHEMA_VERSION,
            created="20260814-091500",
            veny_version="0.2.2",
            interpreter_tag=veny.interpreter_tag(options),
            interpreter_path="/usr/bin/python3",
            packages=(venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None),),
        ),
    )
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    # The manifest matches (same pip name, same interpreter tag) but nothing
    # actually imports in this venv.
    _run_check_against_fake_venv(monkeypatch, importable=set())

    assert veny.check_venv_dir(options, cached_dir) is False


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
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"cv2": ["opencv-python"]}),
    )
    _run_check_against_fake_venv(monkeypatch, importable=set())

    assert veny.check_packages_in_venv(options, venv_dir=tmp_path) is False


class _FakeInstalledVenv:
    """Models a venv well enough to install into, import from, and probe.

    The contract under test is the same one _FakeVenv models for
    resolve_and_verify -- pip installs a *distribution* name, the importer is
    asked about an *import* name -- but the repair path also reads the venv's
    installed-distribution metadata to decide whether a failed candidate is
    still sitting in the venv. So this double additionally answers the probe.
    """

    def __init__(self, provides, installed=(), install_failures=(), unusable=()):
        self.provides = dict(provides)  # pip name -> the import name it supplies
        self.installed = list(installed)  # pip names currently installed
        self.install_failures = set(install_failures)
        # Pip names that install and declare their import name, but whose import
        # fails here because the machine lacks a shared library.
        self.unusable = set(unusable)
        self.attempted = []  # pip names the installer was asked to install
        self.uninstalled = []  # pip names removed
        self.import_checks = []  # names the per-record import check was given

    def install(self, venv_python, pip_name):
        self.attempted.append(pip_name)
        if pip_name in self.install_failures:
            return False
        self.installed.append(pip_name)
        return True

    def uninstall(self, venv_python, pip_name):
        self.uninstalled.append(pip_name)
        if pip_name in self.installed:
            self.installed.remove(pip_name)

    def imports(self, import_name):
        return any(
            self.provides.get(p) == import_name and p not in self.unusable
            for p in self.installed
        )

    def providers_of(self, import_name):
        """The distributions this venv credits with providing an import name."""
        return frozenset(
            alias_index.normalize_pip_name(p)
            for p in self.installed
            if self.provides.get(p) == import_name and p not in self.unusable
        )

    def outcome(self, options, import_name, venv_dir=None):
        """Stand in for import_outcome_in_venv."""
        self.import_checks.append(import_name)
        if self.imports(import_name):
            return veny.ImportOutcome(
                imported=True,
                rejection_kind="",
                detail="",
                providers=self.providers_of(import_name),
            )
        if any(
            self.provides.get(p) == import_name and p in self.unusable
            for p in self.installed
        ):
            return veny.ImportOutcome(
                imported=False,
                rejection_kind="import_unavailable",
                detail="libGL.so.1: cannot open shared object file",
            )
        return veny.ImportOutcome(
            imported=False,
            rejection_kind="import_failed",
            detail=f"No module named {import_name!r}",
        )

    def probe(self, python, timeout=30.0):
        packages: dict[str, list[str]] = {}
        for pip_name in self.installed:
            packages.setdefault(self.provides.get(pip_name, pip_name), []).append(
                pip_name
            )
        return "3.12", packages

    def check(self, options, record=None, venv_dir=None):
        """Stand in for check_packages_in_venv, per record and in bulk."""
        if record is not None:
            self.import_checks.append(record.import_name)
            return self.imports(record.import_name)
        return all(
            self.imports(entry.import_name)
            or (
                # Mirrors the real bulk branch: a record carrying a pip
                # spelling rather than a source import name is judged by what
                # its distribution declares instead.
                entry.import_name not in options.all_imports
                and entry.pip_name in self.installed
            )
            for entry in options.uninstalled_imports
        )


def _options_with_venv(tmp_path, index, records):
    """Build an Options far enough along to run the post-install verification."""
    options = veny.Options()
    options.my_dir = tmp_path
    options.aliases = index
    options.all_imports = {record.import_name for record in records}
    options.uninstalled_imports = set(records)
    options.set_venv_dir(tmp_path / "venv")
    return options


def _live_index(tmp_path, **kwargs):
    """An AliasIndex with a real on-disk cache, so confirm()/reject() are visible."""
    fields = {
        "overrides": {},
        "cache": alias_index.AliasCache.load(
            tmp_path / "alias_cache.json", interpreter_tag="3.12"
        ),
        "installed": {},
        "pypi": None,
        "seed": {},
    }
    fields.update(kwargs)
    return alias_index.AliasIndex(**fields)


def test_setup_virtualenv_verifies_every_import_before_reporting_success(
    monkeypatch, tmp_path
):
    # The seam this task exists to close: resolve_and_verify was built and
    # tested but never called from production, so the cache was never written
    # and two of the five evidence tiers were unreachable. Nothing inside
    # either function could catch that -- only a test of the join can.
    options = veny.Options()
    options.my_dir = tmp_path
    options.uninstalled_imports = {
        veny.ResolvedImport(import_name="thing", pip_name="thing-pkg")
    }
    calls = []
    monkeypatch.setattr(
        environment, "write_requirements_file_with_extras", lambda *args: None
    )
    monkeypatch.setattr(subprocess, "check_call", lambda *a, **k: 0)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 0),
    )

    def fake_verify(opts):
        calls.append("verify")

    def fake_check(opts, record=None, venv_dir=None):
        calls.append("check")
        return True

    monkeypatch.setattr(veny, "verify_and_repair_imports", fake_verify)
    monkeypatch.setattr(veny, "check_packages_in_venv", fake_check)
    # record_venv_state probes the venv's real interpreter for installed
    # versions, which this test's fake subprocess.run cannot answer -- it is
    # unrelated to the ordering this test checks, so it is stubbed out too.
    monkeypatch.setattr(veny, "record_venv_state", lambda opts: None)

    assert veny.setup_virtualenv(options) is True
    # Verification has to happen before the gate that drops the "failed-"
    # prefix, or its repairs cannot affect the answer.
    assert calls == ["verify", "check"]


def test_a_verified_import_is_written_to_the_alias_cache(monkeypatch, tmp_path):
    # Nothing called confirm(), so ~/veny/module_aliases_cache.json was never
    # written, Source.CACHE never fired, and every run re-resolved every import
    # over the network forever.
    index = _live_index(tmp_path)
    record = veny.ResolvedImport(import_name="yaml", pip_name="PyYAML")
    options = _options_with_venv(tmp_path, index, [record])
    fake = _FakeInstalledVenv(provides={"PyYAML": "yaml"}, installed=["PyYAML"])
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)

    veny.verify_and_repair_imports(options)

    assert index.cache.get("yaml") == "PyYAML"
    reloaded = alias_index.AliasCache.load(
        tmp_path / "alias_cache.json", interpreter_tag="3.12"
    )
    assert reloaded.get("yaml") == "PyYAML"


def test_an_import_provided_by_another_distribution_is_not_confirmed(
    monkeypatch, tmp_path
):
    # A passing import check proves the import *works*, not that the record's
    # pip_name is what provided it. Here "thing" is really supplied by
    # other-pkg -- a dependency, or another requested distribution -- while the
    # record's own wrong-pkg resolved wrongly but installably. Confirming that
    # writes a false CACHE entry, which outranks SEED, INSTALLED and
    # PYPI_CONFIRMED on every later run and is durable.
    index = _live_index(tmp_path)
    record = veny.ResolvedImport(import_name="thing", pip_name="wrong-pkg")
    options = _options_with_venv(tmp_path, index, [record])
    fake = _FakeInstalledVenv(
        provides={"wrong-pkg": "something-else", "other-pkg": "thing"},
        installed=["wrong-pkg", "other-pkg"],
    )
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(veny, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    veny.verify_and_repair_imports(options)

    assert index.cache.entries == {}


def test_an_import_attributable_to_its_own_distribution_is_confirmed(
    monkeypatch, tmp_path
):
    # The other side of the same rule: requiring attribution must not stop the
    # ordinary case from being cached, or the CACHE tier is dead again.
    index = _live_index(tmp_path)
    record = veny.ResolvedImport(import_name="thing", pip_name="thing-pkg")
    options = _options_with_venv(tmp_path, index, [record])
    fake = _FakeInstalledVenv(provides={"thing-pkg": "thing"}, installed=["thing-pkg"])
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)

    veny.verify_and_repair_imports(options)

    assert index.cache.get("thing") == "thing-pkg"


def test_an_import_the_batch_install_did_not_provide_is_repaired(monkeypatch, tmp_path):
    # The batch install installs candidates[0] and nothing else, so a wrong
    # first candidate used to be final: ranking past position 0 had no
    # production effect at all.
    index = _live_index(tmp_path, seed={"thing": "right-pkg"})
    record = veny.ResolvedImport(import_name="thing", pip_name="wrong-pkg")
    options = _options_with_venv(tmp_path, index, [record])
    # wrong-pkg installed fine during the batch; it just does not provide "thing".
    fake = _FakeInstalledVenv(
        provides={"wrong-pkg": "something-else", "right-pkg": "thing"},
        installed=["wrong-pkg"],
    )
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(veny, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    veny.verify_and_repair_imports(options)

    assert fake.attempted == ["right-pkg"]
    # The package that installed without providing the import must not be left
    # behind: it pollutes the venv and can shadow the correct package.
    assert fake.uninstalled == ["wrong-pkg"]
    assert index.cache.get("thing") == "right-pkg"
    assert "wrong-pkg" in index.cache.rejected_names("thing")
    # The record now names the package that actually provided the import.
    assert options.uninstalled_imports == {
        veny.ResolvedImport(import_name="thing", pip_name="right-pkg")
    }


def test_the_repair_path_import_checks_the_import_name_never_the_pip_name(
    monkeypatch, tmp_path
):
    # Exactly the defect found and fixed in Task 6. import_module("right-pkg")
    # always fails, so checking the pip name would reject every correct
    # candidate and uninstall it again.
    index = _live_index(tmp_path, seed={"thing": "right-pkg"})
    record = veny.ResolvedImport(import_name="thing", pip_name="wrong-pkg")
    options = _options_with_venv(tmp_path, index, [record])
    fake = _FakeInstalledVenv(
        provides={"wrong-pkg": "something-else", "right-pkg": "thing"},
        installed=["wrong-pkg"],
    )
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(veny, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    veny.verify_and_repair_imports(options)

    assert fake.import_checks
    assert set(fake.import_checks) == {"thing"}


def test_a_record_carrying_a_pip_spelling_is_never_repaired(monkeypatch, tmp_path):
    # requirement_records() (--reqs) and resolve_records() (dependencies) both
    # produce records whose import_name is a pip name, e.g.
    # ("opencv-python", "opencv-python"). import_module("opencv-python") always
    # fails, so treating that as a failed import would uninstall a package that
    # installed perfectly well and is exactly what the user asked for.
    index = _live_index(tmp_path)
    record = veny.ResolvedImport(import_name="opencv-python", pip_name="opencv-python")
    options = _options_with_venv(tmp_path, index, [record])
    options.all_imports = set()  # nothing in the user's source
    fake = _FakeInstalledVenv(
        provides={"opencv-python": "cv2"}, installed=["opencv-python"]
    )
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(veny, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    veny.verify_and_repair_imports(options)

    assert fake.uninstalled == []
    assert fake.attempted == []
    assert index.cache.entries == {}


def test_a_repair_that_cannot_succeed_leaves_the_run_going(monkeypatch, tmp_path):
    # veny's job is to get as far as it can and report honestly. An import
    # nothing can satisfy must not raise out of the verification pass.
    index = _live_index(tmp_path)
    record = veny.ResolvedImport(import_name="mystery", pip_name="mystery")
    options = _options_with_venv(tmp_path, index, [record])
    fake = _FakeInstalledVenv(provides={}, install_failures={"mystery"})
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(veny, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    veny.verify_and_repair_imports(options)

    assert options.uninstalled_imports == {record}
    # A failed install may be transient, so it must not be persisted as a fact
    # about the package.
    assert index.cache.rejected_names("mystery") == frozenset()


def test_a_missing_shared_library_is_classified_as_machine_scoped(
    monkeypatch, tmp_path
):
    # The discriminating text arrives on the ImportError and used to be thrown
    # away one line later by "except ImportError: continue".
    options = veny.Options()
    options.my_dir = tmp_path
    options.set_venv_dir(tmp_path / "venv")
    _run_check_against_fake_venv(
        monkeypatch,
        importable=set(),
        errors={
            "cv2": "libGL.so.1: cannot open shared object file: No such file or directory"
        },
    )

    outcome = veny.import_outcome_in_venv(options, "cv2")

    assert outcome.imported is False
    assert outcome.rejection_kind == "import_unavailable"
    assert "libGL.so.1" in outcome.detail


def test_an_absent_module_is_still_classified_as_a_package_fault(monkeypatch, tmp_path):
    # The distinction must stay sharp in both directions: a package that
    # installs and genuinely does not contain the module is a durable fact, and
    # must keep being remembered so it is not re-attempted every run.
    options = veny.Options()
    options.my_dir = tmp_path
    options.set_venv_dir(tmp_path / "venv")
    _run_check_against_fake_venv(
        monkeypatch, importable=set(), errors={"thing": "No module named 'thing'"}
    )

    outcome = veny.import_outcome_in_venv(options, "thing")

    assert outcome.imported is False
    assert outcome.rejection_kind == "import_failed"


def test_a_working_import_reports_no_rejection(monkeypatch, tmp_path):
    options = veny.Options()
    options.my_dir = tmp_path
    options.set_venv_dir(tmp_path / "venv")
    _run_check_against_fake_venv(monkeypatch, importable={"cv2"})

    outcome = veny.import_outcome_in_venv(options, "cv2")

    assert outcome.imported is True


def test_a_successful_import_reports_which_distribution_provided_it(
    monkeypatch, tmp_path
):
    # The seam between import_outcome_in_venv and the script it generates. If it
    # stops asking the venv who provided the import, every attribution gate
    # downstream is fed an empty set and silently stops caching anything -- or,
    # under a different mistake, stops gating. Checked against a distribution
    # that really is installed (pytest is running this), so the assertion is
    # about real importlib.metadata output rather than a stub of it.
    options = veny.Options()
    options.my_dir = tmp_path
    options.set_venv_dir(tmp_path / "venv")
    _run_check_against_fake_venv(monkeypatch, importable={"pytest"})

    outcome = veny.import_outcome_in_venv(options, "pytest")

    assert outcome.imported is True
    assert "pytest" in outcome.providers


def test_a_per_record_success_credited_elsewhere_is_not_confirmed(
    monkeypatch, tmp_path
):
    # The bulk check fails because of one record, so the run drops to per-record
    # verification -- where another record's import can still be satisfied by a
    # distribution other than the one it names. Same rule, second path.
    index = _live_index(tmp_path)
    broken = veny.ResolvedImport(import_name="alpha", pip_name="alpha-pkg")
    misattributed = veny.ResolvedImport(import_name="beta", pip_name="beta-pkg")
    options = _options_with_venv(tmp_path, index, [broken, misattributed])
    fake = _FakeInstalledVenv(
        # beta-pkg installed and provides something else entirely; beta really
        # comes from other-pkg. alpha-pkg never installed, which is what makes
        # the bulk check fail and forces the per-record path.
        provides={"beta-pkg": "something-else", "other-pkg": "beta"},
        installed=["beta-pkg", "other-pkg"],
    )
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(veny, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    veny.verify_and_repair_imports(options)

    assert index.cache.entries == {}


def test_a_second_candidates_machine_scoped_failure_is_also_not_persisted(
    monkeypatch, tmp_path
):
    # Finding 1's scenario one attempt deeper: the *replacement* candidate is the
    # one this machine cannot load. resolve_and_verify does its own rejecting, so
    # a hardcoded "import_failed" there would durably blacklist a package whose
    # only sin is that libGL is missing here -- the same permanent suppression,
    # reached by the second candidate instead of the first.
    index = _live_index(tmp_path, seed={"cv2": "opencv-python-headless"})
    record = veny.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    options = _options_with_venv(tmp_path, index, [record])
    fake = _FakeInstalledVenv(
        provides={"opencv-python": "cv2", "opencv-python-headless": "cv2"},
        installed=["opencv-python"],
        unusable={"opencv-python", "opencv-python-headless"},
    )
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(veny, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    veny.verify_and_repair_imports(options)

    # The second candidate was tried and removed, like the first.
    assert fake.attempted == ["opencv-python-headless"]
    assert fake.uninstalled == ["opencv-python", "opencv-python-headless"]
    # And neither is remembered anywhere durable.
    assert index.cache.rejections == {}
    assert not (tmp_path / "alias_cache.json").exists()


def test_a_missing_shared_library_is_reported_to_the_user(
    monkeypatch, tmp_path, caplog
):
    # stdlib_index.NEEDS_SYSTEM_PACKAGE answers this class of problem with a
    # report rather than a suppression. Silently trying the next candidate turns
    # "you need to install libgl1" into an unexplained dead end.
    options = veny.Options()
    options.my_dir = tmp_path
    options.set_venv_dir(tmp_path / "venv")
    _run_check_against_fake_venv(
        monkeypatch,
        importable=set(),
        errors={
            "cv2": "libGL.so.1: cannot open shared object file: No such file or directory"
        },
    )

    with caplog.at_level(logging.WARNING):
        veny.import_outcome_in_venv(options, "cv2")

    messages = [record.getMessage() for record in caplog.records]
    assert any("libGL.so.1" in message for message in messages), messages
    assert any("cv2" in message for message in messages), messages


def test_a_machine_scoped_failure_leaves_no_persisted_rejection(monkeypatch, tmp_path):
    # opencv-python installed correctly and declares cv2; this machine just
    # lacks libGL.so.1. The in-session retry is still right -- headless may
    # genuinely be the answer -- but persisting a rejection suppresses the
    # correct package on this machine on every later run, including after the
    # user installs libgl1. The cache outranks every tier except OVERRIDE.
    #
    # The seeding matters: opencv-python is deliberately still resolvable (from
    # the seed, and headless from the target interpreter's metadata), so if the
    # failure were forgotten immediately rather than for the run, resolve() would
    # re-rank the name just uninstalled back to position 0 and veny would
    # re-download and re-install a ~90 MB wheel it has already proven unusable.
    index = _live_index(
        tmp_path,
        seed={"cv2": "opencv-python"},
        installed={"cv2": ["opencv-python-headless"]},
    )
    record = veny.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    options = _options_with_venv(tmp_path, index, [record])
    fake = _FakeInstalledVenv(
        provides={"opencv-python": "cv2", "opencv-python-headless": "cv2"},
        installed=["opencv-python"],
        unusable={"opencv-python"},
    )
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(veny, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    veny.verify_and_repair_imports(options)

    # Removed once, and the next candidate tried -- not the same unusable wheel
    # re-installed because the failure was forgotten the instant it happened.
    assert fake.uninstalled == ["opencv-python"]
    assert fake.attempted == ["opencv-python-headless"]
    # Remembered for the rest of this run...
    assert index.cache.rejected_names("cv2") == frozenset({"opencv-python"})
    # ...and nowhere else: the durable store is untouched, on disk and in memory.
    assert index.cache.rejections == {}
    assert (
        alias_index.AliasCache.load(
            tmp_path / "alias_cache.json", interpreter_tag="3.12"
        ).rejected_names("cv2")
        == frozenset()
    )


def test_a_package_that_lacks_the_import_is_still_rejected_durably(
    monkeypatch, tmp_path
):
    # The guard against over-correcting: an ordinary "installed but does not
    # contain it" failure must still be persisted, or every run re-attempts the
    # same wrong package.
    index = _live_index(tmp_path, seed={"thing": "right-pkg"})
    record = veny.ResolvedImport(import_name="thing", pip_name="wrong-pkg")
    options = _options_with_venv(tmp_path, index, [record])
    fake = _FakeInstalledVenv(
        provides={"wrong-pkg": "something-else", "right-pkg": "thing"},
        installed=["wrong-pkg"],
    )
    monkeypatch.setattr(veny, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(veny, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    veny.verify_and_repair_imports(options)

    assert index.cache.rejected_names("thing") == frozenset({"wrong-pkg"})


def test_the_repair_installer_reports_failure_instead_of_exiting(monkeypatch, tmp_path):
    # install_into_venv drives a single `uv pip install` and, on a nonzero
    # return code, logs the error and returns False rather than raising or
    # exiting. resolve_and_verify's installer must not be able to end the
    # run: one unverifiable import is not a reason to kill everything.
    options = veny.Options()
    options.my_dir = tmp_path
    options.set_venv_dir(tmp_path / "venv")

    def fake_run(command, *args, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr="no such package"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert (
        environment.install_into_venv(options.venv_python, "nonexistent-package")
        is False
    )


def test_resolved_import_still_round_trips_when_alias_index_is_lazy():
    # Making the import lazy must not quietly turn the ResolvedImport and
    # AliasIndex handlers into dead code that falls through to str().
    record = veny.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    assert ek.from_jsonable(ek.to_jsonable(record)) == record


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
    payload = ek.to_jsonable(index)
    assert isinstance(payload, dict)
    assert payload["overrides"] == {"cv2": "my-opencv"}
    assert payload["interpreter_tag"] == "3.12"
    assert payload["cache_path"] == "/tmp/none.json"
    assert payload["offline"] is True


def test_resolved_import_round_trips_through_json():
    # uninstalled_imports is written to the last-used options file, which
    # check_venv_dir still reads for its venv_dir pointer. Without a handler
    # each record stringifies to "ResolvedImport(import_name='cv2', ...)",
    # losing the structured data that the rest of the file depends on.
    record = veny.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    restored = ek.from_jsonable(ek.to_jsonable({record}))
    assert restored == {record}
