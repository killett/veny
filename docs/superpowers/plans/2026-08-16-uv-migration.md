# Phase 2: Migrate to uv — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move veny's environment layer from `pip` + `venv` to `uv`, deleting the wheel-predownload machinery uv's global cache obsoletes, while veny keeps its own venv cache.

**Architecture:** Every virtual environment creation and every package install goes through the `uv` binary, located via the `uv` PyPI package's `find_uv_bin()`. The pre-download layer (`~/veny/packages`, `download_packages.sh`, `--no-index` installs, the batch/individual install split) is deleted — uv's global hardlinked cache does that job, and `verify_and_repair_imports` already establishes which package failed with better evidence than an individual-install sweep. `use_pip_list` goes too, on separate grounds recorded in the design doc. The alias resolution, verification and repair loop — veny's actual differentiator — is untouched.

**Tech Stack:** Python 3.12-3.13, uv 0.12.x, pytest, ruff, mypy, pixi.

**Global Constraints:**
- **Which imports veny discovers must not change.** `tests/test_import_discovery.py` pins it. No task in this plan touches import analysis.
- `pixi run lint` (`ruff check .`) must report zero and `pixi run python -m ruff format --check .` must report every file formatted.
- The whole-repo mypy count must not rise above **39**. Measure with `pixi run typecheck 2>&1 | tail -1`.
- Invoke tools through pixi's `python -m` form (`pixi run python -m pytest`, `pixi run python -m mypy`) — bare binaries hit a shebang-resolution problem on macOS.
- `.git/hooks/pre-commit` is not installed, so `git commit` does not run hooks. Run `pixi run pre-commit run --files <paths>` by hand. Its `mypy` hook is `mypy .` with `pass_filenames: false` and always reports the pre-existing errors; confirm ruff and ruff-format pass and proceed past it.
- Do not use `git stash` or `git checkout <sha>` in the working tree. Use `git worktree add` for any comparison against another commit.
- Stage paths explicitly. A run can leave `.veny_custom_modules_*.pkl` and `logs/` behind; never `git add -A`. `.claude/` and `CLAUDE.md` are untracked and are not to be added.
- **Do not touch phase 3 or 4 work:** no module extraction, no `Options` decomposition beyond the field removals named here, no `--full` changes (phase 3 deletes `--full`).

**User decisions (already made):**
- "b" — uv depth: the environment layer moves to uv; veny keeps its own venv cache. Delegating the cache to `uv run --with` was considered and rejected.
- "Delete it, on the corrected rationale" — `use_pip_list` and `options.pip_list` are deleted because `split_imports` already proves importability by importing, not because of wheel caching. Asked and answered 2026-08-16.
- "delete" — `--full` is removed rather than fixed, in **phase 3**. Do not touch it here.

**Design doc:** `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md`, phase 2 section (corrected 2026-08-16 in commit `9c441b7`).

---

## Verified environment facts

Measured 2026-08-16 against uv 0.12.5 while writing this plan. Do not re-litigate these; do report if you observe otherwise.

