"""Direct tests of the frozen values phase 4 passes between stages."""

import argparse
import dataclasses
import os
import sys
from pathlib import Path

import emmykit as ek
import pytest

from veny import cli, pipeline, state
from veny import settings as settings_module
from veny.analysis import custom_modules
from veny.analysis import scan as analysis_scan


def a_target(**overrides: object) -> state.Target:
    """A Target with every field set, for tests that only vary one of them.

    Public rather than underscored because the other test modules import it:
    a stage that now takes a Target needs one built explicitly at the call
    site, and building all five fields by hand in every test would bury what
    each test is actually varying. Deliberately a function and not a fixture
    -- an explicit call in the test body is what makes a test say which
    values it exercises.

    Args:
        **overrides: Field values to replace on the returned Target.

    Returns:
        A fully-populated Target.
    """
    target = state.Target(
        python_script=Path("/tmp/script-under-test.py"),
        script_dir=Path("/tmp"),
        script_args=(),
        python_command="",
        timestamp="20260821-120000",
    )
    return dataclasses.replace(target, **overrides)  # type: ignore[arg-type]


_a_target = a_target


def a_settings(**overrides: object) -> settings_module.Settings:
    """A Settings with every invariant set, for tests that vary one of them.

    Public for the same reason a_target is: the stages that used to read these
    ten fields off Options now take a Settings, and spelling all ten out in
    every test would bury what the test is varying.

    Args:
        **overrides: Field values to replace on the returned Settings.

    Returns:
        A fully-populated Settings.
    """
    base = settings_module.Settings(
        my_name="veny",
        my_dir=Path("/tmp/veny-under-test"),
        cwd=Path("/tmp"),
        venv_name="myenv",
        stay_out_list=settings_module.DEFAULT_STAY_OUT_LIST,
        search_above_this_dir=True,
        rawlog=True,
        known_bad_imports=settings_module.DEFAULT_KNOWN_BAD_IMPORTS,
        also_needs=settings_module.DEFAULT_ALSO_NEEDS,
        extra_requirements_file="extra_requirements.txt",
    )
    return dataclasses.replace(base, **overrides)  # type: ignore[arg-type]


_a_settings = a_settings


def test_settings_collections_cannot_be_mutated_by_a_consumer() -> None:
    """A stage must not be able to add to the run's own stay-out list.

    Behaviour under test: the types of Settings' three collection fields.

    Concrete bug this catches: declaring stay_out_list as list[str],
    known_bad_imports as set[str] and also_needs as a plain dict. Freezing a
    dataclass freezes the bindings, not the objects behind them, so a stage
    could still call .append and change what every later stage searches --
    a stay_out_list that grew mid-run would silently stop veny finding the
    user's own modules, and each stage would disagree about which.
    """
    settings = a_settings()

    with pytest.raises(AttributeError):
        settings.stay_out_list.append("nope")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        settings.known_bad_imports.add("nope")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        settings.also_needs["nope"] = ()  # type: ignore[index]


def test_settings_is_frozen() -> None:
    """The run's invariants are invariant.

    Behaviour under test: Settings' immutability.

    Concrete bug this catches: a plain @dataclass lets a stage rebind rawlog
    halfway through a run, so veny's commentary appears for some stages and
    not others -- which reads as a logging bug rather than as the ownership
    violation it is.
    """
    settings = a_settings()

    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.rawlog = False  # type: ignore[misc]


