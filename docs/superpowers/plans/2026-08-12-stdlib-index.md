# StdlibIndex Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 935-line hardcoded standard-library `frozenset` in `veny.py` with a resolver that derives standard-library membership from an actual Python interpreter.

**Architecture:** A new leaf module `stdlib_index.py` owns one question — "is this import name part of the standard library of interpreter X?" — and answers it from `sys.stdlib_module_names`, either of the running interpreter or of the target interpreter probed via one subprocess. `veny.py` holds a `StdlibIndex` instance on `Options` and keeps all user-facing logging. The 29-name `known_bad_imports` set is split by owner: Python 2 names move into the resolver, `tkinter` becomes a system-package hint, and six project-specific names stay in `veny.py`.

**Tech Stack:** Python 3.12+ (`requires-python = ">=3.12,<3.14"`), pytest, ruff, mypy, pixi. No new runtime dependencies — veny is a bootstrapping tool and must run on a bare interpreter.

**Global Constraints:**
- `stdlib_index.py` MUST NOT import `veny` or `univ_defs`. The dependency direction is one-way.
- No third-party runtime dependency may be added. `stdlib_list` was explicitly rejected.
- `stdlib_index.py` classifies; it never logs about an individual import name. All per-import reporting stays in `veny.py`.
- The repository is a flat two-script layout (`veny.py`, `univ_defs.py` at the root), **not** the `src/` layout described in the global CLAUDE.md. New modules go at the repository root.
- Design doc: `docs/superpowers/specs/2026-08-12-stdlib-index-design.md`. Read it before Task 1.

**Pre-existing repository state (do NOT try to fix — out of scope):**
- `pixi run lint` reports **1171 ruff errors** in `veny.py` / `univ_defs.py`.
- `pixi run typecheck` reports **158 mypy errors** in the same two files.
- `.git/hooks/pre-commit` is not installed, so `git commit` does not run hooks.
- Therefore **repo-wide `ruff check .` / `mypy .` are NOT the gate.** Every task in this plan verifies with commands scoped to the files it touches. Do not "fix" unrelated pre-existing errors; that would bury the real diff.

**User decisions (already made):**
- Truth source: runner interpreter by default, probe the target when it differs. ("Runner + probe on mismatch")
- Scope: the stdlib list AND the `known_bad_imports` override migration — not the full `split_imports` pipeline.
- Placement: a new module `stdlib_index.py`, not `univ_defs.py` and not inline in `veny.py`.
- Probe failure policy: log a warning and degrade to the running interpreter. Never hard-fail.
- `seaborn` in `known_bad_imports` is stale — remove it.
- The six remaining project-specific names stay hardcoded in `veny.py`; no config file, no CLI flag.

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `stdlib_index.py` | The only place that answers "is this the standard library?". Owns the probe, the degradation policy, `PYTHON2_ONLY`, and `NEEDS_SYSTEM_PACKAGE`. Imports nothing from this repository. | Create (Task 1–3) |
| `tests/__init__.py` | Makes `tests` a package so pytest inserts the repository root on `sys.path`. | Create (Task 1) |
| `tests/test_stdlib_index.py` | Unit tests for the resolver. | Create (Task 1–3) |
| `tests/test_split_imports.py` | Unit tests for the extracted `_compute_bad_imports` helper. | Create (Task 5) |
| `pyproject.toml` | Add `"."` to `tool.pytest.ini_options.pythonpath` so root-level modules import in tests. | Modify (Task 1) |
| `veny.py` | Loses the 935-line literal; gains `options.stdlib`, the `resolve()` call, and the hint reporting. | Modify (Task 4–6) |
| `PROGRESS.md` | Running notebook — refresh the next-action line and gotchas. | Modify (Task 7) |

**Do not touch:** `is_standard_path` / `_is_std_path_cached` (`veny.py:6253`). Those classify filesystem *paths* during the custom-module walk, a different concern from import names. Conflating them is the most likely wrong turn in this plan.

---

### Task 1: StdlibIndex dataclass and running-interpreter source

**Goal:** Create `stdlib_index.py` with the frozen dataclass, first-component lookup, and the running-interpreter constructor, plus the test scaffolding the rest of the plan needs.

**Files:**
- Create: `stdlib_index.py`
- Create: `tests/__init__.py`
- Create: `tests/test_stdlib_index.py`
- Modify: `pyproject.toml` (the `[tool.pytest.ini_options]` block, currently `pythonpath = ["src"]`)

**Acceptance Criteria:**
- [ ] `"xml.etree.ElementTree"` is found in an index whose names are `{"xml"}`.
- [ ] `"osquery"` is NOT found in an index whose names are `{"os"}`.
- [ ] `"mypackage.os"` is NOT found in an index whose names are `{"os"}`.
- [ ] An empty import name is never standard library, even if `""` is in the names set.
- [ ] `for_running_interpreter()` contains `os` and `asyncio`, does not contain `numpy`, reports the running version, and reports `source == "running"`.
- [ ] `pytest` collects and runs `tests/test_stdlib_index.py` from the repository root.