- The `uv` PyPI package exposes exactly one public name, `find_uv_bin`, returning a path to a working binary. It has **no** `__version__`.
- conda-forge's `uv` ships only the binary, no Python module — so the dev environment needs the **PyPI** package.
- `uv venv <dir>` does **not** seed `pip`. The resulting `bin/` holds `python`, the activate scripts, and nothing else.
- `uv venv <dir> --python <interpreter>` selects the interpreter.
- `--python` is accepted **after** the subcommand: `uv pip install --python <venv>/bin/python <pkg>` works, as does `-r <file>`.
- `uv pip uninstall` never prompts. Passing `-y` is accepted but emits `warning: '--yes' has no effect (uv never asks for confirmation)`, so drop it.
- A failed install names the offending package clearly (`Because <pkg> was not found in the package registry ... your requirements are unsatisfiable`), which is why the individual-install fallback is redundant.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/veny/cli.py` | Everything. | Modify — net ~550 lines removed |
| `tests/test_uv_backend.py` | Pins the uv binary locator and the argument lists veny builds. | Create |
| `tests/test_options_surface.py` | Guards which fields `Options` carries. | Modify |
| `pyproject.toml` | Runtime dependencies. | Modify |
| `pixi.toml` | Dev environment. | Modify |
| `README.md` | Install and behaviour notes. | Modify |
| `PROGRESS.md` | Project ledger. | Modify |

Line numbers below are as of commit `9c441b7`. They shift as edits are applied, so **work bottom-up within each task** and locate code by symbol name.

---

### Task 1: Declare uv and add the binary locator

**Goal:** veny can find a `uv` binary deterministically, and says something useful when it cannot.

**Files:**
- Modify: `pyproject.toml:7` (`dependencies`)
- Modify: `pixi.toml` (`[pypi-dependencies]`, and the `[pypi-exclude-newer]` table at ~line 65)
- Modify: `src/veny/cli.py` — add `uv_binary()` near the emmykit guard
- Create: `tests/test_uv_backend.py`

**Acceptance Criteria:**
- [ ] `pixi run python -c "import uv; print(uv.find_uv_bin())"` prints a path inside the pixi environment
- [ ] `uv_binary()` returns the packaged binary when `import uv` works
- [ ] `uv_binary()` falls back to `shutil.which("uv")` with a warning when the package is absent
- [ ] `uv_binary()` raises `SystemExit` naming the install command when neither route finds uv
- [ ] All existing tests still pass

**Verify:** `pixi run python -m pytest tests/test_uv_backend.py -v` → 3 passed

**Test design.** Behaviour, the bug caught, and where the expected value came from:

1. `test_the_packaged_uv_is_preferred_over_the_one_on_path` — behaviour: when the `uv` package is importable, its binary wins. Bug caught: reordering the two routes so PATH wins, which reintroduces the resolve-by-luck failure that retired the shell-alias install. Expected value: the sentinel path the fake `find_uv_bin` returns.
2. `test_a_path_uv_is_used_when_the_package_is_missing` — behaviour: the fallback works and warns. Bug caught: deleting the fallback, which makes veny unusable wherever the package is absent but the binary is present — the exact state this repo was in before this task.
3. `test_no_uv_anywhere_exits_with_an_install_message` — behaviour: the failure names the fix. Bug caught: raising a bare `ImportError`/`None` instead, leaving the user with a traceback. Assert on `SystemExit` **and** that the message contains `uv tool install veny`; a bare `pytest.raises(SystemExit)` would pass against any exit.

Monkeypatch only the two true boundaries — module import and `shutil.which`. Do not mock `uv_binary` itself.

**Steps:**

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, change line 7 from:

```toml
dependencies = ["emmykit>=0.4.0,<1.0"]
```

to:

```toml
dependencies = ["emmykit>=0.4.0,<1.0", "uv>=0.9,<1.0"]
```

In `pixi.toml`, add `uv` to `[pypi-dependencies]` beside `emmykit`:

```toml
uv = ">=0.9, <1.0"
```

Leave the `[pypi-exclude-newer]` table alone. `emmykit = "0d"` is there because it is first-party and needs releases immediately; uv is third-party and the workspace's 7-day cooldown is appropriate for it. Run `pixi install` and confirm it solves.

- [ ] **Step 2: Add the locator**

In `src/veny/cli.py`, immediately after the emmykit guard block that ends with `from . import json_types, venv_cache`, add:

```python
@functools.cache
def uv_binary() -> str:
    """Return the uv executable veny drives its environment layer with.

    Prefers the binary shipped by the ``uv`` PyPI package, which is installed
    alongside veny and so carries a version pinned with veny's own. Falls back
    to whatever is on PATH, which resolves by luck -- the weakness that retired
    the shell-alias install -- and is only preferable to failing outright.

    Returns:
        A path or command name to invoke uv with.

    Raises:
        SystemExit: If neither the packaged binary nor PATH yields a uv.
    """
    try:
        import uv
    except ImportError:
        pass
    else:
        return os.fspath(uv.find_uv_bin())
    on_path = shutil.which("uv")
    if on_path:
        logging.warning(
            "Using the uv found on PATH (%s). The uv package is not installed "
            "alongside veny, so its version is not pinned to veny's.",
            on_path,
        )
        return on_path
    raise SystemExit(
        "veny requires uv, which is not installed and is not on PATH.\n"
        "Reinstall veny with:  uv tool install veny"
    )
```

Add `import functools` and `import shutil` to the imports if absent (`shutil` is already imported; check before adding). This raises at first use rather than at import, deliberately: `Options()` is constructed in every test and must not require uv.

- [ ] **Step 3: Write the test**

Create `tests/test_uv_backend.py`:

```python
"""Pin how veny locates the uv binary it drives its environment layer with."""

import shutil
import sys

import pytest

from veny import cli


def test_the_packaged_uv_is_preferred_over_the_one_on_path(monkeypatch):
    """The uv installed alongside veny wins; PATH is never consulted."""
    fake = type(sys)("uv")
    fake.find_uv_bin = lambda: "/packaged/uv"
    monkeypatch.setitem(sys.modules, "uv", fake)
    monkeypatch.setattr(shutil, "which", lambda _name: "/on/path/uv")
    cli.uv_binary.cache_clear()

    assert cli.uv_binary() == "/packaged/uv"


def test_a_path_uv_is_used_when_the_package_is_missing(monkeypatch, caplog):
    """Without the package, PATH serves -- and veny says the version is unpinned."""
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: "/on/path/uv")
    cli.uv_binary.cache_clear()

    assert cli.uv_binary() == "/on/path/uv"
    assert "not pinned" in caplog.text


def test_no_uv_anywhere_exits_with_an_install_message(monkeypatch):
    """The failure names the command that fixes it, not just a traceback."""
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    cli.uv_binary.cache_clear()

    with pytest.raises(SystemExit) as caught:
        cli.uv_binary()
    assert "uv tool install veny" in str(caught.value)
