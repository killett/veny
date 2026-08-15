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


def test_record_venv_state_renames_before_writing_the_manifest(monkeypatch, tmp_path):
    """A stale folder name would reject a venv the manifest would accept.

    The folder name is written before installing, from the pre-repair pip
    names. If verify_and_repair_imports later swaps one -- exactly what this
    test's records simulate, "yaml" repaired to "PyYAML" plus "numpy" newly
    added -- the folder must be brought back into agreement before the
    manifest is written, and the "failed-" prefix must survive that rename.
    """
    options = an_options()
    old_name = "failed-" + venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=veny.interpreter_tag(options),
        timestamp=options.timestamp,
        pip_names=["yaml"],  # The pre-repair pip name the folder was built with.
    )
    old_dir = tmp_path / old_name
    options.set_venv_dir(old_dir)  # Creates old_dir on disk.

    # Real record_venv_state, real rename_venv, real venv_cache.write_manifest
    # -- only the interpreter probe is stubbed, since it would otherwise spawn
    # a real Python.
    monkeypatch.setattr(
        veny, "installed_versions_in_venv",
        lambda opts: {"pyyaml": "6.0.2", "numpy": "2.1.3"},
    )

    veny.record_venv_state(options)

    wanted_name = venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=veny.interpreter_tag(options),
        timestamp=options.timestamp,
        pip_names=[record.pip_name for record in options.uninstalled_imports],
    )
    new_dir = tmp_path / f"failed-{wanted_name}"

    assert old_dir != new_dir, "the test setup must simulate an actual repair"
    assert options.venv_dir == new_dir
    assert new_dir.is_dir()
    assert not old_dir.exists()

    assert not (old_dir / venv_cache.MANIFEST_FILENAME).exists()
    manifest = venv_cache.read_manifest(new_dir)
    assert manifest is not None
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version == "6.0.2"
    assert by_pip["numpy"].installed_version == "2.1.3"
