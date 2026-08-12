# Design: replace the hardcoded module-alias table with an AliasIndex resolver

Date: 2026-08-12
Status: approved, not yet implemented

## Problem

`veny.py` line 133 defines `Options.module_aliases` as a literal `dict[str, str]`
mapping import names to pip package names, spanning lines 133–1351. That is
1,219 lines, about 22% of a 5,427-line file. Most of the content was copied
from the `pipreqs` repository's `mapping` file on 2024-08-15.

The table is used at three call sites:

- `veny.py:4484` — `split_imports` maps an import name to the pip name to install.
- `veny.py:4398` and `veny.py:4401` — `check_packages_in_venv` maps a pip name
  back to the import name, through `reversed_module_aliases`
  (built at `veny.py:1352`).

Five problems:

1. **It is redundant and internally inconsistent.** The 1,219 lines hold 1,160
   entries but only 837 unique keys. 68 keys are duplicated; `plone` appears
   78 times. Python's dict literal silently keeps the last occurrence, so 323
   entries are dead on arrival and the surviving value for a duplicated key is
   whichever happened to be written last.
2. **The reverse map is wrong today.** `reversed_module_aliases` inverts a dict
   whose keys repeat, so the reverse entries for duplicated keys point back at
   an arbitrary winner. Every consumer of `check_packages_in_venv` inherits that.
3. **It is stale and misdirected.** The bulk is Plone/Zope/buildout-era content
   irrelevant to this project's actual use, while names the project does hit are
   present only because they were added by hand.
4. **It is unmaintainable by construction.** PyPI is the authority for which
   distribution provides which import name. Any in-code snapshot of that mapping
   begins rotting the moment it is written, and nothing signals when it has.
5. **The call sites carry mixed semantics.** `split_imports` adds the *pip* name
   to `options.uninstalled_imports` (`veny.py:4497`) but the *import* name to
   `options.installed_imports` (`veny.py:4493`). Two sibling sets, two different
   kinds of string, no type-level distinction.

## Decision

Replace the literal with a resolver module, `alias_index.py`, that derives the
mapping from evidence and caches verified results. This mirrors the
`stdlib_index.py` precedent established on 2026-08-12: derived truth, probed
from a real interpreter, degrading on failure, one flat module beside `veny.py`.

The resolver returns **ranked candidates with evidence**, not a single answer.
No available source can produce certainty — `packages_distributions()` is exact
but covers only installed distributions, PyPI confirms a project exists but not
that it satisfies a given import, and name heuristics are guesses by
construction. A single-answer return type would misrepresent that. A ranked list
plus an install-and-import verification step makes the only real ground truth —
"it installed and it imported" — the thing that gets cached.

The ranked-candidate mechanism is also a superset: attempting only the top
candidate, or prompting before a fallback attempt, are policies over the same
return type. Building the chain preserves those options; building single-answer
resolution would forfeit them.

### Constraints inherited from PROGRESS.md

- No third-party dependency may be required to run veny. Every source below uses
  only the standard library (`urllib`, `zipfile`, `tomllib`, `json`,
  `subprocess`).
- Being wrong toward "attempt the install" beats being wrong toward "skip the
  install." A wrong attempt fails loudly at install time; a wrong skip fails at
  the user's runtime after veny reports success.
- The repository is a flat two-script layout, not `src/`. New modules travel
  beside `veny.py`.

## Architecture

### Data model

```python
class Source(enum.Enum):        # ordered; lower value = stronger evidence
    OVERRIDE = 0                # ~/veny/module_aliases.toml, human intent
    CACHE = 1                   # ~/veny/module_aliases_cache.json, previously verified
    INSTALLED = 2               # packages_distributions() on the target interpreter
    SEED = 3                    # curated in-repo exceptions
    PYPI_CONFIRMED = 4          # project exists AND its wheel declares this top-level name

@dataclass(frozen=True)
class Candidate:
    pip_name: str
    source: Source
    evidence: str                       # human-readable; appears in logs and reports
    top_levels: frozenset[str] | None   # populated when a wheel was inspected

@dataclass(frozen=True)
class Resolution:
    import_name: str
    candidates: tuple[Candidate, ...]   # ranked, deterministic
```