```

Note `monkeypatch.setitem(sys.modules, "uv", None)` makes `import uv` raise `ImportError`, which is the state being simulated. `cache_clear()` is required in every test because `uv_binary` is `functools.cache`d.

- [ ] **Step 4: Run the tests**

Run: `pixi run python -m pytest tests/test_uv_backend.py -v`
Expected: `3 passed`

Run: `pixi run test`
Expected: `263 passed` (260 + 3)

- [ ] **Step 5: Prove test 1 can fail**

Swap the two routes in `uv_binary` so PATH is checked first. Re-run: `test_the_packaged_uv_is_preferred_over_the_one_on_path` must FAIL with `assert '/on/path/uv' == '/packaged/uv'`. Restore the order and confirm `3 passed`.

Mutate `src/veny/cli.py` **in place** — `pixi.toml` sets `PYTHONPATH = "src"` in `[activation.env]`, which overwrites an inherited value, so pointing `PYTHONPATH` at a mutated copy silently tests the real source and reports a false pass.

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files pyproject.toml pixi.toml src/veny/cli.py tests/test_uv_backend.py
git add pyproject.toml pixi.toml pixi.lock src/veny/cli.py tests/test_uv_backend.py
git commit -m "feat: declare uv as a runtime dependency and locate its binary"
```

---

### Task 2: Route virtual environment creation through uv

**Goal:** Both surviving `venv.create` / `-m venv` sites become `uv venv`, and the now-impossible `pip install wheel` step goes.

**Files:**
- Modify: `src/veny/cli.py` — add `create_venv`; `split_imports` (~2581), `setup_virtualenv` (~3552-3585)

**Acceptance Criteria:**
- [ ] `rg -n '"-m", "venv"' src/veny/cli.py` returns nothing
- [ ] The only remaining `venv.create` is the one inside `use_pip_list`. **Leave it.** *(Corrected 2026-08-16: an earlier revision of this task required `import venv` to be gone, which is impossible here — `use_pip_list` is not deleted until Task 4, so the import is still live. Removing it moved to Task 4.)*
- [ ] The `pip install wheel` step in `setup_virtualenv` is deleted
- [ ] `setup_virtualenv` builds with the interpreter `venv_build_interpreter()` returns, not a default
- [ ] All tests pass

**Verify:** `pixi run test` → 263 passed

**Why the wheel step cannot survive:** it ran `options.venv_pip install wheel`, and `uv venv` seeds no pip, so there is no `bin/pip` to run. uv builds source distributions without needing `wheel` installed in the target environment.

**Steps:**

- [ ] **Step 1: Add the helper**

Next to `uv_binary()`, add:

```python
def create_venv(target: str | os.PathLike[str], python: str = "") -> None:
    """Create a virtual environment at target using uv.

    No pip is seeded: veny drives installs through uv, and a script that
    installs into the environment veny built for it is working against veny.

    Args:
        target: Directory to create the environment in.
        python: Interpreter for uv to build against. Empty means uv chooses.

    Raises:
        subprocess.CalledProcessError: If uv could not create the environment.
    """
    command = [uv_binary(), "venv", os.fspath(target)]
    if python:
        command += ["--python", python]
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Creating venv: %s", " ".join(shlex.quote(str(arg)) for arg in command)
        )
    subprocess.check_call(command)
```

- [ ] **Step 2: Swap the `split_imports` temp venv**

In `split_imports`, replace:

```python
        venv.create(venv_dir, with_pip=True)
```

with:

```python
        create_venv(venv_dir)
```

No interpreter is passed, preserving today's behaviour: `venv.create` built with the running interpreter here. The import check never needed pip, so dropping the seed is a straight speed win.

- [ ] **Step 3: Swap the `setup_virtualenv` venv and delete the wheel step**

Replace this block:

```python
    assert options.venv_dir is not None, "options.venv_dir must be set"
    subprocess.check_call(
        [venv_build_interpreter(options), "-m", "venv", os.fspath(options.venv_dir)]
    )
    if not options.rawlog:
        logging.info("Virtual environment created.")

    # Activate virtual environment and install wheel
    assert options.venv_pip is not None, "options.venv_pip must be set"
    install_command = [os.fspath(options.venv_pip), "install", "wheel"]
    logging.info(
        "Running pip install: %s",
        " ".join(shlex.quote(str(arg)) for arg in install_command),
    )
    subprocess.run(install_command, check=True)
    if not options.rawlog:
        logging.info("Wheel installed in the virtual environment.")
```

with:

```python
    assert options.venv_dir is not None, "options.venv_dir must be set"
    create_venv(options.venv_dir, venv_build_interpreter(options))
    if not options.rawlog:
        logging.info("Virtual environment created.")
```

- [ ] **Step 4: Remove the orphaned import and verify**

Run: `pixi run lint`
Expected: zero. `import venv` is **not** orphaned by this task — `use_pip_list` still calls `venv.create`, and it survives until Task 4. Do not remove the import here.

Run: `pixi run test`
Expected: `263 passed`

