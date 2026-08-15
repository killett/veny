"""Tests for venv_cache."""

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
