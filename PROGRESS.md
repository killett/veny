# PROGRESS

## Current work

**Topic:** Module-alias resolver — complete. Replaced the 1,219-line
hardcoded import-name-to-pip-name table in `veny.py` with `alias_index.py`
(data model, override/cache stores, target-interpreter probe, resolution
chain) and `pypi_client.py` (confirms a project provides an import name by
reading the wheel's zip central directory over an HTTP range request), plus
`veny.resolve_and_verify` (installs ranked candidates and keeps whichever
actually imports).

- Design doc: `docs/superpowers/specs/2026-08-12-module-alias-resolver-design.md`
  (approved 2026-08-12)
- Implementation plan: `docs/superpowers/plans/2026-08-12-module-alias-resolver.md`
  (8 tasks plus a Task 9 whole-branch review pass, all executed on branch
  `alias-index`, 30 commits)
- Task 9 brief / report:
  `.superpowers/sdd/2026-08-12-module-alias-resolver/task-9-brief.md`,
  `.superpowers/sdd/2026-08-12-module-alias-resolver/task-9-report.md`
- Task tracker: `docs/superpowers/plans/2026-08-12-module-alias-resolver.md.tasks.json`

Outcome, verified: `veny.py` 5,475 → 4,646 lines; its `ruff check
veny.py --statistics` count 624 → 302; 137 tests where the repo had 23
before this plan.

Task 9 closed the final review's three Critical and five Important
findings. The consequential one: `resolve_and_verify` had been built,
tested and never called from production, so the cache was never written
and two of the five evidence tiers were unreachable. It is now wired into
`setup_virtualenv` via `verify_and_repair_imports`, which confirms what
really imported and repairs what did not. See the Task 9 report for the
wiring rationale and for two Minors deliberately left unfixed.

**Next action:** fix `find_match_dir_in_cache` — it splits venv folder names
on `-`, which cannot survive a hyphenated pip name (see Deferred items).
The old hardcoded table only ever produced 21 curated names, so this bug
was latent; AliasIndex can now resolve arbitrary PyPI distribution names,
which widens the exposure to all of them. Strongest candidate on the
deferred list.

**Previous topic (complete):** the `StdlibIndex` resolver.

- Design doc: `docs/superpowers/specs/2026-08-12-stdlib-index-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-12-stdlib-index.md`
  (7 tasks, all executed on branch `stdlib-index`)
- Task tracker: `docs/superpowers/plans/2026-08-12-stdlib-index.md.tasks.json`

## Cross-cutting decisions

- **Standard-library membership is a property of the *target* interpreter,**
  not of the interpreter running veny. `options.python_command` is resolved
  early in `main()` (`veny.py:1478`), before any import analysis, so the
  target can be probed without a virtual environment. Decided 2026-08-12.
- **No third-party dependency may be required to run veny.** veny is a
  bootstrapping tool that must work on a bare interpreter, so packages such as
  `stdlib_list` are ruled out on principle, not on preference. Decided
  2026-08-12.
- **Being wrong toward "skip the install" is worse than being wrong toward
  "attempt the install."** A wrong skip fails at the user's runtime, after
  veny reports success; a wrong install attempt fails loudly at install time.
  This asymmetry decided against union-across-versions stdlib lists.
  Decided 2026-08-12.
- **`requires-python = ">=3.12,<3.14"`,** so `sys.stdlib_module_names`
  (Python 3.10+) is unconditionally available. No version guards needed for
  it in our own code.

## Gotchas

- A defect that lives in the **seam between two tasks** is invisible to
  per-task review, because each task is individually correct. Task 6 built
  `resolve_and_verify` and tested it; Task 8 wired resolution into
  `split_imports`; nobody joined them, so the attempt loop had no production
  caller through 113 green tests and a review of every task. Where two pieces
  are meant to meet, write a test of the join itself (see
  `test_setup_virtualenv_verifies_every_import_before_reporting_success`),
  and be suspicious of any parameter or function that no production code
  passes or calls (`build(offline=True)` was the same class of gap).
- A check that widens what counts as a pass fails **open**. The bulk venv check
  went from "this exact import name must import" to "any top-level name of the
  distribution may import", which passes `setuptools` on `_distutils_hack` and
  passes a wrongly resolved pip name on whatever it does provide. When
  loosening a check to serve a new case (`--reqs` records carry pip spellings),
  restrict the loosening to that case rather than applying it to everything —
  `veny.source_import_names()` is what makes that distinction.
- `sys.stdlib_module_names` lists **top-level names only** and is
  platform-independent — it includes `msvcrt` and `winreg` on Linux. Dotted
  imports must be normalized to their first component before lookup.
- CPython deliberately excludes `Lib/test` from `sys.stdlib_module_names`, so
  `test` does not count as standard library. A package named `test` exists on
  PyPI.
- `split_imports` in `veny.py` builds a real temporary virtual environment, so
  it cannot be unit tested directly. Pure logic must be extracted before it
  can be covered.
- The repository is a flat two-script layout (`veny.py` + `univ_defs.py`),
  not the `src/` package layout described in the global CLAUDE.md. New modules
  must travel alongside those two files.
- `pixi run lint` and `pixi run typecheck` fail repo-wide on pre-existing
  `veny.py` / `univ_defs.py` errors (850 ruff, 170 mypy as of 2026-08-12,
  post-alias-resolver). The pre-commit `mypy` hook is literally `mypy .`
  with `pass_filenames: false`, so it always checks the whole repo and
  **cannot pass** while this debt exists — it is not a gate a change can
  satisfy, only a check that must be scoped manually: use `mypy <files>`
  on what you touched. Same logic applies to `ruff`: for `veny.py` itself,
  gate on `ruff check veny.py --statistics` before/after, not the bare
  `pixi run lint`.
- **Never run pre-commit's `ruff`/`ruff-format` hooks against `veny.py`** —
  a trial run during the alias-resolver plan rewrote ~2,000 lines of its
  hand-aligned formatting. Its ruff count is now **302** (was 624; the
  deleted hardcoded alias table was itself ~322 duplicate-key violations).
- A malformed `~/veny/module_aliases.toml` override file is **fatal by
  design** — it raises `AliasOverrideError` and stops the run, rather than
  being skipped. Continuing would resolve import names contrary to what the
  user explicitly wrote in that file. Every other missing or unreadable
  input in the resolution chain (cache, PyPI, probe) degrades silently
  instead.
- Cache entries in `~/veny/module_aliases_cache.json` are tagged with the
  target interpreter's version and ignored under a different one. A "why
  did this re-resolve instead of hitting the cache?" question usually has
  this answer.
- Only `import_failed` rejections persist in the alias cache. `install_failed`
  is deliberately forgotten: a failed install can be a transient network
  blip, and persisting it would blacklist an otherwise-correct package
  forever.
- `alias_index.py` and `pypi_client.py` import nothing from `veny` or
  `univ_defs`; `pypi_client` also imports nothing from `alias_index`.
  `univ_defs.py` imports `alias_index`, never the reverse — same one-way
  dependency discipline as `stdlib_index.py`.
- **`files.pythonhosted.org` answers `501 Unsupported client range` to
  suffix (`bytes=-N`) Range requests.** Only absolute tail ranges computed
  from the wheel's declared size work. This made the entire PyPI tier of
  resolution inert while looking correct — 45 unit tests were green at the
  time because the fake fetcher used in tests honored suffix ranges. Only a
  live check against pypi.org in Task 4's fix round 1 caught it.
- The metadata fetch and the wheel-central-directory fetch use separate
  byte caps; an earlier draft shared one cap and truncated `grpcio`'s
  8.8 MB metadata as a result.
- `rank()`'s tie-break among PEP 503-equivalent spellings (e.g. `Foo-Bar`
  vs `foo_bar`) resolved at the same source is first-encountered order, not
  lexicographic. It is deterministic only because `resolve()` always feeds
  a fixed tier/mutation order — do not assume alphabetical output.