Run: `rg -n 'venv\.create|"-m", "venv"' src/veny/cli.py`
Expected: exactly one hit, the `venv.create` inside `use_pip_list`.

- [ ] **Step 5: Commit**

```bash
pixi run pre-commit run --files src/veny/cli.py
git add src/veny/cli.py
git commit -m "refactor: create virtual environments with uv"
```

---

### Task 3: Route installs through uv and delete the download layer

**Goal:** One `uv pip install` replaces the download-then-batch-then-individual dance, and the machinery that served it goes.

**Files:**
- Modify: `src/veny/cli.py` — `run_pip_in_venv` (~3150) → `run_uv_pip`; `install_into_venv` (~3187); `uninstall_from_venv` (~3220); `setup_virtualenv`'s install block (~3589-3597); `main()` (~623-627)
- Delete from `src/veny/cli.py`: `download_packages` (~2768), `install_packages_simultaneously` (~2814), `install_packages_individually` (~2841), `install_package` (~2861), `recover_pip_versions` (~2927)

**Acceptance Criteria:**
- [ ] `rg -n 'download_packages|install_packages_simultaneously|install_packages_individually|recover_pip_versions|--no-index|--find-links' src/veny/cli.py` returns nothing
- [ ] `rg -n '"-m", "pip"|run_pip_in_venv' src/veny/cli.py` returns nothing. **`venv_pip` still exists at this point** — the field and its `set_venv_dir` assignment are Task 5's to remove; only its *uses* go here, and Task 2 already took the last one
- [ ] `uv pip uninstall` is invoked **without** `-y` (uv never prompts; `-y` only earns a warning)
- [ ] `options.simultaneous_success` is renamed `options.install_succeeded` and still gates the `failed-` prefix drop in `main()`
- [ ] All tests pass

**Verify:** `pixi run test` → 263 passed

**Note on `install_package`:** it is the only caller of `ek.my_critical_error` on the install path, i.e. the only place a failed install killed the run. Removing it means a failed batch install now leaves `install_succeeded` False, the venv keeps its `failed-` prefix, and `verify_and_repair_imports` gets its turn — which is the better behaviour and the reason the individual sweep is redundant.

**Steps:**

- [ ] **Step 1: Replace the pip runner**

Replace `run_pip_in_venv` in full with:

```python
def run_uv_pip(
    options: Options, *args: str
) -> subprocess.CompletedProcess[str] | None:
    """Run one uv pip command against the venv without ever raising.

    Every caller is on a verification path, where the point is to report what
    happened rather than to end the run, so a missing interpreter or an
    unrunnable uv is reported as "no result" instead of an exception.

    Args:
        options: Options object; reads options.venv_python.
        *args:   The uv pip arguments, e.g. "install", "cv2".

    Returns:
        The completed process, or None if uv could not be run at all.
    """
    if options.venv_python is None:
        logging.error(
            "Cannot run uv pip %s: no virtual environment interpreter is set.", args[0]
        )
        return None
    the_command = [
        uv_binary(),
        "pip",
        *args,
        "--python",
        os.fspath(options.venv_python),
    ]
    logging.info(
        "Running uv: %s", " ".join(shlex.quote(str(arg)) for arg in the_command)
    )
    try:
        return subprocess.run(
            the_command,
            capture_output=True,
            text=True,  # noqa: S603
            check=False,
        )
    except OSError:
        logging.exception("Could not run uv pip %s.", args[0])
        return None
```

- [ ] **Step 2: Point the two wrappers at it**

In `install_into_venv`, replace the body's local-wheels block and call:

```python
    local_wheels = (
        ["--find-links", os.fspath(options.packages_dir)]
        if options.packages_dir
        else []
    )
    result = run_pip_in_venv(options, "install", pip_name, *local_wheels)
```

with:

```python
    result = run_uv_pip(options, "install", pip_name)
```

and update its docstring: the paragraph referring to `install_package()`, `ek.my_critical_error`, `packages_dir` and `--no-index` describes deleted code. Replace that paragraph with:

```
    The batch install is a single uv invocation that either succeeds or leaves
    the venv marked failed; this installer serves the verification loop instead,
    where one candidate failing must never end the run, so every failure is
    reported as False.
```

In `uninstall_from_venv`, replace:

```python
    result = run_pip_in_venv(options, "uninstall", "-y", pip_name)
```

with:

```python
    result = run_uv_pip(options, "uninstall", pip_name)
```

`-y` is dropped deliberately: uv never asks for confirmation and warns that the flag has no effect.

- [ ] **Step 3: Replace the install block in `setup_virtualenv`**

Replace:

```python
    download_packages(options)
    if install_packages_simultaneously(options):
        options.simultaneous_success = True
    else:
        options.simultaneous_success = False  # This is redundant, but it's here for clarity. The 'failed' part of the venv_dir will not be removed if this is False.
        logging.error(
            "Failed to install packages simultaneously. Trying to install packages individually to see which fail, but this venv folder will still have 'failed-' in its name..."
        )
        if not install_packages_individually(options):
            logging.error("Failed to install packages individually.")
```

