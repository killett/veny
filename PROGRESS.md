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
  | **3b** `docs/superpowers/plans/2026-08-16-analysis-imports-and-call-graph.md` (executed, complete on branch `analysis-imports-call-graph`) | `analysis/imports.py`, `analysis/call_graph.py`, `analysis/scan.py`, plus `analysis/scan_state.py` (a fourth module the plan added beyond the design's original three) | 1,100 |
  | **3c** `docs/superpowers/plans/2026-08-18-classify-and-environment.md` (executed, complete on branch `classify-and-environment`) | `classify.py`, `environment.py`, plus `state.py` (a third module the plan added, carrying `Requirements`) | 600 |
  | **3d** `docs/superpowers/plans/2026-08-18-verify-cache-search-last-used.md` (executed, complete, merged at `73cf588`) | `verify.py`, `cache_search.py`, `last_used.py` | 1,100 |
  | **3e** `docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming.md` (executed, complete, merged at `4d1846c`) | `pipeline.py`, `run_options.py`, `cli.py` slimming, `--full` deletion. The final `Options` drain was **not** attempted; it stayed phase 4's | 1,079 |

  Phases 1 and 2 are complete and merged to `main`. Phase 3 is complete and
  merged to `main` at `4d1846c`.

- **Phase 4 is three plans, not one** (user ruling, 2026-08-21). The `Options`
  drain, the persistence change and two behaviour changes are more than one
  plan can specify without placeholders, the same way phase 3 was:

  | Plan | Scope |
  |---|---|
  | **4a** `docs/superpowers/plans/2026-08-21-state-model-values.md` (written 2026-08-21, branch `state-model-values`) | The value objects: `Target`, the widened `Settings`, `ImportScan` as a returned product, `Requirements` as a returned product, `VenvHandle` replacing `set_venv_dir`. Also deletes folder scanning (user ruling) and makes a directory or missing script a usage error. |
  | **4b** `docs/superpowers/plans/2026-08-21-last-used-persistence.md` (executed, complete on branch `last-used-persistence`) | The `LastUsed` persistence change (design amendment 9), which breaks the `ek.Options` coupling and deletes `run_options.py`, the `cli.Options` re-export, `pathlibcutoff` and its two readers, and the test references in both spellings. Also deletes `json_types.py` and the pickle `PATHLIB_CUTOFF`, and stops `find_match_dir_in_cache` mutating the `argparse.Namespace` (user rulings, 2026-08-21). |
  | **4c** (not yet written) | The remaining behaviour changes: the in-virtualenv guard (USER RULING 2026-08-20), `--feeling-lucky`'s missing signal normalization, latent defects 1 and 3, and the residual dead arguments. |

**Next action:** **write plan 4c.** Plan 4b is **finished and merged to
`main` at `99f5320`** (a `--no-ff` merge; branch `last-used-persistence`, off
`main` @ `240767b`, deleted after merging -- it was at `5e81355`) on
2026-08-22. Its ten tasks are all committed and its tracker
(`docs/superpowers/plans/2026-08-21-last-used-persistence.md.tasks.json`)
matches. Gates re-measured on `main` after the merge: `pixi run test`
**455 passed**, `pixi run lint` zero, `ruff format --check .` **58 files**,
`pixi run typecheck` **23 errors in 6 files** over 55 source files.

**The whole-branch review found one Important issue**, which per-task review
structurally could not see: Task 1 added `from . import state` to
`last_used.py`, falsifying the "imports nothing from veny at all" claim that
`tests/test_layering.py` and `README.md` both still made. That file's comments
*are* the layer-graph specification, so the next phase could have read "needs
nothing from its peers" and demoted the module. Fixed at `5e81355`, along with
three documentation corrections; five further Minor findings and all seven
deferred minors were triaged as safe to travel and are in Deferred items
below. The reviewer re-derived the phase's own evidence rather than trusting
it -- the differential reproduces at 240 lines and eleven hunks, the sweep at
172 rows, and the rewritten flag algebra was brute-forced over all 16 flag
combinations x 2 pointer states with **zero divergences** from the code it
replaced.

**4c's scope, restated from the phase-4 table above, and everything 4b handed
it:** the in-virtualenv guard (USER RULING 2026-08-20), `--feeling-lucky`'s
missing signal normalization, latent defects 1 and 3, and the residual dead
arguments — which are now **two lists that must be reconciled into one**, 4a's
five and 4b's eight (see Deferred items). 4c also inherits the two findings
below that no code records, and it must **not** run its live check under
`pixi run`.

**Phase 4b is finished.**

**Gates measured on this branch in the closing session, 2026-08-22 — every
number below was measured here, not copied from a task report.**
`pixi run test` **455 passed, 1 warning in 7.89s**; `pixi run lint` **All
checks passed!**; `pixi run python -m ruff format --check .` **58 files
already formatted**; `pixi run typecheck` **23 errors in 6 files (checked 55
source files)**.

**The mypy ceiling did NOT move, and the plan predicted that it would.** Task
6's acceptance criterion said "deleting a dynamically-attributed class should
reduce it". It did not: 23 errors in 6 files before, 23 errors in 6 files
after. The breakdown, measured here: `tests/test_verify.py` **15**,
`analysis/imports.py` **3**, `tests/test_split_imports.py` **2**,
`src/veny/cli.py` **1**, `analysis/literals.py` **1**,
`analysis/call_graph.py` **1**. Both modules 4b deleted —
`run_options.py` and `json_types.py` — were **already mypy-clean**, so
deleting them removed no errors of their own. What *did* move is the
denominator: the checked-file count went 52 → **55**, because 4b net-added
three files (deleted `run_options.py`, `json_types.py`, `tests/test_json_types.py`
and `tests/test_options_surface.py`; added `tests/test_wiring_4b.py`,
`scripts/wiring_sweep_4b.py` and `scripts/differential_4b.py`). The 23 is the
baseline 4c starts from.

**The deletions, re-measured here rather than copied.** `rg -n 'json_types|
pathlibcutoff|run_options|save_options_to_json' src/` → **no matches**. Under
`src/`, the string `Options` survives on exactly **one** line —
`pipeline.py:218`, a docstring sentence saying the copy-back onto the old
`Options` is gone. Across `src/ tests/ scripts/` there are 76 mentions and
**one live constructor call**: `scripts/differential_3d.py:345`
`tree.cli.Options()`, which belongs to the *older tree that script drives* and
already carries a comment saying 4b's removal does not apply to it.

**The `cli.Options` re-export and the two-spelling test references are gone,
measured not copied.** 4a's closing entry recorded **49** literal `cli.Options`
and **24** spelled `veny.Options` (73 in two spellings). Now: `cli.Options`
**3**, all three inside `scripts/differential_3d.py` (two of them the comment
explaining the third); `veny.Options` **0**; and `tests/` holds **zero**
executable references to the class in either spelling. The only other residue
is `scripts/wiring_sweep_4a.py:119`, a substitution-table *string*
(`"run_options.Options()"`) in a historical harness — deliberately left alone,
and already noted in 4b's wiring index as the one stale row not carried over.

**Plan 4b is finished. Ten tasks, thirteen code/test commits, three in-flight
docs corrections and three tracker syncs (`e8568b6`, `009ba45`, `47e86b0`),
after the design amendment and the plan itself:**
`83fd14c` (the five design rulings, into the design doc's Persistence
section), `dbea1bc` (the plan), `0fdf720`+`c22a956` (Task 1, the record —
`state.LastUsed` and `last_used`'s own read and write), `a87da4b`+`2f1fb61`
(Task 2, the writer — `pipeline.run` records the venv it used, after the
`failed-` rename), `823d6a7` (Task 3, the readers, and
`find_match_dir_in_cache`'s `args` de-mutation), `2057af0` (Task 4, the pickle
`PATHLIB_CUTOFF`), `928620a`+`2d32e41` (Task 5, the test repointing),
`7881aff` (Task 6, `Options` and `run_options.py` deleted), `94cdcea`
(Task 7, `json_types.py` deleted and the emmykit guard repointed), `cdb59c8`+
`8651b20` (Task 8, the wiring sweep and the widened rule 4), `e1a5a9e`
(Task 9, the differential). The three docs commits record criteria this plan
got **wrong** and are part of the ledger, not noise: `258888d` (Task 3's
`ek.Options` criterion was unmeetable in its own scope — `cli.main` still
constructed `run_options.Options`, whose base could not go until Task 6),
`987ca82` (Task 4's case-insensitive verify command also matched the unrelated
`Options.pathlibcutoff` field), and `0c5324a` (the differential sees a
**fourth** sanctioned difference the criterion listed only three of — see
below). Task 10 is this entry.

**Four user rulings 4b carried** (2026-08-21, all in the plan's header):
old whole-`Options` records are **ignored, not migrated**; the record is **one
fixed file per script**, `.{script}-{my_name}-last-used.json`, not one per run;
`json_types.py` is **deleted** with the emmykit guard kept in a repointed form;
and `find_match_dir_in_cache` **stops mutating** the `argparse.Namespace`. The
guard's repointing deviates from the ruling's letter — `register_json_type` is
the only symbol new in emmykit 0.4.0, so a `hasattr` probe on any other name
veny calls would let a 0.3.x through, and the guard compares `ek.__version__`
instead. Recorded in the plan's Task 7 and now as **design amendment 6** in
the doc's 4b block, since it is the one place execution went past what the
committed rulings said.

**What phase 4b closed, and is now struck from Deferred items below:**

- **Design amendment 9 — the persistence change itself.** Closed by Tasks 1-3
  (`0fdf720`, `a87da4b`, `823d6a7`). `find_match_dir_in_cache` takes a
  `Callable[[], state.LastUsed | None]` and performs no attribute assignment
  on `args`; the selection-policy writes are locals, because nothing
  serializes the namespace any more.
- **`pathlibcutoff` and both its readers.** Closed by Tasks 3 and 4
  (`823d6a7`, `2057af0`) and swept clean by Task 6 (`7881aff`). The
  `last_used` reader went with the glob (one fixed filename has no timestamp
  to compare); `analysis/custom_modules.PATHLIB_CUTOFF` went because both arms
  of the comparison it guarded call `ek.ensure_path`, so it selected a log
  message and nothing else. The design-doc inaccuracy that recorded a *third*
  consumer is closed with them.
- **The `Options` drain itself, and `run_options.py`.** Closed by Task 6
  (`7881aff`): the class, the module and the `cli.Options` re-export are
  deleted, `run_options` has left `tests/test_layering.py`'s `state` layer,
  and `tests/test_state_values.py` carries a test asserting the class is gone.
- **The `cli.Options` re-export and the two-spelling test references.** Closed
  by Tasks 5 and 6 (`928620a`, `2d32e41`, `7881aff`), with the measured final
  count above: 73 → 3, none of them in `tests/`, none of them live.
- **`json_types.py`.** Closed by Task 7 (`94cdcea`), with its module-scope
  `register_types()` call, its tests, and the two Gotchas entries that
  described the registry (both retired below).

**`check_venv_dir`'s `issubset()` self-heal — design ledger item 5 — did NOT
go with the record, because it was already gone.** Checked, not assumed:
`rg -n 'issubset' src/ tests/` returns **nothing**, and `git log -S issubset`
shows the last source change in `7640f1c` ("refactor: judge every cached venv,
last-used included, by its manifest") — the venv-cache branch, long before
phase 3, which replaced the `uninstalled_imports.issubset(...)` comparison
against a loaded options file with manifest-based matching. The design doc
says phase 4's persistence change "makes it unnecessary"; in fact
manifest-based matching had already deleted it, and 4b removed the file it
used to read rather than the check. **Nothing is left for 4c here.** What *is*
left is a documentation defect: design ledger item 5 still reads as open and
still says "Closed in phase 4 with the persistence change" — see Deferred
items.

**What 4b did NOT do, with its owner named:**

- **The in-virtualenv guard** (USER RULING 2026-08-20) — **4c's**, untouched,
  and still without end-to-end evidence: 4b's live check ran under `pixi run`,
  the one shape where the guard is False. See the live-check paragraph below.
- **`--feeling-lucky` skips the signal normalization** — **4c's**, untouched.
  4b rewrote `feeling_lucky`'s *inputs* (it takes `my_name` and a `LastUsed`
  now, not an `Options` and a `pathlibcutoff`); it did not touch what the
  function omits to do.
- **Latent defects 1 and 3** — **4c's**. Both re-confirmed unchanged by Task
  8's sweep and named again in `scripts/differential_4b.py`'s residual-risk
  item 7: `-y`/`--yes` still never reaches `blank_slate` (argparse writes
  `yes`, the read is `getattr(args, "y", False)`), and `run_script(rawlog=…)`
  is still passed and unread at three of its four sites. Task 8 found a
  **fourth** dead site of defect 3, in `feeling_lucky`.
- **The residual dead arguments** — **4c's**, and now **two lists**: 4a's five
  and 4b's eight. They must be reconciled into one; none of the eight is a
  delete-the-argument fix. See Deferred items.
- **Removing the probe venv from classification** (design amendment 3) and the
  **single-file reachability gap** — still **unowned**, and still not phase
  4's.

**The STANDING CHECK.** `scripts/wiring_sweep_4b.py` and
`docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md`:
**172 arguments across 39 distinct callees**, enumerated from the AST.
**158 killed by a named test** (157 on the first substitution, 1 on a second),
**3 measured by driving** rather than substitution, **8 DEAD**, **3 OPEN HOLE**
each with its reason. **28 rows that were OPEN HOLE under some measurement are
closed by `tests/test_wiring_4b.py`**, eighteen of them log lines — veny's
commentary on a record it decided to ignore is the only thing standing between
"the pointer was stale" and "`--feeling-lucky` silently stopped working", so
it is behaviour, not decoration. **The 8 DEAD are 4c candidates**, not test
gaps. The index is keyed on `file:line` in four modules and goes stale if a
later phase edits any of them — the caveat is in Deferred items and in the
index's own header, and Task 9 was checked against it (it added
`scripts/differential_4b.py` and touched no module under `src/`, so the index
is **still valid at HEAD**).

**Two findings for 4c that no code records.** Both came out of Task 8's sweep
and are written down here because nothing in the tree says them:

1. **`cache_search.py`'s `last_used` term inside `explicit` cannot change any
   outcome, for any command line.** Proved exhaustively across all 16 flag
   combinations. It is one of the eight DEAD rows.
2. **The two `getattr(args, …)` defaults at the top of `cli.main` are
   unreachable**, because every veny flag is `action="store_true"` and
   argparse therefore always defines the dest. Five such unreachable
   `getattr(args, …, False)` defaults are in the DEAD list.

**The differential.** `scripts/differential_4b.py` reuses 4a's harness (which
reuses 3e's) and adds five layers plus a probe on the two last-used readers.
It reduces the whole phase to a **240-line diff in eleven hunks** against
`cf2ded4`, and every hunk is one of six sanctioned things: the
`veny.cli.__file__` header, the record's filename, the record's payload (76
lines of emmykit-tagged `Options.__dict__` becoming three keys), the readers'
own messages, the one fallback for a directory holding only a pre-4b record,
and — the fourth user ruling, which the task's acceptance criteria did not
list — `find_match_dir_in_cache` no longer writing onto the namespace
(`args.latest` reads True after a default run on the old tree and False on the
new one). That omission is corrected in the plan at `0c5324a`.

**It is mutation-tested five ways, and the kill signal is the second column,
not the first** — a mutation that renames a file changes the *content* of
lines the diff already carried without changing how many there are. Measured
2026-08-22: clean **240 lines / 0 differing**; **M1** (the record's filename
loses its leading dot) 236/34 — *smaller* than clean, because the record
becomes invisible to `--blank-slate`'s filter and to the driver's own report;
**M2** (`str` instead of `Path` on read) 251/17; **M3** (the record written
before the `failed-` rename) 282/58; **M4** (the cache search's last-used
pointer ignored) 339/149; **M5** (the record never written at all) 279/81;
reverted **240/0**. **M2 was a no-op until the reader probe existed** —
dropping `ek.ensure_path` on the way out of `last_used.load` changes no
message, no argv and no status, because `run_script`, `check_venv_dir` and
`safe_is_file` all accept a `str`. A weak probe does not make a driver wrong;
it makes it silent.

**The live check, and the shape it used.** A real two-run check ran from a
real shell on 2026-08-22 and is recorded in the driver's docstring with its
output: run 1 wrote `.hello.py-veny-last-used.json` with the venv inside it,
run 2 reused that environment **through the record** (no cache scan at all),
the record deleted made run 3 fall back cleanly, `--feeling-lucky` answered
from the record, and `--feeling-lucky` with the record renamed to the pre-4b
shape fell through to the cache — the live confirmation of the sanctioned
fallback. **Install shape: the pixi environment, where `sys.prefix ==
sys.base_prefix`**, so `last_used.is_virtualenv()` was False and **the
in-virtualenv branch of `pipeline.run` was not exercised by any of it.** That
branch is 4c's, and **4c's live run must not use this shape** — this is the
second phase running whose end-to-end evidence is blind to it.

**Sixteen residual risks the differential cannot see** are in its docstring;
items 1-8 are 4a's, still open, and 9-16 are this phase's — a degraded record,
a non-atomic `write_text`, the forged pre-4b record layer 17 hand-builds, the
pip-name rename turned off in layers 14-16, elided long lists, one record in
one directory, `~/veny` never holding a real interpreter, and the driver's
record filter mirroring the code under test. 4c inherits all sixteen.

Plan 4a is **finished and merged to `main` at `cf2ded4`** (a `--no-ff` merge;
branch `state-model-values`, off `main` @ `b59cfa8`, deleted after merging —
it was at `b58c9a5`) on 2026-08-21. Gates re-measured on `main` after the
merge: `pixi run test` **441 passed**, `pixi run lint` zero,
`ruff format --check .` **59 files**, `pixi run typecheck` **23 errors in 6
files**.

**The independent whole-branch review found nothing.** It ran after the
self-review below and returned zero findings. That is the first time in this
program a whole-branch review has come back clean — 3b, 3c, 3d and 3e each
turned up Important issues per-task review had missed. Read it as "nothing
survived their verification", not as proof of correctness; the eight
residual-risk items in `scripts/differential_4a.py`'s docstring are still
open, and 4b and 4c inherit them.

**Plan 4a is finished.** Ten tasks, ten commits after the plan itself:
`c8c587e` (Task 1, the usage-error change and the folder-scanning deletion),
`c91fd6e` (Task 2, `Target`), `30b80cd` (Task 3, the widened `Settings`),
`1d03ca8` (Task 4, `ImportScan` returned), `5b93c95` (Task 5, `Requirements`
returned), `569515c` (Task 6, `VenvHandle`), `d1847b9` (Task 7, the last
readers drained), `d6428c9` (Task 8, the wiring index), `7f2987b` (Task 9, the
differential and the regression it caught). Task 10 is this entry.

**Gates measured on this branch in the closing session, 2026-08-21 — every
number below was measured here, not copied from a task report.**
`pixi run test` **441 passed, 1 warning**; `pixi run lint` **All checks
passed!**; `pixi run python -m ruff format --check .` **59 files already
formatted**; `pixi run typecheck` **23 errors in 6 files**. The mypy ceiling
moved for the second time in the program: 29 → **23**, and from seven files to
six. Nothing was suppressed to get there — the frozen values' non-optional
fields removed the `Path | None` narrowing errors that needed the asserts, and
the asserts went with them.

**The live runs, and which install shape they used.** `python -m veny
hello.py --some-arg 42` from a real shell: exit 0, the script's own stdout
reached the terminal, `Runtime:` logged. `python -m veny a_directory` → the
message and **exit status 2**; `python -m veny no_such_script.py` → the message
and **exit status 2**. No traceback in either. **Install shape: the pixi
environment, where `sys.prefix == sys.base_prefix`** — so
`last_used.is_virtualenv()` was False and the middle branch of `pipeline.run`
was not exercised. That branch is phase 4c's, and 4c's live run must not use
this shape.

**The differential.** `scripts/differential_4a.py`, thirteen layers, reduces
the whole phase to a **43-line diff (four hunks)** against `4d1846c`: the
header, and Task 1's three usage-error changes — a directory, a missing
script, and a file that is not Python. The third was found by the review, not
by the plan; before layer 13 existed the diff was 29 lines and two hunks. It is
mutation-tested one regression per value object — clean 29, M1 216, M2 37,
M3 197, M4 92, M5 353, reverted 29 — and its eight residual-risk items are in
its docstring, inherited by 4b and 4c.

**It caught one regression the unit suite could not see.** Task 6 moved
`venv_dir` and `venv_python` onto the frozen `VenvHandle` and deleted them from
`Options`. Nothing read them off `Options` any more, so 439 tests stayed
green — but `ek.save_options_to_json` serializes that object's whole
`__dict__`, so the last-used record silently stopped containing a venv at all,
and `load_last_used_venv_python`'s `hasattr` check would have answered False
for every script, forever. Both fields are restored as persistence payload,
written from the handle at the save.
`test_wiring_4a::test_the_saved_record_carries_the_venv_the_run_actually_used`
closes it in-process. **This is the second phase running in which the
differential, not the suite, found the phase's one real defect.**

**The STANDING CHECK.** 178 arguments across 39 callees, enumerated from the
AST rather than by hand. **162 killed by a named test, 6 OPEN HOLE, 5 DEAD, 5
measured by driving.** 24 holes were closed inside Task 8 by
`tests/test_wiring_4a.py`, which asserts identity rather than equality. The
full table is
`docs/superpowers/plans/2026-08-21-state-model-values-wiring-index.md`; the
harness is `scripts/wiring_sweep_4a.py`.

**Six design amendments plan 4a records** (numbered on from 3e's last):

1. **`Settings` has 10 fields, not the design's 15.** `home` exists only to
   derive `my_dir`, so it stays a construction detail in `cli.py`; `log_mode`
   is read once, by `ek.configure_logging`, and stays a local there.
2. **`unusual_imports`, `max_checks` and `check_interval` are dead** —
   measured 2026-08-21, zero readers anywhere under `src/`. The design rehomed
   all three into `Settings`. Deleted instead.
3. **`script_name` is dead** — written once, to `""`, and never read. The
   design lists it in `Target`. Deleted; it is a `.stem` if anything ever
   needs it.
4. **`total_imports` was already a `len()`.** `state.Requirements.total_imports`
   has been a property since 3c; the `Options` attribute shadowing it was
   written and never read. Deleted.
5. **The four dead-argument rows at the old `pipeline.py:125` close by
   construction, not by deletion.** They were dead because
   `find_imports_in_script` built a *second* `Settings` and the scanner reads
   only `rawlog`. One object, built in `cli.main` and handed to both
   consumers, has a live reader for every field.
6. **`python_script`, `script_dir`, `timestamp`, `venv_dir`, `venv_python` and
   `my_name` do NOT leave `Options` in 4a.** The plan's Task 2 and Task 6
   acceptance criteria said they should; both were wrong, and the plan's own
   architecture paragraph was right. `ek.save_options_to_json` builds its
   filename from the first three plus `my_name`, and the last two **are** the
   payload the reader recovers. They are persistence-only fields now, written
   from the `Target` and the `VenvHandle` at the save and read nowhere else.
   Phase 4b removes them with the coupling.

**What phase 4a closed, and is now struck from Deferred items below:**

- **The folder-scanning ruling** — decided (delete, not revive; user, 2026-08-21)
  and executed in Task 1, along with the 16 wiring-index rows whose only killer
  reached them by bypassing `resolve_target`.
- **Latent defect 2** (a missing script leaves `FileNotFoundError` travelling
  uncaught out of `main`) — fixed in Task 1, together with the directory case
  and, as a deviation beyond the plan's acceptance criteria, the `ValueError`
  case `ek.ensure_file` raises for a symlink or an empty file. Leaving that
  one uncaught would have been an inconsistent half-fix.
- **`run_options.py` has never been through the STANDING CHECK** — closed by
  Tasks 6 and 8. All five of its argument-carrying call sites were inside
  `set_venv_dir`, which Task 6 deleted; `VenvHandle.for_dir`'s four
  replacements are in the new index.
- **The four `pipeline.py:125` dead arguments** — closed by construction; see
  amendment 5.

**What 4a did NOT do, with its owner named:**

- **The `Options` deletion itself, and design amendment 9** (the persistence
  change) — **4b's**. The class is down to fourteen fields in four documented
  groups; `run_options.py`'s module docstring accounts for every one.
- **`pathlibcutoff` and its two readers** — **4b's**, unchanged.
- **The `cli.Options` re-export and the test references.** Re-derived on this
  branch, **not copied**: **49** literal `cli.Options` (two of them in `src` —
  `cli.py`'s re-export and `run_options.py`'s own docstring) plus **24**
  spelled `veny.Options` across five test files that alias with
  `from veny import cli as veny` (one of the 24,
  `tests/test_json_types.py:174`, is a comment, not a reference). 3e predicted
  42 and measured 69; **4b must measure again rather than trust this.**
- **The in-virtualenv guard** (USER RULING 2026-08-20) — **4c's**, untouched.
- **`--feeling-lucky` skips the signal normalization** — **4c's**, untouched.
- **Latent defects 1 and 3** — **4c's**. Both re-confirmed unchanged by Task
  8's sweep: `-y`/`--yes` still never reaches `blank_slate`, and
  `run_script(rawlog=…)` is still passed and unread at three of its four
  sites. The fourth, the venv launch, passes `announce=True` and *is* killed.
- **The remaining dead arguments** — **4c's**. Task 8's list is five, not 3e's
  seventeen: the rest closed when the values that carried them became
  arguments with live readers.
- **Removing the probe venv from classification** (design amendment 3) and the
  **single-file reachability gap** — still unowned, and still not phase 4's.

**What the closing self-review found (2026-08-21).** Read this as the
*first* of two passes, not as the phase's review: an independent whole-branch
review was run afterwards and its findings are recorded below this list. The
self-review's coverage is the weaker of the two by construction — it was the
author reading the author's diff — and it still found one Important issue and
four Minor, which is the argument for the second pass rather than against it:

1. **IMPORTANT — a third sanctioned behaviour change nobody had recorded.**
   `veny notes.txt` — a real file that is not a Python script — used to raise
   `ValueError` out of `list_packages` and reach the user as a traceback with
   status 1. It is now a `UsageError` and **status 2**. `ek.ensure_file`
   accepts any file, so `resolve_target` lets it through and `list_packages`
   is where it fails; Task 1 changed that raise along with the two the plan
   named, and neither the plan, this file nor the differential said so. Both
   trees were run to confirm the old status was 1 and the new one is 2. Now
   carries `test_import_discovery::test_a_file_that_is_not_python_is_a_usage_error_not_a_traceback`
   (mutation-checked) and **layer 13** of the differential, which is why the
   diff is now 43 lines and four hunks rather than 29 and two.
2. **MINOR — the saved JSON payload changed, harmlessly.** `run` no longer
   assigns `options.stdlib` or `options.aliases`, so the last-used record now
   carries the defaults `Options.__init__` builds rather than the indexes the
   run resolved. Nothing reads either back — `last_used` reads `venv_python`
   and `cache_search` reads `venv_dir`, both restored — so this is a change to
   the file's contents and nothing else. Phase 4b deletes the whole payload.
3. **MINOR — an orphaned docstring line** in `build_alias_index`, where the
   old `options` entry's continuation ("and the --offline flag.") was left
   dangling under `python_command`.
4. **MINOR — `run`'s summary line** still read "Execute the run described by
   options" after options stopped describing it.
5. **MINOR — a weakened assertion.** Repointing
   `test_main_describes_the_run_to_the_cache_search` had turned
   `assert loaded == [options]` into an `isinstance` check, losing the pin
   that the loader gets the run's *own* Options — the one thing only identity
   can prove, since `load_last_used_options` loads *into* whatever it is
   handed. Restored by capturing the Options at `parse_arguments`, and
   mutation-checked.

**One trap this phase paid for, worth not paying twice.** `pixi run` sets
`PYTHONPATH=src`, and `tests/test_import_guard.py` spawns its own subprocess
that needs it. Task 8's first sweep invoked pytest directly, without it, so
that one test failed under **every** mutation and reported 86 spurious kills —
which would have hidden every real hole behind them. Any tool that runs this
suite outside `pixi run` must set `PYTHONPATH=src`, and any sweep must
sanity-import the mutated module before believing a failure.

Phase 3 is **finished**. `pipeline-and-cli-slimming` was merged to `main` at
`4d1846c` (a `--no-ff` merge; branch deleted after merging — it was at
`581b390`) on 2026-08-20, after the whole-branch review ran and its fix wave
landed. As with 3b, 3c and 3d, that review found Important issues per-task
review had missed — 3e's were two behaviour questions deliberately left for
phase 4 and one test that could not fail on its own bug. Gates re-measured on
`main` after the merge: `pixi run test` **408 passed**, `pixi run lint` zero,
`ruff format --check .` **55 files**, `pixi run typecheck` **29 errors in 7
files**.

Phase 4 inherits, all in Deferred items below:
- **The `Options` drain itself.** 3e moved the class to
  `run_options.py` and deliberately introduced no frozen dataclass. The
  `Settings` that already exists is still constructed twice in the moved
  code. `cli.Options = run_options.Options` is a re-export kept alive
  only for the suite; phase 4 deletes the module and the re-export — and
  when it does, it must repoint **69 references in two spellings**, not the
  42 the plan predicted. Measured at `08622a8`: **41** literal
  `cli.Options`, plus **28** more spelled `veny.Options` because seven test
  files do `from veny import cli as veny` — `test_split_imports.py` 11,
  `test_cache_search.py` 6, `test_options_surface.py` 4,
  `test_manifest_writing.py` 3, `test_venv_naming.py` 2,
  `test_rename_venv.py` 1, `test_json_types.py` 1. The alias spelling
  matches neither `cli\.Options` nor `setattr(cli, …)`, which is the same
  blind spot that broke Task 3's symbol sweep; re-derive with
  `rg -c '\bveny\.Options\b' tests/*.py` and check for other aliases with
  `rg -n 'import cli as (\w+)' tests/` rather than trusting this list.
- **Design amendment 9** — `cache_search.find_match_dir_in_cache` still
  takes and mutates the `argparse.Namespace`, because its selection-policy
  writes reach disk through `ek.save_options_to_json`. That is the
  persistence change, which is phase 4's.
- **`pathlibcutoff`'s two readers** (`analysis/custom_modules.PATHLIB_CUTOFF`
  and `Options.pathlibcutoff`, now in `run_options.py`). Both survived 3e
  untouched; phase 4 must account for both.
- **The 17 DEAD ARGUMENTS** 3e's wiring index measured — values built at a
  call site that the callee never reads. Deletion candidates, not test
  gaps.
- **`run_options.py` has never been through the STANDING CHECK.** Its five
  argument-carrying call sites (all inside `set_venv_dir`) are counted in
  no number anywhere. **Phase 4 owns sweeping them.**
- **The three latent defects 3e recorded but did not fix**, and **the 21
  residual risks 3e's differential cannot see** — both their own entries.
Not phase 4's, and still unowned: **removing the probe venv from
classification** (design amendment 3 — owner is whichever phase will own
that user-visible change) and **the single-file reachability gap**
(owner: a later `analysis/` plan).

Plan 3e, `docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming.md`, is
complete and **merged to `main` at `4d1846c`** (a `--no-ff` merge; branch
`pipeline-and-cli-slimming`, off `main` @ `08622a8`, deleted after merging --
it was at `581b390`). Ten tasks,
**nineteen commits** before this closing one: `c9d3989` (the plan itself),
`e5dfced` (Task 1, `Options` → `run_options.py`), `5acb137`/`f98a775` (Task 2,
every branch of `main()` driven in process *before* it moved, plus a fix
round), `b4edbbe` (Task 3, the analysis driver into `pipeline.py`),
`b4f7671`/`6b35844` (Task 4, the run itself into `pipeline.py`, plus the fix
round that restored the `start_time` baseline and reached `custom_modules` by
module), `7661a23` (Task 5, `--full` deleted and a scriptless run made a usage
error), `75ef8b3` (Task 6, the in-virtualenv branch made reachable),
`4658b27`/`fb751df`/`183bdcc` (Task 7, exit ownership back into `cli.py`, plus
two fix rounds — the second is the seventh sanctioned deviation below),
`2f2f7c3`/`ae59c99`/`ca5bdbb`/`4033c75`/`8b1d5fe`/`ac7998c` (Task 8, the
STANDING CHECK in four test batches, then the wiring index and its fix round),
and `a874f3d` (Task 9, `scripts/differential_3e.py`). Task 10 is this entry.

**On the two resume paths, and which one wins.** This project's CLAUDE.md
tells a resuming session to *prefer* the Superpowers tracker
(`<plan>.md.tasks.json`) over reading this **Current work** block by hand. That
is fine, with one caveat learned here: the tracker is **regenerated state
derived from the plan**, not an independent record, and it can drift from what
is actually committed. 3e's Task 10 closed with the tracker still saying
`"status": "pending"` for task 10 while this entry said the phase was done —
so the *recommended* resume path was the one that would have re-run a
completed task. It was corrected in the same commit that recorded this
paragraph. **When the two disagree, git and this file win; fix the tracker to
match, do not re-do the work.** The tracker also covers only task state — the
Deferred items, cross-cutting decisions, Gotchas and open questions below live
nowhere else and must be read either way.

**Gates measured on this branch at `a874f3d`, 2026-08-19 — every number below
was measured in the closing session, not copied from a task report.**
`pixi run test` **408 passed, 1 warning in 14.54s**; `pixi run lint`
**All checks passed!**; `pixi run python -m ruff format --check .` **55 files
already formatted**; `pixi run typecheck` **29 errors in 7 files**;
`pixi run smoke` **green** (`smoke: OK (console script installed, --version
matched, exit status 7 propagated)`), network available, nothing skipped. The
one warning is **pre-existing and not veny's**: `tests/test_pypi_client.py:17`
sets a >64 KiB zip archive comment on purpose and `zipfile` truncates it with
a `UserWarning`. It predates phase 3e (it is present at `08622a8`); it is
named here because 3d's closing entry did not name it and the next reader
should not have to re-derive it.

**The mypy ceiling fell again, 33 → 29 — the third unplanned fall, and the
lowest it has ever been.** The full breakdown, measured: `tests/test_verify.py`
15, `tests/test_split_imports.py` 6, `analysis/imports.py` 3,
`src/veny/pipeline.py` 2, `src/veny/cli.py` **1**, `analysis/literals.py` 1,
`analysis/call_graph.py` 1. All four of the errors that vanished came out of
one file: `cli.py`
carried **7** on `main` at `08622a8` and now carries **1**, with `pipeline.py`
picking up **2** — so the extraction net-deleted four errors rather than moving
them. Per the ledger, Task 4 dropped one and Task 5 dropped three. The file
count rose 6 → 7 only because `cli.py` split in two.

**Both ends of that 33 → 29 were measured first-hand, and the baseline needed
a trick worth reusing.** The 29 is a plain `pixi run typecheck` on this branch.
The **33** was re-measured at Task 10 in a throwaway
`git worktree add /tmp/veny-main-baseline 08622a8`, run as
`MYPY_CACHE_DIR=… /workspace/.pixi/envs/default/bin/python -m mypy .
--no-incremental` **with the worktree as cwd**, then
`git worktree remove --force`. It reported **33 errors in 6 files**:
`tests/test_verify.py` 15, `src/veny/cli.py` **7**,
`tests/test_split_imports.py` 6, `analysis/imports.py` 3,
`analysis/literals.py` 1, `analysis/call_graph.py` 1 — confirming the recorded
figure exactly, and confirming `cli.py`'s 7 directly rather than by subtraction.

**The trick is proving which tree the tool actually read**, because the
`pixi-activation-overwrites-pythonpath` trap means an editable install can
silently redirect a baseline run at `/workspace/src` and report a false pass.
Four independent tells say this run read the worktree: it names **no**
`pipeline.py` or `run_options.py` (which exist only on this branch, and whose
two errors are absent); its `src/veny/cli.py` errors are at lines **409, 555,
563, 584, 644, 645, 688**, every one past the 206-line end of this branch's
`cli.py` and possible only in a 1,064-line file; it "checked **49** source
files" against this branch's 52, a difference of exactly the three files 3e
added; and its `tests/test_split_imports.py` errors sit at 64/65/122/136/145
where this branch's are at 71/72/129/143/152, the shift Task 3 introduced.
**Never accept a baseline number without a tell like these** — a version-
dependent line number or a file that exists in only one of the two trees.

Line counts (`wc -l`, 2026-08-19, measured this session): **`src/veny/cli.py`
1,064 → 206** — an 858-line drop, **81%**, and the end of the file the whole
re-architecture was scoped around (it was **6,020** lines when the program was
scoped and **4,143** at the start of phase 3a). The lines went to
`pipeline.py` **940** and `run_options.py` **139**. The rest of the tree:
`alias_index.py` 826, `cache_search.py` **753**, `analysis/imports.py` 683,
`verify.py` 680, `venv_cache.py` 465, `analysis/scan.py` 347,
`pypi_client.py` 314, `environment.py` **312**, `classify.py` 274,
`analysis/custom_modules.py` 274, `stdlib_index.py` 233,
`analysis/literals.py` 229, `analysis/call_graph.py` 177, `json_types.py` 136,
`last_used.py` **127**, `state.py` 51, `analysis/scan_state.py` 30,
`settings.py` 23; `src/veny` totals **7,235**. Across the branch,
`src/` is **+1,154 / −900** over five files and `tests/` **+1,724 / −128**
over nine.

**`pipeline.py` landed at 940 lines against the plan's own ~700 prediction and
the design's ~300.** That is not drift to be fixed: about 260 lines are the
transitional `Options` bridge (`find_imports_in_script`'s seven-field
`ImportScan` seeding, `split_imports`' four-field copy-back, and the
`options.<field>` reads inside `list_packages` and `setup_virtualenv`), which
phase 4 deletes. Do **not** pre-emptively split the module to hit an estimate.
`cli.py` came in *under* the plan's ~300 estimate, at 206.

Two live runs closed the phase, because the second is the only end-to-end
exercise of the cache path outside the unit suite — a unit test cannot prove
the extraction left it working. Run 1, `pixi run veny --no-cache` on a
throwaway script importing `yaml`, built
**`/home/claudeuser/veny/myenv-py3.13-20260819-220857-pyyaml`** and printed
`{'phase': '3e', 'closed': True}`, exit 0. Run 2, the **same script with no
flag**, logged `Using existing virtual environment:
/home/claudeuser/veny/myenv-py3.13-20260819-220857-pyyaml` — **the identical
folder** — and printed the same dict, exit 0. Note for anyone re-running this:
the build log shows the folder being created as
`failed-myenv-py3.13-20260819-220857-pyyaml` and the script being launched
from that path; the `failed-` prefix is the *provisional* build name and is
renamed away only after verification succeeds, so "no `failed-` prefix" is a
statement about the folder on disk at the end of the run, not about the log.

3e delivered everything its plan promised except the `Options` drain, which
the plan had already declined. It recorded **three design amendments (12, 13
and 14)** and **seven sanctioned deviations** — one more than the plan's six,
added mid-phase by user ruling; all in Deferred items. Its most transferable
result, as in 3d, is not in the code: the STANDING CHECK, re-run mechanically
over **278 substitutions** at **99 call-site groups**, found **106 of the 250
rows sweep 1 covered** killable with a wrong value while all 388 tests stayed
green, and closed **67** of them (suite 388 → 408). What is left is stated
with its qualifier this time — **215 kills, 16 identity, 47 killing nothing**,
of which **30 are genuine OPEN HOLEs and 17 are DEAD ARGUMENTS** (findings,
not gaps). The index is `docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming-wiring-index.md`.

The whole-branch review then ran on the twenty-one-commit branch (2026-08-20)
and found **three Important issues and five Minors**, all settled in one wave
of four commits — `36bda31` (the test fixes), `0691352` (one docstring in
`cli.py`), this entry, and the citation re-cite that closes it. Neither Important issue was a
regression 3e introduced, and by user ruling neither was fixed here; both are
now phase-4 decisions in Deferred items. **Important 1:** deleting `--full`
(Task 5) also deleted the only production writer of a *directory* into
`options.python_script`, so `get_all_imports`, `stayed_out_dir` and the
directory branch of `list_packages` — about 55 lines — are dead code, and Task
5's fourth acceptance criterion asserts the opposite in writing ("a directory
is still reachable as a positional argument"; it now carries an `[EXECUTION]`
correction). The sting is in the index: **16 wiring-index rows** are killed
only by a test that reaches that code by assigning `options.python_script`
directly, so 16 real kills pin a path no user can take — noted in the index
itself. **Important 2:** `last_used.is_virtualenv()` is `sys.prefix !=
sys.base_prefix`, a fact about **veny's own interpreter**, so under the
`uv tool install veny` shape veny's own README prescribes it is always True
and every run with a missing import exits 1 without ever building; amendment
14 and deviation 3 now carry that qualifier, and both closing live runs used
`pixi run veny` — a conda env, the one shape where the guard is False — so
the phase's end-to-end evidence was blind to it. **Important 3** was fixed:
the timing test could not fail on the bug it is named for. The Minors: `main`'s
docstring over-promised the signal normalization (`--feeling-lucky` skips it);
the `pre-commit install` gotcha above overstated its scope; **two transcribed
deferred minors were themselves wrong and would have made the tree worse if
applied** — `test_a_run_with_no_script_is_a_usage_error`'s docstring is
correct and the `TypeError` it was told to name was a stubbed-harness
artifact, and `pipeline.run`'s `Raises:` section documents two exceptions that
really do come out of it; and two test call sites discarded
`environment.create_venv`'s post-Task-7 `bool`. Five recorded deferred minors
were re-checked and closed or corrected. One citation *was* shifted by the wave and is re-cited rather than
renumbered: `0691352` lengthened `cli.main`'s docstring by five lines, so the
**eight wiring-index rows inside `main`** (`cli.py:172`, `:173`, `:174`,
`:177`, `:178`, `:181`, `:184`, `:198`) are at `+5` in any tree from `7975316`
on. The index keeps its measured numbers — it is the record of a sweep at
`183bdcc`, and renumbering would detach it from that — and now carries the
mapping explicitly, plus the reminder that the function name in each row's
`Site` column is the durable half of the citation. Nothing else moved:
`pipeline.py` is untouched by the wave, `cli.py:156` is above the docstring,
and no file anywhere in the repo cites `PROGRESS.md` or either plan by line
number (checked with `rg`), so this file's own ~+160-line growth broke
nothing. Gates re-measured after the wave:
`pixi run test` **408 passed**, `pixi run lint` zero,
`ruff format --check .` **55 files**, `pixi run typecheck` **29 errors in 7
files** — every number identical to `0f6b315`.

Plan 3d, `docs/superpowers/plans/2026-08-18-verify-cache-search-last-used.md`,
is complete and **merged to `main` at `73cf588`** (a `--no-ff` merge; branch
`verify-cache-search-last-used`, off `main` @ `313e800`, deleted after
merging -- it was at `b072025`). Ten tasks; **twenty commits** before the
whole-branch review, tests before moves
as planned: `23e1fd0` (the plan itself), `fb83800` (Task 1, `tests/wheels.py`,
the shared wheel builder), `238fd5a`/`f526d28` (Task 2, `tests/test_verify.py`,
the verification boundary characterized live before it moved, plus its fix
round), `a5733bb`/`36f6644` (Task 4, `tests/test_last_used.py`, written before
any move, plus a fix round pinning `is_virtualenv` on both branches),
`c0510da`/`f957056`/`277dde4` (Task 3 — `venv_python_for` to `environment.py`,
then `verify.py`, then `cli.py` rewired onto it), `0943370`/`937951f` (Task 5,
extract `last_used.py` and delete the dead `load_last_used_venv_dir`, plus the
fix round that restored the assert-before-crash at the cache-search call site),
`a9ad966`/`6d2b344` (Task 6, `cache_search.py` and the move out of `cli.py`),
`93bca53`/`f961ada` (Task 7, design ledger item 2), `e430a37`/`f0a1bc4`
(Task 8, the dead-symbol sweep and the `rename_venv` mypy block), and
`939856c`/`32a12f7`/`7debbb3` (Task 9, the STANDING CHECK, the committed
differential driver, and the review's three findings). Task 10 is this entry.

The whole-branch review then ran on the twenty-eight-commit branch and found
two Important issues and one Minor, all fixed in one wave --
`3bc82ea`/`bff13ff`/`02d0afb`: `check_venv_dir` now takes a `CacheCandidate`
rather than a bare `Manifest`, so "this manifest was already matched, and for
this folder" is carried by the type instead of a docstring (the old parameter
read only its own None-ness, and phase 3e moves this decision into
`pipeline.py`, where a new caller could have passed an unmatched manifest and
accepted a venv on the folder-name prefilter alone); the wiring index's claim
that every argument kills a named test was falsified for `rawlog` -- 12 of its
17 sites are now pinned by `caplog` tests and the remaining **5 are marked
OPEN HOLE in the index**, two of them unpinned in both substitution
directions; and three tautological assertions in `tests/test_uv_backend.py`
were replaced with literal paths. The re-review verdicted all three addressed
and found a fourth: five `PROGRESS.md` citations the wave itself had shifted,
corrected in `854ee89`, with the last two rewritten as symbol names rather
than bare line numbers in `b072025`. Gates on `main` after the merge
(2026-08-19): `pixi run test` **370 passed**, `pixi run lint` zero,
`ruff format --check .` all **52 files** formatted, `pixi run typecheck`
**33 errors in 6 files**, `pixi run smoke` green.

Three modules landed, and `cli.py` **more than halved**: 2,296 → **1,064
lines**. `verify.py` is 680, `cache_search.py` 741, `last_used.py` 109 — 1,530
new lines against 1,232 removed, the difference being docstrings and the
explicit argument lists that replaced implicit `options.<field>` reads.
`last_used.py` imports nothing from veny at all; `verify` sits above
`environment` and `cache_search` above `verify` (amendment 10), enforced by
`tests/test_layering.py` with **no** new sanctioned exception.

Gates measured on this branch at `7debbb3` (2026-08-18): `pixi run test`
**359 passed** (was 321 on `main` at the branch point, so 3d is +38 tests —
+17 through Task 8, then +21 in Task 9 alone, all closing STANDING CHECK
holes); `pixi run lint` zero; `pixi run python -m ruff format --check .` all
**52 files** formatted; `pixi run typecheck` **33 errors in 6 files** — the
ceiling was 37 through phase 3b, 36 after 3c, and it has **never been this
low**; the breakdown is `tests/test_verify.py` 15, `src/veny/cli.py` 7,
`tests/test_split_imports.py` 6, `analysis/imports.py` 3,
`analysis/literals.py` 1, `analysis/call_graph.py` 1. `pixi run smoke`
**green**, network was available and nothing was skipped. Re-measured after
the whole-branch review's three fixes (2026-08-19): `pixi run test`
**370 passed** (+11 — one for `check_venv_dir`'s folder check, ten for the
`rawlog` sweep); `pixi run lint` zero; format clean (**52 files**);
`pixi run typecheck` **33 errors in 6 files**, the same breakdown — the
ceiling held. Line counts
(`wc -l`, 2026-08-18): `src/veny/cli.py` **1,064**, `alias_index.py` 826,
`cache_search.py` **741**, `analysis/imports.py` 683, `verify.py` **680**,
`venv_cache.py` 465, `analysis/scan.py` 347, `pypi_client.py` 314,
`environment.py` 297, `classify.py` 274, `analysis/custom_modules.py` 274,
`stdlib_index.py` 233, `analysis/literals.py` 229, `analysis/call_graph.py`
177, `json_types.py` 136, `last_used.py` **109**, `state.py` 51,
`analysis/scan_state.py` 30, `settings.py` 23.

Two live runs closed the phase, because the second one is the only end-to-end
exercise of Task 7's change — a unit test cannot prove it. Run 1,
`pixi run veny --no-cache` on a throwaway script importing `yaml`, built
`~/veny/myenv-py3.13-20260818-234604-pyyaml` (the `failed-` prefix dropped on
success), installed PyYAML through uv and printed
`{'phase': '3d', 'closed': True}`. Run 2, the **same script with no flag**,
logged `Using existing virtual environment:
/home/claudeuser/veny/myenv-py3.13-20260818-234604-pyyaml` — the identical
folder — and printed the same result, with the cache now taking **one**
`read_manifest` and **one** `satisfies` on the winning candidate instead of
two of each.

3d delivered everything the plan promised and recorded three design amendments
(9, 10, 11 — see Deferred items), plus a named list of what it declined and a
latent defect it deliberately did not fix (`main()`'s already-in-a-virtualenv
branch is unreachable; pre-existing at `313e800`). Its most important finding
is not in the code at all: the STANDING CHECK, run mechanically over 147
arguments at 40 call sites, found **104 of them replaceable with an empty or
wrong value with all 338 tests still green**. That is written up in Gotchas as
a standing lesson, not just as a phase result.

Plan 3c, `docs/superpowers/plans/2026-08-18-classify-and-environment.md`, is
complete and **merged to `main` at `3aa5d7e`** (a `--no-ff` merge; branch
`classify-and-environment`, off `main` @ `dc1c3c4`, deleted after merging —
it was at `3d9ae39`). Six tasks; twelve commits on the branch, tests before
moves as planned: `cde577b` (the plan itself), `cabe20d` (Task 1,
`tests/test_environment.py`, the uv boundary characterized live before it
moved), `d79eba4` (Task 2, extract
`environment.py`, veny's only `uv` caller), `b79f418` (Task 3,
`tests/test_classify.py`, 11 characterization tests written before any move),
`332d69e` (Task 4, introduce `state.Requirements` and extract `classify.py`),
`a742de3` (Task 6, closing the phase with measured gates and this ledger;
Task 5 was verification and produced no commits), `6551490` (tracker sync,
marking the plan's task checkboxes complete), `1b8a865` (a PROGRESS migration
commit, moving three falsified entries onto their originals), then the
whole-branch review's fix wave in three commits — `143f909` (deletes the dead
`cli.add_dependencies` adapter), `19702c8` (pins the arguments Task 2's
extraction made mis-wirable, plus the single-uv-owner guard), `6b2217a`
(records 3c's two unlogged design gaps and corrects a falsified citation) —
and finally `3d9ae39` (corrects three shifted PROGRESS citations from the fix
wave). `state.py` was forced rather than chosen: `classify` had to return a
product `cli` could read without either module importing the other.

The whole-branch review's two Important findings are written up in full in
Gotchas (the STANDING CHECK entry) and Deferred items (the resolved
`cli.add_dependencies` entry) — not repeated here. In short: a defect can live
in the seam between two individually-correct tasks (Task 3's characterization
tests targeted `cli.add_dependencies` while it was still the production path;
Task 4 moved the call inside `classify.split_imports` without repointing
them, leaving the adapter with zero production callers and `also_needs`
expansion unpinned on the path users take — measured, `also_needs={}` at the
call site left all 316 tests green); and an extraction can turn an implicit
`options.<field>` read into an explicit, mis-wirable call-site argument that
nothing pinned (two more arguments were each replaceable with a wrong value
leaving 316 tests green). Both are now pinned; the STANDING CHECK entry is the
mechanical check ("mutate every argument at every new call site, confirm a
test dies") that would have caught both, added to Gotchas so future
extractions run it as a matter of course.

Gates measured on `main` after the merge (2026-08-18): `pixi run test` **321
passed** (was 296 on `main` after 3b, so 3c is +25 tests — +20 through Task 4
at `332d69e`, +5 more from the fix wave, which added tests along with its
fixes); `pixi run lint` zero; `pixi run python -m ruff format --check .` all
**45 files** formatted; `pixi run typecheck` **36 errors in 5 files** — one
below the 37-error ceiling that has held since phase 2, unchanged from the
`332d69e` measurement (see Deferred items for where the remaining 21 in
`tests/test_split_imports.py` live: `tests/test_split_imports.py` 21,
`src/veny/cli.py` 10, `analysis/imports.py` 3, `analysis/literals.py` 1,
`analysis/call_graph.py` 1); `pixi run smoke` **green**, network was
available and nothing was skipped. Line counts (`wc -l`, 2026-08-18):
`src/veny/cli.py` **2,296 lines** (was 2,314 at `332d69e`, 18 fewer after the
fix wave deleted `cli.add_dependencies`; 2,626 at the start of 3c, 4,143 at
the start of 3a), `analysis/imports.py` 683, `venv_cache.py` 465,
`analysis/scan.py` 347, `pypi_client.py` 314, `environment.py` 280,
`analysis/custom_modules.py` 274, `classify.py` 274, `analysis/literals.py`
229, `analysis/call_graph.py` 177, `json_types.py` 136, `state.py` 51,
`analysis/scan_state.py` 30, `settings.py` 23 (`alias_index.py` 826 and
`stdlib_index.py` 233 are untouched by phase 3 so far). A live run on `main`
after the merge (`pixi run veny --no-cache` on a script importing `yaml`)
built a fresh venv, installed PyYAML with uv, and printed `{'merged': True,
'phase': '3c'}`.

Behaviour was verified differentially, not just by a green suite — the
technique 3b prescribed for 3c, now written up in Gotchas so 3d can reuse it.
Two differentials over a nine-entry corpus (classification state, and the argv
handed to `uv`) came back **empty**, and the check was proved capable of
failing four times over by deliberate mutation. What the differential does
*not* cover is recorded as a residual risk in Deferred items; it is not a
clean bill of health for the whole uv path.

3c did **not** deliver one thing the design promised of it. The design says
this is where `split_imports` "stops needing a temporary virtual environment";
it still needs one. The probe venv is now *injected* as a `ContextManager`
(`cli._probe_venv`) rather than removed, which keeps 3c behaviour-preserving
and delivers the testability the design was after. Removing it is a real,
user-visible behaviour change — see the Gotchas entry measuring exactly what
the probe can still answer "installed" to.

Plan 3b, `docs/superpowers/plans/2026-08-16-analysis-imports-and-call-graph.md`,
is complete and **merged to `main` at `e570ad8`** (branch
`analysis-imports-call-graph`, off `main` @ `3215df5`, deleted after merge).
Its six code tasks landed as one commit each, tests before
moves as planned: `541772c` (Task 1, `tests/test_call_graph.py`, 6
characterization tests written before any move), `b0192e1` (Task 2,
`tests/test_import_collector.py`, 5 tests, values measured by the
implementer), `f1a9b91` (Task 3, extract `analysis/call_graph.py`,
byte-identical move), `006aadb` (Task 4, introduce `analysis/scan_state.py`'s
`ImportScan` and extract `analysis/imports.py`), `6ee6c57` (Task 5, extract
`analysis/scan.py`) followed by `dbf013c` (a fix for a Critical the
whole-branch review found in the bridge — see the Gotchas entry on
`ImportScan`'s seeding), and `5dbcac2` (Task 6, retire `FunctionInfo.ast_node`,
write-only since phase 1), plus `aa15e32`, a tracker-sync commit. `ImportScan`
was forced rather than chosen: once the call-graph symbols moved under
`analysis/` they could not name `Options` without importing `cli`, which
`tests/test_layering.py` fails on.

A whole-branch review then found four Important issues, fixed in one wave
(`b1e4a31`, `4ef3e46`, `20c920c`, `ea2c9bb`): a false claim in this file that
`ModuleInfo.classes` is write-never (it is live — see Deferred items); a
layering guard that could not cover a module which does not exist yet, now
rewritten to derive its forbidden sets from a declared layer ordering so
3c's new modules cannot slip through unguarded; a README project-structure
block seven modules out of date; and the plan file itself, now annotated in
place with the five instructions execution proved wrong. That wave also added
an executable guard for the bridge's no-rebind invariant, deriving its field
list from `ImportScan` itself.

Gates on `main` after the merge: `pixi run test` **296 passed** — two more
than the plan's own predicted 294, because Task 5's fix round (`dbf013c`)
added a regression test and the final fix wave added the no-rebind guard;
`ruff check .` zero; `ruff format --check .` all 40 files
formatted; `pixi run typecheck` 37 errors (at the ceiling, unchanged from
3a); `pixi run smoke` green (network was available, nothing skipped). Line
counts measured at `5dbcac2` (`wc -l`, 2026-08-17): `src/veny/cli.py`
**2,626 lines** (was 3,707 at the start of 3b, 4,143 at the start of 3a);
`analysis/imports.py` 683, `analysis/scan.py` 347,
`analysis/custom_modules.py` 274, `analysis/literals.py` 229,
`analysis/call_graph.py` 177, `analysis/scan_state.py` 30, `settings.py` 23.
A live run on `main` after the merge (`pixi run veny --no-cache`, a script
calling `yaml.safe_load`) built a fresh venv and printed `{'k': 11}`.

Plan 3b also settled three things the approved design left open or wrong, as
its own "Three things this plan settles" section promised: `ImportScan`
carries `seen_stdlib_imports`, so `warn_about_system_packages` keeps firing;
`analysis/` receives stdlib membership as an injected
`is_stdlib: Callable[[str], bool]` (owner's decision, 2026-08-16) rather than
a `StdlibIndex`, satisfying the design's wording with bit-identical
behaviour; and the design's "Pure AST in, names out" claim is still not true
— `_register_constant_path_for_module` and `process_import` both touch the
filesystem during a scan — 3b did not make it true, as it said upfront it
would not. See Deferred items for the design-doc amendments this leaves
outstanding.

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
  early in `main()` (`cli.main` @ `7debbb3:409`), before any import analysis, so the
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
- **The single-uv-owner claim is now enforced, not just true.**
  `tests/test_layering.py::test_only_environment_py_invokes_uv` (added by 3c's
  whole-branch review, 2026-08-18) walks every module under `src/veny/` and
  fails on two syntactic signals outside `environment.py`: a reference to the
  name `uv_binary`, and a list/tuple literal whose first element is the string
  `"uv"`. Both signals were mutation-checked. It deliberately does **not**
  catch a uv path reached indirectly (a variable, a helper's return value,
  `shutil.which("uv")`) or a shell string handed to `os.system`; the docstring
  says so, because a guard that overclaims is worse than none. Calling
  `environment.run_uv_pip` / `environment.create_venv` from anywhere is not a
  violation — routing through `environment` is the point. The docstring is
  honest about those false negatives but states no false-positive limit: the
  list/tuple-literal signal could in principle fire on a non-command sequence
  whose first element happens to be the string `"uv"`; no such sequence
  exists in the tree today, so this is a known, accepted cost, not a bug in
  the guard.
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
  of any plan that touches subprocess invocation. The instruction this entry
  used to carry — that 3c's `environment.py` get a live integration test
  rather than only argument-list assertions — **was done**: 3c's Task 1 wrote
  `tests/test_environment.py`'s live install/uninstall round trip against real
  `uv` and a real venv, using a wheel the test builds itself, with no
  subprocess stubbing and no network.
- **`pixi.toml`'s `[activation.env]` sets `PYTHONPATH = "src"`, which
  *overwrites* an inherited `PYTHONPATH`.** So copying `src/` elsewhere,
  mutating the copy and running `PYTHONPATH=/tmp/mut/src pixi run python -m
  pytest` silently tests `/workspace/src` and reports a false pass. This
  matters because mutation testing is this project's gate for whether a test
  can fail at all. Mutate the working tree in place — but **copy the file to a
  scratch directory first and restore from the copy**, never with
  `git checkout -- <path>` (see the gotcha below on why that one cost a
  session's edits), and never with `git stash`. Or inject the copy with
  `sys.path.insert(0, ...)` inside the process. Confirm which file was
  loaded with `pixi run python -c "import veny.cli as c; print(c.__file__)"`.
- ~~veny's own types are serialized by `json_types.register_types()`, called
  at `src/veny/cli.py` module scope, not inside `main()`.~~ and
  ~~`alias_index.AliasIndex` is registered **encode-only** on purpose.~~ —
  **BOTH RETIRED 2026-08-22 by phase 4b's Task 7 (`94cdcea`). They now
  describe nothing.** `src/veny/json_types.py` is deleted, along with its
  module-scope `register_types()` call and `tests/test_json_types.py`. There
  is no JSON type registry in veny any more, so there is no module-scope-
  versus-`main()` trap to fall into and no encode-only registration to
  reason about. The saved options file was the registry's only consumer;
  `alias_index` writes its own cache with plain `json`, and no `to_jsonable`
  call survives under `src/` (measured: `rg -n 'json_types' src/` → nothing).
  What replaced the payload is `last_used.save`, which writes three plain
  string keys with `json.dumps`, and `last_used.load`, which is plain
  `json.loads` plus `Path(...)` on two fields — no tagged-payload decoding
  anywhere, by design (design ruling 3, 2026-08-21). **The residue of the old
  registry is that emmykit's version guard used to be pointed at
  `register_json_type`;** it is now an `ek.__version__` comparison, because
  that was the only symbol new in emmykit 0.4.0 and a `hasattr` probe on any
  other name veny calls would let a 0.3.x through.
- **The arguments nothing reads are the ones that break silently — and the
  sweep is the only thing that finds them.** Phase 4b's Task 8 review widened
  the sweep's scope rule from "the `pipeline.*` calls in `cli.main`" to "every
  call in `main`", and the eighteen rows that added included
  `ek.print_all_errors(memory_handler, rawlog)` — **both** of whose arguments
  turned out to be pinned by **no test at all**, in a tree with 435 passing
  tests. `rawlog` there decides whether veny's error dump is written for a
  terminal or for a log file; nothing would have failed if it had been wired
  to the wrong value, or to a constant. Task 8 closed both with
  `test_wiring_4b::test_the_error_dump_gets_this_runs_handler_and_this_runs_rawlog`.
  This is the same shape as 3d's `rawlog` finding and 3e's, and the general
  lesson is now four phases old: **an argument that only *selects an output
  channel* has no observable consequence in-process, so it is exactly the kind
  a green suite cannot see.** Sweep the whole function, not the calls you
  think you changed.
- **A test that cannot fail on the bug it is named for is this program's most
  frequent defect — four instances now, one per reviewing phase.** Phase 4b
  added the third and fourth. Task 2's review found a record assertion that
  checked the *contents* of the saved record but never drove the `failed-`
  rename, so the ordering it existed to pin (the record must be written
  **after** the rename, or it names a directory that is gone) could not fail
  it. Task 5's review found a pin on a call-site *choice* that had been
  rewritten, during the repointing off `Options`, into a restatement of two
  literals — it asserted that two constants equalled themselves. The earlier
  two are 3e's timing test and 4a's `test_main_describes_the_run_to_the_cache_search`.
  **The signature is always the same: the assertion survives a refactor that
  removed the thing it was watching.** When repointing a test off a value
  object, re-derive what bug would make it fail; do not check that it still
  passes.
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
  **Count updated 2026-08-19 (3e's Task 10): it is now 29 across seven
  files**, not 46 across two — see the phase-3e gates block in Current work
  for the breakdown. The *mechanism* described above is unchanged and is why
  `.git/hooks/pre-commit` is deliberately **not** installed (its own entry
  below): installing it would make `mypy .` run on every commit and block all
  of them. **Do not "fix" that by running `pre-commit install`** — the
  supported workflow is `pixi run pre-commit run --files <paths>` by hand.
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
- ~~Options files written before this branch hold bare strings where
  `options.aliases` now lives. `check_venv_dir`'s `issubset()` check fails
  once against such a file and rebuilds the venv a single time; it is
  self-healing after that one rebuild.~~ — **RETIRED 2026-08-22 (phase 4b
  Task 10). This has described nothing for several phases.** The `issubset()`
  comparison against a loaded options file was replaced by manifest-based
  matching in `7640f1c`, on the venv-cache branch, long before phase 3;
  `rg -n 'issubset' src/ tests/` returns nothing today. Phase 4b then deleted
  the options file it used to read. See Deferred items for why the design
  doc's ledger item 5 still describes this as phase-4 work.
- `scripts/review-package` can truncate large diffs mid-hunk. A reviewer
  that trusts its output without checking the tail against the working
  tree can sign off on a hunk it never actually saw.
- `.git/hooks/pre-commit` is not installed, so `git commit` does not run the
  hooks. Run `pixi run pre-commit run --files <paths>` by hand.
  **Re-confirmed 2026-08-19 (3e's Task 10):** `.git/hooks/` still holds only
  `*.sample` files and no `core.hooksPath` is set. This is **deliberate, not
  an oversight** — see the `pixi run typecheck` entry above: the `mypy` hook is
  `mypy .` with `pass_filenames: false`, so with the repo's standing errors an
  installed hook would refuse every commit **that stages a Python file**.
  (Scope corrected by 3e's whole-branch review, 2026-08-20: the hook also
  carries `types: [python]`, so pre-commit skips it entirely when nothing
  Python is staged — a docs-only commit would pass. The conclusion is
  unchanged, because `mypy .` type-checks the whole tree the moment any `.py`
  is staged, which is most commits here.) Anyone who "discovers" this and
  reaches for `pre-commit install` will break the workflow for everyone.
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
- **`cache_search.check_venv_dir`'s `candidate` parameter carries a trust
  contract, and since 3d's whole-branch review the *type* is the contract.**
  It takes a `CacheCandidate`, which only `cache_candidates` can build, and
  only for a folder whose manifest it has just read and put through
  `satisfies` against this same `wanted`/`tag` — so "already matched, and for
  this folder" is structural, not prose. It was `matched_manifest:
  Manifest | None` until the review: any `Manifest` disabled the match check,
  including one read straight off disk or belonging to a different folder,
  with only a docstring forbidding it. The remaining hole — a candidate for
  *some other* folder — is closed by an explicit `ValueError` (not an
  `assert`: S101 is enforced in `cache_search.py` and `python -O` strips
  asserts), pinned by
  `test_check_venv_dir_refuses_a_candidate_that_describes_another_folder`.
  Measured cost per cache hit, unchanged by the review fix: **1
  `read_manifest`, 1 `satisfies`** (it was 2 and 2 before 3d's Task 7),
  pinned by `test_a_cache_hit_reads_and_matches_each_manifest_once`
  (`tests/test_cache_search.py:442`). The **last-used path
  passes nothing and does its own 1 read / 1 satisfies**, and must: it reaches
  the folder from a recorded pointer, not from the scan, so there is no
  `CacheCandidate` and nothing has vouched for the manifest. That asymmetry
  is the one branch of the four whose `candidate` handling differs,
  and it is the branch 3d's differential could not reach — it is covered by
  unit tests and by a live two-run check only.
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
- **`ImportFunctionCollector` populates its own `self.base_classes`; only
  `analysis/scan.py`'s `_analyze_module` copies it onto the `ModuleInfo`, as a
  separate assignment after the walk.** A test that constructs the collector
  directly and reads `module_info.base_classes` gets `{}`, so
  `build_call_graph`'s base-class fallback never fires and an inherited
  method's imports look unreachable — which reads exactly like a bug in
  inheritance handling and is not one. Measured both ways while planning 3b:
  direct collector gives `base_classes == {}` and `collect_used_imports`
  returns `set()`; through `_analyze_module` it gives `{'Base': [], 'Child':
  ['Base']}` and `{'base64'}`. Test the call graph through `_analyze_module`.
- **The `ImportScan` bridge is seeded, not just read.** `cli.py`'s
  `find_imports_in_script` hands `analysis/scan.py` the seven live objects
  `options` already holds, and the scanner mutates them in place — there is
  no copy-back. The seeding is load-bearing in both directions:
  `dict_of_custom_modules` populates `options.custom_modules` at
  `cli.main` @ `7debbb3:520`, before `list_packages` reaches the scanner at
  `cli.main` @ `7debbb3:535`,
  and `get_all_imports` calls the scanner once per file, relying on all
  seven fields accumulating across calls. A first attempt at this bridge
  copied results *out* but never seeded them *in*; the measured consequence
  was that a script importing a known local module reported it in
  `all_imports` instead of `loaded_custom_modules` — i.e. veny would try to
  install a local module from PyPI. It passed 294 green tests and a live
  run; only a behavioural diff against the pre-move code caught it, fixed
  in `dbf013c`.
  `tests/test_import_discovery.py::test_a_prepopulated_custom_module_outside_the_script_dir_is_recognized`
  now guards it.
- **Verified by a whole-repo AST pass while planning 3b, worth keeping as an
  invariant:** nothing under `src/veny/analysis/` ever *rebinds* one of
  `ImportScan`'s seven fields — every write is `.add()`, `.append()` or
  `d[k] = v` on the existing object. That invariant is what makes the
  bridge's no-copy-back design (above) correct, and anything that breaks it
  silently detaches the caller's objects mid-scan.
- **Plan 3b's own text was wrong in four separate places, each caught by an
  implementer refusing to guess rather than by any test.** The probe named
  `ModuleInfo` attributes that do not exist (`alias_to_key`/`class_names`,
  when the real fields are `aliases`/`classes`); three symbols were called
  internal to `call_graph.py` when two still had callers outside it; a
  global constraint forbade editing `tests/test_split_imports.py` while a
  task changed a signature that file calls; and the Task 5 wrapper design
  lost the scan's read direction (see the `ImportScan` bridge entry above).
  The standing lesson already in this ledger — that a plan's stated
  "measured" is not evidence — held again, and the tests-before-moves
  ordering is what made the fourth one survivable.
- **The probe virtual environment can only ever answer "installed" for a name
  that is importable from a bare interpreter yet absent from
  `sys.stdlib_module_names`** — and there are more of those than you would
  guess. `all_imports` is already stdlib-free by the time classification sees
  it (`analysis/scan.py` filters through `is_stdlib`, which is
  `sys.stdlib_module_names` on the *target* interpreter), and a bare `uv venv`
  has no third-party package in it, so every other name necessarily comes back
  "not installed". Measured 2026-08-18 against this machine's target
  interpreter (conda-forge CPython 3.13.14), a bare `uv venv` can import 21
  such names: `__hello__`, `__phello__`, `_ctypes_test`,
  `_sysconfigdata__linux_x86_64-linux-gnu`,
  `_sysconfigdata_x86_64_conda_linux_gnu`, `_testbuffer`, `_testcapi`,
  `_testclinic`, `_testclinic_limited`, `_testexternalinspection`,
  `_testimportmultiple`, `_testinternalcapi`, `_testlimitedcapi`,
  `_testmultiphase`, `_testsinglephase`, `_virtualenv` (uv's own `.pth` shim),
  `_xxtestfuzz`, `test`, `xxlimited`, `xxlimited_35`, `xxsubtype`.
  **The probe is never asked about 17 of them.** `_compute_bad_imports` routes
  every leading-underscore name into `bad_imports`
  (`bad.update({imp for imp in all_imports if imp.startswith("_")})`,
  `classify.py:42`) and `split_imports` subtracts them —
  `all_imports = scan.all_imports - bad_imports`, `classify.py:175` — *before*
  the probe loop opens. Measured 2026-08-18: 21 non-stdlib importable names, 4
  surviving the underscore filter — `test`, `xxlimited`, `xxlimited_35`,
  `xxsubtype`. The last three are CPython's own test/demo extension modules,
  present only on builds that ship them, so the reachable set is mechanically
  one name in practice, not a judgement about what scripts plausibly import.
  And `test` is the dangerous one: a PyPI project named `test` exists.
  Verified live — `pixi run veny --no-cache` on a script whose only import is
  `test` logs
  `Checking import test : 1/1 - YES - installed`, builds no venv, and runs the
  script against the pixi interpreter's own `test` package. **So deleting the
  probe is a small but real, user-visible behaviour change**, not a pure
  refactor: `import test` would go from silently "installed" to being sent to
  PyPI. Whoever removes it must decide, deliberately, whether `test` belongs
  in `known_bad_imports`.
- **A local module in the same directory as the script does *not* reach
  `classify.py`'s custom-module branch** — plan 3c's own corpus text claimed
  it did, and that was wrong. `process_import` returns `True` for a same-dir
  `.py` (`analysis/imports.py:104`), and `analysis/scan.py:113` adds a name to
  `scan.all_imports` only when it returns `False`; classification iterates
  `all_imports`, so the branch at `classify.py:207` never sees the name. The
  branch fires **only when a name enters `all_imports` before becoming a known
  custom module** — e.g. a directory scan in which one file imports an
  unresolvable name and a later-scanned file registers that name as a local
  module. Found by an implementer refusing to guess, and confirmed by a
  reviewer's independent mutation: of nine corpus entries, that construction
  was the only one that reached the branch. Re-verified against the source
  2026-08-18.
- **Stale `__pycache__` can make an old-vs-new differential check falsely
  PASS.** A same-size source edit — a pure line reorder, which is exactly what
  refactoring produces — restored within the same *integer second* as the
  mutated compile leaves a `.pyc` whose recorded source mtime and source size
  both still match, so CPython's timestamp invalidation accepts it and the
  import serves the *pre-restore* behaviour. Reproduced from scratch
  2026-08-18: a module whose source says `A = 1` then `A = 2` imported as
  `A == 1` (the reorder's answer) while the file on disk was byte-for-byte the
  original. The remedy is `sys.dont_write_bytecode = True` **plus** a
  `__pycache__` purge before the first import (`PYTHONDONTWRITEBYTECODE=1` or
  `python -B` do the same job); with the purge in place the same setup imports
  as `A == 2`, the real answer. Observed for real during 3c's review, where a
  reviewer constructed the trap deliberately and proved both that it fires and
  that the guard defeats it.
- **The differential-corpus technique, written up so the next phase can reuse
  it.** It is the only technique in this program that has caught a regression
  *before* a fix round rather than after, and 3c ran it twice. The shape:
  `git archive <base> src/veny | tar -x -C /tmp/old` to materialize the old
  tree read-only (no worktree, no `git checkout`); one driver script that takes
  the tree root as an **argument** — never `PYTHONPATH`, because `pixi.toml`'s
  `[activation.env]` overwrites it and you silently test the live source
  twice; the driver prints `veny.cli.__file__` first, so the captured evidence
  itself shows the two runs loaded different files; an **offline**
  `AliasIndex`, `PYTHONHASHSEED=0` and sorted serialization, so the only thing
  that can differ is behaviour; and a throwaway `my_dir`, so `~/veny` is
  neither read nor written. Run it at two layers: the classification state, and
  the argv handed to `uv` captured at the `subprocess` boundary — the argv
  capture is what lets one driver compare two trees that put the same functions
  in different modules. Guard the imports as in the `__pycache__` entry above.
  And the rule that earns the whole thing its keep: **prove the check can fail
  before you trust an empty diff** — mutate the new tree, watch the diff appear,
  restore, watch it vanish.
- **STANDING CHECK for every extraction from here on: after moving a symbol
  out of `cli.py`, mutate *every argument* at the new call site and confirm a
  test dies.** Added by 3c's whole-branch review, 2026-08-18, because it is
  what would have caught both of that review's Important findings
  mechanically, and neither a green suite nor the differential caught either.
  The reason it is needed is specific to this kind of refactor: an extraction
  converts an **implicit** `options.<field>` read inside the callee into an
  **explicit** argument built at the call site. Before the move the value
  could not be mis-wired; after it, it can — and the new module's own unit
  tests pass the value directly, so they never exercise the wiring. The two
  measured instances, both leaving all 316 tests green:
  `write_requirements_file_with_extras(…, options.extra_requirements)` → `{}`
  at two sites, and `install_into_venv(options.venv_python, …)` → `None`.
  A third variant of the same shape is an adapter left behind with no
  production callers, so its tests cover dead code (`cli.add_dependencies`).
  The check is cheap and mechanical: for each argument at the new call site,
  substitute an empty/None/default value in place, run the suite, and require
  a *named* test to fail. Mutate the working tree in place and restore from a
  copy taken beforehand — **never `git stash`, never
  `git checkout -- <path>`**; 3c's Task 4 used the latter and it reverted the
  whole file, discarding every unrelated edit.
- **The standing check paid for itself at a scale nobody predicted: 3d ran it
  mechanically and found that 104 of 147 arguments could be replaced with an
  empty or wrong value with all 338 tests still green.** Measured 2026-08-18
  by 3d's Task 9 over **26 named call sites** (40 once each `check_venv_dir`
  branch and each duplicated site is counted separately) — the plan's own
  call-site table had **14 rows**, so more than half the sites the extraction
  created were not even on the list to check. Before: 147 arguments, 43
  killing a named test, **104 holes**. After: 147 / 147 / **0**. All 104 were
  closed by the **20** tests in `939856c` (suite 338 → 358, and the
  before/after table was measured at 358); the fix round `7debbb3` added one
  more and strengthened three existing ones, taking the suite to 359. Two
  concentrations account for half the holes and are the transferable lesson:
  - **`cli.main()` alone had 27**, for one reason — *nothing in the suite
    drove `main()` in process at all*. Every argument of the cache search,
    the rename, the in-virtualenv check, `--feeling-lucky` and `--reqs` was
    free. A module can be exhaustively unit-tested and its **entry point**
    still be untested; a suite's test count says nothing about whether
    anything ever calls the function that wires the modules together.
  - **The `--oldest` and `--smallest` cache-search branches had zero
    arguments pinned**, and `--latest` had only two of its own; 25 holes sat
    in `find_match_dir_in_cache`'s four `check_venv_dir` branches. Four
    near-identical branches are exactly where a suite quietly covers one and
    calls it coverage.
  Two substitution rules learned the hard way, both worth reusing: a
  boolean's substitution must be the **class default** (`rawlog=False`), not
  its opposite — substituting `True` is a no-op on any run already defaulting
  to `False` and reports false coverage; and an argument with no natural
  empty value gets a **wrong-but-type-correct** value (`Path("/tmp/wrong-…")`,
  `"wrongname"`, `"9.9"`), recorded in the table so the evidence is auditable.
  **Run this on 3e before claiming its extraction is pinned.** 3e slims
  `cli.py` further and drains `Options`, which is the same transformation
  that produced these 104.
- **3e ran it, and the rate was different in a way worth knowing: 106 of the
  250 rows sweep 1 covered were holes (42%), against 3d's 104 of 147 (71%) —
  but over far more sites.** Measured 2026-08-19 by 3e's Task 8, three sweeps,
  the third being the run of record. The rate fell for a *structural* reason
  the next extraction can reproduce deliberately: **`pipeline`'s entry points
  take the `Options` object itself**, so the argument lists inside the moved
  code moved *with* their call sites instead of being re-wired one value at a
  time. The arguments that were newly mis-wirable were only the ones crossing
  the new seam. If you want fewer holes from an extraction, move the carrier,
  not the fields — and then delete the carrier in a later phase, when there is
  a test suite to catch you. The final numbers, all measured: **278
  substitutions** over **238 distinct (site, argument) pairs** at **99
  call-site groups** — 215 kill a named test, 16 are identity, **47 kill
  nothing**. Twenty tests closed 67 of sweep 1's 106 holes (suite 388 → 408).
- **State the headline WITH its qualifier, and split findings out from gaps.**
  3d's index claimed every argument killed a named test; the whole-branch
  review falsified it. 3e's index therefore refuses the bare headline and says
  instead: of 47 rows killing nothing, **17 are DEAD ARGUMENTS** (values the
  callee never reads — deletion candidates, unpinnable by construction) and
  **30 are genuine OPEN HOLEs**, each named with its reason, and 3 of those 30
  are labelled **Conditional** because they reopen the moment a specific
  latent defect is fixed or a specific test plants a value. "30 genuine holes
  plus 17 findings" is a claim that survives review; "zero holes" is not.
- **Publish the argument accounting so an undisclosed gap is arithmetically
  visible.** 3e's sweep 1 measured 250 rows and quietly left 20 arguments
  unmeasured; the review caught it not by re-deriving the list but by adding
  the buckets up — 218 + 222 = 440, against a file total of 458. The index now
  carries **measured 236 + excluded 222 + unmeasured 0 = 458**, with every
  excluded call itemised by category. Any index that does not add to a total
  derived from the source cannot be checked without redoing the whole sweep.
- **A plan's predicted call-site table is a FLOOR, twice running, and by an
  order of magnitude.** 3d predicted 14 rows and the sweep found 40. 3e's plan
  predicted **15** and warned itself that it was a floor — the sweep found
  **99 call-site groups carrying 458 arguments**, a 6.6× miss. Do not size the
  check from the plan; derive the list mechanically from the finished files.
  Budget the sweep as a whole task, not a step.
- **Only an *effect* pins a value; a spy is worth recording as weaker.** 3e
  closed four of 3d's five OPEN HOLE `rawlog` sites with `caplog` tests that
  read a real log line the callee emits. The fifth, `ek.configure_logging`,
  has no veny-visible effect — `rawlog` changes emmykit's handler format on
  records veny never sees — so it is pinned by an argument spy, and the index
  **says so in the row** rather than letting it pass as an equal pin. When no
  effect is reachable, record the weakness; do not launder it.
- **`~/veny/failed-<name>` is the PROVISIONAL build folder, not a failure.**
  Anyone re-running the phase-closing live runs will see `uv venv` create
  `failed-myenv-py…-<pkgs>` and see the script launched from that path in the
  log. The `failed-` prefix is stripped by the rename only after verification
  succeeds, so the acceptance criterion "no `failed-` prefix" is a statement
  about the folder on disk when the run ends, not about the log. Check with
  `ls ~/veny/` after the run; do not read the log and conclude a regression.
- **A differential that sorts its captured records cannot see a reordering.**
  3e's driver sorts log records in layers 1 and 7 (only), which makes those
  layers stable against incidental emission-order noise and simultaneously
  blind to a real reordering within them. That trade is fine as long as it is
  written down — it is residual-risk item 21 — but a driver that sorts
  everywhere would report a 0-line diff for a genuine sequencing regression,
  which is the one thing a sequencing extraction most needs to detect.
- **A two-valued argument needs BOTH values substituted, and a spy pins only
  one of them.** The first rule above is half a rule, and 3d's whole-branch
  review measured the other half: for a `bool`, `True` is a
  wrong-but-type-correct value too, and on 2026-08-18 substituting it at every
  one of the **17 `rawlog=<expr>` sites** in `cli.py` (10), `cache_search.py`
  (5), `last_used.py` (1) and `verify.py` (1) left **16 of 17 green** — all 10
  of `cli.py`'s among them. The mechanism is worth remembering: the pinning
  tests are *argument spies* asserting `rawlog is True` on runs driven with
  `--rawlog`, so the `True` substitution hands each spy exactly the value it
  asserts. A spy proves a value arrived; only reading the *effect* proves the
  right value arrived. Closed 2026-08-19 by seven `caplog` tests that drive
  each path with `rawlog=False` and assert a specific `logging.INFO` record
  (and its absence under `rawlog=True`, so one test covers both directions).
  **12 of 17 now kill a named test; 5 remain open holes**, all in `cli.py`
  (`406` `ek.configure_logging`, `503` `parse_extra_requirements`, `518`
  `Settings`→`dict_of_custom_modules`, `1038` `verify_and_repair_imports`,
  `1055` `record_venv_state`) — two of them (`406`, `518`) unpinned in *both*
  directions. Both sweeps, site by site, are the `rawlog` table in
  `docs/superpowers/plans/2026-08-18-verify-cache-search-last-used-wiring-index.md`;
  the index's headline "every one of them kills a named test" now names the
  substitution class it was measured under, because that qualifier is the
  whole difference between the claim being true and being false.
- **A stub that echoes its argument back turns any assertion against the
  caller's own field into a tautology.** `tests/test_uv_backend.py`'s
  `record_spy` returns its `venv_dir` argument, and `setup_virtualenv` does
  `options.set_venv_dir(record_venv_state(...))` — so
  `assert recorded == [{"venv_dir": options.venv_dir, ...}]` compares the call
  site against its own output and cannot fail. Measured 2026-08-19: a wrong
  `timestamp=` at `setup_virtualenv`'s `build_folder_name` left
  `test_the_manifest_and_the_final_check_describe_the_venv_after_repair` green
  while killing its two siblings, which spell the path out as a literal. Spell
  the expected path out (`tmp_path / "failed-wiredenv-py3.12-…"`) whenever the
  production code assigns the stub's return value back onto the object under
  assertion. The sibling test at `tests/test_uv_backend.py:337` had carried a
  comment forbidding exactly this since 3d's Task 9; the rule now applies to
  every assertion in that file's `setup_virtualenv` block.
- **Never `git checkout -- <path>` to undo a deliberate in-place mutation.** It
  reverts the *whole* file to HEAD, discarding every unrelated edit in it, not
  just the mutation you were testing. It cost 3c's Task 4 an entire session's
  worth of `cli.py` edits, which had to be reapplied from recorded
  substitutions. Copy the file to the scratch directory first and restore from
  the copy. This is the companion to the standing rule against
  `git checkout <sha>` for investigative checkouts.
- **With `--reqs`, one import name can legitimately produce two records, and
  one requirement can land in both the installed and the uninstalled set.**
  Measured during 3c's Task 3 and pinned by `tests/test_classify.py`'s
  `test_reqs_records_are_unioned_in_after_the_loop_with_import_name_as_pip_name`
  and
  `test_a_requirement_already_importable_in_the_probe_is_recorded_in_both_sets`:
  an alias-renamed requirement yields the loop's *resolved*
  spelling and, after the loop, the verbatim `--reqs` spelling; and a
  requirement the probe can already import appears in `installed_imports`
  *and* in `uninstalled_imports`. This is current behaviour, not a bug found
  and left — but it means `Requirements` must not quietly normalize either
  case away, and any plan that "tidies" the record sets is making a
  behaviour change.

## Deferred items

- **The 4b wiring index goes stale if any later phase edits one of the four
  swept modules** (recorded 2026-08-22, phase 4b Task 8; **scope widened and
  re-checked at Task 10**).
  `docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md`
  keys all 172 of its rows on `file:line`, and
  `scripts/wiring_sweep_4b.py` rewrites expressions by source position. If
  anything changes a single line in `last_used.py`, `pipeline.py`,
  `cache_search.py` or `cli.py`, every line number below the edit is wrong and
  the index must be regenerated — `pixi run python scripts/wiring_sweep_4b.py`,
  about twelve minutes. The caveat is repeated in the index's own header,
  where it still names Task 9 specifically.
  **Checked at Task 10 (2026-08-22): Task 9 did not edit any of the four.**
  `e1a5a9e` touches `scripts/differential_4b.py` and `pyproject.toml` (a
  per-file ruff ignore), and `0c5324a` touches `docs/` only — neither reaches
  a swept module. The last commit to reach each swept module is `823d6a7`
  (`last_used.py`,
  `cache_search.py`), `8651b20` (`pipeline.py`) and `94cdcea` (`cli.py`) —
  all inside Tasks 3, 7 and 8. **The index is valid as it stands at HEAD, and
  4c is the first phase that can invalidate it.**

- **The dead-argument list for 4c is split across two indexes and must be
  reconciled** (recorded 2026-08-22, phase 4b Task 8). This file's phase-4a
  entry says "Task 8's list is five", meaning 4a's five. 4b's Task 8 found
  **eight more**, listed in
  `docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md`:
  five unreachable `getattr(args, …, False)` defaults (all veny's flags are
  `action="store_true"`, so argparse always defines the dest), the
  provably-redundant `last_used` term inside `cache_search.py:596`'s
  `explicit` (confirmed exhaustively across all 16 flag combinations), and a
  **fourth** site of 3e's latent defect 3 — `run_script(rawlog=…)` in
  `feeling_lucky`, where `announce` is False so the value cannot reach
  anything. 4c needs one list, not two, and none of the eight is a
  delete-the-argument fix: in every case the argument dies with the construct
  around it, and removing only the argument would break the hand-built
  `argparse.Namespace()` objects the unit tests pass.

  **Arithmetic correction (found and fixed by phase 4c's Task 9,
  2026-08-23): the combined count was 12 distinct sites, not 13.** 4b's
  headline in the index above reads "DEAD ARGUMENT | **6 + 2** = **8**",
  but that counts *arguments*, not *sites*: `cache_search.py:596`'s
  `getattr(args, 'last_used', False)` is one call site carrying two dead
  arguments ("both arguments, and the whole term"), so it is counted twice
  in the "8". The distinct sites the 4b list actually names are **seven**:
  the five single-argument `getattr(..., False)` defaults, the one
  `cache_search.py:596` site (counted once as a site), and the
  `pipeline.py:435` `run_script(rawlog=…)` site. Combined with 4a's five
  (no overlap — 4a's `run_script(rawlog=…)` findings are three *different*
  sites from 4b's fourth), the true distinct total is **5 + 7 = 12**. A
  note was added beside 4b's index headline
  (`docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md`)
  recording the same arithmetic; the index's original "8" is left standing
  as what the sweep literally printed. `docs/superpowers/plans/2026-08-23-behaviour-changes-4c-dead-arguments.md`
  (Task 5's reconciled list) is unaffected by this correction — it already
  lists ten rows, one per distinct finding, and never asserted a combined
  "13" itself.

- **NEW FINDING, recorded not fixed: a second dead `getattr` default Task 5's
  sweep did not cover** (found by phase 4c's Task 6, 2026-08-23; full detail
  in `docs/superpowers/plans/2026-08-23-behaviour-changes-4c-wiring-index.md`,
  "NEW FINDING: a dead argument default Task 5's list does not cover").
  `pipeline.py:853` `getattr(args, "reqs", False)`'s third argument (the
  default) is dead by the same reasoning Task 5 used to close its sibling in
  `run`'s final `else` branch: every one of veny's flags is
  `action="store_true"`, so argparse always defines `args.reqs` and no real
  command line can reach the `False` default. This occurrence is inside
  `run`'s `elif` branch (the already-in-an-activated-virtualenv path) — the
  `else` branch's sibling is what Task 5 closed; this one is a different
  branch of the same `if`/`elif`/`else`, and Task 5's sweep (scoped to the
  five sites 4a and 4b had already found) never named it, so it fell outside
  what the user ruled on. Not fixed here: Task 6 was measurement only, and
  fixing it would mean converting `getattr(args, "reqs", False)` to
  `args.reqs` at this second site too, which is in scope for a future task,
  not this one. No owner assigned.

- **Design ledger item 5 is a documentation defect, not open work** (found
  2026-08-22, phase 4b Task 10). The design doc's ledger item 5 says
  `check_venv_dir`'s `issubset()` self-heal against options files predating
  `options.aliases` "becomes unnecessary, since `LastUsed` never carries an
  `AliasIndex`. Closed in phase 4 with the persistence change." **It was
  already gone before phase 3 began.** Checked, not assumed:
  `rg -n 'issubset' src/ tests/` returns nothing, and `git log -S issubset`
  puts the last source change in `7640f1c` ("refactor: judge every cached
  venv, last-used included, by its manifest"), on the venv-cache branch — the
  commit that replaced the `uninstalled_imports.issubset(...)` comparison
  against a loaded options file with manifest-based matching. Phase 4b deleted
  the *file it used to read*, not the check. Two lines still misdescribe this
  and should be corrected by whoever next edits them rather than by a commit
  of their own: the design doc's item 5, and the Gotchas entry above that
  still says the `issubset()` check "fails once against such a file and
  rebuilds the venv a single time; it is self-healing after that one rebuild"
  — that behaviour has not existed for several phases. **No owner needed:
  there is no code to change.**

  **CLOSED 2026-08-22, before this entry's ink dried: both lines were fixed
  the same day, in the same close-out, by `500c9ee` ("docs: close phase 4b
  with measured gates and its ledger") — on `main`, before phase 4c's branch
  existed. Verified by phase 4c's Task 9 (2026-08-23) rather than assumed:**
  the design doc's ledger item 5 now reads "**CORRECTED 2026-08-22, at phase
  4b's close: this item was already closed when the design was written, and
  phase 4 had nothing to do,**" and this file's Gotchas entry now reads
  "**RETIRED 2026-08-22 (phase 4b Task 10). This has described nothing for
  several phases.**" Phase 4c owed this file nothing; it only had to notice
  the debt was already paid.

- **Four minors from phase 4b's Task 8 and Task 9 reviews, recorded rather
  than fixed** (2026-08-22). Each is a weakness in the *evidence*, not in the
  shipped code, and none is worth a re-run of a twelve-minute sweep or a
  differential on its own:
  1. **The differential's layer 18 hand-writes the record filename it means to
     test.** `--blank-slate` over a directory holding both formats is the
     layer that holds `record_path`'s docstring promise ("still starts with a
     dot and still contains `-{my_name}-`"), but it builds the name itself
     rather than asking `last_used.record_path` for it. Consequence, measured:
     **mutation M1 (the filename loses its leading dot) leaves that layer
     unchanged** — the layer that exists for M1 is the one layer M1 cannot
     move. It is caught elsewhere (M1 moves 34 lines overall), so this is a
     redundancy lost, not a hole.
  2. **The differential's layer 15 prints record *names* only.** The
     second-run read-back layer reports which record files exist, not their
     contents or timestamps, so **a run that never refreshes the record is
     nearly invisible**: measured at **239 lines / 5 differing** against a
     clean 240/0. Five lines is a real signal but a small one for a regression
     that would silently freeze every user's pointer.
  3. **The differential's docstring gloss overstates M2.** It says of M2
     (`str` instead of `Path` on read) that "every line it moves is a
     `last_used ... reader ->` note". Of the 17 lines M2 moves, **6** are
     those notes; the rest are consequential formatting. The claim is
     directionally right — M2 *is* invisible without the reader probe — and
     wrong in its arithmetic.
  4. **Residual item 7 says "three latent defects ... all still live" and
     names two.** The wording is inherited from
     `scripts/differential_4a.py` (item 7) into `scripts/differential_4b.py`
     (item 7). Both name defect 1 (`-y`/`--yes` never reaching `blank_slate`)
     and defect 3 (`run_script(rawlog=…)` dead at three of four sites). **The
     count is stale, not the content:** defect 2 — a missing script leaving
     `FileNotFoundError` travelling uncaught out of `main` — was **fixed by
     4a's own Task 1**, so it was already wrong when 4a wrote it. Two are
     live, both 4c's. 4c should write "two" when it writes its own driver.

     **CLOSED, and stale itself by the time phase 4c read it (checked by
     Task 9, 2026-08-23).** `scripts/differential_4b.py:223` was corrected
     the same day this bullet was written, in the same commit (`5e81355`):
     it reads "**Two of the three** latent defects 3e recorded, still live"
     and already names defect 2 as closed by 4a's own Task 1 — the fix this
     bullet asks for was already in the tree. `rg -n 'three latent defects'
     scripts/` still matches `differential_4a.py:132` (correct: that file
     describes 3e's *original*, three-defect finding, unchanged) and the
     substring inside `differential_4b.py:223`'s "Two of the **three**
     latent defects" (also correct: it is naming how many 3e originally
     recorded, not claiming three are still live). Neither is a defect, so
     no `scripts/` file was touched. `scripts/differential_4c.py:249`
     ("Two latent defects were live at this phase's start; both are closed
     now") was written correctly from the start, by Task 7.

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

     > **CLOSED 2026-08-21 by phase 4b, both readers.** The `last_used` one
     > went with the glob in Task 3 (`823d6a7`) — one fixed filename per
     > script leaves no timestamp to compare — and
     > `analysis/custom_modules.PATHLIB_CUTOFF` went in Task 4 (`2057af0`),
     > because both arms of the comparison it guarded call `ek.ensure_path`,
     > so it selected a log message and nothing else. Task 6 (`7881aff`) swept
     > the last mention out of `src/` with `run_options.py`. Measured
     > 2026-08-22: `rg -n 'pathlibcutoff' src/` → nothing. The design doc's
     > count of consumers was right and is now moot.
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
  - `cli.Options.__init__` @ `7debbb3:69`, `search_above_this_dir` is hardcoded `True` and
    never assigned from parsed args, so `Settings.search_above_this_dir`
    (introduced this plan) now faithfully carries a value that is, in
    practice, a constant. Pre-existing, not introduced by this plan. Plan
    3e's final `Options` drain is the right place to decide whether this
    becomes a real setting or is dropped.
- **Parked by phase 2's reviews, 2026-08-16.** None blocking; each was ruled
  real but out of scope, and the phase they belong to is named.
  - `options.installed_imports` is **write-only** — read nowhere in
    production. Deleting `use_pip_list` took its last reader. Still open, but
    **two details of this entry were falsified by 3c and are corrected here
    rather than contradicted below**: there is no longer a reset, and
    `Requirements` did not wait for phase 4 — it shipped in 3c, in `state.py`.
    The command that re-derives the first claim must be **boundary-aware**:
    `rg -nw 'installed_imports' src/veny/cli.py` gives **three** hits — the
    `Options.__init__` default at `:75`, the copy-back at `:1225`, and a
    docstring field description at `:1239`, which is not a reader, so the
    conclusion stands. (An earlier revision of this entry cited
    `rg 'installed_imports' src/veny/cli.py` and "exactly two hits"; run
    without `-w` that command gives 26, because `installed_imports` is a
    substring of `uninstalled_imports`. Re-measured 2026-08-18 at
    `143f909`; the line numbers moved by 18 when that commit deleted
    `cli.add_dependencies`.) So the shape today is narrower and easier to
    retire: `classify` computes `Requirements.installed`, `cli.py:1225` was
    its only production reader, and it read it only to perform the write
    nobody reads.
    **CLOSED by 3d's Task 8 (`e430a37`): the whole chain is deleted** — the
    `Options.__init__` default, the copy-back in `cli.split_imports` and the
    docstring field description all went. `Requirements.installed` is kept
    (`classify.split_imports` @ `7debbb3:src/veny/classify.py:187`, `:270`);
    only veny's write-only mirror of it on `Options` is gone, and
    `tests/test_layering.py`'s copy-back totality guard now covers four fields
    instead of five. The `cli.py:1225` citation is dead.
  - `venv_build_interpreter()`'s `shutil.which()` fallback returns the
    **unresolved bare name** when nothing is found, which reintroduces exactly
    the resolution bug it exists to prevent — `uv venv --python python3` picks
    by uv's own discovery, not PATH. Believed practically dead (a
    `python_command` that is not on PATH). **No longer untested** — 3c's Task 1
    added
    `test_venv_build_interpreter_falls_back_to_the_unresolved_command_and_warns_when_which_finds_nothing`
    (`tests/test_environment.py:279`), which pins the fallback *and* the
    warning. What remains open is the design question the test does not
    answer: whether the fallback should return `sys.executable` instead of the
    unresolved bare name.
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
  - Mechanism: `setup_virtualenv` (`cli.setup_virtualenv` @ `7debbb3:956`)
    calls
    `options.set_venv_dir(options.my_dir / f"failed-{folder_name}")`, whose
    `set_venv_dir` (`cli.Options.set_venv_dir` @ `7debbb3:173`) does
    `p.mkdir(parents=True,
    exist_ok=True)` — creating the target directory. It used to then call
    `write_requirements_file_with_extras(options)` (now
    `environment.write_requirements_file_with_extras` @
    `7debbb3:src/veny/environment.py:179`, called from `7debbb3:994`), which
    opens `options.requirements_file` (`venv_dir / "requirements.txt"`) for
    writing — putting a file inside the now-existing directory — before
    calling `create_venv(options.venv_dir, ...)` (now `environment.create_venv`
    @ `7debbb3:src/veny/environment.py:62`, called from `7debbb3:974`), which runs
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
    `tempfile.TemporaryDirectory()`-based `create_venv` call in
    `cli._probe_venv` @ `7debbb3:779` (the alias-resolution probe path) was unaffected,
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
- `FunctionInfo.ast_node` (cited as `src/veny/cli.py:1005`; the field was
  retired by 3b's Task 6 (`5dbcac2`) and `FunctionInfo` now lives at
  `analysis/call_graph.py` @ `7debbb3:11` with no such field) was write-only
  as of phase 1.
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
  final review, 2026-08-13. **RESOLVED by 3d's Task 3 (`277dde4`),
  exactly as prescribed.** The test now lives at `tests/test_verify.py:990`
  and carries a second record (`unsatisfied`) that fails the bulk check, with
  `source_names={"thing"}` naming only that second record, so the per-record
  loop actually runs. The filter deletion was re-run against the repaired
  test: `fake.uninstalled` becomes `["opencv-python"]` and exactly this test
  fails, with the other 39 in the file green. It also gained
  `assert fake.attempted == ["thing-only-pkg"]`, which pins that the
  pip-spelled record was filtered out rather than merely surviving.
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
     **Re-found independently and re-measured by 3d's Task 9 (2026-08-18),
     which is worth recording because it arrived from a different direction:
     the STANDING CHECK harness could not kill any argument of this branch,
     which is how it surfaced.** A correction to the entry above: 3d's brief
     called this a *third* crash; it is not — it is this one, item 2, and
     3d's independent measurement confirms it rather than adding to the
     count. Two facts 3d adds. First, **where the assert now lives**: at
     `313e800` the branch read `if check_packages_in_venv(options):` and the
     assert sat one frame deeper, inside `cli.venv_python_for`; 3d's Task 3
     moved `venv_python_for` to `environment.py` (amendment 11), which
     dropped its `options`-defaulting branch, and Task 5's fix round
     deliberately re-asserted at the `main()` call site to preserve the
     `AssertionError` exactly rather than let it become a `TypeError`. So the
     crash is **byte-for-byte the same behaviour** across the whole phase —
     3d moved it, it did not introduce it, and it is out of scope for a
     behaviour-preserving phase. Second, **the branch now has a test**:
     `test_main_checks_the_surrounding_virtualenv_against_this_runs_imports`
     sets `venv_dir` in its harness so the wiring is pinned, and its
     docstring says why, so whoever finally repairs the branch inherits a
     test of it rather than starting from nothing.

  **BOTH CLOSED BY 3e, 2026-08-19.** Item 1 became `pipeline.UsageError`,
  caught in `cli.main` and returned as **exit 2** (Task 5, `7661a23`) — the
  message no longer names `--full`, which was deleted in the same commit.
  Item 2 became reachable (Task 6, `75ef8b3`, **design amendment 14**): the
  branch no longer asserts an unset `venv_dir` but reads the environment it is
  actually in, via `last_used.active_virtualenv_dir()` (`$VIRTUAL_ENV`,
  falling back to `sys.prefix`), and import-checks that. Its
  `script_exit_code = 1` is now reachable through the front door, and the
  success side is exercised end-to-end by layer 6 of
  `scripts/differential_3e.py`, which shows the old tree raising
  `AssertionError: options.venv_dir must be set` where the new tree returns
  the script's own status (**7**). The design predicted exactly this — it
  listed both as out of scope but expected them to be "addressed incidentally
  when `cli.py` and `pipeline.py` take ownership of control flow" — and it was
  right. One residual shortfall was recorded here — that the in-virtualenv
  **success** side asserted the status only, never `launched`, leaving *which
  interpreter* runs the script on that branch unpinned. **CLOSED on the branch,
  verified 2026-08-20:** `test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`
  (`tests/test_cli_entry_point.py:1354`) asserts
  `launched == [[sys.executable, os.fspath(tmp_path / "script.py")]]`, so both
  the interpreter and the script are pinned. Still true and still only an
  artifact: the differential's layer 6 shows the new tree verifying
  `venv_python_for(active)` while launching `sys.executable` (the same
  interpreter in production — an artifact of the stub, not a defect). Nothing
  else in the crash ledger was fixed.
- `src/veny/cli.py`'s script-failure log lines read `result.returncode` as of
  2026-08-15; they previously read `result.stderr`, which was always `None`
  because none of the three script-running `subprocess.run` calls capture
  output. If those calls ever gain `capture_output=True`, the child's output
  stops reaching the terminal live — check both sites before changing them.
- emmykit's shell/alias helpers (`detect_shell`, `find_shell_rc_file`, `find_additional_alias_files`, and the `Options` fields `shell`, `rc_file`, `alias`, `alias_command`, `additional_alias_files`) have no caller in veny as of 2026-08-15. The usage audit is written up as a cross-repo prompt in `docs/prompts/2026-08-15-emmykit-shell-alias-helpers-audit.md` and has not been run yet. They are public API on a published 0.4.0, so removal is a breaking change and the prompt asks for a recommendation rather than a deletion.
- **`ModuleInfo.aliases` (`analysis/call_graph.py:34`) is a write-never
  field, the same shape as the `FunctionInfo.ast_node` that plan 3b's Task 6
  retired.** A later plan should decide it the way Task 6 decided `ast_node`.
  **Correction (whole-branch review of 3b, 2026-08-17): an earlier version of
  this entry also named `ModuleInfo.classes` as write-never. That was wrong —
  `classes` is live and load-bearing**, written at
  `analysis/imports.py:244` (`self.module_info.classes.add(node.name)`) and
  read at `analysis/call_graph.py:87` and `:103` to resolve a class
  constructor call (`Child()` → `Child.__init__`) in the call graph, plus at
  `analysis/imports.py:318`, `:341`, `:348`, `:350`, `:370` and logged at
  `analysis/scan.py:224`. Deleting it would break inheritance-aware
  reachability — exactly what plan 3b's Task 1 characterization tests exist
  to protect. Note that `ImportFunctionCollector` has its own separate
  `self.aliases` (`analysis/imports.py:176`, written at `:191`/`:208`, read
  at `:254-255`, `:304-305`, `:477`, `:492`) which does real work internally
  — a different attribute on a different object, and the source of the
  original mix-up. The two must not be confused.
- `ImportFunctionCollector`'s exotic resolution paths — `super()`, dynamic
  `__import__`, `spec_from_file_location`, `SourceFileLoader(...).load_module()`,
  and the `self.<attr>` type inference — still have no direct tests. 3b
  added five tests covering the paths that decide *which* imports are
  found; these decide *whether a call edge is drawn*, and a break in them
  silently narrows reachability.
- `get_all_imports` and `stayed_out_dir` remain in `cli.py` deliberately.
  When phase 3e gives `get_all_imports` a home in `pipeline.py`,
  `stayed_out_dir` should move with it and take `settings` — it reads only
  `stay_out_list`, which `Settings` already carries. `get_all_imports`
  still has no test of its own.
- `analysis/scan.py` has a function-local `from collections import deque`
  alongside a module-level `import collections` used only for an
  annotation; moved verbatim, worth collapsing when a plan touches the file.
  Still open: 3c did not touch `analysis/scan.py` (verified against
  `git diff --stat dc1c3c4..332d69e`), so the condition was never met.
- **Three design-doc amendments 3b records:** `ImportScan` must list
  `seen_stdlib_imports` (its omission would silence
  `warn_about_system_packages`); "analysis/* … takes neither `AliasIndex`
  nor `StdlibIndex`" is satisfied by injecting
  `is_stdlib: Callable[[str], bool]` rather than by removing the
  dependency; and the doc's "Pure AST in, names out" claim remains untrue —
  `_register_constant_path_for_module` and `process_import` both touch the
  filesystem during a scan — which 3b did not change.
- **Reachability gap: a single-file scan misses imports inside a submodule
  reached via `from package import submodule` followed by a call.** A
  directory scan (which enqueues every local module a package exposes) finds
  those imports; a single-file scan does not, so they never reach
  `all_imports`. Found during the whole-branch review of 3b (2026-08-17) and
  confirmed byte-identical before and after 3b — not a regression introduced
  by this branch, just a pre-existing gap the review happened to notice.
  Left for a later plan (3d or after) to decide whether single-file scans
  should also enqueue submodules reached this way.
- **Five more design-doc amendments 3c records** (a fourth through eighth,
  after 3b's three). The last two were added by the whole-branch review on
  2026-08-18; each is a consequence of a correct, behaviour-preserving move,
  **not a defect**, and neither should be "fixed" in code inside 3c.
  1. `classify.py` is handed `stdlib_index.PYTHON2_ONLY` — a module-level
     `Final[frozenset[str]]` (`stdlib_index.py:187`) — **not** a `StdlibIndex`
     instance. The design's line 239 ("`classify.py` is handed an
     `ImportScan`, a `StdlibIndex`, an `AliasIndex` …") is wrong for this
     module: the only standard-library fact classification needs is the
     Python-2-only name set, and stdlib membership itself was already applied
     upstream by `analysis/`.
  2. `Requirements` needs an `all_imports` field the design's field list (line
     317) omits. The post-filter `all_imports` has consumers outside
     `split_imports`, and it is **not** derivable from `installed ∪
     uninstalled`: a name recognized as a custom module lands in neither set
     (`classify.py:207` sets only a display string), so reconstructing it that
     way would silently drop every local module from the run's accounting.
     `Requirements.total_imports` is a property over it.
  3. The design's "This is where `split_imports` stops needing a temporary
     virtual environment" (line 241) is **not delivered by 3c**. The probe is
     injected as a `ContextManager` (`cli._probe_venv`) rather than removed,
     which keeps 3c behaviour-preserving and still delivers the testability
     the design was after. See the Gotchas entry measuring what the probe can
     still answer, before removing it.
  4. **`environment.py` does raise and does exit, contrary to the design's
     Error-handling section.** The design says "`environment.py` never raises
     and never exits" (design doc line 362) and "`cli.py` owns every exit.
     `sys.exit` and `ek.my_critical_error` do not appear below it" (line 376).
     Measured 2026-08-18: `environment.uv_binary`
     (`environment.uv_binary` @ `7debbb3:src/veny/environment.py:56`; the
     citation `environment.py:55` in an earlier draft of this entry was
     correct before 3d and is off by one now) holds
     the **only `raise SystemExit` anywhere under `src/veny/` below `cli.py`**,
     `__main__.py`'s `sys.exit(main())` aside; and `create_venv` lets
     `subprocess.check_call` raise `CalledProcessError` (documented in its own
     docstring). Both behaviours are byte-identical to `dc1c3c4` — 3c moved
     them, it did not introduce them, and changing either inside 3c would have
     been a behaviour change the phase forbade. **What resolves it:** `cli.py`
     owning the exit — `uv_binary` returning `str | None` (or raising a veny
     exception) with `cli.py` translating it into the `uv tool install veny`
     message, and `create_venv` returning success rather than raising. That is
     a real behaviour-boundary change and belongs to whichever phase is
     willing to own it (3d at the earliest, 3e most naturally, since it owns
     the final `cli.py` slimming).
  5. **`environment.py` takes a raw `venv_python` path, not the `VenvHandle`
     the design specifies.** The design says environment "is handed a
     `VenvHandle` and package names" (line 242) and lists `VenvHandle` in
     `settings.py` (line 215). Measured 2026-08-18: `rg -n 'VenvHandle' src/
     tests/` returns **nothing** — the type does not exist yet; it is a
     phase-4 introduction, and 3c could not have used it. So every
     environment function that needs an interpreter takes
     `venv_python: str | os.PathLike[str] | None`. **What resolves it:**
     `VenvHandle` arriving in phase 4, at which point `run_uv_pip`,
     `install_into_venv` and `uninstall_from_venv` take it instead — which
     also removes the `None` argument that made the mis-wiring the review
     found in `repair_unsatisfied_import` possible in the first place, since a
     handle has no null spelling. (Citation re-measured for 3d: that call has
     left `cli.py` entirely — it is
     `verify.repair_unsatisfied_import.installer` @
     `7debbb3:src/veny/verify.py:513` — the call sits in a nested closure
     (`def installer` @ `:511`) inside `repair_unsatisfied_import`
     (`def` @ `:467`), not in that function's own body, and the citation
     names the closure because that is what the reader has to find. The old
     `cli.py:1409` citation is dead.)
- **Three more design-doc amendments 3d records** (a ninth through eleventh,
  after 3b's three and 3c's five). Each is a consequence of a correct,
  behaviour-preserving move, **not a defect**, and none should be "fixed" in
  code inside 3d.
  9. **`cache_search.find_match_dir_in_cache` keeps taking the
     `argparse.Namespace` and keeps mutating it.** The design says argparse
     dies at the `cli.py` boundary (design doc line 260, and the phase-4 note
     that `args` dies at the argparse boundary). It cannot die here: the
     function's selection policy *writes* `args.last_used = True` as its "no
     flags given" default, and `args.latest = True` / `args.last_used = False`
     as its fallback after a last-used miss — and those writes reach disk,
     because `ek.save_options_to_json` serializes `options.__dict__.copy()`
     and the `args` Namespace is part of that payload. Passing four booleans
     in and dropping the write-back would change the bytes of a user-visible
     artifact. `argparse.Namespace` is stdlib, so taking it introduces no
     veny-layer dependency and the layering guard is satisfied. **What
     resolves it:** phase 3e or 4, when `cli.py` owns the flag surface and the
     persistence change removes the JSON payload the mutation leaks into.
  10. **`verify.py` imports `environment.py`; they are not peers.** The
      design's stack (line 267) lists them side by side under `pipeline`.
      Measured: `repair_unsatisfied_import` installs and uninstalls through
      `environment`, and `verify_and_repair_imports` rewrites
      `requirements.txt` through
      `environment.write_requirements_file_with_extras`. So `verify` is a
      layer **above** `environment`, and `cache_search` a layer above
      `verify` (it calls `check_venv_dir` → `verify.check_packages_in_venv`).
      `tests/test_layering.py`'s `LAYERS` now reads, bottom to top:
      `{settings}`, `{analysis, alias_index, venv_cache, stdlib_index,
      pypi_client, json_types}`, `{state}`, `{classify, environment,
      last_used}`, `{verify}`, `{cache_search}`, `{cli}` — with **no new
      entry in `SANCTIONED_EXCEPTIONS`**, verified by running the suite, not
      by reading the plan.
  11. **`venv_python_for` moved to `environment.py`, not to `verify.py`.**
      The design does not place it. It is venv-layout knowledge (`bin/python`
      vs `Scripts/python.exe`), which is what `environment.py` owns, and
      `tests/test_environment.py` already carried a parked note that its live
      test hardcodes that layout "instead of reusing `cli.venv_python_for`".
      Its `options`-defaulting branch died with the move: every caller now
      passes a directory. Phase 4's `VenvHandle` replaces it outright. One
      widened precondition came with it — see the 3d deferred-minors entry.
- **What 3d explicitly declined, each with the phase that owns it.** Stated
  here rather than left ambiguous, and none of these is a defect 3d
  introduced:
  - **The `environment.uv_binary` / `create_venv` exit-ownership change**
    (amendment 4, above). A real behaviour-boundary change. **Owner: 3e**,
    which owns the final `cli.py` slimming and is the natural place for
    `cli.py` to take back the exit.
  - **The single-file reachability gap** — imports inside a submodule reached
    via `from package import submodule` (its own entry above). It is an
    `analysis/` question; none of 3d's three modules can see it. **Owner: a
    later `analysis/` plan**, not 3e by default.
  - **Removing the probe venv from classification** (amendment 3). The probe
    is injected, not removed, and Gotchas measures exactly what it can still
    answer "installed" to. **Owner: whichever phase is willing to own the
    user-visible behaviour change**; it is not 3d's.
  - **The two pre-existing `AssertionError` crashes** (their own entry above,
    now three — see below). Out of scope by the design. 3d's Task 3 was
    required to *preserve* the second one exactly, and its Task 5 fix round
    restored it at the new call site after the move had accidentally turned it
    into a `TypeError`.
- **Three more design-doc amendments 3e records** (a twelfth through
  fourteenth, after 3b's three, 3c's five and 3d's three). Each is a
  consequence of a correct, behaviour-preserving move, **not a defect**.
  12. **`Options` gets its own module before it dies.** The design goes
      straight from "`Options` carries everything" to "frozen dataclasses" and
      never says where the class lives while `pipeline.py` exists and
      `Options` still does too. It could not stay in `cli.py`: `pipeline.py`
      would then import the module *above* it, which `tests/test_layering.py`
      forbids and which is a real import cycle. So the class moved unchanged
      to `src/veny/run_options.py` (139 lines), and `cli.py` keeps
      `Options = run_options.Options` as a re-export so the suite's existing
      `cli.Options` references keep working. `run_options` joins the `state`
      layer — it imports `alias_index` and `stdlib_index`, both one layer
      below, and nothing at or below that layer imports it. **What resolves
      it:** phase 4 deletes both the module and the re-export.
      > **RESOLVED 2026-08-21 by phase 4b's Tasks 5 and 6** (`928620a`,
      > `2d32e41`, `7881aff`). Both are deleted. The repointing 3e predicted
      > at 42 references and 4a re-measured at 73 in two spellings (49
      > `cli.Options` + 24 `veny.Options`) is done: measured 2026-08-22,
      > `cli.Options` is down to **3** — all three inside
      > `scripts/differential_3d.py`, two of them the comment explaining the
      > third — and `veny.Options` to **0**. `tests/` holds no executable
      > reference to the class in either spelling.
      > `src/veny/json_types.py` went the same way in Task 7 (`94cdcea`),
      > taking `tests/test_json_types.py` with it, so the layering table above
      > no longer lists it. The one string left is
      > `scripts/wiring_sweep_4a.py:119`'s substitution-table entry
      > `"run_options.Options()"`, deliberately not carried over — 4a's
      > harness is history and is left alone, as 4b's index header records.
  13. **`blank_slate` belongs to `pipeline.py`, not `cli.py`.** The design
      says `cli.py` owns "argparse and exit status and nothing else", and the
      blank-slate branch is 45 lines of `shutil.rmtree` and directory
      iteration. It is a *mode of the run*, not a CLI concern, so it landed in
      `pipeline.py` as its own function; `cli.py` parses the flag and maps the
      return to exit 0. The rule the design meant is "`cli.py` owns the flag
      surface", not "`cli.py` owns everything a flag triggers".
  14. **The in-virtualenv branch became reachable.** `main()`'s
      `elif last_used.is_virtualenv():` asserted `options.venv_dir is not
      None` while nothing on that path ever set `venv_dir`, so running veny
      from inside an active virtual environment could only ever raise
      `AssertionError`. The branch now reads the environment it is actually in
      via `last_used.active_virtualenv_dir()` (`$VIRTUAL_ENV`, falling back to
      `sys.prefix`) and import-checks that, which is what it was written to
      do. This closes the **second** of the two pre-existing `AssertionError`
      crashes the design listed as out of scope but expected to be "addressed
      incidentally when `cli.py` and `pipeline.py` take ownership of control
      flow". The design was right about that; it is recorded as an amendment
      because a behaviour change, even a repair, is not a move.

      **The crash is closed but the branch's precondition is still wrong —
      found by the whole-branch review, 2026-08-20, USER RULING: record now,
      fix in phase 4.** `last_used.is_virtualenv()` is `sys.prefix !=
      sys.base_prefix`, which is a statement about **veny's own interpreter**,
      not about the user's shell. `README.md:16` and `environment.py`'s
      `UvUnavailable` message both tell users to install with `uv tool install
      veny`, which puts veny in a venv, and `scripts/smoke-install.sh:33-34`
      does the same with `python -m venv`. In **any** such install
      `is_virtualenv()` is always True, so every run with a non-empty
      `uninstalled_imports` takes the middle branch (`pipeline.py:830-861`),
      import-checks **veny's own tool venv** — which of course lacks the
      user's script's packages — logs "Please deactivate the current virtual
      environment and run the script again." and returns 1. The concrete
      consequence: `uv tool install veny` plus a script with a missing import
      ⇒ **exit 1, never a build**, with the cache search and
      `setup_virtualenv` below it unreachable. This is **not a regression** —
      at `08622a8` the same input hit `assert options.venv_dir is not None`
      and crashed — so amendment 14 traded a crash for a wrong answer, which
      is an improvement; but it did not make the branch correct, and this
      entry previously read as though it had. See Deferred items for the
      phase-4 question and the minimal fix.

- **3e's seven sanctioned deviations — behaviour that visibly changed, each
  deliberate.** The plan carried six; **the seventh was added mid-phase by an
  explicit user ruling** during Task 7's second fix round. All seven are
  reproduced by `scripts/differential_3e.py`, whose whole old-vs-new diff is
  **37 lines** and contains nothing else.
  1. **`environment.py` stops exiting** (the design's amendment 4, which 3d
     declined and named 3e's). `uv_binary` raises `environment.UvUnavailable`
     carrying today's message verbatim instead of `SystemExit`, and
     `create_venv` returns `bool` instead of raising. `cli.main` catches both.
  2. **The no-script path is a usage error.** `veny` with no script used to
     log "You must specify either a script to run or one of these arguments:
     `--full`, `--blank-slate` …" and then fall through into `list_packages`,
     which died on an assert. It is now `pipeline.UsageError`, caught in
     `cli.main` and returned as **exit 2**. First of the two pre-existing
     crashes; the second is amendment 14.
  3. **The in-virtualenv branch runs instead of crashing** — amendment 14,
     restated here because it is user-visible. **Qualifier added by the
     whole-branch review, 2026-08-20:** it now runs, but it still asks about
     the wrong process. `last_used.is_virtualenv()` tests **veny's own**
     interpreter (`sys.prefix != sys.base_prefix`), not the user's shell, so
     under the install shape veny's own docs prescribe — `uv tool install
     veny`, `README.md:16` — it is **always True**. Concrete consequence: a
     `uv tool install veny` user running a script with a missing import gets
     the branch's `script_exit_code = 1` and "Please deactivate the current
     virtual environment and run the script again.", **never a build**; the
     cache search and `setup_virtualenv` are unreachable for them. Not a
     regression (that same input crashed at `08622a8`), but the deviation
     should not be read as "this branch is now correct". **The phase's own
     end-to-end evidence cannot see it:** both closing live runs used `pixi
     run veny`, and a conda env has `sys.prefix == sys.base_prefix` — the one
     install shape where the guard is False and the branch is skipped. USER
     RULING: recorded here, fixed in phase 4; see Deferred items.
  4. **`--full` is gone**, with its help text, its README mention and all
     **six** of its branches. Design ledger item 3 ("`--full` has never
     worked") is closed. `veny --full` now exits 2 with argparse's own
     "unrecognized arguments" error — the flag is *gone*, not ignored.
  5. **Two tail-order changes.** `--justprint` used to call
     `ek.print_all_errors(...)` then `sys.exit(0)`; `--blank-slate` used to
     call `sys.exit(0)` with neither. Both now return a status through
     `cli.main`, so both additionally reach `logging.shutdown()` and
     `--blank-slate` additionally reaches `ek.print_all_errors`. The visible
     consequence: a warning buffered before `--blank-slate` ran (the PATH-`uv`
     warning is the realistic one) is now printed rather than discarded.
  6. **`cli.py` is the sole owner of veny's exit statuses.** Ledger item 4
     ("exit statuses were never designed as a set") is closed: 0 for a run
     that was not meant to launch anything, 1 for "could not find or build an
     environment", 2 for usage, otherwise the script's own status, with a
     signal death normalized to 128 + signal.
  7. **veny's last `ek.my_critical_error` call is gone — USER RULING, added
     mid-phase, not in the plan.** It sat on the failed-venv-build path with
     `choose_breakpoint=True`, and emmykit's helper calls `breakpoint()` in
     that mode. So a refused `uv venv` dropped the user into a `pdb` prompt,
     or died with a `BdbQuit` traceback under a non-tty — from a *build
     failure*, which is an ordinary operational outcome, not a bug to debug.
     It is now `logging.critical("Failed to create a virtual environment.")`,
     with the existing `script_exit_code = 1` carrying the status out through
     `cli.main`. **veny now has no `ek.my_critical_error` call anywhere**
     (verified 2026-08-19: `rg -n 'my_critical_error' src/` returns nothing).
     Two consequences worth knowing: on `configure_logging`'s degraded path
     (log files uncreatable) that CRITICAL now surfaces via
     `logging.lastResort` and loses its timestamp/LEVEL prefix; and veny now
     offers **no interactive debugging affordance anywhere** — if one is
     wanted back it should be an explicit flag, not a hidden mode of a
     failure path.

- **What 3e explicitly declined, each with the phase that owns it.** None of
  these is a defect 3e introduced.
  - **The `Options` drain itself.** No frozen dataclass was introduced; the
    `Settings` that already exists is still constructed twice in the moved
    code. **Owner: phase 4.**
    > **CLOSED 2026-08-21 by phase 4b's Task 6 (`7881aff`).** The class,
    > `src/veny/run_options.py` and the `cli.Options` re-export are all
    > deleted; `run_options` has left `tests/test_layering.py`'s `state`
    > layer, and `tests/test_state_values.py` asserts the class is gone.
    > Phase 4a had already drained it to fourteen fields across six commits;
    > 4b removed the last six, which were persistence payload, by replacing
    > the persistence. Measured 2026-08-22: one `Options` mention survives
    > under `src/` (`pipeline.py:218`, prose saying the copy-back is gone),
    > and one live constructor call survives anywhere —
    > `scripts/differential_3d.py:345`, which drives an *older tree* and
    > already says so in a comment.
  - **Design amendment 9** — `cache_search.find_match_dir_in_cache` keeps
    taking and mutating the `argparse.Namespace`, because its selection-policy
    writes reach disk through `ek.save_options_to_json`. That is the
    persistence change. **Owner: phase 4.**
    > **CLOSED 2026-08-21 by phase 4b's Tasks 1-3** (`0fdf720`, `a87da4b`,
    > `823d6a7`). `find_match_dir_in_cache` takes a
    > `Callable[[], state.LastUsed | None]` and performs **no** attribute
    > assignment on `args`; the `last_used`/`latest` writes are locals now,
    > because nothing serializes the namespace. The change is visible in
    > `scripts/differential_4b.py`'s hunk 2 (`args.latest` after a default run:
    > True on the old tree, False on the new one) — the fourth sanctioned
    > difference, which the task's own acceptance criteria had not listed
    > (corrected at `0c5324a`).
  - **`pathlibcutoff`'s two readers.** Both survived 3e untouched; the
    `Options.pathlibcutoff` one has merely moved file, from `cli.py` to
    `run_options.py`. **Owner: phase 4**, which must account for both.
    > **CLOSED 2026-08-21 by phase 4b's Tasks 3 and 4** (`823d6a7`,
    > `2057af0`); see the fuller note on the design-doc inaccuracy above.
  - **Removing the probe venv from classification** (design amendment 3). It
    moved into `pipeline.py` as `_probe_venv`, still injected, still building
    a real environment. **Owner: whichever phase owns that user-visible
    change** — still not assigned.
  - **The single-file reachability gap.** **Owner: a later `analysis/` plan.**
  - **The third pre-existing `AssertionError`.** `veny -y` with no script was
    fixed (deviation 2); nothing else in the crash ledger was.

> **DEFECT 2 FIXED 2026-08-21 by phase 4a Task 1** (a missing script is now a
> usage error, exit 2). **DEFECTS 1 AND 3 ARE STILL OPEN and are phase 4c's**;
> both were re-confirmed unchanged by 4a's Task 8 sweep.

- **Three latent defects 3e's STANDING CHECK surfaced, recorded and NOT
  fixed** — the phase was behaviour-preserving, and each is pre-existing at
  `08622a8`. Each is a real bug a user can hit.
  1. **`-y`/`--yes` never reaches `blank_slate`.** `argparse` gives the flag
     the dest **`yes`** (`src/veny/cli.py:86-87`), and the only site that
     consults it reads **`getattr(options.args, "y", False)`**
     (`src/veny/pipeline.py:483`). So the read is *always* `False` and
     `veny --blank-slate -y` still prompts. Both spellings re-measured
     directly on 2026-08-19; this is the one latent defect the sweep proved
     **from both directions**, and it has its own wiring-index rows. The
     signature is the asymmetry: the `getattr`'s *receiver* and *flag name*
     are both unpinnable (an attribute-less `object()` behaves identically),
     while its *default* is pinned precisely because the default is the only
     part anything ever consults. Two of the 30 OPEN HOLEs are caused by this
     bug and close the moment it is fixed, and a third
     (`pipeline.py:768` `blank_slate(Options())`) is labelled **Conditional**
     for the same reason.
  2. **A missing script leaves `FileNotFoundError` travelling uncaught out of
     `main`.** `pipeline.py:413` does `ek.ensure_file(...).resolve(strict=True)`;
     nothing catches it, so `veny /no/such/script.py` is a traceback rather
     than a status. Deliberately not pinned: with `strict=True` the only thing
     a test could assert is the traceback, which would make a traceback the
     contract. Fix it by catching, then pin.
  3. **`run_script(rawlog=…)` is passed and unread at three of its four call
     sites** (`pipeline.py:451`, `821`, `844`). `run_script` reads `rawlog`
     only to guard its announce line, and all three of those sites leave
     `announce` False. Six wiring-index rows, one cause. This is a *behaviour
     question* as much as a finding: if any of those three launches is ever
     meant to announce itself, `rawlog` becomes live there and the rows close
     on their own.

> **SUPERSEDED 2026-08-21 by phase 4a Task 8.** The list is five, not
> seventeen. Twelve closed when the values that carried them became arguments
> with live readers; the four `pipeline.py:125` `Settings` rows closed by
> construction (one Settings, two consumers). The survivors are the three
> `run_script(rawlog=…)` sites, the probe venv's `ResolvedImport(pip_name=…)`,
> and one non-substitutable expression. See
> `docs/superpowers/plans/2026-08-21-state-model-values-wiring-index.md`.

- **17 arguments measured DEAD — passed and never read. Phase 4 deletion
  candidates, not test gaps.** They are 17 of the 47 unpinned wiring-index
  rows (13 distinct arguments at six call sites), split out so the headline
  can read "30 genuine holes **plus** 17 findings" instead of blurring the
  two. No test can pin them; they should be deleted.
  - `pipeline.py:125` `Settings(my_name=…, cwd=…, stay_out_list=…,
    search_above_this_dir=…)` — `analysis.scan` reads **only**
    `settings.rawlog`. Four of five fields dead at that site.
  - `pipeline.py:222` `ImportScan(loaded_custom_modules=…, samedir_files=…,
    subfolders=…, sys_path_hints=…, seen_stdlib_imports=…)` —
    `classify.split_imports` reads only `all_imports`, `custom_modules` and
    `seen_stdlib_imports`, and `pipeline.split_imports` copies back only four
    result fields, so even `seen_stdlib_imports` is unobservable here.
  - `pipeline.py:201` `alias_index.ResolvedImport(pip_name=…)` — the
    single-record branch of `check_packages_in_venv` checks `import_name` and
    nothing else.
  - `pipeline.py:451`/`821`/`844` `run_script(rawlog=…)` — the third latent
    defect above; six rows, one cause.

> **CLOSED 2026-08-21 by phase 4a Tasks 6 and 8.** All five sites were inside
> `set_venv_dir`, which Task 6 deleted; `VenvHandle.for_dir`'s four
> replacements are counted in the 4a wiring index.

- **`run_options.py` has never been through the STANDING CHECK, and is
  counted in no number anywhere.** Task 8's brief scoped the sweep to
  `cli.py` and `pipeline.py`. `run_options.py` holds the `Options` class and
  **five argument-carrying call sites, all inside `set_venv_dir`** — which is
  exactly the implicit-write shape the check exists to catch, and the reason
  this is worth writing down rather than shrugging at. They are outside the
  458-argument accounting, outside the 278 substitutions, and outside the
  "47 unpinned" headline. **Owner: phase 4**, which touches that module
  anyway when it deletes it — and which must not read 3e's numbers as
  covering it.

- **RESIDUAL RISK carried out of 3e's differential (twenty-one items).**
  `scripts/differential_3e.py` drives seven layers through `main()` in both
  trees and reduces the whole phase to a **37-line diff** (re-run and
  reproduced verbatim at Task 10, 2026-08-19: 37 lines, 22 of them actually
  differing, six hunks under `diff -u`). It was mutation-tested — four
  deliberate regressions were each caught, growing the diff to 41, 53, 41 and
  59 lines. That is a strong result, and it is **not a clean bill of health**:
  a regression in any of the following would leave the diff at 37 lines.
  Items 1–20 are Task 9's list; **item 21 was added by its review**. Phase 4
  inherits every one of them.
  1. **`--feeling-lucky`.** No layer sets it. Its whole early-return path —
     `print()`-not-`logging` reporting, running *before* `ek.configure_logging`,
     and the change from `sys.exit(returncode)` to a status returned through
     `main()` — is entirely uncompared.
  2. **A scriptless, flagless run (deviation 2).** Layer 7 always passes
     `--blank-slate`, so the `UsageError`/exit-2 change rests on the unit
     suite alone.
  3. **`--full` beyond the argparse dest list.** The six deleted branches show
     up only as one missing dest name; their *behaviour* is not compared,
     because the new tree cannot accept the flag.
  4. **`environment.uv_binary`'s failure path** (deviation 1, first half).
     `uv_binary` is stubbed to a `<uv>` token, so `UvUnavailable` vs
     `SystemExit` — and `cli.main`'s stderr print plus status 1 — is never
     exercised.
  5. **`create_venv`'s failure path** (deviation 1, second half). Layer 5
     fails the *verification*, not the build. A `uv venv` that returns
     non-zero is untested by this driver. Driving the documented-but-unused
     `create_venv_ok=False` policy knob would close this one.
  6. **`_probe_venv`'s `VenvBuildFailed`, and `cli.main`'s handler for it.**
     The throwaway classification venv always builds here.
  7. **The real `verify.verify_and_repair_imports`.** Stubbed to a
     pass-through recorder, so ranking past candidate 0, `confirm()`/
     `reject()`, the alias-cache write and the requirements rewrite are all
     bypassed and layer 4's uv argv is shorter than production's.
  8. **The real `dict_of_custom_modules`.** Stubbed to `{}` — unstubbed it
     walks all of `sys.path`, which includes the tree under test, so its
     answer would differ between trees for a reason that is not behaviour.
  9. **The real `alias_index.build` and `stdlib_index.resolve`.** Stubbed.
     PyPI resolution, the override file, the alias cache and the interpreter
     probe are compared only through the arguments `main()` passes — the
     wiring, not the work.
  10. **`ek.configure_logging`'s real behaviour.** Replaced by a capture
      handler at INFO, so the log file, the memory handler and `--rawlog`'s
      effect on *formatting* are uncompared, and `--debug` is never driven —
      every `isEnabledFor(logging.DEBUG)` branch in both trees is dark.
  11. **Most flags are never passed.** `--rawlog`, `--debug`, `--reqs`,
      `--offline`, `--rc`, `--latest`, `--oldest`, `--smallest` and
      `--last-used` are read at their defaults only.
  12. **The `-y`/`yes` defect is visible but not diffed.** Both trees have it,
      so it produces no hunk — the capture documents it, the differential
      cannot flag it.
  13. **The uncaught `FileNotFoundError`.** No layer passes a nonexistent
      script, so the escape route out of `main` is unobserved in both trees.
  14. **Signal normalization.** The stand-in subprocess never returns a
      negative status, so `128 - script_exit_code` is never evaluated.
  15. **The last-used cache path.** `_load_last_used` always finds no JSON, so
      `check_venv_dir`'s no-candidate branch, `load_last_used_options`' sort
      and the last-used *hit* are all uncompared. Layer 2 sees only the miss
      that falls through to `latest`.
  16. **What veny writes between runs.** `ek.save_options_to_json` is stubbed
      to record its `venv_dir`, so the options JSON — the file
      `--feeling-lucky` and the last-used search later read — is never
      compared.
  17. **stderr from inside `main`.** Only stdout is diffed, so the one thing
      veny prints to stderr from `main` (the `UvUnavailable` message) would
      not appear even if item 4 were driven.
  18. **argparse's own exits.** `-v/--version` and the empty-argv help path
      both `sys.exit(0)` inside `parse_arguments`; no layer drives either.
  19. **Cross-layer timing.** The clock resets per layer, so a baseline that
      moved *within* a layer is visible, but a change shifting every layer's
      clock equally would not be.
  20. **Anything below the module boundary both trees share.** Ten of veny's
      modules are byte-identical between `08622a8` and `a874f3d`; this
      differential can only confirm that `main()` still reaches them the same
      way, never that they are correct.
  21. **Message *ordering* is uncompared in layers 1 and 7.** Added by Task
      9's review: those two layers **sort** their captured log records before
      emitting them, so a change that reordered two messages within either
      layer would produce no hunk. The other five layers keep emission order.

> **FINDING 1 DECIDED AND EXECUTED 2026-08-21 by phase 4a Task 1** (user
> ruling: delete the branch, do not revive it; the 16 rows are retired).
> **FINDING 2 (the in-virtualenv guard) is still open and is phase 4c's.**

- **Two findings from 3e's whole-branch review (2026-08-20) that phase 4 owns.
  Both are behaviour questions, not test gaps, and neither was fixed on the
  branch because 3e is behaviour-preserving.**
  1. **Folder scanning is dead code, and phase 4 must decide whether to revive
     it or delete it.** The symbols: `get_all_imports` (`pipeline.py:322-358`),
     `stayed_out_dir` (`:315-319`), and the `elif ek.safe_is_dir(...)` /
     `else: raise FileNotFoundError` arms of `list_packages` (`:291-301`) —
     about 55 lines. **Why they are unreachable:** `options.python_script` is
     written in exactly one production place, `pipeline.resolve_target`
     (`pipeline.py:409-416`), and that write goes through
     `ek.ensure_file(...)`, which raises `IsADirectoryError` for a directory.
     Before Task 5 the branch was reachable only because the `--full` arm
     assigned `options.python_script = options.cwd`; deleting `--full` deleted
     the only producer of a directory. **The plan says the opposite** — Task
     5's fourth acceptance criterion, ticked, reads "a directory is still
     reachable as a positional argument", which is false; it now carries an
     `[EXECUTION]` correction. **Why this matters beyond the dead lines:**
     `tests/test_import_discovery.py:224`
     (`test_list_packages_walks_a_folder_and_stays_out_of_the_named_directories`)
     reaches the code only by assigning `options.python_script` directly at
     `tests/test_import_discovery.py:254`, bypassing `resolve_target` — and
     that test is the **only** named killer for **16 rows** of the wiring index
     (`docs/superpowers/plans/2026-08-19-pipeline-and-cli-slimming-wiring-index.md`,
     every row for `pipeline.py:291`, `:297`, `:317`/`:318` and `:326`-`:346`).
     Those 16 kills are real kills that pin code no production run reaches. The
     decision phase 4 owes: **either** make `resolve_target` accept a directory
     — restoring folder scanning as a real feature, with its own tests and a
     live run — **or** delete the branch, its helpers and those 16 rows. Do not
     leave it as it is and count the rows as coverage. **Do not "fix" this by
     deleting the code inside a behaviour-preserving phase.**
  2. **The in-virtualenv guard asks about the wrong process: what does
     "already in a virtualenv" mean when veny itself lives in one?**
     `last_used.is_virtualenv()` is `sys.prefix != sys.base_prefix`, which
     describes **veny's own interpreter**, not the user's shell. veny's own
     documented install (`uv tool install veny`, `README.md:16` and
     `environment.py`'s `UvUnavailable` message) puts veny in a venv, as does
     `scripts/smoke-install.sh:33-34`. In any such install the guard is
     **always True**, so every run with a non-empty `uninstalled_imports` takes
     the middle branch of `pipeline.run` (`pipeline.py:830-861`), import-checks
     veny's own tool venv, fails, logs "Please deactivate the current virtual
     environment and run the script again." and returns 1 — leaving the cache
     search and `setup_virtualenv` unreachable. **Not a regression** (at
     `08622a8` the same input hit `assert options.venv_dir is not None` and
     crashed), but design amendment 14 and sanctioned deviation 3 overstated
     what Task 6 fixed; both now carry the qualifier. **The minimal fix the
     review identified:** gate on `os.environ.get("VIRTUAL_ENV")` — the user's
     own statement of which environment they activated, which is already what
     `last_used.active_virtualenv_dir()` prefers — rather than veny's
     `sys.prefix`. That is a **behaviour change**: it needs its own tests
     (both directions: veny-in-a-venv with no `VIRTUAL_ENV` must fall through
     to the cache, and an activated `VIRTUAL_ENV` must still be checked) plus a
     live run **from a tool-install shape**, not from `pixi run`. **USER
     RULING, 2026-08-20: record now, fix in phase 4.** **Why the phase's
     end-to-end evidence is blind to it:** both closing live runs used `pixi
     run veny`, and a conda env has `sys.prefix == sys.base_prefix` — the one
     install shape where the guard is False and the branch is skipped
     entirely. Any future live run meant to exercise this branch must not use
     `pixi run`.

- **`--feeling-lucky` skips the signal normalization, and that is deliberate
  only by accident** (recorded by 3e's whole-branch review, 2026-08-20; not
  fixed). `cli.main` normalizes a signal death to 128 + signal at its tail, but
  the `--feeling-lucky` path returns `pipeline.feeling_lucky`'s status directly
  from the middle of the function, before that tail. So a lucky run killed by
  SIGKILL returns **-9**, which the shell wraps to 247, while the same script
  on the ordinary path returns 137. The behaviour matches `08622a8` exactly —
  only the *prose* was new and wrong, since Task 6's ledger item 4 ("`cli.py`
  is the sole owner of veny's exit statuses") wrote a `main()` docstring
  promising the normalization unconditionally. The docstring now states the
  asymmetry; the behaviour is untouched. Whoever fixes it should route the
  lucky status through the same tail rather than duplicating the arithmetic.

- **3e's deferred minors, none blocking.** Recorded because the per-task
  reports are scratch and are deleted with the phase.
  - Task 2's mutation 1 kill is incidental (`venv_python` is None on that
    branch), so the assertion is not proved to distinguish a valid venv
    interpreter; blank-slate filter clauses 2 (`.err`) and 3
    (`_custom_modules_*.pkl`) are unpinned; the `--blank-slate` confirmation
    guard itself is unpinned (the prompt is stubbed `True` only); `captured`
    is bound and unused in all six new tests (**partly closed 2026-08-20** by
    3e's whole-branch review, which fixed the one site where *both* names were
    dead —
    `test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone`,
    now `_, _ =`. The other five still bind `captured` and never read it, so
    **nothing in the suite reads `_drive_main`'s first return value at all**;
    ruff's F841 exempts tuple unpacking, so no gate catches it); the
    cache-hit/cache-miss tests
    depend on the ambient interpreter not being a virtualenv; and the
    restated docstring's second failure mode (`match_dir` left unset) is
    reasoned rather than mutation-demonstrated.
  - `cli.py`'s `ResolvedImport` re-export comment is no longer true — only
    `tests/test_split_imports.py` uses it. (~~`tests/test_classify.py:487`'s
    docstring still says "cli.py's own `also_needs` table"~~ — **CLOSED
    2026-08-20** by 3e's whole-branch review. Note for the record that it was
    *not* already closed on the branch, as the review first believed: the
    branch had repointed only the docstring's first line (`cli.split_imports`
    → `pipeline.split_imports`), leaving the body's "cli.py's own `also_needs`
    table" behind. The table has lived in `run_options.Options.__init__` since
    Task 1 (`e5dfced`), so the phrase was stale; the docstring now names
    `run_options.Options.__init__`.)
  - **`run_script`'s `announce` argument: pinned, nothing outstanding**
    (checked 2026-08-20 while pruning this list — 3e's whole-branch review
    listed "Task 4's unpinned `announce` branch" as a deferred minor to close,
    but **no such entry was ever written into this file**, so there was nothing
    to prune). Recorded here so the next reader does not go looking: all four
    `announce` rows in the wiring index are accounted for —
    `test_only_the_venv_launch_announces_the_command_it_is_about_to_run` kills
    the `announce=True` probe at `pipeline.py:451`, `:821` and `:844` and the
    `announce=False` substitution at `:909`, and the `announce=True` row at
    `:909` is an identity substitution. What is still open on that argument is
    a different thing entirely and is already recorded above as latent defect
    3: `rawlog` is a DEAD ARGUMENT at the three sites that leave `announce`
    False.
  - `pipeline.run` is **240 lines**; its acquired-venv tail (~85) is the next
    extraction candidate. ~~Its `Raises:` documents `UsageError`/
    `VenvBuildFailed` that this tree never raises from there~~ — **that clause
    was wrong and is withdrawn (2026-08-20, 3e's whole-branch review).** It was
    transcribed unrevised from a pre-Task-5 note. `run` raises `UsageError`
    **in its own body** (`pipeline.py:770`, the no-script-and-no-`--blank-slate`
    arm), and `VenvBuildFailed` really does travel through it — `_probe_venv`
    raises it at `pipeline.py:185`, reached via `run` → `list_packages` →
    `pipeline.split_imports` → `classify.split_imports`. Both `Raises:` entries
    are therefore correct and must not be deleted. What *is* still true in that
    sentence: `cli.main`'s `return 2` / `return 1` handlers skip
    `print_all_errors` and `logging.shutdown`.
    ~~`_drive_main`'s docstring is stale ("main() is 400 lines of sequencing")
    and its `venv_dir=` keyword is now dead — no caller passes it.~~ —
    **both CLOSED on the branch, verified 2026-08-20**: `rg -n '400 lines'
    tests/ src/` returns nothing (the docstring was rewritten to describe the
    post-3e split), and `_drive_main`'s signature is
    `(monkeypatch, tmp_path, argv, *, uninstalled, all_imports, script_args=())`
    — no `venv_dir` parameter survives.
  - ~~**`test_a_run_with_no_script_is_a_usage_error`'s docstring
    (`tests/test_cli_entry_point.py:826-834`) names a crash site that no
    longer exists.** … Fix the docstring to name the `TypeError` in
    `run_script`, or name both with their commits.~~ — **THIS LEDGER ENTRY WAS
    ITSELF WRONG. Withdrawn 2026-08-20 by 3e's whole-branch review; the
    docstring is correct and must NOT be changed.** The docstring describes the
    **shipped** behaviour at `08622a8`, which is what a "concrete bug this
    catches" clause is supposed to describe: at that commit `cli.py`'s
    no-script fall-through really did reach `list_packages`, whose **first
    statement** is `assert options.python_script is not None` (verified:
    `git show 08622a8:src/veny/cli.py`, line 862). The `TypeError: expected
    str, bytes or os.PathLike object, not NoneType` that Task 5 observed was a
    **harness artifact, not the shipped crash**: `_drive_main` has replaced
    `list_packages` with a stub since Task 2 (`5acb137`), so under the harness
    the assert was substituted away and the run travelled on to `run_script`.
    Applying the "fix" this entry asked for would have made a correct docstring
    wrong — it would have pinned the test's rationale to a failure mode no user
    can reach. **The transferable lesson:** when a deferred minor claims a
    docstring names a crash that "no longer exists", check whether the
    observation came from a stubbed harness before believing it, because a stub
    can delete the very statement the docstring is about.
  - **Task 5's report overstated its `VenvBuildFailed` symmetry argument** —
    it compared handlers as though they logged at the same level, when one is
    **ERROR** and the other **INFO**. The conclusion it drew is still correct;
    only the supporting argument was wrong. Recorded so that anyone reusing
    that reasoning to justify a further change re-derives it rather than
    inheriting the flaw.
  - `cli.main`'s `UvUnavailable` handler prints but does not log, so the
    common raise site (after `configure_logging`) misses `print_all_errors`.
    `environment.create_venv` catches `CalledProcessError` but not `OSError`,
    unlike its sibling `run_uv_pip`; `verify.check_packages_in_venv` is the
    same. `classify.split_imports` propagates `VenvBuildFailed` with no
    `Raises:` section. `tests/test_cli_entry_point.py` hardcodes a copy of the
    `UvUnavailable` message with nothing pinning the two texts together.
  - ~~The in-virtualenv success side asserts status only, never `launched` —
    which interpreter runs the script there is unpinned.~~ — **CLOSED on the
    branch, verified 2026-08-20** by
    `test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it`, which
    asserts the whole launched command, not just the status.
  - The wiring index's constants list drops `/tmp/wrong-venv` while 23 kill
    rows still cite it, and its before/after table drops sweep 2's row
    (202/39/8 at `4033c75`) which the prose still references. Summary/rows
    mismatch only; no verdict is at risk.
  - `scripts/differential_3e.py`: three policy knobs (`create_venv_ok`,
    `uv_returncode`, `script_status`) are documented but never driven; the
    interpreter probe dispatches on `"-c" in argv`, which is fragile if a
    future layer passes `-c` as a script argument; the driver's own
    usage/error diagnostics go to stdout, breaking its own stderr rule (misuse
    path only); and layer 6 shows the new tree verifying `venv_python_for(active)`
    but launching `sys.executable` — the same interpreter in production, an
    artifact of the stub.

- **Design ledger item 2 is CLOSED by 3d's Task 7** (`93bca53`, `f961ada`).
  The item, escalated from `venv-cache`'s whole-branch review (2026-08-14) as
  needing a design decision: `satisfies()` ran twice on the winning candidate,
  and the manifest was read twice with it. Both redundancies are gone on the
  winning-candidate path. `cache_search.find_match_dir_in_cache` now keeps the
  whole `CacheCandidate` for each ranked folder — not just the folder — and
  passes it into `check_venv_dir` as **`candidate`** (the parameter went
  `manifest` → `matched_manifest` in the fix round, to make the trust contract
  explicit in the name, and then → `candidate: CacheCandidate | None` after the
  whole-branch review, to make it explicit in the *type*: a `CacheCandidate`
  can only come from `cache_candidates`, which has already read that folder's
  manifest and run `satisfies` on it). Measured, per cache hit: **1 `read_manifest`, 1 `satisfies`**, down
  from 2 and 2, pinned by
  `test_a_cache_hit_reads_and_matches_each_manifest_once`
  (`tests/test_cache_search.py:442`); the last-used side has its own,
  `test_a_last_used_hit_still_reads_and_matches_its_own_manifest`
  (`:674`), and the vanishing-manifest case is
  `test_check_venv_dir_survives_the_manifest_vanishing_after_it_was_already_read`
  (`:536`). The **last-used path still
  does its own 1 read / 1 satisfies** and must: it has no `CacheCandidate`,
  because it is reached from a recorded pointer rather than from the scan.
  A folder that loses its manifest between the scan and the check is still
  handled, and what happens is now pinned by a test rather than assumed.
- **The mypy ceiling moved for the first time: 37 → 36.** Measured both ends on
  2026-08-18 — `main` @ `dc1c3c4` gives `Found 37 errors in 5 files (checked 37
  source files)`, `classify-and-environment` @ `332d69e` gives `Found 36 errors
  in 5 files (checked 42 source files)`. The per-file breakdown is otherwise
  identical: `src/veny/cli.py` 10, `analysis/imports.py` 3,
  `analysis/literals.py` 1, `analysis/call_graph.py` 1. The whole delta is
  `tests/test_split_imports.py`, **22 before 3c and 21 after** — the
  twenty-second moved to `tests/test_classify.py` with its test and was
  annotated there, so the two new test modules and the three new source
  modules contribute **zero**. Leaving the remaining 21 was a decision taken
  during 3c's *planning*, not an oversight found afterwards. Where they live,
  measured by enclosing function: **17 are 3d's territory** — 11 in the
  `resolve_and_verify` tests (`_RecordingIndex` passed where `AliasIndex` is
  declared, plus `Candidate | None` dereferences), 2 in
  `_run_check_against_fake_venv` (the `check_packages_in_venv` helper, an
  untyped def), 4 at `_live_index`'s `AliasIndex(**fields)` construction. The
  **other 4 are not**, and 3d will not clear them by rewriting `verify.py`'s
  tests: 2 in `test_enqueue_top_level_imports_records_stdlib_and_skips_enqueue`
  (bare `set` / `deque` annotations, a scan-layer test that belongs with
  `analysis/scan.py`) and 2 in the `build_alias_index` offline/online pair
  (`options.python_command = None` against a `str`-declared field).
  **Updated 2026-08-18 after 3d: the ceiling is now 33**, measured on
  `verify-cache-search-last-used` @ `7debbb3` — `Found 33 errors in 6 files
  (checked 49 source files)`. It has never been this low. Breakdown:
  `tests/test_verify.py` 15, `src/veny/cli.py` 7,
  `tests/test_split_imports.py` 6, `analysis/imports.py` 3,
  `analysis/literals.py` 1, `analysis/call_graph.py` 1. Two corrections to the
  prediction above, both worth carrying: 3c predicted **17** of
  `test_split_imports.py`'s errors would travel to `tests/test_verify.py` with
  the migrated tests; **15** actually did (21 → 6 in the source file). The two
  that did not are `_run_check_against_fake_venv`'s untyped-def pair: the
  helper now exists in **both** files — the migrated copy in
  `tests/test_verify.py:553` was given type hints and contributes zero, while
  the untyped original stayed at `tests/test_split_imports.py:145` for the one
  test still using it (`:218`) and kept its 2 errors there. A migrated helper
  can be typed on arrival even when the migration is meant to be verbatim, and
  a duplicated helper means the prediction's arithmetic never balances.
  And `src/veny/cli.py` fell 10 → 7 without anyone typing it —
  the three errors went with the code that left the file (Task 8's `f0a1bc4`
  cleared the `rename_venv` block by asserting at the call site). The three
  new source modules and the two new test modules contribute **zero**, the
  standard 3c set and 3d held.
- **`Requirements.seen_stdlib` and `Requirements.extra_requirements` are
  pass-throughs**, not products: classification neither computes nor changes
  them (the first is copied off the scan, the second is the caller's own
  `--reqs` input), and they travel on `Requirements` only because later stages
  need them alongside the classification. 3e should decide whether they stay
  there once `pipeline.py` owns sequencing, or are carried separately.
- **RESIDUAL RISK carried into 3d from 3c's differential.** Both differentials
  came back empty and the check was proved able to fail, but the evidence is
  bounded and the bounds matter more than the empty diff:
  - `environment.write_requirements_file_with_extras` is **entirely uncovered
    by the differential**. The argv differential pins `uv pip install --python
    … -r requirements.txt`, but nothing pins that file's **contents** — a
    mis-sort, a dropped version specifier or an omitted extra produces a
    byte-identical argv diff and installs the wrong versions. It has unit
    tests; it has no old-vs-new comparison. **Narrowed 2026-08-18 (`19702c8`),
    not closed:** both production call sites now have a test asserting the
    written file's *contents* carry a specifier that could only have come from
    `options.extra_requirements`
    (`test_setup_virtualenv_writes_the_extra_requirements_version_specifiers`,
    `test_a_repair_rewrites_requirements_txt_with_the_extra_requirements`), so
    a dropped specifier is caught by a test even though the differential still
    cannot see it. The sort order and the multi-extra case remain
    unit-tested only.
  - Everything downstream of `list_packages` — the install→probe→uninstall
    verification loop, `venv_cache` naming, manifest writing — is never driven
    old-vs-new.
  - The online alias-resolution path is excluded, by `offline=True`.
  - Interpreter selection is bypassed (`python_command = sys.executable`), so
    `environment.venv_build_interpreter`'s `shutil.which() is None` fallback
    and `create_venv`'s no-`--python` branch are never taken.
  - Non-default CLI shapes (`--full`, the debug branches, the custom-module
    pickle cache) are outside the comparison.
  - Whether `Requirements` shares or copies its frozensets is invisible unless
    it changes a final value.
  **Narrowed by 3d's differential (2026-08-18), not closed** — see the 3d
  entry below for the current bounds. Three of the six items above moved:
  `write_requirements_file_with_extras`' output **contents** are now compared
  (sort order and the multi-entry `extra_requirements` case included);
  `install_into_venv`'s success predicate is now compared on all three
  outcomes (`returncode=0`, `returncode=1`, raising), closing the specific gap
  named below; and the cache-search decision is compared at all, which 3c did
  not attempt. The other three stand.
- **RESIDUAL RISK carried into 3e from 3d's differential (ten items).** 3d's
  driver is **committed** this time — `scripts/differential_3d.py`, with
  `PYTHONHASHSEED=0` set *inside the script*, `sys.dont_write_bytecode = True`,
  a `__pycache__` purge before the first import, the tree root taken as an
  argument rather than through `PYTHONPATH`, and `veny.cli.__file__` printed
  first. Layers 1 and 2 came back **byte-identical**; layer 3 shows only the
  sanctioned Task 7 divergence (one fewer `read_manifest`, one fewer
  `satisfies`) with the chosen folder and the flag write-back identical. The
  check was proved able to fail **six** times by deliberate mutation. As
  always, the bounds matter more than the empty diff:
  1. **The import-level confirmation is stubbed, not driven.**
     `check_packages_in_venv` is replaced in both trees, so its own internals
     — the alternatives list, the PEP 503 fallback,
     `run_import_check_in_venv`'s generated snippet — are never compared
     old-vs-new. They have unit tests; they have no differential.
  2. **The repair loop never runs.** With the bulk check answering `True`,
     `verify_and_repair_imports` returns before `repair_unsatisfied_import`,
     `resolve_and_verify`, `confirm_if_attributable` and the requirements
     rewrite. The whole install→probe→uninstall verification loop is outside
     the comparison — the same shape as 3c's "everything downstream of
     `list_packages`".
  3. **`record_venv_state` and manifest writing are not compared.** Layer 2
     drives `setup_virtualenv`, which calls it, but the driver records only
     the uv argv and the requirements file — not the folder rename or the
     manifest bytes. `cache_search.manifest_for`'s output is unverified
     old-vs-new.
  4. **The online alias-resolution path is excluded** (`pypi=None`, fixed
     seed), as in 3c.
  5. **Interpreter selection is bypassed** (`python_command = ""`), so
     `venv_build_interpreter`'s `shutil.which() is None` fallback and
     `create_venv`'s no-`--python` branch are never taken.
  6. **`alias_index.probe_interpreter` is pinned** to `("3.12", {})`, so
     `import_names_by_distribution` and every attribution decision built on it
     are constant rather than compared.
  7. **The last-used *hit* path is never exercised** — layer 3's script
     directory holds no last-used JSON, so `load_last_used_options`'
     timestamp filtering, the `pathlibcutoff` comparison and
     `check_venv_dir` with no `candidate` against a real last-used pointer
     are all unreached. This is the **one branch of the four whose
     `candidate` handling differs** — exactly the code Task 7 changed —
     and the differential sees only its miss. It has unit tests and it was
     exercised by Task 10's second live run; it has no old-vs-new comparison.
  8. **Non-default CLI shapes** (`--full`, `--blank-slate`, `--justprint`,
     `--debug`, the custom-module pickle cache, `--reqs` at layer 1) are
     outside the comparison.
  9. **`smallest_venv` is still not distinguishable, measured.** The fix round
     added a fourth cache folder so the chosen folder now names which ranking
     ran, and a `latest_venv` → `oldest_venv` swap is caught. What genuinely
     remains: `latest_venv` → **`smallest_venv`** still does **not** move the
     chosen folder (`…040404` either way), because both surviving fake-cache
     folders carry exactly one package, so their `num_packages` **tie** and
     the tie-break returns the first folder encountered. Distinguishing
     `smallest` needs a survivor with a different package count. And only the
     `--latest` branch is driven by the differential at all — `--oldest` and
     `--smallest` are reached by the unit tests only.
  10. **`main()` itself is never driven by the differential.** The layers call
      `list_packages`, `setup_virtualenv` and `find_match_dir_in_cache`
      directly. `main()`'s sequencing is covered by the tests Task 9 added
      instead, not by an old-vs-new comparison — which is a weaker guarantee,
      and is the same blind spot that let 27 of `main()`'s arguments go
      unpinned in the first place.
- **3d's deferred minors, none blocking.** Recorded here because the per-task
  ledger they came from (`.superpowers/sdd/2026-08-18-verify-cache-search-last-used/`)
  is gitignored scratch and is deleted when the phase finishes.
  - `tests/test_verify.py`'s bulk-branch test uses a literal `/tmp` path with
    `set_venv_dir` (which has an `mkdir` side effect) instead of `tmp_path`.
    Plan-mandated wording; worth switching whenever that test is next touched.
  - **`environment.venv_python_for` now calls `ek.ensure_dir` on the path that
    `cli.venv_python_for`'s `options` branch did not** — a widened
    precondition. Unreachable today (every caller passes a directory that
    already exists), but it is a real difference introduced by amendment 11's
    move, and **phase 4's `VenvHandle` inherits it** when it replaces the
    function.
  - `assert options.requirements_file is not None` appears **twice** in
    `cli.setup_virtualenv` (mypy re-narrowing). The second site wants a
    one-line comment saying why.
  - Commit `c0510da` swept a dirty `tasks.json` in via `git add -u`. Later 3d
    tasks used explicit paths; **keep doing that** — `git add -u` is how an
    unrelated tracker edit lands in a refactor commit.
  - `tests/test_manifest_writing.py`'s `manifest_kwargs` helper has no type
    hints. (`f0a1bc4` typed it — **resolved**, listed here only so the ledger
    entry is not lost silently.)
  - **Corrected while closing the phase, 2026-08-19.** The per-task ledger
    recorded a now-dead `# noqa: S603` on
    `cache_search.installed_state_in_venv`, and an earlier draft of this
    entry repeated it. Measured at HEAD: `rg 'noqa' src/veny/cache_search.py`
    returns **nothing** — the comment did not survive the task it was logged
    in, so there is nothing to remove there. The same redundancy **does**
    exist one module over and is still open: `src/veny/environment.py:245`
    carries `# noqa: S603` while `pyproject.toml:61` already grants
    `"src/veny/environment.py" = ["S603"]`. Measured, not inferred: deleting
    that comment in place leaves `pixi run lint` reporting `All checks
    passed!`, and the file was restored from a scratch copy afterwards with
    `git diff` empty. The two other `# noqa: S603` comments in the tree —
    `alias_index.py:523` and `stdlib_index.py:117` — are **load-bearing**,
    because neither module has a per-file ignore; do not sweep them together.
  - `tests/test_classify.py`'s `_capture_split_imports_result` inner wrapper
    takes `*args`/`**kwargs` typed `Any` rather than mirroring
    `classify.split_imports`' signature, so it would not catch a signature
    drift.
  - `pyproject.toml` gained one per-file-ignore for `scripts/differential_3d.py`
    (`ANN401`, `S606`), with the reasoning inline — check it still applies if
    that script is ever generalized beyond 3d.
  - The differential driver used to print its `__pycache__` purge count to
    stdout, adding a third diff hunk that varied with how recently the tree
    had been tested. Diagnostics now go to **stderr**; any future driver
    should do the same from the start.
- **Named for 3d to pick up, from 3c's execution.** None blocking.
  - ~~`cli.add_dependencies` has **zero production callers**~~ — **resolved by
    the whole-branch fix wave, 2026-08-18 (`143f909`), not deferred to 3d.**
    The review measured the consequence rather than only the fact: with the
    adapter dead, `also_needs=options.also_needs` → `{}` at `cli.py`'s
    `classify.split_imports` call left the whole suite green, so dependency
    expansion was unpinned on the path users take. The adapter is deleted, its
    three tests repointed at `classify.add_dependencies` with assertions
    untouched, and `test_split_imports_expands_also_needs_onto_the_uninstalled_records`
    (`tests/test_classify.py`) now drives a **nested** chain through
    `cli.split_imports` — which also closes the corpus gap recorded below.
  - **`PYTHONHASHSEED=0` is load-bearing for the differential's argv
    comparison but lives outside the driver.** The technique write-up in
    Gotchas names it, and 3c's runs set it, but the driver scripts are
    throwaway `/tmp` files that were never committed — so nothing in the
    repository carries it (`rg -n 'PYTHONHASHSEED' .` hits only `PROGRESS.md`,
    measured 2026-08-18). Whoever runs 3d's differential must set it
    themselves; a driver that iterates a `set` without it produces argv
    orderings that differ between two runs of the *same* tree, which reads as
    a regression that is not there. If 3d commits its driver, the env var
    should go in the driver, not in the invocation.
    **CLOSED by 3d (`32a12f7`):** the driver is now
    `scripts/differential_3d.py`, tracked in git, and it sets
    `PYTHONHASHSEED=0` inside the script. `rg -n 'PYTHONHASHSEED' .` now hits
    the driver as well as this file.
  - **`install_into_venv`'s success predicate is never compared by the
    differential** — the driver's fake `subprocess.run` always returns
    `returncode=1` and the driver discards the return value, so the
    `result is not None and result.returncode == 0` logic is invisible to it
    in both trees. Unit tests cover it; the old-vs-new comparison does not.
    3d owns `verify.py`, which is where that predicate's callers live.
    **CLOSED by 3d's Task 9:** the driver's fake `subprocess.run` now returns
    `returncode=0` for at least one case and the return value is compared, so
    all three outcomes (`returncode=0`, `returncode=1`, raising) are covered
    old-vs-new.
  - **`cli.load_last_used_venv_dir` (`src/veny/cli.py:1867`) has zero
    references anywhere in `src/` or `tests/`** — definition only. Verified
    2026-08-18 at both ends: `git grep -n 'load_last_used_venv_dir' dc1c3c4 --
    src tests` returns only its `def` at `cli.py:2197`, so it was **already
    dead at the branch point** and 3c neither created nor killed it. For
    whoever owns `last_used.py` in 3d: delete it, or state why it stays.
    (Ruff does not flag an unused module-level function, so nothing will ever
    report it — the same blind spot as `_index_with` below.)
    **CLOSED by 3d's Task 5 (`0943370`): deleted, not moved.** The symbol
    exists nowhere in `src/` or `tests/` at `7debbb3`. The `cli.py:2197 @
    dc1c3c4` citation above is the commit-qualified historical form and is
    still correct *because* it is qualified — the unqualified
    `src/veny/cli.py:1867` in this entry's first line is dead and is recorded
    in the citation sweep below.
  - `tests/test_split_imports.py:314`'s `_index_with` is dead — zero
    references, verified 2026-08-18. Ruff does not flag unused module-level
    functions, so nothing will ever report it. **CLOSED by 3d's Task 8
    (`e430a37`): deleted.**
  - `tests/test_classify.py` carries two near-duplicate resolve-recording
    helpers (`_RecordingIndex` at :57, `_CountingIndex` at :558) and two
    probe-stubbing idioms — an artifact of the mandated verbatim migration.
    Consolidate in 3d. **CLOSED by 3d's Task 8 (`e430a37`):** one recording
    helper (`_RecordingIndex`, now at `tests/test_classify.py:62`), one
    probe-stubbing idiom. Task 8 also hit something its brief did not
    anticipate — **five live `installed_imports` readers in
    `tests/test_classify.py`**, where the brief expected the chain to be
    write-only everywhere; they were rewired onto the `Requirements` product
    rather than deleted.
  - `state.Requirements.extra_requirements` stores the caller's `Mapping` by
    reference, so `frozen=True` is shallow and the auto-generated `__hash__`
    would raise on a `dict`. Nothing hashes a `Requirements` today.
  - `state.py` has no `from __future__ import annotations`. (The per-task
    ledger called it the only top-level module in `src/veny/` without one;
    measured 2026-08-18, that is wrong — `cli.py` and `settings.py` lack it
    too. `state.py` is the only *new* module of 3c that lacks it.)
  - `classify.py:139`'s `known_bad_imports` is typed `set[str]` but never
    mutated; `AbstractSet[str]` is the honest type. (Line re-measured at
    `7debbb3`: still `classify.py:139`. Still open.)
  - The copy-back guard proves **totality**, not source correctness:
    rewriting the adapter as `options.bad_imports = set(result.installed)`
    still passes it. (Cited as `tests/test_layering.py:320`; re-measured at
    `7debbb3` it is `test_split_imports_copies_back_every_field_it_owns` @
    `7debbb3:tests/test_layering.py:337` — name and line both read straight
    off the file, and confirmed identical at `7debbb3` and at HEAD. 3d's
    Task 8 narrowed the guard from five fields to **four** when the
    write-only `installed_imports` chain went; measured at
    `tests/test_layering.py:388-393`, the asserted set is exactly
    `{all_imports, bad_imports, uninstalled_imports, total_imports}`.
    Still open.)
  - The three-assert block plus the `pip_name` generator are duplicated at both
    `write_requirements_file_with_extras` call sites in `cli.py`
    (`1542`-`1555` and `1748`-`1761`); the
    `assert options.uninstalled_imports is not None` in
    `verify_and_repair_imports` is dead, since the attribute is dereferenced
    two lines above it. **CLOSED by 3d's Task 3, structurally rather than by
    de-duplication:** the two call sites are no longer both in `cli.py`. One
    is `cli.setup_virtualenv` @ `7debbb3:991-999` (it still carries the three
    asserts, because `Options`' fields are still `| None`); the other left the
    file with the code, and is now
    `verify.verify_and_repair_imports` @ `7debbb3:src/veny/verify.py:675`,
    which takes `requirements_file` and `extra_requirements` as explicit
    non-optional arguments and therefore needs **no** asserts at all. The dead
    `assert options.uninstalled_imports is not None` went with the move. The
    remaining three asserts in `cli.py` die with the `Options` drain in 3e.
- **The 3d stale-citation table below is COMMIT-QUALIFIED, and 3e moved its
  right-hand column again — do not re-resolve it, read it as history.** 3d's
  sweep rewrote every citation as `symbol name @ 7debbb3:<line>`, which is why
  it is still *readable*: the sha pins each line to a tree that still exists in
  git. But 3e removed a further 858 lines from `cli.py` (1,064 → 206) and every
  symbol in that table except `parse_arguments` and `main` now lives in
  `src/veny/pipeline.py` or `src/veny/run_options.py`. To find one today,
  resolve the symbol name, not the line: `rg -n '<symbol>' src/veny/`. The
  general rule 3d learned holds and is reinforced — **a citation without a sha
  rots at the next extraction, and a citation with one never does** — with the
  3e-specific corollary that the *file* in a qualified citation ages too, so
  cite the symbol as the primary key and the file as commentary. No re-sweep
  was run at 3e's close: the table's citations are all sha-qualified and
  therefore not wrong, only historical.
- **Stale-citation sweep: DONE by 3d's Task 10, 2026-08-18.** The sweep was
  named for 3d because the citations were already stale; every one of them
  then moved **again** under this phase, which removed 1,232 lines from
  `cli.py` (2,296 → 1,064). Each was re-measured against
  `verify-cache-search-last-used` @ `7debbb3` and rewritten as
  **`symbol name @ <sha>:<line>`** — the commit-qualified form the existing
  `cli.py:2197 @ dc1c3c4` citation already used, and the reason that one
  citation is *still* correct while every unqualified neighbour rotted.

  | was | symbol | now, at `7debbb3` |
  |---|---|---|
  | `veny.py:1478` | `options.python_command = ek.find_preferred_python_version()` | `cli.main` @ `7debbb3:409` |
  | `cli.py:537` | `options.custom_modules = dict_of_custom_modules(...)` | `cli.main` @ `7debbb3:520` |
  | `cli.py:552` | `list_packages(options)` | `cli.main` @ `7debbb3:535` |
  | `cli.py:124` | `Options.__init__`'s `self.search_above_this_dir = True` | `cli.Options.__init__` @ `7debbb3:69` |
  | `cli.py:229` | `Options.set_venv_dir` (the `mkdir` side effect) | `cli.Options.set_venv_dir` @ `7debbb3:173` |
  | `cli.py:461` | the `--reqs` block in `main()` | `cli.main` @ `7debbb3:501` |
  | `cli.py:462` | the dict-invariance mypy error at `options.extra_requirements = environment.parse_extra_requirements(...)` | `cli.main` @ `7debbb3:502` |
  | `cli.py:1225` | the only production reader of `Requirements.installed` (the `options.installed_imports` copy-back) | **dead** — the whole chain was deleted by 3d's Task 8 (`e430a37`). `Requirements.installed` is still computed, in `classify.split_imports` @ `7debbb3:src/veny/classify.py:187` and `:270`; `cli.py` has no reader. |
  | `cli.py:2606` | the `TemporaryDirectory`-based `create_venv` on the probe path | `cli._probe_venv` @ `7debbb3:779` |
  | `cli.py:2860` | `write_requirements_file_with_extras(options)` in `setup_virtualenv` | **left `cli.py`'s ownership**: the callee is `environment.write_requirements_file_with_extras` @ `7debbb3:src/veny/environment.py:179`; the `setup_virtualenv` call site is `7debbb3:994` |
  | `cli.py:3304` | `setup_virtualenv` | `cli.setup_virtualenv` @ `7debbb3:956` |
  | `cli.py:3323` | `create_venv(options.venv_dir, ...)` in `setup_virtualenv` | **left `cli.py`'s ownership**: `environment.create_venv` @ `7debbb3:src/veny/environment.py:62`; the call site is `7debbb3:974` |
  | `cli.py:1005` | `FunctionInfo.ast_node` | **dead twice over** — the *field* was retired by 3b's Task 6 (`5dbcac2`) and the *class* left `cli.py` in 3b too. `FunctionInfo` is now `analysis/call_graph.py` @ `7debbb3:11`, with no `ast_node`. |
  | `cli.py:1409` | `install_into_venv(options.venv_python, …)` | **left `cli.py`**: `verify.repair_unsatisfied_import.installer` @ `7debbb3:src/veny/verify.py:513` (a nested closure, `def installer` @ `:511`, inside `repair_unsatisfied_import` @ `:467`) |
  | `cli.py:1867` | `cli.load_last_used_venv_dir` | **deleted** by 3d's Task 5 (`0943370`); the symbol exists nowhere in `src/` or `tests/` |
  | `cli.py:1542-1555` / `1748-1761` | the duplicated three-assert block + `pip_name` generator at the two `write_requirements_file_with_extras` call sites | `cli.setup_virtualenv` @ `7debbb3:991-999` (asserts kept — `Options`' fields are still `\| None`) and `verify.verify_and_repair_imports` @ `7debbb3:src/veny/verify.py:675` (no asserts — explicit non-optional arguments) |
  | `cli.py:2197 @ dc1c3c4` | `cli.load_last_used_venv_dir`, historical | **unchanged and still correct** — it was commit-qualified, so the deletion above does not invalidate it |

  Four of the sixteen turned out to be **dead symbols rather than shifted
  lines**, which is the point of the exercise: a line number that has drifted
  is merely wrong, but a line number for a symbol that no longer exists reads
  as a live fact about the code and is worse than no citation at all. Three
  more now name a *different module*. Write every future citation as
  `symbol @ <sha>:<line>`; if the symbol is worth citing, it is worth naming.
- **Parked by 3c's reviews, 2026-08-18.** None blocking; recorded because the
  per-task ledger they came from does not survive the phase.
  - `tests/test_environment.py` (line numbers re-measured 2026-08-18; the
    per-task ledger's were taken before Task 2 repointed the file, and two of
    its six notes turned out to be obsolete — every `options.` reference is
    gone from the file, which was Task 2's point). **All four line numbers
    below were re-measured again at `7debbb3`, because 3d's Task 1 moved the
    wheel builder out of this file into `tests/wheels.py` and shifted every
    one of them:** the live round trip's uninstall
    (`test_the_live_install_uninstall_round_trip_crosses_the_real_uv_boundary`
    @ `7debbb3:tests/test_environment.py:68`, was cited `:101`) asserts "no
    error" only by the absence of an exception, with no WARNING-record check;
    the argv assertion's element 0 is `environment.uv_binary()` compared
    against itself
    (`test_run_uv_pip_places_the_python_flag_before_the_package_arguments` @
    `7debbb3:tests/test_environment.py:132`, was cited `:165`), so 6 of its 7
    elements are actually pinned; the live test hardcodes the `bin/python`
    venv layout (`7debbb3:tests/test_environment.py:55`, was cited `:88`)
    instead of reusing what is now `environment.venv_python_for` — amendment
    11 moved it into this very module, so the reuse the note asks for is now
    a one-line change with no layering objection;
    `parse_extra_requirements(fixture, rawlog=True)`
    (`7debbb3:tests/test_environment.py:214`, was cited `:247`) deviates from
    the default with no comment. And "`tests/test_environment.py` contributes
    zero mypy errors" is a weaker claim than it sounds: `pyproject.toml:82-87`
    relaxes `tests.*` to `strict = false` with `disallow_untyped_defs` and
    `disallow_untyped_calls` off.
  - `environment.parse_extra_requirements` returns `dict[str, str | None]`;
    the `None` value is unreachable today — the widening exists only to keep
    the mypy ceiling from rising, and deserves a comment saying so.
    **Re-measured 2026-08-18** on a `git archive HEAD` copy, because the
    per-task ledger's figures were taken before Task 4 removed an error and
    were stale by one on both sides: narrowing the return (and its local) to
    `dict[str, str]` gives **37**, leaving it `dict[str, str | None]` gives
    **36**. The one extra error is dict invariance at
    `options.extra_requirements = environment.parse_extra_requirements(...)`
    (cited as `src/veny/cli.py:462`; `cli.main` @ `7debbb3:502`). Both figures
    predate 3d, whose ceiling is 33.
  - The `write_requirements_file_with_extras` stub, cited as
    `tests/test_split_imports.py:878`, was loosened to `lambda *args`, so no
    test pins that `cli.py` hands `environment` an interpreter *path* rather
    than an `Options`; only mypy covers it. **Re-measured at `7debbb3`: the
    stub is `tests/test_split_imports.py:253`** (the file fell 21 lines short
    of the old citation's *EOF*, 351 lines now, because 3d migrated 35 tests
    out of it). **Narrowed by 3d, not closed:** `tests/test_uv_backend.py`'s
    `test_setup_virtualenv_writes_the_extra_requirements_version_specifiers`
    (`def` at `854ee89:tests/test_uv_backend.py:102`) now pins the contract
    in its docstring, and `tests/test_verify.py`'s
    `test_a_repair_rewrites_requirements_txt_with_the_extra_requirements`
    (`def` at `854ee89:tests/test_verify.py:1275`) does the same at the
    repair site, so the written file's contents are asserted even though
    this particular stub is still loose.
  - `cli.py`'s `--reqs` block (cited as `:461`; `cli.main` @ `7debbb3:501`)
    no longer resets
    `options.extra_requirements` to `{}` before reading it — unreachable while
    `my_fopen` has `suppress_errors=True`.
  - `test_no_source_imports_means_no_probe_venv_is_built` (cited as
    `tests/test_classify.py:169`; re-measured at `7debbb3` it is
    `tests/test_classify.py:202`) is killed by a `ValueError` out of `max()`
    rather than by its own `created == []` assertion. Still open.
  - `requirement_records` dropping a version specifier — it is called as
    `requirement_records(extra_requirements.keys())`
    (`classify.split_imports` @ `7debbb3:src/veny/classify.py:262`, unmoved by
    3d) — is not pinned by any test. Still open.
  - Corpus coverage gaps that no differential run will close:
    `add_dependencies`' `while` loop never runs a second pass (no chain in
    `cli.py`'s `also_needs` is nested) — **closed by test, 2026-08-18
    (`143f909`)**: a nested chain now runs through `cli.split_imports` in
    `tests/test_classify.py`, so the fixed point is pinned even though the
    corpus still cannot reach it; `_compute_bad_imports`' `PYTHON2_ONLY`
    intersection is unexercised; `install_into_venv`'s success predicate is
    never compared, because the driver's fake `subprocess.run` always returns
    `returncode=1` and the return value is discarded (see the 3d list below).

- **Five findings from phase 4b's final whole-branch review, deferred to 4c**
  (recorded 2026-08-22). Each would edit one of the four swept modules
  (`last_used.py`, `pipeline.py`, `cache_search.py`, `cli.py`) and restale
  `docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md`,
  so none is fixed here.
  - `cli.py`'s `_emmykit_version()` rejects a two-component version equal to
    the floor: `"0.4"` parses to `(0, 4)`, and `(0, 4) < (0, 4, 0)`, so an
    emmykit released as `0.4` rather than `0.4.0` is refused with "requires
    emmykit >= 0.4.0; found 0.4". Every other shape compares correctly
    (`0.4.0rc1`, `0.4.0.dev1`, `0.10.0`, `1.0`). Fix is to zero-pad to the
    floor's length.
  - `cache_search.py`'s "invalid combination of flags" message prints the
    internal locals `prefer_latest` and `try_last_used` rather than the flag
    spellings the user typed; reachable with `--latest --last-used`.
  - `cli.py`'s `ResolvedImport` re-export says it is "re-exported here
    because veny is where it is used", but no module under `src/` reads it —
    it is a test-only alias since `json_types` died.
  - `tests/test_alias_index.py:651` still says "Options() is constructed
    before the target interpreter is known"; the class no longer exists. Its
    mirror in `alias_index.py`'s docstring was already fixed.
  - `scripts/differential_3e.py` was reworded this phase but carries no note
    that it is no longer runnable against HEAD, unlike `differential_3d.py`,
    which this branch did annotate.

## Open questions

- None currently blocking.
