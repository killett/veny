"""Characterize the uv boundary that environment.py owns.

PROGRESS.md records three phase-2 regressions that shipped past a green,
264-test suite because every test in it stubbed the ``uv`` subprocess -- none
exercised the command lines veny actually builds. This module's live test
(below) drives the real ``uv`` binary against a real venv and a hand-built
wheel, with no network and no ``subprocess`` stubbing, so a broken argv or a
broken success/failure interpretation fails loudly here instead of shipping.

Every symbol under test is imported from ``veny.environment``, where Task 2
moved it from ``veny.cli``. This file does not duplicate what
tests/test_uv_backend.py already pins: uv_binary's three resolution outcomes,
the resolved-interpreter argv create_venv builds, and the
create_venv-before-requirements ordering.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

from tests.wheels import build_wheel
from veny import environment


def test_the_live_install_uninstall_round_trip_crosses_the_real_uv_boundary(
    monkeypatch, tmp_path
):
    """install_into_venv and uninstall_from_venv actually drive real uv.

    This is the fix for the regression class PROGRESS.md records three times:
    every phase-2 test stubbed subprocess, so a wrong verb, a swapped argument,
    or an inverted return-code check would still show a green suite. Here
    nothing is stubbed: a real venv is built with real `uv venv`, a real wheel
    is installed with real `uv pip install`, its module is imported by the
    venv's own interpreter, it is removed with real `uv pip uninstall`, and
    the import is re-attempted. A regression in the argv these functions
    build, or in how they interpret uv's return code, breaks one of the four
    assertions below rather than passing silently.

    UV_OFFLINE=1 is set so the run cannot depend on network reachability --
    re-verified while planning this task to make no difference to the outcome
    for a wheel with no dependencies.
    """
    monkeypatch.setenv("UV_OFFLINE", "1")

    venv_dir = tmp_path / "venv"
    python = shutil.which("python3")
    assert python is not None, "test host must have a python3 on PATH"
    assert environment.create_venv(venv_dir, python) is True

    wheel_path = build_wheel(tmp_path)

    venv_python = venv_dir / "bin" / "python"

    installed = environment.install_into_venv(venv_python, str(wheel_path))
    assert installed is True

    import_after_install = subprocess.run(
        [str(venv_python), "-c", "import venytest; print(venytest.value)"],
        capture_output=True,
        text=True,
    )
    assert import_after_install.returncode == 0
    assert import_after_install.stdout.strip() == "42"

    environment.uninstall_from_venv(venv_python, "venytest")

    import_after_uninstall = subprocess.run(
        [str(venv_python), "-c", "import venytest"],
        capture_output=True,
        text=True,
    )
    assert import_after_uninstall.returncode != 0
    assert "ModuleNotFoundError" in import_after_uninstall.stderr


def test_run_uv_pip_returns_none_and_never_touches_subprocess_without_a_venv_interpreter(
    monkeypatch, caplog
):
    """run_uv_pip short-circuits to None, logging rather than raising or shelling out.

    If the `venv_python is None` guard were removed or reordered after the
    command is built, this would either raise (os.fspath(None)) or
    spawn a subprocess with a garbage path. Asserting subprocess.run is never
    called catches a reordering that a return-value-only assertion would miss.
    """

    def _fail_if_called(*args, **kwargs):
        raise AssertionError(
            "subprocess.run must not be invoked with no venv interpreter"
        )

    monkeypatch.setattr(subprocess, "run", _fail_if_called)
    caplog.set_level(logging.INFO)

    result = environment.run_uv_pip(None, "install", "somepkg")

    assert result is None
    assert "no virtual environment interpreter is set" in caplog.text


def test_run_uv_pip_places_the_python_flag_before_the_package_arguments(monkeypatch):
    """run_uv_pip's argv is [uv, "pip", verb, "--python", venv_python, *rest], in order.

    uv reads --python positionally relative to the verb; if it were appended
    after the package arguments instead of before them, or if venv_python and
    the verb were transposed, uv would either error out or install into the
    wrong interpreter's site-packages -- a defect exactly this shape (a
    resolved-vs-bare interpreter mixup) has already shipped once in this
    project. subprocess.run is stubbed here (the true external boundary)
    purely to capture the argv without spawning a process; every other test
    of this behaviour goes through the real binary.
    """
    captured: list[list[str]] = []

    def _capture(command, **kwargs):
        captured.append(command)
        return subprocess.CompletedProcess(
            args=command, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _capture)

    venv_python = Path("/fake/venv/bin/python")

    environment.run_uv_pip(venv_python, "install", "somepkg", "--upgrade")

    assert captured == [
        [
            environment.uv_binary(),
            "pip",
            "install",
            "--python",
            os.fspath(venv_python),
            "somepkg",
            "--upgrade",
        ]
    ]


def test_install_into_venv_returns_false_and_logs_stderr_on_nonzero_returncode(
    monkeypatch, caplog
):
    """install_into_venv reports failure as False, never as an exception.

    Callers (repair_unsatisfied_import's verification loop) rely on a failed
    candidate being reported, not raised, so one bad candidate never ends the
    run. If the `result.returncode != 0` check were inverted or dropped, a
    failed uv install would be reported as a successful one -- exactly the
    shape of silent-success bug this module exists to catch live.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            args=command, returncode=1, stdout="", stderr="  boom happened  "
        ),
    )
    caplog.set_level(logging.INFO)

    result = environment.install_into_venv(Path("/fake/venv/bin/python"), "somepkg")

    assert result is False
    assert "Failed to install somepkg. Error: boom happened" in caplog.text


