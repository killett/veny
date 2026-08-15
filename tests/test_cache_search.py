"""Tests for choosing cached virtual environments."""

from pathlib import Path

import stdlib_index
import venv_cache
import veny
from alias_index import ResolvedImport


def an_options(records: set[ResolvedImport]) -> veny.Options:
    """Build an Options carrying what the cache search reads."""
    options = veny.Options()
    options.stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )
    options.uninstalled_imports = records
    options.extra_requirements = {}
    return options


def a_cached_venv(
    root: Path, name: str, packages: list[venv_cache.PackageRecord], tag: str = "3.12"
) -> Path:
    """Create a cached venv directory with a manifest."""
    venv_dir = root / name
    venv_dir.mkdir(parents=True, exist_ok=True)
    venv_cache.write_manifest(
        venv_dir,
        venv_cache.Manifest(
            schema_version=venv_cache.SCHEMA_VERSION,
            created="20260814-091500",
            veny_version="0.2.2",
            interpreter_tag=tag,
            interpreter_path="/usr/bin/python3.12",
            packages=tuple(packages),
        ),
    )
    return venv_dir


def test_a_hyphenated_package_does_not_disqualify_its_own_venv(tmp_path: Path) -> None:
    """This is the reported bug: 'ruamel-yaml' read as 'ruamel' plus 'yaml' rejects a good venv."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-ruamel-yaml",
        [venv_cache.PackageRecord("ruamel.yaml", "ruamel-yaml", "0.18.6", None)],
    )
    options = an_options({ResolvedImport("ruamel.yaml", "ruamel-yaml")})
    assert [c.folder for c in veny.cache_candidates(options, [venv_dir])] == [venv_dir]


def test_a_venv_without_a_manifest_is_skipped(tmp_path: Path) -> None:
    """Pre-manifest venvs must be rebuilt, not matched on their names alone."""
    venv_dir = tmp_path / "myenv-py3.12-20260814-091500-numpy"
    venv_dir.mkdir()
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert veny.cache_candidates(options, [venv_dir]) == []


def test_a_venv_for_another_interpreter_is_skipped(tmp_path: Path) -> None:
    """A 3.13 venv cannot serve a run classified against 3.12's standard library."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.13-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
        tag="3.13",
    )
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert veny.cache_candidates(options, [venv_dir]) == []


def test_a_venv_missing_a_package_is_skipped(tmp_path: Path) -> None:
    """Matching on the name alone would accept a venv whose manifest disagrees."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    options = an_options(
        {ResolvedImport("numpy", "numpy"), ResolvedImport("scipy", "scipy")}
    )
    assert veny.cache_candidates(options, [venv_dir]) == []


def test_a_pin_is_checked_against_the_installed_version(tmp_path: Path) -> None:
    """Ignoring --reqs pins hands back a venv that violates them."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "1.0.0", ">=1.2")],
    )
    options = an_options({ResolvedImport("numpy", "numpy")})
    options.extra_requirements = {"numpy": ">=1.2"}
    assert veny.cache_candidates(options, [venv_dir]) == []
    options.extra_requirements = {"numpy": ">=0.9"}
    assert [c.folder for c in veny.cache_candidates(options, [venv_dir])] == [venv_dir]


def test_a_folder_that_loses_its_manifest_between_calls_is_dropped_not_raised(
    tmp_path: Path,
) -> None:
    """The cache directory can be mutated by another process; a vanished manifest must degrade, not crash."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert [c.folder for c in veny.cache_candidates(options, [venv_dir])] == [venv_dir]
    (venv_dir / venv_cache.MANIFEST_FILENAME).unlink()
    assert veny.cache_candidates(options, [venv_dir]) == []


def test_wanted_packages_carries_the_requested_specs() -> None:
    """A spec dropped here makes every pin invisible to matching."""
    options = an_options({ResolvedImport("numpy", "numpy")})
    options.extra_requirements = {"numpy": ">=1.2"}
    assert veny.wanted_packages(options) == [venv_cache.Wanted("numpy", ">=1.2")]


def test_check_venv_dir_rejects_a_directory_with_no_manifest(tmp_path: Path) -> None:
    """The last-used pointer can outlive the venv it points at."""
    venv_dir = tmp_path / "myenv-py3.12-20260814-091500-numpy"
    venv_dir.mkdir()
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert veny.check_venv_dir(options, venv_dir) is False


def test_check_venv_dir_rejects_a_missing_directory(tmp_path: Path) -> None:
    """A deleted venv must be a cache miss, not an exception."""
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert veny.check_venv_dir(options, tmp_path / "gone") is False


def test_check_venv_dir_rejects_a_manifest_that_does_not_match(tmp_path: Path) -> None:
    """Reusing a venv that lacks a package fails at the user's runtime."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    options = an_options({ResolvedImport("scipy", "scipy")})
    assert veny.check_venv_dir(options, venv_dir) is False
