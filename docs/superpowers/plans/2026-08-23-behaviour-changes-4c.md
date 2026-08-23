# Phase 4c: the behaviour changes — the last of the veny re-architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close phase 4 by making the four behaviour changes the earlier phases recorded and refused to make — the in-virtualenv guard asks about the user's environment instead of veny's own, `--feeling-lucky`'s exit status is normalized like every other path's, `-y`/`--yes` actually reaches `blank_slate`, and every launch announces the command it runs — then reconcile the two dead-argument lists into one and retire the entries that these changes kill.

**Architecture:** Every change is local and each has exactly one owner module. `last_used` stops answering "is this process inside a virtualenv?" (`sys.prefix != sys.base_prefix`, which describes veny's own interpreter) and answers "which environment did the *user* activate?" instead, as a single `Path | None` read of `VIRTUAL_ENV`; `pipeline.run`'s middle branch takes that value directly. `cli.main` grows one private helper that owns the negative-returncode arithmetic, and both of its exit paths go through it. `pipeline.blank_slate` reads `args.yes` — the dest argparse actually writes — instead of `args.y`, which never existed. `pipeline.run_script` is called with `announce=True` at all four of its call sites, which makes its `rawlog` argument live everywhere and closes four dead rows by making the behaviour uniform rather than by deleting the argument.

**Tech Stack:** Python 3.12+, `dataclasses` (frozen), stdlib `json`/`os`/`argparse`, pytest, mypy, ruff, pixi, uv.

**Global Constraints:**

- **This phase is NOT behaviour-preserving, and it is the only phase of the program that is not.** Four changes are named and sanctioned — the guard, the lucky exit status, `-y`, and the announce lines. Task 5's dead-argument work IS behaviour-preserving: nothing there may change a single visible byte. Any visible difference outside the four named changes is a bug, not a deviation.
- **Every number in this plan is re-measured, not trusted.** The counts and line numbers below were taken on 2026-08-23 at `f7b11fc` (`main`). Line numbers move as soon as Task 1 lands; re-derive with `rg -n`, never by adding an offset.
- **`pixi run` sets `PYTHONPATH=src`.** Any tool that runs the suite outside `pixi run` must set it, or `tests/test_import_guard.py` fails under every mutation and reports spurious kills. This cost phase 4a a whole sweep and 4b re-recorded the warning; do not pay it a third time.
- **`pixi run` also hides the branch this phase is about.** In the pixi environment `sys.prefix == sys.base_prefix` and `VIRTUAL_ENV` is unset, so the middle branch of `pipeline.run` never executes. That is why Task 8 exists and why its live check must not use `pixi run`. Two phases have now closed with end-to-end evidence blind to this branch; this one may not.
- **`pipeline.py` calls its collaborators through the module object** (`last_used.active_virtualenv_dir()`, never `from .last_used import active_virtualenv_dir`). Keep it that way — it is what lets a test replace one boundary.
- **No module may import the module above it.** `tests/test_layering.py` is the layer-graph specification, and its comments are part of that specification: if a comment there names a function this plan deletes or renames, it is wrong the moment the code lands and must be fixed in the same commit. Phase 4b's whole-branch review caught exactly this failure.
- **The 4b wiring index is keyed on `file:line` in `last_used.py`, `pipeline.py`, `cache_search.py` and `cli.py`.** This plan edits all four, so it invalidates the index at Task 1 and must regenerate it at Task 6. Do not cite a 4b row number as evidence after Task 1.
- **Gates, every task:** `pixi run test`, `pixi run lint` and `pixi run python -m ruff format --check .` must be green before the commit. `pixi run typecheck` must not exceed the **23 errors in 6 files (55 source files)** baseline measured on `main` at `f7b11fc`; re-measure, do not copy.
- **Commit after every task, Conventional Commits, imperative mood.** Never end a task with work uncommitted.

**User decisions (already made):**

- **2026-08-23 — the in-virtualenv guard gates on `VIRTUAL_ENV` only.** A veny installed the documented way (`uv tool install veny`) no longer believes the user is inside a virtualenv, so runs fall through to the cache search. An activated environment is still import-checked. The accepted cost: a virtualenv entered by running its interpreter directly, without activation and therefore without `VIRTUAL_ENV`, stops being checked and gets a cached environment instead.
- **2026-08-23 — every launch announces the command it is about to run.** `announce=True` at all four `run_script` call sites. `rawlog` becomes live at all four and the four dead rows close. The accepted cost: three extra `Running command: …` INFO lines on runs that did not pass `--rawlog` and did not previously emit them.
- **2026-08-23 — the five unreachable `getattr(args, …, False)` defaults become direct attribute access.** The accepted cost: hand-built `argparse.Namespace()` objects in the unit tests that omit those flags start raising `AttributeError` and must be given the attribute explicitly.
- **2026-08-23 — the live end-to-end check is built by the executing agent**, in a throwaway virtualenv, in both shapes (activated with `VIRTUAL_ENV` set; unactivated with it unset), with the output captured into the task report. No action is required from the user.
- **2026-08-21 (carried from 4a and 4b) — phase 4 is three plans.** This is **4c**, the last of them. `Options`, `run_options.py`, `json_types.py` and `pathlibcutoff` are already gone; do not go looking for them.

---

## Context an executing engineer needs

**Read first:** `PROGRESS.md` — all of it, including the deferred items, gotchas and cross-cutting decisions, which live nowhere else — and `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md`.

**Where things stand.** Phases 1, 2, 3 and 4a/4b are merged to `main`, which is at `f7b11fc`. `src/veny/` is 7,256 lines across 22 modules. `pixi run test` reports 455 passed. Nothing in the tree constructs an `Options`.

**The four behaviour changes, with the exact code as it stands at `f7b11fc`.**

1. **The guard.** `src/veny/last_used.py:17-19`:

   ```python
   def is_virtualenv() -> bool:
       """Check if currently running in a virtual environment."""
       return sys.prefix != sys.base_prefix
   ```

   Its one production caller is `src/veny/pipeline.py:841`, the middle branch of `run`: `elif last_used.is_virtualenv():`. That branch import-checks the surrounding environment and, when it does not satisfy the run, logs "Please deactivate the current virtual environment and run the script again." and returns 1 — leaving the cache search and `setup_virtualenv` unreachable. Because veny's own documented install puts veny in a venv (`README.md:16`, `environment.py`'s `UvUnavailable` message, `scripts/smoke-install.sh:33-34`), `sys.prefix != sys.base_prefix` is **always True** there, and every run with a missing import hits that dead end. `active_virtualenv_dir()` (`:22-36`) already prefers `VIRTUAL_ENV` and falls back to `sys.prefix`; Task 1 collapses the pair into one function so the "whether" and the "which" can never disagree, and so the `sys.prefix` fallback — unreachable once the guard reads the environment variable — does not survive as a dead arm.

2. **The lucky exit status.** `src/veny/cli.py:212-219` returns `pipeline.feeling_lucky`'s status from the middle of `main`, before the tail at `:245-247` that turns a negative returncode into `128 + signal`. A lucky run killed by SIGKILL therefore returns `-9`, which the shell wraps to 247, while the same script on the ordinary path returns 137. `main`'s docstring currently documents this asymmetry as deliberate; that docstring is part of what Task 2 changes.

3. **`-y`/`--yes`.** `cli.parse_arguments` registers `"-y", "--yes"` (`src/veny/cli.py:103-108`), so argparse writes the dest **`yes`**. `pipeline.blank_slate` reads `getattr(args, "y", False)` (`src/veny/pipeline.py:462`), which is never set, so `veny --blank-slate -y` prompts anyway — the flag has never worked.

