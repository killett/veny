"""Tests for building a venv's manifest from its final state."""

import stdlib_index
import venv_cache
import veny
from alias_index import ResolvedImport


def an_options() -> veny.Options:
    """Build an Options carrying the fields manifest_for reads."""
    options = veny.Options()
    options.python_command = "/usr/bin/python3.12"
    options.stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )
    options.timestamp = "20260814-091500"
    options.uninstalled_imports = {
        ResolvedImport("yaml", "PyYAML"),
        ResolvedImport("numpy", "numpy"),
    }
    options.extra_requirements = {"numpy": ">=1.2"}
    return options


def test_manifest_for_records_versions_and_specs() -> None:
    """A manifest without versions cannot answer whether a pin is satisfied."""
    manifest = veny.manifest_for(an_options(), {"pyyaml": "6.0.2", "numpy": "2.1.3"})
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version == "6.0.2"
    assert by_pip["PyYAML"].requested_spec is None
    assert by_pip["numpy"].installed_version == "2.1.3"
    assert by_pip["numpy"].requested_spec == ">=1.2"
    assert manifest.interpreter_tag == "3.12"
    assert manifest.interpreter_path == "/usr/bin/python3.12"
    assert manifest.schema_version == venv_cache.SCHEMA_VERSION
    assert manifest.veny_version == veny.__version__


def test_manifest_for_records_an_unknown_version_as_none() -> None:
    """Inventing a version here would let an unsatisfiable pin look satisfied."""
    manifest = veny.manifest_for(an_options(), {})
    assert all(record.installed_version is None for record in manifest.packages)


def test_manifest_for_keys_versions_by_normalized_name() -> None:
    """pip reports 'PyYAML'; the record spells it differently; both name one project."""
    manifest = veny.manifest_for(an_options(), {"py-yaml": "6.0.2"})
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version is None
    manifest = veny.manifest_for(an_options(), {"pyyaml": "6.0.2"})
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version == "6.0.2"
