# Hygiene notes

The running log of hygiene passes: what each one deliberately left alone, and
why, so the next pass does not re-litigate it. Locations are given by symbol,
not line number — line numbers drift with every edit. Re-check an entry
against the code before acting on it.

Real bugs found during a pass are not hygiene and are not listed here; they
are recorded in `PROGRESS.md` under Deferred items.

## 2026-10-19 — whole-repo audit, then the approved fix-now set

Branch `hygiene-2026-10-19`, from `bcc60b6`. Every commit kept the CI gate
green (ruff check, ruff format --check, pytest; mypy held at its 23-error
ceiling). Eight real bugs were found and recorded in `PROGRESS.md`, not fixed.

### Kept, awaiting a ruling

Each is a real smell whose fix is either a behaviour change, touches a
pinned interface, or is a judgement the owner should make.

- **`cache_search.find_match_dir_in_cache`'s latest/oldest/smallest
  branches** are three near-copies (pick, `None` guard, the same six-argument
  `check_venv_dir` call, an error log differing by one word). The `None`
  guards cannot fire: the helpers return `None` only for an empty dict, and
  the branches run only when it is non-empty. `latest_venv` / `oldest_venv` /
  `smallest_venv` also describe their keys as folder paths "as strings or
  os.PathLike objects" while typed `dict[Path, ...]`. Kept: the log text must survive verbatim, mypy
  narrowing would need the `Optional` returns changed, and the branches are
  pinned by spy and differential evidence.
- **`verify.resolve_and_verify` accepts a `bool`-returning importer** that
  only tests use (every `resolve_and_verify` call in `tests/test_verify.py`
  passes one); production always passes an `ImportOutcome` importer. Kept:
  the docstring states the intent; removing it means migrating those tests.
- **`state.Requirements.seen_stdlib` is never read** — `pipeline.report`
  reaches `scan.seen_stdlib_imports` instead, through
  `warn_about_system_packages`. Kept: removal touches every
  `Requirements` constructor in the tests, and PROGRESS.md left "should it
  stay" open.
- **`verify.source_import_names` is computed up to three times per run** from
  the same inputs (in `pipeline.run` and again inside
  `pipeline.setup_virtualenv`). Kept: hoisting it adds a `setup_virtualenv`
  parameter, and `tests/test_wiring_4a.py` spies the exact keyword set.
- **`pipeline.blank_slate` catches `BaseException` around each `unlink`**,
  with no comment saying why, so Ctrl-C mid-loop is logged and the loop goes
  on. `except OSError` is almost certainly what was meant. Kept: narrowing it
  changes what propagates.
- **`alias_index.AliasOverrideError` reaches the user as a traceback** —
  `cli.main` maps the other three run errors to exit statuses but not this
  one. "Fatal by design" is recorded; how it is presented is not.
- **`tests/test_layering.py::test_split_imports_writes_nothing_back_onto_options`
  can no longer fail** — no name `options` exists in `pipeline.py` or
  `cli.py`. Kept: `7e6cc16` deliberately inverted it rather than deleting it.
- **`alias_index.Candidate.top_levels` is written and only a test reads it.**
  Kept: the alias-resolver design spec defines the field.
- **The rejection kinds (`"import_failed"`, `"install_failed"`,
  `"import_unavailable"`) are bare strings** in `verify.py`, checked only at
  runtime by `AliasCache.reject`. A `Literal` alias would let mypy check them.
  Kept: a cross-module type change.
- **`tests/test_pypi_client.py::test_range_request_avoids_transferring_the_whole_wheel`
  overclaims**: its fixture (about 20 KB) is smaller than the 64 KiB first
  window, so the Range it sends covers the whole wheel. Rename, delete, or
  grow the fixture — the owner's call.
- **`tests/test_split_imports.py` no longer tests `split_imports`** (those
  moved to `tests/test_classify.py`); what remains is a mix. A test-layout
  decision.
- **`scripts/`**: the differentials and wiring sweeps are the finished
  re-architecture's record. `differential_3d`, `_3e` and `_4a` no longer run
  against the current tree (each now says so); 440 of
  `wiring_sweep_4b.py`'s 487 lines recur verbatim in `wiring_sweep_4c.py`.
  Whether they are frozen history or maintained tools decides whether that
  copy matters.
- **Sixteen scaffold-baseline dev packages in `pixi.toml`** are referenced by
  nothing in the repo (python-dotenv, httpx, pydantic, typer, stamina,
  openjdk, ipython, ipdb, py-spy, shellcheck, go-shfmt, taplo, difftastic,
  hyperfine, go-yq, hatch-vcs). Kept: removal changes `pixi.lock`, and the
  baseline is scaffold policy.
