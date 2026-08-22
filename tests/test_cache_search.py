"""Tests for choosing cached virtual environments."""

import argparse
import contextlib
import dataclasses
import importlib
import io
import logging
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from veny import (
    alias_index,
    cache_search,
    environment,
    state,
    stdlib_index,
    venv_cache,
    verify,
)
from veny.alias_index import ResolvedImport

from .test_state_values import a_requirements as _a_requirements


def a_stdlib() -> stdlib_index.StdlibIndex:
    """Build the StdlibIndex the cache search still reads.

    Phase 4a moved uninstalled_imports, all_imports and extra_requirements
    onto Requirements; a_reqs below builds the matching value. Only the
    stdlib index is a bag of its own here.
    """
    return stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )


def a_reqs(records: set[ResolvedImport], **overrides: object) -> state.Requirements:
    """The Requirements matching a_stdlib's run description.

    Args:
        records: What the run still has to install.
        **overrides: Field values to replace, e.g. extra_requirements.

    Returns:
        The Requirements the cache search reads.
    """
    return _a_requirements(uninstalled=frozenset(records), **overrides)


def candidates(
    stdlib: stdlib_index.StdlibIndex,
    requirements: state.Requirements,
    folders: list[Path],
) -> list[cache_search.CacheCandidate]:
    """cache_candidates wired the way find_match_dir_in_cache wires it.

    cache_candidates takes no Options any more: what this run needs and which
    interpreter it needs it for are explicit arguments. This keeps a_stdlib
    above as the single description of the run under test.
    """
    return cache_search.cache_candidates(
        folders,
        wanted=cache_search.wanted_packages(
            set(requirements.uninstalled), requirements.extra_requirements
        ),
        tag=cache_search.interpreter_tag(stdlib),
        rawlog=True,
    )


def check(
    stdlib: stdlib_index.StdlibIndex,
    requirements: state.Requirements,
    venv_dir: Path,
) -> bool:
    """check_venv_dir wired the way find_match_dir_in_cache wires it.

    source_names is computed once by main() now and passed down, rather than
    rebuilt inside check_venv_dir; this reproduces that one wiring. No caller
    here ever sets --reqs, so the getattr(args, "reqs", False) this used to
    read off an Options is always False -- inlined rather than threaded
    through as a never-set parameter.
    """
    return cache_search.check_venv_dir(
        venv_dir,
        wanted=cache_search.wanted_packages(
            set(requirements.uninstalled), requirements.extra_requirements
        ),
        tag=cache_search.interpreter_tag(stdlib),
        uninstalled=set(requirements.uninstalled),
        source_names=verify.source_import_names(
            set(requirements.all_imports),
            requirements.extra_requirements,
            False,
        ),
        rawlog=True,
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
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("ruamel.yaml", "ruamel-yaml")})
    assert [c.folder for c in candidates(stdlib, requirements, [venv_dir])] == [
        venv_dir
    ]


def test_a_venv_without_a_manifest_is_skipped(tmp_path: Path) -> None:
    """Pre-manifest venvs must be rebuilt, not matched on their names alone."""
    venv_dir = tmp_path / "myenv-py3.12-20260814-091500-numpy"
    venv_dir.mkdir()
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("numpy", "numpy")})
    assert candidates(stdlib, requirements, [venv_dir]) == []


def test_a_venv_for_another_interpreter_is_skipped(tmp_path: Path) -> None:
    """Rejected by cache_candidates' interpreter-tag check; its manifest is never read at all."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.13-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
        tag="3.13",
    )
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("numpy", "numpy")})
    assert candidates(stdlib, requirements, [venv_dir]) == []


def test_a_venv_missing_a_package_is_skipped(tmp_path: Path) -> None:
    """Rejected by name_allows before satisfies() is ever called: the name has no room for scipy."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    wanted = {ResolvedImport("numpy", "numpy"), ResolvedImport("scipy", "scipy")}
    stdlib = a_stdlib()
    requirements = a_reqs(wanted)

    assert candidates(stdlib, requirements, [venv_dir]) == []


