"""Tests for veny's behaviour when its emmykit dependency is missing."""

import subprocess
import sys
from pathlib import Path

import veny

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
    # Bug caught: either half of the message naming a floor other than the
    # one veny enforces -- an install hint left at an old floor installs an
    # emmykit veny then refuses. 0.7.0 is pyproject.toml's own
    # `emmykit>=0.7.0`; the message is asserted whole because the floor
    # appears in it twice and a substring check passes with one copy wrong.
    result = run_python("import sys; sys.modules['emmykit'] = None; import veny.cli")

    assert result.returncode != 0
    assert result.stderr == (
        "veny requires the emmykit package (>=0.7.0), which is not installed.\n"
        "Install it with:  pip install 'emmykit>=0.7.0'\n"
    )
    assert result.stdout == ""


def test_veny_imports_normally_when_emmykit_is_present():
    # Compared against the version this process imported rather than a
    # literal: src/veny/__init__.py is the only place the number lives
    # (RELEASING.md), so a literal here turned red on every release bump.
    result = run_python("import veny.cli; import veny; print(veny.__version__)")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == veny.__version__


def test_veny_exits_with_an_upgrade_message_when_emmykit_is_too_old():
    # The guard compares ek.__version__ against a (0, 7, 0) floor, so a stub
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
    # Whole message, for the reason given in the missing-emmykit test above.
    assert result.stderr == (
        "veny requires emmykit >= 0.7.0; found 0.3.4.\n"
        "Upgrade it with:  pip install -U 'emmykit>=0.7.0'\n"
    )
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
    assert result.stderr == (
        "veny requires emmykit >= 0.7.0; found unknown.\n"
        "Upgrade it with:  pip install -U 'emmykit>=0.7.0'\n"
    )
    assert result.stdout == ""


def test_veny_refuses_an_emmykit_without_find_python():
    # Bug caught: a floor left below 0.7.0. emmykit 0.6.x passed the old 0.4.0
    # guard, but it has no find_python, which pipeline.run calls on every run,
    # so veny would get as far as a run and die there with an AttributeError.
    source = (
        "import sys, types\n"
        "stub = types.ModuleType('emmykit')\n"
        "stub.__version__ = '0.6.3'\n"
        "sys.modules['emmykit'] = stub\n"
        "import veny.cli\n"
    )
    result = run_python(source)

    assert result.returncode != 0
    assert result.stderr == (
        "veny requires emmykit >= 0.7.0; found 0.6.3.\n"
        "Upgrade it with:  pip install -U 'emmykit>=0.7.0'\n"
    )
    assert result.stdout == ""
