# Phase 4a: the state model — values instead of Options

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mutable per-run `Options` fields that `pipeline.py` reads and writes with the frozen `Settings`, `Target`, `ImportScan`, `Requirements` and `VenvHandle` values the design fixes, leaving `Options` alive only where persistence still needs it.

**Architecture:** Each stage in `pipeline.py` stops writing its product onto the object it was handed and starts returning it. `Settings` (widened, built once in `run`) carries the invariants; `Target` carries what is being run; `ImportScan` is produced by the scan and consumed by classification; `Requirements` is produced by classification and consumed downstream; `VenvHandle` replaces `Options.set_venv_dir` and its three derived attributes. `Options` survives this plan **only** as the argument `last_used.load_last_used_options` and `ek.save_options_to_json` are typed against — phase 4b deletes it when veny writes its own `LastUsed` record.

**Tech Stack:** Python 3.12+, `dataclasses` (frozen), pytest, mypy, ruff, pixi.

**Global Constraints:**
- **Behaviour-preserving except where this plan names a change.** Two changes are named and sanctioned: Task 1's directory/missing-script handling (traceback → `UsageError` → exit 2), and nothing else. Any other visible difference is a bug, not a deviation.
- **No module may import the module above it.** `tests/test_layering.py` enforces the stack. `settings.py` sits one layer above `__init__`; `state.py` sits above the index layer (`alias_index`, `venv_cache`, `stdlib_index`, `pypi_client`, `json_types`). `Target` and `VenvHandle` go in `state.py`; the widened `Settings` stays in `settings.py`.
- **`pipeline.py` calls its collaborators through the module object** (`verify.check_packages_in_venv(...)`, never `from .verify import ...`). Keep it that way — it is what lets a test replace one boundary.
- **Frozen means frozen.** `Settings`, `Target`, `Requirements` and `VenvHandle` are `@dataclass(frozen=True)`. Rebind with `dataclasses.replace`, never with `object.__setattr__`. `ImportScan` stays mutable — it is an accumulator, and `analysis/scan.py` writes into it in place.
- **`AliasIndex` stays mutable and injected** (design's one deliberate exception): it is a cache with disk backing plus a separate in-memory session-rejection store.
- **Gates, every task:** `pixi run test`, `pixi run lint`, `pixi run python -m ruff format --check .` must be green before the commit. `pixi run typecheck` must not exceed the **29 errors in 7 files** baseline measured on `main` at `b59cfa8`; re-measure, do not copy.

**User decisions (already made):**
- **2026-08-21 — folder scanning is DELETED, not revived.** `veny <directory>` is not a feature. Delete `get_all_imports`, `stayed_out_dir`, the directory arms of `list_packages`, the test that reaches them by bypassing `resolve_target`, and retire the 16 wiring-index rows those arms own.
- **2026-08-21 — phase 4 is three plans, not one.** This is **4a** (the value objects). **4b** is the `LastUsed` persistence change, which deletes `run_options.py`, the `cli.Options` re-export and the ~76 test references in two spellings. **4c** is the remaining behaviour changes (the in-virtualenv guard) plus the residual dead-argument deletions.
- **2026-08-20 (carried in from 3e's review) — the in-virtualenv guard is fixed in phase 4, not before.** It is **4c's**, not this plan's. Do not touch `last_used.is_virtualenv()` here.

---

## Context an executing engineer needs

**Read first:** `PROGRESS.md` (all of it — the deferred items, gotchas and cross-cutting decisions live nowhere else), and `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md` § "Phase 4: the state model".

**Where things stand.** Phase 3 finished and merged at `4d1846c`. `src/veny/` is 7,240 lines across 22 modules; `cli.py` is down to 211 lines and `pipeline.py` holds 940. Five modules below `pipeline` (`classify`, `environment`, `verify`, `cache_search`, `last_used`) have **never heard of `Options`** — they already take explicit arguments. `pipeline.py` is where the bridge code lives.

**What `Options` still holds that this plan drains** (all in `src/veny/run_options.py`):

| Field | Where it goes |
|---|---|
| `my_name`, `my_dir`, `cwd`, `venv_name`, `stay_out_list`, `search_above_this_dir`, `rawlog`, `known_bad_imports`, `also_needs`, `extra_requirements_file` | `Settings` (Task 3) |
| `python_script`, `script_dir`, `script_args`, `python_command`, `timestamp` | `Target` (Task 2) |
| `all_imports`, `custom_modules`, `loaded_custom_modules`, `samedir_files`, `subfolders`, `sys_path_hints`, `seen_stdlib_imports` | `ImportScan` (Task 4) |
| `bad_imports`, `uninstalled_imports`, `extra_requirements` | `Requirements` (Task 5) |
| `venv_dir`, `venv_python`, `requirements_file`, `set_venv_dir` | `VenvHandle` (Task 6) |
| `install_succeeded` | a local and a return value (Task 6) |
| `total_imports`, `script_name`, `unusual_imports`, `max_checks`, `check_interval` | **deleted** — see the amendments below |
| `stdlib`, `aliases` | stay as themselves, passed explicitly (design: "they belong to no bundle") |
| `args`, `home`, `log_mode`, `pathlibcutoff`, `options_json_filepath` | **stay on `Options`** — 4b's, not this plan's |

**Five design amendments this plan records** (add them to `PROGRESS.md` in Task 10, numbered from wherever 3e's last one stopped):

1. **`Settings` has 10 fields, not the design's 15.** `home` is only ever used to derive `my_dir`, so it stays a construction detail in `cli.py`. `log_mode` is read once, in `cli.main`, and stays a local there. `rawlog` is in `Settings`. The remaining three below are dead.
2. **`unusual_imports`, `max_checks` and `check_interval` are dead** — measured 2026-08-21, zero readers anywhere under `src/`. The design rehomed all three into `Settings`. Delete them instead.
3. **`script_name` is dead** — `Options.script_name` is written once, to `""`, in `Options.__init__` and never read or reassigned. The design lists it in `Target`. It is a `.stem` if anything ever needs it; delete it.
4. **`total_imports` is already a `len()`** — `state.Requirements.total_imports` is a property and has been since 3c. `Options.total_imports` is written at `pipeline.py:244` and read nowhere. Delete the attribute; the design already said it should be a `len()`.
5. **The four "dead argument" rows at `pipeline.py:125` close by construction, not by deletion.** 3e's wiring index measured `Settings(my_name=…, cwd=…, stay_out_list=…, search_above_this_dir=…)` dead at that site because `analysis.scan` reads only `settings.rawlog`. Task 3 builds **one** `Settings` in `run` and hands the same object to both `custom_modules.dict_of_custom_modules` (which reads the other four) and `analysis_scan.find_imports_in_script` (which reads `rawlog`). No field is deleted and no site passes a value its callee ignores.

**Gotcha that will bite you (3e recorded it, it is still true).** `analysis/scan.py` mutates the `ImportScan` it is handed **in place** — `.add`, `.append`, `d[k] = v` — and never rebinds a field. `dict_of_custom_modules()` fills `custom_modules` *before* the scan runs, and the scan relies on reading it. So the scan must be **seeded**, not merely read afterwards. Task 4 keeps that: one `ImportScan` is constructed with the custom-module dict already in it, handed to the scanner, and returned.

**Gotcha: `uv venv` refuses a non-empty directory.** `VenvHandle.for_dir()` does the `mkdir` that `set_venv_dir` did. The requirements file must not be written into the venv directory until `environment.create_venv` has already succeeded against that (empty) directory. Writing it earlier made every fresh build crash with `CalledProcessError`. Task 6 must not reorder those two.

**Gotcha: `pixi run` hides one branch.** Under `pixi run`, `sys.prefix == sys.base_prefix`, so `last_used.is_virtualenv()` is False and the middle branch of `pipeline.run` is skipped entirely. That branch is 4c's problem, but be aware that a `pixi run veny` live run does not exercise it.

---

## File Structure

| File | Change | Responsibility after this plan |
|---|---|---|
| `src/veny/settings.py` | Modify | `Settings`, widened from 5 fields to 10. The run's invariants. |
| `src/veny/state.py` | Modify | Adds `Target` and `VenvHandle` alongside the existing `Requirements`. The products stages hand each other. |
| `src/veny/analysis/scan_state.py` | Unchanged | `ImportScan` stays exactly as it is — mutable, seven fields. |
| `src/veny/pipeline.py` | Modify heavily | Sequencing only. Every stage returns its product; nothing writes onto a handed-in object. Loses ~90 lines (folder scanning, the two bridge constructors, the copy-backs). |
| `src/veny/cli.py` | Modify | Builds `Settings` and the `Options` that persistence still needs; hands both to `pipeline.run`. |
| `src/veny/run_options.py` | Modify | Shrinks to the persistence fields plus construction inputs. **Not deleted — that is 4b's.** |
| `tests/test_state_values.py` | Create | Direct tests of `Target`, `VenvHandle` and the widened `Settings`. |
| `tests/test_import_discovery.py` | Modify | Loses the folder-walk test; gains the directory-argument usage-error test. |
| `tests/test_cli_entry_point.py`, `tests/test_classify.py`, `tests/test_last_used.py`, `tests/test_options_surface.py`, `tests/test_split_imports.py`, `tests/test_uv_backend.py` | Modify | Repointed off the drained `Options` fields onto the values. |
| `docs/superpowers/plans/2026-08-21-state-model-values-wiring-index.md` | Create | Task 8's argument-by-argument sweep of every changed call site. |
| `scripts/differential_4a.py` | Create | Task 9's before/after comparison, in the shape of `scripts/differential_3e.py`. |

---

### Task 1: A non-script argument is a usage error, and folder scanning is deleted

**Goal:** `veny somedir/` and `veny /no/such/file.py` return exit 2 with a message instead of an uncaught traceback, and the ~55 lines of unreachable folder-scanning code go with them.

**Files:**
- Modify: `src/veny/pipeline.py:246-358` (`list_packages`, `stayed_out_dir`, `get_all_imports`), `src/veny/pipeline.py:394-421` (`resolve_target`)
- Modify: `tests/test_import_discovery.py:224-270` (delete the folder-walk test, add the two usage-error tests)
- Delete rows: `docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming-wiring-index.md` — every row for `pipeline.py:291`, `:297`, `:317`/`:318` and `:326`-`:346` (16 rows)

**Acceptance Criteria:**
- [ ] `pipeline.get_all_imports` and `pipeline.stayed_out_dir` no longer exist; `rg -n 'get_all_imports|stayed_out_dir' src/ tests/` returns nothing.
- [ ] `list_packages` has one arm: a file that `ek.is_python_script` accepts. Everything else is `UsageError`.
- [ ] `resolve_target` raises `UsageError` — not `IsADirectoryError`, not `FileNotFoundError` — when the positional argument is a directory or does not exist.
- [ ] `veny <directory>` and `veny /no/such/script.py` both return **2** through `cli.main`, and log the message rather than printing a traceback.
- [ ] The 16 wiring-index rows are struck from the 3e index with a one-line note naming this task, not silently removed.
- [ ] A test proves the directory case is a status and not a traceback, and a second proves the missing-file case is.

**Verify:** `pixi run test -k "usage_error or list_packages or resolve_target" -v` → all pass; `pixi run test` → no fewer than 407 passed (408 minus the deleted folder-walk test, plus this task's additions).

**Steps:**

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_import_discovery.py`:

```python
def test_a_directory_argument_is_a_usage_error_not_a_traceback(tmp_path):
    """A directory positional must come back as veny's usage status.

    The bug this fails on: resolve_target goes through ek.ensure_file, which
    raises IsADirectoryError. Nothing catches it, so before this task
    `veny somedir/` was a traceback out of main() rather than a status.
    """
    options = cli.Options()
    options.args = argparse.Namespace(script=str(tmp_path), script_args=[])
    with pytest.raises(pipeline.UsageError) as excinfo:
        pipeline.resolve_target(options)
    assert str(tmp_path) in str(excinfo.value)


def test_a_missing_script_is_a_usage_error_not_a_traceback(tmp_path):
    """A script that does not exist must come back as veny's usage status.

    The bug this fails on: `.resolve(strict=True)` raises FileNotFoundError
    from resolve_target and nothing catches it. Latent defect 2 in
    PROGRESS.md; this task closes it.
    """
    options = cli.Options()
    missing = tmp_path / "no_such_script.py"
    options.args = argparse.Namespace(script=str(missing), script_args=[])
    with pytest.raises(pipeline.UsageError) as excinfo:
        pipeline.resolve_target(options)
    assert "no_such_script.py" in str(excinfo.value)


def test_a_directory_argument_returns_status_2_through_main(tmp_path, monkeypatch):
    """End to end: the usage error must reach the shell as 2, not as a crash.

    The bug this fails on: cli.main catches pipeline.UsageError and returns 2.
    If resolve_target raised anything else, this call would propagate it.
    """
    monkeypatch.setattr(sys, "argv", ["veny", str(tmp_path)])
    assert cli.main() == 2
```

Delete `test_list_packages_walks_a_folder_and_stays_out_of_the_named_directories` (`tests/test_import_discovery.py:224`) in the same step. It reaches the deleted code only by assigning `options.python_script` directly at line 254 — bypassing `resolve_target` — which is exactly the bypass that made the branch look reachable.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test -k "usage_error" -v`
Expected: FAIL — `IsADirectoryError` and `FileNotFoundError` escape instead of `pipeline.UsageError`, and `cli.main()` raises rather than returning 2.

- [ ] **Step 3: Make `resolve_target` raise `UsageError`**

In `src/veny/pipeline.py`, replace the body of `resolve_target` (lines 409-421) with:

```python
    script_string = getattr(options.args, "script", None)
    if script_string is None:
        options.python_script = None
        return
    try:
        options.python_script = ek.ensure_file(
            script_string, raise_on_empty=True
        ).resolve(strict=True)
    except IsADirectoryError as exc:
        # veny runs a script, not a tree. Folder scanning was deleted here
        # (user ruling, 2026-08-21): --full was its only producer of a
        # directory, and deleting --full in 3e made every directory arm
        # unreachable. See PROGRESS.md.
        raise UsageError(
            f"{script_string} is a directory. veny runs a single Python "
            f"script; name the script itself."
        ) from exc
    except (FileNotFoundError, OSError) as exc:
        raise UsageError(f"{script_string} is not a file veny can run.") from exc
    options.script_dir = options.python_script.parent.absolute()
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Directory where the script to run is located: %s",
            os.fspath(options.script_dir),
        )
```

Order matters: `IsADirectoryError` is a subclass of `OSError`, so its `except` clause must come first or the directory message never fires.

Update the docstring's `Raises:` section to name `UsageError` and drop the sentence about a directory being reachable.

- [ ] **Step 4: Collapse `list_packages` and delete the folder-scanning helpers**

Replace `list_packages` (lines 246-312) with the single-file form, and delete `stayed_out_dir` (315-319) and `get_all_imports` (322-358) outright:

```python
def list_packages(options: run_options.Options) -> None:
    """Scan the target script for imports, then classify them.

    Args:
        options: The run's Options. Reads python_script and rawlog; the scan
            and classification fields are replaced.

    Raises:
        UsageError: The target is not a Python script veny can read.
    """
    assert options.python_script is not None, "options.python_script must be set"
    python_file = ek.ensure_path(options.python_script)
    if not ek.safe_is_file(python_file) or not ek.is_python_script(python_file):
        raise UsageError(f"'{os.fspath(python_file)}' is not a valid Python script.")
    if not options.rawlog:
        logging.info(
            "Processing a single Python script: %s", os.fspath(python_file)
        )
    options.python_script = python_file
    options.loaded_custom_modules = set()
    options.all_imports = set()
    find_imports_in_script(options, python_file)
    # Filter out invalid imports before splitting
    options.all_imports = {
        imp for imp in options.all_imports if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", imp)
    }
    split_imports(options)
```

The `assert options.script_dir is not None` at line 272 goes: `script_dir` is not read in this function, and Task 2 moves the guarantee into `Target` anyway.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pixi run test -k "usage_error or list_packages" -v`
Expected: PASS.

Run: `pixi run test`
Expected: PASS. If a test outside `test_import_discovery.py` fails, it was reaching the deleted arms — fix it by pointing it at a real script, not by restoring the code.

- [ ] **Step 6: Strike the 16 wiring-index rows**

In `docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming-wiring-index.md`, mark every row for `pipeline.py:291`, `:297`, `:317`/`:318` and `:326`-`:346` as retired, with this note at the point where they were:

```markdown
> **RETIRED 2026-08-21 by phase 4a Task 1.** These 16 rows measured arguments
> to `list_packages`' directory arms, `stayed_out_dir` and `get_all_imports`.
> Their only named killer reached them by assigning `options.python_script`
> directly, bypassing `resolve_target`; no production run could. The code and
> that test are deleted (user ruling, 2026-08-21). The rows are retired, not
> closed — nothing pinned them, and nothing needed to.
```

- [ ] **Step 7: Commit**

```bash
git add src/veny/pipeline.py tests/test_import_discovery.py \
  docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming-wiring-index.md
git commit -m "fix: make a directory or missing script a usage error, and delete folder scanning"
```

---

### Task 2: `Target` — what is being run

**Goal:** `resolve_target` returns a frozen `Target` instead of writing four fields onto `Options`, and every consumer of those fields takes the `Target`.

**Files:**
- Modify: `src/veny/state.py` (add `Target`)
- Modify: `src/veny/pipeline.py:394-421` (`resolve_target`), `:424-466` (`feeling_lucky`), `:553-579` (`_load_last_used`), `:705-940` (`run`)
- Modify: `src/veny/cli.py:170-200` (`main`)
- Create: `tests/test_state_values.py`

**Acceptance Criteria:**
- [ ] `state.Target` is `@dataclass(frozen=True)` with exactly `python_script: Path`, `script_dir: Path`, `script_args: tuple[str, ...]`, `python_command: str`, `timestamp: str`.
- [ ] `resolve_target(args) -> Target | None` takes the parsed namespace, not an `Options`, and returns `None` for a scriptless run.
- [ ] `python_command` is filled by `dataclasses.replace` inside `run` once `ek.find_preferred_python_version()` has answered; `resolve_target` leaves it `""`.
- [ ] `Options.python_script`, `Options.script_dir`, `Options.script_args`, `Options.python_command`, `Options.script_name` are gone from `run_options.py`.
- [ ] `Target` is immutable in fact: assigning to a field raises `FrozenInstanceError`, and a test proves it.
- [ ] `feeling_lucky` takes `(args, target, *, pathlibcutoff, rawlog, options)` — `options` only because `last_used.load_last_used_venv_python` is typed against `ek.Options` until 4b.

**Verify:** `pixi run test tests/test_state_values.py -v` → all pass; `pixi run test` → green.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_state_values.py`:

```python
"""Direct tests of the frozen values phase 4 passes between stages."""

import dataclasses
from pathlib import Path

import pytest

from veny import state


def test_target_is_frozen():
    """A stage must not be able to write its product back onto the target.

    The bug this fails on: declaring Target with a plain @dataclass. Under a
    mutable Target, `resolve_target` returning a value changes nothing --
    a later stage can still reach back and rewrite script_dir, which is the
    exact accumulator behaviour phase 4 exists to remove.
    """
    target = state.Target(
        python_script=Path("/tmp/s.py"),
        script_dir=Path("/tmp"),
        script_args=(),
        python_command="",
        timestamp="20260821-120000",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        target.script_dir = Path("/elsewhere")  # type: ignore[misc]


def test_target_carries_the_python_command_replace_gives_it():
    """python_command is discovered after the target is built, via replace().

    The bug this fails on: building Target with python_command as a mutable
    field written later, or forgetting to rebind the name that `run` goes on
    to use -- which would leave every venv built against "" rather than the
    resolved interpreter.
    """
    target = state.Target(
        python_script=Path("/tmp/s.py"),
        script_dir=Path("/tmp"),
        script_args=("--flag", "value"),
        python_command="",
        timestamp="20260821-120000",
    )
    resolved = dataclasses.replace(target, python_command="/usr/bin/python3.12")
    assert resolved.python_command == "/usr/bin/python3.12"
    assert target.python_command == ""
    assert resolved.script_args == ("--flag", "value")
```

Add to `tests/test_import_discovery.py`:

```python
def test_resolve_target_returns_a_target_and_leaves_options_alone(tmp_path):
    """resolve_target must produce a value, not mutate what it was handed.

    The bug this fails on: keeping the four writes onto Options and merely
    returning a Target built from them. That would leave both spellings live
    and let a later stage read a stale Options field.
    """
    script = tmp_path / "s.py"
    script.write_text("import os\n")
    args = argparse.Namespace(script=str(script), script_args=["-x"])
    target = pipeline.resolve_target(args)
    assert target is not None
    assert target.python_script == script.resolve(strict=True)
    assert target.script_dir == script.parent.absolute()
    assert target.script_args == ("-x",)
    assert not hasattr(cli.Options(), "python_script")


def test_resolve_target_returns_none_for_a_scriptless_run():
    """A scriptless run is not an error here -- `run` decides.

    The bug this fails on: raising UsageError inside resolve_target, which
    would break --blank-slate (it legitimately has no script).
    """
    args = argparse.Namespace(script=None, script_args=[])
    assert pipeline.resolve_target(args) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_state_values.py tests/test_import_discovery.py -k "target" -v`
Expected: FAIL — `AttributeError: module 'veny.state' has no attribute 'Target'`, and `resolve_target` returns `None` for every input because it still returns nothing.

- [ ] **Step 3: Add `Target` to `state.py`**

Append to `src/veny/state.py`:

```python
@dataclass(frozen=True)
class Target:
    """What this run is being asked to run.

    Frozen because the target is decided once, at the argparse boundary, and
    read by every stage after it. `python_command` is the one field discovered
    later -- `run` rebinds the whole value with dataclasses.replace once
    ek.find_preferred_python_version() has answered, rather than leaving a
    mutable hole in an otherwise fixed value.

    Attributes:
        python_script:  The script itself, resolved strictly.
        script_dir:     Its parent -- the directory later stages search for
                        custom modules and last-used records.
        script_args:    Everything after the script on veny's command line.
        python_command: The interpreter veny will build the venv against;
                        "" until `run` resolves it.
        timestamp:      The run's stamp, used in cached venv folder names.
    """

    python_script: Path
    script_dir: Path
    script_args: tuple[str, ...]
    python_command: str
    timestamp: str
```

`state.py` already imports `dataclass`; add `from pathlib import Path` at the top.

- [ ] **Step 4: Make `resolve_target` return one**

Replace `resolve_target` in `src/veny/pipeline.py` with:

```python
def resolve_target(args: argparse.Namespace) -> state.Target | None:
    """Resolve the script argument into a Target.

    The script path is resolved strictly, so a name that does not exist fails
    here rather than three stages later. Its parent becomes script_dir -- the
    directory every later stage searches for custom modules and last-used
    records.

    Args:
        args: The parsed command line. Reads `script` and `script_args`.

    Returns:
        The run's Target, or None when no script was named. A scriptless run
        is not an error here; `run` decides whether the mode flags allow it.

    Raises:
        UsageError: The positional argument is a directory, or is not a file
            veny can read.
    """
    script_string = getattr(args, "script", None)
    if script_string is None:
        return None
    try:
        python_script = ek.ensure_file(script_string, raise_on_empty=True).resolve(
            strict=True
        )
    except IsADirectoryError as exc:
        raise UsageError(
            f"{script_string} is a directory. veny runs a single Python "
            f"script; name the script itself."
        ) from exc
    except (FileNotFoundError, OSError) as exc:
        raise UsageError(f"{script_string} is not a file veny can run.") from exc
    script_dir = python_script.parent.absolute()
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Directory where the script to run is located: %s", os.fspath(script_dir)
        )
    return state.Target(
        python_script=python_script,
        script_dir=script_dir,
        script_args=tuple(getattr(args, "script_args", []) or []),
        python_command="",
        timestamp=dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
    )
```

Add `import argparse` and `from . import state` to `pipeline.py`'s imports.

- [ ] **Step 5: Repoint the consumers**

`feeling_lucky` becomes:

```python
def feeling_lucky(
    args: argparse.Namespace,
    target: state.Target | None,
    *,
    options: run_options.Options,
    pathlibcutoff: str,
    rawlog: bool,
) -> int | None:
    """Try the previous run's virtual environment without analyzing anything.

    This runs before logging is configured, which is why it reports with
    `print()` rather than `logging`: --feeling-lucky's whole point is to reach
    the user's script with as little of veny in the way as possible.

    Args:
        args: The parsed command line; reads the --feeling-lucky flag.
        target: The run's Target, or None for a scriptless run.
        options: The template ek.Options load_last_used_venv_python fills in.
            Still an Options because emmykit's loader is typed against one;
            phase 4b replaces it with a LastUsed record.
        pathlibcutoff: JSON files stamped before this are ignored.
        rawlog: True suppresses veny's own commentary.

    Returns:
        The script's exit status if the lucky path ran it, or None meaning
        "no luck, carry on with the normal run".
    """
    if not getattr(args, "feeling_lucky", False) or target is None:
        return None
    last_used_venv_python = last_used.load_last_used_venv_python(
        options,
        script_dir=target.script_dir,
        python_script=target.python_script,
        pathlibcutoff=pathlibcutoff,
        rawlog=rawlog,
    )
    if last_used_venv_python:
        returncode = run_script(
            last_used_venv_python,
            target.python_script,
            list(target.script_args),
            rawlog=rawlog,
        )
        if returncode != 0 and not rawlog:
            print(f"Script exited with status {returncode}")
        return returncode
    if not rawlog:
        print(
            "No luck: no last used virtual environment found. Running the script as normal."
        )
    return None
```

The two `assert`s go: `target` being non-`None` already guarantees both paths, which is the point of making it a value.

`_load_last_used` becomes:

```python
def _load_last_used(
    options: run_options.Options,
    target: state.Target,
    *,
    pathlibcutoff: str,
    rawlog: bool,
) -> ek.Options | None:
    """Load the previous run's options JSON, for the cache search's last-used pass.

    find_match_dir_in_cache takes this as an injected callable rather than
    reaching for last_used itself, so nothing below pipeline has to know what
    an Options is.

    Args:
        options: The template ek.Options the loader fills in. Phase 4b
            replaces it with a LastUsed record.
        target: The run's Target; supplies script_dir and python_script.
        pathlibcutoff: JSON files stamped before this are ignored.
        rawlog: True suppresses veny's own commentary.

    Returns:
        The previous run's options, or None when there is no usable last-used
        JSON in the script's directory.
    """
    return last_used.load_last_used_options(
        options,
        script_dir=target.script_dir,
        python_script=target.python_script,
        pathlibcutoff=pathlibcutoff,
        rawlog=rawlog,
    )
```

Both `assert`s go for the same reason.

In `run`, replace the `options.python_command` block (lines 729-737) so it rebinds the target:

```python
    python_command = ek.find_preferred_python_version()
    target = dataclasses.replace(target, python_command=python_command)
    if python_command:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(
                "Python %s is available at: %s", ek.PY_VERSION, python_command
            )
    else:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Python %s is not available.", ek.PY_VERSION)
```

and change `run`'s signature to take the target:

```python
def run(
    options: run_options.Options,
    target: state.Target | None,
    *,
    start_time: dt.datetime | None = None,
) -> int:
```

Every `options.python_script` in `run` becomes `target.python_script`, every `options.script_args` becomes `list(target.script_args)`, every `options.timestamp` becomes `target.timestamp`, and every `options.python_command` becomes `target.python_command`. The `if options.python_script:` guard at line 765 becomes `if target is not None:`. Add `import dataclasses` to `pipeline.py`.

`setup_virtualenv` and `_probe_venv` gain a `target: state.Target` parameter and read `target.python_command` and `target.timestamp` through it.

In `src/veny/cli.py`, `main` becomes:

```python
    start_time = dt.datetime.now()
    options = Options()
    parse_arguments(options)
    options.rawlog = getattr(options.args, "rawlog", False)
    memory_handler = None
    try:
        target = pipeline.resolve_target(options.args)
        lucky_status = pipeline.feeling_lucky(
            options.args,
            target,
            options=options,
            pathlibcutoff=options.pathlibcutoff,
            rawlog=options.rawlog,
        )
        if lucky_status is not None:
            return lucky_status
        memory_handler = ek.configure_logging(
            options.my_name, log_level=options.log_mode, rawlog=options.rawlog
        )
        script_exit_code = pipeline.run(options, target, start_time=start_time)
```

The `options.script_args = getattr(options.args, "script_args", [])` line goes — `Target` owns them now.

- [ ] **Step 6: Delete the drained fields from `Options`**

In `src/veny/run_options.py`, delete these five lines from `__init__`:

```python
        self.python_command: str = ""
        self.python_script: Path | None = None
        self.script_name: str = ""  # python_script without the .py extension
        self.script_dir: Path | None = None
        self.script_args: list[str] = []
```

Also delete `self.timestamp` — `Target` owns it. `script_name` is design amendment 3: written once to `""`, never read.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pixi run test tests/test_state_values.py -v`
Expected: PASS.

Run: `pixi run test`
Expected: PASS. Tests that set `options.python_script` directly must be repointed to build a `Target`; that is the intended breakage, not collateral damage.

- [ ] **Step 8: Commit**

```bash
git add src/veny/state.py src/veny/pipeline.py src/veny/cli.py \
  src/veny/run_options.py tests/test_state_values.py tests/
git commit -m "refactor: give the run a frozen Target instead of four Options fields"
```

---

### Task 3: Widen `Settings` and build it once

**Goal:** `Settings` carries all ten run invariants, is constructed exactly once per run, and is handed to both `dict_of_custom_modules` and `analysis_scan.find_imports_in_script` — closing the four dead-argument rows at `pipeline.py:125` by construction.

**Files:**
- Modify: `src/veny/settings.py`
- Modify: `src/veny/pipeline.py:98-143` (`find_imports_in_script`), `:209-244` (`split_imports`), `:468-524` (`blank_slate`), `:705-940` (`run`)
- Modify: `src/veny/cli.py` (build the `Settings`)
- Modify: `src/veny/run_options.py` (delete the ten rehomed fields and the three dead ones)
- Modify: `tests/test_state_values.py`

**Acceptance Criteria:**
- [ ] `Settings` has exactly ten fields: `my_name`, `my_dir`, `cwd`, `venv_name`, `stay_out_list`, `search_above_this_dir`, `rawlog`, `known_bad_imports`, `also_needs`, `extra_requirements_file`.
- [ ] Every collection field is immutable at the type level: `stay_out_list: tuple[str, ...]`, `known_bad_imports: frozenset[str]`, `also_needs: Mapping[str, tuple[str, ...]]`.
- [ ] `rg -c 'Settings\(' src/veny/` reports exactly **one** construction site, in `cli.py`.
- [ ] `pipeline.find_imports_in_script` no longer builds a `Settings`; it takes one.
- [ ] `Options.unusual_imports`, `Options.max_checks` and `Options.check_interval` are deleted (design amendment 2 — zero readers under `src/`).
- [ ] `Options.my_name`, `my_dir`, `cwd`, `venv_name`, `stay_out_list`, `search_above_this_dir`, `known_bad_imports`, `also_needs`, `extra_requirements_file` are deleted; `home` and `rawlog` stay (4b's).

**Verify:** `pixi run test -v` → green; `rg -c 'Settings\(' src/veny/` → `src/veny/cli.py:1`.

**Steps:**

- [ ] **Step 1: Write the failing test**

Add to `tests/test_state_values.py`:

```python
def test_settings_is_built_once_and_reaches_both_consumers(tmp_path, monkeypatch):
    """One Settings object must serve the custom-module walk and the scan.

    The bug this fails on: leaving find_imports_in_script building its own
    Settings. 3e measured four of that site's five fields dead, because the
    scanner reads only `rawlog`. Two constructions is what made them dead;
    one construction, shared, is what closes the rows.
    """
    seen = []
    monkeypatch.setattr(
        custom_modules, "dict_of_custom_modules", lambda s, **kw: seen.append(s) or {}
    )
    monkeypatch.setattr(
        analysis_scan,
        "find_imports_in_script",
        lambda s, p, **kw: seen.append(s),
    )
    ...  # drive pipeline.run through a one-line script, as in test_cli_entry_point
    assert len(seen) == 2
    assert seen[0] is seen[1]


def test_settings_collections_cannot_be_mutated_by_a_consumer():
    """A stage must not be able to add to the run's own stay-out list.

    The bug this fails on: declaring stay_out_list as list[str] and
    known_bad_imports as set[str]. Frozen dataclasses freeze the binding, not
    the object -- a consumer could still call .append and change every later
    stage's search.
    """
    settings = _a_settings()
    with pytest.raises(AttributeError):
        settings.stay_out_list.append("nope")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        settings.known_bad_imports.add("nope")  # type: ignore[attr-defined]
```

Write `_a_settings()` as a module-level helper in `tests/test_state_values.py` returning a fully-populated `Settings`; reuse it in every later test in this file.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pixi run test tests/test_state_values.py -k settings -v`
Expected: FAIL — `TypeError: Settings.__init__() got an unexpected keyword argument 'my_dir'`, and the two-construction test sees two different objects.

- [ ] **Step 3: Widen `Settings`**

Replace `src/veny/settings.py` with:

```python
"""The invariants of one veny run, fixed once and never mutated."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Run invariants that no stage may change.

    Constructed exactly once, in cli.main, and handed down. Every collection
    field is an immutable type on purpose: freezing a dataclass freezes the
    bindings, not the objects behind them, and a stage that could .append to
    stay_out_list would change what every later stage searches.

    Attributes:
        my_name:                 The installed command's name, "veny".
        my_dir:                  Where veny keeps its cached environments.
        cwd:                     The directory veny was invoked from.
        venv_name:               The prefix every cached venv folder is built
                                 from. Must not contain "-".
        stay_out_list:           Path fragments never searched for local modules.
        search_above_this_dir:   Whether to search above cwd for local modules.
        rawlog:                  Suppress veny's own commentary.
        known_bad_imports:       Names that must never be handed to pip.
        also_needs:              Import name to the further import names
                                 installing it also requires.
        extra_requirements_file: The file --reqs reads, relative to cwd.
    """

    my_name: str
    my_dir: Path
    cwd: Path
    venv_name: str
    stay_out_list: tuple[str, ...]
    search_above_this_dir: bool
    rawlog: bool
    known_bad_imports: frozenset[str]
    also_needs: Mapping[str, tuple[str, ...]]
    extra_requirements_file: str
```

- [ ] **Step 4: Build it once, in `cli.main`**

In `src/veny/cli.py`, after `parse_arguments(options)`:

```python
    run_settings = settings.Settings(
        my_name=options.my_name,
        my_dir=options.my_dir,
        cwd=options.cwd,
        venv_name=options.venv_name,
        stay_out_list=DEFAULT_STAY_OUT_LIST,
        search_above_this_dir=True,
        rawlog=getattr(options.args, "rawlog", False),
        known_bad_imports=DEFAULT_KNOWN_BAD_IMPORTS,
        also_needs=DEFAULT_ALSO_NEEDS,
        extra_requirements_file="extra_requirements.txt",
    )
```

The three `DEFAULT_*` constants move out of `Options.__init__` and become module-level constants in `settings.py`, with their existing comments carried over verbatim — including the one explaining that `also_needs` keys and values are *import* names resolved through the alias index, and the one listing the project-specific names in `known_bad_imports`:

```python
# Some imports also need other packages to be installed. Both the keys and the
# values are *import* names: they are matched against and resolved through the
# alias index, which turns e.g. "netCDF4" into pip's "netcdf4".
DEFAULT_ALSO_NEEDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "xarray": ("dask", "netCDF4", "h5netcdf"),
        "litellm": ("tenacity",),
        # NOT PIP PACKAGES: "pyautogui": ["scrot", "python3-tk"]
    }
)

# Project-specific module names that are not on PyPI and never will be. Python 2
# names and system-package cases live in stdlib_index.py instead.
DEFAULT_KNOWN_BAD_IMPORTS = frozenset(
    {
        "snakeClass",
        "GPUampcor",
        "pathfinding_salvo_rework",
        "DQN",
        "bayesOpt",
        "non_existent_module",
    }
)

# Directories to stay out of when searching for local custom imports, because
# they are full of standard library modules or other irrelevant files.
DEFAULT_STAY_OUT_LIST = (
    "myenv",
    ".venv",
    "anaconda3",
    "miniconda3",
    "miniforge3",
    ".conda",
    os.sep + "lib" + os.sep,
    ".vscode",
)
```

`settings.py` gains `import os` and `from types import MappingProxyType`. `MappingProxyType` is what makes `also_needs.add`/`__setitem__` raise rather than silently succeed.

- [ ] **Step 5: Thread it through `pipeline`**

`run` takes `settings_: settings.Settings` as its second positional parameter (name it to avoid shadowing the module — or import the class directly as `from .settings import Settings` and call the parameter `settings`; pick one and keep it consistent across the file). Delete the `Settings(...)` construction at lines 789-794 and pass the parameter to `custom_modules.dict_of_custom_modules`. `find_imports_in_script` becomes:

```python
def find_imports_in_script(
    settings: Settings,
    scan: ImportScan,
    first_path: str | os.PathLike[str],
    *,
    is_stdlib: Callable[[str], bool],
) -> None:
    """Scan a script for imports, accumulating into the given ImportScan.

    The scan is mutated in place, not returned: analysis/scan.py only ever
    calls .add / .append / d[k] = v on it and never rebinds a field, and
    dict_of_custom_modules() has already seeded scan.custom_modules before
    this is reached. Seeding is why the scan is passed in rather than built
    here.

    Args:
        settings: The run's invariants; the scanner reads rawlog.
        scan:     The accumulator to write into.
        first_path: The script to scan.
        is_stdlib: Predicate answering whether a name is standard library.
    """
    analysis_scan.find_imports_in_script(
        settings, first_path, is_stdlib=is_stdlib, scan=scan
    )
```

Every `options.rawlog` inside `pipeline.py` becomes `settings.rawlog`; `options.my_dir` becomes `settings.my_dir`; `options.venv_name` becomes `settings.venv_name`; `options.extra_requirements_file` becomes `settings.extra_requirements_file`; `options.known_bad_imports` and `options.also_needs` become `settings.known_bad_imports` and `settings.also_needs` (converting `also_needs` values to `list` at the `classify.split_imports` boundary if that signature wants lists — check `classify.split_imports`'s annotation and match it rather than guessing).

`blank_slate` takes `(args, settings)` and reads `settings.my_name`, `settings.my_dir`, `settings.cwd`.

- [ ] **Step 6: Delete the rehomed and dead fields from `Options`**

From `run_options.py`'s `__init__`, delete: `my_name`, `my_dir`, `cwd`, `venv_name`, `stay_out_list`, `search_above_this_dir`, `known_bad_imports`, `also_needs`, `extra_requirements_file`, `unusual_imports`, `max_checks`, `check_interval`. Keep `home` (still derives `my_dir` for the caller), `log_mode`, `rawlog`, `pathlibcutoff`, `options_json_filepath`, `stdlib`, `aliases`.

`Options.__init__` can no longer compute `my_dir` from `my_name`; move that derivation into `cli.main`:

```python
    my_dir = options.home / "veny"
```

and note in `run_options.py`'s docstring that `tests/test_options_surface.py:37` asserted `options.my_dir == options.home / options.my_name` — that assertion moves onto the `Settings` construction in `cli.py`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pixi run test tests/test_state_values.py -k settings -v`
Expected: PASS.

Run: `pixi run test` and `rg -c 'Settings\(' src/veny/`
Expected: green, and exactly one construction site.

- [ ] **Step 8: Commit**

```bash
git add src/veny/settings.py src/veny/cli.py src/veny/pipeline.py \
  src/veny/run_options.py tests/
git commit -m "refactor: widen Settings to the run's ten invariants and build it once"
```

---

### Task 4: `ImportScan` as the scan's product

**Goal:** `list_packages` builds one `ImportScan`, seeds it with the custom-module dict, hands it to the scanner and returns it. The seven scan fields leave `Options`.

**Files:**
- Modify: `src/veny/pipeline.py:98-160` (`find_imports_in_script`, `warn_about_system_packages`), `:246-312` (`list_packages`), `:527-551` (`report`), `:705-940` (`run`)
- Modify: `src/veny/run_options.py` (delete the seven fields)
- Modify: `tests/test_split_imports.py`, `tests/test_import_discovery.py`

**Acceptance Criteria:**
- [ ] `list_packages(settings, target, scan, *, is_stdlib) -> ImportScan` returns the scan it filled.
- [ ] The scan is seeded with `custom_modules` before the walk: a test proves that a custom module found by `dict_of_custom_modules` is visible to the scanner.
- [ ] `warn_about_system_packages(scan)` takes the scan.
- [ ] `report` takes the scan and the `Requirements` (Task 5 lands the second half).
- [ ] `Options.all_imports`, `custom_modules`, `loaded_custom_modules`, `samedir_files`, `subfolders`, `sys_path_hints`, `seen_stdlib_imports` are deleted.
- [ ] `rg -n 'ImportScan\(' src/veny/pipeline.py` reports exactly **one** site.

**Verify:** `pixi run test tests/test_split_imports.py tests/test_import_discovery.py -v` → green.

**Steps:**

- [ ] **Step 1: Write the failing test**

Add to `tests/test_import_discovery.py`:

```python
def test_the_scan_is_seeded_with_the_custom_modules_before_it_walks(tmp_path):
    """dict_of_custom_modules fills custom_modules; the scanner must see it.

    The bug this fails on: constructing a fresh ImportScan inside
    list_packages instead of threading the seeded one through. The scanner
    resolves a local import by looking the name up in scan.custom_modules; an
    empty dict makes every local module look like a PyPI package, and veny
    would try to pip install the user's own file.
    """
    helper = tmp_path / "my_helper.py"
    helper.write_text("VALUE = 1\n")
    script = tmp_path / "s.py"
    script.write_text("import my_helper\n")

    settings = _a_settings(cwd=tmp_path)
    target = pipeline.resolve_target(
        argparse.Namespace(script=str(script), script_args=[])
    )
    assert target is not None
    scan = ImportScan(custom_modules={"my_helper": helper})
    result = pipeline.list_packages(
        settings, target, scan, is_stdlib=lambda name: False
    )
    assert "my_helper" in result.loaded_custom_modules
    assert result is scan


def test_list_packages_returns_the_scan_rather_than_writing_to_options(tmp_path):
    """The scan is a return value now, not a write onto a handed-in object.

    The bug this fails on: keeping the copy-back onto Options. That is the
    accumulator shape phase 4 removes -- with it in place, two stages can
    disagree about what the scan found and the later one silently wins.
    """
    script = tmp_path / "s.py"
    script.write_text("import os\nimport nonexistent_thing\n")
    ...  # drive list_packages as above
    assert "nonexistent_thing" in result.all_imports
    assert not hasattr(cli.Options(), "all_imports")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pixi run test tests/test_import_discovery.py -k "seeded or returns_the_scan" -v`
Expected: FAIL — `list_packages` takes an `Options` and returns `None`.

- [ ] **Step 3: Rewrite `list_packages`**

```python
def list_packages(
    settings: Settings,
    target: state.Target,
    scan: ImportScan,
    *,
    is_stdlib: Callable[[str], bool],
) -> ImportScan:
    """Scan the target script for imports and return what was found.

    Args:
        settings: The run's invariants.
        target:   What is being run.
        scan:     The accumulator, already seeded with the custom-module dict.
        is_stdlib: Predicate answering whether a name is standard library.

    Returns:
        The same ImportScan, filled. Returned as well as mutated so that
        callers read a value rather than reaching back into what they passed.

    Raises:
        UsageError: The target is not a Python script veny can read.
    """
    python_file = target.python_script
    if not ek.safe_is_file(python_file) or not ek.is_python_script(python_file):
        raise UsageError(f"'{os.fspath(python_file)}' is not a valid Python script.")
    if not settings.rawlog:
        logging.info("Processing a single Python script: %s", os.fspath(python_file))
    find_imports_in_script(settings, scan, python_file, is_stdlib=is_stdlib)
    # Filter out invalid imports before splitting.
    scan.all_imports = {
        imp for imp in scan.all_imports if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", imp)
    }
    return scan
```

`split_imports` is no longer called from inside `list_packages` — `run` calls it next, which is Task 5's shape. Note the one field that *is* rebound here rather than mutated in place: `all_imports`. That is safe because the scanner has finished by then; do not move the filter earlier.

`warn_about_system_packages` becomes:

```python
def warn_about_system_packages(scan: ImportScan) -> None:
    """Warn once for each standard-library import that needs an OS package.

    Args:
        scan: The run's ImportScan; reads seen_stdlib_imports.
    """
    for name, system_package in stdlib_index.hints_for(
        scan.seen_stdlib_imports
    ).items():
        logging.warning(
            "%s is in the standard library but needs the %s system package "
            "before it will import.",
            name,
            system_package,
        )
```

- [ ] **Step 4: Seed and call it from `run`**

In `run`, replace the `dict_of_custom_modules` block and the `list_packages(options)` call:

```python
    scan = ImportScan(
        custom_modules=custom_modules.dict_of_custom_modules(
            settings,
            use_cache=not getattr(args, "rc", False)
            and not getattr(args, "no_cache", False),
        )
    )
    time2 = dt.datetime.now()
    ...
    scan = list_packages(settings, target, scan, is_stdlib=stdlib.__contains__)
```

- [ ] **Step 5: Delete the seven fields from `Options`**

From `run_options.py`'s `__init__`, delete `all_imports`, `custom_modules`, `loaded_custom_modules`, `samedir_files`, `subfolders`, `sys_path_hints`, `seen_stdlib_imports`, and `total_imports` (design amendment 4 — written at the old `pipeline.py:244`, read nowhere).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pixi run test tests/test_import_discovery.py tests/test_split_imports.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/veny/pipeline.py src/veny/run_options.py tests/
git commit -m "refactor: return the ImportScan instead of writing seven fields onto Options"
```

---

### Task 5: `Requirements` as the classification product

**Goal:** `split_imports` returns the `Requirements` `classify` already produces, the copy-back onto `Options` goes, and every downstream reader takes the value.

**Files:**
- Modify: `src/veny/pipeline.py:209-244` (`split_imports`), `:527-551` (`report`), `:581-702` (`setup_virtualenv`), `:705-940` (`run`)
- Modify: `src/veny/run_options.py` (delete `bad_imports`, `uninstalled_imports`, `extra_requirements`)
- Modify: `tests/test_split_imports.py`, `tests/test_classify.py`, `tests/test_manifest_writing.py`

**Acceptance Criteria:**
- [ ] `pipeline.split_imports(settings, scan, *, args, aliases, extra_requirements, probe) -> state.Requirements` — no copy-back, no `Options`.
- [ ] `report(settings, scan, requirements)` reads `requirements.uninstalled`, `requirements.bad`, `scan.samedir_files`, `scan.subfolders`.
- [ ] `setup_virtualenv` returns `tuple[state.Requirements, state.VenvHandle | None, bool]` — the repaired requirements, the handle, and whether the install succeeded — instead of mutating `options.uninstalled_imports` and `options.install_succeeded`. (The `VenvHandle` half lands in Task 6; until then return the handle as `None` and keep the existing `set_venv_dir` calls.)
- [ ] `verify.verify_and_repair_imports`' result is folded back with `dataclasses.replace(requirements, uninstalled=frozenset(...))`, never by assignment.
- [ ] `Options.bad_imports`, `Options.uninstalled_imports` and `Options.extra_requirements` are deleted.
- [ ] A test proves the replace is a rebind, not a mutation: the pre-repair `Requirements` still holds the pre-repair `uninstalled` set.

**Verify:** `pixi run test tests/test_split_imports.py tests/test_classify.py -v` → green.

**Steps:**

- [ ] **Step 1: Write the failing test**

Add to `tests/test_split_imports.py`:

```python
def test_repairing_imports_rebinds_rather_than_mutating_requirements(tmp_path):
    """verify_and_repair_imports' result must produce a NEW Requirements.

    The bug this fails on: `requirements.uninstalled = frozenset(repaired)` --
    which a frozen dataclass refuses -- or reaching around it with
    object.__setattr__, which it does not. Under a mutation, the manifest
    written before the repair and the check run after it would silently
    describe the same object, and a repair that changed nothing would be
    indistinguishable from one that changed everything.
    """
    before = state.Requirements(
        all_imports=frozenset({"cv2"}),
        bad=frozenset(),
        installed=frozenset(),
        uninstalled=frozenset({ResolvedImport(import_name="cv2", pip_name="cv2")}),
        seen_stdlib=frozenset(),
        extra_requirements={},
    )
    after = dataclasses.replace(
        before,
        uninstalled=frozenset(
            {ResolvedImport(import_name="cv2", pip_name="opencv-python")}
        ),
    )
    assert {r.pip_name for r in before.uninstalled} == {"cv2"}
    assert {r.pip_name for r in after.uninstalled} == {"opencv-python"}
    assert before is not after


def test_split_imports_returns_requirements_and_writes_nothing_back(tmp_path):
    """Classification's product is a return value, not four Options writes.

    The bug this fails on: keeping the copy-back at the old pipeline.py:241-244.
    That copy-back turned each frozenset back into a set specifically so a
    later stage could mutate it -- exactly the accumulator shape the design
    calls out ("ImportScan and Requirements are values, not accumulators").
    """
    ...  # drive pipeline.split_imports with a stub probe, as test_classify does
    assert isinstance(result, state.Requirements)
    assert not hasattr(cli.Options(), "uninstalled_imports")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pixi run test tests/test_split_imports.py -k "rebinds or writes_nothing_back" -v`
Expected: FAIL — `pipeline.split_imports` returns `None`.

- [ ] **Step 3: Rewrite `split_imports`**

```python
def split_imports(
    settings: Settings,
    scan: ImportScan,
    *,
    args: argparse.Namespace,
    aliases: alias_index.AliasIndex,
    extra_requirements: Mapping[str, str | None],
    probe: AbstractContextManager[Callable[[str], bool]],
) -> state.Requirements:
    """Classify the scan's imports and return the result.

    Args:
        settings: The run's invariants; supplies known_bad_imports, also_needs
            and rawlog.
        scan: What the scan found.
        args: The parsed command line; reads --reqs.
        aliases: The alias index. Mutable and injected by design -- it is a
            cache with disk backing plus a session-rejection store.
        extra_requirements: The --reqs file's entries, or {}.
        probe: The throwaway environment classification asks "is this
            importable already?" in.

    Returns:
        What classification decided. A value: nothing downstream writes to it.
    """
    return classify.split_imports(
        scan,
        aliases=aliases,
        known_bad_imports=set(settings.known_bad_imports),
        also_needs={k: list(v) for k, v in settings.also_needs.items()},
        extra_requirements=extra_requirements,
        use_reqs=getattr(args, "reqs", False),
        probe=probe,
        rawlog=settings.rawlog,
    )
```

Match `classify.split_imports`' actual annotations for `known_bad_imports` and `also_needs`; if it already accepts `frozenset` and `Mapping[str, Sequence[str]]`, drop the two conversions rather than widening them.

- [ ] **Step 4: Repoint the downstream readers**

`report(settings, scan, requirements)`:

```python
def report(
    settings: Settings, scan: ImportScan, requirements: state.Requirements
) -> None:
    """Log what the run is about to install and what it refused to.

    Args:
        settings: The run's invariants; reads rawlog.
        scan: What the scan found; reads samedir_files and subfolders.
        requirements: What classification decided; reads uninstalled and bad.
    """
    if settings.rawlog:
        return
    logging.info(
        "Packages to install: %s",
        sorted(record.import_name for record in requirements.uninstalled),
    )
    if requirements.bad:
        logging.warning("Bad imports: %s", set(requirements.bad))
    if scan.samedir_files:
        logging.info(
            "Imported files in the same directory: %s",
            list(map(os.fspath, scan.samedir_files)),
        )
    if scan.subfolders:
        logging.info("Imported subfolders: %s", scan.subfolders)
```

The early return replaces four separate `if not options.rawlog` guards. Confirm against the original that nothing outside those guards ran — at `pipeline.py:535` the whole body is already inside one, so this is a shape change and not a behaviour change.

In `setup_virtualenv`, replace `options.uninstalled_imports = set(verify.verify_and_repair_imports(...))` with:

```python
    requirements = dataclasses.replace(
        requirements,
        uninstalled=frozenset(
            verify.verify_and_repair_imports(
                venv_python=handle.venv_python,
                requirements_file=handle.requirements_file,
                uninstalled=set(requirements.uninstalled),
                extra_requirements=requirements.extra_requirements,
                source_names=source_names,
                index=aliases,
                rawlog=settings.rawlog,
            )
        ),
    )
```

and return the new value. Every `options.extra_requirements` becomes `requirements.extra_requirements`; every `options.all_imports` in a `verify.source_import_names(...)` call becomes `requirements.all_imports`.

In `run`, the `--reqs` block builds the mapping *before* classification and passes it in, rather than writing it onto `options`:

```python
    extra_requirements: Mapping[str, str | None] = {}
    if getattr(args, "reqs", False):
        extra_requirements = environment.parse_extra_requirements(
            settings.extra_requirements_file, rawlog=settings.rawlog
        )
        if not settings.rawlog:
            logging.info(
                "Loaded extra requirements from ./%s: %s",
                settings.extra_requirements_file,
                extra_requirements,
            )
```

- [ ] **Step 5: Delete the three fields from `Options`**

From `run_options.py`'s `__init__`, delete `bad_imports`, `uninstalled_imports` and `extra_requirements`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pixi run test tests/test_split_imports.py tests/test_classify.py tests/test_manifest_writing.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/veny/pipeline.py src/veny/run_options.py tests/
git commit -m "refactor: return Requirements from classification instead of copying it back"
```

---

### Task 6: `VenvHandle` replaces `set_venv_dir`

**Goal:** The three venv-derived paths become one frozen value with a factory, `Options.set_venv_dir` and its five call sites go, and `install_succeeded` becomes a return value.

**Files:**
- Modify: `src/veny/state.py` (add `VenvHandle`)
- Modify: `src/veny/pipeline.py:581-702` (`setup_virtualenv`), `:705-940` (`run`)
- Modify: `src/veny/run_options.py` (delete `venv_dir`, `venv_python`, `requirements_file`, `install_succeeded`, `set_venv_dir`)
- Modify: `tests/test_state_values.py`, `tests/test_venv_naming.py`, `tests/test_rename_venv.py`, `tests/test_uv_backend.py`

**Acceptance Criteria:**
- [ ] `state.VenvHandle` is frozen with exactly `venv_dir`, `venv_python`, `requirements_file`, and a `for_dir` classmethod that does the `mkdir(parents=True, exist_ok=True)` `set_venv_dir` did.
- [ ] `venv_python` is `venv_dir / "bin" / "python"` and is **not** `.resolve()`d — resolving that symlink is what breaks a venv interpreter into its base interpreter, and `set_venv_dir` carried a "Do NOT resolve() this symlink path" comment for that reason. A test pins it.
- [ ] `Options.set_venv_dir` no longer exists; `rg -n 'set_venv_dir' src/ tests/` returns nothing. **This closes PROGRESS.md's "`run_options.py` has never been through the STANDING CHECK" item — all five of its argument-carrying call sites were inside `set_venv_dir` and are deleted here.**
- [ ] `setup_virtualenv` returns `(requirements, handle, install_succeeded)`; `run` decides the rename from the returned flag rather than from an `Options` field.
- [ ] The "failed-" rename still happens only when the script ran *and* the install succeeded, and still goes through `cache_search.rename_venv`.
- [ ] The requirements file is still written **after** `environment.create_venv` succeeds, never before. A test pins the ordering.

**Verify:** `pixi run test tests/test_uv_backend.py tests/test_venv_naming.py tests/test_state_values.py -v` → green.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_state_values.py`:

```python
def test_venv_handle_does_not_resolve_the_interpreter_symlink(tmp_path):
    """venv_python must stay inside the venv, symlink and all.

    The bug this fails on: calling .resolve() on venv_dir / "bin" / "python".
    In a real venv that symlink points at the base interpreter, so a resolved
    path runs the system python with none of the venv's packages -- every
    installed requirement would look missing at run time.
    """
    handle = state.VenvHandle.for_dir(tmp_path / "myenv-py312-20260821-120000")
    assert handle.venv_python.parent.parent == handle.venv_dir
    assert handle.venv_python.name == "python"
    assert handle.requirements_file == handle.venv_dir / "requirements.txt"


def test_venv_handle_creates_the_directory(tmp_path):
    """for_dir must mkdir, as set_venv_dir did.

    The bug this fails on: dropping the mkdir. `uv venv` needs the directory
    to exist-and-be-empty; without the mkdir the later requirements write
    fails with FileNotFoundError instead.
    """
    target_dir = tmp_path / "does" / "not" / "exist" / "yet"
    handle = state.VenvHandle.for_dir(target_dir)
    assert handle.venv_dir.is_dir()


def test_venv_handle_is_frozen(tmp_path):
    """The three paths are derived together and must move together.

    The bug this fails on: a mutable VenvHandle, which would let a caller
    repoint venv_dir after a rename while venv_python still names the old
    path -- the exact drift set_venv_dir's three coupled writes existed to
    prevent.
    """
    handle = state.VenvHandle.for_dir(tmp_path / "v")
    with pytest.raises(dataclasses.FrozenInstanceError):
        handle.venv_dir = tmp_path / "other"  # type: ignore[misc]
```

Add to `tests/test_uv_backend.py`:

```python
def test_the_requirements_file_is_written_only_after_the_venv_exists(tmp_path, monkeypatch):
    """`uv venv` refuses a non-empty directory, so ordering is load-bearing.

    The bug this fails on: moving the write_requirements_file_with_extras call
    above environment.create_venv. That made every fresh build crash with
    CalledProcessError -- the venv directory already existed (for_dir mkdirs
    it) and now had a file in it.
    """
    order = []
    monkeypatch.setattr(
        environment, "create_venv", lambda d, i: order.append("create") or True
    )
    monkeypatch.setattr(
        environment,
        "write_requirements_file_with_extras",
        lambda *a, **kw: order.append("write"),
    )
    ...  # drive pipeline.setup_virtualenv
    assert order == ["create", "write"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run test tests/test_state_values.py -k venv_handle -v`
Expected: FAIL — `AttributeError: module 'veny.state' has no attribute 'VenvHandle'`.

- [ ] **Step 3: Add `VenvHandle`**

Append to `src/veny/state.py`:

```python
@dataclass(frozen=True)
class VenvHandle:
    """One virtual environment, and the two paths derived wholly from it.

    Frozen because the three paths must move together: repointing venv_dir
    after a rename while venv_python still names the old directory is exactly
    the drift Options.set_venv_dir's three coupled writes existed to prevent.
    A rename produces a new handle via for_dir, never an edit to this one.

    Attributes:
        venv_dir:          The environment's directory.
        venv_python:       Its interpreter. NOT resolved -- see for_dir.
        requirements_file: The requirements.txt written inside it.
    """

    venv_dir: Path
    venv_python: Path
    requirements_file: Path

    @classmethod
    def for_dir(cls, venv_dir: str | os.PathLike[str]) -> VenvHandle:
        """Derive a handle from a venv directory, creating the directory.

        The mkdir is not incidental: `uv venv` needs the directory to exist
        and be empty, which is also why nothing may write into it until
        environment.create_venv has succeeded.

        Args:
            venv_dir: Where the environment lives, or will.

        Returns:
            The handle for that directory.
        """
        p = ek.ensure_path(venv_dir)
        p.mkdir(parents=True, exist_ok=True)
        return cls(
            venv_dir=p,
            # Do NOT resolve() this symlink path: in a real venv it points at
            # the base interpreter, and a resolved path runs the system python
            # with none of the venv's packages.
            venv_python=p / "bin" / "python",
            requirements_file=p / "requirements.txt",
        )
```

`state.py` gains `import os`, `from __future__ import annotations` (for the `-> VenvHandle` self-reference) and `import emmykit as ek`.

- [ ] **Step 4: Rewrite `setup_virtualenv` around it**

The signature becomes:

```python
def setup_virtualenv(
    settings: Settings,
    target: state.Target,
    requirements: state.Requirements,
    *,
    args: argparse.Namespace,
    aliases: alias_index.AliasIndex,
    stdlib: stdlib_index.StdlibIndex,
) -> tuple[state.Requirements, state.VenvHandle | None, bool]:
```

Returns: the repaired requirements, the handle (`None` if `uv` refused to build), and whether every requirement installed. Inside, replace the three `set_venv_dir` calls:

```python
    handle = state.VenvHandle.for_dir(settings.my_dir / f"failed-{folder_name}")
```

```python
    handle = state.VenvHandle.for_dir(
        cache_search.record_venv_state(
            handle.venv_dir,
            venv_python=handle.venv_python,
            venv_name=settings.venv_name,
            timestamp=target.timestamp,
            run_tag=run_tag,
            python_command=target.python_command,
            uninstalled=set(requirements.uninstalled),
            extra_requirements=requirements.extra_requirements,
            rawlog=settings.rawlog,
        )
    )
```

Every `assert options.venv_dir is not None` / `assert options.requirements_file is not None` / `assert options.venv_python is not None` goes — the handle's fields are non-optional, which is the point. That includes the pair at the old lines 664-667 that the code called "load-bearing" for mypy's narrowing: with a non-optional `Path` there is nothing to narrow.

The final `return verify.check_packages_in_venv(...)` becomes part of the tuple:

```python
    all_importable = verify.check_packages_in_venv(
        environment.venv_python_for(handle.venv_dir),
        uninstalled=set(requirements.uninstalled),
        source_names=source_names,
    )
    return requirements, (handle if all_importable else None), install_succeeded
```

Read that last line carefully against the original: `setup_virtualenv` returned `False` — which `run` treated as "failed to create a virtual environment" — when either `uv` refused *or* the final import check failed. Returning `None` for the handle in both cases preserves that. `install_succeeded` is returned separately because `run` needs it for the rename decision even on the success path.

- [ ] **Step 5: Rewrite `run`'s venv block**

```python
        if match_dir is None:
            if not settings.rawlog:
                logging.info(
                    "Creating new virtual environment '%s'...", settings.venv_name
                )
            requirements, handle, install_succeeded = setup_virtualenv(
                settings, target, requirements, args=args, aliases=aliases, stdlib=stdlib
            )
            if handle is None:
                # This was emmykit's critical-error helper, called with
                # choose_breakpoint=True: it logged this same message at this
                # same level and then opened a pdb prompt -- a debugger in the
                # user's face on a failed build, and a BdbQuit traceback
                # wherever stdin is not a tty. The status below is the whole of
                # what veny needed from it, and cli.main owns the exit. (Named
                # obliquely on purpose: the phase's exit sweep greps this tree
                # for that helper's name.)
                logging.critical("Failed to create a virtual environment.")
                script_exit_code = 1
        else:
            if not settings.rawlog:
                logging.info("Using existing virtual environment: %s", match_dir)
            handle = state.VenvHandle.for_dir(match_dir)
            install_succeeded = False
```

and the rename:

```python
            if handle.venv_dir.name.startswith("failed-") and install_succeeded:
                # The program made it here, so the venv did NOT fail and can
                # drop its prefix.
                handle = state.VenvHandle.for_dir(
                    cache_search.rename_venv(
                        handle.venv_dir,
                        handle.venv_dir.name.removeprefix("failed-"),
                    )
                )
```

`install_succeeded = False` on the cache-hit branch preserves the original: a reused venv never has a `failed-` prefix (the cache search only offers folders that dropped it), and `options.install_succeeded` was still `False` there because `setup_virtualenv` never ran. If a test proves otherwise, follow the test.

- [ ] **Step 6: Delete `set_venv_dir` and the four fields**

From `run_options.py`, delete `venv_dir`, `venv_python`, `requirements_file`, `install_succeeded` and the whole `set_venv_dir` method.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pixi run test tests/test_state_values.py tests/test_uv_backend.py tests/test_venv_naming.py tests/test_rename_venv.py -v`
Expected: PASS.

Run: `rg -n 'set_venv_dir' src/ tests/`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add src/veny/state.py src/veny/pipeline.py src/veny/run_options.py tests/
git commit -m "refactor: replace set_venv_dir with a frozen VenvHandle"
```

---

### Task 7: Drain the last transitional readers and repoint the suite

**Goal:** Nothing in `pipeline.py` reads or writes `Options` except the two persistence calls, and every test that reached a drained field now builds the value instead.

**Files:**
- Modify: `src/veny/pipeline.py` (whole file — the final sweep)
- Modify: `src/veny/run_options.py` (docstring: state exactly what is left and why)
- Modify: every test file that still references a drained field

**Acceptance Criteria:**
- [ ] `rg -n 'options\.' src/veny/pipeline.py` returns **only** lines inside `_load_last_used` and the `ek.save_options_to_json(options)` call.
- [ ] `Options` retains exactly: `args`, `home`, `log_mode`, `rawlog`, `pathlibcutoff`, `options_json_filepath`, `stdlib`, `aliases`. Anything else is a leftover — delete it or write down why it survived.
- [ ] `run_options.py`'s module docstring names 4b as the plan that deletes the file, and lists what is left.
- [ ] `pixi run test` is green with **no** test asserting a drained `Options` attribute exists.
- [ ] `tests/test_options_surface.py` tests the values, not the god object; rename it in the same commit if its name has stopped describing it.

**Verify:** `pixi run test` → green; `rg -c 'options\.' src/veny/pipeline.py` → 8 or fewer.

**Steps:**

- [ ] **Step 1: Find what is left**

```bash
rg -n 'options\.' src/veny/pipeline.py
rg -n '\bcli\.Options\b|\bveny\.Options\b' tests/ src/
```

Record both counts in the commit message. The second is 4b's headline number and it must be **re-derived**, not copied: 3e's PROGRESS entry predicted 42 and the real figure at `08622a8` was 69; re-measured on `main` on 2026-08-21 it is 49 `cli.Options` (one of which is `cli.py`'s own re-export) plus 28 `veny.Options` (one of which, `tests/test_json_types.py:174`, is a comment, not a reference). Seven test files alias with `from veny import cli as veny`; check for other aliases with `rg -n 'import cli as (\w+)' tests/` rather than trusting any list.

- [ ] **Step 2: Repoint each remaining test**

For each failing test, the fix is mechanical and always the same shape: replace `options = cli.Options(); options.<field> = X` with a direct construction of the value that now owns `<field>`. Use `_a_settings()` from `tests/test_state_values.py` for `Settings` and add sibling helpers `_a_target()` and `_a_requirements()` there, exported for the other test modules to import. Do **not** add a `conftest.py` fixture for these — an explicit constructor call in the test body is what makes a test say what it exercises, which is the whole point of the phase.

- [ ] **Step 3: Rewrite `run_options.py`'s docstring**

```python
"""What is left of the per-run state object, and why.

Phase 4a drained every field the pipeline read or wrote into the frozen
Settings, Target, Requirements and VenvHandle values, and into the mutable
ImportScan the analysis layer accumulates. What remains is here for one
reason: `ek.save_options_to_json` and `last_used.load_last_used_options` are
typed against `ek.Options`, so persistence is still coupled to the class
rather than to a payload.

Phase 4b breaks that coupling -- veny writes its own LastUsed record -- and
deletes this file, the `cli.Options` re-export, and the test references in
both spellings. Nothing new goes in here.
"""
```

- [ ] **Step 4: Run the full suite**

Run: `pixi run test`
Expected: PASS.

Run: `pixi run lint && pixi run python -m ruff format --check . && pixi run typecheck`
Expected: lint clean, format clean, typecheck **no worse than 29 errors in 7 files**. Record the real number.

- [ ] **Step 5: Commit**

```bash
git add src/veny/ tests/
git commit -m "refactor: leave Options only where persistence still needs it"
```

---

### Task 8: The STANDING CHECK and the wiring index

**Goal:** Every argument at every call site this plan changed is measured — is it read by the callee, and is there a test that fails if it is wrong — and the result is written down argument by argument.

**Files:**
- Create: `docs/superpowers/plans/2026-08-21-state-model-values-wiring-index.md`
- Modify: whatever tests the sweep proves are missing

**Acceptance Criteria:**
- [ ] Every call site in `cli.py`, `pipeline.py` and `state.py` that this plan created or changed appears in the index, one row per argument.
- [ ] Each row records: site, argument, whether the callee reads it, and the named test that fails if the value is wrong — or **OPEN HOLE** with a reason.
- [ ] `state.VenvHandle.for_dir`'s call sites are in the index. 3e's sweep never covered `run_options.py`, so `set_venv_dir`'s five argument-carrying sites were counted in no number anywhere; their replacements are counted here. **Say so explicitly in the index's preamble** — this closes that PROGRESS.md item.
- [ ] Any argument measured DEAD is listed separately from the open holes, so the headline reads "N holes **plus** M dead arguments" rather than blurring them.
- [ ] Every OPEN HOLE that a test *can* close, is closed in this task. Ones that cannot are recorded with the reason.

**Verify:** `pixi run test` → green, with the new tests included; the index's row count matches `rg -c` over the changed call sites.

**Steps:**

- [ ] **Step 1: Enumerate the sites**

```bash
git diff main --stat
git diff main -- src/veny/ | rg -n '^\+.*\('
```

Build the row list from the diff, not from memory. 3e's Task 3 symbol sweep missed a whole spelling (`veny.Options`) because it worked from a list rather than from the tree; do not repeat that.

- [ ] **Step 2: For each argument, answer both questions**

For "does the callee read it": read the callee. For "does a test fail if it is wrong": change the value at the call site to something visibly wrong, run the suite, and see what goes red. Record the test that catches it by name. If nothing goes red, it is an OPEN HOLE — or, if the callee does not read it at all, a DEAD ARGUMENT.

Revert each mutation before moving to the next. Do not batch them.

- [ ] **Step 3: Write the index**

Use `docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming-wiring-index.md` as the format. Preamble must state: what was swept, what was not, and that `VenvHandle.for_dir`'s sites are included precisely because `set_venv_dir`'s never were.

- [ ] **Step 4: Close the closable holes**

Write the missing tests. Each one must state, in its docstring, the concrete bug that makes it fail — the same standard the `test-design` skill sets and the rest of this suite already meets.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-08-21-state-model-values-wiring-index.md tests/
git commit -m "docs: add the phase 4a wiring index, measured argument by argument"
```

---

### Task 9: The differential

**Goal:** A script that drives the same inputs through `main()` in both trees and reduces the whole plan to a small, inspectable diff — and that is proved able to fail.

**Files:**
- Create: `scripts/differential_4a.py`

**Acceptance Criteria:**
- [ ] Modelled on `scripts/differential_3e.py` — read it first and match its layer structure and output format.
- [ ] Drives at least these layers: `--justprint` on a script with no third-party imports; `--justprint` on a script with one; `--blank-slate -y`; `--reqs`; a plain run that hits the cache; `--feeling-lucky` with no last-used record; and **a directory argument** (Task 1's sanctioned change — it must show up in the diff as a status-2 line, not as a traceback).
- [ ] Uses `git worktree add` for the baseline tree at `4d1846c`. **Never** `git checkout <sha>` inside the working tree — the user's CLAUDE.md records a 2026-07-02 incident where that left a mixed tree and silently restored deleted files.
- [ ] Mutation-tested: introduce at least four deliberate regressions, one per value object, and record that each grew the diff. A differential that cannot fail proves nothing.
- [ ] The residual-risk list is written into the script's docstring **and** into `PROGRESS.md` in Task 10 — every input the differential does not drive.

**Verify:** `pixi run python scripts/differential_4a.py` → prints the diff and its line count; the four mutation runs each produce a strictly larger diff than the clean run.

**Steps:**

- [ ] **Step 1: Read the 3e differential**

```bash
sed -n '1,120p' scripts/differential_3e.py
```

Match its shape. It reduced a ten-task phase to 37 lines; the target here is the same order of magnitude, and the sanctioned change from Task 1 should be the visible part of it.

- [ ] **Step 2: Build the baseline worktree**

```bash
git worktree add /tmp/veny-4a-baseline 4d1846c
```

Remove it when done: `git worktree remove /tmp/veny-4a-baseline`.

- [ ] **Step 3: Write the script, run it, record the clean diff**

- [ ] **Step 4: Mutation-test it**

Four regressions, one per value:
1. `Target`: drop the `dataclasses.replace` that fills `python_command`, so venvs build against `""`.
2. `Settings`: build a second `Settings` inside `find_imports_in_script` with `rawlog=False` hardcoded.
3. `Requirements`: skip the `dataclasses.replace` after `verify_and_repair_imports`, so repairs are lost.
4. `VenvHandle`: `.resolve()` the interpreter path in `for_dir`.

Each must grow the diff. Record the four line counts. Revert each before the next.

- [ ] **Step 5: Commit**

```bash
git add scripts/differential_4a.py
git commit -m "test: add the phase 4a differential and prove it can fail"
```

---

### Task 10: Close the phase

**Goal:** Gates measured on the branch, `PROGRESS.md` updated with what this plan learned, and the next session pointed at 4b.

**Files:**
- Modify: `PROGRESS.md`
- Modify: `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md` (if an amendment contradicts it, say so there too)
- Modify: `README.md` (if `veny <directory>` was documented anywhere)

**Acceptance Criteria:**
- [ ] All four gates re-measured **in this session**, on this branch, with the numbers pasted from the terminal — not copied from a task report and not from `main`.
- [ ] `PROGRESS.md`'s **Current work** block points at 4b as the next action, names this plan's merge commit, and lists what 4b inherits.
- [ ] The five design amendments from this plan's preamble are recorded in `PROGRESS.md`, numbered on from 3e's last.
- [ ] The retired items are struck from Deferred items, not duplicated: the folder-scanning ruling (**decided and executed**), the `run_options.py` STANDING CHECK gap (**closed by Task 6 + Task 8**), latent defect 2 (**fixed by Task 1**), and the four `pipeline.py:125` dead-argument rows (**closed by construction, Task 3**).
- [ ] What this plan did **not** do stays in Deferred items with its owner named: the in-virtualenv guard (4c), `--feeling-lucky`'s missing signal normalization (4c), latent defects 1 and 3 (4c), the remaining dead arguments (4c), the persistence change and the `Options` deletion (4b), design amendment 9 (4b), `pathlibcutoff`'s two readers (4b), the probe venv in classification (unowned), the single-file reachability gap (a later `analysis/` plan).
- [ ] A live run on a real script, from a real shell, before the branch merges — and its output recorded. Note in the record which install shape it used, because `pixi run` cannot reach the in-virtualenv branch.

**Verify:** `pixi run test && pixi run lint && pixi run python -m ruff format --check . && pixi run typecheck` → paste all four outputs into the PROGRESS.md entry.

**Steps:**

- [ ] **Step 1: Measure the gates**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
```

Baseline to beat or match: 408 passed on `main` at `b59cfa8` (this plan deletes one test and adds more, so the number moves — say by how much and why); lint zero; format 55 files; typecheck **29 errors in 7 files**. Task 6 deletes several `assert x is not None` lines that existed only for mypy's narrowing, so the typecheck number may move in either direction. Report it either way.

- [ ] **Step 2: Do a live run**

```bash
pixi run veny path/to/a/real/script.py
```

Then, separately, prove Task 1's change end to end:

```bash
pixi run veny some_directory/
echo "exit status: $?"
```

Expected: the usage message and `exit status: 2` — no traceback.

- [ ] **Step 3: Update `PROGRESS.md`**

Rewrite the **Current work** block's plan table to add a phase 4 section with 4a marked executed and 4b/4c named. Set the **next action** line to 4b. Add this plan's amendments and residual risks to the appropriate sections. Move — do not copy — every item this plan closed.

- [ ] **Step 4: Fix the tasks tracker if it disagrees**

3e closed with `<plan>.md.tasks.json` still saying `"pending"` for its last task while `PROGRESS.md` said the phase was done, so the *recommended* resume path was the one that would re-run finished work. Check it here, and if it disagrees with git, **git wins**: fix the tracker, do not redo the task.

- [ ] **Step 5: Commit**

```bash
git add PROGRESS.md docs/ README.md
git commit -m "docs: close phase 4a with measured gates and its ledger"
```

- [ ] **Step 6: Merge**

Follow the phase 3 pattern: `git merge --no-ff` onto `main`, then delete the branch, then record the merge commit in `PROGRESS.md` in a follow-up commit. Run the whole-branch review **before** merging — 3b, 3c, 3d and 3e each had one, and each found Important issues that per-task review had missed.
