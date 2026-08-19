"""Everything that proves what a virtual environment really provides.

The live test below is the reason this file exists in this order: PROGRESS
records three phase-2 regressions that a green 264-test suite shipped past,
every one of them because the subprocess was stubbed. run_import_check_in_venv
builds a Python source string and hands it to a real interpreter; a fake can
only ever prove the fake.

The rest of the file is the verification suite that used to live in
tests/test_split_imports.py, moved here with the twelve symbols it exercises
when they became veny.verify. None of it constructs an Options any more:
verify's functions take the paths, names and flags they actually read, so the
tests hand them the same things cli.py does.
"""

import contextlib
import logging
import shutil
import subprocess

import pytest

from tests.wheels import build_wheel
from veny import alias_index, environment, verify
from veny.alias_index import Candidate, Resolution, ResolvedImport, Source


def test_a_live_import_check_reports_the_distribution_that_provided_it(tmp_path):
    """import_outcome_in_venv credits the real distribution, from real metadata.

    A bug that would make this fail: import_providers parsing the wrong prefix,
    or run_import_check_in_venv dropping report_providers, would leave
    providers empty -- and an empty providers set makes
    _credited_with_the_import refuse every confirm(), silently disabling the
    alias cache. No unit test with a fake stdout can catch a mismatch between
    the string the probe script prints and the string the parser expects,
    because both sides are written together in the fake.

    Expected values: "venytest" is the distribution name tests/wheels.py builds;
    the run below was executed to confirm the parse, not reasoned about --
    providers came back as frozenset({"venytest"}), matching the brief.
    """
    venv_dir = tmp_path / "venv"
    python = shutil.which("python3")
    assert python is not None, "test host must have a python3 on PATH"
    environment.create_venv(venv_dir, python)
    wheel_path = build_wheel(tmp_path)
    venv_python = venv_dir / "bin" / "python"
    assert environment.install_into_venv(venv_python, str(wheel_path)) is True

    outcome = verify.import_outcome_in_venv(venv_python, "venytest")
    assert outcome.imported is True
    assert outcome.rejection_kind == ""
    assert outcome.providers == frozenset({"venytest"})

    environment.uninstall_from_venv(venv_python, "venytest")
    after = verify.import_outcome_in_venv(venv_python, "venytest")
    assert after.imported is False
    assert after.rejection_kind == "import_failed"
    assert "venytest" in after.detail


def test_source_import_names_returns_all_imports_when_reqs_is_off():
    """Without --reqs nothing is subtracted, even if extra_requirements is set.

    A bug that would make this fail: dropping the use_reqs guard, which would
    subtract requirement spellings from a run that never asked for them and
    stop those imports being verified.

    Expected value obtained by running source_import_names against these
    exact inputs, which returned {"yaml", "requests"} unchanged.
    """
    assert verify.source_import_names(
        {"yaml", "requests"}, {"requests": None}, False
    ) == {"yaml", "requests"}


def test_source_import_names_subtracts_requirement_spellings_under_reqs():
    """With --reqs the requirement spellings are removed from the source names.

    A bug that would make this fail: subtracting the wrong dict (keys vs
    values), which would leave a pip spelling in the set that import_module()
    can never satisfy, condemning a package that installed perfectly well.

    Expected value obtained by running source_import_names against these
    exact inputs, which returned {"yaml"}.
    """
    assert verify.source_import_names(
        {"yaml", "opencv-python"}, {"opencv-python": ">=4"}, True
    ) == {"yaml"}


def test_source_import_names_leaves_non_overlapping_requirements_alone():
    """A requirement that is not in all_imports subtracts nothing.

    A bug that would make this fail: replacing the set difference with an
    intersection or an assignment, which would empty the result and skip
    verification entirely.

    Expected value obtained by running source_import_names against these
    exact inputs, which returned {"yaml"} unchanged.
    """
    assert verify.source_import_names({"yaml"}, {"requests": None}, True) == {"yaml"}


