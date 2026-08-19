"""Tests for choosing cached virtual environments."""

import argparse
import contextlib
import importlib
import io
import subprocess
from pathlib import Path

import emmykit as ek
import pytest

from veny import alias_index, cache_search, stdlib_index, venv_cache, verify
from veny import cli as veny
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


def candidates(
    options: veny.Options, folders: list[Path]
) -> list[cache_search.CacheCandidate]:
    """cache_candidates wired the way find_match_dir_in_cache wires it.

    cache_candidates takes no Options any more: what this run needs and which
    interpreter it needs it for are explicit arguments. This keeps an_options
    above as the single description of the run under test.
    """
    return cache_search.cache_candidates(
        folders,
        wanted=cache_search.wanted_packages(
            options.uninstalled_imports, options.extra_requirements
        ),
        tag=cache_search.interpreter_tag(options.stdlib),
        rawlog=options.rawlog,
    )


def check(options: veny.Options, venv_dir: Path) -> bool:
    """check_venv_dir wired the way find_match_dir_in_cache wires it.

    source_names is computed once by main() now and passed down, rather than
    rebuilt inside check_venv_dir; this reproduces that one wiring.
    """
    return cache_search.check_venv_dir(
        venv_dir,
        wanted=cache_search.wanted_packages(
            options.uninstalled_imports, options.extra_requirements
        ),
        tag=cache_search.interpreter_tag(options.stdlib),
        uninstalled=options.uninstalled_imports,
        source_names=verify.source_import_names(
            options.all_imports,
            options.extra_requirements,
            getattr(options.args, "reqs", False),
        ),
        rawlog=options.rawlog,
    )


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
    assert [c.folder for c in candidates(options, [venv_dir])] == [venv_dir]


def test_a_venv_without_a_manifest_is_skipped(tmp_path: Path) -> None:
    """Pre-manifest venvs must be rebuilt, not matched on their names alone."""
    venv_dir = tmp_path / "myenv-py3.12-20260814-091500-numpy"
    venv_dir.mkdir()
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert candidates(options, [venv_dir]) == []


def test_a_venv_for_another_interpreter_is_skipped(tmp_path: Path) -> None:
    """Rejected by cache_candidates' interpreter-tag check; its manifest is never read at all."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.13-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
        tag="3.13",
    )
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert candidates(options, [venv_dir]) == []


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
    assert candidates(options, [venv_dir]) == []


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
    assert candidates(options, [venv_dir]) == []


def test_a_pin_is_checked_against_the_installed_version(tmp_path: Path) -> None:
    """Ignoring --reqs pins hands back a venv that violates them."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "1.0.0", ">=1.2")],
    )
    options = an_options({ResolvedImport("numpy", "numpy")})
    options.extra_requirements = {"numpy": ">=1.2"}
    assert candidates(options, [venv_dir]) == []
    options.extra_requirements = {"numpy": ">=0.9"}
    assert [c.folder for c in candidates(options, [venv_dir])] == [venv_dir]


def test_a_folder_that_loses_its_manifest_between_calls_is_dropped_not_raised(
    tmp_path: Path,
) -> None:
    """cache_candidates' own resilience to a vanished manifest, called twice directly.

    This pins cache_candidates in isolation: it must degrade, not crash, if a
    folder that matched on one call has lost its manifest by the next. It
    does NOT represent find_match_dir_in_cache's scan-then-check window any
    more: before ledger item 2 was closed, check_venv_dir re-read the
    manifest from disk, so this two-calls-to-cache_candidates shape was a
    fair proxy for "scan, then check" in production. Now that
    find_match_dir_in_cache passes the winning candidate's already-read
    manifest into check_venv_dir instead of letting it re-read, that window
    is a different mechanism -- see
    test_check_venv_dir_survives_the_manifest_vanishing_after_it_was_already_read
    for what actually happens there now.
    """
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert [c.folder for c in candidates(options, [venv_dir])] == [venv_dir]
    (venv_dir / venv_cache.MANIFEST_FILENAME).unlink()
    assert candidates(options, [venv_dir]) == []


