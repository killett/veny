# Design: replace univ_defs with the emmykit package

**Status:** approved 2026-08-14

## Problem

`veny.py` opens with `import univ_defs as ud` and reaches through that alias at
93 call sites; the tests reach through it at 7 more. `univ_defs.py` is a
9,757-line file sitting beside `veny.py` in this repository. It has been
superseded by [`emmykit`](https://pypi.org/project/emmykit/), a published
package built from the same code.

Keeping the local copy costs more than the duplication. The two have already
diverged (`from_jsonable` handles a missing `value` key differently), so a bug
fixed in emmykit does not reach veny. And the local copy carries a coupling
that should never have existed: `univ_defs._to_jsonable` lazily imports
`alias_index` so it can recognise veny's own types — a utility library
importing its consumer.

## Compatibility, measured

Every symbol veny uses is present in emmykit 0.3.4:

- 41 distinct `ud.*` symbols across `veny.py` and the three test files; all 41
  exist on emmykit's flat top-level namespace.
- Of those, the 27 callables have byte-identical signatures; the constants
  compare equal (`PY_VERSION`, `DEFAULT_ENCODING`, `COMPUTER_NAME`,
  `PYTHON_EXTENSIONS`, the ANSI colours).
- `univ_defs`' 204 public names are a subset of emmykit's 208.

Four differences matter, and each is addressed below: veny's types are not
serializable by emmykit; `Options.args` has a different default; emmykit's
embedded script constants still reference `univ_defs`; and `from_jsonable`
differs in its handling of a missing `value` key (emmykit's is the safer
form, and veny does not depend on the difference).

## Decisions

### emmykit becomes a hard dependency

`veny.py` imports emmykit directly and exits with an actionable message if it
is missing. The guard is stdlib-only, because none of emmykit's helpers —
including `my_critical_error` — exist at that point:

```python
try:
    import emmykit as ek
except ImportError as exc:
    raise SystemExit(
        "veny requires the emmykit package (>=0.4.0), which is not installed.\n"
        "Install it with:  pip install 'emmykit>=0.4.0'"
    ) from exc
```

`pyproject.toml` declares `emmykit>=0.4.0,<1.0`; `pixi.toml` gains it via
`pixi add --pypi emmykit`, since emmykit is not on conda-forge (the API returns
404) and the project standard is `--pypi` only for packages conda-forge lacks.
The floor is 0.4.0 because the serialization registry does not exist before it.
The ceiling stops a future 1.0 from changing behaviour under veny silently.

This **supersedes** the cross-cutting decision of 2026-08-12, "No third-party
dependency may be required to run veny." That decision was argued against
`stdlib_list` — an external package supplying data veny could derive for
itself. emmykit is the utility layer veny is already built on, is first-party,
and is stdlib-only in its base layer. PROGRESS records the supersession rather
than deleting the original decision.

The two rejected alternatives, for the record. Self-bootstrapping (veny
pip-installs emmykit on `ImportError`) puts a second, homegrown installer on
veny's startup path — before logging is configured — and it would have to
handle PEP 668 externally-managed environments, `--user` versus venv,
permissions and offline, all of which veny's main path already handles once.
Keeping `univ_defs.py` as an `except ImportError` fallback preserves two code
paths forever, doubles the test matrix, and invites silent behavioural drift of
exactly the kind the two `from_jsonable` implementations already show.

### The alias becomes `ek`

`import emmykit as ek`, and `ud.` becomes `ek.` at every call site, including
`class Options(ek.Options)`. Keeping `as ud` would leave the alias naming a
file that no longer exists.

The substitution is width-preserving, which matters here specifically:
`veny.py`'s hand-aligned comment and value columns must survive, and the
standing rule is that ruff-format must never be run against `veny.py` (a trial
run once rewrote ~2,000 lines of its alignment). `ud` and `ek` are both two
characters, so the alignment is unaffected.

`veny.py` is the only production consumer. `alias_index.py`, `venv_cache.py`,
`stdlib_index.py` and `pypi_client.py` deliberately import nothing from
`univ_defs`, and that one-way discipline is unchanged by this work. The seam is
therefore a single import line; no adapter module is introduced, because the
indirection would buy nothing.

### veny's types are serialized through a registry in emmykit

emmykit's `save_options_to_json` calls its own module-level `to_jsonable`
(`json_io.py:294`), so a veny-side wrapper would never be reached on the path
veny actually uses (`veny.py:475` saves, `veny.py:4558` loads). The hook must
exist inside emmykit.

emmykit 0.4.0 therefore gains a public registry:

```python
def register_json_type(cls, encode, *, tag=None, decode=None, replace=False) -> None
def unregister_json_type(cls_or_tag) -> None
```

`tag` and `decode` are optional together; supplying one without the other is an
error. Omitting both registers an *encode-only* type, whose payload is never
tagged and which therefore reloads as a plain `dict`.

This inverts the dependency correctly: emmykit provides the mechanism, veny
supplies the knowledge, and emmykit never learns what an `AliasIndex` is. It
also serves emmykit's other consumers, which the veny-local alternatives would
not.

The prompt for that work is `docs/prompts/2026-08-14-emmykit-json-type-registry.md`.

In this repository, a new module `veny_json_types.py` exposes
`register_types()`, idempotent, called once early in `main()` before any
options are saved or loaded. An explicit call rather than import side effects:
it is testable, and it does not read as an unused import.

Three registrations:

| Type | Tag | Round trip |
| --- | --- | --- |
| `alias_index.ResolvedImport` | `resolved_import` | Full — `import_name`, `pip_name` |
| `stdlib_index.StdlibIndex` | `stdlib_index` | Full — `names`, `python_version`, `source` |
| `alias_index.AliasIndex` | *(none)* | Encode-only |

`StdlibIndex`'s registration closes a deferred item: today it falls through to
`str()`, so a restored `options.stdlib` would answer membership tests by
substring matching (`"ma" in restored` is `True` because the repr contains
those letters) with nothing raising.

`AliasIndex` is encode-only **by design**. It holds `installed`, a mapping
obtained by probing the target interpreter, and `pypi`, a live HTTP client.
A decoder could rebuild the other fields, but the resulting index would resolve
imports differently from the real one while looking identical — a fail-open
error of the sort this project has been bitten by before. Its payload stays
what it is today: a diagnostic snapshot of overrides, interpreter tag, cache
path and offline flag. The reason is recorded in the module docstring so that
the missing decoder is not later mistaken for an oversight.

### The five helper scripts leave veny

`veny.py:326-331` writes six files into `options.my_dir`: `mydiff.py`,
`myaudit.py`, `multireplace.py`, `treeview.py`, `printall.py`, and
`univ_defs_sys_path_script.py`. veny never runs any of them. It writes them
only because it happened to have `verify_script` and the constants to hand.

All six calls are removed, along with the six path fields (`veny.py:95-100`)
and `options.univ_defs_path` (`veny.py:94`), which is assigned and never read.

The five scripts move to the `killett/utilities` repository, whose stated
purpose is "General use python scripts. Most of them import emmykit" and whose
existing contents are the same shape. As string constants inside the library
they import, they are the only code in emmykit that cannot be linted,
type-checked, tested or imported. The prompt for that work is
`docs/prompts/2026-08-14-utilities-adopt-emmykit-scripts.md`.

The `sys.path` shim is deleted, not moved. It existed because `univ_defs.py`
was a loose file that nothing put on `sys.path`, so a standalone script could
not import it; an installed package needs no such help. It is also already
broken: emmykit's copy of the constant points `sys.path` at the inner
`.../site-packages/emmykit` directory, which would expose `json_io` and friends
as top-level modules and still would not make `import emmykit` work.

### `Options.args` changes default

emmykit's `Options.__init__` sets `self.args = argparse.Namespace()`, where
`univ_defs`' set it to `None` and annotated it `argparse.Namespace | None`.
veny assigns `options.args` at `veny.py:239` and asserts it non-`None` at
`240`; every other read goes through `getattr(options.args, ...)`. The change
is expected to be behaviour-neutral, but the plan verifies that rather than
assuming it — the failure mode would be an `if options.args is None` branch
that quietly stops firing.

### `univ_defs.py` is deleted

Git history keeps it. README's project-structure section drops its line and
gains a note that veny depends on emmykit.

## Sequencing

The veny branch is built now and merged only after emmykit 0.4.0 is released:

1. Run the emmykit prompt in the emmykit repository; release 0.4.0.
2. In parallel, build the veny branch: dependency declaration, import guard,
   `ud` → `ek` rename, helper-script removal, `univ_defs.py` deletion, test
   port.
3. Add `veny_json_types.py` against the released API, pin `emmykit>=0.4.0`,
   verify, merge.
4. The utilities-repo work is independent and can happen at any time; it
   extracts from `emmykit==0.3.4`, which still has the constants.

Migrating against 0.3.4 and registering the types afterwards was rejected: it
would put a known silent-degradation window into `main`, where `AliasIndex` and
`ResolvedImport` fall through to `str()`. Nothing reads those fields off a
restored options object today, but that code is explicitly precautionary, and
deleting a guard because nothing currently trips it is how the `check_venv_dir`
finding of the previous branch happened.

## Testing

The three test files switch to `import emmykit as ek`. New coverage:

- An options object carrying a `ResolvedImport` and a `StdlibIndex` survives a
  real `ek.save_options_to_json` / `ek.load_options_from_json` round trip, with
  the reconstructed values asserted equal *and* of the right type — not merely
  that the call did not raise.
- `AliasIndex` reloads as a `dict`, pinning the encode-only choice so that a
  later change to a fabricated decoder fails a test.
- `register_types()` is idempotent.
- The import guard, as a subprocess test: setting `sys.modules["emmykit"] =
  None` in a child process makes `import emmykit` raise `ImportError`, proving
  veny exits with the install message rather than a traceback.

## Verification

- Full suite green (223 tests as of this branch's start).
- `ruff check` and `mypy` scoped to the touched files only. Repo-wide runs fail
  on pre-existing `veny.py` / `univ_defs.py` debt, and pre-commit's
  `ruff`/`ruff-format` hooks must never run against `veny.py`.
- One live end-to-end run of veny against a real script, because the layer
  being swapped is the one every path depends on.

## Out of scope

- The two parked venv-cache review findings (interpreter-tag source, the
  double `satisfies()` call).
- `also_needs`, and splitting `veny.py` or the now-deleted `univ_defs.py`.
- Any change to `alias_index.py`'s mutation generator (the `ruamel` gap).