4. **The announce lines.** `run_script` (`src/veny/pipeline.py:311-341`) logs `Running command: …` only when `announce` is True and `rawlog` is False. Four call sites: `:431` (the lucky launch), `:832` (everything already installed), `:855` (the surrounding virtualenv satisfied the run) and `:935` (the venv launch). Only `:935` passes `announce=True`; the other three pass `rawlog=` and nothing can read it. `tests/test_cli_entry_point.py:1353` pins the current asymmetry with a test whose docstring argues *for* it — Task 4 rewrites that test to the new expected behaviour before touching the code, as CLAUDE.md's TDD rule requires for a behaviour change.

**The two dead-argument lists Task 5 reconciles.** 4a's five are in `docs/superpowers/plans/2026-08-21-state-model-values-wiring-index.md` § "The 5 DEAD ARGUMENTS"; 4b's eight are in `docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md` § "The 8 DEAD ARGUMENTS". They overlap: the `run_script(rawlog=…)` finding appears in both (three sites in 4a's, a fourth in 4b's). After Tasks 4 and 5 the reconciled list should hold only the two rows nothing in this phase can close.

**Gotcha: a bare `argparse.Namespace()` in a test is what keeps a `getattr` default alive.** `tests/test_cache_search.py:582` and `:612` and `tests/test_wiring_4b.py:853` hand `find_match_dir_in_cache` a Namespace with no flags at all. Those three are the predicted `AttributeError`s in Task 5; the suite will name any others.

**Gotcha: `ek.print_all_errors` dereferences its first argument.** Its body is `if memory_handler.logs and not rawlog:`, so passing `None` raises `AttributeError`. The lucky path deliberately runs *before* `ek.configure_logging`, so `memory_handler` is `None` there. Task 2 must not route the lucky return through that call — only through the status arithmetic.

**Gotcha: the differential, not the suite, catches this phase's real defect.** Three phases running. The unit tests move with the code; what they cannot see is the two-run, real-shell property — which environment a run actually chose. Task 7's driver and Task 8's live check exist for that.

---

## File Structure

| File | Change | Responsibility after this plan |
|---|---|---|
| `src/veny/last_used.py` | Modify | Owns the record and, now, one honest answer to "which environment did the user activate?" — `active_virtualenv_dir() -> Path \| None`. `is_virtualenv()` is deleted. |
| `src/veny/pipeline.py` | Modify | `run`'s middle branch reads the activated environment once; `blank_slate` reads `args.yes`; all four `run_script` calls announce; `feeling_lucky` reads `args.feeling_lucky` directly. |
| `src/veny/cli.py` | Modify | Gains `_shell_status`, the single owner of the negative-returncode arithmetic, used by both of `main`'s exit paths. Reads `args.rawlog` and `args.debug` directly. |
| `src/veny/cache_search.py` | Modify | Loses the provably redundant `last_used` term inside `explicit`; reads `args.last_used` directly at the surviving site. |
| `tests/test_last_used.py` | Modify | Pins the new guard in both directions; the `sys.prefix`/`sys.base_prefix` test goes with the function it described. |
| `tests/test_cli_entry_point.py` | Modify | Pins the fall-through for a veny that is itself in a venv, the lucky signal normalization, and the four announcing launches. |
| `tests/test_cache_search.py`, `tests/test_wiring_4b.py` | Modify | Hand-built Namespaces gain the flags the direct reads now require. |
| `tests/test_layering.py` | Modify | Any comment naming `is_virtualenv` is corrected in the same commit as its deletion. |
| `scripts/wiring_sweep_4c.py` | Create | Task 6's sweep over the four modules this phase edits. |
| `docs/superpowers/plans/2026-08-23-behaviour-changes-4c-wiring-index.md` | Create | Task 6's argument-by-argument index, replacing 4b's for these modules, and carrying the single reconciled dead-argument list. |
| `scripts/differential_4c.py` | Create | Task 7's before/after driver, in the shape of `scripts/differential_4b.py`. |
| `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md` | Modify | Task 9: ledger item 5's false claim corrected; the phase-4c amendments recorded. |
| `PROGRESS.md` | Modify | Task 10: the phase's ledger entry, measured gates, and what 4c hands on. |

---

### Task 1: The guard asks about the user's environment, not veny's

**Goal:** `pipeline.run`'s middle branch triggers on the environment the user activated (`VIRTUAL_ENV`), not on veny's own interpreter prefix, so a `uv tool install`ed veny reaches its cache search instead of dead-ending.

**Files:**
- Modify: `src/veny/last_used.py:17-36`
- Modify: `src/veny/pipeline.py:841-845`
- Modify: `tests/test_last_used.py:97-146`
- Modify: `tests/test_cli_entry_point.py:509-560`, `:775-790`, `:1323-1335`
- Modify: `tests/test_layering.py` (only if a comment there names `is_virtualenv`)

**Acceptance Criteria:**
- [ ] `last_used.is_virtualenv` no longer exists: `rg -nw 'is_virtualenv' src/ tests/ scripts/` returns nothing outside historical differential drivers under `scripts/`.
- [ ] `last_used.active_virtualenv_dir()` returns `None` when `VIRTUAL_ENV` is unset or empty, and `ek.ensure_path(VIRTUAL_ENV)` when it is set.
- [ ] With `VIRTUAL_ENV` unset, a run whose imports are missing reaches `cache_search.find_match_dir_in_cache` — pinned by a test that fails against the old code.
- [ ] With `VIRTUAL_ENV` set, the surrounding environment is still import-checked, and the existing three tests that drive that branch pass without monkeypatching any veny function.
- [ ] `sys` is still imported in `last_used.py` only if something still uses it; if nothing does, the import goes.

**Verify:** `pixi run python -m pytest tests/test_last_used.py tests/test_cli_entry_point.py -q` → all pass; `pixi run test` → 455 or more passed.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Replace `test_is_virtualenv_reflects_prefix_vs_base_prefix` and `test_active_virtualenv_dir_falls_back_to_sys_prefix` in `tests/test_last_used.py` with these three. Keep `test_active_virtualenv_dir_prefers_the_environment_variable` as it stands.

```python
def test_active_virtualenv_dir_is_none_when_nothing_is_activated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No VIRTUAL_ENV means no activated environment, whatever sys.prefix says.

    A bug that would make this fail: answering from sys.prefix, the way veny
    did until phase 4c. veny's own documented install (`uv tool install veny`)
    puts veny inside a virtualenv, so a sys.prefix answer is True on every
    such install -- and pipeline.run then import-checks veny's own tool venv,
    fails, and tells the user to deactivate an environment they never
    activated, with the cache search unreachable behind it.
    """
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(sys, "prefix", "/fake/venv")
    monkeypatch.setattr(sys, "base_prefix", "/fake/base")

    assert last_used.active_virtualenv_dir() is None


def test_active_virtualenv_dir_is_none_when_the_variable_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty VIRTUAL_ENV is not an activated environment.

    A bug that would make this fail: `os.environ.get("VIRTUAL_ENV") is not
    None` instead of a truthiness test, which would make an exported-but-empty
    variable name Path("") -- the current working directory -- as the
    environment to import-check.
    """
    monkeypatch.setenv("VIRTUAL_ENV", "")

    assert last_used.active_virtualenv_dir() is None


def test_active_virtualenv_dir_answers_with_a_path_not_a_string(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The answer is a Path, because its caller joins bin/python onto it.

    A bug that would make this fail: returning the raw environment string.
    environment.venv_python_for does `venv_dir / "bin" / "python"`, which
    raises TypeError on a str -- but only on the branch this value reaches,
    which no other test in this file drives.
    """
    monkeypatch.setenv("VIRTUAL_ENV", os.fspath(tmp_path / "activated"))

    answer = last_used.active_virtualenv_dir()

    assert isinstance(answer, Path)
    assert answer == tmp_path / "activated"
```