def test_a_venv_whose_name_allows_it_but_manifest_disagrees_is_skipped(
    tmp_path: Path,
) -> None:
    """The folder name is a prefilter only: it can list a package the manifest never actually recorded."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy_scipy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    wanted = {ResolvedImport("numpy", "numpy"), ResolvedImport("scipy", "scipy")}
    stdlib = a_stdlib()
    requirements = a_reqs(wanted)

    assert candidates(stdlib, requirements, [venv_dir]) == []


def test_a_pin_is_checked_against_the_installed_version(tmp_path: Path) -> None:
    """Ignoring --reqs pins hands back a venv that violates them."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "1.0.0", ">=1.2")],
    )
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("numpy", "numpy")})
    requirements = dataclasses.replace(
        requirements, extra_requirements={"numpy": ">=1.2"}
    )
    assert candidates(stdlib, requirements, [venv_dir]) == []
    requirements = dataclasses.replace(
        requirements, extra_requirements={"numpy": ">=0.9"}
    )
    assert [c.folder for c in candidates(stdlib, requirements, [venv_dir])] == [
        venv_dir
    ]


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
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("numpy", "numpy")})
    assert [c.folder for c in candidates(stdlib, requirements, [venv_dir])] == [
        venv_dir
    ]
    (venv_dir / venv_cache.MANIFEST_FILENAME).unlink()
    assert candidates(stdlib, requirements, [venv_dir]) == []


def test_wanted_packages_carries_the_requested_specs() -> None:
    """A spec dropped here makes every pin invisible to matching."""
    requirements = a_reqs(
        {ResolvedImport("numpy", "numpy")}, extra_requirements={"numpy": ">=1.2"}
    )
    assert cache_search.wanted_packages(
        set(requirements.uninstalled), requirements.extra_requirements
    ) == [venv_cache.Wanted("numpy", ">=1.2")]


def test_wanted_packages_finds_a_pin_keyed_by_a_different_spelling() -> None:
    """The record's pip_name and the user's --reqs spelling can differ in case or separators for one project."""
    requirements = a_reqs(
        {ResolvedImport("yaml", "pyyaml")}, extra_requirements={"PyYAML": ">=6.0"}
    )
    assert cache_search.wanted_packages(
        set(requirements.uninstalled), requirements.extra_requirements
    ) == [venv_cache.Wanted("pyyaml", ">=6.0")]


def test_check_venv_dir_rejects_a_directory_with_no_manifest(tmp_path: Path) -> None:
    """The last-used pointer can outlive the venv it points at."""
    venv_dir = tmp_path / "myenv-py3.12-20260814-091500-numpy"
    venv_dir.mkdir()
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("numpy", "numpy")})
    assert check(stdlib, requirements, venv_dir) is False


def test_check_venv_dir_rejects_a_missing_directory(tmp_path: Path) -> None:
    """A deleted venv must be a cache miss, not an exception."""
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("numpy", "numpy")})
    assert check(stdlib, requirements, tmp_path / "gone") is False


def test_check_venv_dir_rejects_a_manifest_that_does_not_match(tmp_path: Path) -> None:
    """Reusing a venv that lacks a package fails at the user's runtime."""
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-numpy",
        [venv_cache.PackageRecord("numpy", "numpy", "2.1.3", None)],
    )
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("scipy", "scipy")})
    assert check(stdlib, requirements, venv_dir) is False


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
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("thing", "thing-pkg")})
    requirements = dataclasses.replace(requirements, all_imports=frozenset({"thing"}))
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"thing"})

    assert check(stdlib, requirements, venv_dir) is True


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
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("thing", "thing-pkg")})
    requirements = dataclasses.replace(requirements, all_imports=frozenset({"thing"}))
    # thing-pkg installs a top-level `_hack`, not `thing`.
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"_hack": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"_hack"})

    assert check(stdlib, requirements, venv_dir) is False


def _never_called() -> state.LastUsed | None:
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
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("thing", "thing-pkg")})
    requirements = dataclasses.replace(requirements, all_imports=frozenset({"thing"}))
    args = argparse.Namespace(
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
            args,
            my_dir=tmp_path,
            venv_name="myenv",
            uninstalled=set(requirements.uninstalled),
            extra_requirements=requirements.extra_requirements,
            source_names=verify.source_import_names(
                set(requirements.all_imports),
                requirements.extra_requirements,
                getattr(args, "reqs", False),
            ),
            tag=cache_search.interpreter_tag(stdlib),
            rawlog=True,
            load_last_used=_never_called,
        )
        == venv_dir
    )


