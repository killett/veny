"""Pin the arguments phase 4a's call sites carry, at the sites themselves.

Phase 4a replaced a god object with five values, which moved a large amount of
wiring from "read a field" to "pass an argument". The STANDING CHECK measured
every one of those arguments by substitution; the holes it found were all the
same shape -- a call site inside ``pipeline.run`` whose callee every existing
test stubs, so no test could tell this run's value from a fresh one of the
same type.

These tests close that shape. They spy on the callee and assert **identity**:
the object the callee received must be the one the run built, not an equal or
default one. Identity is what makes them fail under the substitution -- a
fresh Settings with the same field values would pass an equality check.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import emmykit as ek
import pytest

from veny import (
    alias_index,
    cache_search,
    cli,
    environment,
    last_used,
    pipeline,
    state,
    stdlib_index,
    verify,
)
from veny import (
    settings as settings_module,
)
from veny.analysis import custom_modules
from veny.analysis.scan_state import ImportScan


def _recording_walk(seen: list[Any]) -> Any:
    """A dict_of_custom_modules stub that records the Settings it was given."""

    def walk(settings: Any, **kwargs: Any) -> dict[str, Any]:
        seen.append(settings)
        return {}

    return walk


def _recording_use_cache(seen: list[Any]) -> Any:
    """A dict_of_custom_modules stub that records the use_cache it was given."""

    def walk(settings: Any, *, use_cache: bool) -> dict[str, Any]:
        seen.append(use_cache)
        return {}

    return walk


def _recording_interpreter(seen: list[Any]) -> Any:
    """A venv_build_interpreter stub that records the command it was given."""

    def build(python_command: str) -> str:
        seen.append(python_command)
        return "/probe/python"

    return build


def _a_run(monkeypatch, tmp_path, argv=("--rawlog", "--no-cache")):
    """Drive cli.main() with every subprocess boundary stubbed.

    Deliberately does NOT stub list_packages, setup_virtualenv or
    build_alias_index: those are the call sites under test here, and each test
    replaces exactly the one it is measuring.

    Args:
        monkeypatch: pytest's patcher.
        tmp_path: The run's home.
        argv: Flags to pass before the script path.

    Returns:
        The script path the run was given.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    script = tmp_path / "script.py"
    script.write_text("import thing\n")
    monkeypatch.setenv("HOME", os.fspath(home))
    monkeypatch.setattr(sys, "argv", ["veny", *argv, os.fspath(script)])
    monkeypatch.setattr(ek, "find_preferred_python_version", lambda: "python3")
    monkeypatch.setattr(ek, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(ek, "print_all_errors", lambda *a, **k: None)
    monkeypatch.setattr(ek, "save_options_to_json", lambda options: None)
    monkeypatch.setattr(logging, "shutdown", lambda: None)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, *a, **k: subprocess.CompletedProcess(
            args=command, returncode=0
        ),
    )
    monkeypatch.setattr(
        custom_modules, "dict_of_custom_modules", lambda settings, **kwargs: {}
    )
    return script


