"""Tests for renaming a virtual environment in place."""

from pathlib import Path

from veny import cli as veny


def a_venv(root: Path, name: str) -> veny.Options:
    """Create a directory that looks enough like a venv for renaming.

    The pyvenv.cfg is deliberately stdlib-shaped (a `command = ... -m venv
    <dir>` line naming the venv's own directory) rather than uv-shaped: uv
    never writes such a line, so a uv-built venv's pyvenv.cfg has nothing for
    rename_venv to rewrite. `~/veny/` on a real machine still holds venvs the
    stdlib `venv` module built before the uv migration, and this fixture
    stands in for those.
    """
    options = veny.Options()
    venv_dir = root / name
    venv_dir.mkdir(parents=True, exist_ok=True)
    (venv_dir / "pyvenv.cfg").write_text(
        f"home = /usr/bin\ncommand = /usr/bin/python3.12 -m venv {venv_dir}\n"
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
    """A renamed venv that still records its old path is broken, not merely slow.

    The fixture's pyvenv.cfg is stdlib-shaped because uv-built venvs carry no
    path in pyvenv.cfg at all -- this test covers the pre-migration venvs
    still sitting in the cache, not anything a uv-built venv would trigger.
    """
    options = a_venv(tmp_path, "failed-myenv-py3.12-20260814-091500-numpy")
    veny.rename_venv(options, "myenv-py3.12-20260814-091500-numpy")
    assert options.venv_dir is not None
    config = (options.venv_dir / "pyvenv.cfg").read_text()
    assert "failed-" not in config
    assert "myenv-py3.12-20260814-091500-numpy" in config
    assert "home = /usr/bin" in config


def test_rename_venv_to_the_same_name_is_a_no_op(tmp_path: Path) -> None:
    """Renaming a directory onto itself must not raise or lose the venv."""
    options = a_venv(tmp_path, "myenv-py3.12-20260814-091500-numpy")
    veny.rename_venv(options, "myenv-py3.12-20260814-091500-numpy")
    assert options.venv_dir is not None
    assert options.venv_dir.is_dir()