def test_find_match_dir_in_cache_treats_no_record_at_all_as_a_cache_miss(
    tmp_path: Path,
) -> None:
    """A run with no readable last-used record must be a miss, not a crash.

    This replaces the "a bare emmykit.Options has no venv_dir" tolerance
    test: the reader now hands back a state.LastUsed, whose venv_dir always
    exists, or None. None is the one degraded input left -- no record, an
    unreadable one, or one naming no environment, all of which last_used.load
    turns into None -- and the last-used pass must fall through it to the
    ordinary scan rather than raising on the missing attribute.
    """
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("numpy", "numpy")})
    args = argparse.Namespace(
        latest=False, oldest=False, last_used=False, smallest=False
    )

    assert (
        cache_search.find_match_dir_in_cache(
            args,
            my_dir=tmp_path,
            venv_name="myenv",
            uninstalled=set(requirements.uninstalled),
            extra_requirements=requirements.extra_requirements,
            source_names=verify.source_import_names(
                set(requirements.all_imports),
                requirements.extra_requirements,
                getattr(args, "reqs", False),
            ),
            tag=cache_search.interpreter_tag(stdlib),
            rawlog=False,
            load_last_used=lambda: None,
        )
        is None
    )


def _a_satisfying_venv(
    monkeypatch: pytest.MonkeyPatch, root: Path, timestamp: str
) -> Path:
    """One cached venv folder the run under test can legitimately reuse.

    Args:
        monkeypatch: pytest's monkeypatch fixture, for the interpreter probe
                     and the import-level check the selection runs for real.
        root:        The cache directory the folder is created in.
        timestamp:   The "YYYYmmdd-HHMMSS" stamp in the folder's name, which
                     is what latest_venv orders on.

    Returns:
        The folder created.
    """
    venv_dir = a_cached_venv(
        root,
        f"myenv-py3.12-{timestamp}-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    _stub_successful_import_check(monkeypatch, importable={"thing"})
    return venv_dir


def _search(
    args: argparse.Namespace,
    *,
    my_dir: Path,
    load_last_used: Callable[[], state.LastUsed | None],
) -> Path | None:
    """find_match_dir_in_cache wired for the one-package run the tests build.

    Args:
        args:           The parsed command line the selection reads its flags
                        off.
        my_dir:         The cache directory to search.
        load_last_used: The injected reader of the previous run's record.

    Returns:
        Whatever the search selected, or None.
    """
    stdlib = a_stdlib()
    requirements = dataclasses.replace(
        a_reqs({ResolvedImport("thing", "thing-pkg")}),
        all_imports=frozenset({"thing"}),
    )
    return cache_search.find_match_dir_in_cache(
        args,
        my_dir=my_dir,
        venv_name="myenv",
        uninstalled=set(requirements.uninstalled),
        extra_requirements=requirements.extra_requirements,
        source_names=verify.source_import_names(
            set(requirements.all_imports),
            requirements.extra_requirements,
            False,
        ),
        tag=cache_search.interpreter_tag(stdlib),
        rawlog=True,
        load_last_used=load_last_used,
    )


def test_the_last_used_pointer_selects_the_recorded_venv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A run with no selection flags reuses the venv the record names.

    Bug caught: reading the pointer off the wrong field, or dropping the
    last-used pass entirely -- both leave the run rebuilding an environment
    it already had, which is invisible to a test that only asserts "some
    venv was chosen". Here the recorded folder is the *older* of the two in
    the cache, so a search that skipped the pointer and went straight to
    "latest" returns the other one.
    """
    folder = _a_satisfying_venv(monkeypatch, tmp_path, "20260101-010101")
    newer = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    record = state.LastUsed(folder, folder / "bin" / "python", "20260202-020202")

    chosen = _search(
        argparse.Namespace(), my_dir=tmp_path, load_last_used=lambda: record
    )

    assert chosen == folder
    assert chosen != newer


def test_a_stale_pointer_falls_through_to_the_latest_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A record naming a venv that is gone must not end the search.

    Bug caught: returning None (rebuild) instead of falling through when the
    recorded venv no longer satisfies the run -- the behaviour the old
    `args.latest = True` write implemented. The cache still holds a venv this
    run can use, and rebuilding it would be a silent waste of a whole install.
    """
    newest_satisfying_folder = _a_satisfying_venv(
        monkeypatch, tmp_path, "20260814-091500"
    )
    a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260101-010101-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    record = state.LastUsed(
        tmp_path / "gone", tmp_path / "gone" / "python", "20260101-010101"
    )

    chosen = _search(
        argparse.Namespace(), my_dir=tmp_path, load_last_used=lambda: record
    )

    assert chosen == newest_satisfying_folder


def test_the_cache_search_does_not_write_to_the_command_line(tmp_path: Path) -> None:
    """The selection resolves its own defaults in locals, not on args.

    Bug caught: leaving the in-place flag writes in place. They were only
    ever writes because they reached disk through save_options_to_json;
    with that gone, a mutated Namespace is a shared-state surprise for
    every later reader of args.
    """
    args = argparse.Namespace(
        latest=False, oldest=False, last_used=False, smallest=False
    )
    before = vars(args).copy()

    assert _search(args, my_dir=tmp_path, load_last_used=lambda: None) is None

    assert vars(args) == before


def test_asking_for_both_the_latest_and_the_last_used_venv_selects_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--latest --last-used is the "invalid combination" branch, and stays it.

    Behaviour under test: the one flag combination the selection refuses to
    act on. --latest suppresses the last-used pass, and the four selection
    branches below each require the other three flags to be clear, so nothing
    matches and the run rebuilds from scratch after logging the combination.

    Bug caught: collapsing the two flag reads into a single local during the
    de-mutation of this function -- `try_last_used and not prefer_latest`
    reads as False here, which would quietly turn this combination into a
    plain --latest run and hand back a cached venv where veny used to build a
    new one. Not covered by the four single-flag paths, all of which are
    unaffected by the difference.
    """
    _a_satisfying_venv(monkeypatch, tmp_path, "20260814-091500")
    args = argparse.Namespace(latest=True, oldest=False, last_used=True, smallest=False)

    assert _search(args, my_dir=tmp_path, load_last_used=lambda: None) is None


def test_a_cache_hit_reads_and_matches_each_manifest_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The winning candidate's manifest is read from disk once AND satisfies-checked once.

    A bug that would make this fail: dropping the candidate= argument at a
    selection branch in find_match_dir_in_cache, which restores both the
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
    check_venv_dir's `candidate` parameter carries that trust in its type: a
    CacheCandidate can only be built by cache_candidates, which has already
    put its manifest through venv_cache.satisfies against this same
    wanted/tag, so check_venv_dir skips its own satisfies call entirely and
    goes straight to the import-level confirmation.
    """
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("thing", "thing-pkg")})
    requirements = dataclasses.replace(requirements, all_imports=frozenset({"thing"}))
    args = argparse.Namespace(
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
        args,
        my_dir=tmp_path,
        venv_name="myenv",
        uninstalled=set(requirements.uninstalled),
        extra_requirements=requirements.extra_requirements,
        source_names=verify.source_import_names(
            set(requirements.all_imports),
            requirements.extra_requirements,
            getattr(args, "reqs", False),
        ),
        tag=cache_search.interpreter_tag(stdlib),
        rawlog=True,
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
    find_match_dir_in_cache hands check_venv_dir the CacheCandidate itself --
    cache_candidates' own already-satisfies-checked manifest, paired with the
    folder it was read from -- neither the read nor the satisfies call
    happens again, so the same disappearance is invisible to check_venv_dir:
    the folder is accepted on the strength of the caller's earlier check,
    provided the import-level check still passes. Only the whole directory
    vanishing (not just the manifest file inside it) is still caught, by
    check_venv_dir's is_dir check at the top.

    A bug that would make this fail: restoring the candidate=None default at
    a call site (as in the read/satisfies-count test above) would make this
    venv rejected instead of accepted, since check_venv_dir would then try to
    read the now-missing manifest itself.
    """
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("thing", "thing-pkg")})
    requirements = dataclasses.replace(requirements, all_imports=frozenset({"thing"}))
    found = candidates(stdlib, requirements, [venv_dir])
    assert [c.folder for c in found] == [venv_dir]
    already_matched = found[0]

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
                set(requirements.uninstalled), requirements.extra_requirements
            ),
            tag=cache_search.interpreter_tag(stdlib),
            uninstalled=set(requirements.uninstalled),
            source_names=verify.source_import_names(
                set(requirements.all_imports),
                requirements.extra_requirements,
                False,
            ),
            rawlog=False,
            candidate=already_matched,
        )
        is True
    )


def test_check_venv_dir_refuses_a_candidate_that_describes_another_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The candidate's match is evidence about its own folder and no other.

    `candidate` is what lets check_venv_dir skip venv_cache.satisfies
    entirely: a CacheCandidate can only come from cache_candidates, which has
    already matched that folder's manifest against this same wanted/tag. The
    one way that guarantee can still be wrong is a caller handing over a
    candidate for a different folder -- and then the venv actually being
    checked is accepted on evidence gathered about someone else, with only
    the folder-name prefilter standing between the run and a venv that does
    not hold what it needs.

    Concrete bug this catches: phase 3e's move of the cache decision into
    pipeline.py rewiring a branch as
    `check_venv_dir(chosen, candidate=candidates[0])` -- correct whenever the
    first candidate happens to win, silently wrong the moment it does not.
    Here `other_dir`'s manifest records only other-pkg while this run needs
    thing-pkg, and the import-level probe is stubbed to succeed, so without
    the folder check this call returns True and hands back a venv missing
    the package the script imports.
    """
    wanted_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    other_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091501-other-pkg",
        [venv_cache.PackageRecord("other", "other-pkg", "1.0.0", None)],
    )
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("thing", "thing-pkg")})
    requirements = dataclasses.replace(requirements, all_imports=frozenset({"thing"}))
    found = candidates(stdlib, requirements, [wanted_dir])
    assert [c.folder for c in found] == [wanted_dir]

    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: True)

    with pytest.raises(ValueError) as excinfo:
        cache_search.check_venv_dir(
            other_dir,
            wanted=cache_search.wanted_packages(
                set(requirements.uninstalled), requirements.extra_requirements
            ),
            tag=cache_search.interpreter_tag(stdlib),
            uninstalled=set(requirements.uninstalled),
            source_names={"thing"},
            rawlog=False,
            candidate=found[0],
        )

    message = str(excinfo.value)
    assert os.fspath(wanted_dir) in message
    assert os.fspath(other_dir) in message

    # The control: the very same candidate against its own folder is fine, so
    # what the check rejects is the mismatch and not the candidate itself.
    assert (
        cache_search.check_venv_dir(
            wanted_dir,
            wanted=cache_search.wanted_packages(
                set(requirements.uninstalled), requirements.extra_requirements
            ),
            tag=cache_search.interpreter_tag(stdlib),
            uninstalled=set(requirements.uninstalled),
            source_names={"thing"},
            rawlog=False,
            candidate=found[0],
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
    before the candidate parameter existed.

    A bug that would make this fail: find_match_dir_in_cache's last-used
    branch passing a candidate from somewhere (there is nothing correct it
    could pass), which would skip the match check entirely and hand back a
    venv never confirmed against what this run wants.
    """
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("thing", "thing-pkg")})
    requirements = dataclasses.replace(requirements, all_imports=frozenset({"thing"}))
    args = argparse.Namespace(
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

    last_used_record = state.LastUsed(
        venv_dir, venv_dir / "bin" / "python", "20260202-020202"
    )

    result = cache_search.find_match_dir_in_cache(
        args,
        my_dir=tmp_path,
        venv_name="myenv",
        uninstalled=set(requirements.uninstalled),
        extra_requirements=requirements.extra_requirements,
        source_names=verify.source_import_names(
            set(requirements.all_imports),
            requirements.extra_requirements,
            getattr(args, "reqs", False),
        ),
        tag=cache_search.interpreter_tag(stdlib),
        rawlog=True,
        load_last_used=lambda: last_used_record,
    )

    assert result == venv_dir
    assert read_manifest_calls == 1
    assert satisfies_calls == 1


def _a_run_with_a_pinned_package(
    tmp_path: Path,
) -> tuple[stdlib_index.StdlibIndex, state.Requirements, Path]:
    """Build a run whose four check_venv_dir arguments are all distinguishable.

    Every value the call site has to wire is given a different shape, so a
    swap between two of them cannot pass: `uninstalled` holds records,
    `wanted` holds a Wanted carrying the --reqs spec (which only
    extra_requirements can supply), `source_names` holds an import name that
    is in neither, and `tag` is the run's own interpreter tag.

    Returns:
        The StdlibIndex, the Requirements and the cached venv directory.
    """
    folder_name = venv_cache.build_folder_name(
        venv_name="myenv",
        interpreter_tag="3.12",
        timestamp="20260814-091500",
        pip_names=["thing-pkg"],
    )
    venv_dir = a_cached_venv(
        tmp_path,
        folder_name,
        [venv_cache.PackageRecord("thing", "thing-pkg", "2.5.0", None)],
    )
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("thing", "thing-pkg")})
    requirements = dataclasses.replace(
        requirements, all_imports=frozenset({"thing", "other"})
    )
    requirements = dataclasses.replace(
        requirements, extra_requirements={"thing-pkg": ">=2.0"}
    )
    return stdlib, requirements, venv_dir


@pytest.mark.parametrize(
    ("flags", "candidate_is_handed_over"),
    [
        (
            {"latest": False, "oldest": False, "last_used": True, "smallest": False},
            False,
        ),
        (
            {"latest": True, "oldest": False, "last_used": False, "smallest": False},
            True,
        ),
        (
            {"latest": False, "oldest": True, "last_used": False, "smallest": False},
            True,
        ),
        (
            {"latest": False, "oldest": False, "last_used": False, "smallest": True},
            True,
        ),
    ],
    ids=["last_used", "latest", "oldest", "smallest"],
)
def test_every_branch_hands_check_venv_dir_the_same_description_of_the_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    flags: dict[str, bool],
    candidate_is_handed_over: bool,
) -> None:
    """All four selection branches must describe the run to check_venv_dir identically.

    find_match_dir_in_cache calls check_venv_dir from four separate places,
    each repeating the same six-argument wiring by hand. Nothing before this
    test read those arguments: measured by substitution, `wanted=[]`,
    `tag=""`, `uninstalled=frozenset()`, `source_names=frozenset()` and
    `rawlog=False` could each be written at any of the four sites and all 338
    tests stayed green. Concrete bug this catches: `wanted=[]` on the --oldest
    branch accepts any cached venv whose folder name and interpreter tag look
    right, no matter which packages its manifest actually records, so
    --oldest silently reuses an environment missing the package the script
    imports; `source_names=frozenset()` widens the import check to the
    distribution's whole top-level list, which is the fail-open shape
    PROGRESS records for the bulk check.

    The expected values are derived from the run's own inputs (the same
    wanted_packages/source_import_names calls main() makes), not read back
    off the production call.

    A spy proves the wiring but not that the wiring does anything, so the test
    then puts the REAL check_venv_dir back and drives the same branch against
    a cached venv whose folder name advertises thing-pkg while its manifest
    records only other-pkg. Every branch must reject it. That is the case the
    cheap folder-name prefilter cannot catch, so it is the one that proves
    `wanted` and `tag` are actually consulted rather than merely passed.
    """
    stdlib, requirements, venv_dir = _a_run_with_a_pinned_package(tmp_path)
    args = argparse.Namespace(**flags)
    calls: list[dict[str, object]] = []

    def spy(venv_dir_arg, **kwargs):
        calls.append({"venv_dir": venv_dir_arg, **kwargs})
        return True

    real_check_venv_dir = cache_search.check_venv_dir
    monkeypatch.setattr(cache_search, "check_venv_dir", spy)
    last_used_record = state.LastUsed(
        venv_dir, venv_dir / "bin" / "python", "20260202-020202"
    )

    result = cache_search.find_match_dir_in_cache(
        args,
        my_dir=tmp_path,
        venv_name="myenv",
        uninstalled=set(requirements.uninstalled),
        extra_requirements=requirements.extra_requirements,
        source_names=verify.source_import_names(
            set(requirements.all_imports),
            requirements.extra_requirements,
            getattr(args, "reqs", False),
        ),
        tag=cache_search.interpreter_tag(stdlib),
        rawlog=True,
        load_last_used=lambda: last_used_record,
    )

    assert result == venv_dir
    assert len(calls) == 1
    call = calls[0]
    assert call["venv_dir"] == venv_dir
    assert call["wanted"] == [venv_cache.Wanted(pip_name="thing-pkg", spec=">=2.0")]
    assert call["tag"] == "3.12"
    assert call["uninstalled"] == {ResolvedImport("thing", "thing-pkg")}
    assert call["source_names"] == {"thing", "other"}
    assert call["rawlog"] is True
    if candidate_is_handed_over:
        handed_over = call["candidate"]
        assert isinstance(handed_over, cache_search.CacheCandidate)
        assert handed_over.folder == venv_dir
        assert handed_over.manifest == venv_cache.read_manifest(venv_dir)
    else:
        assert call.get("candidate") is None

    # Second phase, with the REAL check_venv_dir: the arguments above are only
    # worth pinning if this branch actually rejects on them. The cache here
    # holds one folder whose name advertises thing-pkg and whose manifest does
    # not have it -- the one shape the folder-name prefilter cannot catch. Every
    # branch must come back empty-handed. No import-level probe is stubbed
    # because none is reached: venv_cache.satisfies rejects the candidate
    # first, which is the point.
    monkeypatch.setattr(cache_search, "check_venv_dir", real_check_venv_dir)
    liar_dir = tmp_path / "liar"
    liar_dir.mkdir()
    liar = a_cached_venv(
        liar_dir,
        venv_cache.build_folder_name(
            venv_name="myenv",
            interpreter_tag="3.12",
            timestamp="20260814-091500",
            pip_names=["thing-pkg"],
        ),
        [venv_cache.PackageRecord("other", "other-pkg", "1.0.0", None)],
    )
    liar_last_used = state.LastUsed(liar, liar / "bin" / "python", "20260202-020202")
    args = argparse.Namespace(**flags)

    assert (
        cache_search.find_match_dir_in_cache(
            args,
            my_dir=liar_dir,
            venv_name="myenv",
            uninstalled=set(requirements.uninstalled),
            extra_requirements=requirements.extra_requirements,
            source_names=verify.source_import_names(
                set(requirements.all_imports),
                requirements.extra_requirements,
                getattr(args, "reqs", False),
            ),
            tag=cache_search.interpreter_tag(stdlib),
            rawlog=False,
            load_last_used=lambda: liar_last_used,
        )
        is None
    ), "a venv whose manifest lacks the package must never be reused"


def test_the_cache_search_lets_cache_candidates_explain_a_rejected_folder(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """cache_candidates gets this run's rawlog, and it is the only voice on a rejection.

    Measured 2026-08-19 across all 17 `rawlog=` sites in
    cli/cache_search/last_used/verify: substituting the wrong-but-type-correct
    `True` -- a value the STANDING CHECK's own stated method covers -- left 16
    of them with the whole suite green, this one included. The existing pins
    all substitute the class default `False`, which the spy tests catch and a
    silenced run does not.

    Concrete bug this catches: `rawlog=True` at the cache_candidates call
    site. Every "Skipping the cached venv X because Y" line disappears from a
    normal run, so the one explanation veny offers for rebuilding an
    environment the user can see sitting in ~/veny -- a missing package, a
    pin that no longer holds -- is never printed, and the rebuild looks
    arbitrary.
    """
    # The folder name advertises thing-pkg; the manifest records only
    # other-pkg. That is the one shape the cheap name prefilter cannot reject,
    # so venv_cache.satisfies rejects it and cache_candidates says why.
    venv_dir = a_cached_venv(
        tmp_path,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("other", "other-pkg", "1.0.0", None)],
    )
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("thing", "thing-pkg")})
    requirements = dataclasses.replace(requirements, all_imports=frozenset({"thing"}))

    def run(rawlog: bool) -> Path | None:
        return cache_search.find_match_dir_in_cache(
            argparse.Namespace(
                latest=True, oldest=False, last_used=False, smallest=False
            ),
            my_dir=tmp_path,
            venv_name="myenv",
            uninstalled=set(requirements.uninstalled),
            extra_requirements=requirements.extra_requirements,
            source_names={"thing"},
            tag=cache_search.interpreter_tag(stdlib),
            rawlog=rawlog,
            load_last_used=_never_called,
        )

    with caplog.at_level(logging.INFO):
        assert run(False) is None

    assert f"Skipping the cached venv {os.fspath(venv_dir)} because" in caplog.text

    # And the other direction: a run that asked for raw logging must stay
    # quiet, so a hardcoded `rawlog=False` at that call site is caught too.
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert run(True) is None

    assert "Skipping the cached venv" not in caplog.text


@pytest.mark.parametrize(
    "flags",
    [
        {"latest": False, "oldest": False, "last_used": True, "smallest": False},
        {"latest": True, "oldest": False, "last_used": False, "smallest": False},
        {"latest": False, "oldest": True, "last_used": False, "smallest": False},
        {"latest": False, "oldest": False, "last_used": False, "smallest": True},
    ],
    ids=["last_used", "latest", "oldest", "smallest"],
)
def test_every_branch_lets_check_venv_dir_report_a_venv_that_vanished(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    flags: dict[str, bool],
) -> None:
    """All four branches pass their own rawlog to check_venv_dir, and it must be the run's.

    Measured 2026-08-19: `rawlog=True` substituted at any of the four
    check_venv_dir call sites left all 360 tests green. The four-branch
    argument test above pins `rawlog` only against the class default `False`,
    by reading it off a spy -- with `True` hardcoded the spy sees the very
    value it asserts.

    The venv is deleted after cache_candidates has already returned a
    CacheCandidate for it, which is the real window: the scan reads a folder,
    the selection then checks it, and anything can happen in between. The
    last-used branch reaches the same code from a recorded pointer, so it
    needs no such stub.

    Concrete bug this catches: a run whose cached venv was deleted (a manual
    clean-up, another veny run's --blank-slate) silently rebuilds from
    scratch with no line saying the environment it meant to reuse is gone.
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    venv_dir = a_cached_venv(
        cache_dir,
        "myenv-py3.12-20260814-091500-thing-pkg",
        [venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None)],
    )
    stdlib = a_stdlib()
    requirements = a_reqs({ResolvedImport("thing", "thing-pkg")})
    requirements = dataclasses.replace(requirements, all_imports=frozenset({"thing"}))
    already_found = candidates(stdlib, requirements, [venv_dir])
    assert [c.folder for c in already_found] == [venv_dir]

    shutil.rmtree(venv_dir)
    if not flags["last_used"]:
        monkeypatch.setattr(
            cache_search, "cache_candidates", lambda *a, **k: already_found
        )
    last_used_record = state.LastUsed(
        venv_dir, venv_dir / "bin" / "python", "20260202-020202"
    )

    def run(rawlog: bool) -> Path | None:
        return cache_search.find_match_dir_in_cache(
            argparse.Namespace(**flags),
            my_dir=cache_dir,
            venv_name="myenv",
            uninstalled=set(requirements.uninstalled),
            extra_requirements=requirements.extra_requirements,
            source_names={"thing"},
            tag=cache_search.interpreter_tag(stdlib),
            rawlog=rawlog,
            load_last_used=lambda: last_used_record,
        )

    with caplog.at_level(logging.INFO):
        assert run(False) is None

    assert (
        f"The cached venv directory {os.fspath(venv_dir)} is no longer there."
        in caplog.text
    )

    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert run(True) is None

    assert "is no longer there" not in caplog.text


def test_the_cache_search_filters_the_folders_against_this_run_not_a_blank_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """cache_candidates must be given this run's wanted list and log setting.

    Measured by substitution: `wanted=[]` at that call site left all 338
    tests green, and it is the argument that decides whether a cached venv's
    manifest is compared against what the script needs at all -- with an
    empty list venv_cache.satisfies has nothing to reject, so every
    name-and-tag-shaped folder in ~/veny becomes a candidate and the first
    one wins.
    """
    stdlib, requirements, venv_dir = _a_run_with_a_pinned_package(tmp_path)
    args = argparse.Namespace(
        latest=True, oldest=False, last_used=False, smallest=False
    )
    seen: list[dict[str, object]] = []

    def spy(folders, **kwargs):
        seen.append({"folders": list(folders), **kwargs})
        return []

    monkeypatch.setattr(cache_search, "cache_candidates", spy)

    assert (
        cache_search.find_match_dir_in_cache(
            args,
            my_dir=tmp_path,
            venv_name="myenv",
            uninstalled=set(requirements.uninstalled),
            extra_requirements=requirements.extra_requirements,
            source_names=verify.source_import_names(
                set(requirements.all_imports),
                requirements.extra_requirements,
                getattr(args, "reqs", False),
            ),
            tag=cache_search.interpreter_tag(stdlib),
            rawlog=True,
            load_last_used=_never_called,
        )
        is None
    )

    assert seen == [
        {
            "folders": [venv_dir],
            "wanted": [venv_cache.Wanted(pip_name="thing-pkg", spec=">=2.0")],
            "tag": "3.12",
            "rawlog": True,
        }
    ]


def test_check_venv_dir_probes_the_interpreter_inside_the_venv_it_was_given(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The import check must run against the candidate venv, not some other interpreter.

    check_venv_dir's own decision is made from `venv_dir`, but the import
    confirmation it then runs takes a *python path*, built by
    environment.venv_python_for at that call site. Measured by substitution:
    hardcoding any other interpreter path there left all 338 tests green,
    because every test that reaches this line stubs the probe and never looks
    at which interpreter it was asked about. Concrete bug this catches: the
    candidate is accepted on evidence gathered from the interpreter running
    veny (or from a previous candidate), so a venv missing the package is
    reused whenever veny's own environment happens to provide it.
    """
    _, requirements, venv_dir = _a_run_with_a_pinned_package(tmp_path)
    probed: list[str] = []

    def spy(venv_python, **kwargs):
        probed.append(os.fspath(venv_python))
        return True

    monkeypatch.setattr(verify, "check_packages_in_venv", spy)

    assert (
        cache_search.check_venv_dir(
            venv_dir,
            wanted=cache_search.wanted_packages(
                set(requirements.uninstalled), requirements.extra_requirements
            ),
            tag="3.12",
            uninstalled=set(requirements.uninstalled),
            source_names={"thing"},
            rawlog=True,
        )
        is True
    )

    assert probed == [os.fspath(environment.venv_python_for(venv_dir))]
    assert probed[0].startswith(os.fspath(venv_dir))
