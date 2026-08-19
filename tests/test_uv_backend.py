"""Pin how veny locates the uv binary it drives its environment layer with."""

import shutil
import subprocess
import sys

import pytest

from veny import cache_search, cli, environment, verify


def test_the_packaged_uv_is_preferred_over_the_one_on_path(monkeypatch):
    """The uv installed alongside veny wins; PATH is never consulted."""
    fake = type(sys)("uv")
    fake.find_uv_bin = lambda: "/packaged/uv"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uv", fake)
    monkeypatch.setattr(shutil, "which", lambda _name: "/on/path/uv")
    environment.uv_binary.cache_clear()

    assert environment.uv_binary() == "/packaged/uv"


def test_a_path_uv_is_used_when_the_package_is_missing(monkeypatch, caplog):
    """Without the package, PATH serves -- and veny says the version is unpinned."""
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: "/on/path/uv")
    environment.uv_binary.cache_clear()

    assert environment.uv_binary() == "/on/path/uv"
    assert "not pinned" in caplog.text


def test_no_uv_anywhere_exits_with_an_install_message(monkeypatch):
    """The failure names the command that fixes it, not just a traceback."""
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    environment.uv_binary.cache_clear()

    with pytest.raises(SystemExit) as caught:
        environment.uv_binary()
    assert "uv tool install veny" in str(caught.value)


def test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt(
    monkeypatch, tmp_path
):
    """setup_virtualenv must not write requirements.txt into options.venv_dir
    until create_venv has already built the environment there.

    Options.set_venv_dir (called by setup_virtualenv before either
    write_requirements_file_with_extras or create_venv run) creates
    options.venv_dir with mkdir(exist_ok=True), so create_venv always sees a
    directory that already exists. `uv venv` tolerates an existing directory
    only while it is empty -- it refuses (CalledProcessError) once anything
    has been written into it. If write_requirements_file_with_extras ran
    before create_venv, as it used to, the requirements.txt it writes would
    make that directory non-empty and this test's call into the real
    `create_venv` (real `uv venv` subprocess, not stubbed) would raise instead
    of returning, failing this test. Only the parts of setup_virtualenv that
    would need the network or a probed venv interpreter (the actual package
    install, import verification/repair, and manifest recording) are stubbed.
    """
    options = cli.Options()
    options.my_dir = tmp_path
    options.uninstalled_imports = {
        cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")
    }
    monkeypatch.setattr(
        environment,
        "run_uv_pip",
        lambda venv_python, *args: subprocess.CompletedProcess(
            args=list(args), returncode=0
        ),
    )
    # verify_and_repair_imports now returns the final records instead of
    # writing them back onto options, so the no-op stub has to hand back what
    # it was given -- setup_virtualenv assigns the result.
    monkeypatch.setattr(
        verify,
        "verify_and_repair_imports",
        lambda *, uninstalled, **kwargs: frozenset(uninstalled),
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: True)
    # record_venv_state returns the (possibly renamed) venv directory now, and
    # setup_virtualenv feeds that return value straight to options.set_venv_dir.
    # A stub returning None would set_venv_dir(None) and mkdir a path built from
    # it, so the stub hands back the directory it was given.
    monkeypatch.setattr(
        cache_search, "record_venv_state", lambda venv_dir, **kwargs: venv_dir
    )

    assert cli.setup_virtualenv(options) is True

    assert options.venv_dir is not None
    assert (options.venv_dir / "requirements.txt").read_text() == "thing-pkg\n"
    assert (options.venv_dir / "bin" / "python").exists()


def test_setup_virtualenv_writes_the_extra_requirements_version_specifiers(
    monkeypatch, tmp_path
):
    """The specifiers parsed out of --reqs must reach the requirements.txt that
    setup_virtualenv writes, not just the argv `uv pip install -r` is given.

    Phase 3c task 2 turned an implicit `options.extra_requirements` read inside
    write_requirements_file_with_extras into an explicit argument at this call
    site, which created a mis-wiring nothing could see: task 5's differential
    pins `-r requirements.txt` in the uv argv but never that file's contents.

    Concrete bug this catches: pass `{}` (or any other mapping) instead of
    `options.extra_requirements` here and requirements.txt reads a bare
    `thing-pkg`. uv then resolves whatever the newest release is, silently
    discarding the `thing-pkg>=2.0` pin the user wrote in their requirements
    file -- the one thing --reqs exists to honour. The expected text comes from
    write_requirements_file_with_extras' contract (sorted pip names, one per
    line, a specifier appended only where extra_requirements supplies a
    non-empty one), not from re-running the writer.
    """
    options = cli.Options()
    options.my_dir = tmp_path
    options.uninstalled_imports = {
        cli.ResolvedImport(import_name="thing", pip_name="thing-pkg"),
        cli.ResolvedImport(import_name="zeta", pip_name="zeta-pkg"),
    }
    options.extra_requirements = {"thing-pkg": ">=2.0"}
    # The venv itself is a subprocess boundary and is not what this test is
    # about; set_venv_dir has already created the directory the file lands in.
    monkeypatch.setattr(environment, "create_venv", lambda target, python="": None)
    monkeypatch.setattr(
        environment,
        "run_uv_pip",
        lambda venv_python, *args: subprocess.CompletedProcess(
            args=list(args), returncode=0
        ),
    )
    # verify_and_repair_imports now returns the final records instead of
    # writing them back onto options, so the no-op stub has to hand back what
    # it was given -- setup_virtualenv assigns the result.
    monkeypatch.setattr(
        verify,
        "verify_and_repair_imports",
        lambda *, uninstalled, **kwargs: frozenset(uninstalled),
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: True)
    # record_venv_state returns the (possibly renamed) venv directory now, and
    # setup_virtualenv feeds that return value straight to options.set_venv_dir.
    # A stub returning None would set_venv_dir(None) and mkdir a path built from
    # it, so the stub hands back the directory it was given.
    monkeypatch.setattr(
        cache_search, "record_venv_state", lambda venv_dir, **kwargs: venv_dir
    )

    cli.setup_virtualenv(options)

    assert options.venv_dir is not None
    assert (
        options.venv_dir / "requirements.txt"
    ).read_text() == "thing-pkg>=2.0\nzeta-pkg\n"


def test_create_venv_is_given_a_resolved_interpreter_path_not_a_bare_command(
    monkeypatch, tmp_path
):
    """venv_build_interpreter's result, as create_venv passes it to uv, must be
    an absolute path -- never a bare command name like "python3".

    `uv venv --python python3` does not mean "the python3 on PATH": uv treats a
    bare name as a request and resolves it through its own interpreter
    discovery order, which was measured (with no veny involved) to pick a
    different Python (3.12) than the one `python3 -m venv` -- what veny did
    before the uv migration -- used to build with (3.13). That silently builds
    the venv against a different interpreter than the one imports were
    classified against. If venv_build_interpreter regressed to returning
    options.python_command unresolved, this test would see the bare "python3"
    in the captured uv command instead of the absolute path shutil.which
    resolves it to.
    """
    options = cli.Options()
    options.python_command = "python3"
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/resolved/bin/python3" if name == "python3" else None,
    )
    monkeypatch.setattr(environment, "uv_binary", lambda: "/packaged/uv")
    captured: list[list[str]] = []
    monkeypatch.setattr(
        subprocess, "check_call", lambda command: captured.append(command)
    )

    python = environment.venv_build_interpreter(options.python_command)
    environment.create_venv(tmp_path / "target", python)

    assert captured == [
        [
            "/packaged/uv",
            "venv",
            str(tmp_path / "target"),
            "--python",
            "/resolved/bin/python3",
        ]
    ]
