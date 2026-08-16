"""Pin how veny locates the uv binary it drives its environment layer with."""

import shutil
import subprocess
import sys

import pytest

from veny import cli


def test_the_packaged_uv_is_preferred_over_the_one_on_path(monkeypatch):
    """The uv installed alongside veny wins; PATH is never consulted."""
    fake = type(sys)("uv")
    fake.find_uv_bin = lambda: "/packaged/uv"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uv", fake)
    monkeypatch.setattr(shutil, "which", lambda _name: "/on/path/uv")
    cli.uv_binary.cache_clear()

    assert cli.uv_binary() == "/packaged/uv"


def test_a_path_uv_is_used_when_the_package_is_missing(monkeypatch, caplog):
    """Without the package, PATH serves -- and veny says the version is unpinned."""
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: "/on/path/uv")
    cli.uv_binary.cache_clear()

    assert cli.uv_binary() == "/on/path/uv"
    assert "not pinned" in caplog.text


def test_no_uv_anywhere_exits_with_an_install_message(monkeypatch):
    """The failure names the command that fixes it, not just a traceback."""
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    cli.uv_binary.cache_clear()

    with pytest.raises(SystemExit) as caught:
        cli.uv_binary()
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
        cli,
        "run_uv_pip",
        lambda opts, *args: subprocess.CompletedProcess(args=list(args), returncode=0),
    )
    monkeypatch.setattr(cli, "verify_and_repair_imports", lambda opts: None)
    monkeypatch.setattr(cli, "check_packages_in_venv", lambda opts: True)
    monkeypatch.setattr(cli, "record_venv_state", lambda opts: None)

    assert cli.setup_virtualenv(options) is True

    assert options.venv_dir is not None
    assert (options.venv_dir / "requirements.txt").read_text() == "thing-pkg\n"
    assert (options.venv_dir / "bin" / "python").exists()
