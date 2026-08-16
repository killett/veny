# veny re-architecture — design

**Status:** approved 2026-08-15
**Scope:** target architecture only. This document fixes module boundaries and
ownership — which module exists, what it is handed, what it returns. It
deliberately does not fix module internals or task breakdown; those belong to
the per-phase implementation plans that reference this document.

## Problem

`src/veny/cli.py` is 6,020 lines. A single `Options` object carries 48
attributes through 482 use sites, so no function declares what it actually
touches, and most of the file cannot be unit tested without constructing the
whole world. Package installation goes through `pip`, which predates `uv`.
Four changes were requested: split the monolith, retire the `Options` god
object, move to `uv`, and add unit tests wherever they can be meaningful.

The four are not independent. Extracting a module requires deciding what it
receives instead of `options`, and the `uv` migration deletes code that would
otherwise be organized and tested for nothing. They are sequenced below as one
program.

## Decision: refactor, do not restart

A rewrite was considered and rejected on three grounds.

First, the split is already half-done and it worked. `src/veny/` holds five
extracted modules — `alias_index.py` (826), `venv_cache.py` (465),
`pypi_client.py` (314), `stdlib_index.py` (233), `json_types.py` (136) — each
with tests written alongside the extraction, totalling 231 test functions and
257 passing tests. A restart discards ~1,975 clean, tested lines for no gain.

Second, `PROGRESS.md`'s gotchas section is the project's most valuable asset and
a rewrite loses the half of it that was never written down. Examples that each
cost a live debugging session: `files.pythonhosted.org` answers `501
Unsupported client range` to suffix Range requests; CPython excludes `Lib/test`
from `sys.stdlib_module_names`; a machine-scoped import failure (`libGL.so.1`
missing) must not be persisted as a package rejection; a passing import check
proves behaviour, not attribution.

Third, the extraction path is empirically proven in this repository — five
modules, five design docs, five plans, all landed.

On the concern that motivated the restart question — that unit tests written
after the fact rubber-stamp the implementation rather than testing intent — the
concern is correct but mis-located. The failure mode is not tests written
*after* the code; it is tests written *from* the code. Both directions of
evidence already exist here: `test_a_record_carrying_a_pip_spelling_is_never_
repaired` is decorative (delete the filter it names and 153 tests stay green),
found by mutation testing rather than by earlier authorship; and the 45
`pypi_client` tests that were written test-first were nonetheless all wrong,
because the fake they ran against honored suffix ranges the real server
rejects. The protocol that fixes this is in "Testing strategy" below.

## Phases

Phases 1 and 2 are independent of the architecture and land first, reducing
`cli.py` from 6,020 to roughly 3,870 lines before any extraction begins.
Phases 3 and 4 are a single act — the extractions carry the state
decomposition with them — and are sequenced module by module in their plans.

1. **Delete the file/network visitor block.** ~1,600 lines.
2. **Migrate to `uv`** at the depth described below. ~550 further lines.
3. **Extract the survivors** into the module layout below.
4. **Drain `Options`** into the objects below, one extraction at a time.

### Phase 1: delete the visitor block

`FileOperationsVisitor`, `NetworkOperationsVisitor` and their two
`TopLevel*` subclasses span `cli.py:756-2195` and comprise 40-plus
`_process_*` methods recognizing calls to `open`, `pathlib`, `shutil`,
`subprocess`, `requests`, `boto3`, `paramiko`, `grpc` and thirty other
libraries. Their entire product is four lists — `options.read_files`,
`write_files`, `download_urls`, `upload_urls`. The only consumer is
`cli.py:3607-3634`, four `logging.info` calls. Nothing gates on the result, no
manifest records it, and no test references any of it.

Deleted: `_literal_str`, `get_evaluated_arg`, `_record_IO`,
`_get_full_attr_name`, `unpack_method_call`, the four visitor classes,
`transform_call` (already dead — its only reference is its own definition), the
two visitor call sites near `cli.py:3605`, the reporting block at
`cli.py:3607-3634`, the resets at `cli.py:3394-3397`, and five `Options`
fields.

Retained: `collect_pathlib_aliases`, `is_pathlib_ctor`, `_safe_eval_node` and
`safe_eval` (`cli.py:2196-2235` and `2278-2437`, ~200 lines). `SysPathVisitor`
at `cli.py:2455` and `_analyze_module` at `cli.py:3315` still need them.

Net: ~1,600 lines, no test rework.

### Phase 2: migrate to uv

