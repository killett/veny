# Phase 4b: the LastUsed record — veny's own persistence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `ek.save_options_to_json` / `ek.load_options_from_json` with a three-field `LastUsed` record veny writes and reads itself, and delete everything that existed only to feed emmykit's reader and writer — `run_options.py`, the `Options` class, the `cli.Options` re-export, `pathlibcutoff` and both its readers, and `json_types.py`.

**Architecture:** `state.LastUsed` is a frozen value carrying `venv_dir`, `venv_python` and `timestamp`. `last_used.py` gains `record_path`, `save` and `load`, all plain `json.dumps`/`json.loads` with `str(path)` on write and `Path(...)` on read — one fixed file per script, `.{script}-{my_name}-last-used.json`, overwritten each run. `pipeline.run` writes that record instead of copying five fields onto an `Options`; `feeling_lucky` and the cache search's last-used pass read it. With no `Options` reaching disk, the class has no remaining reason to exist, and neither does the JSON type registry that only ever served it.

**Tech Stack:** Python 3.12+, `dataclasses` (frozen), stdlib `json`, pytest, mypy, ruff, pixi.

**Global Constraints:**
- **Behaviour-preserving except where this plan names a change.** Three changes are named and sanctioned, all in Task 1–3: the record's filename, the record's contents, and the one fallback cache scan a script gets when its only record is in the old format. Any other visible difference is a bug, not a deviation.
- **Old records are ignored, never migrated, never deleted.** No code in this phase reads a whole-`Options` JSON, and no code unlinks one. `--blank-slate` keeps removing both shapes, because its filter is a name test, not a format test.
- **No module may import the module above it.** `tests/test_layering.py` enforces the stack and must be updated in the same commit as each deletion — `run_options` leaves the `state` layer (Task 6), `json_types` leaves the index layer and its `SANCTIONED_EXCEPTIONS` entry (Task 7). `last_used` sits above `state`, so `last_used` importing `state` is already legal; do not move either module.
- **`pipeline.py` calls its collaborators through the module object** (`last_used.save(...)`, never `from .last_used import save`). Keep it that way — it is what lets a test replace one boundary.
- **Frozen means frozen.** `LastUsed` is `@dataclass(frozen=True)`, like its four siblings in `state.py`.
- **Every count in this plan is re-measured, not trusted.** The reference counts below were taken on 2026-08-21 at `240767b`. Re-run the commands in Task 5 before repointing anything.
- **`pixi run` sets `PYTHONPATH=src`.** Any tool that runs the suite outside `pixi run` must set it, or `tests/test_import_guard.py` fails under every mutation and reports spurious kills. This cost phase 4a a whole sweep; do not pay it again.
- **Gates, every task:** `pixi run test`, `pixi run lint` and `pixi run python -m ruff format --check .` must be green before the commit. `pixi run typecheck` must not exceed the **23 errors in 6 files** baseline measured on `main` at `240767b`; re-measure, do not copy. Deleting `Options` should lower it — if it rises, the task is not done.

**User decisions (already made):**
- **2026-08-21 — old records are ignored, not migrated.** A script whose only last-used record is an earlier veny's whole-`Options` dump misses the pointer once and falls back to the cache scan; the next save writes the new format. Old files stay on disk. This is what lets the reader be plain `json.loads` with no tagged-payload decoding.
- **2026-08-21 — one fixed file per script, not one per run.** `.{script}-{my_name}-last-used.json`, overwritten. The glob, the `last-used-on-(\d{8}-\d{6})` regex and the newest-wins timestamp sort all go, and veny stops leaving one JSON per run in the user's script directory.
- **2026-08-21 — `json_types.py` is deleted**, with its module-scope call and its tests, and the emmykit version guard that protected it is kept in a repointed form (see the deviation note in Task 7 — the user's ruling said "probe a name veny still calls", and that turns out to be unable to detect a pre-0.4.0 emmykit; the guard becomes a `__version__` comparison instead, which keeps the ruling's intent).
- **2026-08-21 — `find_match_dir_in_cache` stops mutating the `argparse.Namespace` in this phase.** Its `last_used`/`latest` writes were writes only because they reached disk through `save_options_to_json`.
- **2026-08-21 (carried from 4a) — phase 4 is three plans.** This is **4b**. The in-virtualenv guard, `--feeling-lucky`'s missing signal normalization, latent defects 1 and 3 and the residual dead arguments are **4c's**. Do not touch them here.

---

## Context an executing engineer needs

**Read first:** `PROGRESS.md` — all of it, including the deferred items, gotchas and cross-cutting decisions, which live nowhere else — and `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md` § "Persistence", including the `AMENDED 2026-08-21 by phase 4b` block that records this plan's five rulings.

**Where things stand.** Phase 4a merged to `main` at `cf2ded4`; `main` is at `240767b`. `src/veny/` is 7,417 lines across 23 modules. `Options` is down to fourteen fields in four documented groups, all of them accounted for in `run_options.py`'s module docstring. Five modules below `pipeline` never heard of `Options`, and `pipeline` itself reads nothing off it — it only copies five fields onto it at the save and hands it to emmykit's reader as a template.

**What is actually coupled, measured at `240767b`.** Only four call sites touch emmykit's persistence:

| Site | What it does |
|---|---|
| `src/veny/pipeline.py:986-991` | Copies `python_script`, `script_dir`, `timestamp`, `venv_dir`, `venv_python` onto the `Options`, then `ek.save_options_to_json(options)`. |
| `src/veny/last_used.py:69` | `ek.load_options_from_json(options, script_dir / json_files[0])` — the reader, after a glob + regex + newest-wins sort. |
| `src/veny/pipeline.py:427` (`feeling_lucky`) | Reads back a `venv_python` through `last_used.load_last_used_venv_python`. |
| `src/veny/pipeline.py:565` (`_load_last_used`) → `cache_search.find_match_dir_in_cache`'s injected callable | Reads back a `venv_dir` through `last_used.load_last_used_options`. |

Everything else on `Options` is either construction input for the `Settings` `cli.main` already builds (`home`, `cwd`, `my_name`, `log_mode`, `rawlog`), or an object the pipeline rebuilds for itself anyway (`stdlib`, `aliases` — `run` builds its own; the copies on `Options` survive only because `save_options_to_json` serializes the whole `__dict__`).

**The old on-disk shape, for reference — you are not writing a reader for it.** `ek.save_options_to_json` dumps `options.__dict__` through `to_jsonable(..., roundtrip=True)`, so a `Path` lands as `{"__type__": "path", "value": "/a/b"}`, into a file named `.{script}-{my_name}-last-used-on-{YYYYmmdd-HHMMSS}.json`. That is the only thing `json_types.py` ever served: `alias_index` writes its own cache with plain `json.dumps`, and no other `to_jsonable` call exists under `src/`.

**Gotcha: the differential, not the suite, catches this phase's real defect.** Twice running. Phase 4a's Task 6 moved `venv_dir` and `venv_python` off `Options`, 439 tests stayed green, and the saved record silently stopped containing a venv at all — because nothing *reads* those fields in-process, only the writer's `__dict__` sweep did. The same hole is open here: a `save` that writes the wrong keys, or a `load` that returns strings instead of `Path`s, can leave the whole suite green. Task 1's round-trip tests and Task 9's differential exist for exactly that, and `test_wiring_4a::test_the_saved_record_carries_the_venv_the_run_actually_used` is the in-process pin that must be repointed rather than deleted.

**Gotcha: a `str` is not a `Path`.** `load_last_used_venv_python` compares the recovered value against a real `Path` and hands it to `ek.safe_is_file`. If `load` returns `"/a/b"` where the caller expects `Path("/a/b")`, equality assertions fail loudly but *predicate* checks may not — write `Path(...)` in the reader, and assert `isinstance` in the test, not just equality.

**Gotcha: `pixi run` hides the in-virtualenv branch.** Under `pixi run`, `sys.prefix == sys.base_prefix`, so `last_used.is_virtualenv()` is False and the middle branch of `pipeline.run` never executes. That branch is 4c's, but it means a `pixi run` live check cannot exercise it — do not conclude from a green live run that the branch is fine.

**Gotcha: `analysis/custom_modules.PATHLIB_CUTOFF` is a *pickle* cutoff, not the options one.** It guards the custom-modules pickle cache, and both arms of the comparison it selects call `ek.ensure_path`. Deleting the comparison must keep the coercion (Task 4).

---

