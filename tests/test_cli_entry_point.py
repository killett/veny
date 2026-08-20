"""Tests for veny's entry point, identity and retired alias flags."""

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
    stdlib_index,
    verify,
)
from veny.analysis import custom_modules

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
    # Catches: restoring my_name = Path(sys.argv[0]).stem, which under
    # `python -m veny` yields "__main__" and moves every venv, log and pickle
    # veny owns from ~/veny to ~/__main__. No other test would notice: they
    # all build Options under pytest, where argv[0] is already arbitrary.
    monkeypatch.setenv("HOME", os.fspath(tmp_path))
    monkeypatch.setattr(sys, "argv", ["/tmp/anywhere/__main__.py"])

    options = cli.Options()

    assert options.my_name == "veny"
    assert options.my_dir == tmp_path / "veny"


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
    options = cli.Options()

    with pytest.raises(SystemExit) as excinfo:
        cli.parse_arguments(options)

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


def _drive_main(
    monkeypatch, tmp_path, argv, *, uninstalled, all_imports, venv_dir=None
):
    """Run cli.main() in process with every subprocess and scan boundary stubbed.

    main() is 400 lines of sequencing that nothing in the suite drove before
    this helper: it parses argv, resolves an interpreter, scans the script,
    classifies its imports, then picks one of four branches. Everything
    outside the branch under test is replaced -- the interpreter probe, the
    custom-module scan, the import classification, the alias index, the
    subprocess that would run the user's script, and emmykit's logging and
    options-file side effects -- leaving main()'s own wiring as the only live
    code.

    Returns:
        A pair: the one-element list that receives the Options object main()
        built, so a test can assert against the very fields main() wired from,
        and a list that receives one entry per script launch -- the exact
        command main() handed subprocess.run, as strings. The second is what
        lets a branch test tell "ran under sys.executable" apart from "ran
        under the venv's interpreter"; the old stub discarded its arguments,
        so no test could see which interpreter ran the script.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    script = tmp_path / "script.py"
    script.write_text("import thing\n")
    monkeypatch.setenv("HOME", os.fspath(home))
    monkeypatch.setattr(sys, "argv", ["veny", *argv, os.fspath(script)])
    monkeypatch.setattr(ek, "find_preferred_python_version", lambda: "python3")
    monkeypatch.setattr(
        stdlib_index,
        "resolve",
        lambda command: stdlib_index.StdlibIndex(
            names=frozenset({"os"}), python_version=(3, 12), source="test"
        ),
    )
    monkeypatch.setattr(pipeline, "build_alias_index", lambda options: _offline_index())
    monkeypatch.setattr(
        custom_modules, "dict_of_custom_modules", lambda settings, use_cache: {}
    )
    monkeypatch.setattr(ek, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(ek, "print_all_errors", lambda *a, **k: None)
    monkeypatch.setattr(ek, "save_options_to_json", lambda options: None)
    monkeypatch.setattr(logging, "shutdown", lambda: None)
    launched: list[list[str]] = []

    def record_run(command, *args, **kwargs):
        launched.append([os.fspath(part) for part in command])
        return subprocess.CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr(subprocess, "run", record_run)
    captured: list[cli.Options] = []

    def fake_list_packages(options):
        options.all_imports = set(all_imports)
        options.uninstalled_imports = set(uninstalled)
        if venv_dir is not None:
            options.set_venv_dir(venv_dir)
        captured.append(options)

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
    loaded: list[cli.Options] = []

    load_last_used_callbacks: list[Callable[[], object]] = []

    def find_spy(args, *, load_last_used, **kwargs):
        seen.append({"args": args, **kwargs})
        load_last_used_callbacks.append(load_last_used)
        return None

    def load_last_used_spy(options):
        loaded.append(options)
        return None

    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", find_spy)
    monkeypatch.setattr(pipeline, "_load_last_used", load_last_used_spy)
    monkeypatch.setattr(pipeline, "setup_virtualenv", lambda options: False)

    cli.main()

    options = captured[0]
    assert len(seen) == 1
    call = seen[0]
    assert call["args"] is options.args
    assert call["my_dir"] == tmp_path / "home" / "veny"
    assert call["venv_name"] == cli.Options().venv_name
    assert call["uninstalled"] == {
        cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")
    }
    assert call["extra_requirements"] == {}
    assert call["source_names"] == {"thing", "other"}
    assert call["tag"] == "3.12"
    assert call["rawlog"] is True
    # The callback must reach this run's own last-used loader, not a constant.
    assert load_last_used_callbacks[0]() is None
    assert loaded == [options]


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
    monkeypatch.setattr(pipeline, "setup_virtualenv", lambda options: False)

    with caplog.at_level(logging.INFO):
        cli.main()

    # From cache_search.find_match_dir_in_cache (cli.py's rawlog argument to it).
    assert (
        "Checking the cache for a virtual environment with all the required packages"
        in caplog.text
    )
    # From last_used.load_last_used_options, reached through _load_last_used --
    # the cache search's default branch asks for the last-used record first.
    assert "No previous JSON files found in the script directory." in caplog.text

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
    monkeypatch.setattr(pipeline, "setup_virtualenv", lambda options: False)
    with caplog.at_level(logging.INFO):
        cli.main()

    assert "Checking the cache for a virtual environment" not in caplog.text
    assert "No previous JSON files found" not in caplog.text


def test_main_lets_the_feeling_lucky_loader_speak_on_a_run_that_did_not_ask_for_raw_logs(
    monkeypatch, tmp_path, caplog
):
    """--feeling-lucky's loader gets its own rawlog argument, and its own hole.

    Measured 2026-08-19: `rawlog=True` at the load_last_used_venv_python call
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
    monkeypatch.setattr(pipeline, "setup_virtualenv", lambda options: False)

    with caplog.at_level(logging.INFO):
        cli.main()

    assert "No previous JSON files found in the script directory." in caplog.text

    caplog.clear()
    _drive_main(
        monkeypatch,
        tmp_path,
        ["--feeling-lucky", "--rawlog"],
        uninstalled={cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        all_imports={"thing"},
    )
    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "setup_virtualenv", lambda options: False)
    with caplog.at_level(logging.INFO):
        cli.main()

    assert "No previous JSON files found" not in caplog.text


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
    monkeypatch.setattr(pipeline, "setup_virtualenv", lambda options: False)

    cli.main()

    assert parsed == [{"path": cli.Options().extra_requirements_file, "rawlog": True}]
    assert captured[0].extra_requirements == {"extra-pkg": ">=2.0"}
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

    def fake_setup(options):
        options.set_venv_dir(built)
        options.install_succeeded = True
        return True

    monkeypatch.setattr(pipeline, "setup_virtualenv", fake_setup)
    renamed: list[tuple[Path, str]] = []

    def rename_spy(venv_dir, new_name):
        renamed.append((venv_dir, new_name))
        return venv_dir.parent / new_name

    monkeypatch.setattr(cache_search, "rename_venv", rename_spy)

    assert cli.main() == 0

    assert renamed == [(built, "myenv-py3.12-20260101-010203-thing-pkg")]
    assert (
        captured[0].venv_dir == built.parent / "myenv-py3.12-20260101-010203-thing-pkg"
    )