with:

```python
    assert options.requirements_file is not None, (
        "options.requirements_file must be set"
    )
    result = run_uv_pip(options, "install", "-r", os.fspath(options.requirements_file))
    options.install_succeeded = result is not None and result.returncode == 0
    if not options.install_succeeded:
        # uv names the package it could not satisfy, so there is nothing an
        # individual sweep would add. The venv keeps its "failed-" prefix, and
        # verify_and_repair_imports below gets its turn on what did install.
        logging.error(
            "uv could not install every requirement; this venv folder keeps its "
            "'failed-' prefix.%s",
            f" uv reported:\n{result.stderr.strip()}" if result is not None else "",
        )
```

- [ ] **Step 4: Rename the flag**

In `Options.__init__`, replace:

```python
        self.simultaneous_success: bool = False
```

with:

```python
        self.install_succeeded: bool = False
```

In `main()`, replace `options.simultaneous_success` with `options.install_succeeded` in the `failed-` prefix condition. Confirm with `rg -n 'simultaneous_success' src/veny/ tests/` that nothing remains.

- [ ] **Step 5: Delete the five functions**

Delete `download_packages`, `install_packages_simultaneously`, `install_packages_individually`, `install_package` and `recover_pip_versions` in **descending** line order. Each is a whole top-level function; take it from its `def` line through the line before the next `def`.

- [ ] **Step 6: Verify**

Run: `pixi run lint` — delete exactly the imports it flags as unused, nothing more.

Run: `pixi run test`
Expected: `263 passed`. If `tests/test_split_imports.py` or `tests/test_rename_venv.py` fail, they reference deleted symbols — read the failure and update the test to the new surface rather than restoring the symbol. Report any test you change and why.

Run the acceptance `rg` checks. All must be empty.

- [ ] **Step 8: Commit**

```bash
pixi run pre-commit run --files src/veny/cli.py
git add src/veny/cli.py tests/
git commit -m "refactor: install packages with uv and delete the download layer"
```

---

### Task 4: Delete use_pip_list and options.pip_list

**Goal:** Remove the bare-venv name inventory and the reclassification it drove.

**Files:**
- Modify: `src/veny/cli.py` — delete `use_pip_list` (~2989); its two call sites (`check_packages_in_venv` ~2472, `setup_virtualenv` ~3554); the `pip_list` load block in `main()` (~494-508); the `pip_list` field (~88)

**Acceptance Criteria:**
- [ ] `rg -n 'use_pip_list|pip_list' src/veny/cli.py` returns nothing
- [ ] `import venv` is gone from `cli.py` — deleting `use_pip_list` takes the last `venv.create` with it, and ruff will then flag the import as unused (`F401`). *(Moved here from Task 2, which could not do it: the import was still live until this deletion.)*
- [ ] The `--reqs` union at the end of `split_imports` is **kept** — it is what now solely supplies extra requirements
- [ ] `resolve_records` still has at least one caller (it was used by `use_pip_list`; confirm and report if it does not)
- [ ] All tests pass

**Verify:** `pixi run test` → 263 passed

**Why this is safe** (recorded in the design doc, phase 2, group two): `split_imports` builds its own bare venv and actually imports every name through `check_packages_in_venv`, which is stronger evidence than membership in a name inventory. `main()` loaded the newest `pip_list_*.txt` from `~/veny/` unless `--rc` was passed, so the inventory a run reclassified against was usually one an earlier run wrote, possibly under a different interpreter. Its `--reqs` union duplicates the one at the end of `split_imports`.

**Steps:**

- [ ] **Step 1: Check what else `resolve_records` serves**

Run: `rg -n 'resolve_records' src/veny/ tests/`

`use_pip_list` was one caller. If deleting it leaves `resolve_records` with **no** production caller, say so in your report and leave the function in place — do not delete it in this task. A function with only test callers is a phase 3 question, not this task's.

- [ ] **Step 2: Delete the two call sites**

In `check_packages_in_venv`, in the `else` branch where `record is None`, delete the line:

```python
        use_pip_list(options)
```

Keep the comment block below it — it explains the probe-and-invert approach that follows and is unrelated.

In `setup_virtualenv`, delete its first statement:

```python
    use_pip_list(options)
```

- [ ] **Step 3: Delete the function and the field**

Delete `use_pip_list` entirely — from its `def` line through the line before `def parse_extra_requirements`. This takes the `list_installed_packages` / `list_available_modules` / `list_builtin_modules` heredoc with it; those are lines inside its probe-script string, not veny functions.

In `Options.__init__`, delete:

```python
        self.pip_list: list[str] = []
```

- [ ] **Step 4: Delete the loader in `main()`**

Delete the whole block that begins with the comment `# Look for files in options.my_dir that start with pip_list ...` and ends with the `logging.error(f"Error reading {pip_list_files[0]}")` line — the local `pip_list_files`, the debug log, and the `--rc` guarded read. Nothing else in `main()` uses those locals.