## File Structure

| File | Change | Responsibility after this plan |
|---|---|---|
| `src/veny/state.py` | Modify | Adds `LastUsed` alongside `Target`, `Requirements` and `VenvHandle`. The design's state-model listing puts it in `settings.py`; it goes here with its siblings (design amendment, recorded 2026-08-21). |
| `src/veny/last_used.py` | Modify heavily | Owns the record's filename, format, read and write. Loses `load_last_used_options` and `load_last_used_venv_python`; gains `record_path`, `save`, `load` and `load_venv_python`. Keeps `is_virtualenv` and `active_virtualenv_dir` untouched (4c's). |
| `src/veny/pipeline.py` | Modify | Writes a `LastUsed` at the end of a successful run; reads one in `feeling_lucky` and `_load_last_used`. Loses the five copy-backs and every `run_options` reference. |
| `src/veny/cache_search.py` | Modify | `load_last_used` is typed `Callable[[], state.LastUsed | None]` and read directly; the `getattr(..., "venv_dir", None)` defence and the two `args` writes go. |
| `src/veny/cli.py` | Modify | Builds the run from locals; no `Options`, no re-export, no `json_types` call. `parse_arguments()` returns a `Namespace`. |
| `src/veny/run_options.py` | **Delete** | — |
| `src/veny/json_types.py` | **Delete** | — |
| `src/veny/analysis/custom_modules.py` | Modify | Loses `PATHLIB_CUTOFF` and the comparison; keeps the `ek.ensure_path` coercion. |
| `tests/test_last_used.py` | Rewrite | The new record: round-trip, filename, overwrite, and every degraded input. |
| `tests/test_layering.py` | Modify | `run_options` and `json_types` leave the stack; `json_types`' `SANCTIONED_EXCEPTIONS` entry goes. |
| `tests/test_options_surface.py`, `tests/test_json_types.py` | **Delete** | Both exist only to characterize things this plan removes. |
| `tests/test_cache_search.py`, `tests/test_classify.py`, `tests/test_cli_entry_point.py`, `tests/test_import_discovery.py`, `tests/test_manifest_writing.py`, `tests/test_split_imports.py`, `tests/test_state_values.py`, `tests/test_uv_backend.py`, `tests/test_venv_naming.py`, `tests/test_wiring_4a.py` | Modify | Repointed off `Options` onto the real objects they were using it to carry. |
| `docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md` | Create | Task 8's argument-by-argument sweep of every changed call site. |
| `scripts/differential_4b.py` | Create | Task 9's before/after comparison, in the shape of `scripts/differential_4a.py`. |

---

### Task 1: The record — `LastUsed`, and `last_used`'s own read and write

**Goal:** veny can write a three-field record for a script and read it back, with every degraded input answering `None` instead of raising.

**Files:**
- Modify: `src/veny/state.py` (append after `VenvHandle`)
- Modify: `src/veny/last_used.py`
- Test: `tests/test_last_used.py`

**Acceptance Criteria:**
- [ ] `state.LastUsed` is a frozen dataclass with `venv_dir: Path`, `venv_python: Path`, `timestamp: str`.
- [ ] `last_used.record_path(script_dir, python_script, my_name)` returns `script_dir / f".{python_script.name}-{my_name}-last-used.json"`.
- [ ] `last_used.save(...)` writes exactly those three keys as JSON strings and returns the path written.
- [ ] `last_used.load(...)` returns a `LastUsed` whose two path fields are `Path` instances, or `None` for: no file, unreadable file, invalid JSON, a JSON value that is not an object, or a missing/empty `venv_dir` or `venv_python`.
- [ ] `last_used.load_venv_python(...)` returns the recorded interpreter only when `ek.safe_is_file` says it still exists, and `None` with a warning when it does not.
- [ ] A record written by an earlier veny (whole-`Options` dump, timestamped filename) is not read by anything — `load` returns `None` in a directory containing only that file.
- [ ] The old `load_last_used_options` and `load_last_used_venv_python` still exist and still pass their tests at the end of this task; Task 3 deletes them with their callers.

**Verify:** `pixi run test tests/test_last_used.py -v` → all pass, including the eight new tests named in the steps.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_last_used.py`. Each names the bug it catches, per the `test-design` skill.

```python
# --- The new record. Behaviour under test, and the bug each test would catch.

def test_a_saved_record_is_read_back_as_the_same_paths(tmp_path):
    # Bug caught: a reader that hands back the JSON strings instead of Paths.
    # Every consumer compares against a Path or feeds ek.safe_is_file, and a
    # str fails both silently in the second case.
    script = tmp_path / "thing.py"
    script.write_text("import yaml\n")
    record = state.LastUsed(
        venv_dir=tmp_path / "myenv-1",
        venv_python=tmp_path / "myenv-1" / "bin" / "python",
        timestamp="20260202-020202",
    )

    last_used.save(record, script_dir=tmp_path, python_script=script, my_name="veny")
    loaded = last_used.load(
        script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
    )

    assert loaded == record
    assert isinstance(loaded.venv_dir, Path)
    assert isinstance(loaded.venv_python, Path)


def test_the_record_is_named_for_the_script_and_the_program(tmp_path):
    # Bug caught: a filename that omits the script's name, which would make
    # two scripts in one directory share -- and overwrite -- one record.
    script = tmp_path / "thing.py"

    path = last_used.record_path(tmp_path, script, "veny")

    assert path == tmp_path / ".thing.py-veny-last-used.json"


def test_a_second_save_overwrites_rather_than_accumulating(tmp_path):
    # Bug caught: reinstating the per-run timestamped filename, which is what
    # littered the user's script directory with one JSON per run.
    script = tmp_path / "thing.py"
    first = state.LastUsed(tmp_path / "old", tmp_path / "old" / "python", "20260101-010101")
    second = state.LastUsed(tmp_path / "new", tmp_path / "new" / "python", "20260202-020202")

    last_used.save(first, script_dir=tmp_path, python_script=script, my_name="veny")
    last_used.save(second, script_dir=tmp_path, python_script=script, my_name="veny")

    assert [p.name for p in tmp_path.glob(".thing.py-veny*")] == [
        ".thing.py-veny-last-used.json"
    ]
    loaded = last_used.load(
        script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
    )
    assert loaded.venv_dir == tmp_path / "new"


def test_a_missing_record_is_none_and_not_an_error(tmp_path):
    # Bug caught: letting FileNotFoundError out of the reader, which reaches
    # main() as a traceback on every first run of every script.
    assert (
        last_used.load(
            script_dir=tmp_path,
            python_script=tmp_path / "thing.py",
            my_name="veny",
            rawlog=True,
        )
        is None
    )


def test_a_record_written_by_an_earlier_veny_is_ignored(tmp_path):
    # Bug caught: a reader that globs the directory instead of naming one
    # file would pick up the old whole-Options dumps, whose tagged payload
    # this phase deliberately stopped being able to decode. User ruling
    # 2026-08-21: ignore them, do not migrate them.
    script = tmp_path / "thing.py"
    (tmp_path / ".thing.py-veny-last-used-on-20260101-010101.json").write_text(
        json.dumps(
            {
                "venv_dir": {"__type__": "path", "value": str(tmp_path / "old")},
                "venv_python": {"__type__": "path", "value": str(tmp_path / "old" / "python")},
                "pathlibcutoff": "20250810-224900",
            }
        ),
        encoding="utf-8",
    )

    assert (
        last_used.load(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
        )
        is None
    )


@pytest.mark.parametrize(
    "text",
    [
        "{not json",                                    # invalid JSON
        "[]",                                           # valid JSON, wrong shape
        json.dumps({"venv_dir": "/a"}),                 # venv_python missing
        json.dumps({"venv_dir": "", "venv_python": ""}),  # present but empty
    ],
    ids=["invalid", "not-an-object", "missing-key", "empty-values"],
)
def test_a_damaged_record_is_none_and_not_a_crash(tmp_path, text):
    # Bug caught: JSONDecodeError, TypeError or KeyError escaping into main --
    # or, worse, a LastUsed carrying Path("") that every later check treats as
    # a real directory.
    script = tmp_path / "thing.py"
    last_used.record_path(tmp_path, script, "veny").write_text(text, encoding="utf-8")

    assert (
        last_used.load(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
        )
        is None
    )


