# PROGRESS

## Current work

**Topic:** Replace the hardcoded module-alias table in `veny.py` with a derived
`AliasIndex` resolver.

- Design doc: `docs/superpowers/specs/2026-08-12-module-alias-resolver-design.md`
  (approved 2026-08-12)
- Implementation plan: not yet written

**Next action:** write the implementation plan from the approved design.

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
  `veny.py` / `univ_defs.py` errors (1171 ruff, 158 mypy as of 2026-08-12).
  Verify new work with commands scoped to the files you touched.
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

- `univ_defs.py` is 9,711 lines and `veny.py` is 5,427 lines (down from 6,320
  before this plan removed the hardcoded stdlib list). Both are overdue for
  splitting. Not in scope for the stdlib work.
- `known_bad_imports` retains six project-specific local module names,
  hardcoded. If that list grows, move it to a config file under
  `options.my_dir`.
- `also_needs` (`veny.py:120`) maps a package to further packages it needs. It
  is a different relation from the import-to-package aliases and is explicitly
  out of scope for the AliasIndex design; it remains hardcoded and deferred.
  (The module-alias half of this formerly-deferred item became active work on
  2026-08-12 — see Current work.)
- The repository had no `tests/` directory before this work. The stdlib work
  creates the first tests; broader coverage remains open.
- `univ_defs.to_jsonable` has no handler for `StdlibIndex`, so
  `save_options_to_json` serializes `options.stdlib` via `repr()` as a plain
  string rather than structured data. Nothing raises today because every
  current caller of `load_last_used_options` reads only `.venv_dir` /
  `.venv_python` off the restored options — but if a restored `options.stdlib`
  were ever used for membership testing, the `repr()` string would silently
  do substring matching instead of the real lookup (`"ma" in restored` is
  `True` because the string representation contains "ma" somewhere), giving
  wrong stdlib classifications with no error. Fix by adding a `to_jsonable`
  handler for `StdlibIndex` before any caller starts reading other fields off
  restored options.

## Open questions

- None currently blocking.