- Options files written before this branch hold bare strings where
  `options.aliases` now lives. `check_venv_dir`'s `issubset()` check fails
  once against such a file and rebuilds the venv a single time; it is
  self-healing after that one rebuild.
- The `to_jsonable` branch for `AliasIndex` (`univ_defs.py:5682`) is not
  tagged for round-trip, so a reloaded `options.aliases` comes back as a
  plain `dict`, not an `AliasIndex`. Nothing breaks today because no
  current reader resolves off a cached options object — but it is a latent
  `AttributeError` waiting for one that does.
- `scripts/review-package` can truncate large diffs mid-hunk. A reviewer
  that trusts its output without checking the tail against the working
  tree can sign off on a hunk it never actually saw.
- `.git/hooks/pre-commit` is not installed, so `git commit` does not run the
  hooks. Run `pixi run pre-commit run --files <paths>` by hand.
- veny's standard-library skips are silent for top-level imports: the
  `Skipping standard library import` debug line only fires inside
  `process_import`, which top-level imports bypass (`_enqueue_top_level_imports`
  and the used-imports loop in `find_imports_and_IO_in_script` both `continue`
  past stdlib names before `process_import` is ever called). Verify stdlib
  classification by a name's *absence* from the bad and uninstalled sets, not
  by that log line. Predates the stdlib_index plan.
- veny normalizes dotted imports (e.g. `xml.etree.ElementTree`) to their first
  component (`xml`) before any stdlib classification happens
  (`ImportFunctionCollector.visit_Import`), so a dotted name never appears
  verbatim in the logs — only its top-level component does.
- A `--justprint` run leaves `.veny_custom_modules_*.pkl` and a `logs/`
  directory in the working tree. Both are ignored as of 2026-08-12, along with
  `__pycache__/`, the tool caches, and `.pixi/`. Still prefer staging paths
  explicitly over `git add -A` after a run.
