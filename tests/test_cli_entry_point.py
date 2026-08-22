"""Tests for veny's entry point, identity and retired alias flags."""

import argparse
import datetime as dt
import logging
import os
import pickle
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import emmykit as ek
import pytest

import veny
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
from veny import settings as settings_module
from veny.analysis import custom_modules

from .test_state_values import a_requirements as _a_requirements
from .test_state_values import a_settings as _a_settings

REPO_ROOT = Path(__file__).resolve().parent.parent

# Captured before any test can monkeypatch it, so a test that needs the real
# custom-module discovery (rather than the stub _drive_main installs) can put
# it back. Phase 3d left the Settings handed to this function unpinned
# precisely because nothing ever ran the real one.
_REAL_DICT_OF_CUSTOM_MODULES = custom_modules.dict_of_custom_modules


def run_module(*args):
    """Run `python -m veny <args>` with src/ importable, capturing output."""
    env = {**os.environ, "PYTHONPATH": os.fspath(REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "veny", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_module_entry_point_reports_the_package_version():
    # Catches: __main__.py not wired to cli.main; prog left unset, which makes
    # argparse print "__main__.py 0.2.2"; the __init__.py literal drifting
    # from what the CLI reports.
    result = run_module("--version")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"veny {veny.__version__}"


def test_state_directory_ignores_argv0(monkeypatch, tmp_path):
    """The run's identity is the fixed name "veny", never argv[0]'s stem.

    Behaviour under test: the my_name and my_dir cli.main stamps onto the
    Settings every stage below it reads. Phase 4b Task 6 deleted the Options
    class that used to compute them, so this pin -- which is a live
    behaviour assertion, not a drain assertion -- now reads them off the
    Settings the run really builds.

    Concrete bug this catches: restoring my_name = Path(sys.argv[0]).stem,
    which under `python -m veny` yields "__main__" and moves every venv, log
    and record veny owns from ~/veny to ~/__main__. No other test would
    notice: every other run driven here spells argv[0] "veny" already.
    """
    captured, _ = _drive_main(
        monkeypatch, tmp_path, ["--justprint"], uninstalled=set(), all_imports=set()
    )
    # _drive_main spells argv[0] "veny"; replacing it with what
    # `python -m veny` really passes is the whole point of this test.
    monkeypatch.setattr(sys, "argv", ["/tmp/anywhere/__main__.py", *sys.argv[1:]])

    cli.main()

    assert captured.settings[0].my_name == "veny"
    assert captured.settings[0].my_dir == tmp_path / "home" / "veny"


@pytest.mark.parametrize(
    "argv_tail",
    [["--alias", "veny"], ["--manual"]],
    ids=["alias", "manual"],
)
def test_retired_alias_flags_are_rejected(argv_tail, monkeypatch):
    # Catches: a half-applied deletion that leaves the flags registered on the
    # parser while the functions behind them are gone -- an AttributeError at
    # the moment the flag is typed, rather than a clean argparse rejection.
    monkeypatch.setattr(sys, "argv", ["veny", *argv_tail])

    with pytest.raises(SystemExit) as excinfo:
        cli.parse_arguments()

    assert excinfo.value.code == 2


def test_module_entry_point_exits_with_mains_return_value():
    # Catches: __main__.py calling main() bare instead of sys.exit(main()),
    # which swallows any status main() returns rather than raises. Patching
    # main keeps this a test of the __main__ wiring alone -- the real
    # end-to-end proof that a wrapped script's status survives is
    # scripts/smoke-install.sh, which asserts exit 7.
    source = (
        "import runpy, veny.cli\n"
        "veny.cli.main = lambda: 3\n"
        "runpy.run_module('veny', run_name='__main__')\n"
    )
    env = {**os.environ, "PYTHONPATH": os.fspath(REPO_ROOT / "src")}
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 3, result.stderr


def _offline_index():
    """An AliasIndex that cannot reach PyPI, a seed, or a real cache file."""
    return alias_index.AliasIndex(
        overrides={},
        cache=alias_index.AliasCache(
            path=Path("/nonexistent/alias_cache.json"),
            interpreter_tag="3.12",
            entries={},
            rejections={},
        ),
        installed={},
        pypi=None,
        seed={},
    )


class _CapturedRun(list):  # type: ignore[type-arg]
    """The argparse namespace main() parsed, and the values it built from it.

    A list subclass rather than extra return values from _drive_main: every
    existing caller unpacks two values, and the Settings, Target and
    Requirements are needed only by the handful of tests that assert on what
    moved off Options in phase 4a. The list itself holds the namespace, which
    is what is left once the god object is drained.
    """

    def __init__(self) -> None:
        """Start with empty side-channels for the four values."""
        super().__init__()
        self.settings: list[settings_module.Settings] = []
        self.targets: list[state.Target] = []
        self.requirements: list[state.Requirements] = []


def _drive_main(
    monkeypatch, tmp_path, argv, *, uninstalled, all_imports, script_args=()
):
    """Run cli.main() in process with every subprocess and scan boundary stubbed.

    Phase 3e split the sequencing this helper drives out of main() and into
    pipeline.run; main() is now argv, four exception handlers and an exit
    status. The helper still drives the whole run through cli.main, because
    that is the wiring under test: it parses argv, resolves an interpreter,
    scans the script, classifies its imports, then picks one of four
    branches. Everything outside the branch under test is replaced -- the
    interpreter probe, the custom-module scan, the import classification, the
    alias index, the subprocess that would run the user's script, and
    emmykit's logging and options-file side effects -- leaving the wiring as
    the only live code.

    Args:
        script_args: Everything the user typed after the script itself.
            argparse collects these with REMAINDER, so they have to come
            after the script path on the command line, which is why they are
            a separate argument rather than part of `argv`.

    Returns:
        A pair: the _CapturedRun that receives the parsed namespace and its
        Settings/Target/Requirements side channels, so a test can assert
        against the very values main() wired through, and a list that
        receives one entry per script launch -- the exact command main()
        handed subprocess.run, as strings. The second is what lets a branch
        test tell "ran under sys.executable" apart from "ran under the
        venv's interpreter"; the old stub discarded its arguments, so no test
        could see which interpreter ran the script.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    script = tmp_path / "script.py"
    script.write_text("import thing\n")
    monkeypatch.setenv("HOME", os.fspath(home))
    monkeypatch.setattr(sys, "argv", ["veny", *argv, os.fspath(script), *script_args])
    monkeypatch.setattr(ek, "find_preferred_python_version", lambda: "python3")
    monkeypatch.setattr(
        stdlib_index,
        "resolve",
        lambda command: stdlib_index.StdlibIndex(
            names=frozenset({"os"}), python_version=(3, 12), source="test"
        ),
    )
    captured = _CapturedRun()

    def capture_the_run(settings, args, python_command):
        # build_alias_index is the earliest hook every branch of run() passes
        # through. Phase 4a drained the Options out of it too, so what is
        # captured here is the parsed namespace -- which is all any remaining
        # caller needs: the Settings, Target and Requirements have their own
        # side-channels below.
        captured.append(args)
        captured.settings.append(settings)
        return _offline_index()

    monkeypatch.setattr(pipeline, "build_alias_index", capture_the_run)
    monkeypatch.setattr(
        custom_modules, "dict_of_custom_modules", lambda settings, use_cache: {}
    )
    monkeypatch.setattr(ek, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(ek, "print_all_errors", lambda *a, **k: None)
    monkeypatch.setattr(logging, "shutdown", lambda: None)
    launched: list[list[str]] = []

    def record_run(command, *args, **kwargs):
        launched.append([os.fspath(part) for part in command])
        return subprocess.CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr(subprocess, "run", record_run)

    def fake_list_packages(settings, scan, target, **kwargs):
        captured.targets.append(target)
        captured.requirements.append(
            _a_requirements(
                all_imports=frozenset(all_imports),
                uninstalled=frozenset(uninstalled),
                extra_requirements=kwargs.get("extra_requirements", {}),
            )
        )
        return scan, captured.requirements[-1]

    monkeypatch.setattr(pipeline, "list_packages", fake_list_packages)
    return captured, launched


def test_main_describes_the_run_to_the_cache_search(monkeypatch, tmp_path):
    """main() is the only place find_match_dir_in_cache's nine arguments are wired.

    The cache search used to read them all off the Options object; the
    extraction turned every one into an explicit argument built here.
    Measured by substitution, all nine could be replaced with an empty or
    wrong value while all 338 tests stayed green -- nothing drove main() at
    all.

    Concrete bugs this catches: `my_dir=Path(...)` pointing anywhere else
    searches an empty directory, so every run rebuilds from scratch;
    `uninstalled=frozenset()` makes venv_cache.satisfies compare against
    nothing, so the first name-shaped folder in ~/veny is reused whatever it
    holds; `load_last_used=lambda: None` disables the last-used pointer
    entirely, silently, since a missing record is a legitimate miss.
    """
    captured, _ = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing", "other"},
    )
    seen: list[dict[str, object]] = []
    loaded: list[dict[str, object]] = []
    loaded_targets: list[state.Target] = []

    load_last_used_callbacks: list[Callable[[], object]] = []

    def find_spy(args, *, load_last_used, **kwargs):
        seen.append({"args": args, **kwargs})
        load_last_used_callbacks.append(load_last_used)
        return None

    def load_last_used_spy(target, **kwargs):
        loaded_targets.append(target)
        loaded.append(dict(kwargs))
        return None

    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", find_spy)
    monkeypatch.setattr(pipeline, "_load_last_used", load_last_used_spy)
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )

    cli.main()

    assert len(seen) == 1
    call = seen[0]
    # The run's own namespace, not a fresh one: the selection flags live on it.
    assert call["args"] is captured[0]
    assert call["my_dir"] == tmp_path / "home" / "veny"
    assert call["venv_name"] == _a_settings().venv_name
    assert call["uninstalled"] == {
        cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")
    }
    assert call["extra_requirements"] == {}
    assert call["source_names"] == {"thing", "other"}
    assert call["tag"] == "3.12"
    assert call["rawlog"] is True
    # The callback must reach this run's own last-used loader, not a constant.
    assert load_last_used_callbacks[0]() is None
    # One call, and about THIS run's script: the adapter now takes the run's
    # Target and the program's own name instead of an Options template, and
    # those three values are the whole of what decides which record file is
    # read.
    assert len(loaded) == 1
    assert loaded_targets[0].python_script == tmp_path / "script.py"
    assert loaded[0]["my_name"] == "veny"
    assert loaded[0]["rawlog"] is True


def test_main_lets_the_cache_search_speak_on_a_run_that_did_not_ask_for_raw_logs(
    monkeypatch, tmp_path, caplog
):
    """main() must hand the cache search and the last-used loader this run's own rawlog.

    Every other test that drives main() passes --rawlog, so `rawlog=True` --
    a wrong-but-type-correct value the STANDING CHECK's own method covers --
    could be hardcoded at either call site with the whole suite green: the
    spy tests assert `rawlog is True` and get exactly that. Measured
    2026-08-19 across all 17 `rawlog=` sites in cli/cache_search/last_used/
    verify: 16 of them survived the `True` substitution.

    Concrete bug this catches: `rawlog=True` at the find_match_dir_in_cache
    call site silences every informational line a normal run sees from the
    cache search -- "Checking the cache for a virtual environment...",
    "Skipping the cached venv X because Y", "Found N matching venv folders",
    "No matching venv folders found" -- so a user watching veny decide
    whether to reuse an environment is told nothing at all, and the same at
    the _load_last_used call site hides why the last-used pointer was not
    used.
    """
    _drive_main(
        monkeypatch,
        tmp_path,
        [],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    (tmp_path / "home" / "veny").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )

    with caplog.at_level(logging.INFO):
        cli.main()

    # From cache_search.find_match_dir_in_cache (cli.py's rawlog argument to it).
    assert (
        "Checking the cache for a virtual environment with all the required packages"
        in caplog.text
    )
    # From last_used.load, reached through _load_last_used -- the cache
    # search's default branch asks for the last-used record first.
    assert "No usable last-used record for" in caplog.text

    # The other direction: --rawlog must reach both, so a hardcoded
    # `rawlog=False` at either site is caught too.
    caplog.clear()
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )
    with caplog.at_level(logging.INFO):
        cli.main()

    assert "Checking the cache for a virtual environment" not in caplog.text
    assert "No usable last-used record" not in caplog.text


def test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs(
    monkeypatch, tmp_path, caplog
):
    """--feeling-lucky's loader gets its own rawlog argument, and its own hole.

    Measured 2026-08-19: `rawlog=True` at the load_venv_python call
    site left all 360 tests green. The cache search is stubbed out here on
    purpose -- main()'s other last-used call site (_load_last_used, reached
    from find_match_dir_in_cache) logs the identical line, so leaving it live
    would let either site cover for the other and neither would be pinned.

    Concrete bug this catches: a --feeling-lucky run that finds no usable
    record explains nothing about why, on a run that did not ask for raw
    logs.
    """
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--feeling-lucky"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )

    with caplog.at_level(logging.INFO):
        cli.main()

    assert "No usable last-used record for" in caplog.text

    caplog.clear()
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--feeling-lucky", "--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )
    with caplog.at_level(logging.INFO):
        cli.main()

    assert "No usable last-used record" not in caplog.text


def test_main_loads_the_requirements_file_and_keeps_its_names_out_of_the_import_check(
    monkeypatch, tmp_path
):
    """--reqs wires two call sites at once, and neither had a test.

    parse_extra_requirements is given the file name and the log setting;
    what it returns then has to reach both the cache search's
    extra_requirements and -- by its *absence* -- the source_names the import
    check is made against, because a --reqs entry is a pip spelling that
    import_module() can never succeed on.

    Measured by substitution: the file name, the rawlog flag, and all three
    arguments of the source_import_names call could each be replaced with
    all 338 tests green. Concrete bug this catches: dropping `use_reqs`
    leaves `extra-pkg` in source_names, so the venv check demands that
    `import extra_pkg` works, condemns a perfectly installed distribution,
    and rebuilds the environment on every run.
    """
    captured, _ = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog", "--reqs"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing", "extra-pkg"},
    )
    parsed: list[dict[str, object]] = []
    seen: list[dict[str, object]] = []

    def parse_spy(path, *, rawlog):
        parsed.append({"path": path, "rawlog": rawlog})
        return {"extra-pkg": ">=2.0"}

    monkeypatch.setattr(environment, "parse_extra_requirements", parse_spy)

    def find_spy(args, **kwargs):
        seen.append(kwargs)
        return None

    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", find_spy)
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )

    cli.main()

    assert parsed == [{"path": _a_settings().extra_requirements_file, "rawlog": True}]
    # The parsed mapping reaches classification as an argument now, not as a
    # field on Options -- captured.requirements holds what list_packages was
    # handed.
    assert captured.requirements[0].extra_requirements == {"extra-pkg": ">=2.0"}
    assert seen[0]["extra_requirements"] == {"extra-pkg": ">=2.0"}
    assert seen[0]["source_names"] == {"thing"}


def test_main_checks_the_surrounding_virtualenv_against_this_runs_imports(
    monkeypatch, tmp_path
):
    """Run from inside an activated venv, main() checks that venv, not a default.

    This branch skips the cache entirely and asks whether the environment the
    user is already in can serve the script. Measured by substitution, all
    three arguments (and all three of the nested source_import_names call)
    could be emptied with all 338 tests green.

    Concrete bug this catches: `uninstalled=frozenset()` with
    `source_names=frozenset()` makes check_packages_in_venv's bulk branch
    compare nothing at all, so veny reports the surrounding virtualenv is
    fine and runs the script in it -- and the script dies on the import veny
    was asked to provide. A second bug this catches: checking some venv other
    than the one VIRTUAL_ENV names -- e.g. sys.prefix, which under pytest is
    veny's own environment, not the one the run activated.
    """
    active = tmp_path / "activated-venv"
    active.mkdir()
    monkeypatch.setenv("VIRTUAL_ENV", os.fspath(active))
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog", "--reqs"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing", "extra-pkg"},
    )
    # --reqs, so that source_import_names' own use_reqs and extra_requirements
    # arguments are pinned here as well: extra-pkg is a pip spelling and must
    # be dropped from the names the venv is import-checked against.
    monkeypatch.setattr(
        environment,
        "parse_extra_requirements",
        lambda path, *, rawlog: {"extra-pkg": ">=2.0"},
    )
    monkeypatch.setattr(last_used, "is_virtualenv", lambda: True)
    seen: list[dict[str, object]] = []

    def check_spy(venv_python, **kwargs):
        seen.append({"venv_python": venv_python, **kwargs})
        return True

    monkeypatch.setattr(verify, "check_packages_in_venv", check_spy)

    assert cli.main() == 0

    assert seen == [
        {
            "venv_python": environment.venv_python_for(active),
            "uninstalled": {
                cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")
            },
            "source_names": {"thing"},
        }
    ]


def test_main_drops_the_failed_prefix_from_the_venv_it_just_built(
    monkeypatch, tmp_path
):
    """A venv that worked must lose its "failed-" prefix, under its own name.

    setup_virtualenv builds into `failed-<name>` so an interrupted run leaves
    an obviously unusable folder behind; main() renames it only once the run
    has actually succeeded. Measured by substitution: both arguments of that
    rename_venv call could be replaced with all 338 tests green.

    Concrete bug this catches: a hardcoded new name renames the venv to
    something parse_folder_name cannot read, which retires it from the cache
    for good -- every later run rebuilds, and the orphan folder is never
    reused or cleaned up.
    """
    captured, _ = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog", "--no-cache"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    built = tmp_path / "home" / "veny" / "failed-myenv-py3.12-20260101-010203-thing-pkg"

    def fake_setup(settings, target, requirements, **kwargs):
        return requirements, state.VenvHandle.for_dir(built), True

    monkeypatch.setattr(pipeline, "setup_virtualenv", fake_setup)
    renamed: list[tuple[Path, str]] = []

    def rename_spy(venv_dir, new_name):
        renamed.append((venv_dir, new_name))
        return venv_dir.parent / new_name

    monkeypatch.setattr(cache_search, "rename_venv", rename_spy)

    assert cli.main() == 0

    assert renamed == [(built, "myenv-py3.12-20260101-010203-thing-pkg")]
    # The renamed directory really exists -- run() rebuilt its handle from
    # rename_venv's return value, and VenvHandle.for_dir mkdirs it. A stale
    # return value would leave the "failed-" name on disk instead.
    assert (built.parent / "myenv-py3.12-20260101-010203-thing-pkg").is_dir()


def test_main_asks_the_last_used_loader_about_this_script(monkeypatch, tmp_path):
    """--feeling-lucky's five arguments are wired in exactly one place.

    The lucky path skips analysis entirely and reruns the script under
    whichever interpreter the previous run recorded, so its arguments decide
    which record is consulted. Measured by substitution: all five could be
    replaced with all 338 tests green.

    Concrete bug this catches: a wrong `python_script` names another
    script's last-used record in the same directory, and --feeling-lucky runs
    this script under an environment built for a different one.
    """
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog", "--feeling-lucky"],
        uninstalled=set(),
        all_imports=set(),
    )
    seen: list[dict[str, object]] = []

    def spy(**kwargs):
        seen.append(kwargs)
        return None

    monkeypatch.setattr(last_used, "load_venv_python", spy)
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )
    monkeypatch.setattr(
        cache_search, "find_match_dir_in_cache", lambda args, **kwargs: None
    )

    cli.main()

    script = tmp_path / "script.py"
    assert len(seen) == 1
    assert seen[0]["script_dir"] == tmp_path
    assert seen[0]["python_script"] == script
    assert seen[0]["my_name"] == "veny"
    assert seen[0]["rawlog"] is True
    # Four arguments, not five: the Options template the emmykit-typed reader
    # needed is gone, and so is the pathlibcutoff it compared timestamps
    # against. That the loader was reached at all is what proves the run read
    # --feeling-lucky off its own parsed arguments -- a run that did not would
    # never call it.


def test_main_runs_the_script_under_the_running_interpreter_when_nothing_is_missing(
    monkeypatch, tmp_path
):
    """With no uninstalled imports, main() runs the script under sys.executable.

    Behaviour under test: the first of main()'s four branches. Concrete bug
    this catches: routing this branch through the venv interpreter instead --
    which the cached-venv branch below legitimately does -- would make a run
    that needs no environment build a venv anyway, or crash on a venv_python
    that is None. Expected value obtained from the branch's own contract: no
    environment was acquired, so the only interpreter available is the one
    veny is running under.
    """
    captured, launched = _drive_main(
        monkeypatch, tmp_path, ["--rawlog"], uninstalled=set(), all_imports={"os"}
    )

    status = cli.main()

    assert status == 0
    assert launched == [[sys.executable, os.fspath(tmp_path / "script.py")]]


def test_main_runs_the_script_under_the_cached_venvs_interpreter_on_a_cache_hit(
    monkeypatch, tmp_path
):
    """A cache hit runs the script under that venv's python, not sys.executable.

    Behaviour under test: the fourth branch, on the path where
    find_match_dir_in_cache returns a folder. Concrete bug this catches:
    launching with sys.executable after a cache hit would run the user's
    script in whatever environment veny itself is in -- the packages just
    matched would not be importable, and the failure would look like a bad
    cache match rather than a bad launch. Expected value obtained by
    construction: VenvHandle puts the interpreter at <venv>/bin/python.
    """
    venv_dir = tmp_path / "home" / "veny" / "myenv-py3.12-20260819-000000-thing"
    venv_dir.mkdir(parents=True)
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(
        cache_search, "find_match_dir_in_cache", lambda *a, **k: venv_dir
    )

    status = cli.main()

    assert status == 0
    assert launched == [
        [
            os.fspath(venv_dir / "bin" / "python"),
            os.fspath(tmp_path / "script.py"),
        ]
    ]


def test_main_builds_an_environment_when_the_cache_misses(monkeypatch, tmp_path):
    """A cache miss builds an environment and runs the script under it.

    Behaviour under test: the same branch's other side -- the cache search
    returns nothing, so an environment has to be built before anything can
    run. Concrete bug this catches: launching under sys.executable after a
    successful build -- which the all-installed branch above legitimately
    does -- would run the user's script in veny's own environment, where the
    packages just installed are not importable, while main() still returns 0;
    the user sees an ImportError for a package veny reported installing. The
    same assertion also fails if a successful build leaves match_dir unset,
    because then nothing is launched at all and veny still reports success.
    Expected value obtained by construction, not by reading the branch: the
    fake builder is the only thing in this test that sets venv_dir, and
    VenvHandle puts the interpreter at <venv>/bin/python, so
    built_dir/bin/python is the only interpreter path a correct run can use.
    """
    built_dir = tmp_path / "home" / "veny" / "myenv-py3.12-20260819-111111-thing"
    built_dir.mkdir(parents=True)
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", lambda *a, **k: None)

    def fake_setup(settings, target, requirements, **kwargs):
        return requirements, state.VenvHandle.for_dir(built_dir), False

    monkeypatch.setattr(pipeline, "setup_virtualenv", fake_setup)

    status = cli.main()

    assert status == 0
    assert launched == [
        [os.fspath(built_dir / "bin" / "python"), os.fspath(tmp_path / "script.py")]
    ]


def test_main_checks_the_virtualenv_it_is_running_inside(monkeypatch, tmp_path):
    """Inside a virtualenv, main() import-checks that environment's python.

    Behaviour under test: the branch phase 3e made reachable. Concrete bug
    this catches: the old code asserted a venv_dir on Options, which nothing sets
    on this path, so the branch could only ever raise AssertionError --
    veny was unusable from inside an activated environment. Expected value
    obtained by construction: environment.venv_python_for puts the
    interpreter at <venv>/bin/python.
    """
    active = tmp_path / "activated"
    active.mkdir()
    monkeypatch.setenv("VIRTUAL_ENV", os.fspath(active))
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(last_used, "is_virtualenv", lambda: True)
    checked: list[object] = []

    def check_spy(interpreter, **kwargs):
        checked.append(os.fspath(interpreter))
        return False

    monkeypatch.setattr(verify, "check_packages_in_venv", check_spy)

    status = cli.main()

    assert status == 1
    assert checked == [os.fspath(active / "bin" / "python")]
    assert launched == []


def test_justprint_runs_no_script_and_exits_zero(monkeypatch, tmp_path):
    """--justprint reports and stops. Nothing is launched, status is 0.

    Behaviour under test: the flag's entire contract. Concrete bug this
    catches: a reordering that puts the justprint check after the
    all-installed branch would run the user's script on a flag that promises
    not to. Expected value obtained from --help's own wording: "Don't run the
    script, just print its package requirements."
    """
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--justprint", "--rawlog"],
        uninstalled=set(),
        all_imports={"os"},
    )

    status = cli.main()

    assert status == 0
    assert launched == []


def test_blank_slate_deletes_the_state_directory_and_leaves_other_files_alone(
    monkeypatch, tmp_path
):
    """--blank-slate removes ~/veny and veny's own dotfiles, nothing else.

    Behaviour under test: the destructive mode, driven in process for the
    first time. Concrete bug this catches: a widened glob deleting the user's
    own .json files in the working directory -- the branch's filter is four
    OR'd name tests and nothing pinned any of them. The mirror-image bug is
    caught too: narrowing the filter to the .out clause alone leaves the
    last-used JSON record behind, so ~/veny is gone while a pointer into it
    survives in the working directory and the next --feeling-lucky run
    follows it to a directory that no longer exists. Expected values obtained
    by construction from the four clauses: .veny-run.out matches the first
    (".veny-" prefix, ".out" suffix); .script.py-veny-last-used-on-...json
    matches the fourth (dot prefix, "-veny-" inside, ".json" suffix);
    keep.json does not start with a dot and so matches none of them.

    The confirmation prompt is stubbed rather than answered by -y, because
    measured 2026-08-19 the flag does not reach this branch: argparse gives
    `-y/--yes` the dest `yes`, while the branch reads
    `getattr(args, "y", False)`, which is never set and so is always
    False. That is a pre-existing bug, recorded here rather than fixed,
    because this phase is behaviour-preserving; -y is kept in argv so this
    test keeps working unchanged once the dest is corrected and the prompt
    stops being reached at all. Stubbing the
    prompt is a stdin boundary stub, not a stub of the code under test: the
    deletion loop below still runs for real, against real files.
    """
    home = tmp_path / "home"
    state_dir = home / "veny"
    state_dir.mkdir(parents=True)
    (state_dir / "myenv-py3.12-000000-thing").mkdir()
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / ".veny-run.out").write_text("log\n")
    (workdir / ".script.py-veny-last-used-on-20260101-000000.json").write_text("{}\n")
    (workdir / "keep.json").write_text("{}\n")
    monkeypatch.chdir(workdir)
    _, _ = _drive_main(
        monkeypatch,
        tmp_path,
        ["--blank-slate", "-y"],
        uninstalled=set(),
        all_imports=set(),
    )
    monkeypatch.setattr(sys, "argv", ["veny", "--blank-slate", "-y"])
    prompts: list[str] = []

    def confirm_spy(prompt):
        prompts.append(prompt)
        return True

    monkeypatch.setattr(ek, "prompt_then_confirm", confirm_spy)

    status = cli.main()

    assert status == 0
    # The prompt must name what is about to be deleted, in this run's own
    # terms: measured 2026-08-19, replacing it with any other string left the
    # whole suite green, and a prompt that does not say what it will destroy
    # is a prompt nobody can answer responsibly.
    assert prompts == [
        "Are you sure you want to delete everything in ~/veny/ and all veny"
        " .json files in the current directory? (y/n) "
    ]
    assert not state_dir.exists()
    assert not (workdir / ".veny-run.out").exists()
    assert not (workdir / ".script.py-veny-last-used-on-20260101-000000.json").exists()
    assert (workdir / "keep.json").exists()


def test_the_full_flag_is_gone(monkeypatch, tmp_path):
    """--full is rejected by argparse, not silently accepted.

    Behaviour under test: ledger item 3's resolution. Concrete bug this
    catches: deleting the branches but leaving the parser.add_argument call
    would leave a flag that parses, does nothing, and reports success -- worse
    than the broken flag it replaced. Expected value obtained from argparse's
    documented behaviour: an unrecognized option is a usage error, status 2.
    """
    script = tmp_path / "script.py"
    script.write_text("import os\n")
    monkeypatch.setattr(sys, "argv", ["veny", "--full", os.fspath(script)])

    with pytest.raises(SystemExit) as exit_info:
        cli.parse_arguments()

    assert exit_info.value.code == 2


def test_parse_arguments_returns_the_parsed_command_line(monkeypatch):
    """parse_arguments hands its namespace back to the caller.

    Behaviour under test: the return value the signature change introduced.

    Concrete bug this catches: a parse_arguments that still writes onto a
    passed-in object and returns None. Every caller would then read a
    namespace that is never filled -- main() would die on the first getattr.
    The two shapes it has to carry back are asserted together: the `script`
    positional and a store_true flag. `--rawlog` is spelled before the
    script because `script_args` is an argparse.REMAINDER, which swallows
    everything typed after the script path.
    """
    monkeypatch.setattr(sys, "argv", ["veny", "--rawlog", "thing.py", "-x"])

    parsed = cli.parse_arguments()

    assert parsed.script == "thing.py"
    assert parsed.rawlog is True
    assert parsed.script_args == ["-x"]


def test_a_run_with_no_script_is_a_usage_error(monkeypatch, tmp_path, caplog):
    """No script and no --blank-slate returns 2 and says what is missing.

    Behaviour under test: the first of the two pre-existing AssertionError
    crashes. Concrete bug this catches: the old fall-through reached
    `assert options.python_script is not None` inside list_packages and died
    with a traceback, so `veny -y` looked like a veny bug rather than a
    mistyped command. Expected value obtained from the design's exit table:
    2 is a usage error.
    """
    # _drive_main stubs the interpreter probe, the alias index and the scan,
    # then appends a script path to argv; this run must have no script, so
    # argv is replaced afterwards. Everything else it stubs is still needed --
    # the usage check sits after the alias index build, not before it.
    _drive_main(monkeypatch, tmp_path, ["-y"], uninstalled=set(), all_imports=set())
    monkeypatch.setattr(sys, "argv", ["veny", "-y"])

    with caplog.at_level(logging.INFO):
        status = cli.main()

    assert status == 2
    assert "--blank-slate" in caplog.text
    assert "--full" not in caplog.text


def test_main_maps_a_missing_uv_to_status_one(monkeypatch, tmp_path, capsys):
    """UvUnavailable reaches cli.main and becomes exit 1 with its message.

    Behaviour under test: the other half of exit ownership -- raising is only
    correct if someone catches. Concrete bug this catches: an uncaught
    UvUnavailable would surface as a traceback and a status of 1 anyway,
    making the failure look like a veny crash rather than a missing
    dependency. Expected value obtained from the design's exit table: 1 means
    veny could not build or find an environment. The message is the exact text
    environment.uv_binary raises, which is the exact text its SystemExit used
    to carry: it must still reach stderr, where SystemExit put it.
    """
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
    )

    def unavailable(settings, args, target, start_time=None):
        raise environment.UvUnavailable(
            "veny requires uv, which is not installed and is not on PATH.\n"
            "Reinstall veny with:  uv tool install veny"
        )

    monkeypatch.setattr(pipeline, "run", unavailable)

    status = cli.main()

    assert status == 1
    assert "Reinstall veny with:  uv tool install veny" in capsys.readouterr().err


def test_main_maps_a_failed_venv_build_to_status_one(monkeypatch, tmp_path, caplog):
    """VenvBuildFailed reaches cli.main and becomes exit 1 with its message.

    Behaviour under test: the third arm of main()'s status mapping. Nothing
    raised VenvBuildFailed before phase 3e task 7 gave _probe_venv its guard,
    so the handler was unreachable and untested. Concrete bug this catches:
    deleting the `except pipeline.VenvBuildFailed` clause -- which nothing else
    in the suite would notice -- turns a refused probe build into a traceback
    out of main(), which reads as a veny crash, and leaves
    ek.print_all_errors and logging.shutdown unrun.

    pipeline.run is stubbed rather than driven into the real probe path
    because _drive_main already replaces pipeline.list_packages, which is
    where the probe venv is built: this test is about main()'s mapping, and
    tests/test_classify.py pins that _probe_venv is what raises. Expected
    value obtained from the design's exit table: 1 means veny could not build
    or find an environment.
    """
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
    )

    def refused(settings, args, target, start_time=None):
        raise pipeline.VenvBuildFailed(
            "Could not build the throwaway environment used to check which "
            "imports are already available."
        )

    monkeypatch.setattr(pipeline, "run", refused)

    with caplog.at_level(logging.ERROR):
        status = cli.main()

    assert status == 1
    assert "Could not build the throwaway environment" in caplog.text


def test_a_failed_build_reports_at_critical_and_returns_one_without_a_debugger(
    monkeypatch, tmp_path, caplog
):
    """setup_virtualenv returning False logs CRITICAL and ends the run at 1.

    Behaviour under test: the cache-miss build-failure path, which until this
    task called ek.my_critical_error(..., choose_breakpoint=True). Concrete
    bugs this catches. First, that call ended in `breakpoint()`: a user whose
    venv build failed got a pdb prompt, and anywhere stdin is not a tty --
    cron, CI, a pipe -- got a BdbQuit traceback instead of a sentence, so this
    test would hang or die rather than return a status if it came back.
    Second, dropping the report entirely and keeping only the status would
    leave a run that exits 1 having said nothing about why; the record is
    asserted at CRITICAL because ek.configure_logging's MemoryHandler buffers
    at ERROR and above, which is what puts this message in
    ek.print_all_errors' replay at the end of the run.

    Expected values obtained from the design's exit table (1 means veny could
    not build or find an environment) and from the message emmykit logged at
    this site, which is unchanged.
    """
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )

    with caplog.at_level(logging.CRITICAL):
        status = cli.main()

    assert status == 1
    critical = [
        record
        for record in caplog.records
        if record.levelno == logging.CRITICAL
        and record.getMessage() == "Failed to create a virtual environment."
    ]
    assert len(critical) == 1, caplog.text


def test_configure_logging_is_told_this_runs_name_level_and_raw_output_choice(
    monkeypatch, tmp_path
):
    """cli.main hands ek.configure_logging this run's own name, level and rawlog.

    Behaviour under test: the last of phase 3d's five open `rawlog` holes, and
    the one that stays in cli.py. Concrete bug this catches: a hardcoded
    `rawlog=False` here restores timestamps and INFO prefixes to every
    --rawlog run, which is the entire point of the flag; a hardcoded name
    sends veny's log file somewhere other than the program's own name; a
    hardcoded level ignores --debug. None of the three could be seen by any
    existing test, because the effect is inside emmykit's handler
    configuration rather than in veny's own output.

    This is the one site in the phase pinned by an argument spy rather than by
    a log record, and the index says so: the effect lives in emmykit, so
    there is no veny-visible record to read. Expected values come from the
    flags' contracts -- cli.MY_NAME is fixed at "veny", no --debug means
    logging.INFO, --rawlog means rawlog=True.
    """
    seen: list[tuple[str, int, bool]] = []
    _drive_main(
        monkeypatch, tmp_path, ["--rawlog"], uninstalled=set(), all_imports={"os"}
    )
    monkeypatch.setattr(
        ek,
        "configure_logging",
        lambda name, *, log_level, rawlog: seen.append((name, log_level, rawlog)),
    )

    cli.main()

    assert seen == [("veny", logging.INFO, True)]


def test_configure_logging_is_told_when_the_run_wants_normal_output_and_debug(
    monkeypatch, tmp_path
):
    """The same site driven the other way: no --rawlog, and --debug raises the level.

    Behaviour under test: the second half of the substitution pair, plus the
    only consumer of parse_arguments' `--debug` handling. Concrete bug this
    catches: a hardcoded `rawlog=True` strips timestamps and INFO prefixes
    from every ordinary run and suppresses veny's own commentary -- the exact
    inverse failure, invisible to a test that only ever drives --rawlog. A
    second bug it catches: cli.main reading the wrong flag name (or
    defaulting to True) when it decides whether to raise its local log_mode
    to DEBUG, which would either silence --debug entirely or make every run
    debug-verbose. Expected values come from --rawlog's default (False, the
    store_true default parse_arguments gives it) and from --debug's contract
    (logging.DEBUG).
    """
    seen: list[tuple[str, int, bool]] = []
    _drive_main(monkeypatch, tmp_path, ["-d"], uninstalled=set(), all_imports={"os"})
    monkeypatch.setattr(
        ek,
        "configure_logging",
        lambda name, *, log_level, rawlog: seen.append((name, log_level, rawlog)),
    )

    cli.main()

    assert seen == [("veny", logging.DEBUG, False)]


def test_main_lets_the_requirements_reader_explain_a_missing_file(
    monkeypatch, tmp_path, caplog
):
    """--reqs must carry this run's rawlog into the reader that opens the file.

    Behaviour under test: the second of phase 3d's five open `rawlog` holes,
    which moved from cli.py into pipeline.run. 3d could not close it because
    the only test driving --reqs stubs parse_extra_requirements out and
    asserts the value the spy was handed -- `rawlog=True` at the call site
    hands that spy exactly what it asserts. This drives the real reader
    instead and reads its effect: emmykit's my_fopen logs "File does not
    exist" at INFO when, and only when, rawlog is False.

    Concrete bug this catches: `rawlog=True` hardcoded here silences the one
    line telling a user who typed --reqs that there is no
    extra_requirements.txt where veny looked, so the run continues with no
    extra requirements and no explanation of why the pins they wrote were
    ignored. Expected message obtained from emmykit's my_fopen, which is the
    reader parse_extra_requirements calls with suppress_errors=True.
    """
    _drive_main(
        monkeypatch, tmp_path, ["--reqs"], uninstalled=set(), all_imports={"os"}
    )
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / "extra_requirements.txt").exists()

    with caplog.at_level(logging.INFO):
        cli.main()

    assert (
        f"File does not exist: {os.fspath(tmp_path / 'extra_requirements.txt')}"
        in caplog.text
    )

    # The other direction: --rawlog must reach the reader too, so a hardcoded
    # rawlog=False at this call site is caught as well.
    caplog.clear()
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--reqs", "--rawlog"],
        uninstalled=set(),
        all_imports={"os"},
    )
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.INFO):
        cli.main()

    assert "File does not exist" not in caplog.text


def _run_with_the_real_custom_module_scan(monkeypatch, tmp_path, workdir, argv):
    """Drive cli.main() with the real dict_of_custom_modules, in its own directory.

    Each case gets a fresh working directory because the real scan writes a
    pickle into the one it runs in: reusing a directory would let the previous
    case's cache decide which branch the next one takes. sys.path is narrowed
    to that directory so the walk is bounded to it.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    _drive_main(monkeypatch, tmp_path, argv, uninstalled=set(), all_imports={"os"})
    monkeypatch.setattr(
        custom_modules, "dict_of_custom_modules", _REAL_DICT_OF_CUSTOM_MODULES
    )
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(sys, "path", [os.fspath(workdir)])
    cli.main()


