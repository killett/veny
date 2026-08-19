"""Characterize the verification boundary before it becomes veny.verify.

The live test below is the reason this file exists in this order: PROGRESS
records three phase-2 regressions that a green 264-test suite shipped past,
every one of them because the subprocess was stubbed. run_import_check_in_venv
builds a Python source string and hands it to a real interpreter; a fake can
only ever prove the fake.
"""

import shutil

from tests.wheels import build_wheel
from veny import alias_index, cli, environment
from veny.alias_index import ResolvedImport


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

    options = cli.Options()
    options.set_venv_dir(venv_dir)

    outcome = cli.import_outcome_in_venv(options, "venytest")
    assert outcome.imported is True
    assert outcome.rejection_kind == ""
    assert outcome.providers == frozenset({"venytest"})

    environment.uninstall_from_venv(venv_python, "venytest")
    after = cli.import_outcome_in_venv(options, "venytest")
    assert after.imported is False
    assert after.rejection_kind == "import_failed"
    assert "venytest" in after.detail


def test_source_import_names_returns_all_imports_when_reqs_is_off():
    """Without --reqs nothing is subtracted, even if extra_requirements is set.

    A bug that would make this fail: dropping the `getattr(options.args,
    "reqs", False)` guard, which would subtract requirement spellings from a
    run that never asked for them and stop those imports being verified.
    """
    options = cli.Options()
    options.all_imports = {"yaml", "requests"}
    options.extra_requirements = {"requests": None}
    assert cli.source_import_names(options) == {"yaml", "requests"}


def test_source_import_names_subtracts_requirement_spellings_under_reqs():
    """With --reqs the requirement spellings are removed from the source names.

    A bug that would make this fail: subtracting the wrong dict (keys vs
    values), which would leave a pip spelling in the set that import_module()
    can never satisfy, condemning a package that installed perfectly well.
    """
    options = cli.Options()
    options.all_imports = {"yaml", "opencv-python"}
    options.extra_requirements = {"opencv-python": ">=4"}
    options.args.reqs = True
    assert cli.source_import_names(options) == {"yaml"}


def test_source_import_names_leaves_non_overlapping_requirements_alone():
    """A requirement that is not in all_imports subtracts nothing.

    A bug that would make this fail: replacing the set difference with an
    intersection or an assignment, which would empty the result and skip
    verification entirely.
    """
    options = cli.Options()
    options.all_imports = {"yaml"}
    options.extra_requirements = {"requests": None}
    options.args.reqs = True
    assert cli.source_import_names(options) == {"yaml"}


def test_the_bulk_branch_checks_a_source_name_under_that_name_alone(monkeypatch):
    """A name the user wrote is import-checked under exactly that name.

    A bug that would make this fail: handing the bulk branch an empty
    source_names, which drops the name out of the `entry.import_name in
    source_names` test and falls through to the distribution's whole top-level
    list -- fail-open, because a wrongly resolved pip name then passes on
    whatever it does provide. This is the mis-wiring the STANDING CHECK exists
    to catch, pinned here so the mutation has a named test to kill.

    Expected value obtained by running the current implementation and printing
    the `alternatives` list it builds: [["cv2"]], because "cv2" is in
    source_names and so is checked under its own name rather than under the
    distribution's full top-level list.

    Measured mutation caveat: because this fixture's top_levels
    (frozenset({"cv2", "cv"})) also contains "cv2", forcing source_names to
    empty alone does not change the outcome -- the condition's second
    disjunct (`top_levels and entry.import_name in top_levels`) still holds
    and produces the same ["cv2"], confirmed by running that exact mutation.
    The mutation that actually kills this test, and the one that faithfully
    realizes "falls through to the distribution's whole top-level list", is
    disabling the whole `if` condition (both disjuncts) so execution reaches
    `elif top_levels: alternatives.append(sorted(top_levels))`, producing
    ["cv", "cv2"] instead of ["cv2"]. Confirmed by running that mutation.
    """
    seen: list[list[list[str]]] = []

    def fake_run(venv_python, alternatives, report_providers=False):
        seen.append(alternatives)
        return True, ""

    # cli.py resolves these through its own `alias_index` name, bound by
    # `from . import alias_index` to this same module object -- patching the
    # module imported here (rather than the attr-defined-unsafe `cli.alias_index`)
    # reaches the identical singleton cli.check_packages_in_venv calls into.
    monkeypatch.setattr(cli, "run_import_check_in_venv", fake_run)
    monkeypatch.setattr(alias_index, "probe_interpreter", lambda _p: ("3.13", {}))
    monkeypatch.setattr(
        alias_index,
        "import_names_by_distribution",
        lambda _d: {"opencv-python": frozenset({"cv2", "cv"})},
    )

    options = cli.Options()
    options.set_venv_dir("/tmp/does-not-need-to-exist")
    options.uninstalled_imports = {
        ResolvedImport(import_name="cv2", pip_name="opencv-python")
    }
    assert cli.check_packages_in_venv(options, source_names={"cv2"}) is True
    assert seen == [[["cv2"]]]
