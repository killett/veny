"""Tests for renaming a virtual environment in place."""

from pathlib import Path

from veny import cli as veny


def a_venv(root: Path, name: str) -> veny.Options:
    """Create a directory that looks enough like a venv for renaming."""
    options = veny.Options()
    venv_dir = root / name
    venv_dir.mkdir(parents=True, exist_ok=True)
    (venv_dir / "pyvenv.cfg").write_text(
        f"home = /usr/bin\ncommand = /usr/bin/python3.12 -m venv {venv_dir}\n"
    )
    (venv_dir / "download_packages.sh").write_text(
        f"#!/bin/sh\n{venv_dir}/bin/pip download -r {venv_dir}/requirements.txt\n"
    )
    options.set_venv_dir(venv_dir)
    return options


def test_rename_venv_moves_the_directory(tmp_path: Path) -> None:
    """A venv that keeps its 'failed-' name is never found by the cache search."""
    options = a_venv(tmp_path, "failed-myenv-py3.12-20260814-091500-numpy")
    veny.rename_venv(options, "myenv-py3.12-20260814-091500-numpy")
    assert (tmp_path / "myenv-py3.12-20260814-091500-numpy").is_dir()
    assert not (tmp_path / "failed-myenv-py3.12-20260814-091500-numpy").exists()
    assert options.venv_dir == tmp_path / "myenv-py3.12-20260814-091500-numpy"


def test_rename_venv_rewrites_the_recorded_paths(tmp_path: Path) -> None:
    """A renamed venv that still records its old path is broken, not merely slow."""
    options = a_venv(tmp_path, "failed-myenv-py3.12-20260814-091500-numpy")
    veny.rename_venv(options, "myenv-py3.12-20260814-091500-numpy")
    assert options.venv_dir is not None
    config = (options.venv_dir / "pyvenv.cfg").read_text()
    script = (options.venv_dir / "download_packages.sh").read_text()
    assert "failed-" not in config
    assert "failed-" not in script
    assert "myenv-py3.12-20260814-091500-numpy" in config
    assert "home = /usr/bin" in config


def test_rename_venv_to_the_same_name_is_a_no_op(tmp_path: Path) -> None:
    """Renaming a directory onto itself must not raise or lose the venv."""
    options = a_venv(tmp_path, "myenv-py3.12-20260814-091500-numpy")
    veny.rename_venv(options, "myenv-py3.12-20260814-091500-numpy")
    assert options.venv_dir is not None
    assert options.venv_dir.is_dir()