**Verify:** `pixi run python -m pytest tests/test_stdlib_index.py -v` → 5 passed

**Steps:**

- [ ] **Step 1: Make the tests directory importable**

Create `tests/__init__.py` as an empty file.

Then edit `pyproject.toml` — the `[tool.pytest.ini_options]` block currently reads:

```toml
[tool.pytest.ini_options]
addopts = "-v"
pythonpath = ["src"]
```

Change it to:

```toml
[tool.pytest.ini_options]
addopts = "-v"
pythonpath = ["src", "."]  # "." because veny.py and stdlib_index.py live at the repository root, not under src/
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_stdlib_index.py`:

```python
import sys

import pytest

import stdlib_index
from stdlib_index import StdlibIndex


@pytest.fixture(autouse=True)
def clear_probe_cache():
    """Keep lru_cache state from leaking between tests (used from Task 2 onward)."""
    yield
    if hasattr(stdlib_index.for_interpreter, "cache_clear"):
        stdlib_index.for_interpreter.cache_clear()


def _index(*names):
    return StdlibIndex(names=frozenset(names), python_version=(3, 12), source="running")


def test_dotted_import_resolves_by_first_component():
    assert "xml.etree.ElementTree" in _index("xml")


def test_prefix_match_is_not_enough():
    assert "osquery" not in _index("os")


def test_last_component_is_not_used():
    assert "mypackage.os" not in _index("os")


def test_empty_import_name_is_never_stdlib():
    assert "" not in _index("os", "")


def test_running_interpreter_index_has_real_stdlib_contents():
    index = stdlib_index.for_running_interpreter()
    assert "os" in index
    assert "asyncio" in index
    assert "numpy" not in index
    assert index.python_version == (sys.version_info.major, sys.version_info.minor)
    assert index.source == "running"
```

