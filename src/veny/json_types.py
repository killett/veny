"""Registers veny's own types with emmykit's JSON type registry.

emmykit serializes options files through ``to_jsonable``/``from_jsonable``, and
knows nothing about veny's types. Rather than teaching the utility library about
its consumer -- which is what the retired ``univ_defs.py`` did, by lazily
importing ``alias_index`` inside its own serializer -- veny supplies the
knowledge here and emmykit supplies only the mechanism.

This module imports ``emmykit``, ``alias_index`` and ``stdlib_index``. It must
never import ``veny``: that would close an import cycle, since ``veny`` imports
this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import emmykit as ek

from . import alias_index, stdlib_index

_registered = False


def register_types() -> None:
    """Register veny's types with emmykit's JSON registry.

    Idempotent: a second call is a no-op, so importing veny twice (or calling
    main() twice in one process, as the tests do) cannot raise on a duplicate
    tag.
    """
    global _registered
    if _registered:
        return

    ek.register_json_type(
        alias_index.ResolvedImport,
        _encode_resolved_import,
        tag="resolved_import",
        decode=_decode_resolved_import,
    )
    ek.register_json_type(
        stdlib_index.StdlibIndex,
        _encode_stdlib_index,
        tag="stdlib_index",
        decode=_decode_stdlib_index,
    )
    # Encode-only, deliberately: see _encode_alias_index's docstring.
    ek.register_json_type(alias_index.AliasIndex, _encode_alias_index)

    _registered = True


def _encode_resolved_import(record: alias_index.ResolvedImport) -> dict[str, Any]:
    """Return the JSON payload for a ResolvedImport."""
    return {"import_name": record.import_name, "pip_name": record.pip_name}


def _decode_resolved_import(payload: dict[str, Any]) -> alias_index.ResolvedImport:
    """Rebuild a ResolvedImport from its JSON payload."""
    return alias_index.ResolvedImport(
        import_name=payload.get("import_name", ""),
        pip_name=payload.get("pip_name", ""),
    )


def _encode_stdlib_index(index: stdlib_index.StdlibIndex) -> dict[str, Any]:
    """Return the JSON payload for a StdlibIndex."""
    return {
        "names": sorted(index.names),
        "python_version": list(index.python_version),
        "source": index.source,
    }


def _decode_stdlib_index(payload: dict[str, Any]) -> stdlib_index.StdlibIndex:
    """Rebuild a StdlibIndex from its JSON payload.

    ``names`` is restored as a frozenset and ``python_version`` as a two-tuple,
    because a list would make ``__contains__`` linear and would compare unequal
    to every freshly built index.
    """
    return stdlib_index.StdlibIndex(
        names=frozenset(payload.get("names", [])),
        python_version=_coerce_python_version(payload.get("python_version")),
        source=payload.get("source", stdlib_index.SOURCE_DEGRADED),
    )


def _coerce_python_version(raw: object) -> tuple[int, int]:
    """Coerce a JSON value into a ``(major, minor)`` version tuple.

    Every malformed shape -- absent, not iterable, the wrong length, or
    holding non-numeric entries -- lands on the single documented fallback
    ``(0, 0)`` instead of raising a bare ``TypeError`` or ``ValueError`` out
    of ``from_jsonable``. ``(0, 0)`` matches no real interpreter, so a
    corrupt options file degrades to an inert index rather than crashing.

    Args:
        raw: The ``python_version`` value read from the JSON payload.

    Returns:
        A two-int tuple, or ``(0, 0)`` if ``raw`` cannot be coerced into one.
    """
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return (0, 0)
    try:
        return (int(raw[0]), int(raw[1]))
    except (TypeError, ValueError):
        return (0, 0)


def _encode_alias_index(index: alias_index.AliasIndex) -> dict[str, Any]:
    """Return a diagnostic snapshot of an AliasIndex.

    Registered without a tag or a decoder, so this payload reloads as a plain
    dict. That is deliberate and must not be "fixed": an AliasIndex holds
    ``installed``, obtained by probing the target interpreter, and ``pypi``, a
    live HTTP client. A decoder could rebuild the other fields, but the result
    would resolve imports differently from the real index while looking
    identical -- reporting nothing as installed, and reinstalling packages the
    interpreter already has. A readable snapshot plus an honest dict on reload
    beats a plausible-but-wrong object.
    """
    return {
        "overrides": dict(index.overrides),
        "interpreter_tag": index.cache.interpreter_tag,
        "cache_path": _fspath(index.cache.path),
        "offline": index.pypi is None,
    }


def _fspath(path: Path | str) -> str:
    """Return a path as a plain string for JSON."""
    return str(path)