def test_main_lets_the_custom_module_scan_explain_an_empty_cache(
    monkeypatch, tmp_path, caplog
):
    """The Settings pipeline.run builds must carry this run's own name, cwd, rawlog and cache choice.

    Behaviour under test: the third of phase 3d's five open `rawlog` holes --
    the `Settings(...)` handed to dict_of_custom_modules -- together with the
    `use_cache` argument built beside it from --rc and --no-cache. 3d could
    not close it because every test that drives the run stubs
    dict_of_custom_modules out entirely. This one runs the real discovery and
    reads its effect, in four directions.

    Concrete bugs this catches: `rawlog=True` in that Settings silences the
    line explaining that no custom-module cache was found, so a user whose
    run is slow because it rescans sys.path every time is told nothing;
    `use_cache=False`, or reading the wrong flag for --no-cache, skips the
    cache lookup altogether, which is the same slowdown with the same
    silence; `use_cache=True` ignores --no-cache (or --rc) and reuses a stale
    cache the user explicitly asked veny to rebuild; a wrong `my_name` looks for
    pickles under a prefix veny never writes, so the cache is never found and
    every run rescans; a wrong `cwd` looks for them in the wrong directory,
    with the same result. Expected messages obtained from custom_modules,
    which logs them on the cache-lookup branch only.
    """
    with caplog.at_level(logging.INFO):
        _run_with_the_real_custom_module_scan(
            monkeypatch, tmp_path, tmp_path / "plain", []
        )

    assert (
        "No existing custom modules pickle files found in the current directory."
        in caplog.text
    )

    # --rawlog silences it, so a hardcoded rawlog=False in that Settings dies too.
    caplog.clear()
    with caplog.at_level(logging.INFO):
        _run_with_the_real_custom_module_scan(
            monkeypatch, tmp_path, tmp_path / "raw", ["--rawlog"]
        )

    assert "No existing custom modules pickle files" not in caplog.text

    # --no-cache turns the whole cache lookup off, which silences the same
    # line for a different reason: it pins the use_cache argument, not rawlog.
    caplog.clear()
    with caplog.at_level(logging.INFO):
        _run_with_the_real_custom_module_scan(
            monkeypatch, tmp_path, tmp_path / "nocache", ["--no-cache"]
        )

    assert "No existing custom modules pickle files" not in caplog.text

    # --rc means "refresh the custom modules cache", which turns the lookup
    # off by the other flag: it pins the second half of the use_cache
    # expression, which --no-cache alone cannot distinguish.
    caplog.clear()
    with caplog.at_level(logging.INFO):
        _run_with_the_real_custom_module_scan(
            monkeypatch, tmp_path, tmp_path / "rc", ["--rc"]
        )

    assert "No existing custom modules pickle files" not in caplog.text

    # A cache written under veny's own name, in the directory veny was run
    # from, is found and loaded: that pins the my_name and cwd arguments,
    # which the three cases above cannot see because none of them has a
    # pickle to find.
    caplog.clear()
    cached = tmp_path / "cached"
    cached.mkdir()
    planted = cached / f".veny_custom_modules_{ek.COMPUTER_NAME}_20260101-010203.pkl"
    planted.write_bytes(pickle.dumps({}))
    with caplog.at_level(logging.INFO):
        _run_with_the_real_custom_module_scan(monkeypatch, tmp_path, cached, [])

    assert f"Loading custom modules from most recent pickle file: {planted}" in (
        caplog.text
    )