def test_uninstall_from_venv_warns_but_does_not_raise_on_nonzero_returncode(
    monkeypatch, caplog
):
    """uninstall_from_venv degrades to a warning on failure instead of raising.

    It runs from repair_unsatisfied_import's cleanup path, where an uninstall
    that fails must not crash the whole run. If the returncode check were
    removed, a failed uninstall would go unlogged; if it raised instead of
    warning, a routine cleanup failure would take down the caller.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            args=command, returncode=1, stdout="", stderr="  boom happened  "
        ),
    )
    caplog.set_level(logging.INFO)

    environment.uninstall_from_venv(
        Path("/fake/venv/bin/python"), "somepkg"
    )  # must not raise

    assert "Could not uninstall somepkg. Error: boom happened" in caplog.text
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("somepkg" in r.getMessage() for r in warning_records)


def test_parse_extra_requirements_handles_bare_names_specifiers_comments_blanks_and_whitespace(
    tmp_path,
):
    """parse_extra_requirements's regex extraction, measured against a real fixture file.

    A bare name gets an empty specifier, a name with a specifier keeps it
    verbatim, a '#' line and a blank line contribute nothing, and surrounding
    whitespace around a name/specifier pair is stripped. If the comment guard
    or the strip() calls regressed, a comment could be parsed as a package or
    a specifier could carry stray whitespace into the requirements file uv
    reads later.
    """
    fixture = tmp_path / "extra_requirements.txt"
    fixture.write_text(
        "requests\nflask>=2.0\n# a full-line comment\n\n  numpy  ==1.26.0  \n"
    )

    extra_requirements = environment.parse_extra_requirements(fixture, rawlog=True)

    assert extra_requirements == {
        "requests": "",
        "flask": ">=2.0",
        "numpy": "==1.26.0",
    }


def test_write_requirements_file_with_extras_sorts_pip_names_and_appends_specifiers_only_where_present(
    tmp_path,
):
    """write_requirements_file_with_extras: sorted, one per line, specifier only when non-empty.

    Includes a pip name absent from extra_requirements ("beta") and one
    present with an empty specifier ("zeta"), both of which must come out as
    a bare name -- if the "package in extra_requirements" guard were dropped,
    a KeyError would end the run for "beta"; if the empty-specifier check
    were dropped, "zeta" would get a stray trailing separator with nothing
    after it.
    """
    requirements_file = tmp_path / "requirements.txt"

    environment.write_requirements_file_with_extras(
        requirements_file,
        ["zeta", "alpha", "beta"],
        {"alpha": ">=1.0", "zeta": ""},
    )

    assert requirements_file.read_text() == "alpha>=1.0\nbeta\nzeta\n"


def test_venv_build_interpreter_falls_back_to_the_unresolved_command_and_warns_when_which_finds_nothing(
    monkeypatch, caplog
):
    """venv_build_interpreter degrades to the bare command, with a warning, when unresolvable.

    PROGRESS.md calls this branch untested and believed practically dead. If
    it instead raised, a `python_command` that shutil.which cannot resolve
    (a typo, a not-yet-installed interpreter) would crash veny outright
    instead of degrading -- to the behaviour that predates the resolved-path
    fix, still passing an unresolved name to uv.
    """
    monkeypatch.setattr(shutil, "which", lambda name: None)
    caplog.set_level(logging.WARNING)

    result = environment.venv_build_interpreter("definitely-not-a-real-interpreter-xyz")

    assert result == "definitely-not-a-real-interpreter-xyz"
    assert "Could not resolve interpreter" in caplog.text
