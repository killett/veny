"""Tests for renaming a virtual environment in place."""

from pathlib import Path

from veny import cache_search, state


def a_venv(root: Path, name: str) -> Path:
    """Create a directory that looks enough like a venv for renaming.

    The pyvenv.cfg is deliberately stdlib-shaped (a `command = ... -m venv
    <dir>` line naming the venv's own directory) rather than uv-shaped: uv
    never writes such a line, so a uv-built venv's pyvenv.cfg has nothing for
    rename_venv to rewrite. `~/veny/` on a real machine still holds venvs the
    stdlib `venv` module built before the uv migration, and this fixture
    stands in for those.
    """
    venv_dir = root / name
    venv_dir.mkdir(parents=True, exist_ok=True)
    (venv_dir / "pyvenv.cfg").write_text(
        f"home = /usr/bin\ncommand = /usr/bin/python3.12 -m venv {venv_dir}\n"
    )
    return venv_dir


def test_rename_venv_moves_the_directory(tmp_path: Path) -> None:
    """A venv that keeps its 'failed-' name is never found by the cache search."""
    venv_dir = a_venv(tmp_path, "failed-myenv-py3.12-20260814-091500-numpy")
    moved = cache_search.rename_venv(venv_dir, "myenv-py3.12-20260814-091500-numpy")
    assert (tmp_path / "myenv-py3.12-20260814-091500-numpy").is_dir()
    assert not (tmp_path / "failed-myenv-py3.12-20260814-091500-numpy").exists()
    assert moved == tmp_path / "myenv-py3.12-20260814-091500-numpy"


def test_rename_venv_returns_the_directory_the_caller_must_record(
    tmp_path: Path,
) -> None:
    """rename_venv writes nothing; its return value is the only record.

    Concrete bug this catches: `return old_dir` (or returning the argument
    unchanged) instead of the moved directory. Every assertion in
    test_rename_venv_moves_the_directory about the *disk* still holds under
    that mutation -- the directory really did move -- so only following the
    return value into the caller's own VenvHandle can tell them apart.
    VenvHandle.for_dir mkdirs whatever it is handed (as set_venv_dir did
    before phase 4a), so a stale return value does not merely mislabel the
    venv: it resurrects the "failed-" directory as an empty one, which the
    cache search would then read as a real venv.
    """
    venv_dir = a_venv(tmp_path, "failed-myenv-py3.12-20260814-091500-numpy")
    moved = cache_search.rename_venv(venv_dir, "myenv-py3.12-20260814-091500-numpy")

    handle = state.VenvHandle.for_dir(moved)

    assert handle.venv_dir == tmp_path / "myenv-py3.12-20260814-091500-numpy"
    assert not (tmp_path / "failed-myenv-py3.12-20260814-091500-numpy").exists()
    assert (handle.venv_dir / "pyvenv.cfg").is_file()


def test_rename_venv_rewrites_the_recorded_paths(tmp_path: Path) -> None:
    """A renamed venv that still records its old path is broken, not merely slow.

    The fixture's pyvenv.cfg is stdlib-shaped because uv-built venvs carry no
    path in pyvenv.cfg at all -- this test covers the pre-migration venvs
    still sitting in the cache, not anything a uv-built venv would trigger.
    """
    venv_dir = a_venv(tmp_path, "failed-myenv-py3.12-20260814-091500-numpy")
    moved = cache_search.rename_venv(venv_dir, "myenv-py3.12-20260814-091500-numpy")
    config = (moved / "pyvenv.cfg").read_text()
    assert "failed-" not in config
    assert "myenv-py3.12-20260814-091500-numpy" in config
    assert "home = /usr/bin" in config


def test_rename_venv_to_the_same_name_is_a_no_op(tmp_path: Path) -> None:
    """Renaming a directory onto itself must not raise or lose the venv."""
    venv_dir = a_venv(tmp_path, "myenv-py3.12-20260814-091500-numpy")
    moved = cache_search.rename_venv(venv_dir, "myenv-py3.12-20260814-091500-numpy")
    assert moved == venv_dir
    assert moved.is_dir()