def test_the_run_hands_setup_virtualenv_its_own_six_values(monkeypatch, tmp_path):
    """setup_virtualenv's six arguments must be the run's own, not fresh ones.

    Behaviour under test: the call site at the heart of the cache-miss branch,
    which phase 4a grew from one argument to six.

    Concrete bug this catches: any of the six replaced with a default-built
    value of the same type. A fresh Settings builds the venv under a different
    my_dir, so the cache never finds it again and every run rebuilds; a fresh
    Requirements installs nothing, so the venv is reported built and the
    script dies on the first import; a fresh alias index loses the run's
    resolutions, so the repair pass re-resolves every name over the network.
    Measured by substitution 2026-08-21: all six could be replaced with a
    default of the right type and the whole suite stayed green, because every
    test that reaches this branch stubs setup_virtualenv without looking at
    what it was handed.
    """
    _a_run(monkeypatch, tmp_path)
    seen: list[dict[str, Any]] = []
    scans: list[ImportScan] = []
    indexes: list[alias_index.AliasIndex] = []
    # A sentinel index so the stdlib argument can be pinned by identity: a
    # fresh StdlibIndex of the same shape would pass an equality check, and
    # the interpreter tag it decides is what every cached folder name carries.
    resolved_stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="wiring-probe"
    )
    monkeypatch.setattr(stdlib_index, "resolve", lambda command: resolved_stdlib)

    real_build = pipeline.build_alias_index

    def index_spy(settings, args, python_command):
        indexes.append(real_build(settings, args, python_command))
        return indexes[-1]

    def list_spy(settings, scan, target, **kwargs):
        scans.append(scan)
        return scan, state.Requirements(
            all_imports=frozenset({"thing"}),
            bad=frozenset(),
            installed=frozenset(),
            uninstalled=frozenset({alias_index.ResolvedImport("thing", "thing-pkg")}),
            seen_stdlib=frozenset(),
            extra_requirements={},
        )

    def setup_spy(settings, target, requirements, *, args, aliases, stdlib):
        seen.append(
            {
                "settings": settings,
                "target": target,
                "requirements": requirements,
                "args": args,
                "aliases": aliases,
                "stdlib": stdlib,
            }
        )
        return requirements, None, False

    monkeypatch.setattr(pipeline, "build_alias_index", index_spy)
    monkeypatch.setattr(pipeline, "list_packages", list_spy)
    monkeypatch.setattr(pipeline, "setup_virtualenv", setup_spy)

    cli.main()

    assert len(seen) == 1
    call = seen[0]
    # The run's own alias index, not a fresh empty one.
    assert call["aliases"] is indexes[0]
    # The Settings cli.main built: my_dir under this run's HOME.
    assert isinstance(call["settings"], settings_module.Settings)
    assert call["settings"].my_dir == tmp_path / "home" / "veny"
    # The Target resolve_target produced, carrying the resolved interpreter.
    assert call["target"].python_script == (tmp_path / "script.py").resolve()
    assert call["target"].python_command == "python3"
    # What classification decided, not an empty Requirements.
    assert {r.pip_name for r in call["requirements"].uninstalled} == {"thing-pkg"}
    # The parsed command line, carrying the flags this run was given.
    assert call["args"].no_cache is True
    # The stdlib index this run resolved, by identity -- not a fresh one.
    assert call["stdlib"] is resolved_stdlib


def test_the_run_hands_list_packages_the_scan_it_seeded(monkeypatch, tmp_path):
    """list_packages must get the seeded scan, this run's index and its flags.

    Behaviour under test: the call site that joins the custom-module walk to
    the scan.

    Concrete bug this catches: a fresh ImportScan here throws away the
    custom-module dict dict_of_custom_modules just built, so every local
    module looks like a PyPI package and veny tries to pip install the user's
    own files. A fresh alias index loses the run's resolutions. Measured by
    substitution 2026-08-21: scan, aliases, args and is_stdlib could each be
    replaced with a default and the suite stayed green.
    """
    _a_run(monkeypatch, tmp_path)
    monkeypatch.setattr(
        custom_modules,
        "dict_of_custom_modules",
        lambda settings, **kwargs: {"seeded_module": tmp_path / "seeded_module.py"},
    )
    seen: list[dict[str, Any]] = []
    indexes: list[alias_index.AliasIndex] = []
    real_build = pipeline.build_alias_index

    def index_spy(settings, args, python_command):
        indexes.append(real_build(settings, args, python_command))
        return indexes[-1]

    def list_spy(
        settings, scan, target, *, args, aliases, extra_requirements, is_stdlib
    ):
        seen.append(
            {
                "scan": scan,
                "args": args,
                "aliases": aliases,
                "extra_requirements": extra_requirements,
                "is_stdlib": is_stdlib,
            }
        )
        return scan, state.Requirements(
            all_imports=frozenset(),
            bad=frozenset(),
            installed=frozenset(),
            uninstalled=frozenset(),
            seen_stdlib=frozenset(),
            extra_requirements={},
        )

    monkeypatch.setattr(pipeline, "build_alias_index", index_spy)
    monkeypatch.setattr(pipeline, "list_packages", list_spy)

    cli.main()

    assert len(seen) == 1
    call = seen[0]
    # The seeded scan, not a fresh one: the custom-module dict is in it.
    assert call["scan"].custom_modules == {
        "seeded_module": tmp_path / "seeded_module.py"
    }
    assert call["aliases"] is indexes[0]
    assert call["args"].no_cache is True
    # The predicate is bound to this run's stdlib index, which was resolved
    # against python3 -- so a name only that index knows answers True.
    assert call["is_stdlib"]("os") is True
    assert call["is_stdlib"]("definitely_not_stdlib_anywhere") is False