def test_wanted_packages_carries_the_requested_specs() -> None:
    """A spec dropped here makes every pin invisible to matching."""
    options = an_options({ResolvedImport("numpy", "numpy")})
    options.extra_requirements = {"numpy": ">=1.2"}
    assert cache_search.wanted_packages(
        options.uninstalled_imports, options.extra_requirements
    ) == [venv_cache.Wanted("numpy", ">=1.2")]


def test_wanted_packages_finds_a_pin_keyed_by_a_different_spelling() -> None:
    """The record's pip_name and the user's --reqs spelling can differ in case or separators for one project."""
    options = an_options({ResolvedImport("yaml", "pyyaml")})
    options.extra_requirements = {"PyYAML": ">=6.0"}
    assert cache_search.wanted_packages(
        options.uninstalled_imports, options.extra_requirements
    ) == [venv_cache.Wanted("pyyaml", ">=6.0")]


def test_check_venv_dir_rejects_a_directory_with_no_manifest(tmp_path: Path) -> None:
    """The last-used pointer can outlive the venv it points at."""
    venv_dir = tmp_path / "myenv-py3.12-20260814-091500-numpy"
    venv_dir.mkdir()
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert check(options, venv_dir) is False


def test_check_venv_dir_rejects_a_missing_directory(tmp_path: Path) -> None:
    """A deleted venv must be a cache miss, not an exception."""
    options = an_options({ResolvedImport("numpy", "numpy")})
    assert check(options, tmp_path / "gone") is False