The `clear_probe_cache` fixture references `for_interpreter`, which does not exist until Task 2 — the `hasattr` guard keeps it inert until then.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pixi run python -m pytest tests/test_stdlib_index.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'stdlib_index'`

- [ ] **Step 4: Write the minimal implementation**

Create `stdlib_index.py`:

```python
#!/usr/bin/env python3
"""Derive the standard-library module names of a given Python interpreter.

veny needs to know whether an import must be installed with pip. That is a
property of the interpreter which will run the user's script, so this module
asks an interpreter instead of carrying a hardcoded list. See
docs/superpowers/specs/2026-08-12-stdlib-index-design.md for the rationale.

This module deliberately imports nothing from veny or univ_defs, so it can be
tested on its own and so the dependency direction stays one-way.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Final

SOURCE_RUNNING:  Final[str] = "running"
SOURCE_PROBE:    Final[str] = "probe"
SOURCE_DEGRADED: Final[str] = "degraded"


@dataclass(frozen=True)
class StdlibIndex:
    """The standard-library module names of one Python interpreter.

    Attributes:
        names:          Top-level standard-library module names.
        python_version: The (major, minor) version the names came from.
        source:         One of SOURCE_RUNNING, SOURCE_PROBE, SOURCE_DEGRADED.
    """

    names:          frozenset[str]
    python_version: tuple[int, int]
    source:         str

    def __contains__(self, import_name: object) -> bool:
        """Return True if an import name resolves to the standard library.

        Only the first dotted component matters: "xml.etree.ElementTree" is
        standard library because "xml" is.

        Args:
            import_name: The import name as written in the source file.

        Returns:
            True if the name belongs to this interpreter's standard library.
        """
        if not isinstance(import_name, str) or not import_name:
            return False
        return import_name.partition(".")[0] in self.names


def for_running_interpreter() -> StdlibIndex:
    """Build an index from the interpreter that is running veny itself.

    Returns:
        A StdlibIndex tagged with SOURCE_RUNNING.
    """
    return StdlibIndex(names=frozenset(sys.stdlib_module_names),
                       python_version=(sys.version_info.major, sys.version_info.minor),
                       source=SOURCE_RUNNING)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pixi run python -m pytest tests/test_stdlib_index.py -v`
Expected: 5 passed

- [ ] **Step 6: Lint and type check the new files only**

Run: `pixi run python -m ruff check stdlib_index.py tests/`
Expected: `All checks passed!`

Run: `pixi run python -m mypy stdlib_index.py`
Expected: `Success: no issues found in 1 source file`

If ruff reports `D` (docstring) or `ANN` (annotation) findings, fix them in the new file. Do not run repo-wide lint — see the pre-existing-state note in the header.

- [ ] **Step 7: Commit**

```bash
git add stdlib_index.py tests/__init__.py tests/test_stdlib_index.py pyproject.toml
git commit -m "feat: add StdlibIndex with first-component lookup"
```

---

### Task 2: Probe the target interpreter, with degradation

**Goal:** Add `for_interpreter()` and `resolve()` so standard-library truth comes from the interpreter that will actually run the user's script, degrading safely when the probe fails.

**Files:**
- Modify: `stdlib_index.py` (append to the module created in Task 1)
- Modify: `tests/test_stdlib_index.py` (append tests)

**Acceptance Criteria:**
- [ ] `for_interpreter(sys.executable)` returns the same names as `for_running_interpreter()`, tagged `source == "probe"`.
- [ ] A missing interpreter path, a probe timeout, unparseable probe output, and a non-zero probe exit each return `source == "degraded"` with a usable (non-empty) name set, and raise nothing.
- [ ] `resolve(sys.executable)` returns `source == "running"` and spawns no subprocess.
- [ ] `resolve()` of a different interpreter probes exactly once and reports that interpreter's names and version, not the runner's.
- [ ] `resolve(None)` returns the running index.

**Verify:** `pixi run python -m pytest tests/test_stdlib_index.py -v` → 12 passed

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stdlib_index.py` (and extend the import block at the top of the file to `import json`, `import subprocess`, `from pathlib import Path`):

```python
def test_probe_of_own_interpreter_matches_running_index():
    probed = stdlib_index.for_interpreter(sys.executable)
    assert probed.names == stdlib_index.for_running_interpreter().names
    assert probed.python_version == (sys.version_info.major, sys.version_info.minor)
    assert probed.source == "probe"


def test_missing_interpreter_degrades():
    index = stdlib_index.resolve(Path("/nonexistent/python"))
    assert index.source == "degraded"
    assert "os" in index


def test_probe_timeout_degrades(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="python", timeout=10.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    index = stdlib_index.for_interpreter("/opt/wedged/python")
    assert index.source == "degraded"
    assert "os" in index


def test_probe_garbage_output_degrades(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0,
                                           stdout="Warning: banner\nnot json", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    index = stdlib_index.for_interpreter("/opt/chatty/python")
    assert index.source == "degraded"
    assert "os" in index


def test_probe_nonzero_exit_degrades(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="",
            stderr="AttributeError: module 'sys' has no attribute 'stdlib_module_names'")

    monkeypatch.setattr(subprocess, "run", fake_run)
    index = stdlib_index.for_interpreter("/opt/python3.9/bin/python")
    assert index.source == "degraded"
    assert "os" in index


def test_resolve_of_own_interpreter_spawns_no_subprocess(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("resolve() spawned a subprocess for the running interpreter")

    monkeypatch.setattr(subprocess, "run", explode)
    index = stdlib_index.resolve(sys.executable)
    assert index.source == "running"


def test_resolve_of_other_interpreter_uses_that_interpreters_truth(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        payload = json.dumps({"version": [3, 11], "names": ["os", "sys", "asynchat"]})
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=payload, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    index = stdlib_index.resolve("/opt/python3.11/bin/python")
    assert index.source == "probe"
    assert index.python_version == (3, 11)
    assert "asynchat" in index          # stdlib on 3.11, gone on 3.12 -- target truth wins
    assert len(calls) == 1


def test_resolve_of_none_uses_running_interpreter():
    assert stdlib_index.resolve(None).source == "running"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run python -m pytest tests/test_stdlib_index.py -v`
Expected: FAIL — `AttributeError: module 'stdlib_index' has no attribute 'for_interpreter'`

- [ ] **Step 3: Write the implementation**

Add these imports to the top of `stdlib_index.py`:

```python
import json
import logging
import os
import shutil
import subprocess
from functools import lru_cache
```

Then append to `stdlib_index.py`:

```python
_PROBE_TIMEOUT: Final[float] = 10.0

_PROBE_CODE: Final[str] = (
    "import sys, json; "
    "print(json.dumps({'version': list(sys.version_info[:2]), "
    "'names': sorted(sys.stdlib_module_names)}))"
)


def _degraded() -> StdlibIndex:
    """Build a usable index from the running interpreter, tagged as degraded.

    Returns:
        A StdlibIndex with the running interpreter's names and SOURCE_DEGRADED.
    """
    running = for_running_interpreter()
    return StdlibIndex(names=running.names,
                       python_version=running.python_version,
                       source=SOURCE_DEGRADED)


@lru_cache(maxsize=8)
def for_interpreter(python: str | os.PathLike[str],
                    timeout: float = _PROBE_TIMEOUT) -> StdlibIndex:
    """Probe another interpreter for its standard-library module names.

    Any failure -- missing executable, timeout, non-zero exit, unparseable
    output -- degrades to the running interpreter with a warning rather than
    raising, because veny's job is to keep the user's script running.

    Args:
        python:  Path or command name of the interpreter to probe.
        timeout: Seconds to wait for the probe before giving up.

    Returns:
        A StdlibIndex tagged SOURCE_PROBE on success, SOURCE_DEGRADED otherwise.
    """
    command = [os.fspath(python), "-c", _PROBE_CODE]
    try:
        result = subprocess.run(command, capture_output=True, text=True,  # noqa: S603
                                check=False, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        logging.warning("Could not run %s to list its standard library (%s); "
                        "using this interpreter's standard library instead.", python, exc)
        return _degraded()
    if result.returncode != 0:
        logging.warning("%s exited with %d while listing its standard library (%s); "
                        "using this interpreter's standard library instead.",
                        python, result.returncode, result.stderr.strip())
        return _degraded()
    try:
        payload = json.loads(result.stdout)
        names = frozenset(payload["names"])
        major, minor = payload["version"]
    except (ValueError, KeyError, TypeError) as exc:
        logging.warning("Could not read the standard library list from %s (%s); "
                        "using this interpreter's standard library instead.", python, exc)
        return _degraded()
    return StdlibIndex(names=names, python_version=(int(major), int(minor)),
                       source=SOURCE_PROBE)


def _is_running_interpreter(python: str | os.PathLike[str]) -> bool:
    """Return True if a path or command name refers to the interpreter running veny.

    Args:
        python: Path or command name such as "python3.12" or "/usr/bin/python3".

    Returns:
        True if it resolves to the same file as sys.executable.
    """
    located = shutil.which(os.fspath(python))
    if located is None:
        return False
    return os.path.realpath(located) == os.path.realpath(sys.executable)


def resolve(python: str | os.PathLike[str] | None) -> StdlibIndex:
    """Build the standard-library index for the interpreter that will run the script.

    Args:
        python: The target interpreter, or None if none has been chosen yet.

    Returns:
        The running interpreter's index when the target is absent or is the
        running interpreter, otherwise the probed target's index.
    """
    if python is None or _is_running_interpreter(python):
        return for_running_interpreter()
    return for_interpreter(os.fspath(python))
```

The `# noqa: S603` is required: ruff's bandit rules flag every `subprocess.run` with a non-literal argument list. The command is built from an interpreter path veny itself selected, not from user input.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run python -m pytest tests/test_stdlib_index.py -v`
Expected: 12 passed

- [ ] **Step 5: Lint and type check**

Run: `pixi run python -m ruff check stdlib_index.py tests/`
Expected: `All checks passed!`

Run: `pixi run python -m mypy stdlib_index.py`
Expected: `Success: no issues found in 1 source file`

- [ ] **Step 6: Commit**

```bash
git add stdlib_index.py tests/test_stdlib_index.py
git commit -m "feat: probe the target interpreter for stdlib names, degrade on failure"
```

---

### Task 3: Python 2 and system-package constants

**Goal:** Give the resolver the two small hand-maintained tables that replace the classification half of `known_bad_imports`, with invariant tests that catch typos in them.

**Files:**
- Modify: `stdlib_index.py`
- Modify: `tests/test_stdlib_index.py`

**Acceptance Criteria:**
- [ ] `PYTHON2_ONLY` holds exactly the 20 Python 2 names listed in the design doc and shares no name with the running interpreter's standard library.
- [ ] Every key of `NEEDS_SYSTEM_PACKAGE` is a real standard-library name on the running interpreter.
- [ ] `hints_for()` returns only the entries whose names were actually seen.

**Verify:** `pixi run python -m pytest tests/test_stdlib_index.py -v` → 15 passed

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stdlib_index.py`:

```python
def test_python2_only_names_are_not_python3_stdlib():
    overlap = stdlib_index.PYTHON2_ONLY & stdlib_index.for_running_interpreter().names
    assert overlap == frozenset()


def test_system_package_hint_keys_are_stdlib_names():
    running = stdlib_index.for_running_interpreter()
    for name in stdlib_index.NEEDS_SYSTEM_PACKAGE:
        assert name in running.names


def test_hints_for_returns_only_names_that_were_seen():
    assert stdlib_index.hints_for({"tkinter", "os"}) == {"tkinter": "python3-tk"}
    assert stdlib_index.hints_for({"os", "sys"}) == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run python -m pytest tests/test_stdlib_index.py -v`
Expected: FAIL — `AttributeError: module 'stdlib_index' has no attribute 'PYTHON2_ONLY'`

- [ ] **Step 3: Write the implementation**

Add `from collections.abc import Iterable` to the imports, then append to `stdlib_index.py`:

```python
# Python 2 standard-library names. They are not installable under any Python 3,
# so veny must never hand them to pip. This is a fact about Python, not about
# any one user's projects -- which is why it lives here and not in veny.py.
PYTHON2_ONLY: Final[frozenset[str]] = frozenset({
    "BaseHTTPServer", "ConfigParser", "Cookie", "HTMLParser", "Queue",
    "SocketServer", "StringIO", "Tkinter", "UserDict", "__builtin__",
    "cPickle", "cStringIO", "cookielib", "htmlentitydefs", "httplib",
    "tkFileDialog", "tkFont", "tkMessageBox", "urllib2", "urlparse",
})

# Standard-library modules that still need an operating-system package before
# they will import. They must NOT be pip-installed; the user needs a system
# package instead, so veny warns rather than blocking or installing.
NEEDS_SYSTEM_PACKAGE: Final[dict[str, str]] = {
    "tkinter": "python3-tk",
}


def hints_for(import_names: Iterable[str]) -> dict[str, str]:
    """Map the seen standard-library imports that need a system package to that package.

    Args:
        import_names: Import names that were skipped as standard library.

    Returns:
        A mapping of import name to the system package that provides it,
        containing only names that appear in import_names.
    """
    seen = set(import_names)
    return {name: package for name, package in NEEDS_SYSTEM_PACKAGE.items() if name in seen}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run python -m pytest tests/test_stdlib_index.py -v`
Expected: 15 passed

- [ ] **Step 5: Lint and type check**

Run: `pixi run python -m ruff check stdlib_index.py tests/`
Expected: `All checks passed!`

Run: `pixi run python -m mypy stdlib_index.py`
Expected: `Success: no issues found in 1 source file`

- [ ] **Step 6: Commit**

```bash
git add stdlib_index.py tests/test_stdlib_index.py
git commit -m "feat: add PYTHON2_ONLY and NEEDS_SYSTEM_PACKAGE tables"
```

---

### Task 4: Wire the resolver into veny.py and delete the hardcoded list

**Goal:** Replace `Options.standard_modules` with `options.stdlib` at all three call sites and delete the 935-line literal.

**Files:**
- Modify: `veny.py:23` (import block), `veny.py:125-1064` (delete), `veny.py:2410` (main), `veny.py:4323`, `veny.py:4985`, `veny.py:5047`, `veny.py:5181`, `veny.py:5418`

**Acceptance Criteria:**
- [ ] `rg "standard_modules" veny.py` returns nothing.
- [ ] `veny.py` is roughly 940 lines shorter.
- [ ] `import veny` still succeeds and `veny.Options().stdlib` contains `os` and `xml.etree.ElementTree` but not `numpy`.
- [ ] The equivalence check between the deleted list and the new index produces only explainable differences, recorded in the commit message.

**Verify:** `pixi run python -c "import veny; o = veny.Options(); print('os' in o.stdlib, 'xml.etree.ElementTree' in o.stdlib, 'numpy' in o.stdlib)"` → `True True False`

**Steps:**

- [ ] **Step 1: Record the equivalence check before deleting anything**

Run this from the repository root and keep the output — it goes in the commit message:

```bash
pixi run python - <<'EOF'
import ast, sys
src = open("veny.py").read().splitlines()
literal = "\n".join(src[129:1064]).split("=", 1)[1].strip()
literal = literal[len("frozenset("):-1]
old = {name.split(".")[0] for name in ast.literal_eval(literal)}
new = set(sys.stdlib_module_names)
print("old top-level:", len(old), "new:", len(new))
print("removed:", sorted(old - new))
print("added:", sorted(new - old))
EOF
```

Expected shape of the output (exact contents depend on the running Python version): about 53 removed names, all of them either modules deleted from the standard library in 3.12/3.13 (`asynchat`, `asyncore`, `binhex`, `cgi`, `distutils`, `imp`, `lib2to3`, `telnetlib`, …), CPython private test artifacts (`_testcapi`, `_xxtestfuzz`, `xxsubtype`, `__phello__`), conda build contamination (`_sysconfigdata_x86_64_conda_linux_gnu`, `lib`), or the two documented cases `__main__` and `test`; and about 23 added names including `tomllib`, `_pyrepl`, `_interpreters`, `_zoneinfo`.

If a removed name does NOT fall into one of those buckets, stop and report it — that would be a real behavior regression the design did not anticipate.

- [ ] **Step 2: Add the import**

`veny.py` line 23 currently reads:

```python
import univ_defs as ud
```

Replace with:

```python
import stdlib_index
import univ_defs as ud
```

- [ ] **Step 3: Delete the literal and add the attribute**

Delete `veny.py` lines 125 through 1064 — the five comment lines starting `# Keep a list of all python standard library modules.` through the closing `"zoneinfo._tzpath", "zoneinfo._zoneinfo"})`. In their place put:

```python
        # Standard-library membership is derived from a real interpreter, never hardcoded.
        # Replaced in main() once options.python_command is known, so that truth comes from
        # the interpreter that will actually run the user's script. See
        # docs/superpowers/specs/2026-08-12-stdlib-index-design.md
        self.stdlib: stdlib_index.StdlibIndex = stdlib_index.for_running_interpreter()
        self.seen_stdlib_imports:    set[str] = set()  # Standard-library imports that were skipped
```

Confirm the boundary: the line immediately before the deleted block is `        }` closing `self.also_needs`, and the line immediately after is `        # Sometimes, a module is imported in python using a different name than is required in the "pip install" command. Keep track of these exceptions here.`

- [ ] **Step 4: Resolve the target interpreter in main()**

`veny.py` around line 2410 currently reads:

```python
    options.python_command = ud.find_preferred_python_version()
    if options.python_command:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Python %s is available at: %s", ud.PY_VERSION, options.python_command)
    else:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Python %s is not available.", ud.PY_VERSION)
```

Append immediately after that `else` block:

```python
    options.stdlib = stdlib_index.resolve(options.python_command)
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug(
        "Standard library index: %d names from Python %d.%d (source: %s)",
        len(options.stdlib.names), options.stdlib.python_version[0],
        options.stdlib.python_version[1], options.stdlib.source)
```

- [ ] **Step 5: Update the three call sites**

`veny.py:4323`, inside `process_import`, currently:

```python
    if module_name in options.standard_modules:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Skipping standard library import: %s", module_name)
        return False
```

becomes:

```python
    if module_name in options.stdlib:
        options.seen_stdlib_imports.add(module_name)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Skipping standard library import: %s", module_name)
        return False
```

`veny.py:5047`, inside `_enqueue_top_level_imports`, currently:

```python
        if import_name in options.standard_modules:
            continue  # Skip standard modules
```

becomes:

```python
        if import_name in options.stdlib:
            options.seen_stdlib_imports.add(import_name)
            continue  # Skip standard modules
```

`veny.py:5181` currently:

```python
            if import_name in options.standard_modules or import_name in processed_used_imports:
                continue
```

becomes:

```python
            if import_name in options.stdlib:
                options.seen_stdlib_imports.add(import_name)
                continue
            if import_name in processed_used_imports:
                continue
```

- [ ] **Step 6: Update the two docstrings**

`veny.py:4985` currently reads:

```python
            - options.standard_modules: Set of standard library module names.
```

becomes:

```python
            - options.stdlib:           StdlibIndex of the target interpreter's standard library.
```

`veny.py:5418` currently reads:

```python
            - standard_modules:        Set of standard library modules to ignore.
```

becomes:

```python
            - stdlib:                  StdlibIndex used to skip standard library imports.
```

- [ ] **Step 7: Verify**

Run: `rg -n "standard_modules" veny.py`
Expected: no output

Run: `pixi run python -c "import veny; o = veny.Options(); print('os' in o.stdlib, 'xml.etree.ElementTree' in o.stdlib, 'numpy' in o.stdlib)"`
Expected: `True True False`

Run: `pixi run python -m pytest tests/ -v`
Expected: 15 passed

Run: `git diff --stat veny.py`
Expected: roughly 940 deletions, ~20 insertions

- [ ] **Step 8: Commit**

Paste the Step 1 output into the commit body:

```bash
git add veny.py
git commit -m "refactor: derive stdlib membership from the interpreter, not a literal

Deletes the 935-line Options.standard_modules frozenset (1785 entries,
copied from pipreqs in 2024) and replaces it with options.stdlib, a
StdlibIndex resolved from the target interpreter.

Equivalence check (old top-level names vs sys.stdlib_module_names):
<paste the removed/added lists from Step 1 here>"
```

---

### Task 5: Migrate known_bad_imports

**Goal:** Shrink `known_bad_imports` to the six project-specific names and move the Python 2 names into the resolver, behind a pure helper that can be tested without building a virtual environment.

**Files:**
- Modify: `veny.py:2287` (the `known_bad_imports` set), `veny.py:5355-5361` (`split_imports`)
- Create: `tests/test_split_imports.py`

**Acceptance Criteria:**
- [ ] `known_bad_imports` holds exactly six names: `snakeClass`, `GPUampcor`, `pathfinding_salvo_rework`, `DQN`, `bayesOpt`, `non_existent_module`.
- [ ] A Python 2 name such as `httplib` is still classified bad, now via `stdlib_index.PYTHON2_ONLY`.
- [ ] Leading-underscore imports are still classified bad.
- [ ] An ordinary third-party import such as `numpy` is not classified bad.
- [ ] `seaborn`, `tkinter`, and `msvcrt` are no longer in `known_bad_imports`.

**Verify:** `pixi run python -m pytest tests/test_split_imports.py -v` → 4 passed

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_split_imports.py`:

```python
import stdlib_index
import veny


def test_python2_name_is_classified_bad():
    bad = veny._compute_bad_imports({"httplib", "numpy"}, set(), stdlib_index.PYTHON2_ONLY)
    assert bad == {"httplib"}


def test_leading_underscore_name_is_classified_bad():
    bad = veny._compute_bad_imports({"_private_thing", "numpy"}, set(), frozenset())
    assert bad == {"_private_thing"}


def test_ordinary_import_is_not_classified_bad():
    bad = veny._compute_bad_imports({"numpy", "xarray"}, {"DQN"}, stdlib_index.PYTHON2_ONLY)
    assert bad == set()


def test_seaborn_tkinter_and_msvcrt_are_no_longer_blocked():
    blocked = veny.Options().known_bad_imports
    assert blocked == {"snakeClass", "GPUampcor", "pathfinding_salvo_rework",
                       "DQN", "bayesOpt", "non_existent_module"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run python -m pytest tests/test_split_imports.py -v`
Expected: FAIL — `AttributeError: module 'veny' has no attribute '_compute_bad_imports'`

- [ ] **Step 3: Shrink known_bad_imports**

`veny.py:2286-2287` currently reads (line 2287 is one very long line ending in a long trailing comment):

```python
        # Set of known bad imports that should be ignored.
        self.known_bad_imports: set[str] = {"__builtin__", "snakeClass", ... "non_existent_module"}  # ... A more general approach would involve importing stdlib_list ...
```

Replace both lines with:

```python
        # Project-specific module names that are not on PyPI and never will be. Python 2
        # names and system-package cases now live in stdlib_index.py instead.
        self.known_bad_imports: set[str] = {"snakeClass", "GPUampcor", "pathfinding_salvo_rework",
                                            "DQN", "bayesOpt", "non_existent_module"}
```

Also delete the now-orphaned ChatGPT link on the following line (`        # https://chatgpt.com/share/687000fd-be84-8006-a7f4-06af4b1e0eda`), which referred to the stdlib_list question this work has now answered.

- [ ] **Step 4: Extract the classification helper**

`veny.py:5355-5361` currently reads:

```python
def split_imports(options: Options) -> None:
    """Split imports into installed, uninstalled, and bad imports."""
    options.bad_imports = options.known_bad_imports.intersection(options.all_imports)
    options.bad_imports.update({imp for imp in options.all_imports if imp.startswith("_")})
    if options.bad_imports:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Identified bad imports: %s", options.bad_imports)
    options.all_imports = options.all_imports - options.bad_imports
```

Replace with:

```python
def _compute_bad_imports(all_imports: set[str], known_bad: set[str],
                         py2_only: frozenset[str]) -> set[str]:
    """Return the imports that must never be handed to pip.

    Args:
        all_imports: Every import name found in the analysed scripts.
        known_bad:   Project-specific names that are not on PyPI.
        py2_only:    Python 2 standard-library names, from stdlib_index.

    Returns:
        The subset of all_imports that pip must not be asked to install.
    """
    bad = (known_bad | py2_only) & all_imports
    bad.update({imp for imp in all_imports if imp.startswith("_")})
    return bad


def split_imports(options: Options) -> None:
    """Split imports into installed, uninstalled, and bad imports."""
    options.bad_imports = _compute_bad_imports(options.all_imports, options.known_bad_imports,
                                               stdlib_index.PYTHON2_ONLY)
    if options.bad_imports:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Identified bad imports: %s", options.bad_imports)
    options.all_imports = options.all_imports - options.bad_imports
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pixi run python -m pytest tests/ -v`
Expected: 19 passed

- [ ] **Step 6: Commit**

```bash
git add veny.py tests/test_split_imports.py
git commit -m "refactor: move Python 2 names out of known_bad_imports into stdlib_index"
```

---

### Task 6: Report system-package hints once

**Goal:** Preserve the warning that `tkinter` used to get from `known_bad_imports`, without warning per import occurrence.

**Files:**
- Modify: `veny.py:2504-2507` (the reporting block in `main`)
- Modify: `tests/test_split_imports.py`

**Acceptance Criteria:**
- [ ] When `tkinter` was skipped as standard library, exactly one warning names both `tkinter` and `python3-tk`.
- [ ] When no hint-carrying module was seen, no such warning is logged.

**Verify:** `pixi run python -m pytest tests/test_split_imports.py -v` → 6 passed

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_split_imports.py`:

```python
import logging


def test_tkinter_produces_one_system_package_warning(caplog):
    options = veny.Options()
    options.seen_stdlib_imports = {"tkinter", "os"}
    with caplog.at_level(logging.WARNING):
        veny.warn_about_system_packages(options)
    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 1
    assert "tkinter" in messages[0]
    assert "python3-tk" in messages[0]


def test_no_warning_when_no_hint_module_was_seen(caplog):
    options = veny.Options()
    options.seen_stdlib_imports = {"os", "sys"}
    with caplog.at_level(logging.WARNING):
        veny.warn_about_system_packages(options)
    assert caplog.records == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run python -m pytest tests/test_split_imports.py -v`
Expected: FAIL — `AttributeError: module 'veny' has no attribute 'warn_about_system_packages'`

- [ ] **Step 3: Write the implementation**

Add this function to `veny.py` immediately above `def split_imports(options: Options) -> None:`:

```python
def warn_about_system_packages(options: Options) -> None:
    """Warn once for each standard-library import that needs an operating-system package.

    Args:
        options: Options object; reads options.seen_stdlib_imports.
    """
    for name, system_package in stdlib_index.hints_for(options.seen_stdlib_imports).items():
        logging.warning("%s is in the standard library but needs the %s system package "
                        "before it will import.", name, system_package)
```

Then in `main`, `veny.py:2504-2507` currently reads:

```python
    if not options.rawlog:
        logging.info("Uninstalled imports: %s", options.uninstalled_imports)
        if options.bad_imports:
            logging.warning("Bad imports: %s", options.bad_imports)
```

Insert the call directly after the `bad_imports` warning:

```python
    if not options.rawlog:
        logging.info("Uninstalled imports: %s", options.uninstalled_imports)
        if options.bad_imports:
            logging.warning("Bad imports: %s", options.bad_imports)
        warn_about_system_packages(options)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run python -m pytest tests/ -v`
Expected: 21 passed

- [ ] **Step 5: Commit**

```bash
git add veny.py tests/test_split_imports.py
git commit -m "feat: warn once when a stdlib import needs a system package"
```

---

### Task 7: End-to-end smoke run and notebook update

**Goal:** Confirm the whole pipeline classifies a real script correctly, and leave `PROGRESS.md` accurate for the next session.

**Files:**
- Create: a throwaway script under the scratchpad directory (not committed)
- Modify: `PROGRESS.md`

**Acceptance Criteria:**
- [ ] On a script importing `os`, `xml.etree.ElementTree`, `httplib`, and `numpy`, veny skips the first two as standard library, reports `httplib` as a bad import, and lists `numpy` as an uninstalled import to install.
- [ ] The debug log shows the standard library index line with a name count and a source of `running`, `probe`, or `degraded`.
- [ ] `PROGRESS.md` names the completed work and the next action.

**Verify:** `pixi run python veny.py --debug --justprint /tmp/claude-1000/-workspace/*/scratchpad/smoke_imports.py 2>&1 | rg "Standard library index|Skipping standard library import|Bad imports|Uninstalled imports"`

**Steps:**

- [ ] **Step 1: Write the smoke script**

Write to the session scratchpad directory (path shown in the environment notes) as `smoke_imports.py`:

```python
import os
import xml.etree.ElementTree
import httplib
import numpy

print(os.name, xml.etree.ElementTree.__name__, httplib, numpy)
```

- [ ] **Step 2: Run veny against it**

Run: `pixi run python veny.py --debug --justprint <scratchpad>/smoke_imports.py`

Expected in the output:
- one line matching `Standard library index: <N> names from Python 3.<minor> (source: ...)` with N in the low 300s
- `Skipping standard library import: os` and `Skipping standard library import: xml.etree.ElementTree`
- `Bad imports: {'httplib'}`
- `numpy` present in the `Uninstalled imports:` set

If `numpy` is missing from the uninstalled set because the machine has no network access for the temporary virtual environment, that is acceptable — the standard library, bad-import, and index lines are the ones this task verifies. Note the network limitation in the PROGRESS.md gotchas if it occurs.

- [ ] **Step 3: Run the whole suite once more**

Run: `pixi run python -m pytest tests/ -v`
Expected: 21 passed

Run: `pixi run python -m ruff check stdlib_index.py tests/`
Expected: `All checks passed!`

Run: `pixi run python -m mypy stdlib_index.py`
Expected: `Success: no issues found in 1 source file`

- [ ] **Step 4: Update PROGRESS.md**

In the **Current work** section, replace the next-action line with:

```markdown
**Next action:** stdlib work is complete through Task 7. Pick the next
architectural problem in veny; candidates are recorded under Deferred items.
```

Add to **Gotchas**:

```markdown
- `pixi run lint` and `pixi run typecheck` fail repo-wide on pre-existing
  `veny.py` / `univ_defs.py` errors (1171 ruff, 158 mypy as of 2026-08-12).
  Verify new work with commands scoped to the files you touched.
- `.git/hooks/pre-commit` is not installed, so `git commit` does not run the
  hooks. Run `pixi run pre-commit run --files <paths>` by hand.
```

- [ ] **Step 5: Commit**

```bash
git add PROGRESS.md
git commit -m "docs: record stdlib_index completion and repo-wide lint state"
```

---

## Self-Review

**Spec coverage:** Design doc sections map to tasks as follows — component and API → Tasks 1–2; probe payload and degradation → Task 2; classification tables and the `known_bad_imports` migration → Tasks 3 and 5; the six `veny.py` changes → Tasks 4 and 6; behavior differences / equivalence check → Task 4 Step 1; test plan items 1–13 → Tasks 1–3, items 14–16 → Task 5; success criteria → Tasks 4 and 7. No spec section is unclaimed.

**Type consistency:** `StdlibIndex(names, python_version, source)` is constructed identically in Tasks 1, 2, and the tests. `for_interpreter`, `for_running_interpreter`, `resolve`, `hints_for`, `PYTHON2_ONLY`, and `NEEDS_SYSTEM_PACKAGE` keep the same names and signatures everywhere they appear. `options.stdlib` and `options.seen_stdlib_imports` are introduced in Task 4 Step 3 before every use in Tasks 4–6.

**One known cross-task dependency:** the `clear_probe_cache` fixture is written in Task 1 but only becomes active in Task 2, guarded by `hasattr`. That is deliberate, not a placeholder.