def _a_cache_hit(monkeypatch, tmp_path, argv, script_args=()):
    """Drive a run that finds a cached venv and launches the script from it."""
    venv_dir = tmp_path / "home" / "veny" / "myenv-py3.12-20260819-000000-thing"
    venv_dir.mkdir(parents=True, exist_ok=True)
    _, launched = _drive_main(
        monkeypatch,
        tmp_path,
        argv,
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
        script_args=script_args,
    )
    monkeypatch.setattr(
        cache_search, "find_match_dir_in_cache", lambda *a, **k: venv_dir
    )
    return venv_dir, launched


def _an_active_virtualenv_that_satisfies_the_run(
    monkeypatch, tmp_path, argv, script_args=()
):
    """Drive a run from inside an activated venv that has everything needed."""
    active = tmp_path / "activated"
    active.mkdir(exist_ok=True)
    monkeypatch.setenv("VIRTUAL_ENV", os.fspath(active))
    _, launched = _drive_main(
        monkeypatch,
        tmp_path,
        argv,
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
        script_args=script_args,
    )
    monkeypatch.setattr(last_used, "is_virtualenv", lambda: True)
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: True)
    return launched


def _a_lucky_run(monkeypatch, tmp_path, argv, script_args=()):
    """Drive --feeling-lucky with a last-used interpreter that exists."""
    lucky_python = tmp_path / "lucky-venv" / "bin" / "python"
    lucky_python.parent.mkdir(parents=True, exist_ok=True)
    _, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--feeling-lucky", *argv],
        uninstalled=set(),
        all_imports=set(),
        script_args=script_args,
    )
    monkeypatch.setattr(last_used, "load_venv_python", lambda **kwargs: lucky_python)
    return lucky_python, launched