Then add this test to `tests/test_cli_entry_point.py`, next to `test_main_checks_the_surrounding_virtualenv_against_this_runs_imports`:

```python
def test_main_ignores_venys_own_virtualenv_and_goes_to_the_cache(
    monkeypatch, tmp_path
):
    """veny installed in a venv is not the user standing in one.

    Behaviour under test: with no VIRTUAL_ENV exported, a run with a missing
    import must reach the cache search, whatever sys.prefix says about veny's
    own interpreter.

    Concrete bug this catches: the pre-4c guard, `sys.prefix !=
    sys.base_prefix`. veny's documented install is `uv tool install veny`,
    which puts veny in a venv, so that guard was True on every such install:
    the run import-checked veny's own tool environment, failed, logged
    "Please deactivate the current virtual environment and run the script
    again." and returned 1 -- with find_match_dir_in_cache never called.
    """
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(sys, "prefix", "/fake/venv")
    monkeypatch.setattr(sys, "base_prefix", "/fake/base")
    _drive_main(
        monkeypatch,
        tmp_path,
        [],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    seen: list[dict[str, object]] = []

    def search_spy(args, **kwargs):
        seen.append({"args": args, **kwargs})
        return None

    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", search_spy)

    cli.main()

    assert len(seen) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run python -m pytest tests/test_last_used.py -q -k active_virtualenv` and `pixi run python -m pytest tests/test_cli_entry_point.py -q -k ignores_venys_own`

Expected: the three `last_used` tests FAIL (`active_virtualenv_dir` returns `Path("/fake/venv")` and `Path("")` rather than `None`), and the `cli_entry_point` test FAILS with `assert 0 == 1` — the run took the in-virtualenv branch and never reached the search.

- [ ] **Step 3: Change the guard**

In `src/veny/last_used.py`, delete `is_virtualenv` and replace `active_virtualenv_dir` with:

```python
def active_virtualenv_dir() -> Path | None:
    """The virtual environment the user activated, if there is one.

    Deliberately not `sys.prefix != sys.base_prefix`: that describes veny's
    own interpreter, and veny's documented install (`uv tool install veny`)
    puts veny inside a virtualenv. Under that install the prefix test was
    always true, so every run with a missing import checked veny's own tool
    environment, failed, and told the user to deactivate something they had
    never activated -- with the cache search unreachable behind it.
    VIRTUAL_ENV is what an activate script exports, and is the user's own
    statement of which environment they meant.

    One function rather than a whether/which pair, so the two answers cannot
    disagree: a caller that gets a directory back knows the user activated it.

    Returns:
        The activated environment's root directory, or None when the user has
        not activated one. A virtualenv entered by running its interpreter
        directly, without activation, reads as None -- veny treats that as
        "no environment declared" and uses its own cache instead.
    """
    declared = os.environ.get("VIRTUAL_ENV")
    if not declared:
        return None
    return ek.ensure_path(declared)
```

Delete `import sys` from `last_used.py` if nothing else in the module uses it (`rg -nw 'sys' src/veny/last_used.py`).

In `src/veny/pipeline.py`, rewrite the middle branch's head — the `elif` at `:841` and the `active_venv` assignment at `:844`:

```python
    elif (active_venv := last_used.active_virtualenv_dir()) is not None:
        if not settings.rawlog:
            logging.info("Already in a virtual environment.")
        if verify.check_packages_in_venv(
```

(the `active_venv = last_used.active_virtualenv_dir()` line is deleted; the rest of the branch is unchanged.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test`

Expected: all pass. If `test_main_checks_the_surrounding_virtualenv_against_this_runs_imports`, `:775` or `:1323` fail, it is because they monkeypatch `last_used.is_virtualenv`, which no longer exists — delete that `monkeypatch.setattr(last_used, "is_virtualenv", lambda: True)` line from each. They already `monkeypatch.setenv("VIRTUAL_ENV", …)`, which is now sufficient, and dropping the stub makes them stronger: they drive the real function.

- [ ] **Step 5: Check the layer-graph specification**

Run: `rg -nw 'is_virtualenv' tests/test_layering.py README.md docs/`

Expected: no hits. If there are any, fix them in this commit — `tests/test_layering.py`'s comments ARE the layer specification, and phase 4b's whole-branch review found exactly this kind of stale claim after the code moved under it.

- [ ] **Step 6: Commit**

```bash
git add src/veny/last_used.py src/veny/pipeline.py tests/
git commit -m "feat: gate the in-virtualenv branch on VIRTUAL_ENV, not veny's own prefix"
```

---

### Task 2: `--feeling-lucky` gets the same exit status arithmetic as every other path

**Goal:** A lucky run killed by a signal returns `128 + signal`, exactly as the ordinary path does, with the arithmetic owned by one function rather than duplicated.

**Files:**
- Modify: `src/veny/cli.py:173-247`
- Modify: `tests/test_cli_entry_point.py` (add one test beside the lucky-launch tests near `:1494`)

**Acceptance Criteria:**
- [ ] `cli._shell_status` exists, is the only place `128 - script_exit_code` is written, and is called on both of `main`'s exit paths.
- [ ] A lucky run whose child returns `-9` makes `cli.main()` return `137`.
- [ ] An ordinary run whose child returns `-9` still returns `137` (unchanged).
- [ ] The lucky path still does NOT call `ek.print_all_errors` — `memory_handler` is `None` there and that function dereferences it.
- [ ] `main`'s docstring no longer documents the asymmetry as deliberate.

**Verify:** `pixi run python -m pytest tests/test_cli_entry_point.py -q -k "lucky or status"` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli_entry_point.py`:

```python
def test_a_lucky_run_killed_by_a_signal_reports_the_shell_status(
    monkeypatch, tmp_path
):
    """--feeling-lucky normalizes a signal death like every other path.

    Behaviour under test: a child killed by SIGKILL returns -9 from
    subprocess, and a process exiting with -9 wraps around to 247 in the
    shell. Every other veny path turns that into 137 (128 + 9).

    Concrete bug this catches: returning pipeline.feeling_lucky's status
    from the middle of main(), which is what veny did until phase 4c -- so
    the same script killed the same way reported 247 under --feeling-lucky
    and 137 without it, and a wrapper script keying on 137 silently stopped
    seeing kills the moment a user added the flag.
    """
    lucky_python, _ = _a_lucky_run(monkeypatch, tmp_path, [])
    monkeypatch.setattr(
        pipeline, "run_script", lambda *args, **kwargs: -9
    )

    assert cli.main() == 137
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pixi run python -m pytest tests/test_cli_entry_point.py -q -k lucky_run_killed`

Expected: FAIL with `assert -9 == 137`.

- [ ] **Step 3: Give the arithmetic one owner and route both paths through it**

In `src/veny/cli.py`, add above `main`:

```python
def _shell_status(script_exit_code: int) -> int:
    """Map a child's returncode onto the status veny exits with.

    A script killed by a signal yields a negative returncode (e.g. -9 for
    SIGKILL). Exiting a process with a negative status wraps around to the
    wrong shell status (-9 becomes 247), so it is reported as the
    conventional 128 + signal number (-9 becomes 137) instead.

    One function rather than two copies of the arithmetic: until phase 4c
    the --feeling-lucky path returned from the middle of main() and skipped
    the tail that did this, so the same signal produced two different
    statuses depending on one flag.

    Args:
        script_exit_code: The child's returncode, negative if it was killed.

    Returns:
        The status veny should exit with.
    """
    if script_exit_code < 0:
        return 128 - script_exit_code
    return script_exit_code
```

In `main`, replace the lucky return:

```python
        if lucky_status is not None:
            return _shell_status(lucky_status)
```

and the tail (`src/veny/cli.py:242-247`, the comment plus the `if` plus the `return`):

```python
    return _shell_status(script_exit_code)
```

Then rewrite the four docstring lines in `main` that describe the asymmetry:

```python
        The wrapped script's exit status; 0 when nothing was meant to run
        (--justprint, --blank-slate); 1 when veny could not find or build an
        environment; 2 for a usage error. A child killed by a signal is
        reported as 128 + signal rather than as a negative status, which the
        shell would wrap around to the wrong number -- on every path,
        --feeling-lucky included, since phase 4c.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test`

Expected: all pass, including the pre-existing ordinary-path normalization tests. `rg -n '128 - ' src/` must return exactly one line.

- [ ] **Step 5: Commit**

```bash
git add src/veny/cli.py tests/test_cli_entry_point.py
git commit -m "fix: normalize --feeling-lucky's exit status like every other path"
```

---

### Task 3: `-y`/`--yes` actually reaches `blank_slate`

**Goal:** `veny --blank-slate -y` deletes without prompting, which is what `--yes`'s help text has always promised.

**Files:**
- Modify: `src/veny/pipeline.py:456-462`
- Modify: `tests/test_cli_entry_point.py` (beside the existing blank-slate tests)

**Acceptance Criteria:**
- [ ] `blank_slate` reads `args.yes` — the dest argparse writes for `"-y", "--yes"` — and `rg -n '"y"' src/veny/pipeline.py` returns nothing.
- [ ] A run with `--blank-slate -y` never calls `ek.prompt_then_confirm` and still deletes.
- [ ] A run with `--blank-slate` alone still prompts, and still returns 0 when the user declines.

**Verify:** `pixi run python -m pytest tests/test_cli_entry_point.py -q -k blank_slate` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli_entry_point.py`:

```python
def test_yes_skips_the_blank_slate_confirmation(monkeypatch, tmp_path):
    """--yes means veny must not stop to ask.

    Behaviour under test: the flag documented as "automatically say yes to
    any prompts to allow this program to run without the need for user
    interaction" must suppress the only prompt veny has.

    Concrete bug this catches: reading `getattr(args, "y", False)`, which is
    what veny did until phase 4c. argparse writes the dest `yes` for
    "-y", "--yes", so the read was of an attribute that never existed and
    the default False always won: every --blank-slate -y run blocked on a
    prompt, which is exactly the unattended use the flag exists for.
    """
    asked: list[str] = []
    monkeypatch.setattr(
        ek, "prompt_then_confirm", lambda prompt: asked.append(prompt) or True
    )
    monkeypatch.setattr(sys, "argv", ["veny", "--blank-slate", "-y"])
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "home" / "veny").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    assert cli.main() == 0

    assert asked == []
    assert not (tmp_path / "home" / "veny").exists()