Leave `--rc`'s other effect alone: its `--help` text mentions refreshing "the custom modules cache and the pip list". Update that help string to drop the pip-list half, keeping the custom-modules half. Do the same for `--no-cache`'s help text at line ~238.

- [ ] **Step 5: Verify**

Run: `rg -n 'use_pip_list|pip_list' src/veny/cli.py`
Expected: no output.

Run: `pixi run test`
Expected: `263 passed`. `tests/test_split_imports.py` and `tests/test_cache_search.py` both reference `pip_list`; update them to the new surface and report what you changed.

Run: `pixi run lint` — clear anything it flags.

- [ ] **Step 6: Commit**

```bash
pixi run pre-commit run --files src/veny/cli.py tests/
git add src/veny/cli.py tests/
git commit -m "refactor: delete the bare-venv name inventory and its reclassification"
```

---

### Task 5: Retire the dead Options fields

**Goal:** The fields the last three tasks orphaned are gone and cannot come back.

**Files:**
- Modify: `src/veny/cli.py` — `Options.__init__` (~74, ~75, ~103), `set_venv_dir` (~180), `main()`'s `packages_dir` mkdir (~413-419)
- Modify: `tests/test_options_surface.py`

**Acceptance Criteria:**
- [ ] `rg -n 'packages_dir|test_dir|venv_pip|download_script_path' src/veny/cli.py` returns nothing
- [ ] `RETIRED_FIELDS` in `tests/test_options_surface.py` gains `packages_dir`, `test_dir`, `venv_pip`, `download_script_path`, `pip_list` and `simultaneous_success`
- [ ] `test_options_still_carries_the_directories_veny_uses` no longer asserts on `packages_dir`, and still asserts on `my_dir`
- [ ] Re-adding any one retired field to `Options.__init__` makes `test_options_no_longer_carries_helper_script_paths` fail
- [ ] All tests pass

**Verify:** `pixi run test` → 263 passed

**Steps:**

- [ ] **Step 1: Delete the fields**

From `Options.__init__`, delete:

```python
        self.packages_dir: Path = self.my_dir / "packages"
        self.test_dir: Path = self.my_dir / "test"
```

and:

```python
        self.venv_pip: Path | None = None
```

and:

```python
        self.download_script_path: Path | None = None
```

From `set_venv_dir`, delete the `venv_pip` and `download_script_path` assignments:

```python
        self.venv_pip = p / "bin" / "pip"  # Do NOT resolve() this symlink path
```

```python
        self.download_script_path = p / "download_packages.sh"
```

From `main()`, delete the `packages_dir` existence check and `mkdir` block. Keep the `my_dir` one directly above it.

- [ ] **Step 2: Update the guard**

In `tests/test_options_surface.py`, add the six names to `RETIRED_FIELDS`:

```python
    "packages_dir",
    "test_dir",
    "venv_pip",
    "download_script_path",
    "pip_list",
    "simultaneous_success",
```

In `test_options_still_carries_the_directories_veny_uses`, delete the line:

```python
    assert options.packages_dir == options.my_dir / "packages"
```

leaving the `my_dir` assertion, which still holds.

- [ ] **Step 3: Prove the guard bites**

Temporarily re-add `self.packages_dir: Path = self.my_dir / "packages"` to `Options.__init__`. Run:

`pixi run python -m pytest tests/test_options_surface.py -v`

Expected: `test_options_no_longer_carries_helper_script_paths` FAILS with `retired fields still on Options: ['packages_dir']`. Remove the line again, confirm the suite is back to 263 passed, and confirm `git diff src/veny/cli.py` shows no leftover.

Edit in place — `PYTHONPATH = "src"` in pixi's `[activation.env]` overwrites an inherited value, so a side copy tests the real source.

- [ ] **Step 4: Commit**

```bash
pixi run pre-commit run --files src/veny/cli.py tests/test_options_surface.py
git add src/veny/cli.py tests/test_options_surface.py
git commit -m "refactor: retire the Options fields the uv migration orphaned"
```

---

### Task 6: Make the manifest's interpreter tag a fact about the venv

**Goal:** Close design ledger item 1 — a manifest can record an `interpreter_tag` and an `interpreter_path` that disagree.

**Files:**
- Modify: `src/veny/cli.py` — `_VERSION_PROBE_CODE` (~3416), `installed_versions_in_venv` (~3424), `manifest_for` (~3475), `record_venv_state` (~3517)

**Acceptance Criteria:**
- [ ] `_VERSION_PROBE_CODE` reports the venv interpreter's `sys.version_info[:2]` alongside the distribution versions
- [ ] `installed_versions_in_venv` is renamed `installed_state_in_venv` and returns `tuple[dict[str, str], str]`
- [ ] `manifest_for` records the venv's tag, not `options.stdlib.python_version`
- [ ] When the probe cannot run, the tag falls back to `interpreter_tag(options)`, documented in the docstring
- [ ] Two tests pin the new behaviour: the venv's tag wins over the run's, and an empty tag falls back
- [ ] `tests/test_manifest_writing.py:99` and `:146`, which name the old function, are updated to the new name and return shape
- [ ] All tests pass