def test_the_bulk_branch_checks_a_source_name_under_that_name_alone(
    monkeypatch, tmp_path
):
    """A name the user wrote is import-checked under exactly that name.

    A bug that would make this fail: handing the bulk branch an empty
    source_names, which drops the name out of the `entry.import_name in
    source_names` test and falls through to the distribution's whole top-level
    list -- fail-open, because a wrongly resolved pip name then passes on
    whatever it does provide. That mis-wiring is now reachable by accident:
    source_names is a keyword argument defaulting to frozenset(), so a caller
    that simply forgets it gets the fail-open behaviour with no error. This is
    the mis-wiring the STANDING CHECK exists to catch, pinned here so the
    mutation has a named test to kill.

    Expected value obtained by running the current implementation and printing
    the `alternatives` list it builds: [["cv2"]], because "cv2" is in
    source_names and so is checked under its own name rather than under the
    distribution's full top-level list. top_levels deliberately does NOT
    contain "cv2" (only its sibling "cv"), so the condition's second disjunct
    (`top_levels and entry.import_name in top_levels`) cannot itself supply a
    match -- only source_names can put "cv2" in scope. That was necessary:
    with top_levels containing "cv2" too (tried first, and measured), an
    emptied source_names is masked by that disjunct and the assertion cannot
    tell the two apart. Confirmed by running the literal mutation named
    above (dropping source_names={"cv2"} from this test's own call, standing
    in for the mis-wiring a caller elsewhere could introduce): with this
    fixture it changes `seen` to [[["cv"]]], failing this test's assertion,
    whereas the unmutated call with source_names={"cv2"} produces [[["cv2"]]]
    and passes.
    """
    seen: list[list[list[str]]] = []

    def fake_run(venv_python, alternatives, report_providers=False):
        seen.append(alternatives)
        return True, ""

    # verify.py resolves these through its own `alias_index` name, bound by
    # `from . import alias_index` to this same module object -- patching the
    # module imported here reaches the identical singleton
    # verify.check_packages_in_venv calls into.
    monkeypatch.setattr(verify, "run_import_check_in_venv", fake_run)
    monkeypatch.setattr(alias_index, "probe_interpreter", lambda _p: ("3.13", {}))
    monkeypatch.setattr(
        alias_index,
        "import_names_by_distribution",
        lambda _d: {"opencv-python": frozenset({"cv"})},
    )

    assert (
        verify.check_packages_in_venv(
            environment.venv_python_for(tmp_path),
            uninstalled={ResolvedImport(import_name="cv2", pip_name="opencv-python")},
            source_names={"cv2"},
        )
        is True
    )
    assert seen == [[["cv2"]]]


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

    winner = verify.resolve_and_verify(
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
        return verify.ImportOutcome(
            imported=True,
            rejection_kind="",
            detail="",
            providers=frozenset({"scikit-learn"}),
        )

    winner = verify.resolve_and_verify(
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
        return verify.ImportOutcome(
            imported=True,
            rejection_kind="",
            detail="",
            providers=frozenset({"skill_metrics"}),
        )

    verify.resolve_and_verify(
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
    verify.resolve_and_verify(
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
    verify.resolve_and_verify(
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

    result = verify.resolve_and_verify(
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
    result = verify.resolve_and_verify(
        Resolution("thing", ()),
        _RecordingIndex(),
        installer=tried.append,
        importer=lambda name: True,
        uninstaller=lambda name: None,
    )
    assert result is None
    assert tried == []


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
    captured = _captured_venv_check_code(monkeypatch)

    verify.check_packages_in_venv(
        environment.venv_python_for(tmp_path),
        record=ResolvedImport(import_name="cv2", pip_name="opencv-python"),
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
    uninstalled = {
        ResolvedImport(import_name="cv2", pip_name="opencv-python"),
        ResolvedImport(import_name="yaml", pip_name="PyYAML"),
    }
    monkeypatch.setattr(
        alias_index, "probe_interpreter", lambda python, timeout=30.0: ("3.12", {})
    )
    captured = _captured_venv_check_code(monkeypatch)

    verify.check_packages_in_venv(
        environment.venv_python_for(tmp_path), uninstalled=uninstalled
    )

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
    uninstalled = {
        ResolvedImport(import_name="opencv-python", pip_name="opencv-python"),
    }
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"cv2": ["opencv-python"]}),
    )
    captured = _captured_venv_check_code(monkeypatch)

    verify.check_packages_in_venv(
        environment.venv_python_for(tmp_path), uninstalled=uninstalled
    )

    assert "'cv2'" in captured[0]
    assert "'opencv-python'" not in captured[0]


def test_check_packages_in_venv_bulk_branch_matches_pep503_spelling(
    monkeypatch, tmp_path
):
    # The venv metadata may report a distribution name spelled differently
    # (underscores vs hyphens) than the record's pip_name. The lookup must
    # normalize both sides, per PEP 503, or a genuinely installed package
    # gets checked under the wrong name and rejected.
    uninstalled = {
        ResolvedImport(import_name="opencv_python", pip_name="opencv_python"),
    }
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        # Metadata reports the hyphenated spelling; the record uses underscores.
        lambda python, timeout=30.0: ("3.12", {"cv2": ["opencv-python"]}),
    )
    captured = _captured_venv_check_code(monkeypatch)

    verify.check_packages_in_venv(
        environment.venv_python_for(tmp_path), uninstalled=uninstalled
    )

    assert "'cv2'" in captured[0]


def test_check_packages_in_venv_bulk_branch_falls_back_when_distribution_unknown(
    monkeypatch, tmp_path
):
    # A record whose pip_name is not in the venv's metadata (e.g. it was
    # never actually installed, or metadata is incomplete) must still be
    # checked -- under its import_name, exactly as before -- never skipped.
    uninstalled = {ResolvedImport(import_name="numpy", pip_name="numpy")}
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"some_other_thing": ["unrelated-pkg"]}),
    )
    captured = _captured_venv_check_code(monkeypatch)

    verify.check_packages_in_venv(
        environment.venv_python_for(tmp_path), uninstalled=uninstalled
    )

    assert "'numpy'" in captured[0]


