# Design: match cached virtual environments from a manifest, not a folder name

Status: approved 2026-08-14
Supersedes nothing. Follows the StdlibIndex and AliasIndex plans.

## Problem

`find_match_dir_in_cache` (`veny.py:4579`) decides whether a virtual
environment already in `~/veny` can be reused. It answers that question from
two artifacts, and both are the wrong kind of evidence.

The first is the folder name. `pretty_packages_list` (`veny.py:3978`) joins pip
names with `-`, and the matcher splits the name back apart on `-`
(`veny.py:4617`), so any hyphenated pip name is shattered into fragments that
never match the real name. `ruamel-yaml` becomes `ruamel` and `yaml`;
`types-requests` becomes `types` and `requests`. The wanted name is then
reported missing and the folder is rejected. The format has never been safe:
`Options.venv_name` is documented as "Can NOT include dashes"
(`veny.py:55`), which is the same constraint discovered once and never applied
to package names.

The bug was latent before the alias resolver, because the hardcoded alias table
produced only 21 curated pip names and none of them were hyphenated. `AliasIndex`
resolves arbitrary PyPI distribution names, so the exposure is now the whole
index.

The second artifact is `requirements.txt`. It is the input handed to pip, not a
record of what the venv contains. The matcher compares a set of pip names to the
raw lines of that file with `issubset` (`veny.py:4638`), so a `--reqs` line
carrying a version spec (`numpy>=1.2`, written at `veny.py:4122`) never matches
the record named `numpy`.

A third layer disagrees with both. `check_venv_dir` (`veny.py:4553`) compares
`ResolvedImport` records with exact dataclass equality, so a venv built when
`yaml` resolved to `PyYAML` is rejected by a run that spells it `pyyaml`, even
though PyPI treats those as the same project.

Every one of these failures is a false negative: a good venv is discarded and
rebuilt. None is unsafe, but together they make the cache unreliable in exactly
the cases the alias resolver made reachable.

## Decision

Record what a virtual environment *is* in a versioned manifest inside it, and
match against that. Reduce the folder name to a cheap, correctly encoded
prefilter. Keep the import-level check that Task 9 added as the final backstop.

Concretely:

- A new module `venv_cache.py` owns folder-name construction and parsing,
  manifest read/write, the match predicate, and a limited version comparator.
- Each venv gains `veny_manifest.json`, recording the interpreter it was built
  for and, per package, the import name, the pip name as pip received it, the
  version actually installed, and any requested spec.
- The comparison key for "does this venv hold the packages I need" is the PEP 503
  normalized pip name, at every layer.
- The interpreter is recorded and is part of the match.
- Virtual environments without a manifest are skipped. There is no legacy read
  path.

### Constraints inherited from PROGRESS.md

- No third-party dependency may be required to run veny, so PEP 440 handling is
  hand-rolled and deliberately partial rather than delegated to `packaging`.
- The repository is a flat two-script layout; `venv_cache.py` sits alongside
  `veny.py`, `univ_defs.py`, `stdlib_index.py`, `alias_index.py`, and
  `pypi_client.py`.
- `veny.py` and `univ_defs.py` are not lint-clean. Gate on `ruff check
  veny.py --statistics` before and after, and on `mypy` over touched files
  only. Never run the pre-commit `ruff`/`ruff-format` hooks against `veny.py`.

## Architecture

### Module boundary

`venv_cache.py` imports only the standard library. It imports nothing from
`veny`, `univ_defs`, `alias_index`, or `pypi_client`, the same one-way
discipline `stdlib_index.py` follows. `veny.py` imports it.

It owns four responsibilities:

1. **Naming.** `build_folder_name(venv_name, interpreter_tag, timestamp,
   pip_names)` and `parse_folder_name(name)`.
2. **Manifest.** A `Manifest` dataclass with `write_manifest(venv_dir, manifest)`
   and `read_manifest(venv_dir)`.
3. **Matching.** `satisfies(manifest, wanted, interpreter_tag)`, pure, returning
   a decision and a reason string for logging.
4. **Version comparison.** `version_satisfies(installed, spec)`.

`veny.py` keeps everything that touches the outside world: iterating `my_dir`,
reading and writing files, the `--latest / --oldest / --smallest / --last-used`
flag logic, creating venvs, and probing a venv for installed versions.

`venv_cache` needs PEP 503 normalization and may not import `alias_index` to get
it, so it carries its own three-line copy of the rule. This duplication is
deliberate and must be documented in both modules: a second, silent
implementation of a comparison rule is the kind of thing that drifts apart, and
the two must be kept identical.

### Folder name

    <venv_name>-py<interpreter_tag>-<YYYYMMDD>-<HHMMSS>-<packages>

