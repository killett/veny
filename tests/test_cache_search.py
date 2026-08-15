"""Tests for choosing cached virtual environments."""

import argparse
import contextlib
import importlib
import io
import subprocess
from pathlib import Path

import emmykit as ek
import pytest

from veny import alias_index
from veny import cli as veny
from veny import stdlib_index
from veny import venv_cache
from veny.alias_index import ResolvedImport


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
    """Rejected by cache_candidates' interpreter-tag check; its manifest is never read at all."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.13-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
        tag="3.13",
    )
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert veny.cache_candidates(options, [venv_dir]) == []


def test_a_venv_missing_a_package_is_skipped(tmp_path: Path) -> None:
    """Rejected by name_allows before satisfies() is ever called: the name has no room for scipy."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    options = an_options(
        {ResolvedImport("numpy", "numpy"), ResolvedImport("scipy", "scipy")}
    )
    assert veny.cache_candidates(options, [venv_dir]) == []


def test_a_venv_whose_name_allows_it_but_manifest_disagrees_is_skipped(
    tmp_path: Path,
) -> None:
    """The folder name is a prefilter only: it can list a package the manifest never actually recorded."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy_scipy",
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


def test_wanted_packages_finds_a_pin_keyed_by_a_different_spelling() -> None:
    """The record's pip_name and the user's --reqs spelling can differ in case or separators for one project."""
    options = an_options({ResolvedImport("yaml", "pyyaml")})
    options.extra_requirements = {"PyYAML": ">=6.0"}
    assert veny.wanted_packages(options) == [venv_cache.Wanted("pyyaml", ">=6.0")]


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


def _stub_successful_import_check(
    monkeypatch: pytest.MonkeyPatch, importable: set[str]
) -> None:
    """Make the import-level probe check_packages_in_venv runs report success for `importable` names.

    Only importlib.import_module and subprocess.run are faked; everything
    else -- venv_cache.satisfies, cache_candidates' cheap filters, and
    check_packages_in_venv's own alternative-building logic -- runs for
    real. Mirrors test_split_imports.py's _run_check_against_fake_venv.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
        importable:  Names that "import" successfully in the fake venv.
    """

    def fake_import_module(name: str) -> None:
        if name not in importable:
            raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    def fake_run(command, *args, **kwargs):
        source = command[-1]
        buf = io.StringIO()
        exit_code = 0
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(source, "<fake-venv-check>", "exec"), {})
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        return subprocess.CompletedProcess(
            command, exit_code, stdout=buf.getvalue(), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_check_venv_dir_accepts_a_manifest_match_whose_import_actually_imports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The floor this predicate exists for: a real match must be accepted.

    Nothing in the suite reached check_venv_dir's `return True` before this
    test -- every other check_venv_dir test here asserts False, so
    `def check_venv_dir(...): return False` silently disabled every venv
    reuse and still passed the whole suite. See
    test_find_match_dir_in_cache_returns_a_manifest_match below for the
    matching floor test on find_match_dir_in_cache.
    """
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    options = an_options({ResolvedImport("thing", "thing-pkg")})
    options.all_imports = {"thing"}
    monkeypatch.setattr(veny, "use_pip_list", lambda opts: None)
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"thing"})

    assert veny.check_venv_dir(options, venv_dir) is True


def test_find_match_dir_in_cache_returns_a_manifest_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """find_match_dir_in_cache had no test at all before this one.

    Builds a real cached venv folder with a manifest and drives the default
    ("latest") search path through cache_candidates and check_venv_dir for
    real, stubbing only the import-level probe (see
    _stub_successful_import_check).
    """
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    options = an_options({ResolvedImport("thing", "thing-pkg")})
    options.all_imports = {"thing"}
    options.my_dir = tmp_path
    options.venv_name = "myenv"
    options.args = argparse.Namespace(
        latest=True, oldest=False, last_used=False, smallest=False
    )
    monkeypatch.setattr(veny, "use_pip_list", lambda opts: None)
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"thing"})

    assert veny.find_match_dir_in_cache(options) == venv_dir


def test_find_match_dir_in_cache_tolerates_a_last_used_options_without_venv_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A last-used JSON restored as a bare emmykit.Options must be a cache miss, not an AttributeError.

    venv_dir is declared only in veny.Options.__init__, not in the
    emmykit.Options base class load_last_used_options builds from, so an
    options JSON written before that field existed (or otherwise missing
    the key) must not crash the run.
    """
    options = an_options({ResolvedImport("numpy", "numpy")})
    options.my_dir = tmp_path
    options.args = argparse.Namespace(
        latest=False, oldest=False, last_used=False, smallest=False
    )
    monkeypatch.setattr(veny, "load_last_used_options", lambda opts: ek.Options())

    assert veny.find_match_dir_in_cache(options) is None
