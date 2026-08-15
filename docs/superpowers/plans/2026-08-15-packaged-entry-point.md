# Packaged Console-Script Entry Point Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace veny's rc-file shell alias with a packaged `veny` console-script entry point, moving the repository to a `src/veny/` package.

**Architecture:** The six flat root modules move into `src/veny/` with `git mv`, `veny.py` becoming `cli.py` verbatim. The alias installer and its four shell dialects are deleted. `pyproject.toml` gains a hatchling `[build-system]` and `[project.scripts] veny = "veny.cli:main"`, so the launcher is written onto PATH by `uv tool install` / `pipx` with a satisfying interpreter and emmykit resolved.

**Tech Stack:** Python 3.12–3.13, hatchling, pixi, pytest, ruff, mypy, `python -m build`, `uv tool` / `pipx` (consumer side).

**Global Constraints:**
- The move is **behaviour-preserving**. `pixi run test` is 252 passed before and after (plus new tests). `ruff check src/veny/cli.py --statistics` is 299 or fewer (was 299 for `veny.py`); `mypy src/veny/cli.py src/veny/json_types.py` is 28 or fewer. An *increase* in either means the move introduced something.
- **No formatter may touch `cli.py`.** Its hand-aligned columns were once rewritten across ~2,000 lines by `ruff-format`. Never run pre-commit's `ruff` or `ruff-format` hooks against it; Task 1 adds an `exclude` so it cannot happen by accident.
- `pixi run lint` and `pixi run typecheck` **cannot pass** repo-wide — the pre-commit `mypy` hook is `mypy .` with `pass_filenames: false` and the repo carries 28 pre-existing errors. Always scope gates to the files touched.
- Never `git checkout <sha>` or `git stash` in this working tree; use `git worktree add` on a side path for any baseline comparison.
- `json_types.register_types()` stays at **module scope** in `cli.py`, never inside `main()`.
- Commit after every task. `.git/hooks/pre-commit` is not installed, so run `pixi run pre-commit run --files <paths>` by hand.

**User decisions (already made):**
- "PyPI is the goal" — veny becomes an installable distribution, not a personal script.
- "Full packaging now" — do the `src/veny/` move, the `[build-system]`, and the alias deletion as one coherent piece of work rather than an interim symlink installer.
- "Move whole, rename to cli.py" — `veny.py` moves verbatim; splitting its 5,101 lines is explicitly *not* part of this plan.
- "README note only" for the leftover rc-file alias — no `--doctor`, no rc-file parsing, nothing that keeps the shell-dialect code alive.
- The emmykit follow-up prompt must include a pasteable `fd` command so usage can be searched **outside** both repositories, not just inside emmykit.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `src/veny/__init__.py` | **Create.** The `__version__` literal and nothing else. No imports, so importing the package cannot trigger the emmykit guard. |
| `src/veny/__main__.py` | **Create.** `python -m veny` → `cli.main()`. |
| `src/veny/cli.py` | **Move** from `veny.py`. Argument parsing, import analysis, venv orchestration. Minus the alias installer. |
| `src/veny/alias_index.py` | **Move.** Import-name → pip-name resolution. Only its `pypi_client` import changes. |
| `src/veny/pypi_client.py` | **Move.** Unchanged; imports nothing of veny's. |
| `src/veny/stdlib_index.py` | **Move.** Unchanged. |
| `src/veny/venv_cache.py` | **Move.** Unchanged. |
| `src/veny/json_types.py` | **Move** from `veny_json_types.py`. The `veny_` prefix existed only to disambiguate a top-level name. |
| `tests/test_cli_entry_point.py` | **Create.** The three new tests covering the new surface. |
| `scripts/smoke-install.sh` | **Create.** Builds the wheel, installs it into a throwaway venv, proves the console script and exit-code propagation. |
| `pyproject.toml` | **Modify.** `[build-system]`, `[project.scripts]`, dynamic version, pytest/coverage paths. |
| `pixi.toml` | **Modify.** `veny` and `smoke` tasks. |
| `.pre-commit-config.yaml` | **Modify.** Exclude `src/veny/cli.py` from the two ruff hooks. |
| `README.md` | **Modify.** Installation, upgrade-from-alias note, project structure. |
| `PROGRESS.md` | **Modify.** Gate paths, layout gotcha, formatter gotcha. |
| `docs/prompts/2026-08-15-emmykit-shell-alias-helpers-audit.md` | **Create.** Cross-repo usage audit prompt. |

---

### Task 1: Move the modules into `src/veny/`

**Goal:** The six root modules live in `src/veny/` as an importable package, with `__init__.py` and `__main__.py`, and the whole existing test suite passes unchanged in behaviour.