Chosen depth: the environment layer moves to `uv`; veny keeps its own venv
cache.

Rejected alternatives. *Installer swap only* — replace `pip install` with `uv
pip install` and change nothing else — buys speed and deletes nothing.
*Delegating the cache to `uv run --with`* was the tempting option and was
rejected for two reasons. It loses superset reuse: veny's manifest match reuses
a `{numpy, pandas}` environment for a script wanting `{numpy}`, whereas uv's
ephemeral environment cache keys on the exact requirement set. And the repair
loop needs a mutable environment it controls — `repair_unsatisfied_import`
installs a candidate, checks whether the import works, and uninstalls it when
the evidence does not attribute the import to that package — whereas `uv run
--with` yields a finished ephemeral environment. Delegating the cache would
therefore delete the cache while still requiring a scratch environment to do
half of what it did. That option remains reachable later from this one; it is
not a door this design closes.

What uv does not supply, and what therefore survives untouched, is veny's
actual differentiator: deriving the requirement set from source, and the
import-name-to-pip-name resolution with attribution behind it — `alias_index`,
`pypi_client`, and the resolve/verify/repair loop.

**Locating the binary.** `uv` is declared as a runtime dependency in
`pyproject.toml` alongside `emmykit`, and the binary is located with
`uv.find_uv_bin()`. The `uv` PyPI package ships the binary and exposes that
entry point. Because veny is installed with `uv tool install`, the binary lands
in veny's own tool environment and is found deterministically rather than by
PATH lookup — the same failure mode that motivated retiring the shell-alias
install. Falls back to a PATH lookup if the import fails, and exits with an
install message if neither works, in the same shape as the existing emmykit
guard at `cli.py:38`.

This is the second waiver of the standing rule that no third-party dependency
may be required to run veny. It is argued on the same basis as the emmykit
waiver: uv is the tool veny now delegates its environment layer to, and a
declared, version-pinned dependency is a strictly weaker requirement than
"must happen to be on PATH".

**Command mapping.**

| Today | Under uv |
|---|---|
| `venv.create(venv_dir, with_pip=True)` (`cli.py:4239`) | `uv venv <dir> --python <target>` |
| `[python, "-m", "venv", dir]` (`cli.py:5231`) | `uv venv <dir> --python <target>` |
| `venv_python -m pip install <pkg>` | `uv pip install --python <venv_python> <pkg>` |
| `venv_python -m pip uninstall <pkg>` | `uv pip uninstall --python <venv_python> <pkg>` |
| `venv_python -m pip list` | `uv pip list --python <venv_python> --format json` |
| `download_packages` + `--find-links` + `--no-index` | deleted; uv's global cache serves this purpose |

**Deleted with this phase:** `download_packages`, `packages_dir`,
`download_packages.sh`, the `--no-index` install paths,
`install_packages_simultaneously`, `install_packages_individually`,
`install_package`, `recover_pip_versions`, `use_pip_list`, and
`options.pip_list`. This machinery exists to avoid re-downloading wheels; uv's
global hardlinked cache does that job better.

**Behaviour change to document, not bury:** `uv venv` does not seed `pip` into
the environment, whereas `venv.create(with_pip=True)` does. A user script that
shells out to `pip` inside its environment will stop working. veny does not
pass `--seed`: it is faster, and a script installing into the environment veny
built for it is working against veny. This belongs in README.md.

### Phase 3: module layout

Sizes are post-phase-2 estimates.

```
src/veny/
  cli.py             ~250  argparse surface, main(), exit-status policy
  pipeline.py        ~300  the run: analyze -> classify -> acquire env -> run
  settings.py        ~120  Settings, Target, VenvHandle, LastUsed (frozen)
  analysis/
    literals.py      ~200  safe_eval chain, pathlib alias handling
    imports.py       ~700  ImportFunctionCollector, process_import, SysPathVisitor
    call_graph.py    ~250  FunctionInfo, ModuleInfo, build_call_graph, collect_used_imports
    scan.py          ~300  find_imports_in_script, _analyze_module, enqueue
    custom_modules.py ~250 local-module discovery, stay-out and path predicates
  classify.py        ~350  split_imports, add_dependencies, resolve_records
  environment.py     ~350  uv venv creation, uv pip install/uninstall, requirements
  verify.py          ~600  import checking, attribution, repair loop
  cache_search.py    ~600  candidate ranking, check_venv_dir, record_venv_state, rename
  last_used.py       ~120  read/write the LastUsed record; is_virtualenv
  alias_index.py      826  unchanged
  venv_cache.py       465  unchanged (data model: naming, manifest, satisfies)
  pypi_client.py      314  unchanged
  stdlib_index.py     233  unchanged
  json_types.py       136  unchanged
```

