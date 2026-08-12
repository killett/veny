# PROGRESS

## Current work

**Topic:** Replace the hardcoded standard-library list in `veny.py` with a
derived `StdlibIndex` resolver.

- Design doc: `docs/superpowers/specs/2026-08-12-stdlib-index-design.md`
  (approved 2026-08-12)
- Implementation plan: not yet written
- Task tracker: not yet created

**Next action:** write the implementation plan from the approved design doc.

## Cross-cutting decisions

- **Standard-library membership is a property of the *target* interpreter,**
  not of the interpreter running veny. `options.python_command` is resolved
  early (`veny.py:2410`), before any import analysis, so the target can be
  probed without a virtual environment. Decided 2026-08-12.
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

## Deferred items

- `univ_defs.py` is 9,711 lines and `veny.py` is 6,320 lines. Both are overdue
  for splitting. Not in scope for the stdlib work.
- `known_bad_imports` retains six project-specific local module names,
  hardcoded. If that list grows, move it to a config file under
  `options.my_dir`.
- Full rework of the `split_imports` classification pipeline (module aliases,
  `also_needs`, installed/uninstalled) was considered and deferred — too large
  a blast radius for a codebase with no test suite yet.
- The repository had no `tests/` directory before this work. The stdlib work
  creates the first tests; broader coverage remains open.

## Open questions

- None currently blocking.