- `known_bad_imports` is **not** a usable escape hatch for a name that IS in
  `sys.stdlib_module_names`. `process_import` checks `options.stdlib` first
  and returns before `split_imports` ever consults `known_bad_imports`, so
  adding a genuine stdlib name to that set has no effect — blocking it
  requires a change in `stdlib_index.py` instead. The design doc's proposed
  remedy of "one entry in `known_bad_imports`" for the `test`-module edge
  case works only because `test` is deliberately excluded from
  `sys.stdlib_module_names` (see the gotcha above); it does not generalize to
  any name that CPython actually reports as standard library.

## Deferred items

- `univ_defs.py` is 9,734 lines and `veny.py` is 4,379 lines (down from
  5,475 before the alias-resolver plan removed the hardcoded alias table,
  and from 6,320 before the stdlib plan before that removed the hardcoded
  stdlib list). Both are overdue for splitting.
- `alias_index.py` is 732 lines, accepted over the plan's ~600-line split
  target by controller ruling (no further split this plan; see the ledger's
  Task 5b entry — the byte-identical move was verified symbol-by-symbol).
  `AliasCache` (~170 lines) and the interpreter probe / `_running_tag`
  (~95 lines) are genuinely separable seams — self-contained, coupled to
  the resolution logic only through constructor injection — for a future
  `alias_cache.py` / `interpreter_probe.py` split.
- **`find_match_dir_in_cache` splits venv folder names on `-`,** which
  cannot survive a hyphenated pip name. Predates this plan, but the plan
  widens its exposure: the old hardcoded table produced only 21 curated
  pip names, so the bug was effectively latent; `AliasIndex` can resolve
  any PyPI distribution name, many of which are hyphenated. Strongest
  candidate for the next session (see Current work).
- `known_bad_imports` retains six project-specific local module names,
  hardcoded. If that list grows, move it to a config file under
  `options.my_dir`.
- `also_needs` (`veny.py:120`) maps a package to further packages it needs.
  It is a different relation from the import-to-package aliases and was
  explicitly out of scope for the AliasIndex design; it remains hardcoded
  and deferred. (The module-alias half of this formerly-deferred item is
  now done — see the completed alias-resolver plan under Current work.
  `also_needs` itself was never part of that plan and stays open.)
- The repository had no `tests/` directory before the stdlib work. Coverage
  now stands at 137 tests (`tests/test_alias_index.py`,
  `tests/test_pypi_client.py`, `tests/test_split_imports.py`,
  `tests/test_stdlib_index.py`); broader coverage of `veny.py` /
  `univ_defs.py` beyond what these plans touched remains open.
- `univ_defs.to_jsonable` still has no handler for `StdlibIndex` — this gap
  is now StdlibIndex-only; `AliasIndex` got its own handler
  (`univ_defs.py:5682`) during the alias-resolver plan, so `options.aliases`
  no longer falls through to `repr()`. The `StdlibIndex` mechanism of harm
  is unchanged: `save_options_to_json` still serializes `options.stdlib` via
  `repr()` as a plain string, and every current caller of
  `load_last_used_options` reads only `.venv_dir` / `.venv_python` off the
  restored options, so nothing raises today — but if a restored
  `options.stdlib` were ever used for membership testing, the `repr()`
  string would silently do substring matching instead of the real lookup
  (`"ma" in restored` is `True` because the string representation contains
  "ma" somewhere), giving wrong stdlib classifications with no error. Fix by
  adding a `to_jsonable` handler for `StdlibIndex`, mirroring the
  `AliasIndex` one, before any caller starts reading other fields off
  restored options. (`AliasIndex`'s new handler has its own gap — it is not
  tagged for round-trip, so a reloaded `options.aliases` comes back as a
  plain `dict` rather than an `AliasIndex` — see Gotchas.)
- Smaller items carried from the alias-resolver ledger, not worth their own
  paragraph: unused `_CONNECT_TIMEOUT`; a `.`-prefixed zip member yields
  `"."` as a top-level name; single-file extension modules (`.so`/`.pyd`)
  are never confirmed, a fail-closed false negative; the `https://` prefix
  check is case-sensitive; one non-`https://` distribution entry fails
  resolution for the whole project rather than just that entry; a wheel
  smaller than the first read window still triggers a byte-identical second
  request; `isinstance(size, int)` accepts `bool`, so a `"size": true`
  payload yields a 1-byte range; logging goes through the root logger
  instead of `logging.getLogger(__name__)`; `AliasCache._save()` is not an
  atomic write (no temp-file-plus-rename); `mutations()` has no direct
  test; the `py`-prefix name variant is not dash-normalized like its three
  siblings; `build()` spawns the interpreter probe before validating the
  override file, so a malformed override is discovered later than it could
  be; `--reqs` may produce duplicate records when the resolve loop and
  `requirement_records` disagree on `pip_name`.

## Open questions

- None currently blocking.
