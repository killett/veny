"""Tests for veny's behaviour when its emmykit dependency is missing."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_python(source):
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_veny_exits_with_an_install_message_when_emmykit_is_missing():
    result = run_python("import sys; sys.modules['emmykit'] = None; import veny")

    assert result.returncode != 0
    assert "emmykit" in result.stderr
    assert "pip install" in result.stderr
    assert "Traceback" not in result.stdout


def test_veny_imports_normally_when_emmykit_is_present():
    result = run_python("import veny; print(veny.__version__)")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.2.2"
