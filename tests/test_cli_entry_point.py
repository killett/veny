"""Tests for veny's entry point, identity and retired alias flags."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import veny
from veny import cli

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_module(*args):
    """Run `python -m veny <args>` with src/ importable, capturing output."""
    env = {**os.environ, "PYTHONPATH": os.fspath(REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "veny", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_module_entry_point_reports_the_package_version():
    # Catches: __main__.py not wired to cli.main; prog left unset, which makes
    # argparse print "__main__.py 0.2.2"; the __init__.py literal drifting
    # from what the CLI reports.
    result = run_module("--version")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"veny {veny.__version__}"


def test_state_directory_ignores_argv0(monkeypatch, tmp_path):
    # Catches: restoring my_name = Path(sys.argv[0]).stem, which under
    # `python -m veny` yields "__main__" and moves every venv, log and pickle
    # veny owns from ~/veny to ~/__main__. No other test would notice: they
    # all build Options under pytest, where argv[0] is already arbitrary.
    monkeypatch.setenv("HOME", os.fspath(tmp_path))
    monkeypatch.setattr(sys, "argv", ["/tmp/anywhere/__main__.py"])

    options = cli.Options()

    assert options.my_name == "veny"
    assert options.my_dir == tmp_path / "veny"


@pytest.mark.parametrize(
    "argv_tail",
    [["--alias", "veny"], ["--manual"]],
    ids=["alias", "manual"],
)
def test_retired_alias_flags_are_rejected(argv_tail, monkeypatch):
    # Catches: a half-applied deletion that leaves the flags registered on the
    # parser while the functions behind them are gone -- an AttributeError at
    # the moment the flag is typed, rather than a clean argparse rejection.
    monkeypatch.setattr(sys, "argv", ["veny", *argv_tail])
    options = cli.Options()

    with pytest.raises(SystemExit) as excinfo:
        cli.parse_arguments(options)

    assert excinfo.value.code == 2