def test_only_the_venv_launch_announces_the_command_it_is_about_to_run(
    monkeypatch, tmp_path, caplog
):
    """`announce` is set at exactly one of run_script's four call sites.

    Behaviour under test: which launches log "Running command: ...". The venv
    launch has always announced itself; the three bare-interpreter launches
    never have, and run_script's `announce` argument is what preserves that
    difference now that all four go through one function.

    Measured by substitution: adding `announce=True` at any of the other
    three sites, and removing it from the venv site, left the whole suite
    green -- the driver records the argv a launch produced, not the lines it
    logged. Concrete bug this catches: `announce=True` everywhere prints a
    command line before every run, including the one that needed no
    environment at all, which is exactly the noise --rawlog exists to remove
    and which veny has never emitted on those paths; dropping it from the
    venv site removes the only record of which interpreter a cached
    environment actually launched, which is the first thing anyone debugging
    a wrong-venv run looks for.
    """
    venv_dir, _ = _a_cache_hit(monkeypatch, tmp_path, [])

    with caplog.at_level(logging.INFO):
        cli.main()

    expected = (
        f"Running command: {os.fspath(venv_dir / 'bin' / 'python')} "
        f"{os.fspath(tmp_path / 'script.py')}"
    )
    assert expected in caplog.text

    # --rawlog silences it: run_script's rawlog argument must be this run's own.
    caplog.clear()
    _a_cache_hit(monkeypatch, tmp_path, ["--rawlog"])
    with caplog.at_level(logging.INFO):
        cli.main()

    assert "Running command" not in caplog.text

    # The three launches that must stay quiet, each on a run that did not ask
    # for raw logs -- so silence is the announce argument, not the flag.
    caplog.clear()
    _drive_main(monkeypatch, tmp_path, [], uninstalled=set(), all_imports={"os"})
    with caplog.at_level(logging.INFO):
        cli.main()

    assert "Running command" not in caplog.text

    caplog.clear()
    _an_active_virtualenv_that_satisfies_the_run(monkeypatch, tmp_path, [])
    with caplog.at_level(logging.INFO):
        cli.main()

    assert "Running command" not in caplog.text

    caplog.clear()
    _a_lucky_run(monkeypatch, tmp_path, [])
    with caplog.at_level(logging.INFO):
        cli.main()

    assert "Running command" not in caplog.text