Package names are PEP 503 normalized before joining, so each contains only
`[a-z0-9-]`, and they are joined with `_`, which therefore cannot occur inside a
name. Up to five names are listed, in sorted order; beyond that the tail becomes
`_and_<N>_more`.

    myenv-py3.12-20260814-091500-numpy_ruamel-yaml_types-requests
    myenv-py3.12-20260814-091500-numpy_pandas_scipy_matplotlib_ruamel-yaml_and_7_more

Parsing is `name.split("-", 4)`, giving venv name, interpreter field, date,
time, and the package section, which is then split on `_`. The literal
`versionless` field in the current format is replaced by the interpreter field,
which makes the interpreter a cheap prefilter rather than a fact only the
manifest knows.

The interpreter field is the literal `py` followed by the same tag the manifest
stores, dot included: `py3.12`, not `py312`. The dot is safe here because `-`
and `_` are the separators, and keeping it means the field parses back to the
manifest's tag by stripping a prefix, with no digit-regrouping rule to get wrong
(`py3100` could be read as either `3.100` or `31.00`). One tag spelling,
one inverse, no second representation to keep in step.

Names that do not parse are skipped, not repaired.

### Manifest

`<venv_dir>/veny_manifest.json`:

```json
{
  "schema_version": 1,
  "created": "20260814-091500",
  "interpreter_tag": "3.12",
  "interpreter_path": "/usr/bin/python3.12",
  "packages": [
    {"import_name": "yaml",  "pip_name": "PyYAML",
     "installed_version": "6.0.2", "requested_spec": null},
    {"import_name": "numpy", "pip_name": "numpy",
     "installed_version": "2.1.3", "requested_spec": ">=1.2"}
  ]
}
```

- `pip_name` is stored as pip received it, never normalized. Normalization
  happens at comparison time on both sides, following the contract
  `alias_index.normalize_pip_name` already documents. Storing the normalized
  form would destroy the record of what was installed.
- `installed_version` is what the venv reports afterwards, read through
  `importlib.metadata` inside that venv. It is not what was requested and not
  what pip printed. `null` when the probe could not answer, which makes any spec
  check on that package fail closed.
- `requested_spec` is the `--reqs` spec for that package or `null`. It is not
  used for matching; it records why a version was pinned, which is the
  diagnostic wanted when a cache miss is surprising.
- `schema_version` is checked on read. Any value other than the one this build
  understands returns `None`, so the folder is skipped. That is what allows the
  schema to change later without a migration path or a compatibility branch.
- The manifest describes the venv's final state. It is written after
  installation *and* after `verify_and_repair_imports`, so a repaired venv
  records the package that actually provided the import.
- There is no `veny_version` field. The codebase has no version constant to
  record and `schema_version` carries what matters.

### Matching

`satisfies(manifest, wanted, interpreter_tag)` is true when all hold:

- `manifest.interpreter_tag == interpreter_tag`.
- Every wanted record's normalized pip name appears among the manifest's
  normalized pip names.
- For every wanted record carrying a spec, `version_satisfies(installed, spec)`
  is true for the version the manifest records.

A manifest holding packages beyond those wanted still matches. Extra packages
are what `--smallest` exists to discriminate between.

Import names are not part of this key. "Does this venv contain the right
distributions" is a question about distributions, which pip, PyPI and
`importlib.metadata` all key on the normalized project name. "Does this venv
work for this script" is a question about import names, and it is answered the
only sound way, by importing them: `check_packages_in_venv(source_names=...)`
stays exactly as Task 9 left it, as the final confirmation of a chosen venv.

## Data flow

### Creating a venv

1. Resolve the build interpreter: `options.python_command` when set, otherwise
   `sys.executable`. `find_preferred_python_version()` returns `""` when the
   preferred Python is absent (`veny.py:303-307`), and the fallback preserves
   today's behaviour in exactly that case.
2. Take the interpreter tag from that same interpreter, in the `major.minor`
   form `alias_index._running_tag` uses, so the tag in the folder name, the tag
   in the manifest, and the alias cache's tag all mean one thing.
3. Create the venv at `failed-<venv_name>-py<tag>-<timestamp>-<packages>`,
   install, and run `verify_and_repair_imports` as today.
4. Probe the venv for installed versions, write the manifest, then rename to
   drop the `failed-` prefix on success.

This is also the fix for a real discrepancy. `options.python_command` comes from
`ud.find_preferred_python_version()` (`veny.py:303`) and is what stdlib and
alias resolution are probed against (`veny.py:270`, `veny.py:308`), but the venv
is currently built with `sys.executable` (`veny.py:4365`). Those can be
different interpreters, so imports can be classified for one Python and
installed into a venv for another. Recording an interpreter in a manifest while
that mismatch stands would record a truth contradicting the rest of the run.