def test_the_run_reports_the_scan_it_filled(monkeypatch, tmp_path):
    """report must be handed the scan list_packages returned, not a fresh one.

    Behaviour under test: the report call site.

    Concrete bug this catches: a fresh ImportScan makes the "Imported files in
    the same directory" and "Imported subfolders" lines empty on every run, so
    the only place a user is told veny read their own code goes silent.
    Measured by substitution 2026-08-21: the scan argument could be replaced
    with ImportScan() and the suite stayed green.
    """
    _a_run(monkeypatch, tmp_path, argv=("--justprint",))
    filled = ImportScan(subfolders=["wiring_probe_pkg"])

    def list_spy(settings, scan, target, **kwargs):
        return filled, state.Requirements(
            all_imports=frozenset(),
            bad=frozenset(),
            installed=frozenset(),
            uninstalled=frozenset(),
            seen_stdlib=frozenset(),
            extra_requirements={},
        )

    seen: list[ImportScan] = []
    monkeypatch.setattr(pipeline, "list_packages", list_spy)
    monkeypatch.setattr(
        pipeline,
        "report",
        lambda settings, scan, requirements: seen.append(scan),
    )

    cli.main()

    assert seen == [filled]
    assert seen[0] is filled


def test_the_run_builds_its_alias_index_from_its_own_settings(monkeypatch, tmp_path):
    """build_alias_index must get this run's Settings and resolved interpreter.

    Behaviour under test: the alias index's two wiring arguments.

    Concrete bug this catches: a fresh Settings puts the alias cache under a
    different my_dir, so the cache is written where the next run will not look
    and every import is re-resolved over the network. An empty python_command
    probes the interpreter running veny rather than the one that will run the
    script -- the phase 2 task 9 defect, where `cgi` was classified installed
    under 3.12 and died under 3.13. Measured by substitution 2026-08-21: both
    could be replaced and the suite stayed green.
    """
    _a_run(monkeypatch, tmp_path, argv=("--justprint",))
    seen: list[tuple[Any, str]] = []

    def index_spy(settings, args, python_command):
        seen.append((settings, python_command))
        return alias_index.empty(settings.my_dir)

    monkeypatch.setattr(pipeline, "build_alias_index", index_spy)
    monkeypatch.setattr(
        pipeline,
        "list_packages",
        lambda settings, scan, target, **kwargs: (
            scan,
            state.Requirements(
                all_imports=frozenset(),
                bad=frozenset(),
                installed=frozenset(),
                uninstalled=frozenset(),
                seen_stdlib=frozenset(),
                extra_requirements={},
            ),
        ),
    )

    cli.main()

    assert len(seen) == 1
    built_settings, python_command = seen[0]
    assert built_settings.my_dir == tmp_path / "home" / "veny"
    assert python_command == "python3"