def test_every_launch_path_passes_the_scripts_own_arguments_through(
    monkeypatch, tmp_path
):
    """Everything the user typed after the script must reach the script.

    Behaviour under test: Target.script_args, which resolve_target reads off the
    parsed namespace and which all four run_script call sites forward.
    Measured by substitution: replacing that argument with `[]` at every one
    of the four sites left the whole suite green -- no test had ever put an
    argument after the script name.

    Concrete bug this catches: veny silently swallowing the script's own
    command line. `veny train.py --epochs 50` would run train.py with no
    arguments at all, and the script would either use its defaults or fail
    on a missing required argument, with nothing in veny's output to say the
    arguments were dropped. Expected values obtained from argparse's
    REMAINDER contract: everything after the script is the script's.
    """
    script = os.fspath(tmp_path / "script.py")
    passed = ["--epochs", "50"]

    venv_dir, launched = _a_cache_hit(monkeypatch, tmp_path, [], script_args=passed)
    cli.main()
    assert launched == [
        [os.fspath(venv_dir / "bin" / "python"), script, "--epochs", "50"]
    ]

    _, launched = _drive_main(
        monkeypatch,
        tmp_path,
        [],
        uninstalled=set(),
        all_imports={"os"},
        script_args=passed,
    )
    cli.main()
    assert launched == [[sys.executable, script, "--epochs", "50"]]

    launched = _an_active_virtualenv_that_satisfies_the_run(
        monkeypatch, tmp_path, [], script_args=passed
    )
    cli.main()
    assert launched == [[sys.executable, script, "--epochs", "50"]]

    lucky_python, launched = _a_lucky_run(monkeypatch, tmp_path, [], script_args=passed)
    cli.main()
    assert launched == [[os.fspath(lucky_python), script, "--epochs", "50"]]