def test_check_venv_dir_rejects_a_manifest_that_does_not_match(tmp_path: Path) -> None:
    """Reusing a venv that lacks a package fails at the user's runtime."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    options = an_options({ResolvedImport("scipy", "scipy")})
    assert check(options, venv_dir) is False


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
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"thing"})

    assert check(options, venv_dir) is True


def test_check_venv_dir_checks_the_name_the_user_wrote_not_the_distributions_others(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """source_names must reach check_packages_in_venv, or the check goes fail-open.

    check_venv_dir hands verify.check_packages_in_venv both `uninstalled` and
    `source_names`. `source_names` has an empty default that is NOT a "work it
    out yourself" fallback: with it empty, the bulk branch stops requiring the
    name the user actually wrote and accepts any top-level name the
    distribution happens to install -- the setuptools/_distutils_hack
    fail-open its docstring warns about.

    Concrete bug this catches: drop `source_names=source_names` from
    check_venv_dir's call (leaving verify's empty default). Here the user
    wrote `import thing`, thing-pkg is installed but provides only `_hack`,
    and only `_hack` imports. Correctly wired, the venv is rejected because
    `thing` does not import. Mis-wired, `_hack` imports and the cached venv is
    handed back to a script that will die on its first import.
    """
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    options = an_options({ResolvedImport("thing", "thing-pkg")})
    options.all_imports = {"thing"}
    # thing-pkg installs a top-level `_hack`, not `thing`.
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"_hack": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"_hack"})

    assert check(options, venv_dir) is False


def _never_called() -> ek.Options | None:
    """A load_last_used the --latest path must never reach.

    --latest short-circuits the last-used pass, so consulting the previous
    run's JSON there would be a wiring bug: it would let a stale pointer win
    over the latest matching venv the user explicitly asked for.
    """
    raise AssertionError("load_last_used must not be called on the --latest path")


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
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"thing"})

    assert (
        cache_search.find_match_dir_in_cache(
            options.args,
            my_dir=options.my_dir,
            venv_name=options.venv_name,
            uninstalled=options.uninstalled_imports,
            extra_requirements=options.extra_requirements,
            source_names=verify.source_import_names(
                options.all_imports,
                options.extra_requirements,
                getattr(options.args, "reqs", False),
            ),
            tag=cache_search.interpreter_tag(options.stdlib),
            rawlog=options.rawlog,
            load_last_used=_never_called,
        )
        == venv_dir
    )


def test_find_match_dir_in_cache_tolerates_a_last_used_options_without_venv_dir(
    tmp_path: Path,
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

    assert (
        cache_search.find_match_dir_in_cache(
            options.args,
            my_dir=options.my_dir,
            venv_name=options.venv_name,
            uninstalled=options.uninstalled_imports,
            extra_requirements=options.extra_requirements,
            source_names=verify.source_import_names(
                options.all_imports,
                options.extra_requirements,
                getattr(options.args, "reqs", False),
            ),
            tag=cache_search.interpreter_tag(options.stdlib),
            rawlog=options.rawlog,
            load_last_used=lambda: ek.Options(),
        )
        is None
    )


def test_a_cache_hit_reads_and_matches_each_manifest_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The winning candidate's manifest is read from disk once AND satisfies-checked once.

    A bug that would make this fail: dropping the matched_manifest= argument
    at a selection branch in find_match_dir_in_cache, which restores both the
    second read_manifest call and the second satisfies call check_venv_dir
    used to make on the winning folder.

    Measured directly (not assumed) with counting spies around
    venv_cache.read_manifest and venv_cache.satisfies, driving
    find_match_dir_in_cache's default ("latest") path against a cache
    holding one matching folder:

    Before ledger item 2 was closed at all: 2 read_manifest calls, 2
    satisfies calls -- one pair from cache_candidates' scan, one pair from
    check_venv_dir re-reading and re-checking the same folder.

    After the read fix alone (this task's first pass, since corrected): 1
    read_manifest call, 2 satisfies calls -- check_venv_dir stopped
    re-reading the manifest but still called venv_cache.satisfies on it a
    second time, which a design review caught: satisfies() is a pure
    function of (manifest, wanted, tag), and find_match_dir_in_cache hands
    both calls the identical wanted/tag objects, so the second call could not
    possibly return a different answer than the first -- it was pure waste,
    and it was the specific duplication ledger item 2 is named after, not
    merely the disk read.

    After closing the item fully: 1 read_manifest call, 1 satisfies call.
    check_venv_dir's matched_manifest parameter now means what its name says:
    a manifest already checked against this same wanted/tag by
    venv_cache.satisfies, so check_venv_dir trusts that and skips its own
    satisfies call entirely, going straight to the import-level
    confirmation.
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
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"thing"})

    read_manifest_calls = 0
    satisfies_calls = 0
    orig_read_manifest = venv_cache.read_manifest
    orig_satisfies = venv_cache.satisfies

    def counting_read_manifest(venv_dir):
        nonlocal read_manifest_calls
        read_manifest_calls += 1
        return orig_read_manifest(venv_dir)

    def counting_satisfies(*args, **kwargs):
        nonlocal satisfies_calls
        satisfies_calls += 1
        return orig_satisfies(*args, **kwargs)

    monkeypatch.setattr(venv_cache, "read_manifest", counting_read_manifest)
    monkeypatch.setattr(venv_cache, "satisfies", counting_satisfies)

    result = cache_search.find_match_dir_in_cache(
        options.args,
        my_dir=options.my_dir,
        venv_name=options.venv_name,
        uninstalled=options.uninstalled_imports,
        extra_requirements=options.extra_requirements,
        source_names=verify.source_import_names(
            options.all_imports,
            options.extra_requirements,
            getattr(options.args, "reqs", False),
        ),
        tag=cache_search.interpreter_tag(options.stdlib),
        rawlog=options.rawlog,
        load_last_used=_never_called,
    )

    assert result == venv_dir
    assert read_manifest_calls == 1
    assert satisfies_calls == 1


def test_check_venv_dir_survives_the_manifest_vanishing_after_it_was_already_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Pins the lost-manifest window this task's change narrows.

    Before ledger item 2 was closed, check_venv_dir re-read the manifest
    from disk and re-ran satisfies on what it read, so a manifest deleted
    between cache_candidates' scan and check_venv_dir's own check was caught
    there: read_manifest returned None and the folder was rejected. Now that
    find_match_dir_in_cache hands check_venv_dir a matched_manifest --
    cache_candidates' own already-satisfies-checked manifest -- neither the
    read nor the satisfies call happens again, so the same disappearance is
    invisible to check_venv_dir: the folder is accepted on the strength of
    the caller's earlier check, provided the import-level check still
    passes. Only the whole directory vanishing (not just the manifest file
    inside it) is still caught, by check_venv_dir's is_dir check at the top.

    A bug that would make this fail: restoring the matched_manifest=None
    default at a call site (as in the read/satisfies-count test above) would
    make this venv rejected instead of accepted, since check_venv_dir would
    then try to read the now-missing manifest itself.
    """
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    options = an_options({ResolvedImport("thing", "thing-pkg")})
    options.all_imports = {"thing"}
    found = candidates(options, [venv_dir])
    assert [c.folder for c in found] == [venv_dir]
    manifest_already_matched = found[0].manifest

    (venv_dir / venv_cache.MANIFEST_FILENAME).unlink()

    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"thing"})

    assert (
        cache_search.check_venv_dir(
            venv_dir,
            wanted=cache_search.wanted_packages(
                options.uninstalled_imports, options.extra_requirements
            ),
            tag=cache_search.interpreter_tag(options.stdlib),
            uninstalled=options.uninstalled_imports,
            source_names=verify.source_import_names(
                options.all_imports,
                options.extra_requirements,
                getattr(options.args, "reqs", False),
            ),
            rawlog=options.rawlog,
            matched_manifest=manifest_already_matched,
        )
        is True
    )