def test_the_last_used_callback_carries_this_runs_target_and_cutoff(
    monkeypatch, tmp_path
):
    """The injected loader must close over this run's target and cutoff.

    Behaviour under test: the lambda handed to find_match_dir_in_cache, which
    is the only place the last-used pass reaches a Target at all.

    Concrete bug this catches: a wrong script_dir looks in a directory that
    holds no last-used JSON, so the last-used pointer silently never wins and
    every run falls through to "latest"; a cutoff of "00000000-000000" lets a
    pre-2025-08-10 record through, resurrecting string-valued paths into a run
    that expects Paths. Measured by substitution 2026-08-21: the options, the
    target and the cutoff could each be replaced and the suite stayed green.
    """
    script = _a_run(monkeypatch, tmp_path, argv=("--rawlog", "--last-used"))
    seen: list[dict[str, Any]] = []

    def loader_spy(options, *, script_dir, python_script, pathlibcutoff, rawlog):
        seen.append(
            {
                "script_dir": script_dir,
                "python_script": python_script,
                "pathlibcutoff": pathlibcutoff,
            }
        )
        return None

    monkeypatch.setattr(
        pipeline,
        "list_packages",
        lambda settings, scan, target, **kwargs: (
            scan,
            state.Requirements(
                all_imports=frozenset({"thing"}),
                bad=frozenset(),
                installed=frozenset(),
                uninstalled=frozenset(
                    {alias_index.ResolvedImport("thing", "thing-pkg")}
                ),
                seen_stdlib=frozenset(),
                extra_requirements={},
            ),
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )
    monkeypatch.setattr(last_used, "load_last_used_options", loader_spy)

    cli.main()

    assert len(seen) == 1
    assert seen[0]["script_dir"] == script.parent.absolute()
    assert seen[0]["python_script"] == script.resolve()
    assert seen[0]["pathlibcutoff"] == cli.Options().pathlibcutoff


def test_cli_builds_the_settings_from_the_shipped_defaults(monkeypatch, tmp_path):
    """The three default tables must reach the run, not empty stand-ins.

    Behaviour under test: cli.main's Settings construction, which is the only
    place the shipped tables are read.

    Concrete bug this catches: an empty stay_out_list makes the custom-module
    walk descend into every cached venv under ~/veny and report each package
    it finds as an import of the user's project; an empty known_bad_imports
    hands pip a name that is not on PyPI and never will be; an empty
    also_needs silently stops installing every dependency veny's own table
    declares, so the venv is reported complete while xarray cannot open a
    netCDF file. Measured by substitution 2026-08-21: all three could be
    replaced with empty collections and the suite stayed green.
    """
    _a_run(monkeypatch, tmp_path, argv=("--justprint",))
    seen: list[settings_module.Settings] = []
    monkeypatch.setattr(
        custom_modules,
        "dict_of_custom_modules",
        _recording_walk(seen),
    )
    monkeypatch.setattr(
        pipeline,
        "list_packages",
        lambda settings, scan, target, **kwargs: (
            scan,
            state.Requirements(
                all_imports=frozenset(),
                bad=frozenset(),
                installed=frozenset(),
                uninstalled=frozenset(),
                seen_stdlib=frozenset(),
                extra_requirements={},
            ),
        ),
    )

    cli.main()

    assert len(seen) == 1
    assert seen[0].stay_out_list == settings_module.DEFAULT_STAY_OUT_LIST
    assert seen[0].known_bad_imports == settings_module.DEFAULT_KNOWN_BAD_IMPORTS
    assert seen[0].also_needs == settings_module.DEFAULT_ALSO_NEEDS
    # Not merely equal to *something*: the shipped tables are non-empty, which
    # is what an empty stand-in would fail.
    assert "myenv" in seen[0].stay_out_list
    assert "snakeClass" in seen[0].known_bad_imports
    assert seen[0].also_needs["xarray"] == ("dask", "netCDF4", "h5netcdf")


def test_split_imports_gets_this_runs_index_flags_and_pins(monkeypatch, tmp_path):
    """Classification's five wiring arguments must be the run's own.

    Behaviour under test: the call list_packages makes into split_imports,
    which is where the run's alias index, its --reqs flag and its parsed pins
    reach classification.

    Concrete bug this catches: a fresh alias index resolves every name from
    scratch and cannot see the overrides the user configured, so `cv2` is
    handed to pip as "cv2" rather than "opencv-python"; empty
    extra_requirements drops every --reqs pin, so the venv is built without
    the versions the user asked for and reported complete. Measured by
    substitution 2026-08-21: settings, target, aliases and extra_requirements
    could each be replaced at this site and the suite stayed green.
    """
    script = _a_run(monkeypatch, tmp_path, argv=("--rawlog", "--reqs"))
    monkeypatch.setattr(
        environment,
        "parse_extra_requirements",
        lambda path, *, rawlog: {"thing-pkg": ">=2.0"},
    )
    seen: list[dict[str, Any]] = []
    indexes: list[alias_index.AliasIndex] = []
    real_build = pipeline.build_alias_index

    def index_spy(settings, args, python_command):
        indexes.append(real_build(settings, args, python_command))
        return indexes[-1]

    def split_spy(settings, scan, target, *, args, aliases, extra_requirements):
        seen.append(
            {
                "settings": settings,
                "target": target,
                "aliases": aliases,
                "extra_requirements": extra_requirements,
                "reqs": getattr(args, "reqs", False),
            }
        )
        return state.Requirements(
            all_imports=frozenset(),
            bad=frozenset(),
            installed=frozenset(),
            uninstalled=frozenset(),
            seen_stdlib=frozenset(),
            extra_requirements=extra_requirements,
        )

    monkeypatch.setattr(pipeline, "build_alias_index", index_spy)
    monkeypatch.setattr(pipeline, "split_imports", split_spy)
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )
    monkeypatch.setattr(
        cache_search, "find_match_dir_in_cache", lambda args, **kwargs: None
    )

    cli.main()

    assert len(seen) == 1
    call = seen[0]
    assert call["aliases"] is indexes[0]
    assert call["extra_requirements"] == {"thing-pkg": ">=2.0"}
    assert call["reqs"] is True
    assert call["target"].python_script == script.resolve()
    assert call["settings"].my_dir == tmp_path / "home" / "veny"