def test_a_satisfied_surrounding_virtualenv_runs_the_script_under_it(
    monkeypatch, tmp_path
):
    """The in-a-virtualenv branch's success side must launch something, and the right thing.

    Behaviour under test: the half of the branch phase 3e made reachable that
    no test looked at -- the existing pair assert the import check's
    arguments and the failure status, never that a script ran or under which
    interpreter. Measured by substitution: the interpreter and the script
    handed to run_script here could both be replaced with a wrong path and
    the whole suite stayed green.

    Concrete bug this catches: launching the venv veny would have built (or
    None) instead of the interpreter veny is running under, on the one branch
    where no environment was acquired at all -- so a run from inside a
    perfectly good activated environment either crashes on a None path or
    runs the user's script somewhere else entirely. Expected value obtained
    from the branch's contract: the surrounding environment already has the
    packages, so sys.executable is the interpreter that has them.
    """
    launched = _an_active_virtualenv_that_satisfies_the_run(monkeypatch, tmp_path, [])

    status = cli.main()

    assert status == 0
    assert launched == [[sys.executable, os.fspath(tmp_path / "script.py")]]


def test_feeling_lucky_launches_the_interpreter_the_loader_named(monkeypatch, tmp_path):
    """--feeling-lucky must run the script under the last-used interpreter it found.

    Behaviour under test: the lucky path's launch, which the existing lucky
    test never reaches -- its loader stub returns None, so nothing is
    launched. Measured by substitution: the interpreter, the script and the
    script's arguments at this call site could all be replaced with wrong
    values and the whole suite stayed green.

    Concrete bug this catches: launching sys.executable here instead of the
    recorded interpreter, which makes --feeling-lucky mean "run the script in
    veny's own environment" -- it would fail on the very imports the recorded
    environment exists to provide, while veny reports the lucky path
    succeeded. Expected value obtained by construction: the loader is the
    only thing in this test that names an interpreter.
    """
    lucky_python, launched = _a_lucky_run(monkeypatch, tmp_path, [])

    status = cli.main()

    assert status == 0
    assert launched == [[os.fspath(lucky_python), os.fspath(tmp_path / "script.py")]]


