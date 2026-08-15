# Prompt: add a public custom-type registry to emmykit's JSON serialization

Paste everything below the line into a Claude Code session opened in the
`emmykit` repository.

---

Add a public extension point to `emmykit`'s JSON serialization so that a
consuming package can teach `to_jsonable` / `from_jsonable` about its own
types, without `emmykit` importing that package.

## Why

`emmykit.json_io.to_jsonable` recognises a fixed set of types and falls back to
`str()` for anything else. A consumer with its own types therefore has two bad
choices: accept a silent `str()` flattening, or patch its types into
`emmykit`'s own source. The predecessor of this package (`univ_defs.py`) took
the second path — it did a lazy `import alias_index` inside `_to_jsonable` so
it could recognise a consumer's types. That inverts the dependency: a utility
library importing its own consumer.

`veny` is the first consumer to need this. It has three types that must
survive a JSON round trip — `alias_index.ResolvedImport`,
`alias_index.AliasIndex`, and `stdlib_index.StdlibIndex` — and it reaches them
through `emmykit.save_options_to_json` / `load_options_from_json`, which call
`to_jsonable` / `from_jsonable` internally. A registry lets `veny` supply the
knowledge while `emmykit` supplies only the mechanism.

The failure mode this prevents is silent, not loud. When an unregistered
object falls through to `str()`, a reloaded options file holds a repr string
where a lookup object should be, and membership tests degrade to substring
matching — `"ma" in restored` is `True` because the repr happens to contain
those letters. Nothing raises; the answers are just wrong.

## What to build

A public registry in `emmykit/json_io.py`, re-exported from the top-level
`emmykit` namespace (consumers use the flat surface, e.g. `ek.to_jsonable`).

Suggested shape — adjust names to match the package's conventions:

```python
def register_json_type(
    cls: type,
    encode: Callable[[Any], dict[str, Any]],
    *,
    tag: str | None = None,
    decode: Callable[[dict[str, Any]], Any] | None = None,
    replace: bool = False,
) -> None: ...

def unregister_json_type(cls_or_tag: type | str) -> None: ...
```

`tag` and `decode` are optional **together**: supplying one without the other is
an error. Omitting both registers an *encode-only* type — see below.

Requirements:

1. **Encode side.** `_to_jsonable` consults the registry *before* the `str()`
   fallback and before any generic object/`__dict__` handling, so a registered
   type always wins over the generic path. Dispatch is by `isinstance`, so a
   subclass of a registered class is handled; when two registrations both
   match, the more specific class wins, and ties break in favour of the most
   recently registered.
2. **Round-trip tagging.** With `roundtrip=True` the result is
   `{"__type__": tag, **encode(obj)}`, matching the existing built-in
   handlers. With `roundtrip=False` the bare payload is returned, untagged.
3. **Encode-only registration.** A type registered with no `tag` and no
   `decode` is serialized through its encoder but never tagged, in either
   `roundtrip` mode, and so reloads as a plain `dict`. This is not an
   oversight to design away: some objects can be *described* faithfully but
   not *rebuilt* faithfully — veny's `AliasIndex` holds a mapping obtained by
   probing a live interpreter and a live HTTP client, so a reconstructed one
   would answer differently from the real one while looking identical. For
   those, a readable snapshot plus an honest `dict` on reload beats a decoder
   that fabricates a plausible-but-wrong object. Make this a first-class,
   documented mode rather than something a caller has to fake.
4. **Nested values.** The dict returned by `encode` is itself passed through
   `_to_jsonable`, so a payload may contain `Path`, `set`, `datetime`, or
   another registered type. The existing `_seen` recursion guard must stay in
   effect across that call — a registered encoder must not be able to defeat
   it.
5. **Decode side.** `from_jsonable` looks up `__type__` in the registry after
   its built-in tags and calls `decode(payload)`. Behaviour for an unknown tag
   must not change from what it is today.
6. **Duplicate registration.** Registering a tag that is already registered
   raises unless `replace=True`, and so does registering a class that is
   already registered. Tags that collide with a built-in tag (`datetime`,
   `date`, `time`, `decimal`, `re_pattern`, `recursion`, and any others
   already in use) are rejected outright.
7. **No consumer imports.** `emmykit` must not import any consuming package,
   lazily or otherwise, to make this work.