def test_the_run_stamps_its_target_with_the_time_it_started(monkeypatch, tmp_path):
    """Target.timestamp must be this run's, in the format the cache parses.

    Behaviour under test: resolve_target's stamp, which every cached venv
    folder name is built from.

    Concrete bug this catches: a hardcoded or misformatted stamp makes
    venv_cache.parse_folder_name reject the run's own venv on the next
    invocation, so the cache never hits and every run rebuilds from scratch --
    silently, because a cache miss is a legitimate outcome. Measured by
    substitution 2026-08-21: the stamp could be replaced with a literal and
    the suite stayed green.
    """
    script = tmp_path / "s.py"
    script.write_text("import os\n")
    args = argparse.Namespace(script=os.fspath(script), script_args=[])

    target = pipeline.resolve_target(args)

    assert target is not None
    parsed = venv_cache_parseable(target.timestamp)
    assert parsed, f"{target.timestamp!r} is not a folder-name stamp"
    # This run's, not a fixed one: the stamp is today's date.
    import datetime as dt

    assert target.timestamp.startswith(dt.datetime.now().strftime("%Y%m%d"))


def venv_cache_parseable(stamp: str) -> bool:
    """Whether venv_cache can parse a folder name carrying this stamp.

    Args:
        stamp: The candidate "YYYYmmdd-HHMMSS" string.

    Returns:
        True if a folder name built with it round-trips through venv_cache.
    """
    from veny import venv_cache

    name = venv_cache.build_folder_name(
        venv_name="myenv", interpreter_tag="3.12", timestamp=stamp, pip_names=["x"]
    )
    return venv_cache.parse_folder_name(name) is not None


def test_the_probe_venv_asks_about_the_interpreter_it_built(monkeypatch, tmp_path):
    """_probe_venv must build against the target's interpreter, not a default.

    Behaviour under test: the throwaway environment classification asks its
    "is this importable already?" question in.

    Concrete bug this catches: building the probe with the running interpreter
    rather than the one the script will run under classifies imports for the
    wrong Python -- a module removed in 3.13 imports fine in a 3.12 probe and
    is marked installed, then fails at run time under 3.13.
    """
    seen: list[str] = []
    monkeypatch.setattr(
        environment,
        "venv_build_interpreter",
        _recording_interpreter(seen),
    )
    monkeypatch.setattr(environment, "create_venv", lambda venv_dir, python: True)
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: False)
    target = state.Target(
        python_script=Path("/tmp/s.py"),
        script_dir=Path("/tmp"),
        script_args=(),
        python_command="the-runs-own-python",
        timestamp="20260821-120000",
    )

    with pipeline._probe_venv(target) as is_importable:
        assert is_importable("anything") is False

    assert seen == ["the-runs-own-python"]