def test_the_run_reports_the_imports_it_decided_are_missing(
    monkeypatch, tmp_path, caplog
):
    """pipeline.run must hand the report this run's own findings.

    Behaviour under test: the one call between classification and the branch
    that acquires an environment. Measured by substitution: handing `report`
    a throwaway Options left the whole suite green -- every test that drives
    the run either passes --rawlog, which silences the report entirely, or
    never looks at what was logged.

    Concrete bug this catches: the report describing anything other than this
    run, which removes the only line naming the packages veny is about to
    spend a build installing. A user watching a slow run has nothing to
    check the decision against, and a wrong classification -- the failure the
    line exists to make visible -- becomes silent.
    """
    _drive_main(
        monkeypatch,
        tmp_path,
        [],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )

    with caplog.at_level(logging.INFO):
        cli.main()

    assert "Uninstalled imports: ['thing']" in caplog.text


def test_no_cache_skips_the_cache_search_entirely(monkeypatch, tmp_path):
    """--no-cache must stop the cache being searched, not merely ignored.

    Behaviour under test: the flag read that chooses between searching the
    cache and going straight to a build. Measured by substitution: reading
    any other attribute name off the parsed arguments there left the whole
    suite green, because every test that reaches this branch either stubs the
    cache search to return None or never passes --no-cache.

    Concrete bug this catches: a misread flag makes --no-cache search the
    cache anyway and reuse whatever it finds, which is the exact opposite of
    what the user asked for -- and invisible, because a reused environment
    that happens to work looks like a successful run.
    """
    built = tmp_path / "home" / "veny" / "myenv-py3.12-20260101-000000-thing"
    built.mkdir(parents=True)
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--rawlog", "--no-cache"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing")},
        all_imports={"thing"},
    )
    searched: list[object] = []

    def find_spy(args, **kwargs):
        searched.append(args)
        return built

    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", find_spy)

    def fake_setup(settings, target, requirements, **kwargs):
        return requirements, state.VenvHandle.for_dir(built), False

    monkeypatch.setattr(pipeline, "setup_virtualenv", fake_setup)

    assert cli.main() == 0
    assert searched == []