def test_load_venv_python_returns_the_recorded_interpreter(tmp_path):
    # Bug caught: dropping the existence check, which would hand
    # --feeling-lucky a deleted interpreter and turn a clean fallback into a
    # FileNotFoundError from subprocess.
    script = tmp_path / "thing.py"
    interpreter = tmp_path / "myenv-1" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("#!/bin/sh\n")
    last_used.save(
        state.LastUsed(interpreter.parent.parent, interpreter, "20260202-020202"),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )

    assert (
        last_used.load_venv_python(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
        )
        == interpreter
    )


def test_load_venv_python_is_none_when_the_interpreter_is_gone(tmp_path, caplog):
    # Bug caught: returning a Path to a deleted venv, which is the whole
    # reason the old reader called ek.safe_is_file.
    script = tmp_path / "thing.py"
    gone = tmp_path / "deleted-env" / "bin" / "python"
    last_used.save(
        state.LastUsed(gone.parent.parent, gone, "20260202-020202"),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )

    with caplog.at_level(logging.WARNING):
        result = last_used.load_venv_python(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=False
        )

    assert result is None
    assert "no longer valid" in caplog.text
```

Add `import json` and `from veny import state` to the test module's imports; `logging`, `pytest` and `Path` are already imported there.

- [ ] **Step 2: Run them and confirm they fail**

Run: `pixi run test tests/test_last_used.py -k "record or load_venv_python or damaged or earlier_veny" -v`
Expected: FAIL — `AttributeError: module 'veny.last_used' has no attribute 'record_path'` (and `state` has no `LastUsed`).

- [ ] **Step 3: Add the value**

In `src/veny/state.py`, after `VenvHandle`:

```python
@dataclass(frozen=True)
class LastUsed:
    """The one thing veny remembers between runs.

    Frozen, like every other product in this module: it is written once at
    the end of a successful run and only read on the next one.

    Phase 4b wrote this record itself rather than persisting an ek.Options,
    which is what coupled veny's state object to emmykit's reader and writer.
    The design's state-model listing puts LastUsed in settings.py; it lives
    here with its siblings instead, because settings.py holds the run's
    invariants and this is a product.

    Attributes:
        venv_dir:    The environment the last successful run used.
        venv_python: That environment's interpreter -- recorded rather than
                     derived, so a reader need not know how a venv is laid
                     out on this platform.
        timestamp:   The run's stamp, in the same "YYYYmmdd-HHMMSS" format
                     Target carries. Diagnostic: nothing selects on it now
                     that there is one record per script rather than one per
                     run.
    """

    venv_dir: Path
    venv_python: Path
    timestamp: str
```

- [ ] **Step 4: Add the read and write**

In `src/veny/last_used.py`, above `load_last_used_options` (which stays until Task 3). Add `import json` and `from . import state` to the module's imports.

```python
RECORD_SUFFIX: Final[str] = "-last-used.json"


def record_path(script_dir: Path, python_script: Path, my_name: str) -> Path:
    """Where this script's last-used record lives.

    One fixed file per script, not one per run: veny used to leave a
    timestamped JSON in the user's directory on every successful run and then
    glob, regex and sort them to find the newest. The name still starts with
    a dot and still contains "-{my_name}-", which is what --blank-slate's
    filter matches on.

    Args:
        script_dir:    The directory the script lives in.
        python_script: The script the record belongs to.
        my_name:       The program's own name, as it appears in the filename.

    Returns:
        The record's path. Says nothing about whether it exists.
    """
    return script_dir / f".{python_script.name}-{my_name}{RECORD_SUFFIX}"


def save(
    record: state.LastUsed,
    *,
    script_dir: Path,
    python_script: Path,
    my_name: str,
) -> Path:
    """Write this run's record, replacing any earlier one for the same script.

    Args:
        record:        What to remember: the environment and its interpreter.
        script_dir:    The directory the script lives in.
        python_script: The script the record belongs to.
        my_name:       The program's own name, for the filename.

    Returns:
        The path written.
    """
    path = record_path(script_dir, python_script, my_name)
    payload = {
        "venv_dir": os.fspath(record.venv_dir),
        "venv_python": os.fspath(record.venv_python),
        "timestamp": record.timestamp,
    }
    path.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")
    return path


def load(
    *,
    script_dir: Path,
    python_script: Path,
    my_name: str,
    rawlog: bool,
) -> state.LastUsed | None:
    """Read this script's last-used record, or None if there is not a usable one.

    Every degraded input -- absent, unreadable, not JSON, not an object,
    missing either path -- is "no record", never an exception: this runs on
    the first line of a user's ordinary run, and the cost of no record is one
    cache scan.

    Records written before phase 4b are a different format under a different
    filename and are ignored by construction: this reads one named file and
    never globs. (User ruling, 2026-08-21.)

    Args:
        script_dir:    The directory the script lives in.
        python_script: The script whose record is wanted.
        my_name:       The program's own name, for the filename.
        rawlog:        True suppresses veny's own commentary.

    Returns:
        The record, or None.
    """
    path = record_path(script_dir, python_script, my_name)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if not rawlog:
            logging.info("No usable last-used record for %s.", os.fspath(python_script))
        return None
    if not isinstance(payload, dict):
        if not rawlog:
            logging.info("Last-used record %s is not an object.", os.fspath(path))
        return None
    venv_dir = payload.get("venv_dir")
    venv_python = payload.get("venv_python")
    if not isinstance(venv_dir, str) or not isinstance(venv_python, str):
        if not rawlog:
            logging.info("Last-used record %s names no environment.", os.fspath(path))
        return None
    if not venv_dir or not venv_python:
        if not rawlog:
            logging.info("Last-used record %s names an empty path.", os.fspath(path))
        return None
    timestamp = payload.get("timestamp")
    return state.LastUsed(
        venv_dir=ek.ensure_path(venv_dir),
        venv_python=ek.ensure_path(venv_python),
        timestamp=timestamp if isinstance(timestamp, str) else "",
    )


def load_venv_python(
    *,
    script_dir: Path,
    python_script: Path,
    my_name: str,
    rawlog: bool,
) -> Path | None:
    """The interpreter the last successful run used, if it still exists.

    Args:
        script_dir:    The directory the script lives in.
        python_script: The script whose record is wanted.
        my_name:       The program's own name, for the filename.
        rawlog:        True suppresses veny's own commentary.

    Returns:
        The recorded interpreter, or None when there is no record or the
        interpreter it names is gone.
    """
    record = load(
        script_dir=script_dir,
        python_script=python_script,
        my_name=my_name,
        rawlog=rawlog,
    )
    if record is None:
        if not rawlog:
            logging.info("No last used record found, so no venv_python to return.")
        return None
    if not ek.safe_is_file(record.venv_python):
        if not rawlog:
            logging.warning(
                "Last used venv_python %s is no longer valid.",
                os.fspath(record.venv_python),
            )
        return None
    if not rawlog:
        logging.info(
            "Last used venv_python found: %s", os.fspath(record.venv_python)
        )
    return record.venv_python
```

Add `Final` to the module's `typing` import.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `pixi run test tests/test_last_used.py -v`
Expected: PASS, new tests and the existing ones for the old readers alike.

- [ ] **Step 6: Gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --all-files
git add src/veny/state.py src/veny/last_used.py tests/test_last_used.py
git commit -m "feat: give veny its own last-used record, read and written here"
```

---

### Task 2: The writer — `pipeline.run` records the venv it used

**Goal:** A successful run writes a `LastUsed` through `last_used.save` instead of copying five fields onto an `Options` and calling `ek.save_options_to_json`.

**Files:**
- Modify: `src/veny/pipeline.py:983-991` (the copy-backs and the save)
- Test: `tests/test_wiring_4a.py` (repoint `test_the_saved_record_carries_the_venv_the_run_actually_used`)
- Test: `tests/test_last_used.py` (add the `--blank-slate` pin)

**Acceptance Criteria:**
- [ ] `pipeline.run` calls `last_used.save(...)` with a `LastUsed` built from `handle` and `target`, through the module object.
- [ ] No assignment to `options.*` remains anywhere in `pipeline.py`.
- [ ] `ek.save_options_to_json` appears nowhere under `src/`.
- [ ] The record is written **after** the `failed-` rename, so it names the folder that exists on disk — the rename rebinds `handle`, and recording the pre-rename path would point the next run at a directory that is gone.
- [ ] `--blank-slate` still deletes the new record.

**Verify:** `pixi run test tests/test_wiring_4a.py tests/test_last_used.py -v` → all pass; `rg -n 'save_options_to_json' src/` → no matches.