**Ownership, stated as what each module is handed and what it returns.**

- `analysis/*` is handed a script path plus `Settings` and returns an
  `ImportScan`. It performs no network access, builds no environment, and takes
  neither `AliasIndex` nor `StdlibIndex`. Pure AST in, names out.
- `classify.py` is handed an `ImportScan`, a `StdlibIndex`, an `AliasIndex` and
  the `--reqs` requirements, and returns a `Requirements`. This is where
  `split_imports` stops needing a temporary virtual environment.
- `environment.py` is handed a `VenvHandle` and package names and reports
  success or failure. It is the only module that invokes `uv`.
- `verify.py` is handed a `VenvHandle`, a `Requirements`, and an
  installer/importer/uninstaller trio, and returns an outcome plus the
  attribution facts to record. `repair_unsatisfied_import` already takes those
  callables by injection; this makes injection the module's interface rather
  than one function's.
- `cache_search.py` is handed `Settings` and a `Requirements` and returns a
  matching venv directory or `None`. It reads manifests through `venv_cache`
  and never installs.
- `pipeline.py` owns sequencing and is the only module that knows the order. It
  absorbs `list_packages`, which is a driver rather than a unit of work, and
  the user-facing reporting currently inlined in `main()` —
  `warn_about_system_packages` and the uninstalled/bad/samedir/subfolder
  summary. (`list_installed_packages`, `list_available_modules` and
  `list_builtin_modules` are not veny functions — they are lines inside
  `use_pip_list`'s probe-script string literal, and they go with it in
  phase 2.)
- `cli.py` owns argparse and exit status and nothing else.

**Import direction** is one-way and enforced by a test, extending the
discipline already held among `alias_index`, `pypi_client` and `venv_cache`
(`tests/test_import_guard.py` is the existing home):

```
cli -> pipeline -> {analysis, classify, environment, verify, cache_search,
                    last_used} -> {alias_index, venv_cache, stdlib_index,
                    pypi_client} -> settings
```

**Two boundaries deliberately not drawn.** `venv_cache.py` and
`cache_search.py` stay separate: `venv_cache` is the data model (folder naming,
manifest read/write, `satisfies`) and `cache_search` is the selection policy
(ranking, tie-breaks, `check_venv_dir`). Merging them would put policy behind
the one-way boundary that keeps `venv_cache` free of `alias_index` — which is
why `normalize_pip_name` is deliberately duplicated between them today. And
`analysis/` is a subpackage rather than a module: at ~1,450 lines it is the
largest survivor and holds veny's differentiator.

### Phase 4: the state model

`Options` stops existing. Frozen dataclasses are passed explicitly, so that
each signature declares what the function actually needs and each test
constructs only what it exercises.

A single `Context` object composing the same sub-objects was considered and
rejected: `def check_venv_dir(ctx)` tells a reader and a test exactly as little
as `def check_venv_dir(options)` does today. The problem with `Options` was
never parameter count — it was that 482 use sites across 6,000 lines left no
function with an honest declaration of what it touched.

```python
@dataclass(frozen=True)
class Settings:          # invariants for the whole run
    my_name, my_dir, home, cwd, venv_name,
    stay_out_list, unusual_imports, known_bad_imports, also_needs,
    extra_requirements_file, max_checks, check_interval,
    search_above_this_dir, log_mode, rawlog

@dataclass(frozen=True)
class Target:            # what is being run
    python_script, script_dir, script_name, script_args,
    python_command, timestamp

@dataclass(frozen=True)
class VenvHandle:        # derived wholly from venv_dir
    venv_dir, venv_python, requirements_file

@dataclass(frozen=True)
class ImportScan:        # produced by analysis/, consumed by classify
    all_imports, custom_modules, loaded_custom_modules,
    samedir_files, subfolders, sys_path_hints

@dataclass(frozen=True)
class Requirements:      # produced by classify, consumed downstream
    installed, uninstalled, bad, seen_stdlib, extra_requirements

@dataclass(frozen=True)
class LastUsed:          # the only thing that persists between runs
    venv_dir, venv_python, timestamp
```

`StdlibIndex` and `AliasIndex` are already objects and are passed as
themselves; they belong to no bundle.

