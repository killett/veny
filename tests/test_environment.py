"""Characterize the uv boundary before Task 2 moves it into environment.py.

PROGRESS.md records three phase-2 regressions that shipped past a green,
264-test suite because every test in it stubbed the ``uv`` subprocess -- none
exercised the command lines veny actually builds. This module's live test
(below) drives the real ``uv`` binary against a real venv and a hand-built
wheel, with no network and no ``subprocess`` stubbing, so a broken argv or a
broken success/failure interpretation fails loudly here instead of shipping.

Every symbol under test is imported from ``veny.cli``, where it lives today;
Task 2 repoints these tests at ``veny.environment`` mechanically. This file
does not duplicate what tests/test_uv_backend.py already pins: uv_binary's
three resolution outcomes, the resolved-interpreter argv create_venv builds,
and the create_venv-before-requirements ordering.
"""

import logging
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from veny import cli


def _build_wheel(
    directory: Path, *, name: str = "venytest", version: str = "0.1", value: int = 42
) -> Path:
    """Build a minimal, real, installable wheel entirely from scratch.

    A plain zip carrying ``<name>/__init__.py`` plus a
    ``<name>-<version>.dist-info/`` with METADATA, WHEEL and RECORD -- the
    format verified (2026-08-18, while planning this task) to install through
    real ``uv pip install`` with no --no-index/--offline flag and no network.
    """
    staging = directory / "wheel-staging"
    pkg_dir = staging / name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text(f"value = {value}\n")

    dist_info = staging / f"{name}-{version}.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    )
    (dist_info / "WHEEL").write_text(
        "Wheel-Version: 1.0\nGenerator: test_environment\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    (dist_info / "RECORD").write_text("")

    wheel_path = directory / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging))
    return wheel_path


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
    cli.create_venv(venv_dir, python)

    wheel_path = _build_wheel(tmp_path)

    options = cli.Options()
    options.venv_python = venv_dir / "bin" / "python"

    installed = cli.install_into_venv(options, str(wheel_path))
    assert installed is True

    import_after_install = subprocess.run(
        [str(options.venv_python), "-c", "import venytest; print(venytest.value)"],
        capture_output=True,
        text=True,
    )
    assert import_after_install.returncode == 0
    assert import_after_install.stdout.strip() == "42"

    cli.uninstall_from_venv(options, "venytest")

    import_after_uninstall = subprocess.run(
        [str(options.venv_python), "-c", "import venytest"],
        capture_output=True,
        text=True,
    )
    assert import_after_uninstall.returncode != 0
    assert "ModuleNotFoundError" in import_after_uninstall.stderr


def test_run_uv_pip_returns_none_and_never_touches_subprocess_without_a_venv_interpreter(
    monkeypatch, caplog
):
    """run_uv_pip short-circuits to None, logging rather than raising or shelling out.

    If the `options.venv_python is None` guard were removed or reordered
    after the command is built, this would either raise (os.fspath(None)) or
    spawn a subprocess with a garbage path. Asserting subprocess.run is never
    called catches a reordering that a return-value-only assertion would miss.
    """

    def _fail_if_called(*args, **kwargs):
        raise AssertionError(
            "subprocess.run must not be invoked with no venv interpreter"
        )

    monkeypatch.setattr(subprocess, "run", _fail_if_called)
    caplog.set_level(logging.INFO)

    options = cli.Options()
    options.venv_python = None

    result = cli.run_uv_pip(options, "install", "somepkg")

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

    options = cli.Options()
    options.venv_python = Path("/fake/venv/bin/python")

    cli.run_uv_pip(options, "install", "somepkg", "--upgrade")

    assert captured == [
        [
            cli.uv_binary(),
            "pip",
            "install",
            "--python",
            os.fspath(options.venv_python),
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

    options = cli.Options()
    options.venv_python = Path("/fake/venv/bin/python")

    result = cli.install_into_venv(options, "somepkg")

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

    options = cli.Options()
    options.venv_python = Path("/fake/venv/bin/python")

    cli.uninstall_from_venv(options, "somepkg")  # must not raise

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

    options = cli.Options()
    options.extra_requirements_file = fixture
    options.rawlog = True

    cli.parse_extra_requirements(options)

    assert options.extra_requirements == {
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

    options = cli.Options()
    options.requirements_file = requirements_file
    options.uninstalled_imports = {
        cli.ResolvedImport(import_name="a_import", pip_name="alpha"),
        cli.ResolvedImport(import_name="b_import", pip_name="beta"),
        cli.ResolvedImport(import_name="z_import", pip_name="zeta"),
    }
    options.extra_requirements = {"alpha": ">=1.0", "zeta": ""}

    cli.write_requirements_file_with_extras(options)

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

    options = cli.Options()
    options.python_command = "definitely-not-a-real-interpreter-xyz"

    result = cli.venv_build_interpreter(options)

    assert result == "definitely-not-a-real-interpreter-xyz"
    assert "Could not resolve interpreter" in caplog.text
