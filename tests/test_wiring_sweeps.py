"""The wiring sweeps must never leave a mutation in the repository they measure."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
MODULES = ("cli", "pipeline", "state", "last_used", "cache_search")


def _load_sweep(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _a_repository(root):
    """A stand-in for the repository: the files a sweep reads and copies."""
    for module in MODULES:
        path = root / "src" / "veny" / f"{module}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# the real {module}.py\n")
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("")
    (root / "scripts").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'stand-in'\n")


@pytest.mark.parametrize(
    "name", ["wiring_sweep_4a", "wiring_sweep_4b", "wiring_sweep_4c"]
)
def test_a_sweep_never_mutates_the_repository_it_measures(name, tmp_path, monkeypatch):
    """While the suite runs against a mutation, the repository's own file is untouched.

    Concrete bug this catches: each sweep wrote its mutation into the real
    src/ and restored it in a `finally`. A run killed mid-sweep -- SIGKILL, a
    dead session -- never reaches the `finally`, and leaves the mutation in
    the working tree, where the suite stays green by construction for every
    OPEN HOLE and the next commit carries it.

    Everything outside the boundary is the sweep's real main(); only the site
    list, the mutation and the subprocess calls are stand-ins. The stand-in
    for the test run records what the repository holds at that moment -- the
    moment a kill would freeze.
    """
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sweep = _load_sweep(name)
    repository = tmp_path / "repository"
    _a_repository(repository)
    site = {
        "file": "src/veny/pipeline.py",
        "line": 1,
        "call": "f",
        "arg": "x",
        "expr": "x",
        "sub": "None",
    }
    monkeypatch.setattr(sweep, "REPO", repository)
    monkeypatch.setattr(sweep, "OUT", tmp_path)
    monkeypatch.setattr(sweep, "collect", lambda: [dict(site)])
    monkeypatch.setattr(sweep, "apply", lambda site, original: "# MUTATED\n")
    monkeypatch.setattr(sys, "argv", [name])
    held_during_runs: list[str] = []

    def a_green_run(command, *args, **kwargs):
        held_during_runs.append((repository / site["file"]).read_text())
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(sweep.subprocess, "run", a_green_run)

    sweep.main()

    assert held_during_runs, "the sweep never reached its test run"
    assert set(held_during_runs) == {"# the real pipeline.py\n"}