**Deleted rather than rehomed**, fifteen attributes. With the visitor block:
`read_files`, `write_files`, `download_urls`, `upload_urls`,
`current_method_name`. With uv: `pip_list`, `current_pip_version`,
`new_pip_version`, `simultaneous_success`, `download_script_path`, `venv_pip`,
`test_dir`, `packages_dir`. With the persistence change: `pathlibcutoff` and
`options_json_filepath`. And `total_imports` is a `len()`.

**Mutation direction.** Today `find_imports_in_script(options)` returns
`None` and writes eleven fields onto `options`; `split_imports(options)`
returns `None` and writes four more. Under this design each stage returns its
product and mutates nothing it was handed. `ImportScan` and `Requirements` are
values, not accumulators.

One deliberate exception: `AliasIndex` stays mutable and injected. It is a
cache with a disk backing and a separate in-memory session-rejection store, and
that separation is load-bearing — a shared store would be flushed to disk by
the next `confirm()`.

**Persistence.** `ek.save_options_to_json(options)` is typed against
`ek.Options`, so persistence is currently coupled to the class rather than to a
payload. But the payload `load_last_used_venv_dir` and `load_last_used_venv_
python` actually recover is a venv directory and its interpreter. veny writes a
`LastUsed` record itself, dropping the coupling. `ek.Options` contributed
`args`, `log_mode`, `rawlog` and `home`; `args` dies at the argparse boundary
and the other three land in `Settings`, so nothing in veny needs the base class
and nothing in emmykit requires an instance of it.

`json_types.register_types()` stays at module scope. Moving it into `main()`
would make `save_options_to_json` write repr strings for any consumer not going
through `main()`, invisibly to every in-process test.

## Error handling

Stated per layer, unchanged in spirit from current behaviour.

- `environment.py` never raises and never exits. `run_uv(...) -> CompletedProcess
  | None` keeps `run_pip_in_venv`'s contract: a missing interpreter or an
  unrunnable `uv` is "no result", not an exception. Every caller is on a
  verification path where reporting beats dying.
- `verify.py` never exits; it returns outcomes. `install_into_venv`'s existing
  distinction from `install_package` — report `False` rather than call
  `ek.my_critical_error` — becomes the module's rule rather than one
  function's.
- `cache_search.py` degrades silently. A missing, unreadable or stale manifest
  means "no match", costing a rebuild.
- `classify.py` is fatal for exactly one input: a malformed
  `~/veny/module_aliases.toml`, which raises `AliasOverrideError` and stops the
  run, because continuing would resolve import names contrary to what the user
  explicitly wrote. This is the single deliberate exception.
- `cli.py` owns every exit. `sys.exit` and `ek.my_critical_error` do not appear
  below it.

**Exit statuses**, designed as a set for the first time, which closes the open
question recorded in the packaged-entry-point design doc:

| Status | Meaning |
|---|---|
| `0` | success, or nothing was meant to run (`--justprint`) |
| child's status | a script ran; its status is returned |
| `128 + signal` | the child was killed by a signal (already handled at `cli.py:660`) |
| `1` | veny could not build or find an environment |
| `2` | usage error |

## Ledger items closed by this design

Each of the following is parked in `PROGRESS.md` as blocked on "it changes what
the approved design says". This document is the new design, and each item is
assigned to the phase that closes it.

1. **`interpreter_tag` and `interpreter_path` can disagree** in a manifest when
   the stdlib probe degrades, so a run targeting 3.13 can write
   `interpreter_tag: "3.11"` and a later degraded run matches that tag and
   reuses a 3.13 environment labelled 3.11. Closed in phase 2: `uv pip list
   --python <venv_python>` already spawns the environment's own interpreter, so
   it also reports `sys.version_info[:2]` and that is recorded as the tag.
   Every manifest field then describes the environment rather than the run that
   built it.
2. **`satisfies()` runs twice** on the winning candidate — once in
   `cache_candidates`, again in `check_venv_dir`, which re-reads the manifest
   from disk. Closed in phase 3: `find_match_dir_in_cache` passes the manifest
   it already holds to `check_venv_dir`, which is left doing only the
   import-level confirmation.
3. **`--full` has never worked** and its directory branch is unreachable. It
   sets `python_script` to a directory but never `script_dir`, and
   `list_packages` opens with `assert options.script_dir is not None`; passing
   a directory positionally instead raises `IsADirectoryError` from
   `ek.ensure_file`. **Resolution: delete it** — the flag, its `--help` text,
   its README.md line, and the unreachable `list_packages` branch. It has no
   users by definition, and it is the only reason `Target` would need to be
   polymorphic over script-versus-directory, which would tax every module
   downstream.
