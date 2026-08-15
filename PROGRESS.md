# PROGRESS

## Current work

**Topic:** Replaced `univ_defs.py` with the published `emmykit` package —
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

The veny branch is built now but merged only after emmykit 0.4.0 exists, so
that no known-degraded state reaches `main`.

**Next action:** Migration complete. Tasks 0–7 are all done on branch
`emmykit-migration`. `pyproject.toml` and `pixi.toml` pin
`emmykit>=0.4.0,<1.0` (installed: 0.4.0); the `[pypi-exclude-newer]`
override that exempts emmykit from the workspace's 7-day cooldown stays in
`pixi.toml`. Full suite: 250 passed. `ruff check veny.py --statistics` and
`mypy veny.py veny_json_types.py` are unchanged from the pre-pin baseline
(301 / 30 errors respectively). A live run against a real script (installing
PyYAML into a fresh/reused venv) succeeded end to end; see
`.superpowers/sdd/2026-08-14-emmykit-migration/task-7-report.md` for full
captured output. Both cross-repo prompts: the emmykit prompt
(`docs/prompts/2026-08-14-emmykit-json-type-registry.md`) is done — emmykit
0.4.0 is released and installed; the utilities prompt
(`docs/prompts/2026-08-14-utilities-adopt-emmykit-scripts.md`) is still
outstanding — see Deferred items. The branch has not been merged into
`main`; that decision is left to the coordinator.

**Previous topic (complete):** Venv-cache matching — design approved
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

**Earlier topic (complete):** Module-alias resolver. Replaced the 1,219-line
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

- veny's own types are serialized by `veny_json_types.register_types()`, called
  at `veny.py` module scope, not inside `main()`. Anything that imports veny --
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
- emmykit's `Options.args` is typed `argparse.Namespace`, while `veny.Options`
  re-declares it as `argparse.Namespace | None` (`veny.py:110` as of this
  task; the exact line drifts as the file changes). mypy reports this as an
  incompatible override, and it is expected — one of the 30 baseline mypy
  errors on `veny.py`/`veny_json_types.py`. It is harmless today because
  emmykit only ever assigns `.args`, never reads it, but veny's `| None`
  re-declaration must stay: defaulting to an empty `argparse.Namespace`
  instead would turn a loud `AttributeError` on an unparsed run into a
  silent "every flag is False". The real fix belongs upstream, in emmykit —
  annotate `Options.args` there as `argparse.Namespace | None = None`.
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
- `split_imports` in `veny.py` builds a real temporary virtual environment, so
  it cannot be unit tested directly. Pure logic must be extracted before it
  can be covered.
- The repository is a flat script layout (`veny.py` plus `alias_index.py`,
  `pypi_client.py`, `stdlib_index.py`, `venv_cache.py`, `veny_json_types.py`),
  not the `src/` package layout described in the global CLAUDE.md. New modules
  must travel alongside those files.
- `pixi run lint` and `pixi run typecheck` fail repo-wide on pre-existing
  `veny.py` errors (301 ruff, 30 mypy across `veny.py` + `veny_json_types.py`,
  as of 2026-08-14, post-emmykit-migration). The pre-commit `mypy` hook is
  literally `mypy .` with `pass_filenames: false`, so it always checks the
  whole repo and
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
  `veny_json_types`; `pypi_client` also imports nothing from `alias_index`.
  `veny_json_types.py` imports `alias_index` and `stdlib_index`, never
  `veny` — same one-way dependency discipline as `stdlib_index.py`.
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

## Deferred items

- The five helper scripts (`mydiff`, `myaudit`, `multireplace`, `treeview`,
  `printall`) that veny used to write into `~/veny` still need adopting as
  real, standalone files in the `killett/utilities` repository, per
  `docs/prompts/2026-08-14-utilities-adopt-emmykit-scripts.md`. They must be
  extracted from **emmykit 0.3.4**, not the current 0.4.0 — 0.4.0 removed
  the embedded script constants these scripts were generated from, so 0.4.0
  no longer carries the source text to extract them from.
- **A manifest can record an `interpreter_tag` and an `interpreter_path`
  that disagree.** `interpreter_tag()` (`veny.py:3974`) reads
  `options.stdlib.python_version`, while `venv_build_interpreter()` returns
  `options.python_command or sys.executable`. Those agree unless the stdlib
  probe degrades: `stdlib_index.for_interpreter` falls back to the *running*
  interpreter's index on a timeout or a non-zero exit, so a run whose target
  is 3.13 can write `interpreter_tag: "3.11"` next to
  `interpreter_path: "python3.13"`, and a second degraded run then matches
  that tag and reuses a 3.13 venv labelled 3.11. Nothing validates the pair.
  The design doc's creation flow says the tag comes from the build
  interpreter, so the code and the doc currently disagree about which
  interpreter the tag describes. Fix shape: `installed_versions_in_venv`
  already spawns the venv's own Python — have it also return
  `sys.version_info[:2]` and record *that* as the tag, making every manifest
  field a fact about the venv rather than about the run that built it.
  Raised by the whole-branch review 2026-08-14, parked because it changes
  what the approved design says.
- `satisfies()` runs twice on the winning cached venv: once inside
  `cache_candidates` (`veny.py:4788`) and again inside `check_venv_dir`
  (`veny.py:4695`), which re-reads the manifest from disk to do it. Correct
  but redundant, and it reintroduces the "the folder changed underneath the
  run" re-read that `CacheCandidate` removed from the ranking loop. Fix
  shape: have `find_match_dir_in_cache` pass the manifest it already holds
  through to `check_venv_dir`, leaving that function to do only the
  import-level confirmation. Same shape as the Task 8 ruling, and best done
  together with the interpreter-tag item above.
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
- `univ_defs.py` is gone, deleted in the emmykit migration. `veny.py` is
  5,101 lines (`wc -l veny.py`, 2026-08-15).
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
- `also_needs` (`veny.py:120`) maps a package to further packages it needs.
  It is a different relation from the import-to-package aliases and was
  explicitly out of scope for the AliasIndex design; it remains hardcoded
  and deferred. (The module-alias half of this formerly-deferred item is
  now done — see the completed alias-resolver plan under Current work.
  `also_needs` itself was never part of that plan and stays open.)
- The repository had no `tests/` directory before the stdlib work. Coverage
  now stands at 250 tests (`tests/test_alias_index.py`,
  `tests/test_pypi_client.py`, `tests/test_split_imports.py`,
  `tests/test_stdlib_index.py`); broader coverage of `veny.py` beyond what
  these plans touched remains open.
- emmykit annotates `Options.args` as `argparse.Namespace` while
  `veny.Options` re-declares it `argparse.Namespace | None`, which mypy
  reports as an incompatible override; harmless today because emmykit never
  reads `.args`, and veny's re-declaration must stay; the permanent fix is
  to annotate emmykit's `Options.args` as `argparse.Namespace | None = None`
  upstream.
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
- `veny.py:3306`/`3521` — the `Provided by:` line reports the *succeeding*
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

## Open questions

- None currently blocking.