```

Check the existing blank-slate tests first (`rg -n 'blank_slate' tests/test_cli_entry_point.py`) and reuse their fixture style if they already have a helper for the home directory and cwd — do not build a second one beside it.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pixi run python -m pytest tests/test_cli_entry_point.py -q -k yes_skips`

Expected: FAIL on `assert asked == []` — the prompt was issued.

- [ ] **Step 3: Read the flag argparse actually writes**

In `src/veny/pipeline.py`, change the guard and the docstring line above it:

```python
    Args:
        settings: The run's invariants; reads my_name, my_dir and cwd.
        args: The parsed command line; reads the --yes flag.
```

```python
    if not args.yes:
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test`

Expected: all pass. If a test that drives `blank_slate` with a hand-built Namespace now raises `AttributeError: 'Namespace' object has no attribute 'yes'`, add `yes=False` to that Namespace — it is the same class of repair Task 5 does deliberately.

- [ ] **Step 5: Commit**

```bash
git add src/veny/pipeline.py tests/test_cli_entry_point.py
git commit -m "fix: read the --yes dest argparse writes so -y skips the prompt"
```

---

### Task 4: Every launch announces the command it runs

**Goal:** All four `run_script` call sites pass `announce=True`, so `Running command: …` appears on every launch unless `--rawlog` silences it — and `rawlog` becomes a live argument at all four, closing 3e's latent defect 3.

