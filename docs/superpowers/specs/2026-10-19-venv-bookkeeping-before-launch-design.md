# Venv bookkeeping before launch — design

**Status:** approved 2026-10-19 (option A, chosen by the user over B, C and D
below)
**Scope:** when `pipeline.run` drops a new venv's `failed-` prefix and saves the
last-used record, and making the venvs veny builds survive that rename. One
behaviour change, one uv flag, their tests and docs.

## Problem

Every interrupted run leaks a `failed-` venv, and the next run builds another.
The user runs long-lived monitor scripts that never exit on their own: they end
with Ctrl-C or a reboot. Their `~/veny` holds hundreds of orphaned venvs.

`pipeline.run` builds a new venv as `failed-<name>`. It drops the prefix
(`cache_search.rename_venv`) and saves the last-used record (`last_used.save`)
only *after* `run_script` returns. Ctrl-C delivers SIGINT to the whole
foreground process group, so veny is interrupted too. `subprocess.run`
re-raises `KeyboardInterrupt`, and nothing in `src/veny` catches it or any
signal. A reboot sends SIGTERM, and veny simply dies. Either way the venv keeps
its prefix and no record is written. The cache scan keeps only folders whose
name starts with `venv_name`, so it never offers a `failed-` folder, and the
next run finds nothing and builds again.

The user's pre-repo `veny.py` has the same ordering and the same filter, and
shows the same symptom.

Reproduced live on `main` at `6346830`. Three runs of a `while True: sleep`
script importing `unidecode` were each ended with a group signal: SIGINT,
SIGINT, then SIGTERM. They left three `failed-myenv-py3.13-…-unidecode` folders
and no last-used record. Run 2 logged "No matching venv folders found in the
cache." A control script that exits normally was renamed and recorded as
designed.

## What the rename gate actually checks

The `failed-` prefix was meant to mean "this venv has not been shown to run the
script". The code never implemented that intent. The rename condition is
"prefix present and `install_succeeded`", and the script's exit status is not
consulted. A script that imports cleanly and then dies with
`ModuleNotFoundError` on a dynamic import exited 1 and was still renamed and
recorded, live on `main`.

By the time `run_script` is called, every input to the gate is already known:

1. `uv venv` succeeded.
2. `uv pip install -r` succeeded (`install_succeeded`).
3. `verify_and_repair_imports` ran.
4. The manifest was written.
5. `check_packages_in_venv` passed. If it fails, `setup_virtualenv` returns no
   handle, the script never runs, and the folder keeps its prefix.

Placing the rename after the run therefore adds exactly one condition: veny was
still alive when the script ended. That says nothing about the venv.

## Decision

Do the rename and the last-used save immediately **before** launching the
script, and build venvs with `uv venv --relocatable`.

After this change, `failed-` means exactly this: the build did not finish, or
its install or imports did not verify. That is the job the prefix does well.
A Ctrl-C or reboot in the middle of an install leaves a half-built venv, and
the prefix keeps it from ever being reused. Those are the failures a rebuild
can actually fix.

### Alternatives rejected

- **Gate the rename on the script exiting 0.** Long-running scripts never exit
  0: Ctrl-C gives -2 and a reboot gives nothing. Such a gate would make the leak
  permanent by design. Many nonzero exits have nothing to do with the venv (bad
  arguments, network down, a bug in the script). And when a failure *is* the
  venv's fault — an import static analysis missed, or a newer package version
  that broke an API — a rebuild from the same requirements produces the same
  venv. Keeping `failed-` then costs a rebuild and an orphan, and fixes
  nothing.
- **Rename once the script has survived N seconds.** Renaming a venv while a
  script runs from it breaks every import that script has not done yet. Shown
  live: a venv renamed one second into a run gave `ModuleNotFoundError` on the
  script's next import. A rename may happen only before launch or after exit.
- **B — keep the post-run rename, catch SIGINT, SIGTERM and SIGHUP.** It adds
  no validation, because the gate still ignores the script's outcome. It still
  leaks on SIGKILL, the out-of-memory killer and power loss. Signal handling in
  the parent is fiddly to get right (forwarding, a second Ctrl-C). A second
  instance started while the first runs still cannot see the venv.
- **C — never rename; build at the final name and mark completion in the
  manifest.** This avoids every rename hazard, but the folder name is the cache
  search's prefilter, and `record_venv_state` renames a folder whose package
  list changed during repair. Both would need redesigning, which is too large
  for this fix.
- **D — record runtime `ModuleNotFoundError`s in the manifest so the next run
  installs the missing package.** This is the only option that delivers "make
  sure the script can run with this venv", by learning from the failure
  instead of rebuilding an identical venv. It is a separate feature, deferred.

## Design

### 1. Ordering — `src/veny/pipeline.py`, `run`

In the branch that runs the script from a cached or freshly built venv, the
`failed-` rename block and the `last_used.save` call move from after
`run_script` to immediately before it. `run_script` is then called with the
interpreter of the post-rename handle, so the script launches from the venv's
final path. Launching from the stale `failed-` path after renaming would break
the script's later imports — the mid-run hazard above.

Unchanged:

- The rename condition: the prefix is present and `install_succeeded` is true.
- A venv whose imports fail to verify keeps `failed-`, and the script does not
  run (status 1).
- A venv with `install_succeeded` false but every import verified keeps
  `failed-` and still runs. Its last-used record points at the `failed-`
  folder, and the next run's last-used path re-verifies it at the import level
  (`check_venv_dir` does not reject the prefix). The only difference is that
  the record now gets written before the launch instead of after it.