- **`scripts/smoke-install.sh` says "Run it before publishing"**, but neither
  `RELEASING.md` nor `release.yml` runs `pixi run smoke`. Either the runbook
  is missing a step or the script's instruction is stale.
- **The `venv_tag or run_tag` fallback is applied in two places** in
  `cache_search` (`record_venv_state` and `manifest_for`), whose comment says
  they must agree. Kept: merging them changes `manifest_for`'s signature,
  which the tests call directly.

### Kept until the bug they describe is fixed

These comments are false, but they describe the code paths of two recorded
bugs and should change with the fix, not before it:

- The pipeline comment saying emmykit "document[s] `""` for absent",
  `environment.venv_build_interpreter`'s docstring, and the comments in
  `tests/test_venv_naming.py` and `tests/test_alias_index.py` saying
  `find_preferred_python_version()` returns `""` or is passed "straight
  into build()" — all part of the empty-interpreter alias-probe bug.
  **Corrected with that fix** (audit bug-fix plan, Task 2).
- `verify.check_packages_in_venv`'s "This function does not raise
  exceptions" — part of the dangling-interpreter `FileNotFoundError` bug.

### Candidates for a later pass

Found by the audit, low risk, but not in the set approved for this pass:

- `analysis/imports.py`: the `mod, loc = res; _register_import_name(mod); if
  loc: ...` block is written three times, and the `__import__` branch
  hand-writes `_register_import_name`'s top-level-or-function choice.
- Test helpers: `a_stdlib()` is defined three times (`test_cache_search`,
  `test_manifest_writing`, `test_venv_naming`); the exec-the-check-script
  fake venv three times (`test_cache_search`, `test_verify`,
  `test_split_imports`); `tests/test_wiring_4a.py` spells
  `state.Requirements(...)` out 11 times instead of using `a_requirements`;
  `test_setup_virtualenv_writes_the_extra_requirements_version_specifiers`
  re-creates `_stub_the_venv_away` stub for stub;
  `test_probe_degrades_on_nonzero_exit` is a weaker duplicate of
  `test_a_probe_failure_reports_an_unknown_interpreter_tag`.
- `cli.py`'s shebang and "For Python 3.7+ compatibility" comment, and the
  shebangs on `alias_index.py` and `stdlib_index.py` (all mode 100644,
  none runnable directly).
- `alias_index.empty()` has no production caller since `Options` died, yet
  its docstring and `pipeline.build_alias_index`'s still describe the
  "needed before the target interpreter is known" flow. Decide whether
  `empty()` moves into the tests.

### PROGRESS.md entries the audit found false

Not corrected in this pass (PROGRESS.md was only appended to). Each was
checked against the tree on 2026-10-19:

- 156 of the 157 distinct commit hashes in it predate the 2026-08-23 history
  rewrite and no longer resolve (41 more across 13 files in
  `docs/superpowers/`). Nothing in the file says so.
- Cross-cutting decisions quotes `requires-python = ">=3.12,<3.14"`; the cap
  was dropped at publication.
- The `pixi run typecheck` gotcha still leads with "46 pre-existing errors";
  the count is 23.
- Gotchas place `split_imports` and `rename_venv`'s `pyvenv.cfg` rewrite in
  `src/veny/cli.py`, and `run_import_check_in_venv` there too; they are in
  `classify.py`, `cache_search.py` and `verify.py`.
- "the five test files that reference `veny.<name>`" — two remain.
- `known_bad_imports` gotcha: "`process_import` checks `options.stdlib`"
  — `Options` is gone.
- `Options.also_needs` "(in `src/veny/cli.py`)" — it is
  `settings.DEFAULT_ALSO_NEEDS`.
- "mypy is not gated anywhere" says "The pre-commit hook still runs mypy on
  changed files". The hook runs `mypy .` on the whole tree, and no hook is
  installed at all.
- "The 4b wiring index goes stale…" still says 4c is the first phase that
  can invalidate it; 4c did, and the 4b index's own header says SUPERSEDED.
- "`rename_venv` loops over a single-element tuple" is listed as open; the
  loop is already gone.

### Test-environment gotcha

The live interpreter-probe tests —
`tests/test_alias_index.py::test_probe_of_the_running_interpreter_reports_its_own_version`
and
`tests/test_cli_entry_point.py::test_build_alias_index_reads_this_runs_own_directory_and_interpreter`
— run a real `packages_distributions()` subprocess under a 10 s timeout.
On a host at load average 7–11 on 4 CPUs they timed out four times across
this pass's gate runs, all unrelated to the change under test, and more often
under `pytest --cov`, which traces the child process too. A re-run passed
each time. Treat a lone failure of these two, with "timed out after 10.0
seconds" in the captured log, as load, and re-run before investigating.