`Source` deliberately has no `HEURISTIC` member. Name mutations (PEP 503
normalization, `python-` prefix and suffix, `py` prefix, dash/underscore swaps,
case folding) are **candidate generators**, not an evidence tier. A mutation
enters `candidates` only after wheel inspection confirms that project declares
the import name, at which point its source is `PYPI_CONFIRMED`. There is
therefore no code path that installs an unverified guess. This is the
typosquat mitigation, expressed structurally rather than as a runtime check.

Ranking sorts by `(source.value, pip_name)`. Identical inputs produce identical
order on every run, and the full chain is logged at debug level so a surprising
resolution can be audited afterwards.

### Storage: two files, split by authority

Both live under `options.my_dir` (`~/veny`, `veny.py:43`), alongside the
existing `pip_list_*` and `.veny_custom_modules_*.pkl` artifacts.

- `module_aliases.toml` — human-authored overrides. Read-only to veny, parsed
  with stdlib `tomllib`, which is unconditionally available at
  `requires-python = ">=3.12"`. veny ships no TOML writer, so "never rewritten
  by veny" is enforced by the absence of the capability rather than by
  discipline.
- `module_aliases_cache.json` — machine-written, verified results only. Safe to
  delete at any time; the only cost of deleting it is a slower next run.

Splitting authority means deleting the cache can never destroy user intent, and
a cache write can never mangle a hand-edited file.

### The class

`AliasIndex` holds the two stores plus injected collaborators — an HTTP fetcher
and an interpreter prober — so that it is fully testable without network access
or a virtual environment. That is precisely the property `split_imports` lacks
today.

Public surface:

- `resolve(import_name) -> Resolution`
- `confirm(import_name, pip_name) -> None` — writes a verified cache entry
- `reject(import_name, pip_name) -> None` — records a failed attempt

### Options changes

`Options.module_aliases` (`veny.py:133`) and `Options.reversed_module_aliases`
(`veny.py:1352`) are both deleted. One field replaces them:

```python
self.aliases: alias_index.AliasIndex
```

It is constructed in `main()` once `options.python_command` is resolved, exactly
as `options.stdlib` is today (`veny.py:130`), so the resolver probes the
interpreter that will actually run the user's script.

## Resolution chain

`resolve(import_name)` walks tiers in order, stopping early only on decisive
evidence.

- **T0 overrides.** On hit, return a single candidate. Human intent
  short-circuits everything, including the cache.
- **T1 cache.** On hit, return a single candidate. The cache holds only entries
  that once installed *and* imported, so a hit is a verified fact.
- **T2 installed distributions.** Runs `importlib.metadata.packages_distributions()`
  inside the **target** interpreter via subprocess, following the
  `stdlib_index` probing pattern. It returns `{top_level: [distribution, ...]}`,
  answering the reverse question exactly rather than by inference. Multiple
  distributions for one name produce multiple candidates. Does not stop the walk.
- **T3 seed.** The curated in-repo exceptions (`osgeo` → `gdal`,
  `cv2` → `opencv-python`, `netCDF4` → `netcdf4`, `yaml` → `PyYAML`,
  `zmq` → `pyzmq`, and the rest). The seed is curated by *correctness and
  reachability*, not by provenance: entries from the old hand-added block that
  are broken (`jnp` → `jax.numpy`, which is not a PyPI project) or unreachable
  (`mypy.api` → `mypy`, whose dotted key can never match after veny normalizes
  imports to their first component) are left out, while correct high-traffic
  aliases are included regardless of which part of the old table they appeared
  in. Its size is the constraint: a short list of exceptions, never a table. Contributes a candidate; does not stop the walk, so a seed
  entry can never silently outrank stronger evidence. A user who needs a seed
  entry to win can say so in the override file.
