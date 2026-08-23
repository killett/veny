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
    result = run_python("import sys; sys.modules['emmykit'] = None; import veny.cli")

    assert result.returncode != 0
    assert "emmykit" in result.stderr
    assert "pip install" in result.stderr
    assert "0.4.0" in result.stderr
    assert result.stdout == ""


def test_veny_imports_normally_when_emmykit_is_present():
    result = run_python("import veny.cli; import veny; print(veny.__version__)")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.2.2"


def test_veny_exits_with_an_upgrade_message_when_emmykit_is_too_old():
    # The guard compares ek.__version__ against a (0, 4, 0) floor, so a stub
    # reporting an older version reproduces the old-emmykit shape regardless
    # of which attributes it happens to carry. `Options` is included anyway
    # because a real 0.3.x emmykit would have it too.
    source = (
        "import sys, types\n"
        "stub = types.ModuleType('emmykit')\n"
        "stub.__version__ = '0.3.4'\n"
        "class Options:\n"
        "    pass\n"
        "stub.Options = Options\n"
        "sys.modules['emmykit'] = stub\n"
        "import veny.cli\n"
    )
    result = run_python(source)

    assert result.returncode != 0
    assert "0.4.0" in result.stderr
    assert "pip install" in result.stderr
    assert result.stdout == ""


def test_veny_exits_when_emmykit_reports_no_version():
    # Bug caught: a version guard that reads a missing __version__ as "fine".
    # veny cannot know what it is talking to, and the failure it would
    # otherwise hit is an AttributeError from inside a run.
    source = (
        "import sys, types\n"
        "stub = types.ModuleType('emmykit')\n"
        "class Options:\n"
        "    pass\n"
        "stub.Options = Options\n"
        "sys.modules['emmykit'] = stub\n"
        "import veny.cli\n"
    )
    result = run_python(source)

    assert result.returncode != 0
    assert "0.4.0" in result.stderr
    assert result.stdout == ""