@pytest.mark.parametrize("flag", ["rc", "no_cache"])
def test_either_refresh_flag_turns_the_custom_module_cache_off(
    monkeypatch, tmp_path, flag
):
    """--rc and --no-cache must each disable the custom-module cache.

    Behaviour under test: the use_cache expression, which is the one place
    two flags are combined into a single argument.

    Concrete bug this catches: reading only one of the two leaves the other
    flag silently inert, so `veny --rc script.py` reuses the stale cache it
    was invoked specifically to refresh. Measured by substitution 2026-08-21:
    the whole expression is multi-line and the first sweep could not mutate
    it, so it was measured by driving both flags instead.
    """
    _a_run(monkeypatch, tmp_path, argv=("--justprint", f"--{flag.replace('_', '-')}"))
    seen: list[bool] = []
    monkeypatch.setattr(
        custom_modules,
        "dict_of_custom_modules",
        _recording_use_cache(seen),
    )
    monkeypatch.setattr(
        pipeline,
        "list_packages",
        lambda settings, scan, target, **kwargs: (
            scan,
            state.Requirements(
                all_imports=frozenset(),
                bad=frozenset(),
                installed=frozenset(),
                uninstalled=frozenset(),
                seen_stdlib=frozenset(),
                extra_requirements={},
            ),
        ),
    )

    cli.main()

    assert seen == [False]


def test_the_custom_module_cache_is_on_when_neither_flag_is_given(
    monkeypatch, tmp_path
):
    """The other direction: an ordinary run must use the cache.

    Behaviour under test: the same expression's default.

    Concrete bug this catches: hardcoding use_cache=False makes every run
    re-walk the whole search tree for custom modules -- correct, but slow
    enough to be the difference between a one-second and a one-minute start,
    with nothing in the output to say why.
    """
    _a_run(monkeypatch, tmp_path, argv=("--justprint",))
    seen: list[bool] = []
    monkeypatch.setattr(
        custom_modules,
        "dict_of_custom_modules",
        _recording_use_cache(seen),
    )
    monkeypatch.setattr(
        pipeline,
        "list_packages",
        lambda settings, scan, target, **kwargs: (
            scan,
            state.Requirements(
                all_imports=frozenset(),
                bad=frozenset(),
                installed=frozenset(),
                uninstalled=frozenset(),
                seen_stdlib=frozenset(),
                extra_requirements={},
            ),
        ),
    )

    cli.main()

    assert seen == [True]