**Files:**
- Create: `src/veny/__init__.py`, `src/veny/__main__.py`
- Move: `veny.py` → `src/veny/cli.py`; `alias_index.py`, `pypi_client.py`, `stdlib_index.py`, `venv_cache.py` → `src/veny/`; `veny_json_types.py` → `src/veny/json_types.py`
- Modify: `src/veny/cli.py` (import lines only), `src/veny/alias_index.py:32`, `src/veny/json_types.py:21-22`
- Modify: `tests/test_alias_index.py`, `tests/test_cache_search.py`, `tests/test_import_guard.py`, `tests/test_json_types.py`, `tests/test_manifest_writing.py`, `tests/test_options_surface.py`, `tests/test_rename_venv.py`, `tests/test_split_imports.py`, `tests/test_stdlib_index.py`, `tests/test_venv_cache.py`, `tests/test_venv_naming.py`
- Modify: `pyproject.toml` (pytest `pythonpath`), `.pre-commit-config.yaml`

**Acceptance Criteria:**
- [ ] No `.py` file for veny remains at the repository root
- [ ] `pixi run test` reports 252 passed
- [ ] `ruff check src/veny/cli.py --statistics` totals 299 or fewer findings
- [ ] `mypy src/veny/cli.py src/veny/json_types.py` reports 28 or fewer errors
- [ ] `git log --follow src/veny/cli.py` shows the pre-move history
- [ ] The `ruff` and `ruff-format` pre-commit hooks skip `src/veny/cli.py`

**Verify:** `pixi run test` → `252 passed`

**Steps:**

- [ ] **Step 1: Record the three baselines before touching anything**

```bash
pixi run test 2>&1 | tail -1
ruff check veny.py --statistics 2>&1 | tail -3
pixi run python -m mypy veny.py veny_json_types.py 2>&1 | tail -1
```

Expected: `252 passed`, a findings total of 299, and `Found 28 errors`. Write these three numbers down; they are the comparison for Step 12.

- [ ] **Step 2: Move the files with `git mv` so history follows**

```bash
mkdir -p src/veny
git mv veny.py            src/veny/cli.py
git mv alias_index.py     src/veny/alias_index.py
git mv pypi_client.py     src/veny/pypi_client.py
git mv stdlib_index.py    src/veny/stdlib_index.py
git mv venv_cache.py      src/veny/venv_cache.py
git mv veny_json_types.py src/veny/json_types.py
```

- [ ] **Step 3: Create `src/veny/__init__.py`**

It holds the version literal and nothing else. No imports: `import veny` must not pull in `cli` and therefore must not trigger the emmykit guard, which `tests/test_import_guard.py` depends on being reachable only through `veny.cli`.

```python
"""veny — run a Python script in a virtual environment built from its imports."""

from __future__ import annotations

__version__: str = "0.2.2"
```

- [ ] **Step 4: Create `src/veny/__main__.py`**