**Verify:** `pixi run test` → 265 passed (263 + 2)

**The bug being closed:** `interpreter_tag()` reads `options.stdlib.python_version`, while `venv_build_interpreter()` returns `options.python_command or sys.executable`. `stdlib_index.for_interpreter` falls back to the *running* interpreter's index on a timeout or non-zero exit, so a run targeting 3.13 can write `interpreter_tag: "3.11"` beside `interpreter_path: "python3.13"`. A later degraded run then matches that tag and reuses a 3.13 venv labelled 3.11. `installed_versions_in_venv` already spawns the venv's own interpreter, so it can report the truth for free.

**Test design.** Two tests, each with the bug it catches:

1. `test_the_manifest_tag_comes_from_the_venv_not_the_run` — behaviour: when the venv reports a version, the manifest records it. Bug caught: reverting `manifest_for`'s `interpreter_tag=` to `interpreter_tag(options)`, which reintroduces exactly the 3.13-labelled-3.11 mismatch. Expected value by construction: the fixture's `options.stdlib` says `(3, 12)` and the venv is made to say `3.13`, so the two candidate sources give visibly different answers and only one is right.
2. `test_an_unreadable_venv_falls_back_to_the_runs_own_tag` — behaviour: an empty tag is not written into the manifest as an empty string. Bug caught: writing `interpreter_tag=venv_tag` unconditionally, which would put `""` in the manifest and make every later cache match against it fail in a way no one would trace back here.

Both call `manifest_for` directly rather than going through `record_venv_state`; the tag decision lives in `manifest_for`, and testing it there needs no venv on disk.

**Steps:**

- [ ] **Step 1: Extend the probe**

Replace `_VERSION_PROBE_CODE` with:

```python
_VERSION_PROBE_CODE = (
    "import json, sys\n"
    "from importlib.metadata import distributions\n"
    "print(json.dumps({"
    "'python': list(sys.version_info[:2]),"
    " 'versions': {d.metadata['Name']: d.version for d in distributions()"
    " if d.metadata['Name']}}))\n"
)
```

- [ ] **Step 2: Return both from the probe**

Change `installed_versions_in_venv` to return `tuple[dict[str, str], str]` — the versions and the tag. On every existing failure path it currently returns `{}`; each must now return `({}, "")`, where `""` means "the venv did not say". Update the return-type annotation, the Returns docstring, and the final expression:

```python
    return (
        {
            venv_cache.normalize_pip_name(name): str(version)
            for name, version in payload.get("versions", {}).items()
        },
        ".".join(str(part) for part in payload.get("python", [])),
    )
```

Rename it `installed_state_in_venv`, since it no longer returns only versions, and update its docstring summary line.

- [ ] **Step 3: Take the tag in `manifest_for`**

Add a parameter and use it:

```python
def manifest_for(
    options: Options, versions: dict[str, str], venv_tag: str = ""
) -> venv_cache.Manifest:
```

with the `interpreter_tag=` argument becoming:

```python
        interpreter_tag=venv_tag or interpreter_tag(options),
```

Document in the Args block: `venv_tag: The "major.minor" the venv's own interpreter reported. Empty when the probe could not run, in which case the run's own tag serves -- the pre-existing behaviour, and the only case where the tag can still disagree with interpreter_path.`

- [ ] **Step 4: Thread it through `record_venv_state`**

Replace:

```python
    venv_cache.write_manifest(
        options.venv_dir, manifest_for(options, installed_versions_in_venv(options))
    )
```

with:

```python
    versions, venv_tag = installed_state_in_venv(options)
    venv_cache.write_manifest(
        options.venv_dir, manifest_for(options, versions, venv_tag)
    )
```

- [ ] **Step 5: Update the two tests that name the old function**

`tests/test_manifest_writing.py:99` monkeypatches `"installed_versions_in_venv"` and `:146` asserts `veny.installed_versions_in_venv(options) == {}`. Update both to the new name, and the second to the new return shape:

```python
    assert veny.installed_state_in_venv(options) == ({}, "")
```

The monkeypatch at `:99` must now return a two-tuple; give it `lambda _options: ({...same versions dict it uses today...}, "3.12")`.

- [ ] **Step 6: Add the two new tests**

Append to `tests/test_manifest_writing.py`, using the existing `an_options()` helper — it already sets `options.stdlib` to `StdlibIndex(names=frozenset({"os"}), python_version=(3, 12), source="test")` and `options.python_command` to `"/usr/bin/python3.12"`, which is exactly the disagreement this needs:

```python
def test_the_manifest_tag_comes_from_the_venv_not_the_run() -> None:
    """A degraded stdlib probe must not mislabel the venv's interpreter.

    an_options() classifies against 3.12. A venv reporting 3.13 must be recorded
    as 3.13, or a later degraded run matches the wrong tag and reuses it.
    """
    manifest = veny.manifest_for(an_options(), {}, "3.13")
    assert manifest.interpreter_tag == "3.13"
    assert manifest.interpreter_path == "/usr/bin/python3.12"


def test_an_unreadable_venv_falls_back_to_the_runs_own_tag() -> None:
    """An empty tag means the probe failed, not that the venv has no version."""
    manifest = veny.manifest_for(an_options(), {}, "")
    assert manifest.interpreter_tag == "3.12"
```