- **T4 PyPI.** Two probes, both yielding `PYPI_CONFIRMED`:
  1. *Identity* — does a project named exactly `import_name` exist, and does its
     wheel declare that top-level name?
  2. *Mutations* — generate candidate names and test each identically.
     Confirmed names become candidates; unconfirmed ones are discarded at debug
     level.

If no tier produces a candidate, `Resolution.candidates` is empty and the import
name goes to the unresolved report.

### Wheel inspection without downloading wheels

`GET https://pypi.org/pypi/<name>/json` lists released files with their sizes.
Select the smallest `.whl`. A wheel is a zip archive, and a zip's **central
directory** — which lists every member path — sits at the end of the file.
Therefore:

1. One HTTP Range request for the trailing ~64 KB.
2. Locate the end-of-central-directory record.
3. Parse member paths and take their first path components.

Top-level names fall out of the listing alone. No member is decompressed and no
multi-megabyte wheel is transferred; typical cost is one JSON request plus one
ranged read of tens of kilobytes.

Fallbacks, in order:

- End-of-central-directory record not found in the trailing window (zip64, or a
  long archive comment): widen the window once and retry.
- Server ignores `Range` and returns the whole file: accept only if the wheel is
  under a 5 MB cap; otherwise abandon the candidate.

An abandoned candidate has no evidence and is therefore **not attempted**.
Failing closed here is deliberate: it is the difference between "we could not
prove this package provides the module" and "install it and find out."

## Verification loop

The resolver never installs anything. The attempt loop lives in `veny.py`, with
injected collaborators so it is unit-testable:

```python
def resolve_and_verify(resolution, installer, importer, *, max_attempts=3) -> Candidate | None
```

For each candidate, up to `max_attempts`:

1. Install it into the virtual environment.
2. Import-check the original import name.
3. On success: call `aliases.confirm()` and return the candidate.
4. On failure: uninstall the candidate, call `aliases.reject()`, continue.

Exhausting the candidates returns `None`, and the import name goes to the
unresolved report with a suggested override-file entry.

Uninstalling rejected candidates is required, not optional: a rejected package
left installed pollutes the environment veny is building and can shadow the
correct package on a later attempt.

## Call-site rewiring

`split_imports` (`veny.py:4462`) and `check_packages_in_venv` (`veny.py:4372`)
stop exchanging bare strings. `options.installed_imports` and
`options.uninstalled_imports` become sets of records carrying both the import
name and the resolved pip name, which retires two defects at once:

- The mixed-type sets (`veny.py:4493` holds import names, `veny.py:4497` holds
  pip names) become uniformly typed.
- `check_packages_in_venv` reads `record.import_name` directly instead of
  inverting a lossy dict, so the 68-duplicate-key inversion bug disappears by
  construction rather than by patch.

## Error handling

The governing rule: **silence for absent information, noise for contradicted
information.**

| Condition | Behavior |
| --- | --- |
| Network unreachable or timeout (5 s connect, 10 s read) | Skip T4, log at debug, continue. Offline is a normal state. |
| Cache unreadable or malformed JSON | Rename to `module_aliases_cache.json.corrupt-<timestamp>`, start empty, warn once. The bad file is kept as evidence, not deleted. |
| Override file is malformed TOML | **Hard failure. Stop.** Carrying on would resolve names contrary to what the user explicitly wrote. |
| PyPI 404, no wheels, or no matching top-level name | Not an error. The candidate simply does not materialize. |
| Target-interpreter probe fails | T2 contributes nothing, warn once, continue — the degradation contract `stdlib_index` already established. |
| Install succeeds but the import still fails | The loop working as designed: uninstall, record the rejection, try the next candidate. |

### Cache invalidation

Each entry stores the pip name, the confirming source, and the target
interpreter's version tag. An entry is used only when its version tag matches
the interpreter being probed, so a resolution verified under 3.12 never
silently governs a 3.13 run.

There is no TTL. Verified facts do not expire on a clock, and a wrong entry
corrects itself the moment its install-and-import check fails.

