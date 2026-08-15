"""Tests for registering veny's own types with emmykit's JSON registry."""

import json

import emmykit as ek
import pytest

import alias_index
import stdlib_index
import veny_json_types


@pytest.fixture(autouse=True)
def registered():
    veny_json_types.register_types()


def roundtrip(obj):
    """Send an object through the real JSON text layer and back."""
    return ek.from_jsonable(json.loads(json.dumps(ek.to_jsonable(obj))))


def test_resolved_import_survives_a_real_json_round_trip():
    # Catches: no registration at all (the record stringifies to
    # "ResolvedImport(import_name='cv2', ...)"), or a decoder that drops one of
    # the two names -- which would send pip the wrong package.
    record = alias_index.ResolvedImport(import_name="cv2", pip_name="opencv-python")

    restored = roundtrip(record)

    assert restored == record
    assert isinstance(restored, alias_index.ResolvedImport)
    assert restored.pip_name == "opencv-python"


def test_resolved_import_tag_is_pinned():
    # Catches: renaming the "resolved_import" tag string. The round-trip test
    # above stays green under a rename -- only the encoder and decoder need to
    # agree with each other, not with the string already written to disk in
    # existing options files -- so the wire tag needs its own assertion.
    record = alias_index.ResolvedImport(import_name="cv2", pip_name="opencv-python")

    assert ek.to_jsonable(record)["__type__"] == "resolved_import"


def test_resolved_imports_survive_inside_a_set():
    # Catches: an encoder that works on a bare record but not on the shape veny
    # actually stores -- options.uninstalled_imports is a set, and sets are
    # themselves a tagged type, so the two handlers must nest.
    records = {
        alias_index.ResolvedImport(import_name="cv2", pip_name="opencv-python"),
        alias_index.ResolvedImport(import_name="yaml", pip_name="pyyaml"),
    }

    assert roundtrip(records) == records


def test_stdlib_index_survives_a_real_json_round_trip():
    # Catches: falling through to str(), which turns membership into substring
    # matching -- "ma" in the repr is True, so a restored index would call "ma"
    # a standard-library module and veny would skip installing a real package.
    index = stdlib_index.StdlibIndex(
        names=frozenset({"os", "sys", "xml"}),
        python_version=(3, 13),
        source=stdlib_index.SOURCE_PROBE,
    )

    restored = roundtrip(index)

    assert isinstance(restored, stdlib_index.StdlibIndex)
    assert restored.names == frozenset({"os", "sys", "xml"})
    assert restored.python_version == (3, 13)
    assert restored.source == stdlib_index.SOURCE_PROBE
    assert "xml.etree.ElementTree" in restored
    assert "cv2" not in restored


def test_stdlib_index_tag_is_pinned():
    # Catches: renaming the "stdlib_index" tag string -- same wire-format
    # concern as the ResolvedImport tag above.
    index = stdlib_index.StdlibIndex(
        names=frozenset(), python_version=(3, 12), source=stdlib_index.SOURCE_DEGRADED
    )

    assert ek.to_jsonable(index)["__type__"] == "stdlib_index"


def test_stdlib_index_encodes_a_readable_diff_stable_payload():
    # Catches: encoding `names` as a raw frozenset or `python_version` as a
    # raw tuple instead of a sorted list -- both would still round-trip
    # correctly, since frozenset and tuple are themselves tagged types emmykit
    # already knows how to nest, but the on-disk payload would become a
    # nested {"__type__": "frozenset", "value": [...]} blob with
    # nondeterministic member ordering, destroying the readable, diff-stable
    # options file this encoder is meant to produce.
    index = stdlib_index.StdlibIndex(
        names=frozenset({"os", "sys", "xml"}),
        python_version=(3, 13),
        source=stdlib_index.SOURCE_PROBE,
    )

    payload = ek.to_jsonable(index)

    assert payload["names"] == ["os", "sys", "xml"]
    assert payload["python_version"] == [3, 13]


@pytest.mark.parametrize("raw_version", [3, ["a", "b"]])
def test_stdlib_index_decode_falls_back_to_zero_zero_on_malformed_version(raw_version):
    # Catches: a decoder that raises a bare TypeError (non-iterable input,
    # e.g. a plain int) or ValueError (a list of non-numeric entries) out of
    # from_jsonable instead of landing on the single documented (0, 0)
    # fallback -- either crash would take down loading a whole options file
    # over one corrupt field instead of degrading to an inert index.
    payload = {
        "__type__": "stdlib_index",
        "names": ["os"],
        "python_version": raw_version,
        "source": stdlib_index.SOURCE_PROBE,
    }

    restored = ek.from_jsonable(payload)

    assert restored.python_version == (0, 0)


def test_an_empty_stdlib_index_round_trips_as_an_empty_frozenset():
    # Catches: an encoder guarded by `if names:` or a decoder using
    # `names or None` -- an empty index would come back as None and the next
    # membership test would raise TypeError instead of returning False.
    index = stdlib_index.StdlibIndex(
        names=frozenset(),
        python_version=(3, 12),
        source=stdlib_index.SOURCE_DEGRADED,
    )

    restored = roundtrip(index)

    assert restored.names == frozenset()
    assert "os" not in restored


def test_alias_index_serializes_as_a_snapshot_and_returns_a_plain_dict(tmp_path):
    # Catches: (a) falling through to str(), losing the structured snapshot;
    # (b) somebody adding a decoder -- a reconstructed AliasIndex would carry
    # installed={} and answer "nothing is installed" for every import, silently
    # reinstalling packages the target interpreter already has.
    index = alias_index.AliasIndex(
        overrides={"cv2": "my-opencv"},
        cache=alias_index.AliasCache(
            path=tmp_path / "cache.json",
            interpreter_tag="3.13",
            entries={},
            rejections={},
        ),
        installed={"cv2": ["opencv-python"]},
        pypi=None,
    )

    payload = json.loads(json.dumps(ek.to_jsonable(index)))

    assert payload["overrides"] == {"cv2": "my-opencv"}
    assert payload["interpreter_tag"] == "3.13"
    assert payload["cache_path"] == str(tmp_path / "cache.json")
    assert payload["offline"] is True
    assert "__type__" not in payload

    restored = ek.from_jsonable(payload)
    assert isinstance(restored, dict)
    assert not isinstance(restored, alias_index.AliasIndex)


def test_register_types_is_idempotent():
    # Catches: registering without guarding against a second call -- emmykit
    # raises on a duplicate tag, so the second veny.Options() in a test session
    # (or a second main() call) would die at import time.
    veny_json_types.register_types()
    veny_json_types.register_types()

    record = alias_index.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    assert roundtrip(record) == record


def test_importing_veny_is_enough_to_register_the_types():
    # Catches: register_types() never called from veny, or called only inside
    # main() -- production would then write repr strings into the options file
    # while every direct-registration test stayed green.
    import subprocess
    import sys
    from pathlib import Path

    source = (
        "import veny, json, emmykit as ek, alias_index;"
        "r = alias_index.ResolvedImport(import_name='cv2', pip_name='opencv-python');"
        "print(ek.from_jsonable(json.loads(json.dumps(ek.to_jsonable(r)))) == r)"
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"
