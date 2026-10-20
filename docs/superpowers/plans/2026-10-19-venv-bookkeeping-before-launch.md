# Venv bookkeeping before launch — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop every interrupted run from leaking a `failed-` venv, by dropping
the prefix and saving the last-used record before the script launches, and
make renamed venvs keep working console scripts and `activate`.

**Architecture:** `pipeline.run` moves two existing blocks (the `failed-`
rename and `last_used.save`) from after `run_script` to just before it, and
launches from the renamed venv's interpreter. `environment.create_venv` adds
`--relocatable` to `uv venv`. No new modules.

**Tech Stack:** Python 3.12+, uv (>=0.9), pytest, pixi.

**Spec:** `docs/superpowers/specs/2026-10-19-venv-bookkeeping-before-launch-design.md`
— read it first. It holds the evidence, the rejected alternatives, and what
stays unchanged.

## Global Constraints

- **Branch:** `venv-bookkeeping-before-launch`, off `main` @ `9204234`. It
  already carries the spec (`eeea3cc`) and the PROGRESS.md migration
  (`30b29e7`).
- **Red/green TDD.** Each new test is written first and seen to fail for the
  stated reason before the fix. The guard test in Task 1 passes on today's
  code by design, so it is shown to fail by mutation instead (Task 1, Step 6).