def test_the_run_builds_exactly_one_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One Settings object must serve the custom-module walk and the scan.

    Behaviour under test: that cli.main builds the Settings and both
    consumers below it receive that same object.

    Concrete bug this catches: leaving find_imports_in_script to build its
    own. 3e's wiring index measured four of that site's five fields dead,
    because the scanner reads only `rawlog`; two constructions is what made
    them dead. One construction, shared, is what closes those rows -- and a
    second construction built from defaults would quietly ignore whatever
    this run configured, so the scan would search directories the run asked
    it to stay out of.
    """
    script = tmp_path / "s.py"
    script.write_text("import os\n")
    seen: list[object] = []
    monkeypatch.setattr(sys, "argv", ["veny", "--justprint", os.fspath(script)])
    monkeypatch.setattr(ek, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(ek, "print_all_errors", lambda *a, **k: None)

    def record_walk(settings: object, **kwargs: object) -> dict[str, Path]:
        seen.append(settings)
        return {}

    monkeypatch.setattr(custom_modules, "dict_of_custom_modules", record_walk)
    monkeypatch.setattr(
        analysis_scan,
        "find_imports_in_script",
        lambda settings, path, **kwargs: seen.append(settings),
    )

    cli.main()

    assert len(seen) == 2
    assert seen[0] is seen[1]


def test_target_is_frozen() -> None:
    """A stage must not be able to write its product back onto the target.

    Behaviour under test: Target's immutability.

    Concrete bug this catches: declaring Target with a plain @dataclass.
    Under a mutable Target, resolve_target returning a value changes nothing
    -- a later stage can still reach back and rewrite script_dir, which is
    the accumulator behaviour phase 4 exists to remove. The run would then
    search one directory for custom modules and another for the last-used
    record, with nothing in the type system to say which was intended.
    """
    target = _a_target()

    with pytest.raises(dataclasses.FrozenInstanceError):
        target.script_dir = Path("/elsewhere")  # type: ignore[misc]


def test_target_carries_the_python_command_replace_gives_it() -> None:
    """python_command is discovered after the target is built, via replace().

    Behaviour under test: that dataclasses.replace produces a new Target
    carrying the resolved interpreter while leaving the original alone.

    Concrete bug this catches: forgetting to rebind the name `run` goes on to
    use, so every venv is built against "" rather than the resolved
    interpreter -- uv would fall back to whatever python it finds, and the
    stdlib index would describe a different version than the one that runs
    the script.
    """
    target = _a_target(script_args=("--flag", "value"))

    resolved = dataclasses.replace(target, python_command="/usr/bin/python3.12")

    assert resolved.python_command == "/usr/bin/python3.12"
    assert target.python_command == ""
    assert resolved.script_args == ("--flag", "value")


def test_target_holds_script_args_as_a_tuple() -> None:
    """The script's own arguments must not be a list a stage can append to.

    Behaviour under test: the type of Target.script_args.

    Concrete bug this catches: a list here is shared with whatever argparse
    handed over, so a stage that appends -- or a test that reuses the
    namespace -- silently changes what gets passed to the user's script on a
    later launch. The launch paths call list(...) on it at the boundary
    precisely so the run's own copy stays fixed.
    """
    target = _a_target(script_args=("-x", "1"))

    assert isinstance(target.script_args, tuple)


def test_resolve_target_returns_a_target_built_from_the_namespace(
    tmp_path: Path,
) -> None:
    """resolve_target must produce a value, not mutate what it was handed.

    Behaviour under test: resolve_target's whole contract -- it takes the
    parsed namespace and returns a Target.

    Concrete bug this catches: keeping the writes onto Options and merely
    returning a Target built from them. That leaves both spellings live, and
    a stage reading the stale Options field gets whatever the last writer
    left there rather than what this run resolved.

    Options keeps `python_script`, `script_dir` and `timestamp` through phase
    4a, because ek.save_options_to_json builds its filename off them and is
    typed against ek.Options rather than a payload. pipeline.run copies them
    across at the save and nowhere else; phase 4b removes them with the
    coupling. What resolve_target must no longer produce is a *run-time*
    reader of them, which is what the two assertions below pin.
    """
    script = tmp_path / "s.py"
    script.write_text("import os\n")
    args = argparse.Namespace(script=str(script), script_args=["-x"])

    target = pipeline.resolve_target(args)

    assert target is not None
    assert target.python_script == script.resolve(strict=True)
    assert target.script_dir == script.parent.absolute()
    assert target.script_args == ("-x",)
    assert target.python_command == ""
    # Drained outright: nothing reads either off Options any more.
    assert not hasattr(cli.Options(), "script_args")
    assert not hasattr(cli.Options(), "python_command")
    # Still present, and still empty: resolve_target must not write to them.
    assert cli.Options().python_script is None
    assert cli.Options().timestamp == ""


def test_resolve_target_returns_none_for_a_scriptless_run() -> None:
    """A scriptless run is not an error here -- `run` decides.

    Behaviour under test: what resolve_target does when no positional was
    given.

    Concrete bug this catches: raising UsageError inside resolve_target,
    which breaks --blank-slate. That mode legitimately has no script, and
    `run` is the layer that knows which mode flags excuse the absence.
    """
    args = argparse.Namespace(script=None, script_args=[])

    assert pipeline.resolve_target(args) is None


def test_resolve_target_stamps_the_run(tmp_path: Path) -> None:
    """The timestamp cached venv folder names are built from lives on Target.

    Behaviour under test: that resolve_target produces the run's stamp in the
    format venv_cache.build_folder_name parses.

    Concrete bug this catches: a stamp in another format -- or an empty one
    -- makes every cached folder name unparseable, so venv_cache.parse
    rejects the run's own venv on the next invocation and the cache never
    hits. The format is YYYYmmdd-HHMMSS; cache_search sorts on it by
    stripping the dash and comparing as an int.
    """
    script = tmp_path / "s.py"
    script.write_text("import os\n")
    args = argparse.Namespace(script=str(script), script_args=[])

    target = pipeline.resolve_target(args)

    assert target is not None
    assert len(target.timestamp) == 15
    assert target.timestamp[8] == "-"
    assert target.timestamp.replace("-", "").isdigit()