```python
"""Entry point for `python -m veny`."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Rewire the imports at the top of `src/veny/cli.py`**

Lines 26-27 currently read:

```python
import alias_index
import stdlib_index
```

Replace with:

```python
from . import alias_index
from . import stdlib_index
```

Lines 40-41 currently read:

```python
import venv_cache
import veny_json_types
```

Replace with:

```python
from . import json_types
from . import venv_cache
```

Line 43 currently reads `__version__: str = "0.2.2"`. Delete it and put in its place:

```python
from . import __version__
```

Move that line up beside the other `from . import` lines so the module's imports stay together. Leave the emmykit `try:`/`except ImportError:` guard and the `hasattr(ek, "register_json_type")` check exactly where they are, between the two groups.

- [ ] **Step 6: Update the three `veny_json_types` references in `cli.py`**

Line 47 is a comment ending "Its JSON handlers live in veny_json_types." — change the name to `json_types`. Line 53 reads:

```python
veny_json_types.register_types()
```

Replace with:

```python
json_types.register_types()
```

It stays at module scope. Moving it into `main()` makes `save_options_to_json` write `"ResolvedImport(...)"` repr strings for any consumer that does not go through `main()`, and no in-process test notices.

- [ ] **Step 7: Rewire the two sibling modules**

`src/veny/alias_index.py:32` currently reads:

```python
from pypi_client import PyPIClient
```

Replace with:

```python
from .pypi_client import PyPIClient
```

`src/veny/json_types.py:21-22` currently read:

```python
import alias_index
import stdlib_index
```

Replace with:

```python
from . import alias_index
from . import stdlib_index
```

- [ ] **Step 8: Rewire the test imports**

Straight module imports become package imports:

```python
# tests/test_alias_index.py:7-8
from veny import alias_index
from veny.alias_index import (

# tests/test_stdlib_index.py:8-9
from veny import stdlib_index
from veny.stdlib_index import StdlibIndex

# tests/test_venv_cache.py:8
from veny import venv_cache

# tests/test_venv_naming.py:5
from veny import stdlib_index
```

The five files that do `import veny` and then reference `veny.<name>` on many lines get an aliased import, so not one of those references changes:

```python
# tests/test_cache_search.py:13-17
from veny import alias_index
from veny import cli as veny
from veny import stdlib_index
from veny import venv_cache
from veny.alias_index import ResolvedImport

# tests/test_manifest_writing.py:7-10
from veny import cli as veny
from veny import stdlib_index
from veny import venv_cache
from veny.alias_index import ResolvedImport

# tests/test_options_surface.py:5, tests/test_rename_venv.py:5
from veny import cli as veny

# tests/test_split_imports.py:9-13
from veny import alias_index
from veny import cli as veny
from veny import stdlib_index
from veny import venv_cache
from veny.alias_index import Candidate, Resolution, Source

# tests/test_venv_naming.py:6
from veny import cli as veny
```

`tests/test_manifest_writing.py:40` asserts `manifest.veny_version == veny.__version__`; under the alias that resolves through `cli`, which re-exports `__version__` after Step 5, so the line is left alone.

- [ ] **Step 9: Rewire the subprocess source strings**

These are strings, so a plain find-and-replace on import statements misses them.

In `tests/test_json_types.py`, line 10 becomes:

```python
from veny import json_types as veny_json_types
```

(the local name is kept so lines 15, 177 and 178 are untouched), and line 193 becomes:

```python
        "import veny.cli, json, emmykit as ek; from veny import alias_index;"
```

In `tests/test_import_guard.py`, all three sources must import `veny.cli`, since that is where the guard lives now:

```python
# line 21
    result = run_python("import sys; sys.modules['emmykit'] = None; import veny.cli")

# line 31
    result = run_python("import veny.cli; import veny; print(veny.__version__)")

# line 52, inside the stub source
        "import veny.cli\n"
```

- [ ] **Step 10: Point pytest at `src` only**

In `pyproject.toml`, this line:

```toml
pythonpath = ["src", "."]  # "." because veny.py and stdlib_index.py live at the repository root, not under src/
```

becomes:

```toml
pythonpath = ["src"]
```

The `"."` entry existed only because the modules sat at the root. `tests/test_import_guard.py` runs subprocesses with `cwd=REPO_ROOT`; they find the package through `PYTHONPATH=src`, which `pixi.toml`'s `[activation.env]` already exports and which subprocesses inherit.

- [ ] **Step 11: Make the formatter trap unsteppable**

In `.pre-commit-config.yaml`, add an `exclude` to the `ruff` and `ruff-format` hooks only (leave `mypy` alone — it is `mypy .` with `pass_filenames: false`):

```yaml
      - id: ruff
        name: ruff
        entry: pixi run python -m ruff check --fix
        language: system
        types: [python]
        # cli.py is hand-aligned; a formatter run once rewrote ~2,000 of its
        # lines. Its 299 pre-existing findings are tracked by scoped
        # `ruff check src/veny/cli.py --statistics` runs instead.
        exclude: '^src/veny/cli\.py$'
      - id: ruff-format
        name: ruff-format
        entry: pixi run python -m ruff format
        language: system
        types: [python]
        exclude: '^src/veny/cli\.py$'
```

- [ ] **Step 12: Run the full suite and compare all three baselines**

```bash
pixi run test 2>&1 | tail -1
ruff check src/veny/cli.py --statistics 2>&1 | tail -3
pixi run python -m mypy src/veny/cli.py src/veny/json_types.py 2>&1 | tail -1
```

Expected: `252 passed`; a findings total of 299; `Found 28 errors`. The counts must match Step 1 exactly — nothing was deleted in this task, only relocated. A different number means an import rewrite changed behaviour or a file was reformatted.

- [ ] **Step 13: Confirm history survived the move**

```bash
git log --oneline --follow src/veny/cli.py | head -3
```

Expected: the pre-move commits (`f3fe56b refactor: adopt emmykit's empty-Namespace default...` and older).

- [ ] **Step 14: Commit**

```bash
pixi run pre-commit run --files \
  src/veny/__init__.py src/veny/__main__.py \
  src/veny/alias_index.py src/veny/json_types.py \
  .pre-commit-config.yaml pyproject.toml
git add -A src tests pyproject.toml .pre-commit-config.yaml
git commit -m "refactor: move veny's modules into a src/veny/ package"
```

---

### Task 2: Delete the alias installer and pin veny's identity

**Goal:** The alias installer, its four shell dialects and both flags are gone; `my_name` and argparse's `prog` are the constant `"veny"` rather than derived from `sys.argv[0]`.

**Files:**
- Create: `tests/test_cli_entry_point.py`
- Modify: `src/veny/cli.py` (`Options.__init__`, `parse_arguments`, `main`, and the four alias functions)

**Acceptance Criteria:**
- [ ] `define_alias_command`, `alias_exists`, `add_alias_to_rc_file`, `add_alias`, `manual_instructions` and `my_filepath` no longer exist in `cli.py`
- [ ] `--alias` and `--manual` both exit 2
- [ ] `options.my_dir` is `~/veny` whatever `sys.argv[0]` says
- [ ] `python -m veny --version` prints exactly `veny 0.2.2`
- [ ] `pixi run test` reports 256 passed (252 + the 4 new cases)
- [ ] `ruff check src/veny/cli.py --statistics` total is below 299

**Verify:** `pixi run python -m pytest tests/test_cli_entry_point.py -v` → 4 passed

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_entry_point.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

```bash
pixi run python -m pytest tests/test_cli_entry_point.py -v
```

Expected: 4 failures. `--version` prints `__main__.py 0.2.2` (no `prog`); `my_name` is `"__main__"`; both flag cases exit 0 instead of 2, because `--manual` prints the manual and `--alias` tries to write to an rc file.

- [ ] **Step 3: Delete `my_filepath` and pin `my_name`**

In `Options.__init__`, lines 64-65 read:

```python
        self.my_filepath:                  Path = ek.ensure_path(sys.argv[0])  # Full (invoked) path to this script
        self.my_name:                       str = self.my_filepath.stem  # The base name of this script without the .py extension
```

Replace both with:

```python
        self.my_name:                       str = "veny"  # Fixed: the installed command's name, not whatever argv[0] happens to be.
```

`my_filepath` has no other reader once the alias code is gone.

- [ ] **Step 4: Delete `manual_instructions`**

Remove the whole `self.manual_instructions: str = f"""..."""` assignment (lines 115-137), from `self.manual_instructions` through the closing `"""`. It documents how to hand-write a shell alias, which is no longer how veny is installed.

- [ ] **Step 5: Delete the four alias functions**

Remove these four function definitions from `cli.py`, docstrings included, leaving the surrounding blank-line spacing intact: `define_alias_command`, `alias_exists`, `add_alias_to_rc_file`, `add_alias`. They run from `def define_alias_command(options: Options) -> None:` through the end of `add_alias`, immediately before `def _literal_str(expr_node: ast.AST) -> str | None:`.

This removes veny's last calls to `ek.detect_shell`, `ek.find_shell_rc_file` and `ek.find_additional_alias_files` — the subject of Task 6.

- [ ] **Step 6: Remove both flags and set `prog`**

In `parse_arguments`, the parser line becomes:

```python
    parser = argparse.ArgumentParser(prog="veny", description="Run a python script with optional flags.")
```

Without `prog`, argparse on 3.12/3.13 derives it from `basename(sys.argv[0])`, so `python -m veny --help` prints `usage: __main__.py` and `%(prog)s` in the `--version` template prints `__main__.py`.

Delete the `--manual` argument:

```python
    parser.add_argument("--manual", action="store_true",
                        help="Print instructions for manually adding the alias to the shell configuration file.")
```

Delete the `--alias` argument:

```python
    parser.add_argument("--alias", type=str,
                        help="Add an alias to the shell configuration file so that typing ALIAS anywhere runs this program.")
```

In the same function's docstring, the line `SystemExit: If "-version" or "-manual" flags are provided, the program will print the relevant information and exit.` becomes `SystemExit: If the "-version" flag is provided, the program will print the version and exit.`

- [ ] **Step 7: Delete the two dispatch blocks**

Still in `parse_arguments`, remove:

```python
    # Print instructions for manually adding the alias to the shell configuration file, etc.
    if getattr(options.args, "manual", False):
        print(options.manual_instructions)
        sys.exit(0)
```

In `main`, this block:

```python
    if getattr(options.args, "alias", False):
        # Add the alias to the shell configuration file
        options.alias = options.args.alias
        add_alias(options)
        sys.exit(0)
    elif getattr(options.args, "full", False) and options.python_script:
```

becomes:

```python
    if getattr(options.args, "full", False) and options.python_script:
```

Leave the `elif`/`else` branches that follow untouched.

- [ ] **Step 8: Run the new tests and confirm they pass**

```bash
pixi run python -m pytest tests/test_cli_entry_point.py -v
```

Expected: 4 passed.

- [ ] **Step 9: Confirm nothing else regressed**

```bash
pixi run test 2>&1 | tail -1
ruff check src/veny/cli.py --statistics 2>&1 | tail -3
pixi run python -m mypy src/veny/cli.py src/veny/json_types.py 2>&1 | tail -1
grep -n 'my_filepath\|manual_instructions\|add_alias\|alias_exists\|define_alias_command' src/veny/cli.py
```

Expected: `256 passed`; a ruff total below 299; 28 or fewer mypy errors; and no output at all from `grep` (exit status 1).

- [ ] **Step 10: Commit**

```bash
pixi run pre-commit run --files tests/test_cli_entry_point.py
git add src/veny/cli.py tests/test_cli_entry_point.py
git commit -m "feat: drop the shell-alias installer for a fixed command identity"
```

---

### Task 3: Make the package installable

**Goal:** `pyproject.toml` declares a build backend, a `veny` console script and a single-sourced version, and `python -m build` produces a wheel whose entry point is `veny.cli:main`.

**Files:**
- Modify: `pyproject.toml`, `pixi.toml`, `.gitignore`

**Acceptance Criteria:**
- [ ] `pixi run build` writes `dist/veny-0.2.2-py3-none-any.whl` and a matching `.tar.gz`
- [ ] The wheel's `entry_points.txt` contains `veny = veny.cli:main` under `[console_scripts]`
- [ ] The wheel version comes from `src/veny/__init__.py`, with no `version` left in `[project]`
- [ ] `pixi run veny --version` prints `veny 0.2.2`
- [ ] `dist/`, `build/` and `*.egg-info/` are gitignored

**Verify:** `pixi run build && pixi run python -c "import zipfile,glob; w=glob.glob('dist/*.whl')[0]; print(zipfile.ZipFile(w).read([n for n in zipfile.ZipFile(w).namelist() if n.endswith('entry_points.txt')][0]).decode())"` → prints `[console_scripts]` and `veny = veny.cli:main`

**Steps:**

- [ ] **Step 1: Declare the build backend, script and dynamic version**

In `pyproject.toml`, the `[project]` table currently reads:

```toml
[project]
name = "veny"
version = "0.1.0"  # Required by PEP 621. Keep set even without a [build-system] so any uv-using tool that walks up into this directory doesn't fail PEP 621 validation.
requires-python = ">=3.12,<3.14"
dependencies = ["emmykit>=0.4.0,<1.0"]
```

Replace it with:

```toml
[project]
name = "veny"
dynamic = ["version"]  # Single-sourced from src/veny/__init__.py by hatchling.
description = "Run a Python script in a virtual environment built from its imports."
requires-python = ">=3.12,<3.14"
dependencies = ["emmykit>=0.4.0,<1.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
veny = "veny.cli:main"

[tool.hatch.version]
path = "src/veny/__init__.py"

[tool.hatch.build.targets.wheel]
packages = ["src/veny"]
```

The static `version = "0.1.0"` is deleted, not updated: it disagreed with `veny.py`'s `__version__ = "0.2.2"`, so a wheel built from it would have been labelled with a version that contradicts both `--version` and the `veny_version` field written into every venv manifest.

- [ ] **Step 2: Add the two pixi tasks**

In `pixi.toml`, after `typecheck = "python -m mypy ."` in `[tasks]`:

```toml
# Run veny from the working tree. PYTHONPATH=src is already exported by
# [activation.env], so no editable install is needed inside pixi.
veny = "python -m veny"
# Build the sdist + wheel. python-build and hatchling are already pinned in
# [dependencies].
build = "python -m build"
# Install the built wheel into a throwaway venv and prove the console script
# works. Needs the network; deliberately not part of `pixi run test`.
smoke = "bash scripts/smoke-install.sh"
```

- [ ] **Step 3: Ignore the build outputs**

Append to `.gitignore`:

```gitignore
# Packaging build outputs
dist/
build/
*.egg-info/
```

- [ ] **Step 4: Build and inspect the wheel**

```bash
pixi run build 2>&1 | tail -3
ls dist/
```

Expected: `dist/veny-0.2.2-py3-none-any.whl` and `dist/veny-0.2.2.tar.gz`. A filename saying `0.1.0` means `[tool.hatch.version]` is not being read.

- [ ] **Step 5: Confirm the console script is declared in the wheel**

```bash
pixi run python - <<'EOF'
import glob, zipfile
wheel = glob.glob("dist/*.whl")[0]
with zipfile.ZipFile(wheel) as zf:
    name = next(n for n in zf.namelist() if n.endswith("entry_points.txt"))
    print(wheel)
    print(zf.read(name).decode())
EOF
```

Expected output includes:

```
[console_scripts]
veny = veny.cli:main
```

- [ ] **Step 6: Confirm the in-repo runner still works**

```bash
pixi run veny --version
```

Expected: `veny 0.2.2`.

- [ ] **Step 7: Commit**

```bash
pixi run pre-commit run --files pyproject.toml pixi.toml .gitignore
git add pyproject.toml pixi.toml .gitignore
git commit -m "build: declare a hatchling build backend and a veny console script"
```

---

### Task 4: Prove the installed entry point works

**Goal:** A `pixi run smoke` check that builds the wheel, installs it into a throwaway virtual environment, and proves both that the `veny` console script exists and that a wrapped script's exit status reaches the caller.

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Create: `scripts/smoke-install.sh`

**Acceptance Criteria:**
- [ ] `pixi run smoke` exits 0 and its last line reads `smoke: OK`
- [ ] The script fails loudly if `<venv>/bin/veny` is absent after installing the wheel
- [ ] `veny --version` run from the throwaway venv prints `veny 0.2.2`
- [ ] Running a fixture of `import sys; sys.exit(7)` through the installed `veny` exits **7**, not 0 and not 1
- [ ] The run leaves no venv behind under the real `~/veny` (it runs with `HOME` pointed at the temporary directory)

**Verify:** `pixi run smoke` → exit 0, final line `smoke: OK (console script installed, --version matched, exit status 7 propagated)`

**Steps:**

- [ ] **Step 1: Write `scripts/smoke-install.sh`**

```bash
#!/usr/bin/env bash
#
# smoke-install.sh — build the wheel, install it into a throwaway virtual
# environment, and prove the console script entry point works end to end.
#
# Nothing in-process can check [project.scripts]: that string is interpreted
# only by an installer. This is the only test that exercises it.
#
# Needs the network (pip resolves emmykit) and builds a real venv, so it is
# NOT part of `pixi run test`. Run it before publishing.

set -euo pipefail

repo_root=$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$repo_root"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

echo "smoke: building the wheel"
rm -rf dist
python -m build --wheel --outdir dist >/dev/null

wheel=$(ls dist/veny-*.whl | head -1)
[[ -n "$wheel" ]] || { echo "smoke: no wheel in dist/" >&2; exit 1; }
echo "smoke: built $wheel"

echo "smoke: installing into a throwaway venv"
python -m venv "$work/venv"
"$work/venv/bin/python" -m pip install --quiet "$wheel"

veny_bin="$work/venv/bin/veny"
[[ -x "$veny_bin" ]] || {
    echo "smoke: FAIL — $veny_bin missing; [project.scripts] did not take" >&2
    exit 1
}

# HOME is redirected for every veny invocation below so the check cannot
# write venvs or logs into the real ~/veny.
expected="veny $("$work/venv/bin/python" -c 'import veny; print(veny.__version__)')"
actual=$(HOME="$work" "$veny_bin" --version)
[[ "$actual" == "$expected" ]] || {
    echo "smoke: FAIL — --version printed '$actual', expected '$expected'" >&2
    exit 1
}

HOME="$work" "$veny_bin" --help >/dev/null || {
    echo "smoke: FAIL — --help did not run" >&2
    exit 1
}

echo "smoke: checking exit-status propagation"
printf 'import sys\nsys.exit(7)\n' > "$work/fixture.py"
set +e
(cd "$work" && HOME="$work" "$veny_bin" fixture.py >"$work/out.txt" 2>&1)
status=$?
set -e
[[ "$status" -eq 7 ]] || {
    echo "smoke: FAIL — fixture exited $status, expected 7" >&2
    tail -20 "$work/out.txt" >&2
    exit 1
}

echo "smoke: OK (console script installed, --version matched, exit status 7 propagated)"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/smoke-install.sh
```

- [ ] **Step 3: Run it**

```bash
pixi run smoke
```

Expected final line: `smoke: OK (console script installed, --version matched, exit status 7 propagated)`, exit status 0. It takes a minute or two: pip downloads emmykit, and veny then builds a virtual environment for the fixture.

- [ ] **Step 4: Prove the exit-code check is load-bearing**

Temporarily change the fixture line in the script from `sys.exit(7)` to `sys.exit(0)`, re-run `pixi run smoke`, and confirm it now FAILS with `smoke: FAIL — fixture exited 0, expected 7`. Restore `sys.exit(7)` and confirm it passes again. A check that cannot fail proves nothing; capture both outputs.

- [ ] **Step 5: Confirm the real home directory was untouched**

```bash
ls ~/veny | wc -l
```

Compare against the same count taken before Step 3. The numbers must match — the smoke run redirects `HOME`, so no new venv folder should appear.

- [ ] **Step 6: Commit**

```bash
git add scripts/smoke-install.sh
git commit -m "test: prove the installed console script and its exit status"
```

---

### Task 5: Update the documentation

**Goal:** `README.md` documents the three install paths and how to remove the old alias; `PROGRESS.md` points at the new paths and drops the gotchas this work invalidated.

**Files:**
- Modify: `README.md`, `PROGRESS.md`

**Acceptance Criteria:**
- [ ] README's Installation section covers `uv tool install veny`, `uv tool install --editable <clone>`, and `pixi run veny`
- [ ] README carries an "Upgrading from the alias install" section naming the exact line to delete and the `hash -r` / `rehash` follow-up
- [ ] README's project-structure block shows `src/veny/` with the current filenames
- [ ] PROGRESS.md's scoped-gate instructions name `src/veny/cli.py`, not `veny.py`
- [ ] PROGRESS.md's "flat script layout" gotcha is replaced, not merely amended
- [ ] PROGRESS.md's Current work block records the plan as complete with the next action

**Verify:** `rg -n 'uv tool install|Upgrading from the alias install|src/veny/cli\.py' README.md PROGRESS.md` → hits in both files; `rg -n 'flat script layout' PROGRESS.md` → only inside the replacement's historical clause

**Steps:**

- [ ] **Step 1: Rewrite README's Installation section**

Replace the existing `## Installation` section (the `pixi install` block and the paragraph about dev tools) with:

````markdown
## Installation

veny is an application, so install it as a tool rather than into a project
environment — that gives it a private virtual environment with a satisfying
interpreter and its `emmykit` dependency resolved for it:

```
uv tool install veny
```

`pipx install veny` works the same way. To install from a clone instead, so
that `git pull` takes effect with no reinstall:

```
uv tool install --editable ~/path/to/veny
```

Either way the `veny` command lands on your PATH — visible to scripts, cron and
`subprocess`, not just to interactive shells. `uv tool upgrade veny` and
`uv tool uninstall veny` manage it from there.

### Upgrading from the alias install

Earlier versions of veny installed themselves by appending a line to a shell
configuration file. A shell alias takes precedence over PATH, so that line will
keep running the old copy after you install the command. Delete it from your
`~/.bashrc`, `~/.zshrc` or equivalent:

```
alias veny="python3 ~/veny.py"
```

then refresh the current shell's command lookup with `hash -r` (bash) or
`rehash` (zsh), or just open a new terminal.

### Working on veny itself

```
pixi install
pixi run veny my_script.py
```

This installs the development tools (ruff, mypy, pytest, pre-commit) plus the
scaffold baseline — none of it is a runtime dependency of veny. `pixi run veny`
runs the working tree directly through `python -m veny`; no editable install is
involved.
````

- [ ] **Step 2: Update README's project structure block**

Replace the existing structure block with:

````markdown
```
src/veny/
    __init__.py    # Version literal.
    __main__.py    # python -m veny.
    cli.py         # Argument parsing, import analysis driving, venv
                   # build/run orchestration.
    alias_index.py # Import-name -> pip-name resolution (overrides, cache,
                   # target-interpreter probe, PyPI confirmation chain).
    json_types.py  # Registers veny's own types with emmykit's JSON registry.
    pypi_client.py # Confirms a project provides an import name by reading a
                   # wheel's central directory over an HTTP range request.
    stdlib_index.py # Standard-library membership for the target interpreter.
    venv_cache.py  # Folder naming, manifests, and matching for cached
                   # virtual environments.
scripts/           # smoke-install.sh: wheel + console-script verification.
tests/             # pytest test suite.
docs/              # Design docs and implementation plans.
```
````

Note that `alias_index.py` is about *import-name aliases* — it is unrelated to
the shell alias this work removed, and it stays.

- [ ] **Step 3: Fix PROGRESS.md's scoped-gate instructions**

In the Gotchas section, the entry beginning "`pixi run lint` and `pixi run typecheck` fail repo-wide" names `veny.py` three times and `veny_json_types.py` once. Update every path to `src/veny/cli.py` and `src/veny/json_types.py`, and update the following gotcha ("Never run pre-commit's `ruff`/`ruff-format` hooks against `veny.py`") to name `src/veny/cli.py` and to record that the two hooks now carry `exclude: '^src/veny/cli\.py$'`, so the rule is enforced rather than remembered.

- [ ] **Step 4: Replace the flat-layout gotcha**

This entry is now false:

> The repository is a flat script layout (`veny.py` plus `alias_index.py`, `pypi_client.py`, `stdlib_index.py`, `venv_cache.py`, `veny_json_types.py`), not the `src/` package layout described in the global CLAUDE.md. New modules must travel alongside those files.

Replace it with:

> The repository uses the `src/veny/` package layout as of 2026-08-15 (it was a flat script layout before that; `veny.py` is now `src/veny/cli.py` and `veny_json_types.py` is now `src/veny/json_types.py`). New modules go inside `src/veny/` and are imported with `from . import <name>`. Tests import them as `from veny import <name>`, and the five test files that reference `veny.<name>` throughout use `from veny import cli as veny` to keep those references working.

- [ ] **Step 5: Refresh PROGRESS.md's Current work block**

Replace the "Implementation plan: not written yet" line and the "**Next action:**" line of the Current work block with:

```markdown
- Implementation plan: `docs/superpowers/plans/2026-08-15-packaged-entry-point.md`
  (6 tasks)
- Task tracker: `docs/superpowers/plans/2026-08-15-packaged-entry-point.md.tasks.json`

**Next action:** Task 6 — write the emmykit usage-audit prompt. Tasks 1-5 are
complete: the six modules live in `src/veny/`, the alias installer and its four
shell dialects are deleted, `pyproject.toml` declares a hatchling build backend
and `[project.scripts] veny = "veny.cli:main"`, and `pixi run smoke` proves the
installed console script propagates a wrapped script's exit status.
```

- [ ] **Step 6: Verify the docs describe what exists**

```bash
rg -n 'veny\.py|veny_json_types' README.md PROGRESS.md
```

Expected: hits only where the text is deliberately historical (the alias line to delete, the "was a flat script layout" note). Any other hit is a stale path.

- [ ] **Step 7: Commit**

```bash
pixi run pre-commit run --files README.md PROGRESS.md
git add README.md PROGRESS.md
git commit -m "docs: document the console-script install and drop the alias"
```

---

### Task 6: Write the emmykit usage-audit prompt

**Goal:** A cross-repo prompt, in the same shape as the two existing ones, asking the emmykit repository whether its shell/alias helpers have any remaining callers — plus a pasteable `fd` command for searching everywhere else.

**Files:**
- Create: `docs/prompts/2026-08-15-emmykit-shell-alias-helpers-audit.md`
- Modify: `PROGRESS.md` (Deferred items)

**Acceptance Criteria:**
- [ ] The prompt names all three functions and all five `Options` fields, with their file paths
- [ ] It asks for a usage audit and a recommendation, and explicitly does **not** ask for a deletion
- [ ] It states that these are public API on a published 0.4.0, so removal is a breaking change
- [ ] It carries an `fd` command, split across short lines, that counts occurrences under an arbitrary directory
- [ ] PROGRESS.md's Deferred items records the outstanding prompt, as the emmykit and utilities prompts were recorded before

**Verify:** `bash -n` is not applicable; instead run the prompt's own `fd` command against this repository and confirm it now reports **no** hits (Task 2 deleted the last three)

**Steps:**

- [ ] **Step 1: Write the prompt**

Create `docs/prompts/2026-08-15-emmykit-shell-alias-helpers-audit.md`:

````markdown
# Prompt for the emmykit repository: audit the shell/alias helpers

Run this in a Claude Code session opened on the `emmykit` repository.

---

veny — until 2026-08-15 emmykit's only known consumer of these symbols — has
stopped calling emmykit's shell and alias helpers. It used to install itself by
appending an alias to a shell configuration file; it now ships a console-script
entry point (`[project.scripts] veny = "veny.cli:main"`), so the whole alias
installer was deleted.

That leaves the following symbols with no known caller:

**Functions** (`emmykit/python_env.py`, all three exported in `__init__.py`'s
`__all__`):

- `detect_shell(options)`
- `find_shell_rc_file(options)`
- `find_additional_alias_files(options)`

**`Options` fields** (`emmykit/options.py`, lines 16-20):

- `shell: str | None`
- `rc_file: Path | None`
- `alias: str | None`
- `alias_command: str | None`
- `additional_alias_files: list[Path]`

Please **audit, do not delete**. Specifically:

1. For each of the three functions, find every reference inside this
   repository — call sites, re-exports, `__all__` entries, tests, docstrings
   and documentation. Report them as `path:line`.
2. Do the same for each of the five `Options` fields. Note that `shell` and
   `alias` are short, common words: match `options.shell`, `self.shell`,
   `options.alias` and `self.alias` rather than the bare names, and say which
   spellings you searched.
3. Say whether each symbol is used **only** by the others in this list (that
   is, whether the group is self-contained and dead as a whole) or whether
   something outside the group depends on it.
4. Note that emmykit 0.4.0 is published on PyPI and all three functions are in
   `__all__`, so removing any of them is a breaking change. Recommend a
   disposition for the group — remove in a 0.5.0, deprecate with a warning
   first, or keep — with your reasoning. Do not make the change.

Report back with the reference table and the recommendation.
````

- [ ] **Step 2: Append the external-search command to the same file**

````markdown

---

## Searching outside both repositories

The audit above covers emmykit only. To check for callers anywhere else — other
projects, scratch scripts, anything on disk — run this against whichever
directory you want to search (substitute it for `~/code`). `fd` selects the
files, `rg` counts within them, and the excludes keep vendored copies of
emmykit itself out of the count:

```bash
fd -t f -e py . ~/code \
   -E .pixi -E site-packages -E .git \
   -X rg -c -w \
      -e detect_shell \
      -e find_shell_rc_file \
      -e find_additional_alias_files
```

Output is one `path:count` line per file with at least one hit; no output means
no callers. For a single total instead of a per-file breakdown, append:

```bash
   | awk -F: '{ total += $NF } END { print total + 0 }'
```

The five `Options` fields need the attribute-access forms, since `shell` and
`alias` are too common to search bare:

```bash
fd -t f -e py . ~/code \
   -E .pixi -E site-packages -E .git \
   -X rg -c \
      -e '\.shell\b' \
      -e '\.rc_file\b' \
      -e '\.alias\b' \
      -e '\.alias_command\b' \
      -e '\.additional_alias_files\b'
```

That second one is deliberately loose and will pick up unrelated `.shell` and
`.alias` attributes on other objects; treat its output as a list of places to
look at by hand, not as a count of real callers.
````

- [ ] **Step 3: Verify the command against this repository**

```bash
fd -t f -e py . . \
   -E .pixi -E site-packages -E .git \
   -X rg -c -w \
      -e detect_shell \
      -e find_shell_rc_file \
      -e find_additional_alias_files
```

Expected: no output. Before Task 2 this same command reported `./veny.py:3` — the three call sites in `add_alias`. Their absence now is the evidence that veny really has stopped using these helpers, which is the claim the prompt makes.

- [ ] **Step 4: Record the outstanding prompt in PROGRESS.md**

Add to Deferred items, alongside the still-open utilities prompt:

> - emmykit's shell/alias helpers (`detect_shell`, `find_shell_rc_file`, `find_additional_alias_files`, and the `Options` fields `shell`, `rc_file`, `alias`, `alias_command`, `additional_alias_files`) have no caller in veny as of 2026-08-15. The usage audit is written up as a cross-repo prompt in `docs/prompts/2026-08-15-emmykit-shell-alias-helpers-audit.md` and has not been run yet. They are public API on a published 0.4.0, so removal is a breaking change and the prompt asks for a recommendation rather than a deletion.

- [ ] **Step 5: Commit**

```bash
pixi run pre-commit run --files \
  docs/prompts/2026-08-15-emmykit-shell-alias-helpers-audit.md PROGRESS.md
git add docs/prompts/2026-08-15-emmykit-shell-alias-helpers-audit.md PROGRESS.md
git commit -m "docs: prompt emmykit to audit its now-unused alias helpers"
```

---

## Out of scope

- Publishing to PyPI. The name is unclaimed (checked 2026-08-15), and this plan
  makes veny buildable and installable, but the upload is a separate decision.
- Splitting `cli.py` into smaller modules.
- The 299 ruff findings and 28 mypy errors, which cross the move unchanged.
- Any change to how veny resolves `options.python_command` or builds virtual
  environments.
- Deleting anything from emmykit. Task 6 produces the audit request only.