- Reused venvs are never renamed. Their last-used record is now saved before
  launch instead of after.
- `run` still returns the script's exit status, and still logs "Script exited
  with status N" for a nonzero one.
- The other two `run_script` branches — no packages needed, and already inside
  a venv — never touch `~/veny` or the last-used record, and are not changed.

The comments and docstrings that describe the rename as happening once the
script "has run successfully" are rewritten to state the gate as it is. That
covers the inline comment on the rename, the comment on the save, the
reused-venv comment, `setup_virtualenv`'s "Only remove the failed part if this
process completes successfully" comment, and its docstring's account of why
`run` needs `install_succeeded`.

A last-used record that cannot be written — the script's directory is shared
or read-only, or the disk is full — logs a warning, and the script still
launches. The record is a shortcut: without it, the next run's cache scan
finds the renamed venv by its manifest. The branch's final review found this
gap. While the save came after the launch, a failed write cost only a
traceback once the run was over. Before the launch, an unguarded write would
stop the script from ever running.

### 2. Relocatable venvs — `src/veny/environment.py`, `create_venv`

`create_venv` passes `--relocatable` to `uv venv`. With it, console scripts get
a `/bin/sh` shim that locates `python` relative to its own resolved path, and
`activate` computes `VIRTUAL_ENV` from its own location.

This fixes an existing breakage. Every venv veny renames today keeps the
`failed-` path in its console scripts and its `activate`. Shown live:
`bin/unidecode` in a renamed venv fails with
`…/failed-myenv-…/bin/python: not found`. With `--relocatable` on uv 0.12.3,
the same rename leaves the entry point working and `activate` pointing at the
new path.

- `uv venv --relocatable` exists in uv 0.9.0, veny's declared floor
  (`uv>=0.9,<1.0`). The floor does not change.
- `uv pip install` into the venv honours the setting. Shown live: entry points
  installed after creation got the relative shim.
- `rename_venv`'s `pyvenv.cfg` fix-up stays. It is harmless and covers a venv
  not built by `create_venv`.
- Caveat, which follows from the shim: an entry point *copied* out of the venv
  no longer works, because it looks for `python` next to itself. A symlink to
  one still works, because the shim resolves `$0` with `realpath` first.
- The shim and the relocatable `activate` call the `realpath` command, which
  macOS 12 and earlier do not ship. There, a venv's console scripts and
  `activate` fail. veny's own launches are unaffected, because veny runs
  `bin/python` directly.
- Venvs built before this change are not retrofitted. Their console scripts
  stay broken, which does not affect veny's own launches (veny runs
  `bin/python` directly).

## Testing

Red first for each, per the project's TDD rules and the `test-design` skill.

1. **The interrupted-run test**, in `tests/test_cli_entry_point.py`, driven
   through the existing `_drive_main` harness like
   `test_main_drops_the_failed_prefix_from_the_venv_it_just_built`. It uses a
   fake `setup_virtualenv` that returns a real `failed-…` folder with
   `install_succeeded=True`, and a fake `run_script` that records its
   interpreter argument and then raises `KeyboardInterrupt`, as a Ctrl-C
   reaching veny does. It asserts that `KeyboardInterrupt` propagates out of
   `cli.main`, and then that:

   - the folder exists without its prefix and the `failed-` path is gone;
   - a last-used record exists for the script, naming the renamed folder;
   - the interpreter `run_script` received lies inside the renamed folder.

   Today's code fails all three.
2. **The `create_venv` command test**, `tests/test_uv_backend.py`'s exact-argv
   assertion (currently around line 328), now expects `--relocatable`.
3. **A live relocation test**, in `tests/test_environment.py`, with real uv,
   `UV_OFFLINE=1`, and no `subprocess` stubbing. `tests/wheels.py`'s
   `build_wheel` gains an optional console-script parameter, which writes
   `entry_points.txt` and a `main()`. The test builds a venv with
   `create_venv`, installs the wheel, renames the folder, then asserts that
   the console script runs from the new path and that sourcing `bin/activate`
   sets `VIRTUAL_ENV` to the new path.
4. **The existing rename test's docstring** ("renames it only once the run has
   actually succeeded") is corrected to the new gate.
5. **A live run**, repeating the reproduction in a throwaway `HOME`. Two
   Ctrl-C'd runs of the never-exiting script must leave exactly one venv, with
   no `failed-` prefix. The second run must log "Using existing virtual
   environment", and the folder's console script must run.

`pixi run pytest --cov` and `pixi run pre-commit run --all-files` must pass
before each commit.

## Documentation

- **`PROGRESS.md`.** The deferred item "Every interrupted run leaks a `failed-`
  venv…" migrates to this spec and its plan, leaving a pointer behind. The
  gotcha "`~/veny/failed-<name>` is the PROVISIONAL build folder" is updated:
  the log now shows the script launching from the final, unprefixed path. A
  `failed-` folder left on disk after a run now means the build or
  verification failed or was interrupted.
- **`README.md`.** It does not mention the prefix, so no change is needed.

## Out of scope

- Cleaning up the orphans already in `~/veny`. Venvs built by the pre-repo
  `veny.py` have no manifest, and the cache search already skips those, so
  `--blank-slate` or a manual delete is the user's call.
- Option D (learning runtime import failures).
- Retrofitting `--relocatable` onto existing venvs.
- Regenerating the wiring indexes, which have been marked stale since the
  2026-10-19 hygiene pass.