### Finding a cached venv

1. List folders in `my_dir` whose names start with `venv_name`, and parse each
   name. Unparseable names are skipped.
2. Cheap rejects from the name alone: the interpreter tag differs, or a wanted
   package is absent from the named packages beyond the `_and_N_more` slack.
   This is the same rule as today, over names that now survive hyphens.
3. Read the manifest. Absent, malformed, or of an unknown schema version means
   skip. This is what retires every pre-manifest venv.
4. Apply `satisfies`.
5. Rank the survivors by `--latest / --oldest / --smallest / --last-used` as
   today, then confirm the winner with
   `check_packages_in_venv(source_names=...)`.

### The `--last-used` path

Today it trusts the records inside the last-used options JSON and compares them
with exact `ResolvedImport` equality (`veny.py:4553`). Under this design the
JSON supplies only the pointer — which directory — and that directory's manifest
answers the same `satisfies` question every other candidate answers. One
authority. The recorded gotcha that pre-branch options files hold bare strings
where records now live stops mattering, because those fields are no longer read
for matching.

### Renaming

Repairs can change a package's pip name after the folder has been named, leaving
the name listing a package the venv no longer holds. The manifest would be
right and the name stale, and the cheap prefilter would then reject a venv that
actually matches.

The success path already renames a venv: it drops the `failed-` prefix and
patches the `command = ` line in `pyvenv.cfg` and the download script
(`veny.py:472-487`). That code becomes a single `rename_venv(options,
new_name)` helper used for both the prefix drop and any repair-driven rename, so
the name and the manifest can never disagree and the two rename paths become
one.

## Error handling

Every failure on the cache path means "not a match", never an exception. A
cached venv is an optimization and the worst outcome of ignoring one is a
rebuild. Unreadable manifest, malformed JSON, unexpected schema version,
unparseable folder name, missing directory, failed version probe: each skips
that folder and logs the reason at info level.

This is deliberately the opposite of the override-file rule, where
`AliasOverrideError` is fatal because that file carries the user's explicit
intent. A cache carries no intent.

Writing the manifest is best-effort. A write failure leaves the venv usable for
this run and merely absent from the cache next time, logged as a warning.

## Version comparison

`version_satisfies(installed, spec) -> bool`.

Supported: comma-separated clauses, all of which must hold, each `<op><version>`
with `op` in `==`, `!=`, `>=`, `<=`, `>`, `<`, `~=`, and versions made only of
dot-separated integers. The shorter release is zero-padded before comparison, so
`1.2` equals `1.2.0`. `~=X.Y.Z` desugars to `>=X.Y.Z` combined with
`<X.(Y+1)`, per PEP 440's compatible-release rule. `==X.Y.*` is a
release-segment prefix match, not a string prefix match.

Everything else returns False, meaning no match, meaning rebuild: epochs
(`1!2.0`), pre-, post- and dev releases (`1.2b1`, `1.2.post1`, `1.2.dev0`),
local versions (`1.2+cpu`), arbitrary equality (`===`), URLs, environment
markers, extras syntax, a spec that is present but empty, and any
`installed_version` of `null`.

Failing closed is the correct direction here for the same reason recorded in the
stdlib design: being wrong toward "rebuild" costs time, while being wrong toward
"reuse" hands back a venv that violates the user's pin and fails at their
runtime.

Two consequences to state plainly rather than discover later:

- A package installed as a pre-release never satisfies any spec, so such a
  package triggers a rebuild on every run until the comparator grows.
- This is not a PEP 440 implementation. Its docstring must say what it refuses,
  not imply completeness.

## Testing

Unit tests live in `tests/test_venv_cache.py`, with a small number of
`veny.py`-side tests beside them. Every test below is paired with the bug it
would catch. Expected values are computed by hand from the format rules and
PEP 440, not by executing the code under test.

**Naming**

- `build_folder_name` on `["ruamel.yaml", "NumPy", "types_requests"]` produces
  exactly `myenv-py3.12-20260814-091500-numpy_ruamel-yaml_types-requests`.
  Catches a join that reverts to `-`, and a missing normalization of `.` or `_`.
- Parsing that name returns `{numpy, ruamel-yaml, types-requests}`. Catches the
  reported bug directly, where `ruamel-yaml` shatters into two fragments.
- Eight packages produce five names plus `_and_3_more`, and parsing returns five
  known names and an unnamed count of 3. Catches an off-by-one in the overflow
  count and a count read from the wrong token.
- Names with no timestamp field, too few fields, or an empty package section
  return `None`. Catches an unrelated directory in `~/veny` being treated as a
  venv candidate.