def test_the_state_directory_is_only_announced_when_it_has_to_be_created(
    monkeypatch, tmp_path, caplog
):
    """The "does not exist yet" line must be about veny's own directory.

    Behaviour under test: the existence check that decides whether to create
    ~/veny and say so. Measured by substitution: asking about any other path
    left the whole suite green, because no test that reaches this line runs
    with ~/veny already there.

    Concrete bug this catches: checking the wrong path makes veny announce
    that it is creating its state directory on every single run, including
    the thousands where the directory has been there for months -- noise that
    trains users to ignore the one run where it is true, which is the run
    where their cache has just been deleted.
    """
    (tmp_path / "home" / "veny").mkdir(parents=True)
    _drive_main(monkeypatch, tmp_path, [], uninstalled=set(), all_imports={"os"})

    with caplog.at_level(logging.INFO):
        cli.main()

    assert "does not exist yet" not in caplog.text


def test_blank_slate_with_no_state_directory_still_completes(monkeypatch, tmp_path):
    """--blank-slate on a machine that has never run veny must not blow up.

    Behaviour under test: --blank-slate on a machine with no ~/veny at all,
    which the only other --blank-slate test cannot reach because it creates
    the directory first.

    Concrete bug this catches: any first-ever --blank-slate that fails --
    a traceback, or a non-zero status, for a request that was already
    satisfied before it was made. It does not pin `ignore_errors=True` on the
    removal itself: pipeline.run creates settings.my_dir a few lines before it
    reaches this branch, so the removal never sees a missing directory. The
    wiring index records that as an open hole with this as its reason.
    """
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--blank-slate", "-y"],
        uninstalled=set(),
        all_imports=set(),
    )
    monkeypatch.setattr(sys, "argv", ["veny", "--blank-slate", "-y"])
    monkeypatch.setattr(ek, "prompt_then_confirm", lambda prompt: True)
    assert not (tmp_path / "home" / "veny").exists()

    assert cli.main() == 0


def test_build_alias_index_reads_this_runs_own_directory_and_interpreter(
    tmp_path, monkeypatch
):
    """The alias index must be built from this run's my_dir and target interpreter.

    Behaviour under test: the two positional arguments of the alias_index.build
    call. Measured by substitution: both could be replaced with a wrong string
    or a wrong path and the whole suite stayed green -- every test that drives
    the run replaces build_alias_index wholesale, and the one test of the
    `offline` argument spies on the call rather than on what comes back.

    Concrete bugs this catches: a wrong my_dir puts the alias cache and the
    user's own override file somewhere veny never reads again, so every run
    re-resolves every import name from scratch and hand-written overrides are
    silently ignored; a wrong interpreter tags the cache with the wrong
    Python, which is what lets an entry recorded under one version
    short-circuit resolution for a target on another. Expected values are
    read off the returned index rather than from a spy: the cache's own path
    and the tag the probe produced.
    """
    args = argparse.Namespace(offline=True)

    index = pipeline.build_alias_index(
        _a_settings(my_dir=tmp_path), args, sys.executable
    )

    assert index.cache.path == tmp_path / "module_aliases_cache.json"
    # The probe really ran against the interpreter named above, so it knows
    # both that interpreter's version and what is installed in it.
    assert index.cache.interpreter_tag == (
        f"{sys.version_info[0]}.{sys.version_info[1]}"
    )
    assert "pytest" in index.installed


def test_the_run_is_timed_from_the_moment_veny_started(monkeypatch, tmp_path, caplog):
    """cli.main must hand pipeline.run the start it took before argparse.

    Behaviour under test: the `start_time` argument, which is the only reason
    `pipeline.run` takes one at all -- it defaults to "now", so a call site
    that forgets it still produces a plausible-looking number. Measured by
    substitution: replacing it with a fixed past datetime left the whole
    suite green.

    Concrete bug this catches: an elapsed time that is not this run's. The
    substitution recorded in the wiring index, `dt.datetime(2000, 1, 1)`,
    makes both "Elapsed time" lines report about nine thousand *days*; the
    mirror-image bug, a start taken after the work rather than before it,
    reports a negative delta. Either way the two lines a user reads to decide
    whether veny or their own script is the slow part become fiction.

    The log-shape assertions alone cannot see the bug this test is named for,
    which is why the argument itself is recorded here as well. Dropping
    `start_time=start_time` from `cli.main`'s `pipeline.run` call makes `run`
    fall back to its own `dt.datetime.now()` default and report a few
    milliseconds -- comfortably inside "non-negative and under a minute", so
    every log assertion below still passes. That regression is real: Task 4
    shipped it and its fix round (`6b35844`) repaired it. So `pipeline.run` is
    wrapped rather than replaced -- the real run still executes and still logs
    -- and the recorded `start_time` is bracketed between an instant taken
    before `cli.main` and the instant `cli.parse_arguments` returned. Three
    mutations die on that bracket: dropping the keyword (recorded value is
    None), passing a fixed past datetime (below the lower bound, which is the
    wiring index's `dt.datetime(2000, 1, 1)` row), and taking the start after
    argparse instead of before it (above the upper bound). No sleep and no
    assumption about how long anything takes: `<=` at both ends means even a
    clock too coarse to separate the two instants still passes.
    """
    _drive_main(monkeypatch, tmp_path, [], uninstalled=set(), all_imports={"os"})

    handed: list[dt.datetime | None] = []
    real_run = pipeline.run

    def run_spy(settings, args, target, start_time=None):
        handed.append(start_time)
        return real_run(settings, args, target, start_time=start_time)

    monkeypatch.setattr(pipeline, "run", run_spy)

    parsed_at: list[dt.datetime] = []
    real_parse_arguments = cli.parse_arguments

    def parse_arguments_spy():
        parsed = real_parse_arguments()
        parsed_at.append(dt.datetime.now())
        return parsed

    monkeypatch.setattr(cli, "parse_arguments", parse_arguments_spy)

    before_main = dt.datetime.now()
    with caplog.at_level(logging.INFO):
        cli.main()

    reported = [
        record.args[0]
        for record in caplog.records
        if record.getMessage().startswith("Elapsed time:")
    ]
    assert reported, caplog.text
    assert all(
        dt.timedelta(0) <= elapsed < dt.timedelta(minutes=1) for elapsed in reported
    ), reported

    assert handed, "cli.main never reached pipeline.run"
    assert parsed_at, "cli.main never reached cli.parse_arguments"
    (start_time,) = handed
    assert start_time is not None, (
        "cli.main called pipeline.run without start_time, so run timed itself "
        "from inside instead of from when veny started"
    )
    assert before_main <= start_time <= parsed_at[0], (
        f"start_time {start_time} is not veny's own start: it must fall "
        f"between {before_main} (before cli.main) and {parsed_at[0]} (when "
        f"parse_arguments returned)"
    )