def test_check_packages_in_venv_probes_the_venv_once_per_call(monkeypatch, tmp_path):
    # Each probe is a subprocess; probing per record instead of per call would
    # multiply that cost by the number of uninstalled imports.
    uninstalled = {
        ResolvedImport(import_name="cv2", pip_name="opencv-python"),
        ResolvedImport(import_name="yaml", pip_name="PyYAML"),
        ResolvedImport(import_name="numpy", pip_name="numpy"),
    }
    probe_calls = []

    def fake_probe(python, timeout=30.0):
        probe_calls.append(python)
        return "3.12", {}

    monkeypatch.setattr(alias_index, "probe_interpreter", fake_probe)
    _captured_venv_check_code(monkeypatch)

    verify.check_packages_in_venv(
        environment.venv_python_for(tmp_path), uninstalled=uninstalled
    )

    assert len(probe_calls) == 1


def _run_check_against_fake_venv(
    monkeypatch: pytest.MonkeyPatch,
    importable: set[str],
    errors: dict[str, str] | None = None,
) -> None:
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
    uninstalled = {
        ResolvedImport(import_name="opencv-python", pip_name="opencv-python"),
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

    assert (
        verify.check_packages_in_venv(
            environment.venv_python_for(tmp_path), uninstalled=uninstalled
        )
        is True
    )


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
    uninstalled = {ResolvedImport(import_name="setuptools", pip_name="setuptools")}
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

    assert (
        verify.check_packages_in_venv(
            environment.venv_python_for(tmp_path), uninstalled=uninstalled
        )
        is False
    )


def test_check_packages_in_venv_bulk_branch_fails_an_unprovided_source_import(
    monkeypatch, tmp_path
):
    # The other half of the fail-open hole, and the exact case the repair pass
    # exists for: the record's pip_name resolved *wrongly*, so it installed a
    # distribution that declares some other top-level name. Judging the record
    # by that distribution's metadata passes it -- the wrong package imports
    # fine, it just is not what the user wrote. The name in the user's source
    # is the one that has to import.
    uninstalled = {ResolvedImport(import_name="thing", pip_name="wrong-pkg")}
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"something_else": ["wrong-pkg"]}),
    )
    _run_check_against_fake_venv(monkeypatch, importable={"something_else"})

    assert (
        verify.check_packages_in_venv(
            environment.venv_python_for(tmp_path),
            uninstalled=uninstalled,
            source_names={"thing"},
        )
        is False
    )