8. **Backwards compatibility.** Every currently supported type keeps
   serializing exactly as it does now, and a JSON payload written by an
   earlier `emmykit` still loads. The registry starts empty.

## Tests

Follow the repository's existing test conventions and TDD discipline — write
each test, watch it fail, then implement.

Cover at least:

- Round trip of a custom class through `to_jsonable` → `json.dumps` →
  `json.loads` → `from_jsonable`, asserting equality of the reconstructed
  object, not merely that it is the right class.
- A registered object nested inside a `dict`, a `list`, and a `set`.
- `roundtrip=False` yields the bare payload with no `__type__` key, and a
  registered encoder whose payload itself contains a `Path` and a `set`.
- An encode-only registration (no `tag`, no `decode`) emits an untagged payload
  under `roundtrip=True` and reloads as a plain `dict`; supplying `tag` without
  `decode`, or `decode` without `tag`, raises.
- Subclass dispatch, and the specificity rule when a base class and a subclass
  are both registered.
- Duplicate-tag registration raises; `replace=True` succeeds; a built-in tag is
  rejected.
- An unknown `__type__` behaves exactly as it did before this change (pin the
  current behaviour in a test first, then keep it green).
- The recursion guard still fires for a self-referencing structure reached
  through a registered encoder.
- `unregister_json_type` removes the handler and the type falls back to the
  previous behaviour — and use it (or a fixture) to keep registrations from
  leaking between tests.

## Second job in the same session: retire the embedded script constants

`emmykit` currently carries five standalone command-line programs as string
constants in `embedded_scripts.py` — `PRINTALL_SCRIPT` (260 lines),
`MYDIFF_SCRIPT`, `MYAUDIT_SCRIPT`, `MULTIREPLACE_SCRIPT`, `TREEVIEW_SCRIPT`
(60-71 lines each) — plus `UNIV_DEFS_SYS_PATH_SCRIPT`, a generated shim that
appends a directory to `sys.path`.

These are moving to the `killett/utilities` repository as real `.py` files,
where they can be linted, type-checked, tested and imported like ordinary
code. As string constants inside the library they import, none of that is
possible.

The shim is being deleted outright, not moved. It existed because
`univ_defs.py` was a loose file that no `sys.path` entry pointed at, so a
standalone script could not import it. `emmykit` is an installed package, so
`import emmykit` already works anywhere the package is installed — the shim
solves a problem that packaging has already solved. It is also already broken:
the constant points `sys.path` at the *inner* `.../site-packages/emmykit`
directory, which would expose `json_io`, `constants` and friends as top-level
modules and still would not make `import emmykit` work.

In this session:

- Delete all six constants and any now-unused code in `embedded_scripts.py`
  (delete the module if nothing remains), along with their re-exports from the
  top-level namespace.
- Note them in the CHANGELOG as a breaking removal, with a pointer to
  `killett/utilities`.
- Before deleting, print each constant's exact text to files so it can be
  moved verbatim — the utilities repo work depends on the current content, and
  the five scripts must not be rewritten from memory.

The only known consumer of these constants is `veny`, which writes them to
disk and never runs them; it is dropping that behaviour in the same release
cycle. Both removals belong in 0.4.0.

## Also

- Document the registry in the README with a short worked example.
- Add a CHANGELOG entry covering both the registry and the constant removals.
- Bump the minor version (0.3.4 → 0.4.0) — new public API plus a breaking
  removal.
- Report the released version number when done; `veny` will pin against it.

## The consumer's call sites, for context

`veny` will register three types. Two round-trip:

```python
import emmykit as ek
import alias_index

ek.register_json_type(
    alias_index.ResolvedImport,
    lambda o: {"import_name": o.import_name, "pip_name": o.pip_name},
    tag="resolved_import",
    decode=lambda p: alias_index.ResolvedImport(
        import_name=p.get("import_name", ""), pip_name=p.get("pip_name", "")
    ),
)
```

`stdlib_index.StdlibIndex` follows the same shape (`names`, `python_version`,
`source` — all self-contained). `alias_index.AliasIndex` is the encode-only
case described above: its payload is a diagnostic snapshot (overrides,
interpreter tag, cache path, offline flag) and it deliberately gets no tag and
no decoder, because its `installed` mapping comes from probing a live
interpreter and cannot be honestly reconstructed from JSON.