def test_a_last_used_hit_still_reads_and_matches_its_own_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The satisfies skip must not leak into the last-used path.

    The last-used path has no CacheCandidate -- the folder comes from a
    previous run's options JSON, not from cache_candidates' scan -- so it has
    no manifest that has already passed venv_cache.satisfies. It must keep
    reading its own manifest and keep calling satisfies on it, exactly as
    before matched_manifest existed.

    A bug that would make this fail: find_match_dir_in_cache's last-used
    branch passing matched_manifest from somewhere (there is nothing correct
    it could pass), which would skip the match check entirely and hand back
    a venv never confirmed against what this run wants.
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
        latest=False, oldest=False, last_used=True, smallest=False
    )
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"thing"})

    read_manifest_calls = 0
    satisfies_calls = 0
    orig_read_manifest = venv_cache.read_manifest
    orig_satisfies = venv_cache.satisfies

    def counting_read_manifest(venv_dir):
        nonlocal read_manifest_calls
        read_manifest_calls += 1
        return orig_read_manifest(venv_dir)

    def counting_satisfies(*args, **kwargs):
        nonlocal satisfies_calls
        satisfies_calls += 1
        return orig_satisfies(*args, **kwargs)

    monkeypatch.setattr(venv_cache, "read_manifest", counting_read_manifest)
    monkeypatch.setattr(venv_cache, "satisfies", counting_satisfies)

    last_used_options = ek.Options()
    last_used_options.venv_dir = venv_dir  # type: ignore[attr-defined]

    result = cache_search.find_match_dir_in_cache(
        options.args,
        my_dir=options.my_dir,
        venv_name=options.venv_name,
        uninstalled=options.uninstalled_imports,
        extra_requirements=options.extra_requirements,
        source_names=verify.source_import_names(
            options.all_imports,
            options.extra_requirements,
            getattr(options.args, "reqs", False),
        ),
        tag=cache_search.interpreter_tag(options.stdlib),
        rawlog=options.rawlog,
        load_last_used=lambda: last_used_options,
    )

    assert result == venv_dir
    assert read_manifest_calls == 1
    assert satisfies_calls == 1