**Manifest**, against real files under `tmp_path`, since the filesystem is the
boundary being exercised and is not mocked

- Write-then-read returns an equal `Manifest`, including `installed_version` and
  `requested_spec`. Catches a field dropped in serialization, which would turn
  every pinned package into an unpinned one.
- A missing file, malformed JSON, and `schema_version: 2` each return `None`.
  Catches an exception escaping into the run instead of skipping one folder, and
  a future schema being misparsed as version 1.

**Matching**

- An exact match returns True; a manifest missing one wanted package returns
  False. The floor of the predicate.
- Manifest tag `3.12` against a run tagged `3.13` returns False. Catches a 3.13
  run reusing a 3.12 venv.
- A manifest holding extra packages returns True. Catches over-strict set
  equality, which would defeat reuse entirely and make `--smallest` meaningless.
- Manifest `pip_name` `ruamel.yaml` against wanted `ruamel-yaml` returns True.
  Catches normalization applied to only one side of the comparison.
- A wanted spec against `installed_version: null` returns False. Catches
  "unknown version" being read as "satisfies", the fail-open direction.

**Version comparator**, table-driven

- `1.10.0` satisfies `>1.9`. Catches lexicographic string comparison, where
  `"1.10" < "1.9"`.
- `1.2` satisfies `>=1.2.0`. Catches release segments compared without zero
  padding.
- `1.2.3` satisfies `~=1.2.0` and `1.3.0` does not. Catches a wrong
  compatible-release upper bound.
- `1.2.5` satisfies `==1.2.*` and `1.3.0` does not. Catches prefix matching done
  on the string, where `1.20` would wrongly match `1.2.*`.
- `1.5` satisfies `>=1.0,<2.0` and `2.1` does not. Catches only the first clause
  being honoured.
- `1.2b1`, `1.2+cpu`, `1!2.0`, `===1.2`, and a `None` installed version all
  return False. Catches a comparator that strips or ignores suffixes and then
  reports a pre-release as satisfying a stable pin.

**`veny.py` side**

- The build-interpreter helper returns `options.python_command` when set and
  `sys.executable` when it is `""`. Catches a regression back to building the
  venv with the wrong interpreter.
- `rename_venv` on a fixture venv directory renames it and rewrites the
  `command = ` line in `pyvenv.cfg`. Catches a rename that leaves the venv
  recording its old path, which is a broken venv rather than a slow one.
- The candidate-folder filter keeps a folder whose name lists `ruamel-yaml` for
  a run wanting `ruamel-yaml`. The reported bug stated at the `veny.py` level,
  above the pure module.

**Two process requirements**, both from lessons already recorded in
PROGRESS.md:

1. After implementation, delete each new filter or guard one at a time and
   confirm a test fails. The deferred entry for
   `test_a_record_carrying_a_pip_spelling_is_never_repaired` is a test that
   named a guard without exercising it, found only by mutation.
2. One manual end-to-end run: build a venv for a script importing a package with
   a hyphenated pip name, confirm the manifest is written, run again, and
   confirm the venv is reused rather than rebuilt. The seam between a pure
   module and the real world is where the `files.pythonhosted.org` range-request
   bug hid behind 45 green tests.

## Migration

There is no migration. Virtual environments already in `~/veny` carry no
manifest, so they are skipped and rebuilt once, on first use under the new code.
Old folders remain on disk until deleted by hand; they are inert, since their
names also fail to parse under the new format.

This was chosen over a `requirements.txt` fallback, and over a fallback that
backfills manifests, because either keeps the fragile parsing path alive
indefinitely as a second code path to maintain and test.

## Out of scope

- `also_needs` (`veny.py:120`), still hardcoded, still deferred.
- Splitting `veny.py` and `univ_defs.py`, and the further `alias_index.py`
  split.
- A `to_jsonable` handler for `StdlibIndex`, and round-trip tagging for the
  `AliasIndex` handler.
- Broader `veny.py` / `univ_defs.py` test coverage beyond the paths this design
  touches.
- Full PEP 440 support in the comparator.
- Garbage collection of stale venvs in `~/veny`, including the pre-manifest ones
  this design orphans.

## Consequences

- The first run after this lands rebuilds every venv, once per package set.
- Cache hits become correct for hyphenated pip names, for equivalent spellings
  of the same project, and for `--reqs` pins, all of which currently miss.
- A venv built for a different interpreter is no longer reused, which is a new
  rejection and a correct one.
- `veny.py` sheds the naming, parsing and matching logic to a module that can be
  unit tested, continuing the pattern of the two previous plans.
- `options.pretty_requirements` (`veny.py:4103-4137`) is computed and never
  read by anything. It is unrelated to the folder name and can be deleted in
  this work if it is still unread when the implementation reaches it.