def test_check_packages_in_venv_still_fails_a_genuinely_missing_package(
    monkeypatch, tmp_path
):
    # This must not become a way for everything to pass: when the package
    # really is missing -- whether or not metadata knows about it -- the
    # check must still fail.
    uninstalled = {ResolvedImport(import_name="cv2", pip_name="opencv-python")}
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"cv2": ["opencv-python"]}),
    )
    _run_check_against_fake_venv(monkeypatch, importable=set())

    assert (
        verify.check_packages_in_venv(
            environment.venv_python_for(tmp_path), uninstalled=uninstalled
        )
        is False
    )


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

    def outcome(self, venv_python, import_name):
        """Stand in for import_outcome_in_venv."""
        self.import_checks.append(import_name)
        if self.imports(import_name):
            return verify.ImportOutcome(
                imported=True,
                rejection_kind="",
                detail="",
                providers=self.providers_of(import_name),
            )
        if any(
            self.provides.get(p) == import_name and p in self.unusable
            for p in self.installed
        ):
            return verify.ImportOutcome(
                imported=False,
                rejection_kind="import_unavailable",
                detail="libGL.so.1: cannot open shared object file",
            )
        return verify.ImportOutcome(
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

    def check(
        self,
        venv_python,
        *,
        record=None,
        uninstalled=frozenset(),
        source_names=frozenset(),
    ):
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
                entry.import_name not in source_names
                and entry.pip_name in self.installed
            )
            for entry in uninstalled
        )


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


def _verify_and_repair(
    tmp_path, index, records, *, source_names=None, extra_requirements=None
):
    """Run verify_and_repair_imports wired the way cli.setup_virtualenv wires it.

    The venv paths match Options.set_venv_dir's documented shape
    (<venv>/bin/python, <venv>/requirements.txt), written out here rather than
    read back off an Options -- verify has never heard of one.

    Args:
        tmp_path:           Pytest's per-test temporary directory.
        index:              The AliasIndex to resolve against and record in.
        records:            The uninstalled records the install was asked for.
        source_names:       The user's own source imports. Defaults to every
                            record's import name, which is what Options carries
                            for a run with no --reqs entries.
        extra_requirements: The --reqs entries kept in a rewritten
                            requirements.txt. Defaults to none.

    Returns:
        The final uninstalled records verify_and_repair_imports produced.
    """
    venv_dir = tmp_path / "venv"
    venv_dir.mkdir(parents=True, exist_ok=True)
    return verify.verify_and_repair_imports(
        venv_python=venv_dir / "bin" / "python",
        requirements_file=venv_dir / "requirements.txt",
        uninstalled=set(records),
        extra_requirements=extra_requirements if extra_requirements else {},
        source_names={record.import_name for record in records}
        if source_names is None
        else source_names,
        index=index,
        rawlog=False,
    )


def test_a_verified_import_is_written_to_the_alias_cache(monkeypatch, tmp_path):
    # Nothing called confirm(), so ~/veny/module_aliases_cache.json was never
    # written, Source.CACHE never fired, and every run re-resolved every import
    # over the network forever.
    index = _live_index(tmp_path)
    record = ResolvedImport(import_name="yaml", pip_name="PyYAML")
    fake = _FakeInstalledVenv(provides={"PyYAML": "yaml"}, installed=["PyYAML"])
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)

    _verify_and_repair(tmp_path, index, [record])

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
    record = ResolvedImport(import_name="thing", pip_name="wrong-pkg")
    fake = _FakeInstalledVenv(
        provides={"wrong-pkg": "something-else", "other-pkg": "thing"},
        installed=["wrong-pkg", "other-pkg"],
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    _verify_and_repair(tmp_path, index, [record])

    assert index.cache.entries == {}


def test_an_import_attributable_to_its_own_distribution_is_confirmed(
    monkeypatch, tmp_path
):
    # The other side of the same rule: requiring attribution must not stop the
    # ordinary case from being cached, or the CACHE tier is dead again.
    index = _live_index(tmp_path)
    record = ResolvedImport(import_name="thing", pip_name="thing-pkg")
    fake = _FakeInstalledVenv(provides={"thing-pkg": "thing"}, installed=["thing-pkg"])
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)

    _verify_and_repair(tmp_path, index, [record])

    assert index.cache.get("thing") == "thing-pkg"