**Files:**
- Modify: `src/veny/pipeline.py:431`, `:832`, `:855` (the three `run_script(...)` calls without `announce`)
- Modify: `src/veny/pipeline.py:311-341` (`run_script`'s docstring for `announce`)
- Modify: `tests/test_cli_entry_point.py:1353-1415` (the test that pins the current asymmetry)

**Acceptance Criteria:**
- [ ] All four `run_script` call sites pass `announce=True`; `rg -n 'announce=' src/veny/pipeline.py` returns four call-site lines plus the parameter.
- [ ] Each of the four launches logs `Running command: <interpreter> <script> <args…>` on a run that did not pass `--rawlog`.
- [ ] Each of the four stays silent under `--rawlog`.
- [ ] `run_script`'s `announce` parameter keeps its default of `False` — no caller relies on the default, and leaving it means a future caller must say what it wants.

**Verify:** `pixi run python -m pytest tests/test_cli_entry_point.py -q -k announce` → all pass.

**Steps:**

- [ ] **Step 1: Rewrite the existing test to the new expected behaviour**

Replace `test_only_the_venv_launch_announces_the_command_it_is_about_to_run` (`tests/test_cli_entry_point.py:1353`) with this. The name changes with the behaviour; the four helpers it drives (`_a_cache_hit`, `_drive_main`, `_an_active_virtualenv_that_satisfies_the_run`, `_a_lucky_run`) are unchanged.

```python
def test_every_launch_announces_the_command_it_is_about_to_run(
    monkeypatch, tmp_path, caplog
):
    """All four of run_script's call sites announce, and --rawlog silences all four.

    Behaviour under test: which launches log "Running command: ...". Until
    phase 4c only the venv launch did; the other three passed run_script a
    `rawlog` argument that nothing could read, because `announce` was False
    there and `rawlog` guards only the announce line.

    Concrete bug this catches: dropping announce=True from any one site,
    which removes the only record of which interpreter that path launched --
    the first thing anyone debugging a wrong-environment run looks for, and
    the one thing the differential cannot recover after the fact. A second
    bug this catches: announcing regardless of rawlog, which puts veny's own
    commentary into output whose contract is "the same output you would see
    without veny".
    """
    script = os.fspath(tmp_path / "script.py")

    # 1. The venv launch.
    venv_dir, _ = _a_cache_hit(monkeypatch, tmp_path, [])
    with caplog.at_level(logging.INFO):
        cli.main()
    assert (
        f"Running command: {os.fspath(venv_dir / 'bin' / 'python')} {script}"
        in caplog.text
    )

    # 2. Nothing to install: the bare interpreter launch.
    caplog.clear()
    _drive_main(monkeypatch, tmp_path, [], uninstalled=set(), all_imports={"os"})
    with caplog.at_level(logging.INFO):
        cli.main()
    assert f"Running command: {sys.executable} {script}" in caplog.text

    # 3. The activated virtualenv satisfied the run.
    caplog.clear()
    _an_active_virtualenv_that_satisfies_the_run(monkeypatch, tmp_path, [])
    with caplog.at_level(logging.INFO):
        cli.main()
    assert f"Running command: {sys.executable} {script}" in caplog.text

    # 4. --feeling-lucky, which reports with print() rather than logging for
    #    everything else it says, because it runs before logging is
    #    configured -- but run_script's announce line is a log line on every
    #    path, and caplog sees it.
    caplog.clear()
    lucky_python, _ = _a_lucky_run(monkeypatch, tmp_path, [])
    with caplog.at_level(logging.INFO):
        cli.main()
    assert f"Running command: {os.fspath(lucky_python)} {script}" in caplog.text

    # --rawlog silences every one of them: run_script's rawlog argument is
    # this run's own, at all four sites.
    for setup in (
        lambda: _a_cache_hit(monkeypatch, tmp_path, ["--rawlog"]),
        lambda: _drive_main(
            monkeypatch,
            tmp_path,
            ["--rawlog"],
            uninstalled=set(),
            all_imports={"os"},
        ),
        lambda: _an_active_virtualenv_that_satisfies_the_run(
            monkeypatch, tmp_path, ["--rawlog"]
        ),
        lambda: _a_lucky_run(monkeypatch, tmp_path, ["--rawlog"]),
    ):
        caplog.clear()
        setup()
        with caplog.at_level(logging.INFO):
            cli.main()
        assert "Running command" not in caplog.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pixi run python -m pytest tests/test_cli_entry_point.py -q -k every_launch_announces`

Expected: FAIL at assertion 2 — the bare-interpreter launch logs nothing.

- [ ] **Step 3: Announce at the three quiet sites**

In `src/veny/pipeline.py`, add `announce=True,` to the calls at `:431` (inside `feeling_lucky`), `:832` (the "All required packages are already installed" branch) and `:855` (the satisfied-virtualenv branch). Each becomes, with its own interpreter and arguments unchanged:

```python
        returncode = run_script(
            last_used_venv_python,
            target.python_script,
            list(target.script_args),
            rawlog=rawlog,
            announce=True,
        )
```

Then correct `run_script`'s docstring for the argument, which currently describes the asymmetry this task removes:

```python
        announce: True logs the command before running it. Every call site
            passes True since phase 4c; the default stays False so a new
            caller has to say what it wants.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run test`

Expected: all pass. Any other test asserting `"Running command" not in caplog.text` for one of these three paths is asserting the old behaviour — update it to expect the line, and say so in the commit message.

- [ ] **Step 5: Commit**

```bash
git add src/veny/pipeline.py tests/test_cli_entry_point.py
git commit -m "feat: announce the command on every launch, not just the venv one"
```

---

### Task 5: One dead-argument list, and the entries this phase can close

**Goal:** Reconcile 4a's five and 4b's eight dead arguments into a single list with a disposition for each, delete the two constructs that are provably unreachable, and convert the five unreachable `getattr` defaults to direct attribute access — with no visible behaviour change from any of it.

**Files:**
- Modify: `src/veny/cache_search.py:593-604` (the `explicit` term and the surviving `last_used` read)
- Modify: `src/veny/pipeline.py:422`, `:888`
- Modify: `src/veny/cli.py:191`, `:194`
- Modify: `tests/test_cache_search.py:582`, `:612`; `tests/test_wiring_4b.py:853` (and any others the suite names)
- Create: `docs/superpowers/plans/2026-08-23-behaviour-changes-4c-dead-arguments.md`

**Acceptance Criteria:**
- [ ] `cache_search.find_match_dir_in_cache`'s `explicit` is `getattr(args, "latest", False) or getattr(args, "oldest", False) or getattr(args, "smallest", False)` — the `last_used` term is gone, and the comment above `try_last_used` still describes what the code does.
- [ ] The five sites read `args.last_used`, `args.feeling_lucky`, `args.reqs`, `args.rawlog` and `args.debug` directly.
- [ ] `pixi run test` is green with no test skipped or deleted; hand-built Namespaces gained attributes rather than losing assertions.
- [ ] The reconciled list names every one of the thirteen prior rows, each marked `CLOSED by Task N` or `OPEN, with its reason`, and the OPEN set is exactly two: `pipeline.py`'s `ResolvedImport(pip_name=import_name)` probe row (indistinguishable by construction) and the `state.VenvHandle.for_dir(record_venv_state(...))` row (mis-filed — measured by driving, not dead).
- [ ] No visible behaviour changes: this task's commit must not alter any log line, status or argv.

**Verify:** `pixi run test` → 455 or more passed; `pixi run python -m pytest tests/test_cache_search.py -q` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test for the flag algebra that must not move**

The `explicit` deletion is provable by exhaustion, so pin it by exhaustion. Add to `tests/test_cache_search.py`:

```python
@pytest.mark.parametrize(
    "flags",
    [
        {"latest": a, "oldest": b, "last_used": c, "smallest": d}
        for a in (False, True)
        for b in (False, True)
        for c in (False, True)
        for d in (False, True)
    ],
)
def test_the_last_used_pass_is_tried_for_exactly_the_same_flag_combinations(
    tmp_path: Path, flags: dict[str, bool]
) -> None:
    """All 16 flag combinations decide the last-used pass the same way.

    Behaviour under test: whether find_match_dir_in_cache consults the
    last-used record. The rule is "no explicit choice, or an explicit
    --last-used, and neither --latest nor --smallest overriding it".

    Concrete bug this catches: dropping the wrong term while simplifying
    `explicit`. Removing `--oldest` from it, for example, makes a bare
    `--oldest` run consult the last-used record first and quietly return the
    last environment rather than the oldest matching one -- a wrong venv, on
    a flag whose whole purpose is to name which venv.
    """
    args = argparse.Namespace(**flags)
    consulted: list[bool] = []

    def load() -> None:
        consulted.append(True)
        return None

    _search(args, my_dir=tmp_path, load_last_used=load)

    expected = not (flags["latest"] or flags["oldest"] or flags["smallest"]) or (
        flags["last_used"] and not flags["latest"] and not flags["smallest"]
    )
    assert bool(consulted) is expected
```

Check `_search`'s signature in that file first and match it; it is the module-level helper the existing tests use.

- [ ] **Step 2: Run the test to verify it passes against the current code**

Run: `pixi run python -m pytest tests/test_cache_search.py -q -k same_flag_combinations`

Expected: PASS — this one is a characterization test, written green on purpose. It is the safety net for Step 3, not a red/green cycle: the whole claim being relied on is that the code before and after decide identically, and a test that only passes after the change could not say that. Record the pass in the task report; if it FAILS, stop — the simplification's premise is wrong and the rest of this task must not proceed.

- [ ] **Step 3: Delete the redundant term and read the flags directly**

In `src/veny/cache_search.py`:

```python
    explicit = (
        getattr(args, "latest", False)
        or getattr(args, "oldest", False)
        or getattr(args, "smallest", False)
    )
    # No flag at all means "the one you used last time" -- a local now, not a
    # write onto args. It was a write only because args was serialized into
    # the options JSON, which veny no longer keeps. The --last-used term is
    # only in try_last_used: inside `explicit` it could not change any
    # outcome, for any of the 16 flag combinations (phase 4b, measured).
    try_last_used = not explicit or args.last_used
```

In `src/veny/pipeline.py:422`:

```python
    if not args.feeling_lucky or target is None:
```

In `src/veny/pipeline.py:888` (the `source_import_names` call inside `run`'s cache-search arm), replace `getattr(args, "reqs", False)` with `args.reqs`.

In `src/veny/cli.py:191` and `:194`:

```python
    rawlog = args.rawlog
    # Only ek.configure_logging below reads this, so it is a local rather
    # than a field on anything.
    log_mode = logging.DEBUG if args.debug else logging.INFO
```

Leave every other `getattr(args, …)` alone. The rule, worth writing into the dead-argument doc: a `getattr` default that a test reaches is live and stays; these five were reachable from nothing at all.

- [ ] **Step 4: Run the suite and repair the hand-built Namespaces**

Run: `pixi run test`

Expected: failures with `AttributeError: 'Namespace' object has no attribute 'last_used'` from `tests/test_cache_search.py:582` and `:612` and `tests/test_wiring_4b.py:853`, each of which passes a bare `argparse.Namespace()`. Repair each by naming the flags it means:

```python
        argparse.Namespace(latest=False, oldest=False, last_used=False, smallest=False),
```

Re-run until green. Do NOT repair by restoring a `getattr` — if a site genuinely needs a default, it is not dead and belongs back on the OPEN list with that reason.

- [ ] **Step 5: Write the reconciled list**

Create `docs/superpowers/plans/2026-08-23-behaviour-changes-4c-dead-arguments.md` with a heading, one sentence saying it supersedes the two prior "DEAD ARGUMENTS" sections (naming both files and their counts, five and eight), and one table:

| Row (as the prior index named it) | From | Disposition |
|---|---|---|
| `run_script(rawlog=…)` at the three non-announcing sites | 4a | CLOSED by Task 4 — `announce=True` makes `rawlog` live at all four sites |
| `run_script(rawlog=…)` in `feeling_lucky` | 4b | CLOSED by Task 4 — the fourth site, same fix |
| `ResolvedImport(pip_name=import_name)` in the probe environment | 4a | OPEN — the two fields are the same string by construction and `check_packages_in_venv` reads only `import_name`; no substitution can distinguish them. Not a test gap and not deletable |
| `state.VenvHandle.for_dir(record_venv_state(...))` | 4a | OPEN, mis-filed — measured by driving, not dead. Belongs under "measured by driving"; the 4c index files it there |
| `getattr(args, 'feeling_lucky', False)` default | 4b | CLOSED by Task 5 |
| `getattr(args, 'reqs', False)` default | 4b | CLOSED by Task 5 |
| `getattr(args, 'last_used', False)` default | 4b | CLOSED by Task 5 |
| `getattr(args, 'rawlog', False)` default | 4b | CLOSED by Task 5 |
| `getattr(args, 'debug', False)` default | 4b | CLOSED by Task 5 |
| the `last_used` term inside `explicit` (both arguments) | 4b | CLOSED by Task 5 — deleted, with the 16-combination characterization test as the evidence it changed nothing |

Add the rule under the table: *a `getattr(args, …)` default that a test reaches is live and stays; the five closed here were reachable from nothing, in production or in tests.*

- [ ] **Step 6: Commit**

```bash
git add src/veny/cache_search.py src/veny/pipeline.py src/veny/cli.py tests/ docs/superpowers/plans/2026-08-23-behaviour-changes-4c-dead-arguments.md
git commit -m "refactor: reconcile the dead-argument lists and retire what this phase kills"
```

---

### Task 6: The STANDING CHECK — sweep the four modules this phase edited

**Goal:** Regenerate the argument-by-argument wiring index the phase invalidated, so the next phase inherits a valid one instead of a table whose line numbers moved under it.

**Files:**
- Create: `scripts/wiring_sweep_4c.py`
- Create: `docs/superpowers/plans/2026-08-23-behaviour-changes-4c-wiring-index.md`
- Modify: `docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md` (header note only: superseded for these modules)

**Acceptance Criteria:**
- [ ] `scripts/wiring_sweep_4c.py --list` enumerates every call site in scope and prints a count.
- [ ] The full sweep runs to completion and writes its JSON; each site carries a verdict of KILLED, OPEN HOLE, DEAD, MULTILINE or NO SUBSTITUTE.
- [ ] The index names, for every OPEN HOLE, the reason it is open, and for every DEAD row, its disposition — cross-referenced to the Task 5 list rather than restating it.
- [ ] The index's header carries the staleness caveat in the same words 4b's did: it is keyed on `file:line` and any later edit to a swept module invalidates every row below the edit.
- [ ] The four launches Task 4 changed appear as KILLED rows (the announce test kills them), not as OPEN HOLEs.

**Verify:** `pixi run python scripts/wiring_sweep_4c.py --list` → prints the site count; then the full run → JSON written with no site left unverdicted.

**Steps:**

- [ ] **Step 1: Copy 4b's sweep and re-scope it**

```bash
cp scripts/wiring_sweep_4b.py scripts/wiring_sweep_4c.py
```

Then edit `scripts/wiring_sweep_4c.py`:

- Rewrite the module docstring for this phase: what changed (the guard, the lucky status, `-y`, the announce lines, the five direct reads) and what the sweep covers.
- Change the output filename from `sweep4b.json` to `sweep4c.json`.
- In `collect()`, replace the four scope rules with these four:
  1. `src/veny/last_used.py` whole — Task 1 rewrote its virtualenv answer.
  2. `src/veny/pipeline.py`: `feeling_lucky`, `blank_slate` and `run_script` whole, plus every `run_script(...)` call inside `run` and the whole of `run`'s middle branch (the `elif` Task 1 rewrote).
  3. `src/veny/cache_search.py`: `find_match_dir_in_cache` down to the statement that spends `try_last_used`, as 4b's rule already computes it — unchanged, but the line numbers moved.
  4. `src/veny/cli.py`: the whole of `main`, plus `_shell_status`.
- Keep the `PYTHONPATH=src` environment (`ENV`) and the import sanity check exactly as they are. They are why 4a's first sweep had to be thrown away.

- [ ] **Step 2: List the sites and sanity-check the scope**

Run: `pixi run python scripts/wiring_sweep_4c.py --list`

Expected: a site list that includes `pipeline.py`'s four `run_script` calls with their `announce` arguments, `cli.py`'s `_shell_status` calls, and `last_used.py`'s `os.environ.get('VIRTUAL_ENV')`. If any of those is missing, a scope rule is wrong — fix it before the full run. This is the failure 4b's rule-based scope was written to prevent.

- [ ] **Step 3: Run the sweep**

Run: `pixi run python scripts/wiring_sweep_4c.py`

Expected: about twelve minutes, one line per site, ending with a written JSON. Record the headline counts.

- [ ] **Step 4: Write the index**

Create `docs/superpowers/plans/2026-08-23-behaviour-changes-4c-wiring-index.md` in the shape of 4b's: the staleness caveat in the header, the headline table (KILLED / OPEN HOLE / DEAD / measured-by-driving counts), a numbered section giving each OPEN HOLE its reason, a section pointing at the Task 5 dead-argument list rather than duplicating it, and the full `Site | Argument | Expression | Substitute | Verdict | Killed by` table.

Add one line to the top of `docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md`: **SUPERSEDED for `last_used.py`, `pipeline.py`, `cache_search.py` and `cli.py` by the 4c index (2026-08-23); its line numbers predate phase 4c and no longer resolve.**

- [ ] **Step 5: Commit**

```bash
git add scripts/wiring_sweep_4c.py docs/superpowers/plans/
git commit -m "test: sweep every argument phase 4c rewired"
```

---

### Task 7: The differential — what a real run does differently

**Goal:** Reduce the whole phase to a bounded, explained diff between the old tree and the new one, and prove the driver can see each of the four behaviour changes by mutating each one.

**Files:**
- Create: `scripts/differential_4c.py`

**Acceptance Criteria:**
- [ ] The driver runs `veny.cli.main()` against both trees through the harness `scripts/differential_4b.py` already uses, and prints a diff.
- [ ] It adds four layers, one per sanctioned change: a run with `VIRTUAL_ENV` set, the same run with it unset while `sys.prefix != sys.base_prefix` (the tool-install shape), a `--feeling-lucky` run whose child is killed by a signal, and a `--blank-slate -y` run.
- [ ] Every hunk in the diff is one of the four sanctioned changes plus the announce lines; anything else is a regression and stops the task.
- [ ] Five mutations are run, each moving the diff, with the measured line counts recorded in the docstring: M1 the guard reads `sys.prefix` again; M2 `active_virtualenv_dir` returns a `str`; M3 `_shell_status` is not applied to the lucky return; M4 `blank_slate` reads `args.y` again; M5 `announce=True` dropped from the three new sites. Reverted → back to the clean baseline.
- [ ] The docstring's residual-risk list carries forward the sixteen items from `scripts/differential_4b.py` plus anything this phase adds, and says **two** latent defects were live at the phase's start (defect 2 was fixed by 4a) — 4b's list said "three" and named two.

**Verify:** `pixi run python scripts/differential_4c.py` → prints the diff and its line/hunk counts; clean run reports 0 differing lines beyond the sanctioned hunks.

**Steps:**

- [ ] **Step 1: Copy 4b's driver and re-point it**

```bash
cp scripts/differential_4b.py scripts/differential_4c.py
```

Read `scripts/differential_4c.py`'s "How to run it, and against what base" section and set the base commit to `f7b11fc` (`main` before this phase). Rewrite the module docstring for this phase: what changed, why a green suite cannot see it, and what this driver adds.

- [ ] **Step 2: Retire the layers that cannot run against the new tree**

4b's driver stubs `ek.save_options_to_json` and spies on `cli.parse_arguments`; both are settled now. What changes shape in 4c is `last_used.is_virtualenv`, which the old tree has and the new one does not — any layer or probe naming it must guard with `getattr(last_used, "is_virtualenv", None)` so the file imports against both trees. This is the same class of breakage 4b hit with `parse_arguments`, one phase later.

- [ ] **Step 3: Add the four layers**

Add them after 4b's last layer, numbered on from it. Each sets its environment explicitly rather than inheriting the driver's:

- **Layer A — activated environment.** `VIRTUAL_ENV` set to a directory the layer creates, a run whose imports are missing. Report: which environment was import-checked, and the final status. Both trees should agree — this is the direction the change preserves.
- **Layer B — the tool-install shape.** `VIRTUAL_ENV` deleted from the environment, `sys.prefix` monkeypatched away from `sys.base_prefix`, same run. Report: whether `cache_search.find_match_dir_in_cache` was reached, and the final status. **This is the layer the whole phase exists for** — old tree dead-ends with status 1 and the deactivate message, new tree reaches the cache.
- **Layer C — a lucky run killed by a signal.** `--feeling-lucky` with a record in place and `run_script` returning `-9`. Report: the status `main()` returned. Old tree `-9`, new tree `137`.
- **Layer D — `--blank-slate -y`.** With the confirmation prompt replaced by a recorder. Report: whether the prompt was issued and whether the directory survived. Old tree prompts, new tree does not.

- [ ] **Step 4: Run it clean and record the diff**

Run: `pixi run python scripts/differential_4c.py`

Expected: a diff whose every hunk is one of — the deactivate-message dead end becoming a cache search (layer B), the lucky status (layer C), the prompt (layer D), and the announce lines (everywhere a launch happens). Record the exact line and hunk counts in the docstring. If a hunk appears that is none of those, stop and investigate: that is the regression this task exists to find.

- [ ] **Step 5: Mutate five ways**

For each mutation: apply it to `src/`, re-run the driver, record **both** the total line count and the number of lines differing from the clean run, then revert and confirm the clean numbers return.

```bash
# M1: the guard reads sys.prefix again
#   in last_used.active_virtualenv_dir, return Path(sys.prefix) when
#   VIRTUAL_ENV is unset instead of None
# M2: the answer is a str
#   return os.environ["VIRTUAL_ENV"] rather than ek.ensure_path(...)
# M3: the lucky status skips the arithmetic
#   `return lucky_status` instead of `return _shell_status(lucky_status)`
# M4: -y is read from the wrong dest again
#   `if not getattr(args, "y", False):` in blank_slate
# M5: the three new announce=True arguments are removed
```

The second column is the kill signal, not the first: a mutation can change what a line says without changing how many lines there are. If any mutation moves nothing, the driver cannot see that change — add the probe that makes it visible before moving on, and say in the docstring what the probe is for. 4b paid for this lesson with M2, which was a no-op until a reader probe existed.

- [ ] **Step 6: Commit**

```bash
git add scripts/differential_4c.py
git commit -m "test: add the phase 4c differential and its mutation evidence"
```

---

### Task 8: The live end-to-end check, in the shape two phases have been blind to

**Goal:** Prove, from a real shell in a real virtualenv install, that veny now reaches its cache when the user has activated nothing and still checks the environment when they have.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Modify: none (evidence only; the captured output goes into the task report and, at Task 10, into `PROGRESS.md`)

**Acceptance Criteria:**
- [ ] veny is installed into a throwaway virtualenv **outside** the pixi environment, and `python -c "import sys; print(sys.prefix != sys.base_prefix)"` inside it prints `True` — the shape where the old guard was always True.
- [ ] **Unactivated shape:** with `VIRTUAL_ENV` unset, running the venv's interpreter directly against a script with a missing import does NOT print "Please deactivate the current virtual environment", reaches the cache/venv-build path, and the script's own stdout appears. Captured verbatim.
- [ ] **Activated shape:** with `VIRTUAL_ENV` exported to that same venv, the same run DOES import-check that environment — either it runs the script there or it prints the deactivate message, and which one it does is recorded with the reason.
- [ ] Both runs' exit statuses are recorded via `echo $?`.
- [ ] Neither run uses `pixi run`. The report states the install shape explicitly, as 4a's and 4b's did.

**Verify:** the two captured shell transcripts, each with its `echo $?` line, pasted into the task report.

**Steps:**

- [ ] **Step 1: Build the throwaway environment**

```bash
cd /tmp
python -m venv /tmp/veny-live-4c
/tmp/veny-live-4c/bin/python -m pip install -q uv
/tmp/veny-live-4c/bin/python -m pip install -q /workspace
```

- [ ] **Step 2: Confirm the shape is the one that used to break**

```bash
/tmp/veny-live-4c/bin/python -c \
  "import sys; print(sys.prefix != sys.base_prefix)"
```

Expected: `True`. If it prints `False`, the environment is not a virtualenv and this whole task proves nothing — stop and rebuild it.

- [ ] **Step 3: Write a script with a missing import**

```bash
mkdir -p /tmp/veny-live-4c-work
cd /tmp/veny-live-4c-work
printf 'import yaml\nprint("live 4c ok", yaml.__name__)\n' > live.py
```

- [ ] **Step 4: The unactivated run — the one the phase exists for**

```bash
cd /tmp/veny-live-4c-work
env -u VIRTUAL_ENV /tmp/veny-live-4c/bin/python -m veny live.py
echo $?
```

Expected: no "Please deactivate the current virtual environment" line; veny builds or reuses a cached environment and `live 4c ok yaml` reaches the terminal; status 0. Capture the whole transcript. Against the pre-4c tree this run ended in the deactivate message with status 1 — say so in the report, and if you want the contrast on the record, run the same command against a `git worktree` of `f7b11fc` rather than checking out inside the working tree (see CLAUDE.md).

- [ ] **Step 5: The activated run**

```bash
cd /tmp/veny-live-4c-work
VIRTUAL_ENV=/tmp/veny-live-4c \
  /tmp/veny-live-4c/bin/python -m veny live.py
echo $?
```

Expected: veny import-checks `/tmp/veny-live-4c` itself. Whether it then runs the script or prints the deactivate message depends on whether `yaml` is installed there — record which happened and why, and do not "fix" either outcome: both are the branch working.

- [ ] **Step 6: Clean up and record**

```bash
rm -rf /tmp/veny-live-4c /tmp/veny-live-4c-work
```

Paste both transcripts and both statuses into the task report, with one sentence naming the install shape. Leave `~/veny`'s cache alone — it is not this task's to clear.

- [ ] **Step 7: Commit**

Nothing to commit unless a defect was found. If one was, fix it with its own test first, then commit that fix — and note in the message that the live check found it.

---

### Task 9: The documentation this phase can finally correct

**Goal:** Close the three documentation defects the earlier phases recorded and could not fix, and record 4c's own amendments in the design doc.

**Files:**
- Modify: `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md` (ledger item 5; a new phase-4c amendment block)
- Modify: `PROGRESS.md` (the Gotchas entry describing `check_venv_dir`'s `issubset()` self-heal)
- Modify: `scripts/differential_4c.py` (residual item 7's count, if Task 7 did not already write "two")

**Acceptance Criteria:**
- [ ] Design ledger item 5 no longer claims the `issubset()` self-heal is "Closed in phase 4 with the persistence change"; it records that manifest-based matching deleted it at `7640f1c`, before phase 3 began.
- [ ] `PROGRESS.md`'s Gotchas entry describing that check as "self-healing after that one rebuild" is corrected the same way — the behaviour has not existed for several phases.
- [ ] The design doc carries a phase-4c amendment block recording the four behaviour changes and the four user decisions from this plan's header, in the same form as the 4b block.
- [ ] `rg -n 'three latent defects' scripts/` returns nothing.

**Verify:** `rg -n 'issubset' docs/ PROGRESS.md` → every surviving mention describes it in the past tense with `7640f1c` named.

**Steps:**

- [ ] **Step 1: Correct ledger item 5**

Replace its closing sentence with: *Already gone before phase 3 began — `7640f1c` ("refactor: judge every cached venv, last-used included, by its manifest") replaced the `uninstalled_imports.issubset(...)` comparison against a loaded options file with manifest-based matching. Phase 4b deleted the file the check used to read, not the check. Recorded 2026-08-23 by phase 4c; no code change was needed.*

- [ ] **Step 2: Correct the Gotchas entry**

In `PROGRESS.md`, find the entry saying the `issubset()` check "fails once against such a file and rebuilds the venv a single time; it is self-healing after that one rebuild" (`rg -n 'self-healing' PROGRESS.md`) and mark it historical in place: keep the mechanism for the record, prefix the claim with **NO LONGER TRUE since `7640f1c`**, and name manifest-based matching as what replaced it.

- [ ] **Step 3: Record 4c's amendments in the design doc**

Add a block in the same form as the doc's `AMENDED 2026-08-21 by phase 4b` block, listing: the guard now reads `VIRTUAL_ENV` and `is_virtualenv` is deleted (with the accepted cost — an unactivated virtualenv reads as no environment); `--feeling-lucky` shares `main`'s exit-status arithmetic through `cli._shell_status`; `blank_slate` reads `args.yes`; all four `run_script` sites announce. One sentence each, naming the task that made it.

- [ ] **Step 4: Fix the stale count**

Run: `rg -n 'three latent defects' scripts/`

If `scripts/differential_4c.py` inherited the phrase from 4b, change it to **two** and name them: defect 1 (`-y` never reaching `blank_slate`) and defect 3 (`run_script(rawlog=…)` dead at three of four sites) — both of which this phase closed. Defect 2 was fixed by 4a's own Task 1, so the count was already wrong when 4a wrote it.

- [ ] **Step 5: Commit**

```bash
git add docs/ PROGRESS.md scripts/differential_4c.py
git commit -m "docs: correct the issubset ledger claim and record 4c's amendments"
```

---

### Task 10: Close the phase

**Goal:** Leave `main` with measured gates, a `PROGRESS.md` ledger entry that a cold session can resume from, and an honest statement of what phase 4c did not do.

**Files:**
- Modify: `PROGRESS.md` (Current work, deferred items)
- Modify: `docs/superpowers/plans/2026-08-23-behaviour-changes-4c.md.tasks.json` (tracker state)

**Acceptance Criteria:**
- [ ] All four gates are re-measured **in this session, on this branch**, and written into `PROGRESS.md` with their exact numbers: `pixi run test`, `pixi run lint`, `pixi run python -m ruff format --check .`, `pixi run typecheck`. Copying a number from a task report is the failure this criterion exists to prevent.
- [ ] The mypy count is compared against the 23-errors-in-6-files baseline and any movement is explained by file, not asserted.
- [ ] The ledger entry names every commit of the phase, and states for each behaviour change what a user will now see differently.
- [ ] "What 4c did NOT do" names its owner for each item: the probe venv in classification (design amendment 3) and the single-file reachability gap are still unowned; the sixteen residual risks from `scripts/differential_4b.py` carry forward into 4c's docstring; the two OPEN dead-argument rows stay open with their reasons.
- [ ] The **Next action** line says what the next session should do — and if phase 4 is complete, says that, rather than pointing at a plan that does not exist.
- [ ] The task tracker's ten entries are all `completed`.

**Verify:** `pixi run test && pixi run lint && pixi run python -m ruff format --check . ; pixi run typecheck` → the four numbers, pasted into `PROGRESS.md` verbatim.

**Steps:**

- [ ] **Step 1: Measure the gates, here, now**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
```

Record all four outputs verbatim. For mypy, also get the per-file breakdown so the comparison against 23-in-6 is by file:

```bash
pixi run typecheck 2>&1 | rg '^\S+\.py' | sed 's/:.*//' | sort | uniq -c | sort -rn
```

- [ ] **Step 2: Write the ledger entry**

In `PROGRESS.md`'s **Current work**, add the 4c block above 4b's, in the same shape: the measured gates; the commit list with what each did; the four behaviour changes stated as user-visible differences; the differential's clean and mutated numbers; the live check with its install shape named; what 4c did not do with owners; and the deferred items it opened or closed. Move anything that becomes stale rather than leaving a copy behind — migrate, don't duplicate.

- [ ] **Step 3: Update the Next action line**

Rewrite it to say what the next session does first. Phase 4 was scoped as 4a + 4b + 4c; if nothing in the design doc's phase-4 section remains, say **phase 4 is complete** and name the unowned items (design amendment 3's probe venv, the single-file reachability gap) as the candidates for whatever comes next — do not invent a phase 5.

- [ ] **Step 4: Sync the tracker**

Mark all ten tasks `completed` in `docs/superpowers/plans/2026-08-23-behaviour-changes-4c.md.tasks.json` and in the native task list.

- [ ] **Step 5: Commit**

```bash
git add PROGRESS.md docs/superpowers/plans/
git commit -m "docs: close phase 4c with measured gates and its ledger"
```

---

## After the plan: merging

This phase is the first of the program that is not behaviour-preserving, so the whole-branch review matters more here than usual — per-task review structurally cannot see a phase-wide claim (4b's review caught a stale layer-graph comment exactly that way). Run it before merging, and treat its findings as this phase's, not the next one's. Then merge with `--no-ff` and record the merge commit in `PROGRESS.md`, as 4a and 4b did.
