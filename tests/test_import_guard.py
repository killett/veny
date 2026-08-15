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
    # A pre-0.4.0 emmykit satisfies every plain `import`/attribute access
    # veny.py performs before its own version check -- register_json_type is
    # the only symbol that is new in 0.4.0 -- so the stub only needs to omit
    # that one attribute to reproduce the old-emmykit shape. `Options` is
    # included anyway because veny.py subclasses it later in the module; a
    # real 0.3.x emmykit would have it too.
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