4. **Exit statuses were never designed as a set.** Closed in phase 3 by the
   table above, once `cli.py` is their sole owner.
5. **`check_venv_dir`'s `issubset()` self-heal** against options files written
   before `options.aliases` existed becomes unnecessary, since `LastUsed` never
   carries an `AliasIndex`. Closed in phase 4 with the persistence change.

## Testing strategy

**Extraction is the forcing function, not timing.** Moving `split_imports` into
`classify.py` requires stating what it is handed and what it returns. That
statement is intent: it is written before the body moves and is checkable
against this document. Tests written at that moment derive from the contract.
Tests written later, against a function still reachable only through `options`,
have nothing to derive from but the body. Same calendar order, opposite
epistemics.

**Per-test protocol**, from the `test-design` skill. Before each test, the plan
states the behaviour under test, a concrete bug that would make it fail, and
how the expected value was obtained without mentally executing the code. If the
second sentence cannot be written, the test is dropped rather than weakened.
Expected values come from hand calculation, fixture data or domain knowledge.

**Mutation testing is the gate, not coverage.** The exit condition for each
extraction is: delete or invert the branch a test names, and watch that test
fail. A test surviving its own mutation is fixed or deleted in the same commit.
This is the discipline that found `test_a_record_carrying_a_pip_spelling_is_
never_repaired` to be decorative, which neither review nor coverage caught.

**Two standing rules, promoted from the gotchas ledger.**

- If a double replaces X everywhere, one test must still exercise the real X.
  Patching `import_outcome_in_venv` in every repair test let a mutation
  deleting its `report_providers=True` survive 150 tests. `verify.py` takes its
  trio by injection, which makes doubles easy and this rule mandatory.
- A green suite against a fake proves the fake. Anything crossing a real
  boundary — `uv` invocation, PyPI, the interpreter probe — keeps one live
  check outside the unit suite. `scripts/smoke-install.sh` is that home.

**Newly testable, which is the payoff.**

- `classify.py` — `split_imports` currently builds a real temporary virtual
  environment, which is why it cannot be unit tested today. After extraction it
  is a pure function over an `ImportScan` and two indexes. This is the largest
  untested block in the codebase becoming testable.
- `cache_search.py` — ranking and tie-breaks become pure over a list of
  manifests. Three cases the ledger names as uncovered become reachable:
  `satisfies` with an empty wanted list, with empty `manifest.packages`, and
  with two pip names normalizing to one key.
- `analysis/literals.py` — `safe_eval` over hand-written expressions, no
  filesystem.
- `pipeline.py` — the seam tests. A defect living between two tasks is
  invisible to per-task review: `resolve_and_verify` had no production caller
  through 113 green tests and a review of every task. With sequencing owned by
  one module, the joins are addressable.

**Untested deliberately, and in writing:** the `uv` subprocess invocations
beyond argument construction — argument lists are asserted, the child process
is not simulated — and `cli.py`'s argparse wiring beyond exit-status mapping.
Both are boundary layers where a unit test would assert the mock.

**Untested because deleted:** the visitor block. No existing test references
it, so phase 1 costs nothing in test rework.

**Ordering.** Each extraction is: characterize current behaviour at the new
interface, move the code, run the suite, mutate.

**One honest limit.** Characterization tests written at a new interface
describe *current* behaviour, and current behaviour is occasionally wrong — the
ledger enumerates a dozen such cases. This protocol catches tests that cannot
fail; it does not catch a contract that faithfully encodes a real bug. The
defense is that those items are already known and enumerated, and each phase's
plan names which of them it closes.

## Out of scope

- Delegating the venv cache to `uv run --with` and PEP 723 inline metadata.
  Reachable from this design later; see the phase 2 rationale.
- Full PEP 440 support in `venv_cache.version_satisfies`.
- Garbage collection of stale environments in `~/veny`, including the
  pre-manifest ones that no longer match but are never deleted.
- `Options.also_needs` remains a hardcoded table; it moves into `Settings`
  unchanged.
- The two pre-existing `AssertionError` crashes recorded in `PROGRESS.md`
  (`veny -y` with no script; the already-inside-a-venv branch). Both are
  reachable from `main()`, so both are addressed incidentally when `cli.py` and
  `pipeline.py` take ownership of control flow — but neither is a goal of this
  design, and neither gates a phase.
- The emmykit shell/alias helper usage audit, still open as a cross-repo
  prompt.
