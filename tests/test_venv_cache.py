"""Tests for venv_cache."""

import json
from pathlib import Path

import pytest

import venv_cache


def test_build_folder_name_normalizes_and_joins_with_underscores() -> None:
    """A hyphen inside a pip name must not be mistaken for a field separator."""
    name = venv_cache.build_folder_name(
        venv_name="myenv",
        interpreter_tag="3.12",
        timestamp="20260814-091500",
        pip_names=["ruamel.yaml", "NumPy", "types_requests"],
    )
    assert name == "myenv-py3.12-20260814-091500-numpy_ruamel-yaml_types-requests"


def test_parse_folder_name_recovers_hyphenated_package_names() -> None:
    """Splitting the whole name on '-' shatters 'ruamel-yaml' into two fragments."""
    parsed = venv_cache.parse_folder_name(
        "myenv-py3.12-20260814-091500-numpy_ruamel-yaml_types-requests"
    )
    assert parsed is not None
    assert parsed.venv_name == "myenv"
    assert parsed.interpreter_tag == "3.12"
    assert parsed.timestamp == "20260814-091500"
    assert parsed.packages == frozenset({"numpy", "ruamel-yaml", "types-requests"})
    assert parsed.unnamed_count == 0


def test_more_than_five_packages_are_summarised_and_counted() -> None:
    """An off-by-one in the overflow count makes the prefilter reject good venvs."""
    pip_names = ["a", "b", "c", "d", "e", "f", "g", "h"]
    name = venv_cache.build_folder_name("myenv", "3.12", "20260814-091500", pip_names)
    assert name == "myenv-py3.12-20260814-091500-a_b_c_d_e_and_3_more"
    parsed = venv_cache.parse_folder_name(name)
    assert parsed is not None
    assert parsed.packages == frozenset({"a", "b", "c", "d", "e"})
    assert parsed.unnamed_count == 3


def test_parse_folder_name_rejects_malformed_names() -> None:
    """An unrelated directory in ~/veny must not be treated as a venv candidate."""
    assert venv_cache.parse_folder_name("myenv-py3.12-20260814-091500") is None
    assert venv_cache.parse_folder_name("myenv-3.12-20260814-091500-numpy") is None
    assert venv_cache.parse_folder_name("myenv-py3.12-2026081-091500-numpy") is None
    assert venv_cache.parse_folder_name("myenv-py3.12-20260814-091500-") is None
    assert venv_cache.parse_folder_name("") is None


def test_normalize_pip_name_matches_pep503() -> None:
    """Comparing two spellings of one project requires the same rule on both sides."""
    assert venv_cache.normalize_pip_name("Ruamel.YAML") == "ruamel-yaml"
    assert venv_cache.normalize_pip_name("types__requests") == "types-requests"


def a_manifest() -> venv_cache.Manifest:
    """Build a manifest fixture with one plain and one pinned package."""
    return venv_cache.Manifest(
        schema_version=venv_cache.SCHEMA_VERSION,
        created="20260814-091500",
        veny_version="0.2.2",
        interpreter_tag="3.12",
        interpreter_path="/usr/bin/python3.12",
        packages=(
            venv_cache.PackageRecord("yaml", "PyYAML", "6.0.2", None),
            venv_cache.PackageRecord("numpy", "numpy", "2.1.3", ">=1.2"),
        ),
    )


def test_manifest_round_trips_every_field(tmp_path: Path) -> None:
    """A dropped requested_spec would turn every pinned package into an unpinned one."""
    assert venv_cache.write_manifest(tmp_path, a_manifest()) is True
    assert venv_cache.read_manifest(tmp_path) == a_manifest()


def test_read_manifest_returns_none_for_a_missing_file(tmp_path: Path) -> None:
    """A pre-manifest venv must be skipped, not crash the run."""
    assert venv_cache.read_manifest(tmp_path) is None


def test_read_manifest_returns_none_for_malformed_json(tmp_path: Path) -> None:
    """A truncated write must cost one cache miss, not abort the run."""
    (tmp_path / venv_cache.MANIFEST_FILENAME).write_text('{"schema_version": 1,')
    assert venv_cache.read_manifest(tmp_path) is None