def test_an_import_the_batch_install_did_not_provide_is_repaired(monkeypatch, tmp_path):
    # The batch install installs candidates[0] and nothing else, so a wrong
    # first candidate used to be final: ranking past position 0 had no
    # production effect at all.
    index = _live_index(tmp_path, seed={"thing": "right-pkg"})
    record = ResolvedImport(import_name="thing", pip_name="wrong-pkg")
    # wrong-pkg installed fine during the batch; it just does not provide "thing".
    fake = _FakeInstalledVenv(
        provides={"wrong-pkg": "something-else", "right-pkg": "thing"},
        installed=["wrong-pkg"],
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    final = _verify_and_repair(tmp_path, index, [record])

    assert fake.attempted == ["right-pkg"]
    # The package that installed without providing the import must not be left
    # behind: it pollutes the venv and can shadow the correct package.
    assert fake.uninstalled == ["wrong-pkg"]
    assert index.cache.get("thing") == "right-pkg"
    assert "wrong-pkg" in index.cache.rejected_names("thing")
    # The record now names the package that actually provided the import.
    assert final == {ResolvedImport(import_name="thing", pip_name="right-pkg")}


def test_the_repair_path_import_checks_the_import_name_never_the_pip_name(
    monkeypatch, tmp_path
):
    # Exactly the defect found and fixed in Task 6. import_module("right-pkg")
    # always fails, so checking the pip name would reject every correct
    # candidate and uninstall it again.
    index = _live_index(tmp_path, seed={"thing": "right-pkg"})
    record = ResolvedImport(import_name="thing", pip_name="wrong-pkg")
    fake = _FakeInstalledVenv(
        provides={"wrong-pkg": "something-else", "right-pkg": "thing"},
        installed=["wrong-pkg"],
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    _verify_and_repair(tmp_path, index, [record])

    assert fake.import_checks
    assert set(fake.import_checks) == {"thing"}


def test_a_record_carrying_a_pip_spelling_is_never_repaired(monkeypatch, tmp_path):
    """A --reqs record whose "import name" is a pip name is never uninstalled.

    requirement_records() (--reqs) and resolve_records() (dependencies) both
    produce records whose import_name is a pip name, e.g. ("opencv-python",
    "opencv-python"). import_module("opencv-python") always fails, so treating
    that as a failed import would uninstall a package that installed perfectly
    well and is exactly what the user asked for.

    A bug that would make this fail: dropping the source_names filter in
    verify_and_repair_imports, which would send the pip-spelled record down the
    repair path -- uninstalling a package that installed perfectly well,
    because import_module() can never succeed on "opencv-python".

    The second record is what makes this test load-bearing: with only the
    pip-spelled record present the function returns before the filter is
    reached, and PROGRESS records that the earlier version of this test passed
    with the filter deleted. `unsatisfied` fails the bulk check (nothing
    provides "thing") and is the only name in source_names, so the per-record
    loop runs -- but must run over that record alone.

    Expected values measured by running this test against the real
    implementation: the pip-spelled record is neither uninstalled nor
    re-attempted, and the only install attempt is the override candidate for
    the second record, which is rigged to fail so the repair ends without
    writing anything to the cache. Deleting the filter was then run: the
    pip-spelled record reaches repair_unsatisfied_import, whose metadata lookup
    finds "opencv-python" installed and uninstalls it, so `fake.uninstalled`
    becomes ["opencv-python"] and the first assertion fails. That mutation was
    run; exactly this test failed, with the other 39 in this file still green.
    """
    index = _live_index(tmp_path, overrides={"thing": "thing-only-pkg"})
    pip_spelled = ResolvedImport(import_name="opencv-python", pip_name="opencv-python")
    unsatisfied = ResolvedImport(import_name="thing", pip_name="thing-pkg")
    fake = _FakeInstalledVenv(
        provides={"opencv-python": "cv2"},
        installed=["opencv-python"],
        install_failures={"thing-only-pkg"},
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    _verify_and_repair(
        tmp_path, index, [pip_spelled, unsatisfied], source_names={"thing"}
    )

    assert fake.uninstalled == []
    # Only the second record's candidate was ever installed: the pip-spelled
    # record was filtered out before the loop and never touched.
    assert fake.attempted == ["thing-only-pkg"]
    assert index.cache.entries == {}


def test_a_repair_that_cannot_succeed_leaves_the_run_going(monkeypatch, tmp_path):
    # veny's job is to get as far as it can and report honestly. An import
    # nothing can satisfy must not raise out of the verification pass.
    index = _live_index(tmp_path)
    record = ResolvedImport(import_name="mystery", pip_name="mystery")
    fake = _FakeInstalledVenv(provides={}, install_failures={"mystery"})
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    final = _verify_and_repair(tmp_path, index, [record])

    assert final == {record}
    # A failed install may be transient, so it must not be persisted as a fact
    # about the package.
    assert index.cache.rejected_names("mystery") == frozenset()


def test_a_missing_shared_library_is_classified_as_machine_scoped(
    monkeypatch, tmp_path
):
    # The discriminating text arrives on the ImportError and used to be thrown
    # away one line later by "except ImportError: continue".
    _run_check_against_fake_venv(
        monkeypatch,
        importable=set(),
        errors={
            "cv2": "libGL.so.1: cannot open shared object file: No such file or directory"
        },
    )

    outcome = verify.import_outcome_in_venv(tmp_path / "bin" / "python", "cv2")

    assert outcome.imported is False
    assert outcome.rejection_kind == "import_unavailable"
    assert "libGL.so.1" in outcome.detail


def test_an_absent_module_is_still_classified_as_a_package_fault(monkeypatch, tmp_path):
    # The distinction must stay sharp in both directions: a package that
    # installs and genuinely does not contain the module is a durable fact, and
    # must keep being remembered so it is not re-attempted every run.
    _run_check_against_fake_venv(
        monkeypatch, importable=set(), errors={"thing": "No module named 'thing'"}
    )

    outcome = verify.import_outcome_in_venv(tmp_path / "bin" / "python", "thing")

    assert outcome.imported is False
    assert outcome.rejection_kind == "import_failed"


def test_a_working_import_reports_no_rejection(monkeypatch, tmp_path):
    _run_check_against_fake_venv(monkeypatch, importable={"cv2"})

    outcome = verify.import_outcome_in_venv(tmp_path / "bin" / "python", "cv2")

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
    _run_check_against_fake_venv(monkeypatch, importable={"pytest"})

    outcome = verify.import_outcome_in_venv(tmp_path / "bin" / "python", "pytest")

    assert outcome.imported is True
    assert "pytest" in outcome.providers


def test_a_per_record_success_credited_elsewhere_is_not_confirmed(
    monkeypatch, tmp_path
):
    # The bulk check fails because of one record, so the run drops to per-record
    # verification -- where another record's import can still be satisfied by a
    # distribution other than the one it names. Same rule, second path.
    index = _live_index(tmp_path)
    broken = ResolvedImport(import_name="alpha", pip_name="alpha-pkg")
    misattributed = ResolvedImport(import_name="beta", pip_name="beta-pkg")
    fake = _FakeInstalledVenv(
        # beta-pkg installed and provides something else entirely; beta really
        # comes from other-pkg. alpha-pkg never installed, which is what makes
        # the bulk check fail and forces the per-record path.
        provides={"beta-pkg": "something-else", "other-pkg": "beta"},
        installed=["beta-pkg", "other-pkg"],
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    _verify_and_repair(tmp_path, index, [broken, misattributed])

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
    record = ResolvedImport(import_name="cv2", pip_name="opencv-python")
    fake = _FakeInstalledVenv(
        provides={"opencv-python": "cv2", "opencv-python-headless": "cv2"},
        installed=["opencv-python"],
        unusable={"opencv-python", "opencv-python-headless"},
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    _verify_and_repair(tmp_path, index, [record])

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
    _run_check_against_fake_venv(
        monkeypatch,
        importable=set(),
        errors={
            "cv2": "libGL.so.1: cannot open shared object file: No such file or directory"
        },
    )

    with caplog.at_level(logging.WARNING):
        verify.import_outcome_in_venv(tmp_path / "bin" / "python", "cv2")

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
    record = ResolvedImport(import_name="cv2", pip_name="opencv-python")
    fake = _FakeInstalledVenv(
        provides={"opencv-python": "cv2", "opencv-python-headless": "cv2"},
        installed=["opencv-python"],
        unusable={"opencv-python"},
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    _verify_and_repair(tmp_path, index, [record])

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
    record = ResolvedImport(import_name="thing", pip_name="wrong-pkg")
    fake = _FakeInstalledVenv(
        provides={"wrong-pkg": "something-else", "right-pkg": "thing"},
        installed=["wrong-pkg"],
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    _verify_and_repair(tmp_path, index, [record])

    assert index.cache.rejected_names("thing") == frozenset({"wrong-pkg"})


def test_a_repair_rewrites_requirements_txt_with_the_extra_requirements(
    monkeypatch, tmp_path
):
    """The requirements.txt a repair rewrites must keep the --reqs specifiers.

    verify_and_repair_imports rewrites the venv's requirements.txt once a
    repair has swapped a record, so the file keeps describing what is really
    installed. Phase 3c task 2 made options.extra_requirements an explicit
    argument at that call site; nothing then checked it arrives, and task 5's
    differential pins the uv argv rather than this file's contents.

    Concrete bug this catches: pass `{}` instead of the extra_requirements
    argument here and the rewritten file reads a bare `right-pkg`. The venv's
    own record of what it holds silently loses the `>=3.1` pin the user
    supplied, so a later `uv pip install -r` against it -- or a human reading
    it -- installs a version the run was never allowed to use. The expected
    text follows write_requirements_file_with_extras' contract, not a re-run of
    the writer.
    """
    index = _live_index(tmp_path, seed={"thing": "right-pkg"})
    record = ResolvedImport(import_name="thing", pip_name="wrong-pkg")
    fake = _FakeInstalledVenv(
        provides={"wrong-pkg": "something-else", "right-pkg": "thing"},
        installed=["wrong-pkg"],
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", fake.install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    final = _verify_and_repair(
        tmp_path, index, [record], extra_requirements={"right-pkg": ">=3.1"}
    )

    # The repair happened -- without it the rewrite branch is never reached and
    # this test would be asserting on a file nobody wrote.
    assert final == {ResolvedImport(import_name="thing", pip_name="right-pkg")}
    assert (tmp_path / "venv" / "requirements.txt").read_text() == "right-pkg>=3.1\n"


def test_the_repair_installer_is_given_the_venvs_own_interpreter(monkeypatch, tmp_path):
    """install_into_venv must be handed the venv's interpreter, not None.

    Phase 3c task 2 replaced install_into_venv's implicit `options.venv_python`
    read with an explicit first argument built at this call site, so the
    interpreter can now be wired wrongly where before it could not be.

    Concrete bug this catches: call `environment.install_into_venv(None, ...)`
    in repair_unsatisfied_import's `installer` closure. run_uv_pip's
    `venv_python is None` branch then logs and returns None for every
    candidate, so install_into_venv returns False every time, resolve_and_verify
    exhausts the ranked list, and veny reports "Could not find a package that
    provides the import thing" for an import whose correct package was sitting
    right there and installable. Nothing raises and nothing else in the suite
    notices. The expected path is Options.set_venv_dir's documented shape
    (<venv>/bin/python), written out here rather than read back off options.
    """
    index = _live_index(tmp_path, seed={"thing": "right-pkg"})
    record = ResolvedImport(import_name="thing", pip_name="wrong-pkg")
    fake = _FakeInstalledVenv(
        provides={"wrong-pkg": "something-else", "right-pkg": "thing"},
        installed=["wrong-pkg"],
    )
    interpreters = []

    def recording_install(venv_python, pip_name):
        interpreters.append(venv_python)
        return fake.install(venv_python, pip_name)

    monkeypatch.setattr(verify, "check_packages_in_venv", fake.check)
    monkeypatch.setattr(verify, "import_outcome_in_venv", fake.outcome)
    monkeypatch.setattr(alias_index, "probe_interpreter", fake.probe)
    monkeypatch.setattr(environment, "install_into_venv", recording_install)
    monkeypatch.setattr(environment, "uninstall_from_venv", fake.uninstall)

    _verify_and_repair(tmp_path, index, [record])

    assert interpreters == [tmp_path / "venv" / "bin" / "python"]
