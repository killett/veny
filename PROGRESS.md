# PROGRESS

## Current work

**Topic:** Re-architecting veny. Four requested changes — split what was, at
the time this program was scoped, the 6,020-line `src/veny/cli.py`, retire
the 48-attribute `Options` god object, move from
`pip` to `uv`, and add unit tests wherever they can be meaningful — are
sequenced as one program of four phases, because extracting a module requires
deciding what it receives instead of `options`, and the `uv` migration deletes
code that would otherwise be organized and tested for nothing. A rewrite was
considered and rejected: five modules are already cleanly extracted and tested
(~1,975 lines), and a restart loses the undocumented half of this file's
gotchas ledger.

- Design doc: `docs/superpowers/specs/2026-08-15-veny-rearchitecture-design.md`
  (approved 2026-08-15). Fixes module boundaries and ownership only; internals
  and task breakdown belong to the per-phase plans.
- Implementation plans, one per phase — **except phase 3, which is a sequence
  of five.** Thirteen modules out of a 4,143-line `cli.py`, each extraction
  carrying its own state decomposition and tests, is past what one plan can
  specify without placeholders; the design doc already says phases 3 and 4 are
  "sequenced module by module in their plans". Ordered leaf-first so each lands
  on already-extracted foundations:

  | Plan | Modules | ~Lines |
  |---|---|---|
  | **3a** `docs/superpowers/plans/2026-08-16-analysis-foundation.md` (executed, complete) | `analysis/literals.py`, `analysis/custom_modules.py`, `settings.py` | 430 |
  | **3b** `docs/superpowers/plans/2026-08-16-analysis-imports-and-call-graph.md` (written, not executed) | `analysis/imports.py`, `call_graph.py`, `scan.py`, plus `analysis/scan_state.py` | 1,100 |
  | 3c (not written) | `classify.py`, `environment.py` | 600 |
  | 3d (not written) | `verify.py`, `cache_search.py`, `last_used.py` | 1,100 |
  | 3e (not written) | `pipeline.py`, `cli.py` slimming, `--full` deletion, final `Options` drain | 450 |

  Phases 1 and 2 are complete and merged to `main`.

**Next action:** execute plan 3b, `docs/superpowers/plans/2026-08-16-analysis-imports-and-call-graph.md`,
on branch `analysis-imports-call-graph` (already created off `main` @ `3215df5`;
the plan and its `.tasks.json` are committed there as `e4f79ea`, the only commit
on the branch). Its seven tasks are ready and **none has been implemented**. The
plan opens with a "Starting state" section written for a session that does not
have the authoring context — read it first. Two things in it are worth knowing
before you begin: the task order is deliberately *tests before moves*, because
the call-graph half of the neighbourhood (`build_call_graph`,
`collect_used_imports`, `_analyze_module`, `split_function_name`, `FunctionInfo`,
`ModuleInfo`) has zero test coverage today; and `ImportScan` is forced rather
than chosen, because once those symbols live under `analysis/` they cannot name
`Options` without importing `cli`, which `tests/test_layering.py` fails on.