- **Mutations** are made in place from a scratch copy and restored from that
  copy. Never `git checkout -- <path>`, never `git stash` (the stash hazard is
  in memory and in PROGRESS.md's gotchas). Never test a mutated copy of
  `src/` through `PYTHONPATH`: pixi activation overwrites it and silently
  tests the real source.
- **The gate before every commit**, run from `/workspace`:
  - `pixi run ruff check .` → `All checks passed!`
  - `pixi run ruff format --check .` → `… files already formatted`
  - `pixi run python -m pytest` (what `test.yml` runs) → all passed
  - `pixi run python -m pytest --cov` → all passed (the user's global rule)
  - `pixi run python -m mypy --exclude '^tempy/' .` → `Found 23 errors in 6
    files` or fewer. The `--exclude` is required: `tempy/` is the user's
    untracked scratch directory (gitignored at `6346830`), and its `veny.py`
    makes plain `mypy .` stop with `Duplicate module named "veny"`.
  - `pixi run pre-commit run --all-files` → every hook passes **except
    `mypy`**. That hook is a whole-repo `mypy .` that cannot pass on the
    existing errors (PROGRESS.md gotcha "`pixi run typecheck` still cannot
    pass"), and with `tempy/` present it stops at `Duplicate module named
    "veny"`. Its real count is the mypy line above. Do not run
    `pre-commit install` (same gotcha).
- **Baseline** on this branch: 493 passed, mypy 23, ruff and format clean.
  Expected after Task 1: 495 passed. After Task 2: 496 passed.
- **Do not touch `tempy/`.**
- **Commits:** Conventional Commits, imperative mood, one per task, test and
  fix together, each ending with
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- **A lone failure of the two live interpreter-probe tests** with "timed out
  after 10.0 seconds" in the log is host load (`docs/hygiene-notes.md`).
  Re-run.
- **PROGRESS.md after every task** (the project's durability rule). Its
  **Next action** paragraph starts `**Next action:** Task 1 of` when this plan
  is committed. Task 1's commit changes that to `Task 2 of`, Task 2's to
  `Task 3 of`, and Task 3 rewrites the opening (Task 3, Step 4). Nothing else
  in PROGRESS.md changes before Task 3.

**User decisions (already made):**
- 2026-10-19: option A — rename and save before launch, and build venvs
  `--relocatable`. Options B (signal handling), C (no rename) and D (learn
  runtime import failures) were rejected or deferred; see the spec.
- 2026-10-19: the spec is approved as written, including its out-of-scope
  list: no orphan cleanup, no retrofitting existing venvs, no wiring-index
  regeneration.
- Merging `venv-bookkeeping-before-launch` into `main`, and pushing, are the
  user's call after Task 3. They are not part of this plan.

---

### Task 1: Do the bookkeeping before the launch

**Goal:** `pipeline.run` drops a verified build's `failed-` prefix and saves
the last-used record before it launches the script, and launches from the
renamed path, so a Ctrl-C'd or rebooted run leaves a reusable venv.

**Files:**
- Modify: `src/veny/pipeline.py` — `run` (the `if handle is not None:` block,
  around lines 941-990, and the reused-venv comment around lines 935-939);
  `setup_virtualenv` (the docstring's last sentence, around lines 590-592,
  and the comment around line 604)
- Modify: `src/veny/cache_search.py` — `rename_venv`'s docstring (around line
  186)
- Test: `tests/test_cli_entry_point.py` — two new tests after
  `test_main_drops_the_failed_prefix_from_the_venv_it_just_built`, and that
  test's docstring
- Test: `tests/test_wiring_4a.py` — the docstring of
  `test_the_saved_record_names_the_post_rename_venv_dir` (around line 757)
- Modify: `PROGRESS.md` — **Next action**, `Task 1 of` → `Task 2 of`

**Acceptance Criteria:**
- [ ] `test_an_interrupted_run_still_leaves_a_reusable_venv_and_a_last_used_record`
  fails on the unmodified code with the assertion `assert final.is_dir()`, and
  passes after the fix.
- [ ] `test_a_build_whose_install_failed_keeps_its_prefix_and_is_recorded_under_it`
  passes before and after the fix, and fails when `and install_succeeded` is
  deleted from the moved condition (mutation, then restored).
- [ ] `test_main_drops_the_failed_prefix_from_the_venv_it_just_built` and
  `test_the_saved_record_names_the_post_rename_venv_dir` still pass.
- [ ] `rg -n 'has run successfully|completes successfully|once a run succeeds|once the run has' src/veny tests`
  prints nothing.
- [ ] The full gate passes. `pixi run python -m pytest` reports 495 passed.

**Verify:** `pixi run python -m pytest tests/test_cli_entry_point.py tests/test_wiring_4a.py -q` → all passed; then the full gate.

**Steps:**

- [ ] **Step 1: Write the two tests.** Insert them into
  `tests/test_cli_entry_point.py` directly after
  `test_main_drops_the_failed_prefix_from_the_venv_it_just_built` (which ends
  with `assert (built.parent / "myenv-py3.12-20260101-010203-thing-pkg").is_dir()`).
  Every name they use (`_drive_main`, `cli`, `pipeline`, `state`,
  `last_used`, `os`, `subprocess`, `pytest`) is already imported or defined
  in that file.

  Test design, per the `test-design` skill:
  - *Interrupted-run test.* **Behaviour:** a Ctrl-C reaching veny while the
    script runs still leaves the build renamed, recorded, and launched from
    the renamed path. **Bug it catches:** the bookkeeping sitting after
    `run_script` (today's code), and also a rename that is hoisted while the
    script still launches from the stale `failed-` path, which breaks the
    script's later imports. **Expected values** come by construction: the
    fake builder is the only source of the folder name, the final name is
    that name with the literal `failed-` removed by hand, and `VenvHandle`
    puts the interpreter at `<venv>/bin/python`. The `KeyboardInterrupt` is
    raised from `subprocess.run`, the real boundary where a Ctrl-C surfaces
    in veny. `run_script` itself stays live.
  - *Guard test.* **Behaviour:** a build whose install reported an error
    keeps its `failed-` prefix, and its record names that folder. **Bug it
    catches:** dropping `and install_succeeded` while moving the condition,
    which would turn every partially failed build into a cache candidate.
    **Expected values** are by construction, as above.

```python
def test_an_interrupted_run_still_leaves_a_reusable_venv_and_a_last_used_record(
    monkeypatch, tmp_path
):
    """Ctrl-C during the user's script must not orphan the venv just built.

    Behaviour under test: a script that never exits on its own (a monitor
    loop) ends with Ctrl-C, and SIGINT reaches veny too, so subprocess.run
    raises KeyboardInterrupt inside run_script and nothing after that call
    runs. The "failed-" rename and the last-used save therefore happen before
    the launch. Their gate (prefix present, install succeeded) is fully known
    by then, and the script's outcome never entered it.

    Concrete bug this catches: the bookkeeping placed after run_script, where
    it sat until 2026-10-19, leaves `failed-<name>` on disk and no record. The
    next run's cache scan skips "failed-" folders, finds nothing and builds
    another venv -- once per run, forever. Also catches a rename hoisted
    above the launch while the script still launches from the old failed-
    path: renaming a venv under a running interpreter breaks every import it
    has not done yet.

    Expected values by construction: the fake builder is the only source of
    the folder name, the final name is that name without its literal
    "failed-", and VenvHandle puts the interpreter at <venv>/bin/python.
    """
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog", "--no-cache"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    built = tmp_path / "home" / "veny" / "failed-myenv-py3.12-20260101-010203-thing-pkg"
    final = tmp_path / "home" / "veny" / "myenv-py3.12-20260101-010203-thing-pkg"

    def fake_setup(settings, target, requirements, **kwargs):
        return requirements, state.VenvHandle.for_dir(built), True

    monkeypatch.setattr(pipeline, "setup_virtualenv", fake_setup)
    launched_with: list[str] = []

    def interrupted_run(command, *args, **kwargs):
        launched_with.append(os.fspath(command[0]))
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "run", interrupted_run)

    with pytest.raises(KeyboardInterrupt):
        cli.main()

    assert final.is_dir()
    assert not built.exists()
    record = last_used.load(
        script_dir=tmp_path,
        python_script=tmp_path / "script.py",
        my_name="veny",
        rawlog=True,
    )
    assert record is not None
    assert record.venv_dir == final
    assert record.venv_python == final / "bin" / "python"
    assert launched_with == [os.fspath(final / "bin" / "python")]


def test_a_build_whose_install_failed_keeps_its_prefix_and_is_recorded_under_it(
    monkeypatch, tmp_path
):
    """A build uv could not fully install keeps "failed-", before and after launch.

    Behaviour under test: the rename's gate still includes install_succeeded
    now that it runs before the launch. setup_virtualenv can hand back a
    usable handle (every import verified) while uv reported an install error;
    that venv runs the script, keeps its prefix so the cache scan never
    offers it, and the last-used record names the folder as it is on disk.

    Concrete bug this catches: dropping `and install_succeeded` while moving
    the condition above run_script. Every partially failed build would then
    lose its prefix and become a cache candidate for other scripts that need
    the package uv could not install.

    Expected values by construction, as in the interrupted-run test above.
    """
    _, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog", "--no-cache"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    built = tmp_path / "home" / "veny" / "failed-myenv-py3.12-20260101-010203-thing-pkg"

    def fake_setup(settings, target, requirements, **kwargs):
        return requirements, state.VenvHandle.for_dir(built), False

    monkeypatch.setattr(pipeline, "setup_virtualenv", fake_setup)

    assert cli.main() == 0

    assert built.is_dir()
    assert not (tmp_path / "home" / "veny" / "myenv-py3.12-20260101-010203-thing-pkg").exists()
    record = last_used.load(
        script_dir=tmp_path,
        python_script=tmp_path / "script.py",
        my_name="veny",
        rawlog=True,
    )
    assert record is not None
    assert record.venv_dir == built
    assert launched == [
        [os.fspath(built / "bin" / "python"), os.fspath(tmp_path / "script.py")]
    ]
```

- [ ] **Step 2: Run them; confirm the right one fails for the right reason.**

  Run: `pixi run python -m pytest tests/test_cli_entry_point.py -q -k "interrupted_run_still_leaves or install_failed_keeps_its_prefix"`

  Expected: `1 failed, 1 passed`. The failure is
  `test_an_interrupted_run_still_leaves_a_reusable_venv_and_a_last_used_record`
  at `assert final.is_dir()`. If it fails anywhere else (for example inside
  `pytest.raises` because no `KeyboardInterrupt` came out, or at
  `last_used.load`), the test is wrong — fix the test, not the code. The
  guard test passing is expected: it pins behaviour that already exists.

- [ ] **Step 3: Move the bookkeeping in `src/veny/pipeline.py` `run`.**
  Replace this block (starting at `        if handle is not None:` and ending
  with the closing `            )` of `last_used.save(`):

```python
        if handle is not None:
            start_venv_time = dt.datetime.now()
            elapsed_time = start_venv_time - start_time
            if not settings.rawlog:
                logging.info("Elapsed time: %s", elapsed_time)
            script_exit_code = run_script(
                handle.venv_python,
                target.python_script,
                list(target.script_args),
                rawlog=settings.rawlog,
                announce=True,
            )
            end_time = dt.datetime.now()
            elapsed_time = end_time - start_venv_time
            if not settings.rawlog:
                logging.info(
                    "Elapsed time since activating virtual environment: %s",
                    elapsed_time,
                )
            if script_exit_code != 0 and not settings.rawlog:
                logging.error("Script exited with status %d", script_exit_code)
            if (
                handle.venv_dir.name.startswith(venv_cache.FAILED_PREFIX)
                and install_succeeded
            ):
                # If the program has made it to this point, it has run successfully, so the venv directory can be renamed because it DIDN'T fail.
                handle = state.VenvHandle.for_dir(
                    cache_search.rename_venv(
                        handle.venv_dir,
                        handle.venv_dir.name.removeprefix(venv_cache.FAILED_PREFIX),
                    )
                )

            # What the next run needs, and nothing else: which environment
            # ran this script and which interpreter is inside it. Written
            # after the failed- rename above, so the recorded folder is the
            # one that exists on disk.
            last_used.save(
                state.LastUsed(
                    venv_dir=handle.venv_dir,
                    venv_python=handle.venv_python,
                    timestamp=target.timestamp,
                ),
                script_dir=target.script_dir,
                python_script=target.python_script,
                my_name=settings.my_name,
            )
```

  with:

```python
        if handle is not None:
            # The bookkeeping comes BEFORE the launch. Its gate -- the prefix
            # is present and every requirement installed -- is fully known
            # here; the script's outcome never entered it. A script that never
            # exits on its own ends with Ctrl-C or a reboot, which end veny
            # too, so code after run_script never runs for it: the venv kept
            # its "failed-" prefix, no record was written, and every next run
            # built another venv (2026-10-19). Never rename during the run
            # either: moving a venv under a running interpreter breaks every
            # import it has not done yet.
            if (
                handle.venv_dir.name.startswith(venv_cache.FAILED_PREFIX)
                and install_succeeded
            ):
                # The build installed and its imports verified, so the venv
                # drops the prefix that marked it as provisional.
                handle = state.VenvHandle.for_dir(
                    cache_search.rename_venv(
                        handle.venv_dir,
                        handle.venv_dir.name.removeprefix(venv_cache.FAILED_PREFIX),
                    )
                )

            # What the next run needs, and nothing else: which environment
            # runs this script and which interpreter is inside it. Written
            # after the failed- rename above, so the recorded folder is the
            # one that exists on disk.
            last_used.save(
                state.LastUsed(
                    venv_dir=handle.venv_dir,
                    venv_python=handle.venv_python,
                    timestamp=target.timestamp,
                ),
                script_dir=target.script_dir,
                python_script=target.python_script,
                my_name=settings.my_name,
            )

            start_venv_time = dt.datetime.now()
            elapsed_time = start_venv_time - start_time
            if not settings.rawlog:
                logging.info("Elapsed time: %s", elapsed_time)
            # The post-rename handle, so the script runs from the folder's
            # final path.
            script_exit_code = run_script(
                handle.venv_python,
                target.python_script,
                list(target.script_args),
                rawlog=settings.rawlog,
                announce=True,
            )
            end_time = dt.datetime.now()
            elapsed_time = end_time - start_venv_time
            if not settings.rawlog:
                logging.info(
                    "Elapsed time since activating virtual environment: %s",
                    elapsed_time,
                )
            if script_exit_code != 0 and not settings.rawlog:
                logging.error("Script exited with status %d", script_exit_code)
```

  The line after the block, `    return script_exit_code`, is unchanged.

- [ ] **Step 4: Run the two tests; confirm both pass.**

  Run: `pixi run python -m pytest tests/test_cli_entry_point.py -q -k "interrupted_run_still_leaves or install_failed_keeps_its_prefix"`

  Expected: `2 passed`.

- [ ] **Step 5: Correct the comments and docstrings that describe the old
  ordering.** Five exact replacements.

  `src/veny/pipeline.py`, the reused-venv branch of `run`. Replace:

```python
            # A reused venv never carries a "failed-" prefix -- the cache
            # search only offers folders that dropped it -- and
            # setup_virtualenv never ran, which is what left
            # install_succeeded False on the state object here before phase 4a.
            install_succeeded = False
```

  with:

```python
            # A reused venv is never renamed. The cache scan only offers
            # folders that already dropped the "failed-" prefix; the last-used
            # path can return a "failed-" folder (uv reported an install error
            # but every import verified), and that one keeps its prefix, as it
            # did on the run that built it. setup_virtualenv never ran, which
            # is what left install_succeeded False on the state object here
            # before phase 4a.
            install_succeeded = False
```

  `src/veny/pipeline.py`, `setup_virtualenv`'s docstring. Replace:

```text
        `pipeline.run` reports as status 1; and whether every requirement
        installed, which `run` needs separately because it decides the
        "failed-" rename even on the success path.
```

  with:

```text
        `pipeline.run` reports as status 1; and whether every requirement
        installed, which `run` needs separately because it gates the
        "failed-" rename: a handle can be usable (every import verified)
        while uv still reported an install error.
```

  `src/veny/pipeline.py`, `setup_virtualenv`'s body. Replace the single line:

```python
    # Create a virtual environment directory that starts with "failed" in case the process fails. Only remove the "failed" part if this process completes successfully.
```

  with:

```python
    # Build under a "failed-" name. run() drops the prefix just before it
    # launches the script, and only if every requirement installed and every
    # import verified, so a build that is interrupted or does not verify is
    # never offered by the cache scan.
```

  `src/veny/cache_search.py`, `rename_venv`'s docstring. Replace:

```text
    points at a path that no longer exists. Two callers need this: dropping the
    "failed-" prefix once a run succeeds, and re-naming a venv whose package
    list changed when verify_and_repair_imports repaired a wrongly resolved pip
    name.
```

  with:

```text
    points at a path that no longer exists. Two callers need this: dropping the
    "failed-" prefix once a build has installed and verified, and re-naming a
    venv whose package list changed when verify_and_repair_imports repaired a
    wrongly resolved pip name.
```

  `tests/test_cli_entry_point.py`, the docstring of
  `test_main_drops_the_failed_prefix_from_the_venv_it_just_built`. Replace:

```text
    setup_virtualenv builds into `failed-<name>` so an interrupted run leaves
    an obviously unusable folder behind; main() renames it only once the run
    has actually succeeded. Measured by substitution: both arguments of that
    rename_venv call could be replaced with all 338 tests green.
```

  with:

```text
    setup_virtualenv builds into `failed-<name>` so an interrupted build leaves
    an obviously unusable folder behind; main() renames it once the build has
    installed and verified, just before launching the script. Measured by
    substitution: both arguments of that rename_venv call could be replaced
    with all 338 tests green.
```

  `tests/test_wiring_4a.py`, the docstring of
  `test_the_saved_record_names_the_post_rename_venv_dir`. Replace:

```text
    actually exists on disk once the run has succeeded.
```

  with:

```text
    actually exists on disk once the build has verified.
```

  Then run:
  `rg -n 'has run successfully|completes successfully|once a run succeeds|once the run has' src/veny tests`
  Expected: no output.

- [ ] **Step 6: Prove the guard test can fail (mutation).** Take
  `$SCRATCH` to be a fresh directory in this session's scratchpad (the
  system prompt names it), never `/tmp` and never inside the repository.

```bash
cp src/veny/pipeline.py "$SCRATCH/pipeline.py.orig"
python3 - <<'EOF'
from pathlib import Path

p = Path("src/veny/pipeline.py")
text = p.read_text()
needle = "                and install_succeeded\n"
assert text.count(needle) == 1, text.count(needle)
p.write_text(text.replace(needle, ""))
EOF
pixi run python -m pytest tests/test_cli_entry_point.py -q -k "install_failed_keeps_its_prefix"
cp "$SCRATCH/pipeline.py.orig" src/veny/pipeline.py
cmp src/veny/pipeline.py "$SCRATCH/pipeline.py.orig" && echo restored
```

  Expected: `1 failed`, at `assert built.is_dir()`, then `restored`. If it
  passes under the mutation, the guard is not guarding — strengthen it
  before going on.

- [ ] **Step 7: Point PROGRESS.md at Task 2.** In the **Next action**
  paragraph, replace `**Next action:** Task 1 of` with
  `**Next action:** Task 2 of`.

- [ ] **Step 8: Run the full gate** (Global Constraints). Expected: 495
  passed, mypy 23 or fewer, ruff and format clean, every pre-commit hook
  but the known `mypy` one passing. `git status
  --short` lists only the five files under **Files**.

- [ ] **Step 9: Commit.**

```bash
git add src/veny/pipeline.py src/veny/cache_search.py tests/test_cli_entry_point.py tests/test_wiring_4a.py PROGRESS.md
git commit -m "fix: drop the failed- prefix and save last-used before launching the script

A script that never exits on its own ends with Ctrl-C or a reboot, which
end veny too, so the rename and the record placed after run_script never
ran. The venv kept its prefix, the cache scan skipped it, and every next
run built another one. Their gate never consulted the script's outcome,
so they now run before the launch, and the script launches from the
renamed path.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Build relocatable venvs

**Goal:** `environment.create_venv` builds with `uv venv --relocatable`, so a
venv's console scripts and `bin/activate` keep working after the `failed-`
rename moves it.

**Files:**
- Modify: `src/veny/environment.py` — `create_venv` (around lines 72-97)
- Modify: `tests/wheels.py` — `build_wheel` gains `console_script`
- Test: `tests/test_environment.py` — one new live test
- Test: `tests/test_uv_backend.py` —
  `test_create_venv_is_given_a_resolved_interpreter_path_not_a_bare_command`'s
  expected argv (around line 325)
- Modify: `PROGRESS.md` — **Next action**, `Task 2 of` → `Task 3 of`

**Acceptance Criteria:**
- [ ] `test_a_venv_veny_builds_keeps_working_scripts_after_it_is_renamed`
  fails on the unmodified `create_venv` at
  `assert script.returncode == 0`, and passes after the fix, with real uv,
  `UV_OFFLINE=1`, and no subprocess stubbing.
- [ ] The updated argv test fails before the fix and passes after it.
- [ ] `build_wheel` called without `console_script` writes exactly what it
  wrote before (no `entry_points.txt`, the same `__init__.py`). The existing
  live round-trip test in `tests/test_environment.py` still passes.
- [ ] The full gate passes. `pixi run python -m pytest` reports 496 passed.

**Verify:** `pixi run python -m pytest tests/test_environment.py tests/test_uv_backend.py -q` → all passed; then the full gate.

**Steps:**

- [ ] **Step 1: Give `build_wheel` an optional console script.** In
  `tests/wheels.py`, replace the signature and docstring `Args` and the
  `__init__.py` write, and add `entry_points.txt` when asked. Replace:

```python
def build_wheel(
    directory: Path, *, name: str = "venytest", version: str = "0.1", value: int = 42
) -> Path:
```

  with:

```python
def build_wheel(
    directory: Path,
    *,
    name: str = "venytest",
    version: str = "0.1",
    value: int = 42,
    console_script: str | None = None,
) -> Path:
```

  Replace:

```text
        value:     The integer the built package's ``value`` attribute holds.
```

  with:

```text
        value:     The integer the built package's ``value`` attribute holds.
        console_script: If given, the wheel also declares a console script of
                   this name, which runs the package's ``main()``. That
                   function prints ``value``.
```

  Replace:

```python
    (pkg_dir / "__init__.py").write_text(f"value = {value}\n")
```

  with:

```python
    init = f"value = {value}\n"
    if console_script is not None:
        init += "\n\ndef main():\n    print(value)\n"
    (pkg_dir / "__init__.py").write_text(init)
```

  Replace:

```python
    (dist_info / "RECORD").write_text("")
```

  with:

```python
    (dist_info / "RECORD").write_text("")
    if console_script is not None:
        (dist_info / "entry_points.txt").write_text(
            f"[console_scripts]\n{console_script} = {name}:main\n"
        )
```

- [ ] **Step 2: Write the live test.** Append to `tests/test_environment.py`.
  It already imports `os`, `shutil`, `subprocess`, `Path`, `build_wheel`
  and `environment`.

  Test design: **Behaviour:** a venv built by `create_venv` and then renamed
  still runs its console scripts and activates at its new path. **Bug it
  catches:** `create_venv` without `--relocatable`, the state seen live on
  2026-10-19 (`bin/unidecode` failed with
  `…/failed-myenv-…/bin/python: not found`). **Expected values:** `42` is
  the fixture wheel's own `value`; the activated path is the rename target
  this test chose. Nothing is stubbed. uv, the install and the rename are all
  real, the same standard as the round-trip test above it.

```python
def test_a_venv_veny_builds_keeps_working_scripts_after_it_is_renamed(
    monkeypatch, tmp_path
):
    """A venv's console scripts and activate must survive the failed- rename.

    pipeline.run builds every venv as `failed-<name>` and renames it once it
    verifies. A plain `uv venv` writes the venv's absolute path into each
    console script and into bin/activate, so after the rename they still
    name the `failed-` path, which no longer exists. Seen live on
    2026-10-19: a renamed venv's bin/unidecode failed with
    ".../failed-myenv-.../bin/python: not found". create_venv builds with
    --relocatable, whose scripts find the venv relative to themselves.

    Concrete bug this catches: create_venv without --relocatable. The console
    script then exits nonzero, and activate sets VIRTUAL_ENV to the old
    path. Nothing is stubbed -- real `uv venv`, a real `uv pip install` of a
    hand-built wheel, a real rename -- so dropping or misspelling the flag
    fails here.

    Expected values: 42 is the fixture wheel's own `value`, and the
    activated path is the rename target chosen below.
    """
    monkeypatch.setenv("UV_OFFLINE", "1")
    python = shutil.which("python3")
    assert python is not None, "test host must have a python3 on PATH"
    built = tmp_path / "failed-venv"
    assert environment.create_venv(built, python) is True
    wheel_path = build_wheel(tmp_path, console_script="venytest-cli")
    assert (
        environment.install_into_venv(built / "bin" / "python", str(wheel_path))
        is True
    )

    renamed = tmp_path / "venv"
    built.rename(renamed)

    # Through bash, so a dangling shebang shows up as a nonzero exit with
    # bash's message on stderr, rather than as an exec error raised inside
    # this process.
    script = subprocess.run(
        ["bash", "-c", '"$0"', os.fspath(renamed / "bin" / "venytest-cli")],
        capture_output=True,
        text=True,
    )
    assert script.returncode == 0, script.stderr
    assert script.stdout.strip() == "42"

    activate = renamed / "bin" / "activate"
    activated = subprocess.run(
        ["bash", "-c", f'source "{activate}" && printf %s "$VIRTUAL_ENV"'],
        capture_output=True,
        text=True,
    )
    assert activated.returncode == 0, activated.stderr
    assert Path(activated.stdout).resolve() == renamed.resolve()
```

- [ ] **Step 3: Update the argv test to expect the flag.** In
  `tests/test_uv_backend.py`,
  `test_create_venv_is_given_a_resolved_interpreter_path_not_a_bare_command`,
  replace:

```python
    assert captured == [
        [
            "/packaged/uv",
            "venv",
            str(tmp_path / "target"),
            "--python",
            "/resolved/bin/python3",
        ]
    ]
```

  with:

```python
    # The exact argv also pins --relocatable: without it, the failed- rename
    # leaves the venv's console scripts and activate naming a path that no
    # longer exists (see test_environment's rename test).
    assert captured == [
        [
            "/packaged/uv",
            "venv",
            "--relocatable",
            str(tmp_path / "target"),
            "--python",
            "/resolved/bin/python3",
        ]
    ]
```

- [ ] **Step 4: Run both; confirm they fail for the right reason.**

  Run: `pixi run python -m pytest tests/test_environment.py tests/test_uv_backend.py -q -k "keeps_working_scripts or resolved_interpreter_path"`

  Expected: `2 failed`. The live test fails at
  `assert script.returncode == 0` with `assert 127 == 0`. The printed stderr
  is bash's report on the script itself; its shebang names the vanished
  `failed-venv/bin/python`. Seen while writing this plan, with bash 5.2:
  `<tmp>/venv/bin/venytest-cli: line 1: <tmp>/venv/bin/venytest-cli: cannot
  execute: required file not found`. An older bash says `bad interpreter: No
  such file or directory` instead. The
  argv test fails on the list comparison, with `--relocatable` missing. If
  the live test fails earlier — at `create_venv`, at `install_into_venv`, or
  because no `venytest-cli` file exists — the fixture is wrong: fix
  `build_wheel` or the test, not `create_venv`.

- [ ] **Step 5: Add the flag.** In `src/veny/environment.py`, `create_venv`.
  Replace:

```python
    No pip is seeded: veny drives installs through uv, and a script that
    installs into the environment veny built for it is working against veny.
```

  with:

```python
    No pip is seeded: veny drives installs through uv, and a script that
    installs into the environment veny built for it is working against veny.

    The environment is relocatable: its console scripts and activate find it
    relative to their own location instead of recording its absolute path.
    pipeline.run builds every venv under a "failed-" name and renames it once
    it verifies, and a plain venv's scripts would go on naming the old path.
```

  Replace:

```python
    command = [uv_binary(), "venv", os.fspath(target)]
```

  with:

```python
    command = [uv_binary(), "venv", "--relocatable", os.fspath(target)]
```

- [ ] **Step 6: Run them; confirm both pass.**

  Run: `pixi run python -m pytest tests/test_environment.py tests/test_uv_backend.py -q`

  Expected: all passed, including the existing round-trip test.

- [ ] **Step 7: Point PROGRESS.md at Task 3.** In the **Next action**
  paragraph, replace `**Next action:** Task 2 of` with
  `**Next action:** Task 3 of`.

- [ ] **Step 8: Run the full gate** (Global Constraints). Expected: 496
  passed, mypy 23 or fewer, ruff and format clean, every pre-commit hook
  but the known `mypy` one passing. `git status
  --short` lists only the five files under **Files**.

- [ ] **Step 9: Commit.**

```bash
git add src/veny/environment.py tests/wheels.py tests/test_environment.py tests/test_uv_backend.py PROGRESS.md
git commit -m "fix: build venvs relocatable so the failed- rename keeps their scripts working

A plain uv venv records its absolute path in every console script and in
bin/activate, so after the rename they named a failed- path that no
longer existed. --relocatable makes them find the venv relative to
themselves. uv has had the flag since before veny's 0.9 floor.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Live run and documentation

**Goal:** A live reproduction of the original bug, run against this branch,
shows two Ctrl-C'd runs leaving exactly one unprefixed, reused venv. The
evidence is recorded in this plan, and PROGRESS.md's `failed-` gotcha and
next-action line describe the new behaviour.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-19-venv-bookkeeping-before-launch.md`
  — the **Execution record** at the end
- Modify: `PROGRESS.md` — the gotcha "`~/veny/failed-<name>` is the
  PROVISIONAL build folder" (around line 2280) and the **Next action** line

**Acceptance Criteria:**
- [ ] After two runs, each ended with SIGINT to the whole process group,
  `ls "$S/home/veny" | rg myenv` prints exactly one line, matching
  `^myenv-py3\.\d+-\d{8}-\d{6}-unidecode$` (no `failed-`).
- [ ] `$S/run2.log` contains `Using existing virtual environment:` and does
  not contain `Creating new virtual environment`.
- [ ] `$S/proj/.forever.py-veny-last-used.json` exists and its `venv_dir`
  is that folder.
- [ ] That folder's `bin/unidecode --help` exits 0 and prints a line starting
  `usage: unidecode`.
- [ ] The Execution record holds the commands run and their observed output
  for every criterion above, plus Tasks 1 and 2's red and green lines.
- [ ] PROGRESS.md's gotcha and next-action line match Step 4 below.
  `pixi run pre-commit run --all-files` passes every hook but the known
  `mypy` one.

**Verify:** the commands in Steps 2-3, with output pasted into the Execution record.

**Steps:**

- [ ] **Step 1: Set up the reproduction.** This needs network access to PyPI,
  to install `unidecode`. It runs veny from this branch's `src/` with a
  throwaway `HOME`, so the real `~/veny` is untouched. `S` must be a fresh
  directory in this session's scratchpad (the system prompt names it), never
  `/tmp` and never inside the repository.

```bash
mkdir -p "$S/home" "$S/proj"
cat > "$S/proj/forever.py" <<'EOF'
"""Stand-in for a monitor script: a loop that never exits on its own."""

import time

import unidecode

while True:
    print("still monitoring", unidecode.unidecode("naïve"), flush=True)
    time.sleep(1)
EOF
cat > "$S/drive.py" <<'EOF'
"""Run veny on forever.py, then signal its whole process group, as Ctrl-C does.

The child gets SIGINT at its default disposition explicitly: a job started
in the background of a non-interactive shell inherits SIGINT as ignored,
which silently turns the Ctrl-C into a no-op.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

S = Path(sys.argv[1])
run = sys.argv[2]
sig = getattr(signal, sys.argv[3])
log = S / f"run{run}.log"
env = dict(os.environ, HOME=str(S / "home"), PYTHONPATH="/workspace/src")


def _default_sigint() -> None:
    signal.signal(signal.SIGINT, signal.SIG_DFL)


with log.open("w") as out:
    proc = subprocess.Popen(
        [sys.executable, "-m", "veny", "forever.py"],
        cwd=S / "proj", env=env, stdout=out, stderr=subprocess.STDOUT,
        process_group=0, preexec_fn=_default_sigint,
    )
    deadline = time.monotonic() + 280
    while "still monitoring" not in log.read_text() and time.monotonic() < deadline:
        if proc.poll() is not None:
            sys.exit(f"veny exited early with {proc.returncode}")
        time.sleep(1)
    time.sleep(2)
    os.killpg(proc.pid, sig)
    print(f"run {run}: sent {sys.argv[3]}; veny exit status {proc.wait(timeout=30)}")
EOF
```

- [ ] **Step 2: Run it twice, Ctrl-C'ing each run** (from `/workspace`,
  with a timeout of at least 5 minutes per run):

```bash
pixi run python "$S/drive.py" "$S" 1 SIGINT
pixi run python "$S/drive.py" "$S" 2 SIGINT
```

  Expected for each: `run N: sent SIGINT; veny exit status -2`.

- [ ] **Step 3: Check the outcome.**

```bash
ls "$S/home/veny" | rg myenv
rg -o 'INFO - (Checking the cache|No matching|Found \d+ matching|Creating new|Using existing).*' "$S/run2.log"
python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['venv_dir'])" "$S/proj/.forever.py-veny-last-used.json"
"$S"/home/veny/myenv-py3.*-unidecode/bin/unidecode --help | head -1
```

  Expected: one `myenv-py3.<minor>-<timestamp>-unidecode` line; run 2's log
  shows `Using existing virtual environment: …/myenv-py3.…-unidecode`;
  the record's `venv_dir` is that same folder; `usage: unidecode …`. If run 1
  left a `failed-` folder, or run 2 built a second venv, stop: the fix did
  not work. Report it; do not paper over it.

- [ ] **Step 4: Update PROGRESS.md.** Replace the gotcha:

```markdown
- **`~/veny/failed-<name>` is the PROVISIONAL build folder, not a failure.**
  Anyone re-running the phase-closing live runs will see `uv venv` create
  `failed-myenv-py…-<pkgs>` and see the script launched from that path in the
  log. The `failed-` prefix is stripped by the rename only after verification
  succeeds, so the acceptance criterion "no `failed-` prefix" is a statement
  about the folder on disk when the run ends, not about the log. Check with
  `ls ~/veny/` after the run; do not read the log and conclude a regression.
```

  with:

```markdown
- **`~/veny/failed-<name>` is the PROVISIONAL build folder, not a failure.**
  Anyone re-running a live run will see `uv venv` create
  `failed-myenv-py…-<pkgs>`. Since 2026-10-19
  (`docs/superpowers/specs/2026-10-19-venv-bookkeeping-before-launch-design.md`)
  the prefix is dropped, and the last-used record saved, just *before* the
  script launches, so the log's `Running command:` line names the final,
  unprefixed path. Before that date the script launched from the `failed-`
  path and the rename came after it exited. A `failed-` folder left on disk
  after a run now means the build was interrupted, or its install or imports
  did not verify. Check with `ls ~/veny/` after the run.
```

  Replace the **Next action** paragraph's opening, from
  `**Next action:** Task 3 of` through the sentence ending
  ``and venvs are built `--relocatable`.``, with:

```markdown
**Next action:** the user decides whether to merge branch
`venv-bookkeeping-before-launch` (plan
`docs/superpowers/plans/2026-10-19-venv-bookkeeping-before-launch.md`, all
three tasks done, with its execution record and live run at its end) into
`main`, and whether to push. It fixes the interrupted-run `failed-` venv
leak: the rename and last-used save now come before the launch, and venvs
are built `--relocatable`.
```

- [ ] **Step 5: Fill in the Execution record below** with the commit SHAs,
  the red and green lines from Tasks 1 and 2, the Task 1 mutation result,
  the final gate's numbers, and Steps 2-3's commands and output, verbatim.

- [ ] **Step 6: Commit.**

```bash
pixi run pre-commit run --all-files
git add PROGRESS.md docs/superpowers/plans/2026-10-19-venv-bookkeeping-before-launch.md
git commit -m "docs: record the live run of the venv-bookkeeping fix

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Execution record

This record was filled in on 2026-10-19.

### Task 1

Commit `53ff786`.

Red (`pytest tests/test_cli_entry_point.py`, new tests only), the guard test
passing by design:

```text
>       assert final.is_dir()
E       AssertionError: assert False
================== 1 failed, 1 passed, 44 deselected in 0.62s ==================
```

Green:

```text
======================= 2 passed, 44 deselected in 0.45s =======================
```

Mutation (deleting `and install_succeeded` from the rename gate; restored
byte-identical afterwards). The guard test fails:

```text
>       assert built.is_dir()
E       AssertionError: assert False
FAILED tests/test_cli_entry_point.py::test_a_build_whose_install_failed_keeps_its_prefix_and_is_recorded_under_it
======================= 1 failed, 45 deselected in 0.74s =======================
```

Gate at the commit:

```text
pixi run python -m pytest                      495 passed in 18.78s
pixi run python -m pytest --cov                495 passed in 23.81s (TOTAL 86%)
pixi run python -m mypy --exclude '^tempy/' .  Found 23 errors in 6 files
pixi run ruff check .                          All checks passed!
pixi run ruff format --check .                 65 files already formatted
```

### Task 2

Commit `d3e719b`.

Red (`pytest tests/test_environment.py tests/test_uv_backend.py -k "keeps_working_scripts or resolved_interpreter_path"`):

```text
E       AssertionError: .../venv/bin/venytest-cli: line 1: .../venv/bin/venytest-cli: cannot execute: required file not found
E
E       assert 127 == 0
E       At index 0 diff: ['/packaged/uv', 'venv', '<target>', '--python', '/resolved/bin/python3'] != ['/packaged/uv', 'venv', '--relocatable', '<target>', '--python', '/resolved/bin/python3']
======================= 2 failed, 21 deselected in 2.91s =======================
```

Green (`pytest tests/test_environment.py tests/test_uv_backend.py`):

```text
============================== 23 passed in 2.00s ==============================
```

Gate at the commit:

```text
pixi run python -m pytest                      496 passed in 15.57s
pixi run python -m pytest --cov                496 passed in 23.67s
pixi run python -m mypy --exclude '^tempy/' .  Found 23 errors in 6 files
pixi run ruff check .                          All checks passed!
pixi run ruff format --check .                 65 files already formatted
```

### Task 3 — live run

Final gate, run on the tree before this commit (it changes only
`PROGRESS.md` and this plan):

```text
pixi run python -m pytest                      496 passed in 22.95s
pixi run python -m pytest --cov                496 passed in 28.25s (TOTAL 86%)
pixi run python -m mypy --exclude '^tempy/' .  Found 23 errors in 6 files
pixi run ruff check .                          All checks passed!
pixi run ruff format --check .                 65 files already formatted
```

Setup: Step 1's `forever.py` and `drive.py`, with
`S=/tmp/claude-1000/-workspace/aebab7f9-8205-41f1-8dbc-6cc8c5b95862/scratchpad/venv-leak-live`
(a throwaway `HOME` of `$S/home`, veny from `/workspace/src`, network to PyPI
for `unidecode`). Python 3.13.

Step 2, from `/workspace`, each run ended with SIGINT to the whole process group:

```bash
pixi run python "$S/drive.py" "$S" 1 SIGINT
pixi run python "$S/drive.py" "$S" 2 SIGINT
```

```text
run 1: sent SIGINT; veny exit status -2
run 2: sent SIGINT; veny exit status -2
```

Step 3:

```bash
ls "$S/home/veny" | rg myenv
rg -o 'INFO - (Checking the cache|No matching|Found \d+ matching|Creating new|Using existing).*' "$S/run2.log"
python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['venv_dir'])" "$S/proj/.forever.py-veny-last-used.json"
"$S"/home/veny/myenv-py3.*-unidecode/bin/unidecode --help | head -1
```

```text
myenv-py3.13-20261019-185414-unidecode
INFO - Using existing virtual environment: /tmp/claude-1000/-workspace/aebab7f9-8205-41f1-8dbc-6cc8c5b95862/scratchpad/venv-leak-live/home/veny/myenv-py3.13-20261019-185414-unidecode
/tmp/claude-1000/-workspace/aebab7f9-8205-41f1-8dbc-6cc8c5b95862/scratchpad/venv-leak-live/home/veny/myenv-py3.13-20261019-185414-unidecode
usage: unidecode [-h] [-e ENCODING] [-c TEXT] [FILE]
```

The remaining acceptance checks:

```bash
ls -A "$S/home/veny"
rg -c 'Creating new virtual environment' "$S/run2.log"; echo "rc=$?"
rg -c 'Using existing virtual environment:' "$S/run2.log"
"$S"/home/veny/myenv-py3.*-unidecode/bin/unidecode --help >/dev/null; echo "rc=$?"
ls "$S/home/veny/" | rg '^myenv-py3\.\d+-\d{8}-\d{6}-unidecode$'
```

```text
module_aliases_cache.json
myenv-py3.13-20261019-185414-unidecode
rc=1
1
rc=0
myenv-py3.13-20261019-185414-unidecode
```

`rc=1` on the `Creating new virtual environment` count means no match: run 2
built nothing. `run1.log` shows the build in `failed-myenv-py3.13-…` and its
`Running command:` line already naming the unprefixed `myenv-…` path.

### Final review fix

The final whole-branch review found that `last_used.save`, now done before the
launch, raised `OSError` out of `cli.main` when the script's directory was not
writable, so the script never ran.

Red (`pytest tests/test_cli_entry_point.py -k cannot_be_saved`):

```text
E       PermissionError: [Errno 13] Permission denied: '/tmp/pytest-of-claudeuser/pytest-134/test_a_record_that_cannot_be_s0'
======================= 1 failed, 46 deselected in 2.00s =======================
```

Green:

```text
======================= 1 passed, 46 deselected in 1.44s =======================
```

Gate at the commit:

```text
pixi run python -m pytest                      497 passed in 26.32s
pixi run python -m pytest --cov                497 passed in 25.52s (TOTAL 86%)
pixi run python -m mypy --exclude '^tempy/' .  Found 23 errors in 6 files
pixi run ruff check .                          All checks passed!
pixi run ruff format --check .                 65 files already formatted
```

```text
pixi run pre-commit run --all-files
ruff.....................................................................Passed
ruff-format..............................................................Passed
mypy.....................................................................Failed
check-merge-conflict.....................................................Passed
check-added-large-files (limit 500 KB)...................................Passed
check-toml...............................................................Passed
```

The `mypy` hook is the known failure: with `tempy/` present it stops at
`Duplicate module named "veny"`, and its real count is the mypy line above.