**Steps:**

- [ ] **Step 1: Repoint the in-process pin, and add the blank-slate pin**

In `tests/test_wiring_4a.py`, `test_the_saved_record_carries_the_venv_the_run_actually_used` currently asserts on the Options handed to `ek.save_options_to_json`. Rewrite its assertion to read the record off disk — this is the test that caught phase 4a's one real regression, so it must keep asserting the *venv the run used*, not merely that a file appeared:

```python
    record = last_used.load(
        script_dir=target.script_dir,
        python_script=target.python_script,
        my_name="veny",
        rawlog=True,
    )
    # Identity of the environment, not just its existence: the 4a regression
    # this test was written for wrote a record with no venv in it at all.
    assert record is not None
    assert record.venv_python == handle.venv_python
    assert record.venv_dir == handle.venv_dir
```

In `tests/test_last_used.py`:

```python
def test_blank_slate_deletes_the_new_last_used_record(tmp_path, monkeypatch):
    # Bug caught: a record filename that no longer matches blank_slate's
    # ".{...}-veny-...json" test, which would leave veny's own dotfiles behind
    # after the user asked for a clean slate.
    script = tmp_path / "thing.py"
    record = last_used.save(
        state.LastUsed(tmp_path / "env", tmp_path / "env" / "python", "20260202-020202"),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )
    assert record.exists()
    settings_for_run = a_settings(my_dir=tmp_path / "veny-home", cwd=tmp_path)

    pipeline.blank_slate(settings_for_run, argparse.Namespace(y=True))

    assert not record.exists()
```

`a_settings` is the existing helper in `tests/test_state_values.py`; import it the way `tests/test_last_used.py` already imports `a_target`. Add `import argparse` there.

- [ ] **Step 2: Run them and confirm they fail**

Run: `pixi run test tests/test_wiring_4a.py::test_the_saved_record_carries_the_venv_the_run_actually_used tests/test_last_used.py::test_blank_slate_deletes_the_new_last_used_record -v`
Expected: FAIL — the wiring test fails because no record file is written yet (`record is None`); the blank-slate test passes only if the filename already matches, so treat a pass here as evidence for the filename, not for the writer.

- [ ] **Step 3: Replace the copy-backs with the record**

In `src/veny/pipeline.py`, replace lines 983-991 (the comment block, the five assignments and the `ek.save_options_to_json(options)` call) with:

```python
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

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `pixi run test tests/test_wiring_4a.py tests/test_last_used.py -v`
Expected: PASS.

- [ ] **Step 5: Gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --all-files
git add src/veny/pipeline.py tests/test_wiring_4a.py tests/test_last_used.py
git commit -m "refactor: write veny's own last-used record at the end of a run"
```

---

### Task 3: The readers — `--feeling-lucky`, the cache search, and the end of `ek.Options`

**Goal:** Both readers take a `LastUsed`; `last_used.load_last_used_options` and `load_last_used_venv_python` are deleted; `find_match_dir_in_cache` stops mutating the `argparse.Namespace`.