def test_the_saved_record_carries_the_venv_the_run_actually_used(monkeypatch, tmp_path):
    """The last-used record must contain the venv, or nothing can read it back.

    Behaviour under test: what pipeline.run hands to last_used.save at the
    end of a run.

    Concrete bug this catches: phase 4a's Task 6 moved venv_dir and
    venv_python onto the frozen VenvHandle and deleted them from Options. The
    unit suite stayed green -- nothing read them off Options any more -- but
    the saved record silently stopped containing a venv, so
    last_used.load_last_used_venv_python's `hasattr` check answered False and
    --feeling-lucky could never match again, on any script, forever. Found by
    scripts/differential_4a.py, which drives main() in both trees; this test
    is what closes it in-process. Phase 4b replaced the Options copy-back
    with veny's own LastUsed record; this test now reads that record off
    disk instead of inspecting what was handed to the old writer.
    """
    _a_run(monkeypatch, tmp_path, argv=("--rawlog", "--no-cache"))
    built = tmp_path / "home" / "veny" / "myenv-py3.12-20260101-010203-thing-pkg"
    targets: list[state.Target] = []
    handles: list[state.VenvHandle] = []
    monkeypatch.setattr(
        pipeline,
        "list_packages",
        lambda settings, scan, target, **kwargs: (
            scan,
            state.Requirements(
                all_imports=frozenset({"thing"}),
                bad=frozenset(),
                installed=frozenset(),
                uninstalled=frozenset(
                    {alias_index.ResolvedImport("thing", "thing-pkg")}
                ),
                seen_stdlib=frozenset(),
                extra_requirements={},
            ),
        ),
    )

    def setup_spy(settings, target, requirements, **kwargs):
        targets.append(target)
        handle = state.VenvHandle.for_dir(built)
        handles.append(handle)
        return requirements, handle, True

    monkeypatch.setattr(pipeline, "setup_virtualenv", setup_spy)

    cli.main()

    target = targets[0]
    handle = handles[0]
    record = last_used.load(
        script_dir=target.script_dir,
        python_script=target.python_script,
        my_name="veny",
        rawlog=True,
    )
    # Identity of the environment, not just its existence: the 4a regression
    # this test was written for wrote a record with no venv in it at all.
    assert record is not None
    assert record.venv_python == handle.venv_python
    assert record.venv_dir == handle.venv_dir


def test_the_saved_record_names_the_post_rename_venv_dir(monkeypatch, tmp_path):
    """The saved record must name the renamed folder, not the failed- one.

    Behaviour under test: last_used.save runs after the "failed-" rename in
    pipeline.run, so the record it writes points at the directory that
    actually exists on disk once the run has succeeded.

    Concrete bug this catches: hoisting the last_used.save call above the
    rename block -- the exact regression this task's brief names -- would
    record the pre-rename "failed-..." path, the directory rename_venv is
    about to move away from under it. The next run's --feeling-lucky lookup
    (or any other reader of the record) would then point at a directory that
    no longer exists.

    Neither sibling test catches this: the identity assertions in
    test_the_saved_record_carries_the_venv_the_run_actually_used never
    exercise the rename branch (its built venv has no "failed-" prefix, so
    pre- and post-rename `handle` are the same object regardless of where
    the save sits), and test_main_drops_the_failed_prefix_from_the_venv_it_
    just_built checks that the rename happened but never inspects the saved
    record. This test drives the rename for real and reads the record back
    off disk.
    """
    _a_run(monkeypatch, tmp_path, argv=("--rawlog", "--no-cache"))
    built = tmp_path / "home" / "veny" / "failed-myenv-py3.12-20260101-010203-thing-pkg"
    renamed = built.parent / "myenv-py3.12-20260101-010203-thing-pkg"
    monkeypatch.setattr(
        pipeline,
        "list_packages",
        lambda settings, scan, target, **kwargs: (
            scan,
            state.Requirements(
                all_imports=frozenset({"thing"}),
                bad=frozenset(),
                installed=frozenset(),
                uninstalled=frozenset(
                    {alias_index.ResolvedImport("thing", "thing-pkg")}
                ),
                seen_stdlib=frozenset(),
                extra_requirements={},
            ),
        ),
    )
    targets: list[state.Target] = []

    def setup_spy(settings, target, requirements, **kwargs):
        targets.append(target)
        # install_succeeded=True, and a "failed-" prefixed dir, is exactly
        # what fires pipeline.run's rename branch.
        return requirements, state.VenvHandle.for_dir(built), True

    monkeypatch.setattr(pipeline, "setup_virtualenv", setup_spy)

    cli.main()

    target = targets[0]
    record = last_used.load(
        script_dir=target.script_dir,
        python_script=target.python_script,
        my_name="veny",
        rawlog=True,
    )
    assert record is not None
    # The post-rename path, not the "failed-" one the venv was built under.
    assert record.venv_dir == renamed
    assert record.venv_python == renamed / "bin" / "python"
    # And it must be the real, post-rename directory on disk -- not merely
    # a Path string that happens to match while nothing is actually there.
    assert record.venv_dir.is_dir()
    assert not built.exists()