## Testing

Per the `test-design` skill, each test names the behavior under test and a
concrete bug that would make it fail. The resolver's injected collaborators mean
all of these run with no network and no virtual environment.

| Behavior | Bug it catches |
| --- | --- |
| Candidates from several tiers sort by `(source, pip_name)` | A heuristic-derived name outranking an override |
| An override hit never invokes the fetcher | T0 leaking network calls |
| A mutation whose wheel does not declare the import name never appears in `candidates` | The highest-consequence bug in the design: installing an unverified guess |
| End-of-central-directory located in a synthetic trailing buffer; zip64/comment case forces the widened window | Off-by-one truncation of the central directory |
| An oversized wheel with `Range` refused abandons the candidate | A fail-open regression that would download and trust arbitrary wheels |
| `confirm()` then re-`resolve()` returns the cached candidate with no fetcher call | Cache writes that do not round-trip |
| A cache entry with a mismatched interpreter tag is ignored | Cross-version cache contamination |
| A corrupt cache is quarantined and resolution proceeds; a corrupt override raises | Inverting the silence/noise policy |
| Attempt loop where candidate 1 fails and candidate 2 succeeds confirms the winner and uninstalls the reject | Leaving rejected packages installed in the venv |

## Migration

Four commits, each leaving the tree working:

1. `alias_index.py` plus its tests, not yet used by `veny.py`.
2. `resolve_and_verify` plus its tests, still unused.
3. Rewire `split_imports` and `check_packages_in_venv` to records; delete
   `module_aliases` (`veny.py:133–1351`) and `reversed_module_aliases`
   (`veny.py:1352`); add the seed constant. `veny.py` drops roughly 1,210
   lines, from 5,427 to about 4,220.
4. Update `PROGRESS.md`: retire the deferred module-alias item, record new
   gotchas.

Verification is scoped to touched files, per PROGRESS.md: repo-wide
`pixi run lint` and `pixi run typecheck` fail on 1,171 pre-existing ruff and 158
mypy errors in `veny.py` and `univ_defs.py`. `.git/hooks/pre-commit` is not
installed, so run `pixi run pre-commit run --files <paths>` by hand.

## Serialization note

`univ_defs.to_jsonable` has no handler for `StdlibIndex`, so `options.stdlib` is
serialized via `repr()` as a plain string (PROGRESS.md deferred item). An
`AliasIndex` field would hit the same trap, with the same failure mode: a
restored `repr()` string does substring matching instead of real lookup, giving
wrong answers with no error.

This design therefore adds a `to_jsonable` handler for `AliasIndex`. The
equivalent `StdlibIndex` gap remains open and stays recorded in PROGRESS.md.

## Out of scope

- `Options.also_needs` (`veny.py:120`) — a different relation
  (package → dependencies, not import → package). PROGRESS.md already defers the
  wider `split_imports` rework.
- `Options.known_bad_imports` (`veny.py:1355`) — six project-specific local
  module names; PROGRESS.md defers moving them to a config file.
- The `StdlibIndex` half of the `to_jsonable` gap described above.

## Consequences

Accepted trade-offs, stated explicitly:

- **Weaker offline cold-cache coverage than the table provided.** With no
  network and an empty cache, resolution has only T0–T3. A name such as `cv2`
  resolves offline solely because it is in the seed; an unseeded alias needs one
  online pass before it is cached. This was chosen knowingly: refusing to
  install unverified guesses is worth more than resolving rare names offline.
- **Latency on cache misses.** One PyPI JSON request plus one ranged wheel read
  per unknown name, and up to `max_attempts` install attempts for names that
  resist. Bounded, and paid once per name per interpreter version.
- **Run-to-run variability that a frozen table did not have.** PyPI is a moving
  target. Mitigated by deterministic ranking, the verified cache, and debug
  logging of the full chain.
- **A new network dependency in classification.** veny already requires network
  access to `pip install`, so this adds no new hard requirement — but it does
  move network contact earlier, into the classification phase.