The first test also asserts `interpreter_path` is unchanged, pinning that this fix alters only the tag — the two fields are now allowed to describe different things only when the probe failed.

- [ ] **Step 7: Run and mutate**

Run: `pixi run test`
Expected: `265 passed`

Then revert `manifest_for`'s `interpreter_tag=` to `interpreter_tag(options)` and confirm the new test FAILS with `assert '3.11' == '3.13'`. Restore.

- [ ] **Step 8: Commit**

```bash
pixi run pre-commit run --files src/veny/cli.py tests/test_manifest_writing.py
git add src/veny/cli.py tests/test_manifest_writing.py
git commit -m "fix: record the venv's own interpreter version in its manifest"
```

---

### Task 7: Document the behaviour change, run the gates, update PROGRESS

**Goal:** The pip-seeding change is written down where users read, every gate is confirmed, and `PROGRESS.md` points at phase 3.

**Files:**
- Modify: `README.md`
- Modify: `PROGRESS.md`

**Acceptance Criteria:**
- [ ] README states that veny requires uv, and that cached environments no longer contain `pip`
- [ ] README's "Virtual environment cache" section does not describe pre-downloaded wheels in `~/veny/packages`
- [ ] `pixi run test` passes with 265 tests
- [ ] `ruff check .` zero; `ruff format --check .` every file formatted
- [ ] `pixi run typecheck 2>&1 | tail -1` at or below 39 errors
- [ ] `pixi run smoke` green, or the completion note says it was skipped for lack of network
- [ ] A live run against a real script builds a venv with uv and runs the script
- [ ] `PROGRESS.md` **Current work** names phase 3 as the next action with the measured `wc -l src/veny/cli.py`, and the Deferred-items line recording that count is updated to match
- [ ] The Deferred-items entries for the interpreter-tag disagreement and for `~/veny/packages` are removed or marked closed, since Task 6 and Task 3 closed them

**Verify:** `pixi run test && pixi run lint && pixi run smoke` → all green

**Steps:**

- [ ] **Step 1: Update README.md**

Add to the "Working on veny itself" paragraph, which currently says veny's only runtime dependency is emmykit: veny now also requires `uv`, installed with it as a PyPI dependency and located through `uv.find_uv_bin()`.

Add a short subsection under "Virtual environment cache":

```markdown
### Cached environments have no pip

veny builds its environments with `uv venv`, which does not install `pip` into
them. A script that shells out to `pip` from inside its veny-built environment
will not find one. This is deliberate: veny manages the environment's packages,
and a script installing into it is working against that.
```

Check the rest of README for claims about `~/veny/packages` or downloaded wheels and remove any you find.

- [ ] **Step 2: Run every gate**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run smoke
```

Then the counts:

```bash
pixi run typecheck 2>&1 | tail -1
wc -l src/veny/cli.py
```

`pixi run smoke` builds a wheel and installs it into a throwaway venv, so it needs the network. If offline, say so rather than reporting it passed.

- [ ] **Step 3: Prove it works on a real script**

The unit suite never invokes uv for real. Run veny end to end:

```bash
printf 'import yaml\nprint(yaml.safe_load("a: 1"))\n' > /tmp/veny-live.py
pixi run veny /tmp/veny-live.py
```

Expected: veny resolves `yaml` to `PyYAML`, builds an environment under `~/veny/`, installs into it with uv, and prints `{'a': 1}`. Capture the output. Then confirm the environment it built has no pip:

```bash
ls ~/veny/myenv-*/bin/ | head
```

Expected: `python`, `python3`, activate scripts — no `pip`. Report both outputs. If the run fails, that is a real defect in this phase: report it rather than working around it.

- [ ] **Step 4: Update PROGRESS.md**

Replace the `**Next action:**` block under **Current work** with a phase 3 pointer carrying the measured line count, in the same shape phase 1's entry used. Update the Deferred-items bullet recording `src/veny/cli.py`'s length. Remove the two Deferred-items entries this phase closed (the `interpreter_tag`/`interpreter_path` disagreement is closed by Task 6; garbage collection of `~/veny` is *not* closed and stays).

Add a Gotchas entry recording that `uv venv` seeds no pip, so `options.venv_python` is the only interpreter in a veny environment.

- [ ] **Step 5: Commit**

```bash
pixi run pre-commit run --files README.md PROGRESS.md
git add README.md PROGRESS.md
git commit -m "docs: record the uv migration and point at the module extraction"
```

---

## Rollback

Each task is one commit on branch `uv-migration`, off `9c441b7`. To undo the phase, reset the branch. Do not use `git stash` — a pre-commit formatter hook rewriting files mid-stash has blocked the pop in this repository before.