**Files:**
- Modify: `src/veny/last_used.py` (delete the two old readers)
- Modify: `src/veny/pipeline.py:397-449` (`feeling_lucky`), `:538-571` (`_load_last_used`), `:905-913` (the injected lambda)
- Modify: `src/veny/cache_search.py:557-628`
- Modify: `src/veny/cli.py:198-205` (`feeling_lucky`'s call site)
- Test: `tests/test_last_used.py`, `tests/test_cache_search.py`, `tests/test_cli_entry_point.py`

**Acceptance Criteria:**
- [ ] `feeling_lucky` takes no `options` and no `pathlibcutoff`; it takes `my_name` and calls `last_used.load_venv_python`.
- [ ] `_load_last_used` returns `state.LastUsed | None` and takes no `options`.
- [ ] `find_match_dir_in_cache`'s `load_last_used` parameter is `Callable[[], state.LastUsed | None]`, and the body reads `record.venv_dir` directly — the `getattr(options_last_used, "venv_dir", None)` defence is gone with the base class that made it necessary.
- [ ] `find_match_dir_in_cache` performs **no** attribute assignment on `args`. The default-to-last-used decision and the fall-through to latest are locals.
- [ ] Selection behaviour is unchanged: no flags → try the last-used pointer, then fall through to latest; `--latest` or `--smallest` → skip the pointer entirely; a pointer that fails `check_venv_dir` → fall through to latest.
- [ ] `ek.Options` appears nowhere under `src/`.

**Verify:** `pixi run test tests/test_cache_search.py tests/test_last_used.py tests/test_cli_entry_point.py -v` → all pass; `rg -n 'ek\.Options|load_last_used_options|load_last_used_venv_python' src/` → no matches.

**Steps:**

- [ ] **Step 1: Write the failing tests**

In `tests/test_cache_search.py`:

```python
def test_the_last_used_pointer_selects_the_recorded_venv(tmp_path):
    # Bug caught: reading the pointer off the wrong field, or dropping the
    # last-used pass entirely -- both leave the run rebuilding an environment
    # it already had, which is invisible to a test that only asserts "some
    # venv was chosen".
    ...  # build one satisfying venv folder + manifest with the existing helpers
    record = state.LastUsed(folder, folder / "bin" / "python", "20260202-020202")

    chosen = cache_search.find_match_dir_in_cache(
        argparse.Namespace(),
        ...,
        load_last_used=lambda: record,
    )

    assert chosen == folder


def test_a_stale_pointer_falls_through_to_the_latest_match(tmp_path):
    # Bug caught: returning None (rebuild) instead of falling through when the
    # recorded venv no longer satisfies the run -- the behaviour the old
    # `args.latest = True` write implemented.
    record = state.LastUsed(tmp_path / "gone", tmp_path / "gone" / "python", "20260101-010101")

    chosen = cache_search.find_match_dir_in_cache(
        argparse.Namespace(), ..., load_last_used=lambda: record
    )

    assert chosen == newest_satisfying_folder


def test_the_cache_search_does_not_write_to_the_command_line(tmp_path):
    # Bug caught: leaving the in-place flag writes in place. They were only
    # ever writes because they reached disk through save_options_to_json;
    # with that gone, a mutated Namespace is a shared-state surprise for
    # every later reader of args.
    args = argparse.Namespace(latest=False, oldest=False, last_used=False, smallest=False)
    before = vars(args).copy()

    cache_search.find_match_dir_in_cache(args, ..., load_last_used=lambda: None)

    assert vars(args) == before
```

Fill the `...` from the existing fixtures in that file (`an_options` → a plain `StdlibIndex`, `a_reqs`, `write_manifest`); the file already builds satisfying and non-satisfying folders for its other tests.

In `tests/test_last_used.py`, repoint the `--feeling-lucky` tests onto the new record (`_write_record` is deleted with the old reader; use `last_used.save`).

- [ ] **Step 2: Run them and confirm they fail**

Run: `pixi run test tests/test_cache_search.py -k "pointer or command_line" -v`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'venv_dir'` from the `getattr` defence returning None, and the mutation test failing on `last_used`/`latest` having been written.

- [ ] **Step 3: Rewrite the readers**

`src/veny/last_used.py`: delete `load_last_used_options` and `load_last_used_venv_python` entirely, plus the now-unused `datetime as dt`, `re` and `cast` imports and the `typing` import if nothing else needs it.

`src/veny/pipeline.py` — `feeling_lucky`:

```python
def feeling_lucky(
    args: argparse.Namespace,
    target: state.Target | None,
    *,
    my_name: str,
    rawlog: bool,
) -> int | None:
```

with the body's reader call becoming:

```python
    last_used_venv_python = last_used.load_venv_python(
        script_dir=target.script_dir,
        python_script=target.python_script,
        my_name=my_name,
        rawlog=rawlog,
    )
```

and the `options` and `pathlibcutoff` entries dropped from its Args docstring.

`_load_last_used`:

```python
def _load_last_used(
    target: state.Target,
    *,
    my_name: str,
    rawlog: bool,
) -> state.LastUsed | None:
    """Load the previous run's record, for the cache search's last-used pass.

    find_match_dir_in_cache takes this as an injected callable rather than
    reaching for last_used itself, so nothing below pipeline has to know
    where the record lives.

    Args:
        target:  The run's Target; supplies script_dir and python_script.
        my_name: The program's own name, for the record's filename.
        rawlog:  True suppresses veny's own commentary.

    Returns:
        The previous run's record, or None when there is no usable one.
    """
    return last_used.load(
        script_dir=target.script_dir,
        python_script=target.python_script,
        my_name=my_name,
        rawlog=rawlog,
    )
```

and its call site inside `run`:

```python
                load_last_used=lambda: _load_last_used(
                    target, my_name=settings.my_name, rawlog=settings.rawlog
                ),
```

`src/veny/cli.py`:

```python
        lucky_status = pipeline.feeling_lucky(
            parsed_args,
            target,
            my_name=my_name,
            rawlog=rawlog,
        )
```

(`parsed_args`, `my_name` and `rawlog` are `options.args`, `options.my_name` and `options.rawlog` until Task 6 turns them into locals — keep reading them off `options` here and let Task 6 do the rename in one place.)

- [ ] **Step 4: Rewrite the cache search's last-used pass**

In `src/veny/cache_search.py`, retype the parameter to `Callable[[], state.LastUsed | None]`, update its docstring line, and replace the flag-writing block:

```python
    wanted = wanted_packages(uninstalled, extra_requirements)
    explicit = (
        getattr(args, "latest", False)
        or getattr(args, "oldest", False)
        or getattr(args, "last_used", False)
        or getattr(args, "smallest", False)
    )
    # No flag at all means "the one you used last time" -- a local now, not a
    # write onto args. It was a write only because args was serialized into
    # the options JSON, which veny no longer keeps.
    try_last_used = not explicit or getattr(args, "last_used", False)
    prefer_latest = getattr(args, "latest", False)
    if (
        try_last_used
        and not prefer_latest
        and not getattr(args, "smallest", False)
    ):
        record = load_last_used()
        if record is not None and check_venv_dir(
            record.venv_dir,
            wanted=wanted,
            tag=tag,
            uninstalled=uninstalled,
            source_names=source_names,
            rawlog=rawlog,
        ):
            return ek.ensure_path(record.venv_dir)
        if not rawlog:
            logging.info("Trying to load the latest matching venv now.")
        # If that didn't work, take the latest -- the same fall-through the
        # `args.latest = True` write used to encode.
        prefer_latest = True
```

Then replace every later `getattr(args, "latest", False)` in this function with `prefer_latest`, and every later `getattr(args, "last_used", False)` with `try_last_used and not prefer_latest`. **Walk the whole function** — there are further reads of both flags in the selection block below; the `--oldest` and `--smallest` reads are untouched.

Also update the `args` line in the docstring's Args block: it is read, not written, now.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `pixi run test tests/test_cache_search.py tests/test_last_used.py tests/test_cli_entry_point.py -v`
Expected: PASS. Then the whole suite: `pixi run test`.

- [ ] **Step 6: Gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --all-files
git add src/veny tests/
git commit -m "refactor: read the last-used record instead of an emmykit Options"
```

---

### Task 4: The pickle cutoff

**Goal:** `analysis/custom_modules.PATHLIB_CUTOFF` and its comparison are deleted; the path coercion it selected between stays.

**Files:**
- Modify: `src/veny/analysis/custom_modules.py:18`, `:169-187`
- Test: `tests/test_import_discovery.py`

**Acceptance Criteria:**
- [ ] A pickle written with `str` paths loads as `Path` values, whatever its filename's timestamp.
- [ ] `PATHLIB_CUTOFF` appears nowhere in the repository.
- [ ] The log line the old branch emitted ("...Converting all paths to pathlib.Path objects.") is gone with it; nothing else in the function's output changes.

**Verify:** `pixi run test tests/test_import_discovery.py -v` → all pass; `rg -ni 'pathlib_?cutoff' .` → no matches.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_a_pickle_of_string_paths_loads_as_paths(tmp_path):
    # Bug caught: deleting the whole normalization along with the cutoff
    # comparison. The cutoff only chose between two arms that both coerce;
    # dropping the coercion would hand every consumer str where it expects
    # Path, and the same-directory import checks silently stop matching.
    cache = tmp_path / ".veny_custom_modules_20250101-010101.pkl"
    cache.write_bytes(pickle.dumps({"helper": str(tmp_path / "helper.py")}))

    loaded = custom_modules.load_custom_modules_cache(a_settings(cwd=tmp_path), ...)

    assert loaded == {"helper": tmp_path / "helper.py"}
    assert all(isinstance(v, Path) for v in loaded.values())
```

Use the real function name and signature at `src/veny/analysis/custom_modules.py` — read it before writing the call; the surrounding tests in `tests/test_import_discovery.py` already build these pickles.

- [ ] **Step 2: Run it and confirm it passes for the wrong reason**

Run: `pixi run test tests/test_import_discovery.py -k string_paths -v`
Expected: PASS *before* the change — this test pins behaviour that must survive the deletion. Record that it passed; it is the regression net, not a red test. (Confirm it can fail: temporarily return `loaded_modules` unnormalized and watch it fail, then revert.)

- [ ] **Step 3: Delete the cutoff**

Remove the `PATHLIB_CUTOFF` constant and collapse the `if most_recent_timestamp < PATHLIB_CUTOFF:` / `else:` pair into the single coercing dict comprehension, keeping the `else` arm's isinstance-narrowing form (mypy needs it):

```python
                    # Pickles written before 2025-08-10 hold str, later ones
                    # hold Path; ek.ensure_path answers for both, which is why
                    # the date comparison that used to pick between two arms
                    # was deleted with veny's other pathlib cutoff.
                    normalized: dict[str, Path] = {
                        k: (v if isinstance(v, Path) else ek.ensure_path(v))
                        for k, v in loaded_modules.items()
                    }
                    return normalized
```

- [ ] **Step 4: Run the tests**

Run: `pixi run test tests/test_import_discovery.py -v`
Expected: PASS.

- [ ] **Step 5: Gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --all-files
git add src/veny/analysis/custom_modules.py tests/test_import_discovery.py
git commit -m "refactor: drop the pickle pathlib cutoff, keep the coercion"
```

---

### Task 5: Repoint every test off `Options`

**Goal:** No test constructs an `Options`. The class is unreferenced outside `cli.py` and `run_options.py`, and the suite is green — so Task 6's deletion is a deletion, not a rewrite.

**Files:**
- Modify: `tests/test_cache_search.py`, `tests/test_classify.py`, `tests/test_cli_entry_point.py`, `tests/test_import_discovery.py`, `tests/test_manifest_writing.py`, `tests/test_split_imports.py`, `tests/test_state_values.py`, `tests/test_uv_backend.py`, `tests/test_venv_naming.py`, `tests/test_wiring_4a.py`
- Modify: `scripts/differential_3d.py:343`, `scripts/differential_3e.py:33` (a docstring)

**Acceptance Criteria:**
- [ ] `rg -n '\b(cli|veny)\.Options\b' tests/ scripts/` → no matches.
- [ ] Every repointed test asserts the same thing it asserted before. Where a test used `Options` only as a bag for `stdlib`, `aliases` or `args`, it now builds that object directly — no new indirection, no new fixture that hides which value is under test.
- [ ] The drain assertions in `tests/test_state_values.py` (`not hasattr(cli.Options(), ...)`) are **deleted**, not rewritten: they pin that a field is not on a class that is about to not exist. Task 6 replaces them with one assertion that the class is gone.
- [ ] `tests/test_wiring_4a.py:404` and `tests/test_cli_entry_point.py:653` — the two `pathlibcutoff` pins — are deleted.
- [ ] Test counts do not fall except where this plan names a deletion. Report the before/after `pixi run test` counts in the commit message.

**Verify:** `pixi run test` → green, with a count equal to the previous run minus exactly the deletions named above.

**Steps:**

- [ ] **Step 1: Re-measure before touching anything**

```bash
rg -c '\bcli\.Options\b' tests/ scripts/ src/
rg -c '\bveny\.Options\b' tests/ scripts/ src/
rg -n 'import cli as (\w+)' tests/ scripts/
```

Reference measurement at `240767b` — **re-derive, do not trust**: 48 literal `cli.Options` across 8 test files, 25 `veny.Options` across 6 test files (5 of them aliasing `from veny import cli as veny`), 2 in `src/` (the re-export and `run_options.py`'s docstring), 2 in `scripts/` (one live call in `differential_3d.py`, one docstring in `differential_3e.py`). Phase 3e predicted 42 and measured 69; phase 4a measured 73. The alias spelling matches neither `cli\.Options` nor `setattr(cli, …)` — that blind spot has broken a symbol sweep in this program once already.

- [ ] **Step 2: Repoint, file by file, running that file's tests after each**

The three shapes, all mechanical:

```python
# Shape A -- Options as a bag for the stdlib index (test_cache_search.py,
# test_split_imports.py, test_venv_naming.py, test_manifest_writing.py):
options = veny.Options()
options.stdlib = stdlib_index.StdlibIndex(names=frozenset({"os"}), python_version=(3, 12), source="test")
...  interpreter_tag(options.stdlib)
# becomes
stdlib = stdlib_index.StdlibIndex(names=frozenset({"os"}), python_version=(3, 12), source="test")
...  interpreter_tag(stdlib)

# Shape B -- Options as a bag for the alias index (test_classify.py, 18 sites):
options = cli.Options()
options.aliases = _RecordingIndex({"uninst": "uninst-pypi"})
...  classify.split_imports(scan, aliases=options.aliases, ...)
# becomes
aliases = _RecordingIndex({"uninst": "uninst-pypi"})
...  classify.split_imports(scan, aliases=aliases, ...)

# Shape C -- Options as a bag for the parsed command line:
options.args = argparse.Namespace(reqs=True)
# becomes a plain argparse.Namespace(reqs=True) passed where args is wanted.
```

Where a helper's *signature* names `veny.Options` (`an_options`, `candidates`, `check` in `test_cache_search.py`; `an_options` in `test_manifest_writing.py` and `test_venv_naming.py`; `_settings_and_options` in `test_import_discovery.py`), retype the helper to take/return what it actually carries — a `StdlibIndex`, not an `Options` — and rename it to say so (`a_stdlib`). A helper called `an_options` that returns a `StdlibIndex` is worse than no rename.

In `tests/test_cli_entry_point.py`, the four list annotations (`self.options: list[cli.Options]`, `loaded: list[cli.Options]`, `passed_options: list[cli.Options]`) belong to spies over `save_options_to_json` / `load_last_used_options`, which no longer exist after Tasks 2 and 3 — those spies were already repointed there. Retype them to what they now capture (`list[state.LastUsed]`) or delete the spy if the test it served is gone.

`cli.parse_arguments(cli.Options())` at `tests/test_cli_entry_point.py:912` becomes `cli.parse_arguments()` in Task 6; leave it compiling here by passing a throwaway `Options()` only if you must, and note it for Task 6.

`scripts/differential_3d.py:343` is a *historical* driver for an older tree — it runs against a checkout of that era, so its `tree.cli.Options()` is correct for the tree it drives. Leave the call; add a one-line comment saying the symbol is that tree's, not this one's. `scripts/differential_3e.py:33` is a docstring; edit the prose.

- [ ] **Step 3: Confirm the sweep is complete**

```bash
rg -n '\b(cli|veny)\.Options\b' tests/ scripts/
rg -n 'Options' tests/ | rg -v 'test_options_surface|argparse'
```
Expected: the first prints nothing; the second prints only comments you have read and decided to keep.

- [ ] **Step 4: Gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --all-files
git add tests/ scripts/
git commit -m "test: build the values under test directly instead of an Options bag"
```

---

### Task 6: Delete `Options`

**Goal:** `run_options.py`, the `cli.Options` re-export and the last construction-input reads are gone; `cli.main` builds the run from locals and `parse_arguments()` returns the parsed command line.

**Files:**
- Delete: `src/veny/run_options.py`, `tests/test_options_surface.py`
- Modify: `src/veny/cli.py`, `src/veny/pipeline.py` (signature + docstrings)
- Modify: `tests/test_layering.py`, `tests/test_state_values.py`, `tests/test_cli_entry_point.py`

**Acceptance Criteria:**
- [ ] `parse_arguments() -> argparse.Namespace` takes no argument and returns the namespace; the two `--help` texts that interpolate `options.my_name` use the module-level name instead.
- [ ] `pipeline.run(settings, args, target, *, start_time=None)` — the `options` parameter is gone.
- [ ] `cli.main` builds `my_name = "veny"`, `home`, `cwd`, `log_mode` and `rawlog` as locals feeding the existing `Settings` construction. Nothing named `options` survives in `cli.py`.
- [ ] `src/veny/run_options.py` and `tests/test_options_surface.py` are deleted; `run_options` leaves `tests/test_layering.py`'s `state` layer, and the comment there stops promising a phase-4 deletion that has happened.
- [ ] `tests/test_state_values.py` carries one new test asserting the class is gone, replacing the seven `not hasattr(cli.Options(), ...)` drain assertions Task 5 deleted.
- [ ] `pixi run typecheck` is at or below 23 errors in 6 files — deleting a dynamically-attributed class should reduce it. Record the new number; it becomes the baseline for 4c.

**Verify:** `pixi run test` → green; `rg -n 'run_options|Options' src/` → no matches except `argparse` internals.

**Steps:**

- [ ] **Step 1: Write the failing tests**

In `tests/test_state_values.py`:

```python
def test_the_options_god_object_is_gone():
    # Bug caught: leaving the class alive as a re-export or an unused module,
    # which is how it survived phases 3e and 4a. The whole point of phase 4
    # is that there is one place a run's state lives, and this asserts there
    # is no second one.
    assert not hasattr(cli, "Options")
    assert importlib.util.find_spec("veny.run_options") is None
```

In `tests/test_cli_entry_point.py`, repoint `cli.parse_arguments(cli.Options())` at `:912`:

```python
def test_parse_arguments_returns_the_parsed_command_line(monkeypatch):
    # Bug caught: a parse_arguments that still writes onto a passed-in object
    # and returns None -- callers would read a namespace that is never filled.
    monkeypatch.setattr(sys, "argv", ["veny", "thing.py", "--rawlog"])

    parsed = cli.parse_arguments()

    assert parsed.script == "thing.py"
    assert parsed.rawlog is True
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `pixi run test tests/test_state_values.py::test_the_options_god_object_is_gone tests/test_cli_entry_point.py -k parse_arguments -v`
Expected: FAIL — `assert not hasattr(cli, "Options")` fails, and `parse_arguments()` raises `TypeError: parse_arguments() missing 1 required positional argument`.

- [ ] **Step 3: Rewrite `cli.py`**

```python
MY_NAME: Final[str] = "veny"


def parse_arguments() -> argparse.Namespace:
    """Parse the command line.

    Returns:
        The parsed arguments. `--help` with no arguments at all prints the
        guide and exits 0 rather than returning.

    Raises:
        SystemExit: --version or a bare invocation; argparse's own behaviour.
    """
```

with `options.my_name` in the `--blank-slate` and `--rawlog` help texts replaced by `MY_NAME`, and the tail becoming:

```python
    return parser.parse_args()
```

and `main`:

```python
    start_time = dt.datetime.now()
    args = parse_arguments()
    rawlog = getattr(args, "rawlog", False)
    log_mode = logging.DEBUG if getattr(args, "debug", False) else logging.INFO
    run_settings = settings.Settings(
        my_name=MY_NAME,
        my_dir=Path.home() / MY_NAME,
        cwd=Path.cwd().expanduser().resolve(strict=True),
        venv_name="myenv",
        stay_out_list=settings.DEFAULT_STAY_OUT_LIST,
        search_above_this_dir=True,
        rawlog=rawlog,
        known_bad_imports=settings.DEFAULT_KNOWN_BAD_IMPORTS,
        also_needs=settings.DEFAULT_ALSO_NEEDS,
        extra_requirements_file="extra_requirements.txt",
    )
```

then `target = pipeline.resolve_target(args)`, `pipeline.feeling_lucky(args, target, my_name=MY_NAME, rawlog=rawlog)`, `ek.configure_logging(MY_NAME, log_level=log_mode, rawlog=rawlog)`, `pipeline.run(run_settings, args, target, start_time=start_time)` and `ek.print_all_errors(memory_handler, rawlog)`.

Add `from pathlib import Path` and `Final`; drop `run_options` from the imports.

Note the one behaviour detail worth preserving deliberately: `Options.__init__` resolved `cwd` with `Path.cwd().expanduser().resolve(strict=True)` *before* argparse ran. It now resolves after. Nothing between them changes the working directory, so this is not a behaviour change — but say so in the commit message so the next reader does not have to re-derive it.

- [ ] **Step 4: Drop the parameter from `pipeline.run` and delete the module**

Remove `options` from `run`'s signature and Args docstring, remove the `run_options` import, and rewrite the module docstring's opening paragraph (lines 14-19), which currently describes the coupling this phase removed.

```bash
git rm src/veny/run_options.py tests/test_options_surface.py
```

In `tests/test_layering.py`, change the `state` layer to `frozenset({"state"})` and rewrite the comment that explains `run_options`' membership.

- [ ] **Step 5: Run everything**

Run: `pixi run test`
Expected: PASS.

- [ ] **Step 6: Gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --all-files
git add -A src/veny tests/
git commit -m "refactor: delete the Options god object and its module"
```

---

### Task 7: Delete `json_types` and repoint the emmykit guard

**Goal:** The JSON type registry goes with its only consumer, and veny still refuses a pre-0.4.0 emmykit at import with a readable message.

**Files:**
- Delete: `src/veny/json_types.py`, `tests/test_json_types.py`
- Modify: `src/veny/cli.py:23-38`, `tests/test_layering.py`, `tests/test_split_imports.py:323-359`, `tests/test_import_guard.py`

**Acceptance Criteria:**
- [ ] `json_types` appears nowhere in the repository, including `tests/test_layering.py`'s index layer and its `SANCTIONED_EXCEPTIONS`.
- [ ] The three `to_jsonable`/`from_jsonable` tests in `tests/test_split_imports.py` are deleted — they test registration that no longer happens, and their stated justification ("written to the last-used options file") is exactly what this phase removed.
- [ ] `cli.ResolvedImport` stays: it is re-exported for the suite and for readers, and `alias_index` still defines it.
- [ ] Importing `veny.cli` against an emmykit reporting `0.3.4` still exits non-zero, mentioning `0.4.0` and `pip install`; against one reporting nothing, likewise.
- [ ] `tests/test_import_guard.py`'s three existing tests still pass, with the stub comment corrected — `register_json_type` is no longer what the guard probes.

**Verify:** `pixi run test tests/test_import_guard.py tests/test_layering.py -v` → all pass; `rg -n 'json_types|register_json_type' .` → no matches.

**Deviation from the user's ruling, recorded here rather than silently.** The ruling was "keep the guard but probe a name veny still calls". That cannot work: `tests/test_import_guard.py` records that `register_json_type` is *the only symbol new in 0.4.0*, so every other name veny calls exists in 0.3.x too and a `hasattr` probe on one would let an old emmykit through — the guard would become decoration. The guard therefore compares `ek.__version__` (which the installed emmykit reports as `"0.4.0"`) against a floor. That keeps the ruling's intent — fail at import with an install hint rather than mid-run with an `AttributeError` — and is why this task has a test for the no-`__version__` case, which the old `hasattr` shape did not need.

**Steps:**

- [ ] **Step 1: Write the failing test**

In `tests/test_import_guard.py`:

```python
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
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pixi run test tests/test_import_guard.py -k no_version -v`
Expected: FAIL — with the current `hasattr(ek, "register_json_type")` guard the stub has no such attribute, so it *passes* for the wrong reason. Confirm the reason: temporarily add `stub.register_json_type = lambda *a, **k: None` to the stub source and re-run; it then fails, which is the state the new guard must handle. Remove the temporary line before continuing.

- [ ] **Step 3: Replace the guard**

In `src/veny/cli.py`, replace the `hasattr` block:

```python
_MINIMUM_EMMYKIT: Final[tuple[int, int, int]] = (0, 4, 0)


def _emmykit_version() -> tuple[int, ...]:
    """The installed emmykit's version, as far as it can be read.

    Returns:
        The leading numeric components of ``ek.__version__``, or an empty
        tuple when it is absent or unreadable -- which compares less than any
        real version, so an emmykit that will not say what it is is refused.
    """
    parts: list[int] = []
    for piece in str(getattr(ek, "__version__", "")).split("."):
        digits = ""
        for character in piece:
            if not character.isdigit():
                break
            digits += character
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


if _emmykit_version() < _MINIMUM_EMMYKIT:
    raise SystemExit(
        f"veny requires emmykit >= 0.4.0; found {getattr(ek, '__version__', 'unknown')}.\n"
        f"Upgrade it with:  pip install -U 'emmykit>=0.4.0'"
    )
```

and delete the `json_types` import and the `json_types.register_types()` call, keeping the `ResolvedImport` re-export and rewriting its comment (it currently ends "Its JSON handlers live in json_types.").

- [ ] **Step 4: Delete the module, its tests and its layering entries**

```bash
git rm src/veny/json_types.py tests/test_json_types.py
```

In `tests/test_layering.py`: drop `"json_types"` from the index layer's frozenset and delete its `SANCTIONED_EXCEPTIONS` entry and the comment above it. In `tests/test_split_imports.py`: delete `test_resolved_import_still_round_trips_when_alias_index_is_lazy`, `test_alias_index_is_serialized_as_structured_data` and `test_resolved_import_round_trips_through_json`, and any import left unused. In `src/veny/alias_index.py:84`, fix the comment that explains `ResolvedImport` lives there "so that json_types can register" it — the reason is now just that `alias_index` imports nothing of veny's.

- [ ] **Step 5: Run everything**

Run: `pixi run test`
Expected: PASS.

- [ ] **Step 6: Gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --all-files
git add -A src/veny tests/
git commit -m "refactor: delete the JSON type registry with its only consumer"
```

---

### Task 8: The STANDING CHECK — a wiring index for every changed call site

**Goal:** Every argument at every call site this phase changed is either killed by a named test, driven, or recorded as an open hole — measured from the AST, not by hand.

**Files:**
- Create: `docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md`
- Modify: `scripts/wiring_sweep_4a.py` → copy to `scripts/wiring_sweep_4b.py` and retarget
- Create/Modify: `tests/test_wiring_4b.py` for the holes the sweep finds

**Acceptance Criteria:**
- [ ] The sweep enumerates arguments at every call site in `last_used.py`, `pipeline.py`'s three changed sites, `cache_search.find_match_dir_in_cache` and `cli.main`, from the AST.
- [ ] Each row is KILLED (named test), DEAD (no reader — a deletion candidate for 4c, not a fix here), or OPEN HOLE.
- [ ] Every OPEN HOLE is either closed by a test in `tests/test_wiring_4b.py` or recorded in the index with the reason it is left open.
- [ ] Tests added here assert **identity** where identity is the property (the record the run saved is built from the handle the run used), not merely equality of two freshly-built values.
- [ ] The sweep runs under `pixi run` (so `PYTHONPATH=src` is set) and sanity-imports each mutated module before believing a failure. Phase 4a's first sweep reported 86 spurious kills for want of this.

**Verify:** `pixi run python scripts/wiring_sweep_4b.py` → a table with zero unexplained OPEN HOLE rows; `pixi run test tests/test_wiring_4b.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Copy and retarget the harness**

```bash
cp scripts/wiring_sweep_4a.py scripts/wiring_sweep_4b.py
```

Change its target list to this phase's changed sites, and its docstring to say which phase it belongs to and what it measured (fill the numbers in after the first clean run — no placeholder may survive the task).

- [ ] **Step 2: Run it and read every row**

Run: `pixi run python scripts/wiring_sweep_4b.py`

- [ ] **Step 3: Close the holes**

Write one test per OPEN HOLE in `tests/test_wiring_4b.py`, in the shape `tests/test_wiring_4a.py` uses. The three that must exist whatever the sweep says:

```python
def test_the_saved_record_names_the_folder_the_run_ended_with(tmp_path, ...):
    # Bug caught: writing the record before the failed- rename, which points
    # the next run at a directory that no longer exists -- and the failure is
    # a silent cache miss, not an error.

def test_the_cache_search_is_handed_the_record_for_this_script(tmp_path, ...):
    # Bug caught: building the reader's script_dir/python_script from the
    # wrong source (cwd rather than the target), which makes the pointer
    # never match for a script run from another directory.

def test_feeling_lucky_reads_the_same_record_the_run_writes(tmp_path, ...):
    # Bug caught: the writer and the two readers disagreeing about the
    # filename. Nothing else in the suite compares them against each other,
    # and each side passes its own tests while the pair is broken.
```

- [ ] **Step 4: Write the index**

`docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md`, in the shape of `docs/superpowers/plans/2026-08-21-state-model-values-wiring-index.md`: one row per argument, with the killer named by test function, and a header carrying the totals.

- [ ] **Step 5: Gates and commit**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
pixi run pre-commit run --all-files
git add scripts/wiring_sweep_4b.py tests/test_wiring_4b.py docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md
git commit -m "test: sweep every argument phase 4b rewired"
```

---

### Task 9: The differential, and a live two-run check

**Goal:** The whole phase reduces to a diff whose every hunk is one of the three sanctioned changes — measured against `cf2ded4`, mutation-tested so a clean diff means something.

**Files:**
- Create: `scripts/differential_4b.py`
- Modify: `PROGRESS.md` is Task 10's; this task's findings go in the script's docstring

**Acceptance Criteria:**
- [ ] The driver runs `veny.cli.main()` through argv in two trees, with a counting clock, a fixed hash seed, a purged bytecode cache and a stand-in at every subprocess, network and venv boundary — reusing `scripts/differential_4a.py` rather than reimplementing it.
- [ ] It adds layers for what this phase changed: a run that writes a record (report the record's filename and contents), a second run that reads it, `--feeling-lucky` with a record present, `--feeling-lucky` with only an old-format record present (the sanctioned fallback), and `--blank-slate` with a record in the directory.
- [ ] The diff against `cf2ded4` contains only: the `veny.cli.__file__` header line, the record's filename and payload, and the one fallback for a directory holding only an old-format record. Anything else is a regression to fix before the commit.
- [ ] Mutation evidence in the docstring: at least four deliberate regressions (wrong filename, `str` instead of `Path` on read, record written before the rename, cache-search pointer ignored), each with the diff size it produced, plus the clean and reverted numbers.
- [ ] A **live two-run check**, run from a real shell and recorded in the docstring with its actual output: run a script, confirm the record file appears with the venv inside it, run it again, confirm the second run reuses that environment. Then delete the record and confirm the run rebuilds or rescans without error. Note the install shape used (`pixi run` means `sys.prefix == sys.base_prefix`, so the in-virtualenv branch is **not** exercised — that is 4c's).

**Verify:**
```bash
git archive cf2ded4 src/veny | tar -x -C /tmp/old-veny
pixi run python scripts/differential_4b.py /tmp/old-veny > /tmp/old.txt
pixi run python scripts/differential_4b.py /workspace    > /tmp/new.txt
diff -u /tmp/old.txt /tmp/new.txt
```
→ only the sanctioned hunks above.

**Steps:**

- [ ] **Step 1: Copy the harness and add this phase's layers**

```bash
cp scripts/differential_4a.py scripts/differential_4b.py
```

Read `scripts/differential_4a.py`'s docstring first — it documents the `sys.path.insert` requirement (never `PYTHONPATH`, which `pixi.toml`'s `[activation.env]` overwrites, silently testing the live source twice) and the stand-ins. Keep both.

- [ ] **Step 2: Run it against both trees and read the diff line by line**

Any hunk you cannot name is a regression. Fix the code, not the driver.

- [ ] **Step 3: Mutate, and record what each mutation cost**

For each of the four regressions above: introduce it, re-run both trees, record the diff line count, revert, re-run and confirm the number returns to the clean value. A mutation that does not change the diff is a coverage hole in the driver — add the layer that would have caught it.

- [ ] **Step 4: The live two-run check**

From a real shell, not from a test:

```bash
cd /tmp && mkdir -p venytest && cd venytest
printf 'import yaml\nprint("ok")\n' > hello.py
pixi run --manifest-path /workspace/pixi.toml python -m veny hello.py
ls -a | grep last-used
cat .hello.py-veny-last-used.json
pixi run --manifest-path /workspace/pixi.toml python -m veny hello.py
```

Record the exit statuses, the record's contents and whether the second run reused the environment.

- [ ] **Step 5: Write the docstring and commit**

The docstring carries: what the driver adds over 4a's, the expected hunks, the mutation table with real numbers, the live-run transcript summary, and a numbered list of residual risks this differential cannot see (4a's had eight; inherit the ones still open and add any this phase introduces). No placeholder numbers.

```bash
pixi run lint
pixi run python -m ruff format --check .
git add scripts/differential_4b.py
git commit -m "test: add the phase 4b differential and its mutation evidence"
```

---

### Task 10: Close the phase

**Goal:** `PROGRESS.md` tells the next session the truth about what 4b did, what it did not, and who owns what is left.

**Files:**
- Modify: `PROGRESS.md`
- Modify: `README.md` (only if it mentions the options JSON or the per-run files)
- Modify: `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md` (only if this phase deviated from the amendment block already committed at `83fd14c`)

**Acceptance Criteria:**
- [ ] **Current work** points at 4c as the next action, with 4c's scope restated from the phase-4 table.
- [ ] Every gate number is **measured in the closing session**, not copied from a task report: `pixi run test`, `pixi run lint`, `ruff format --check`, `pixi run typecheck` (the new mypy ceiling, with its file count).
- [ ] The deferred items 4b closes are struck with the commit that closed them: design amendment 9, `pathlibcutoff` and both readers, the `Options` drain, the `cli.Options` re-export and the two-spelling test references (with the **measured** final count, not this plan's reference figure), and `check_venv_dir`'s `issubset()` self-heal if it turns out to have gone with the record — check, do not assume.
- [ ] What 4b did **not** do is listed with its owner: the in-virtualenv guard, `--feeling-lucky`'s signal normalization, latent defects 1 and 3, the residual dead arguments (all 4c's); removing the probe venv from classification and the single-file reachability gap (still unowned).
- [ ] Any amendment this phase's execution forced beyond the five already recorded is added to the design doc's 4b block, numbered on.
- [ ] The gotchas section gains anything this phase learned that the code does not say — at minimum, the retirement of the "keep `register_types()` at module scope" gotcha, which now describes nothing.
- [ ] A whole-branch review is requested before the merge. 3b, 3c, 3d and 3e each turned up Important issues per-task review missed; 4a's came back clean, which is one data point, not a reason to skip it.

**Verify:** `rg -n '4b|last-used' PROGRESS.md | head -40` → the current-work block reads as a true statement of where the program is.

**Steps:**

- [ ] **Step 1: Re-measure the gates on the branch**

```bash
pixi run test
pixi run lint
pixi run python -m ruff format --check .
pixi run typecheck
```

- [ ] **Step 2: Re-measure the deletions**

```bash
rg -c 'Options' src/ tests/ scripts/
rg -n 'json_types|pathlibcutoff|run_options' . || echo "clean"
```

- [ ] **Step 3: Rewrite the Current work block and migrate the closed items**

Move, do not copy: an item that 4b closed leaves Deferred items and appears in the closing entry with its commit.

- [ ] **Step 4: Commit**

```bash
pixi run pre-commit run --all-files
git add PROGRESS.md README.md docs/
git commit -m "docs: close phase 4b with measured gates and its ledger"
```

- [ ] **Step 5: Request the whole-branch review**

Use `superpowers-extended-cc:requesting-code-review` against the whole branch (`main..last-used-persistence`), then work its findings before merging `--no-ff`.

---

## Self-review of this plan

**Spec coverage.** The design's Persistence paragraph is Tasks 1–3; its 4b amendment block is Tasks 1 (record location and filename), 3 (old records ignored, args de-mutation), 4 (both pathlib cutoffs) and 7 (`json_types`, guard). The "Deleted rather than rehomed" list names `pathlibcutoff` (Tasks 3, 4, 6) and `options_json_filepath` (Task 6). Ledger item 5 — `check_venv_dir`'s `issubset()` self-heal, which the design says phase 4's persistence change makes unnecessary — is **not** given its own task: it is checked in Task 10's acceptance criteria, because whether it is still reachable depends on what Task 3 leaves behind. If it survives, 4c owns it, and Task 10 records that.

**Placeholders.** Task 4's test and Task 8's tests carry `...` where the surrounding fixtures supply arguments that already exist in those files; each says which helper to read. Task 9's mutation numbers are explicitly to be filled by running the mutations — the acceptance criterion forbids placeholder numbers surviving the commit.

**Type consistency.** `state.LastUsed(venv_dir, venv_python, timestamp)` is constructed in Tasks 1, 2, 8 and 9 and consumed in Tasks 2 and 3 under those field names. `last_used.load(*, script_dir, python_script, my_name, rawlog)` and `last_used.load_venv_python(...)` share one keyword set, used identically at every call site in Tasks 1–3. `last_used.save(record, *, script_dir, python_script, my_name)` takes the record positionally everywhere.