Plan 3b also settles three things the approved design left open or wrong, all
recorded in its own "Three things this plan settles" section: `ImportScan` must
carry `seen_stdlib_imports` or `warn_about_system_packages` silently stops
firing; `analysis/` receives stdlib membership as an injected
`is_stdlib: Callable[[str], bool]` (owner's decision, 2026-08-16) rather than a
`StdlibIndex`, which satisfies the design's wording with bit-identical
behaviour; and the design's "Pure AST in, names out" claim is not true today —
`_register_constant_path_for_module` and `process_import` both touch the
filesystem during a scan — and 3b does not make it true.

Phase 3a is merged to `main` at `3215df5`. It landed six tasks (a task gained mid-execution,
numbered 2b, between the `/`-operator fix and the `settings.py`/`custom_modules.py`
extraction), all committed —
`a20224e` (extract `analysis/literals.py`, byte-identical move, 7 tests),
`598e690` (fix the `/` operator: a bare `Path(...)` constructor branch in
`_safe_eval_node`, 3 tests), `94c8a5d`/`d88e3fc` (Task 2b, added mid-execution:
gate `is_pathlib_ctor`'s alias set correctly, 2 tests), `41f5ef1` (create
`settings.py`, extract `analysis/custom_modules.py`), `728c62d`/`79cefc7`
(`tests/test_layering.py`, 3 tests enforcing the one-way import direction),
plus `dd811d1` recording Task 2b in the plan file, `4577189`/`73bdca0`/`4840886`/
`c7b9d90`/`0fe47b1` closing the whole-branch review's findings, and `2c62f5b`
correcting a false test-count claim in the plan's own Task 1. Gates on `main`: `pixi
run test` 283 passed; `ruff check .` zero; `ruff format --check .` all 33
files formatted; `pixi run typecheck` 37 errors (at the ceiling, not a
regression — see Gotchas); `pixi run smoke` green (network was available, so
nothing was skipped). `src/veny/cli.py` is now **3,707 lines** (was 4,143 at
the start of 3a); the three new/grown files measure `analysis/literals.py`
229, `analysis/custom_modules.py` 258, `settings.py` 23. A live run
(`pixi run veny --no-cache`, a script calling `yaml.safe_load`) built a fresh
venv and printed `{'i': 9}`, confirming custom-module discovery and the
`/`-operator fix both work through `main()`, not just under the unit suite.

The rest of this block is phase 2's closing state, kept because it records
what "green" currently means. The BLOCKING live-run
defect that used to be listed here is fixed — see Deferred items below for
the fix commit and verification. Task 9 (2026-08-16) closed a second
live-run-only defect the 265-test suite could not see: `venv_build_interpreter()`
handed uv a bare `"python3"`, which `uv venv --python` resolves through its
own interpreter discovery order rather than PATH, silently building against a
different Python than the one imports were classified against — see the
Gotchas entry (`uv venv --python <bare name> does not mean...`) for the fix
and live verification. Phase 2's gates (`pixi run test` 266 passed,
`ruff check .` zero, `ruff format --check .` all formatted, `pixi run
typecheck` 37 errors, `pixi run smoke` green) are all green, and
`src/veny/cli.py` is 4,143 lines (was 4,362 after phase 1, 6,020 before
phase 1). A live run (`pixi run veny --no-cache`, importing `yaml`) now
succeeds end to end: it resolves `yaml` to `PyYAML`, builds a fresh venv
under `~/veny/` with a resolved absolute-path interpreter, installs with uv,
prints the parsed result, and drops the venv folder's `failed-` prefix, with
the manifest's `interpreter_tag` agreeing with the folder name's `pyX.Y`.

Phase order and expected size: (1) delete the visitor block, ~1,600 lines,
complete on branch `delete-visitor-block`; (2) migrate to `uv` with veny
keeping its own venv cache, complete on branch `uv-migration`; (3) extract the
survivors into the module layout in the design doc; (4) drain `Options` into
frozen per-subsystem dataclasses, carried by the phase 3 extractions rather
than done separately. Phases 1 and 2 are independent of the architecture and
land first; the original combined estimate for both was 6,020 down to
roughly 3,870 lines before any extraction begins. Phase 1 landed at 4,362
lines and phase 2 landed at 4,143 — 219 lines lighter, short of the original
combined estimate, so phase 3's extraction has more to move than that
estimate assumed.

**Previous topic (complete):** Replacing veny's rc-file shell alias with a packaged console-script
entry point. veny installs itself today by appending `alias veny="python3
~/veny.py"` to a shell configuration file, which costs four shell dialects plus
rc-file discovery, is invisible to scripts and cron, and cannot guarantee the
interpreter it names satisfies `requires-python >=3.12,<3.14` or has emmykit
installed. The repository moves to a `src/veny/` package (`veny.py` → `cli.py`
verbatim, minus the alias code), gains a `[build-system]` and
`[project.scripts] veny = "veny.cli:main"`, and is installed with
`uv tool install`. A PATH symlink (the `clean-caches.sh --install` approach) was
considered and rejected as insufficient — it delegates interpreter choice to
`#!/usr/bin/env python3`, which resolves emmykit and the Python floor by luck.

- Design doc: `docs/superpowers/specs/2026-08-15-packaged-entry-point-design.md`
  (approved 2026-08-15)
- Implementation plan: `docs/superpowers/plans/2026-08-15-packaged-entry-point.md`
  (7 tasks: 1, 2, 3, 4a, 4, 5, 6)
- Task tracker: `docs/superpowers/plans/2026-08-15-packaged-entry-point.md.tasks.json`

**Next action:** none on this plan. All 7 tasks are complete on branch
`packaged-entry-point` (14 commits), the whole-branch review is clean, and the
branch is ready to merge. Gates: 257 passed; `ruff check src/veny/cli.py
--statistics` 294 (was 299 for `veny.py`); `mypy src/veny/cli.py
src/veny/json_types.py` 27 (was 28); `pixi run smoke` green, including the
mutation check that proves its exit-status assertion can fail. The outstanding
follow-up is the emmykit usage-audit prompt in `docs/prompts/`, which is
written but has not been run in the emmykit repository — see Deferred items.

Tasks 1-6 delivered: the six modules live in `src/veny/`, the alias installer and its
four shell dialects are deleted, `pyproject.toml` declares a hatchling build
backend and `[project.scripts] veny = "veny.cli:main"`, and `pixi run smoke`
proves the installed console script propagates a wrapped script's exit
status. Task 4a, inserted mid-plan after Task 4's smoke check caught it,
fixed a pre-existing defect where `main()` discarded the subprocess return
code on all three script-running paths, so `veny` exited 0 no matter how the
wrapped script exited; `main()` is now `-> int`, captures `result.returncode`
on all three paths and returns it after existing cleanup, and
`src/veny/__main__.py` is `sys.exit(main())`.

**Earlier topic (complete):** Replaced `univ_defs.py` with the published `emmykit` package —
design approved 2026-08-14, implementation plan executed on branch
`emmykit-migration`. `veny.py` imported `univ_defs as ud` at 93 call sites
(7 more in tests); all 41 symbols it used existed in emmykit 0.3.4 with
identical signatures. The swap deleted the 9,757-line local file, renamed
the alias `ud` → `ek`, dropped the five helper scripts veny wrote but never
ran, and moved veny's own serialization out of the utility library and into
the JSON type registry emmykit gained in 0.4.0.

- Design doc: `docs/superpowers/specs/2026-08-14-emmykit-migration-design.md`
  (approved 2026-08-14)
- Cross-repo prompt (emmykit): `docs/prompts/2026-08-14-emmykit-json-type-registry.md`
  — adds the JSON type registry and removes the embedded script constants;
  ships as emmykit 0.4.0
- Cross-repo prompt (utilities): `docs/prompts/2026-08-14-utilities-adopt-emmykit-scripts.md`
  — adopts the five standalone scripts as real files
- Implementation plan: `docs/superpowers/plans/2026-08-14-emmykit-migration.md`
  (8 tasks, 0-7; Task 0 is the external emmykit release and blocks Tasks 3-7)
- Task tracker: `docs/superpowers/plans/2026-08-14-emmykit-migration.md.tasks.json`

The branch was held back until emmykit 0.4.0 existed, so that no
known-degraded state reached `main`.

**Outcome:** nothing outstanding on that plan. Tasks 0–7 are all complete and branch
`emmykit-migration` is merged into `main` (14 commits, deleted after merge).
`pyproject.toml` and `pixi.toml` pin `emmykit>=0.4.0,<1.0` (installed:
0.4.0); the `[pypi-exclude-newer]` override that exempts emmykit from the
workspace's 7-day cooldown stays in `pixi.toml` — without it the environment
silently reverts to 0.3.4 on the next solve. Full suite: 252 passed. Scoped
gates: 299 ruff findings in `veny.py`, 28 mypy errors across `veny.py` +
`veny_json_types.py`. A live run against a real script (installing PyYAML
into a fresh/reused venv) succeeded end to end, left the helper scripts in
`~/veny` untouched, and wrote an options JSON carrying no `univ_defs` key and
no `ResolvedImport(` repr strings.

A follow-up on 2026-08-15 dropped veny's `Options.args` re-declaration and
the two `assert options.args is not None` lines it forced, aligning veny with
the empty-`Namespace` default emmykit chose deliberately — see the gotcha
below. That is what moved the gates from 301/30 to 299/28 and the suite from
250 to 252.

Of the two cross-repo prompts, the emmykit one
(`docs/prompts/2026-08-14-emmykit-json-type-registry.md`) is done — 0.4.0 is
released and installed. The utilities one
(`docs/prompts/2026-08-14-utilities-adopt-emmykit-scripts.md`) is still
outstanding; see Deferred items.

**Earlier topic (complete):** Venv-cache matching — design approved
2026-08-14, plan complete
on branch `venv-cache`. Cached virtual environments are matched from a folder
name that splits on `-` (so no hyphenated pip name survives) and from
`requirements.txt`, which is pip's input rather than a record of the venv.
Replace both with a versioned `veny_manifest.json` inside each venv, a
correctly encoded folder name used only as a cheap prefilter, and one
comparison key — the PEP 503 normalized pip name — at every layer. Also
fixes the interpreter mismatch where the venv is built with `sys.executable`
while imports are classified against `options.python_command`.

- Design doc: `docs/superpowers/specs/2026-08-14-venv-cache-matching-design.md`
  (approved 2026-08-14)
- Implementation plan: `docs/superpowers/plans/2026-08-14-venv-cache-matching.md`
  (11 tasks, executed on branch `venv-cache`)
- Task tracker: `docs/superpowers/plans/2026-08-14-venv-cache-matching.md.tasks.json`
- Task briefs / reports: `.superpowers/sdd/2026-08-14-venv-cache-matching/`
  (not checked in — `.superpowers/` is gitignored)

Tasks 1–10 complete: folder naming, the manifest data model, the version
comparator, the match predicate, building the venv with the classified
interpreter, the `rename_venv` helper, writing `veny_manifest.json` after
install and repair (renaming the folder first if repairs changed the package
set), matching cached venvs from the manifest, judging every cached venv —
last-used included — by its manifest, and (Task 10) deleting the
name-building and requirements-comparison code the manifest replaced
(`pretty_packages_list`, `options.pretty_list`, `options.pretty_requirements`)
plus documenting the manifest and folder-name format in README.md.

Task 11 (verification, no code changes) is complete. Mutation-checked all
three guards named in the brief — each deletion produced a real test
failure, each restoration left `git diff` empty and the full suite green
(223 passed):

- `venv_cache.satisfies`'s `manifest.interpreter_tag != interpreter_tag`
  early return: deleting it failed
  `test_satisfies_rejects_a_different_interpreter`.
- `venv_cache.version_satisfies`'s `installed is None` fail-closed term:
  deleting it failed `test_version_satisfies_fails_closed[None->=1.0]` and
  `test_satisfies_rejects_a_pin_when_the_installed_version_is_unknown`.
- `veny.record_venv_state`'s rename branch: deleting it failed
  `test_record_venv_state_renames_before_writing_the_manifest`.

Live two-run verification against `ruamel.yaml` (pip name `ruamel-yaml`,
the brief's chosen hyphenated-pip-name package) confirmed the whole path
end to end:

- Run 1 built `~/veny/myenv-py3.13-20260814-201804-ruamel-yaml`, printed
  `ok ruamel.yaml`, and wrote a `veny_manifest.json` with
  `schema_version: 1`, `interpreter_tag: "3.13"`, and a package record
  `pip_name: "ruamel-yaml"`, `installed_version: "0.19.1"`.
- Run 2 logged `Using existing virtual environment:
  /home/claudeuser/veny/myenv-py3.13-20260814-201804-ruamel-yaml` — the
  identical folder — and printed `ok ruamel.yaml` again.
- `ls ~/veny` before vs. after the two runs differs by exactly one venv
  folder (`myenv-py3.13-20260814-201804-ruamel-yaml`), plus expected
  incidental files (`module_aliases_cache.json`, a `pip_list_*.txt`, and
  veny's own `test` probe dir — none are second venv folders).

One environmental blocker required a workaround, recorded as a gotcha
below: the alias resolver could not discover `ruamel` → `ruamel-yaml` on
its own (a pre-existing, unrelated gap in `alias_index.py`'s mutation
generator, not in this plan's code), so a `module_aliases.toml` override
was used to supply that mapping. This is a legitimate, documented
mechanism (`AliasIndex.resolve`'s OVERRIDE tier) and does not touch any
code this plan changed.

Full verification detail, including all captured command output, is in
`.superpowers/sdd/2026-08-14-venv-cache-matching/task-11-report.md` (not
checked in — `.superpowers/` is gitignored).

A subsequent whole-branch review of `venv-cache` found 4 Important and 6
Minor findings; all 10 were fixed in one wave (2026-08-14), including the
most consequential one: nothing in the 223-test suite asserted a cached venv
is ever *accepted* -- `check_venv_dir`'s `return True` and all of
`find_match_dir_in_cache` were unreached, so `def check_venv_dir(...):
return False` silently disabled every venv reuse and still passed the whole
suite. Full detail, including load-bearing mutation evidence for every
fix, is in
`.superpowers/sdd/2026-08-14-venv-cache-matching/final-fix-report.md` (not
checked in). Two reviewer findings (interpreter_tag reading
options.stdlib.python_version rather than probing the build interpreter;
satisfies() running twice on the winning candidate) were deliberately left
unfixed, escalated to the human partner as needing a design decision.

Nothing outstanding on that plan: tasks 1–11 all complete, the whole-branch
review's findings all fixed, merged to `main` at `66d60bf`.

**Earlier still (complete):** Module-alias resolver. Replaced the 1,219-line
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

**Earliest topic (complete):** the `StdlibIndex` resolver.

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
  2026-08-12. **Superseded 2026-08-14** by the emmykit migration: veny now
  requires `emmykit>=0.4.0` and exits with an install message when it is
  absent. The original decision was argued against `stdlib_list`, an external
  package supplying data veny could derive for itself; emmykit is the utility
  layer veny is already built on, first-party, and stdlib-only in its base.
  The principle still holds for everything else — no *further* runtime
  dependency may be added without the same kind of argument.
- **Being wrong toward "skip the install" is worse than being wrong toward
  "attempt the install."** A wrong skip fails at the user's runtime, after
  veny reports success; a wrong install attempt fails loudly at install time.
  This asymmetry decided against union-across-versions stdlib lists.
  Decided 2026-08-12.
- **`requires-python = ">=3.12,<3.14"`,** so `sys.stdlib_module_names`
  (Python 3.10+) is unconditionally available. No version guards needed for
  it in our own code.

## Gotchas

- **`safe_eval` used to silently drop every `sys.path` entry built with
  pathlib's `/` operator.** Fixed 2026-08-16 by plan 3a's Task 2, commit
  `598e690`; the code now lives in `src/veny/analysis/literals.py`, not
  `cli.py`. `safe_eval`'s docstring listed "the `/` operator for joining
  pathlib Paths" as supported and `_safe_eval_node` opened with a dedicated
  `ast.BinOp`/`ast.Div` branch for it — but there was **no branch for a bare
  `Path(...)` constructor**, only for `Path(...).resolve()`, `.absolute()` and
  `.joinpath(...)`. So evaluating the left operand fell through to
  `raise ValueError(f"Unsupported call: ...")`, which propagated out of the
  `Div` branch and was swallowed by `safe_eval`'s `except`, yielding `None`.
  Measured before the fix: `Path("a").joinpath("b", "c")` → `"a/b/c"` but
  `Path("a") / "b"` → `None` and `Path("a")` → `None`. Reproduced through
  `SysPathVisitor`: given three `sys.path` lines, it found `{'/opt/plain',
  '/opt/libs/other'}` and dropped the `/`-built one entirely. The symptom was
  invisible — veny simply never scanned that directory for custom modules, so
  an import satisfied there was reported as a bad import or sent to PyPI to be
  installed. `/` is the more idiomatic pathlib form than `.joinpath()`. Found
  by probing the evaluator while planning its extraction, not by any test.
  The fix is a bare `Path(...)` constructor branch added to
  `_safe_eval_node`, covered by 3 tests.
- **`is_pathlib_ctor` ignored its own alias set, so a locally-defined `class
  Path` with no pathlib import anywhere had its constructor calls evaluated as
  filesystem paths.** Found by Task 1's own characterization tests (Task 2b,
  commits `94c8a5d`/`d88e3fc`, 2026-08-16), not by a review — one of the eight
  expected values that Task 1 claimed were "measured against the current
  implementation" was not:
  `test_an_unaliased_pathlib_name_is_not_evaluated` asserted
  `safe_eval('Path("a").joinpath("b")')` returns `None` with no alias set, but
  it actually returned `"a/b"`. Cause: `is_pathlib_ctor` read `if fn.id in
  allowed or fn.id in pathlib_aliases:`, and `allowed` always contains
  pathlib's own class names, so `pathlib_aliases` could only ever *add* names
  and never gate one — a script defining its own `Path` fed a bogus directory
  into veny's custom-module search. The first fix attempt over-corrected to
  `fn.id in pathlib_aliases and fn.id in allowed`, which broke every
  **renamed** import instead: `from pathlib import Path as P` yields the alias
  set `{"P"}`, and `P` can never be in `allowed`, because `allowed` holds
  pathlib's own class names while `pathlib_aliases` holds this module's local
  bindings — two different kinds of thing, and the regression from
  intersecting them was caught in review, not by the 279-test suite at the
  time. The landed fix is `if fn.id in pathlib_aliases:` alone: for a name
  already in the alias set this reproduces the original `or` form exactly (it
  short-circuited on alias membership before ever checking `allowed`); for a
  name outside it, it now correctly rejects. Any future edit that intersects
  `allowed` and `pathlib_aliases` will break renamed imports the same way.
- **A plan's stated "measured against the current implementation" is not
  evidence — re-measure before building on it.** Plan 3a made that claim for
  eight characterization-test expected values in Task 1; one was wrong (see
  the `is_pathlib_ctor` entry above), and the fix built to correct it was
  itself wrong in the opposite direction. Both defects were caught by review
  and by an implementer refusing to guess, not by the unit suite — the
  279-test suite at the time was green through both the original bug and the
  overcorrected regression. This cost two fix rounds in 3a and is expected to
  recur in 3b–3e, since those plans will make the same kind of claim about
  values they have not re-checked against the tree.
- **A test that stubs a subprocess proves your code calls the stub.** Phase 2
  shipped three separate regressions past a green 264-test suite, all of the
  same shape: every test stubs the `uv` subprocess, so nothing exercised the
  command lines veny actually builds. Each was caught by a live run instead —
  (1) `uv venv` refusing a non-empty directory broke *every* fresh build;
  (2) `uv venv --python python3` resolving to 3.12 where PATH's `python3` is
  3.13; (3) the same defect again in `split_imports`' probe venv, where a script
  importing `cgi` (stdlib in 3.12, removed in 3.13) was classified "installed"
  and then died at runtime. Make a live end-to-end run an acceptance criterion
  of any plan that touches subprocess invocation, and when phase 3c extracts
  `environment.py` as the sole owner of uv invocation, give it a live
  integration test rather than only argument-list assertions.
- **`pixi.toml`'s `[activation.env]` sets `PYTHONPATH = "src"`, which
  *overwrites* an inherited `PYTHONPATH`.** So copying `src/` elsewhere,
  mutating the copy and running `PYTHONPATH=/tmp/mut/src pixi run python -m
  pytest` silently tests `/workspace/src` and reports a false pass. This
  matters because mutation testing is this project's gate for whether a test
  can fail at all. Mutate the working tree in place and restore with
  `git checkout -- src/veny/cli.py` (never `git stash`), or inject the copy
  with `sys.path.insert(0, ...)` inside the process. Confirm which file was
  loaded with `pixi run python -c "import veny.cli as c; print(c.__file__)"`.
- veny's own types are serialized by `json_types.register_types()`, called
  at `src/veny/cli.py` module scope, not inside `main()`. Anything that imports veny --
  including every test -- gets production's serialization behaviour. If you move
  the call into `main()`, `save_options_to_json` will silently write
  `"ResolvedImport(...)"` repr strings for any consumer that does not go through
  `main()`, and no test will notice unless it runs in a subprocess.
- `alias_index.AliasIndex` is registered **encode-only** on purpose. It holds
  `installed` (probed from the target interpreter) and a live `pypi` client, so a
  decoder would return an index that reports nothing as installed while looking
  identical to a real one. It reloads as a plain dict by design.
- pixi's per-package cooldown override for a PyPI package is a
  `[pypi-exclude-newer]` table keyed by package name (`pixi.toml`'s
  `emmykit = "0d"`). The `[exclude-newer]` table the surrounding comment
  points at is not accepted for PyPI packages, and neither is the spelling
  `exclude-newer-package` (that one belongs to uv, and leaks through as a
  hint from pixi's bundled resolver). Getting the table name wrong does not
  reliably error: `pixi update` can just report "Lock-file was already
  up-to-date" and leave the old version pinned, so a silently-wrong spelling
  looks identical to success.
- `git stash` / `git stash pop` is unsafe for the same reason CLAUDE.md
  already warns off `git checkout <sha>` for investigative baselines:
  mid-task in this session, pre-commit's `ruff-format` hook rewrote test
  files in place while changes were stashed, and that rewrite then blocked
  `git stash pop`. Use `git worktree add` on a side path for any comparison
  against another commit or state instead of stashing.
- **`Options.args` defaults to an empty `argparse.Namespace`, not to `None`,
  and that is upstream's deliberate choice — do not "restore" the `| None`
  form.** emmykit inherited it from `univ_defs` commit `67e054a` (2026-04-04,
  "Fixed various issues raised by mypy"), which flipped all six
  `self.args: argparse.Namespace | None = None` declarations to
  `argparse.Namespace = argparse.Namespace()` and deleted the
  `assert options.args is not None  # to appease mypy` that the optional type
  had forced. veny re-declared `| None` anyway until 2026-08-15, which cost an
  incompatible-override error from mypy plus two more `assert options.args is
  not None` lines; dropping the re-declaration removed all three.
  The safety argument for `| None` does not survive contact with the code:
  `getattr(None, "flag", False)` and `getattr(Namespace(), "flag", False)`
  both return `False` without raising, and veny reads every flag through
  `getattr` with a default. Direct access (`options.args.alias`) raises
  `AttributeError` under either spelling. The one real difference is
  assignment — `options.args.last_used = True` fails on `None` and succeeds on
  an empty `Namespace` — which cannot arise today because `parse_arguments`
  runs first in `main()`.
- Recording nothing and recording forever are both wrong for a failure whose
  cause is environmental. veny keeps `import_unavailable` in a *separate
  in-memory* store: filtered for the rest of the run so the same unusable wheel
  is not re-downloaded, never written so the next run may try again. The
  separation is load-bearing — a shared store would be flushed to disk by the
  very next `confirm()` (`alias_index.AliasCache.session_rejections`).
- When a test double stands in for the function under audit, the seam behind it
  is unguarded. Patching `import_outcome_in_venv` in every repair test meant a
  mutation deleting its `report_providers=True` stayed green across 150 tests.
  If a double replaces X everywhere, one test must still exercise the real X.
- A passing check proves the **behaviour**, not the **attribution**. "The
  import works" is not "this package provided it": it may come from a transitive
  dependency while the record's own pip name resolved wrongly-but-installably.
  Before recording a durable fact about X, check that the evidence is about X.
  (`veny.confirm_if_attributable` — the cache outranks every tier except
  OVERRIDE on every later run, so an unattributed confirm is durable
  misinformation.)
- Before remembering a failure, ask whose fault it is. An import that fails
  because *this machine* lacks `libGL.so.1` says nothing about the package, and
  persisting it as a package rejection suppresses the correct package here
  forever — including after the user installs the system library. veny keeps
  machine-scoped failures (`import_unavailable`) in-session only and *reports*
  them, following `stdlib_index.NEEDS_SYSTEM_PACKAGE`. The evidence for the
  distinction is usually already in hand: the exception text.
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
- `split_imports` in `src/veny/cli.py` builds a real temporary virtual
  environment, so it cannot be unit tested directly. Pure logic must be
  extracted before it can be covered.
- The repository uses the `src/veny/` package layout as of 2026-08-15 (it was
  a flat script layout before that; `veny.py` is now `src/veny/cli.py` and
  `veny_json_types.py` is now `src/veny/json_types.py`). New modules go
  inside `src/veny/` and are imported with `from . import <name>`. Tests
  import them as `from veny import <name>`, and the five test files that
  reference `veny.<name>` throughout use `from veny import cli as veny` to
  keep those references working.
- **`pixi run lint` and `pixi run format` now pass repo-wide, and must stay
  that way.** As of 2026-08-15 `ruff check .` reports zero and
  `ruff format --check .` reports every file formatted. Both pre-commit ruff
  hooks run over every file with no `exclude`. This reverses the long-standing
  rule that `src/veny/cli.py` must never be formatted: the hand-aligned column
  style was retired on the owner's instruction, and `ruff format` rewrote
  ~3,200 lines of it in one go. Do not reintroduce hand-alignment — the
  formatter will simply undo it, producing noise in the next diff.
- **`pixi run typecheck` still cannot pass.** The pre-commit `mypy` hook is
  literally `mypy .` with `pass_filenames: false`, so it always checks the
  whole repo, and 46 pre-existing errors remain across `src/veny/cli.py` and
  `tests/test_split_imports.py` (down from 49 over the course of 2026-08-15's
  ruff cleanup and the pipreqs deletion). It is not a gate a change can
  satisfy, only a check to scope manually:
  use `mypy <files>` on what you touched, and confirm the whole-repo count has
  not risen.
- **`ruff format` also formats Python code blocks inside Markdown** in this
  version. A bare `ruff format .` rewrote 696 lines across eight design docs
  and plans, whose code blocks are a record of what the code looked like at
  approval time. `pyproject.toml`'s `[tool.ruff] extend-exclude = ["docs/"]`
  now prevents that; do not remove it. The pre-commit hooks were never at risk
  here — they carry `types: [python]`, so Markdown never reaches them.
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
- `alias_index.py` and `pypi_client.py` import nothing from `cli` or
  `json_types`; `pypi_client` also imports nothing from `alias_index`.
  `json_types.py` imports `alias_index` and `stdlib_index`, never
  `cli` — same one-way dependency discipline as `stdlib_index.py`.
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
- `scripts/review-package` can truncate large diffs mid-hunk. A reviewer
  that trusts its output without checking the tail against the working
  tree can sign off on a hunk it never actually saw.
- `.git/hooks/pre-commit` is not installed, so `git commit` does not run the
  hooks. Run `pixi run pre-commit run --files <paths>` by hand.
- veny's standard-library skips are silent for top-level imports: the
  `Skipping standard library import` debug line only fires inside
  `process_import`, which top-level imports bypass (`_enqueue_top_level_imports`
  and the used-imports loop in `find_imports_in_script` both `continue`
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

- `venv_cache.normalize_pip_name` duplicates `alias_index.normalize_pip_name`
  deliberately (one-way imports — `venv_cache.py` must not import `alias_index`
  the way `alias_index.py` must not import `veny`), and the two must be
  changed together.
- The folder name is a prefilter only, and a stale one costs a rebuild, which
  is why `record_venv_state` renames after repairs — the manifest is the
  source of truth, but a wrong folder name still causes a wasted match
  attempt before the manifest is even read.
- `version_satisfies` refuses every non-numeric version form (pre-releases,
  post-releases, dev releases, local version identifiers, epochs), so an
  installed pre-release always fails the match and forces a rebuild — this is
  fail-closed by design, not a bug to fix casually.
- `alias_index.mutations()` cannot discover a pip name that adds a suffix
  unrelated to case/separator changes, e.g. `ruamel` (the import) →
  `ruamel-yaml` (the pip name): its generated forms are only
  `dash-for-underscore`, `python-<name>`, `<name>-python`, `py<name>`, and
  the `py`-prefix strip. `ruamel-yaml` matches none of them, and there is
  no `SEED` entry for `ruamel`, so `AliasIndex.resolve("ruamel")` returns
  no candidates and `split_imports` falls back to using the bare import
  name as the pip name — which does not exist on PyPI and fails to
  install. Found live during Task 11's verification run, worked around
  with a `module_aliases.toml` override (`ruamel = "ruamel-yaml"`); not a
  bug in this plan's code, since `alias_index.py` belongs to the earlier
  module-alias-resolver plan. Left as a gap for that resolver, not fixed
  here.
- **Renaming a directory carries everything already written inside it,
  so a test asserting end-state file layout cannot distinguish "write then
  rename" from "rename then write."** `record_venv_state`'s test asserted
  `not (old_dir / MANIFEST_FILENAME).exists()` to pin that the manifest is
  written after the rename -- but `old_dir` no longer exists at all by that
  point either way, making the assertion vacuous, and swapping the two
  calls still leaves a valid manifest under `new_dir` regardless of order.
  When call order matters but produces identical end state, spy on the call
  itself (capture the argument a wrapped function was actually invoked
  with) rather than inspecting what's left on disk afterward.
- **A dict `.get()` lookup silently returns `None` for a spelling mismatch;
  it never raises, so the failure is invisible unless something asserts the
  positive case.** `manifest_for` and `wanted_packages` both looked up
  `options.extra_requirements` (user-typed spelling) by `record.pip_name`
  (however alias resolution happened to spell it) with no normalization,
  one line away from a versions dict that *was* keyed normalized. Same
  fix both places: build a normalized view of the dict once, look up by
  `normalize_pip_name` on both sides. Whenever two spellings of the same
  project name might meet at a dict boundary, that boundary needs
  `normalize_pip_name` on both the write side and the read side, not just
  one.
- **`uv venv` seeds no pip, so `options.venv_python` is the only interpreter
  in a veny environment.** There is no `bin/pip` to shell out to, by design
  (see README's "Cached environments have no pip"). A related, easy-to-miss
  fact: `uv venv`'s `pyvenv.cfg` carries only `home`, `implementation`, `uv`,
  `version_info` and `include-system-site-packages` — unlike stdlib `venv`,
  it records no path to the venv's own directory (stdlib `venv` writes a
  `command = ... -m venv <dir>` line). That absence is *why*
  `rename_venv`'s `pyvenv.cfg` rewrite still exists in `src/veny/cli.py`
  despite `uv venv` needing no such fix-up itself: the rewrite still matters
  for stdlib-built venvs already sitting in users' `~/veny` caches from
  before this migration, which do record their own path and would break on
  rename without it.
- **`uv venv` refuses to build into a directory that already exists and is
  non-empty.** Found live during phase 2 Task 7's Step 3
  (`pixi run veny --no-cache /tmp/veny-live.py`, 2026-08-16), because
  `setup_virtualenv` always creates the target directory
  (`Options.set_venv_dir`'s `mkdir`) and used to write `requirements.txt`
  into it (`write_requirements_file_with_extras`) before calling
  `create_venv` — stdlib `venv.create` tolerated that ordering, `uv venv`
  does not. **Fixed in Task 8** (2026-08-16): `create_venv` now runs before
  `write_requirements_file_with_extras`; see the Deferred-items entry above
  for the fix, its regression test, and mutation evidence. `--clear` /
  `UV_VENV_CLEAR=1` is not the fix — it deletes the directory's existing
  contents, which would erase `requirements.txt` before the install that
  reads it.
- **`uv venv --python <bare name>` does not mean "the `<bare name>` found on
  PATH."** Found live in Task 9, fixed 2026-08-16, commit `cc64b8b`.
  `venv_build_interpreter()`
  returned `options.python_command or sys.executable`, and `python_command`
  is the bare string `"python3"` from `ek.find_preferred_python_version()`.
  `python3 --version` on PATH and `python3 -m venv` (what veny built with
  before the uv migration) agreed with each other; `uv venv --python python3`
  resolved to a *different* interpreter on the same machine, through uv's own
  interpreter discovery order rather than a PATH lookup. Since
  `options.python_command` is also what stdlib and alias resolution were
  probed against, this silently built an environment for the wrong Python
  after classifying imports against a different one. Fixed by resolving the
  interpreter with `shutil.which()` inside `venv_build_interpreter()` before
  it reaches `create_venv` — chosen over resolving only inside `create_venv`
  because `venv_build_interpreter()`'s return value is also recorded as the
  manifest's `interpreter_path` field, where an absolute path is strictly
  more useful than a bare name. When `shutil.which()` finds nothing, the bare
  name is returned unchanged (today's pre-fix behaviour) and a warning is
  logged, since the invariant can no longer be guaranteed for that run. Test:
  `tests/test_uv_backend.py::test_create_venv_is_given_a_resolved_interpreter_path_not_a_bare_command`.
  Verified live: `pixi run veny --no-cache` against a script importing
  `yaml` built a venv whose `bin/python --version` matched `python3` on PATH
  (both 3.13.14, resolved through the pixi env's PATH order to
  `.pixi/envs/default/bin/python3`), and whose manifest `interpreter_tag`
  (`"3.13"`) agreed with the folder name's `py3.13` — before the fix, a
  reproduction with no veny involved showed `uv venv --python python3`
  picking 3.12 against the same PATH where `python3 --version` reports
  3.13.14.

## Deferred items

- **Two inaccuracies in the approved re-architecture design doc**, found while
  planning phase 3a on 2026-08-16. Neither invalidates the design; both mislead
  anyone implementing from it verbatim.
  1. **Resolved.** The phase 3 section said the one-way import direction "can
     be enforced by a test — you already have `tests/test_import_guard.py`".
     It could not: that file guards *emmykit availability* (missing, present,
     too old) and says nothing about import direction. Plan 3a's Task 4
     created the real layering guard as `tests/test_layering.py`, landed
     2026-08-16 (`728c62d`, `79cefc7`), with its rule table validated against
     the tree (zero violations, zero unguarded modules, correctly permitting
     `alias_index → pypi_client` and `json_types → alias_index`) and closing a
     bare-`from veny import cli` gap the first version missed.
  2. **Corrected, not just resolved.** The phase 4 section lists `pathlibcutoff`
     among fields that die with the persistence change, naming
     `dict_of_custom_modules`'s pickle check as its only other consumer. Plan
     3a's execution found a **third** consumer the design missed entirely:
     `cli.py`'s options-JSON loader, which ignores JSON files written before
     that timestamp. So the value does not simply outlive phase 4 by one
     consumer — it now lives in two places at once. `PATHLIB_CUTOFF` is a
     module constant in `analysis/custom_modules.py` (the pickle consumer,
     rehomed there as an honest historical fact about veny's on-disk format
     rather than a setting), while `Options.pathlibcutoff` still survives in
     `cli.py` for the JSON-loader consumer — the same timestamp literal
     duplicated in two files. Whichever plan finally retires `pathlibcutoff`
     needs to account for both readers, not just the pickle one.
- **Parked by 3a's reviews, 2026-08-16.** None blocking.
  - No test exercises either branch of `dict_of_custom_modules`'s `use_cache`
    keyword — the polarity was preserved by inspection and a live run only.
    The whole-branch review (2026-08-16) closed the verification gap, not
    the test gap: it exercised both branches live (a cache hit, a cache
    bypass, a legacy pre-`PATHLIB_CUTOFF` pickle whose `str` values convert to
    `Path`, and both filename conventions) and confirmed all of it behaves
    correctly. No *permanent* regression test exists for any of that yet;
    plan 3b should add one alongside whatever else it does to
    `analysis/custom_modules.py`.
  - `is_pathlib_ctor`'s `ast.Name` branch no longer honours `allow_pure=False`
    for an aliased `Pure*` name. This matches the pre-3a baseline (the old
    `or` form had the same hole), so it is **not a regression** — but the
    reason previously recorded here, that the gap is "unreachable in
    practice, since `PurePath` has no `.resolve()`/`.absolute()`", is wrong:
    `safe_eval` never executes the source it reads, so the `resolve`/
    `absolute` branch happily recomputes with a canonical concrete `Path`
    regardless of what the aliased name actually supports. Measured directly
    against `analysis/literals.safe_eval` on this branch, 2026-08-16:
    `safe_eval('PurePath("/a/b").resolve()', pathlib_aliases={"PurePath"})`,
    `safe_eval('PurePosixPath("/a/b").absolute()',
    pathlib_aliases={"PurePosixPath"})` and `safe_eval('Q("/a/b").resolve()',
    pathlib_aliases={"Q"})` all return `'/a/b'` — the gap is reachable at the
    AST level. The corrected reasoning: it is reachable, but only from source
    that would itself raise `AttributeError` if actually run (`PurePath` has
    no `.resolve`/`.absolute` method), and the pre-3a `or` form evaluated the
    identical three expressions to the identical result, so this is not a
    regression this plan introduced — it is baseline behaviour, mis-described
    rather than mis-fixed.
  - `src/veny/cli.py:124`, `search_above_this_dir` is hardcoded `True` and
    never assigned from parsed args, so `Settings.search_above_this_dir`
    (introduced this plan) now faithfully carries a value that is, in
    practice, a constant. Pre-existing, not introduced by this plan. Plan
    3e's final `Options` drain is the right place to decide whether this
    becomes a real setting or is dropped.
- **Parked by phase 2's reviews, 2026-08-16.** None blocking; each was ruled
  real but out of scope, and the phase they belong to is named.
  - `options.installed_imports` is **write-only** — written in `split_imports`,
    reset alongside `uninstalled_imports`, read nowhere. Deleting `use_pip_list`
    took its last reader. Phase 4's `Requirements` dataclass is where its fate
    belongs. (Same shape as phase 1's `FunctionInfo.ast_node`, still open.)
  - `venv_build_interpreter()`'s `shutil.which()` fallback returns the
    **unresolved bare name** when nothing is found, which reintroduces exactly
    the resolution bug it exists to prevent — `uv venv --python python3` picks
    by uv's own discovery, not PATH. The branch is untested and believed
    practically dead (a `python_command` that is not on PATH). Worth either a
    `sys.executable` fallback or a test.
  - `rename_venv` loops over a single-element tuple, `for path in (venv_dir /
    "pyvenv.cfg",)`, left that way when the download-script half went. Simplify
    when `cache_search.py` is extracted in phase 3.
  - `create_venv` uses `subprocess.check_call`, so uv's `Using CPython …` and
    `Creating virtual environment at: …` lines reach the terminal even under
    `--rawlog`, whose contract is "the same output you would see without veny".
  - The import-check probe venv no longer seeds pip/setuptools, so `setuptools`,
    `pkg_resources` and `pip` now classify as *not installed* and get installed
    into the real venv. Follows from the sanctioned no-seed decision; benign but
    undocumented for users.
  - Two orphaned environments in `~/veny` (`myenv-py3.13-20260816-141521-pyyaml`
    and `…-141900-pyyaml`) carry `interpreter_tag: "3.12"` under a `py3.13`
    folder name, built mid-phase before the interpreter-resolution fix. They can
    never be matched and are never collected — a concrete instance of the
    garbage-collection item further down this list.
- **FIXED 2026-08-16 (Task 8, commit `10400f7`).** `setup_virtualenv`
  used to crash with an unhandled `subprocess.CalledProcessError` on every
  fresh venv build, because `uv venv` refuses a non-empty target directory
  and `setup_virtualenv` always handed it one. Original writeup, kept for
  the historical mechanism:
  - Reproduction: `pixi run veny --no-cache /tmp/veny-live.py` against a
    clean throwaway script importing `yaml`. Crashed every time; confirmed
    by also running `uv venv` by hand against an empty vs. a non-empty
    directory (empty succeeds, non-empty fails with `error: Failed to
    create virtual environment / Caused by: A directory already exists
    at: <path> / hint: Use the --clear flag or set UV_VENV_CLEAR=1`).
  - Mechanism: `setup_virtualenv` (`src/veny/cli.py:3304`) calls
    `options.set_venv_dir(options.my_dir / f"failed-{folder_name}")`, whose
    `set_venv_dir` (`cli.py:229`) does `p.mkdir(parents=True,
    exist_ok=True)` — creating the target directory. It used to then call
    `write_requirements_file_with_extras(options)` (`cli.py:2860`), which
    opens `options.requirements_file` (`venv_dir / "requirements.txt"`) for
    writing — putting a file inside the now-existing directory — before
    calling `create_venv(options.venv_dir, ...)` (`cli.py:3323`), which runs
    `uv venv <target>`. Stdlib `venv.create()` (what this code path was
    written against, pre-migration) tolerates a pre-existing, non-empty
    target directory; `uv venv` does not, and raised. Nothing caught the
    resulting `CalledProcessError`, so the whole run died with a Python
    traceback instead of veny's normal error handling.
  - Why the unit suite (264 passing) never caught it: every test stubbed
    the `uv venv` subprocess call, so none of them exercised the real
    ordering constraint uv enforces on its target directory.
  - Scope: hit every "build a new venv" path through `setup_virtualenv` —
    i.e. any run where no cache match is found, which includes a new
    user's very first invocation with an empty `~/veny`. The
    `tempfile.TemporaryDirectory()`-based `create_venv` call at
    `cli.py:2606` (inside the alias-resolution probe path) was unaffected,
    because nothing writes into that directory before `create_venv` runs.
  - **The fix:** `setup_virtualenv` now calls `create_venv` first and only
    calls `write_requirements_file_with_extras` after it returns
    successfully — `--clear`/`UV_VENV_CLEAR=1` was considered and rejected,
    because it deletes the target directory's contents and would wipe
    `requirements.txt` out from under the `uv pip install -r` that reads it
    right after. Everything else in `setup_virtualenv` kept its order.
  - **Regression test:**
    `tests/test_uv_backend.py::test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt`
    calls the real `create_venv` (real `uv venv` subprocess, not stubbed)
    against a directory `Options.set_venv_dir` prepared exactly the way
    `setup_virtualenv` prepares it, with only the network/interpreter-probe
    calls (`run_uv_pip`, `verify_and_repair_imports`,
    `check_packages_in_venv`, `record_venv_state`) stubbed. Mutation-checked:
    restoring the old (write-requirements-before-create_venv) ordering made
    this test fail with the exact `CalledProcessError` /
    "A directory already exists at" error the live run hit; restoring the
    fix made it pass again, alongside the rest of the 265-test suite.
  - Live end-to-end re-verification (`pixi run veny --no-cache`, a script
    importing `yaml`): resolved `yaml` → `PyYAML`, built
    `~/veny/myenv-py3.13-20260816-141521-pyyaml`, installed with uv, printed
    `{'a': 1}`, and dropped the venv folder's `failed-` prefix on success.
    `ls ~/veny/myenv-py3.13-20260816-141521-pyyaml/bin/` confirms no `pip`
    binary — the venv uv built has none, by design.
- The five helper scripts (`mydiff`, `myaudit`, `multireplace`, `treeview`,
  `printall`) that veny used to write into `~/veny` still need adopting as
  real, standalone files in the `killett/utilities` repository, per
  `docs/prompts/2026-08-14-utilities-adopt-emmykit-scripts.md`. They must be
  extracted from **emmykit 0.3.4**, not the current 0.4.0 — 0.4.0 removed
  the embedded script constants these scripts were generated from, so 0.4.0
  no longer carries the source text to extract them from.
- **Migrated 2026-08-15 into the re-architecture design doc** (see Current
  work), which is now the single place these are tracked: the
  `interpreter_tag`/`interpreter_path` disagreement in manifests (a degraded
  stdlib probe can label a 3.13 venv 3.11, and a later degraded run then
  matches that tag) — **closed by phase 2's Task 6** (2026-08-16), which now
  tags the manifest from the venv's own reported `sys.version_info` rather
  than from the run's classified interpreter, so the two no longer have
  independent sources to disagree from; the duplicate `satisfies()` call
  between `cache_candidates()` and `check_venv_dir()`; the unreachable,
  never-working `--full` mode, resolved there as *delete*; veny's exit
  statuses never having been designed as a set; and `check_venv_dir`'s
  `issubset()` self-heal against options files predating `options.aliases`.
  The remaining four were parked on "it changes what the approved design
  says" — and that design doc is the new design.
- Smaller items carried from the venv-cache branch's review ledger, none
  blocking: `venv_cache` logs through the root logger rather than
  `logging.getLogger(__name__)` (consistent with the rest of the codebase);
  `build_folder_name` documents but does not enforce "`venv_name` must not
  contain `-`" (unreachable today — `venv_name` is the hardcoded `"myenv"`);
  the `_and_N_more` tail parse could misfire on a PyPI project literally
  named `and` or `more` beside a digit-named one (worst case, one wasted
  match attempt the manifest then rejects); `_RELEASE_RE`/`_CLAUSE_RE` sit at
  the top of `venv_cache.py` rather than beside `_release`/`_clause_holds`;
  no test covers `satisfies` with an empty wanted list, an empty
  `manifest.packages`, or two pip names normalizing to one key (last wins);
  `test_check_venv_dir_rejects_a_missing_directory` does not uniquely pin the
  `safe_is_dir` guard, since `read_manifest` also degrades on a missing
  directory.
- `univ_defs.py` is gone, deleted in the emmykit migration. `src/veny/cli.py`
  is **4,143 lines** (`wc -l src/veny/cli.py`, 2026-08-16, after phase 2 of
  the re-architecture migrated the environment layer to `uv`, plus the
  whole-branch review's finding-1/finding-2 fixes). Before that it
  was 4,362 lines, measured after phase 1 deleted the file/network visitor
  block; before phase 1 it was 6,020 lines; an earlier note here said 4,959,
  measured before `ruff format` rewrote ~3,200 lines of it and unwound the
  hand-aligned column style — the formatting reversal, not new code,
  accounted for that earlier difference.
- `FunctionInfo.ast_node` (`src/veny/cli.py:1005`) is write-only as of phase 1.
  Its only reader was the per-function loop that ran `FileOperationsVisitor`
  over each reachable `FunctionDef`, deleted with the visitor block. Every
  function of every analyzed module now retains a live `ast.FunctionDef`
  reference that nothing consumes. Parked deliberately rather than removed:
  it is harmless, and phase 3 splits `FunctionInfo` and the call graph into
  `analysis/call_graph.py`, which is the right moment to decide whether the
  field has a consumer in the new shape. Raised by phase 1's whole-branch
  review, 2026-08-16.
- `alias_index.py` is 732 lines, accepted over the plan's ~600-line split
  target by controller ruling (no further split this plan; see the ledger's
  Task 5b entry — the byte-identical move was verified symbol-by-symbol).
  `AliasCache` (~170 lines) and the interpreter probe / `_running_tag`
  (~95 lines) are genuinely separable seams — self-contained, coupled to
  the resolution logic only through constructor injection — for a future
  `alias_cache.py` / `interpreter_probe.py` split.
- `known_bad_imports` retains six project-specific local module names,
  hardcoded. If that list grows, move it to a config file under
  `options.my_dir`.
- `Options.also_needs` (in `src/veny/cli.py`) maps a package to further packages it needs.
  It is a different relation from the import-to-package aliases and was
  explicitly out of scope for the AliasIndex design; it remains hardcoded
  and deferred. (The module-alias half of this formerly-deferred item is
  now done — see the completed alias-resolver plan under Current work.
  `also_needs` itself was never part of that plan and stays open.)
- The repository had no `tests/` directory before the stdlib work. Coverage
  now stands at 257 passing tests across 13 files in `tests/`; broader
  coverage of `src/veny/cli.py` beyond what these plans touched remains open,
  and is what the re-architecture's phase 3 and 4 extractions exist to make
  possible.
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
- **`test_a_record_carrying_a_pip_spelling_is_never_repaired` does not
  actually guard what it names.** It is supposed to pin the
  `source_import_names` filter that stops `repair_unsatisfied_import`
  uninstalling a good `--reqs` package whose "import name" is really a pip
  name. But it sets `options.all_imports = set()`, so the function returns
  before reaching the branch, and its fake's bulk check passes, so the
  record never reaches the per-record path where the uninstall happens.
  Delete the filter and all 153 tests still pass. **Production behaviour is
  correct; the test is decorative.** Fix: give it a second record that
  fails the bulk check, with `all_imports` naming only that second record —
  then removing the filter uninstalls the package and the existing
  `assert fake.uninstalled == []` fails. Found by mutation testing in the
  final review, 2026-08-13.
- `run_import_check_in_venv()` in `src/veny/cli.py` — the `Provided by:` line reports the *succeeding*
  alternative while `successes.append(alternatives[0])` records the first,
  and `import_providers` unions across every such line. Provably equivalent
  today, because `report_providers=True` is only ever set with a single
  one-name group. If the bulk path ever enables that flag, both need a
  group index. Same latent shape as the `details`-accumulation note above.
- Attribution keys on top-level module names, since `packages_distributions()`
  maps `foo` and not `foo.bar`. A dotted import name attributes to nothing
  and skips the cache write — fails closed, correct direction, untested.

- Full PEP 440 support in `venv_cache.version_satisfies` — today it only
  compares dotted-numeric versions and fails closed on every pre-release,
  post-release, dev-release, local-version, and epoch form.
- Garbage collection of stale venvs in `~/veny`, including the pre-manifest
  ones this plan's Task 10 orphans (no manifest means no match, so they are
  never selected again but are also never deleted).
- **Two pre-existing `AssertionError` crashes, both found by the packaged
  entry-point branch's final review (2026-08-15) and both left unfixed as out
  of scope.** Neither is a regression — the reviewer confirmed both are
  byte-identical in `git show 4db27ef:src/veny/cli.py`.
  1. `veny -y` (or any flag set with no script argument, no `--full` and no
     `--blank-slate`) prints the "you must specify..." message, then sets
     `options.python_script = None` and crashes in `list_packages()` on
     `assert options.python_script is not None`. The message should be
     followed by an exit, not by falling through.
  2. The "already inside a virtual environment that lacks the required
     packages" branch crashes in `check_packages_in_venv` on
     `assert options.venv_dir is not None` before it can reach its own error
     path, because `options.venv_dir` is only set in the venv-*creation*
     branch. **This makes that branch's `script_exit_code = 1` unreachable
     through the front door** — the fix is correct but currently inert, and
     was verified by monkeypatching around `main()` rather than organically.
- `src/veny/cli.py`'s script-failure log lines read `result.returncode` as of
  2026-08-15; they previously read `result.stderr`, which was always `None`
  because none of the three script-running `subprocess.run` calls capture
  output. If those calls ever gain `capture_output=True`, the child's output
  stops reaching the terminal live — check both sites before changing them.
- emmykit's shell/alias helpers (`detect_shell`, `find_shell_rc_file`, `find_additional_alias_files`, and the `Options` fields `shell`, `rc_file`, `alias`, `alias_command`, `additional_alias_files`) have no caller in veny as of 2026-08-15. The usage audit is written up as a cross-repo prompt in `docs/prompts/2026-08-15-emmykit-shell-alias-helpers-audit.md` and has not been run yet. They are public API on a published 0.4.0, so removal is a breaking change and the prompt asks for a recommendation rather than a deletion.

## Open questions

- None currently blocking.