def test_main_asks_the_last_used_loader_about_this_script(monkeypatch, tmp_path):
    """--feeling-lucky's five arguments are wired in exactly one place.

    The lucky path skips analysis entirely and reruns the script under
    whichever interpreter the previous run recorded, so its arguments decide
    which record is consulted. Measured by substitution: all five could be
    replaced with all 338 tests green.

    Concrete bug this catches: a wrong `python_script` matches another
    script's last-used JSON in the same directory, and --feeling-lucky runs
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
    passed_options: list[cli.Options] = []

    def spy(options, **kwargs):
        seen.append(kwargs)
        passed_options.append(options)
        return None

    monkeypatch.setattr(last_used, "load_last_used_venv_python", spy)
    monkeypatch.setattr(pipeline, "setup_virtualenv", lambda options: False)
    monkeypatch.setattr(
        cache_search, "find_match_dir_in_cache", lambda args, **kwargs: None
    )

    cli.main()

    script = tmp_path / "script.py"
    assert len(seen) == 1
    assert seen[0]["script_dir"] == tmp_path
    assert seen[0]["python_script"] == script
    assert seen[0]["pathlibcutoff"] == cli.Options().pathlibcutoff
    assert seen[0]["rawlog"] is True
    # The run's own Options, not a fresh one: a fresh emmykit Options carries
    # an empty Namespace, so --feeling-lucky would read back as False and the
    # loader would be answering about a different (empty) run.
    passed = passed_options[0]
    assert getattr(passed.args, "feeling_lucky", False) is True
    assert passed.python_script == script


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
    construction: set_venv_dir puts the interpreter at <venv>/bin/python.
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
    set_venv_dir puts the interpreter at <venv>/bin/python, so
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

    def fake_setup(options):
        options.set_venv_dir(built_dir)
        return True

    monkeypatch.setattr(pipeline, "setup_virtualenv", fake_setup)

    status = cli.main()

    assert status == 0
    assert launched == [
        [os.fspath(built_dir / "bin" / "python"), os.fspath(tmp_path / "script.py")]
    ]


def test_main_checks_the_virtualenv_it_is_running_inside(monkeypatch, tmp_path):
    """Inside a virtualenv, main() import-checks that environment's python.

    Behaviour under test: the branch phase 3e made reachable. Concrete bug
    this catches: the old code asserted options.venv_dir, which nothing sets
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
    `getattr(options.args, "y", False)`, which is never set and so is always
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
    captured, launched = _drive_main(
        monkeypatch,
        tmp_path,
        ["--blank-slate", "-y"],
        uninstalled=set(),
        all_imports=set(),
    )
    monkeypatch.setattr(sys, "argv", ["veny", "--blank-slate", "-y"])
    monkeypatch.setattr(ek, "prompt_then_confirm", lambda prompt: True)

    status = cli.main()

    assert status == 0
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
        cli.parse_arguments(cli.Options())

    assert exit_info.value.code == 2


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

    def unavailable(options, start_time=None):
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

    def refused(options, start_time=None):
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
    monkeypatch.setattr(pipeline, "setup_virtualenv", lambda options: False)

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
    flags' contracts -- Options.my_name is fixed at "veny", no --debug means
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
    second bug it catches: parse_arguments reading the wrong flag name (or
    defaulting to True) when it decides whether to raise options.log_mode to
    DEBUG, which would either silence --debug entirely or make every run
    debug-verbose. Expected values come from Options.rawlog's default (False)
    and from --debug's contract (logging.DEBUG).
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