def test_read_manifest_returns_none_for_an_unknown_schema_version(tmp_path: Path) -> None:
    """A future schema read as version 1 would match on fields that changed meaning."""
    data = {
        "schema_version": venv_cache.SCHEMA_VERSION + 1,
        "created": "20260814-091500",
        "veny_version": "0.2.2",
        "interpreter_tag": "3.12",
        "interpreter_path": "/usr/bin/python3.12",
        "packages": [],
    }
    (tmp_path / venv_cache.MANIFEST_FILENAME).write_text(json.dumps(data))
    assert venv_cache.read_manifest(tmp_path) is None


def test_read_manifest_returns_none_when_a_package_entry_is_not_a_mapping(
    tmp_path: Path,
) -> None:
    """A hand-edited manifest must degrade to a cache miss, not a TypeError."""
    data = {
        "schema_version": venv_cache.SCHEMA_VERSION,
        "created": "20260814-091500",
        "veny_version": "0.2.2",
        "interpreter_tag": "3.12",
        "interpreter_path": "/usr/bin/python3.12",
        "packages": ["numpy"],
    }
    (tmp_path / venv_cache.MANIFEST_FILENAME).write_text(json.dumps(data))
    assert venv_cache.read_manifest(tmp_path) is None


def test_write_manifest_returns_false_when_the_directory_is_missing(tmp_path: Path) -> None:
    """A venv that cannot record itself is still usable now; it just will not be reused."""
    assert venv_cache.write_manifest(tmp_path / "absent", a_manifest()) is False


def test_read_manifest_returns_none_for_invalid_utf8(tmp_path: Path) -> None:
    """A truncated multi-byte UTF-8 sequence must degrade to a cache miss, not raise."""
    (tmp_path / venv_cache.MANIFEST_FILENAME).write_bytes(b'{"schema_version": 1, "created": "\xff\xfe"}')
    assert venv_cache.read_manifest(tmp_path) is None


@pytest.mark.parametrize(
    ("installed", "spec", "expected"),
    [
        ("1.10.0", ">1.9", True),      # lexicographic compare would say "1.10" < "1.9"
        ("1.2", ">=1.2.0", True),      # zero padding
        ("1.2.0", "==1.2", True),      # zero padding, other direction
        ("1.2.3", "~=1.2.0", True),    # compatible release, in range
        ("1.3.0", "~=1.2.0", False),   # compatible release, above the bound
        ("1.9.9", "~=1.2", True),      # two-component compatible release
        ("2.0.0", "~=1.2", False),
        ("1.2.5", "==1.2.*", True),    # prefix match on release segments
        ("1.3.0", "==1.2.*", False),
        ("1.20.0", "==1.2.*", False),  # string prefix matching would say True
        ("1.5", ">=1.0,<2.0", True),   # every clause must hold
        ("2.1", ">=1.0,<2.0", False),
        ("1.5", "!=1.5", False),
        ("1.5", "!=1.6", True),
    ],
)
def test_version_satisfies_supported_forms(installed: str, spec: str, expected: bool) -> None:
    """A comparator that compares strings, or honours only the first clause, fails here."""
    assert venv_cache.version_satisfies(installed, spec) is expected


@pytest.mark.parametrize(
    ("installed", "spec"),
    [
        ("1.2b1", ">=1.0"),    # pre-release
        ("1.2.post1", ">=1.0"),
        ("1.2.dev0", ">=1.0"),
        ("1.2+cpu", ">=1.0"),  # local version
        ("1!2.0", ">=1.0"),    # epoch
        ("1.2", "===1.2"),     # arbitrary equality
        ("1.2", ">=1.0b1"),    # unsupported form on the spec side
        ("1.2", "~=1"),        # compatible release needs two components
        ("1.2", "1.2"),        # no operator
        ("1.2", ""),           # present but empty
        ("1.2", "@ https://example.invalid/x.whl"),
        (None, ">=1.0"),       # unknown installed version
    ],
)
def test_version_satisfies_fails_closed(installed: str | None, spec: str) -> None:
    """Stripping a suffix and comparing anyway would report a pre-release as satisfying a pin."""
    assert venv_cache.version_satisfies(installed, spec) is False
