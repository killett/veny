"""Direct tests of the frozen values phase 4 passes between stages."""

import argparse
import contextlib
import dataclasses
import os
import sys
from pathlib import Path

import emmykit as ek
import pytest

from veny import alias_index, cli, pipeline, state
from veny import settings as settings_module
from veny.alias_index import ResolvedImport
from veny.analysis import custom_modules
from veny.analysis import scan as analysis_scan
from veny.analysis.scan_state import ImportScan


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


def a_requirements(**overrides: object) -> state.Requirements:
    """A Requirements with every field set, for tests that vary one of them.

    Public for the same reason a_target and a_settings are: classification's
    product is a value now, so the stages that consume it need one built at
    the call site.

    Args:
        **overrides: Field values to replace on the returned Requirements.

    Returns:
        A fully-populated Requirements. Empty by default -- a test that cares
        about a particular import names it.
    """
    base = state.Requirements(
        all_imports=frozenset(),
        bad=frozenset(),
        installed=frozenset(),
        uninstalled=frozenset(),
        seen_stdlib=frozenset(),
        extra_requirements={},
    )
    return dataclasses.replace(base, **overrides)  # type: ignore[arg-type]


_a_requirements = a_requirements


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


def test_repairing_imports_rebinds_rather_than_mutating_requirements() -> None:
    """The repair pass must produce a NEW Requirements, not edit the old one.

    Behaviour under test: that Requirements is a value, so
    dataclasses.replace is the only way to fold a repair in.

    Concrete bug this catches: `requirements.uninstalled = frozenset(...)`,
    which a frozen dataclass refuses, or reaching around it with
    object.__setattr__, which it does not. Under a mutation the manifest
    written before the repair and the check run after it would describe the
    same object, so a repair that changed everything would be
    indistinguishable from one that changed nothing -- and the manifest would
    claim the venv holds whatever was first attempted rather than what
    actually provided each import.
    """
    before = a_requirements(
        all_imports=frozenset({"cv2"}),
        uninstalled=frozenset({ResolvedImport(import_name="cv2", pip_name="cv2")}),
    )

    after = dataclasses.replace(
        before,
        uninstalled=frozenset(
            {ResolvedImport(import_name="cv2", pip_name="opencv-python")}
        ),
    )

    assert {r.pip_name for r in before.uninstalled} == {"cv2"}
    assert {r.pip_name for r in after.uninstalled} == {"opencv-python"}
    assert before is not after
    with pytest.raises(dataclasses.FrozenInstanceError):
        before.uninstalled = frozenset()  # type: ignore[misc]


def test_split_imports_returns_requirements_and_writes_nothing_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Classification's product is a return value, not four Options writes.

    Behaviour under test: pipeline.split_imports' contract.

    Concrete bug this catches: keeping the copy-back that stood at the old
    pipeline.py:235-238. It turned each frozenset back into a set precisely
    so a later stage could mutate it -- the accumulator shape the design
    rules out ("ImportScan and Requirements are values, not accumulators").
    With both spellings live, a stage reading the stale Options field gets
    whatever the last writer left there.
    """
    monkeypatch.setattr(
        pipeline,
        "_probe_venv",
        lambda target: contextlib.nullcontext(lambda import_name: False),
    )
    scan = ImportScan(all_imports={"widgetlib"})

    result = pipeline.split_imports(
        a_settings(rawlog=True),
        scan,
        a_target(),
        args=argparse.Namespace(reqs=False),
        aliases=alias_index.empty(tmp_path / "index"),
        extra_requirements={},
    )

    assert isinstance(result, state.Requirements)
    assert {r.import_name for r in result.uninstalled} == {"widgetlib"}
    assert not hasattr(cli.Options(), "uninstalled_imports")
    assert not hasattr(cli.Options(), "bad_imports")
    assert not hasattr(cli.Options(), "all_imports")


def test_venv_handle_does_not_resolve_the_interpreter_symlink(tmp_path: Path) -> None:
    """venv_python must stay inside the venv, symlink and all.

    Behaviour under test: the three paths VenvHandle.for_dir derives.

    Concrete bug this catches: calling .resolve() on venv_dir/"bin"/"python".
    In a real venv that symlink points at the base interpreter, so a resolved
    path runs the system python with none of the venv's packages -- every
    installed requirement would look missing at run time, and veny would
    rebuild the environment on every invocation.

    The interpreter symlink is real here, and has to be: .resolve() on a path
    that does not exist returns the path unchanged, so a fixture without the
    symlink cannot tell the bug from the fix. Measured 2026-08-21 -- the
    first version of this test passed under the mutation.
    """
    base = tmp_path / "base" / "bin"
    base.mkdir(parents=True)
    (base / "python3.12").write_text("#!/bin/sh\n")
    venv_dir = tmp_path / "myenv-py3.12-20260821-120000"
    (venv_dir / "bin").mkdir(parents=True)
    (venv_dir / "bin" / "python").symlink_to(base / "python3.12")

    handle = state.VenvHandle.for_dir(venv_dir)

    assert handle.venv_python.parent.parent == handle.venv_dir
    assert handle.venv_python.name == "python"
    assert handle.venv_python == venv_dir / "bin" / "python"
    # The decisive one: resolving would land in base/bin, outside the venv.
    assert handle.venv_python.resolve() != handle.venv_python
    assert handle.requirements_file == handle.venv_dir / "requirements.txt"


def test_venv_handle_creates_the_directory(tmp_path: Path) -> None:
    """for_dir must mkdir, as set_venv_dir did.

    Behaviour under test: the side effect for_dir inherited.

    Concrete bug this catches: dropping the mkdir. `uv venv` needs the
    directory to exist and be empty; without the mkdir the requirements write
    that follows a successful build fails with FileNotFoundError instead.
    """
    target_dir = tmp_path / "does" / "not" / "exist" / "yet"

    handle = state.VenvHandle.for_dir(target_dir)

    assert handle.venv_dir.is_dir()


def test_venv_handle_is_frozen(tmp_path: Path) -> None:
    """The three paths are derived together and must move together.

    Behaviour under test: VenvHandle's immutability.

    Concrete bug this catches: a mutable VenvHandle would let a caller
    repoint venv_dir after a rename while venv_python still named the old
    path -- the exact drift set_venv_dir's three coupled writes existed to
    prevent, and the reason a rename produces a new handle rather than an
    edit.
    """
    handle = state.VenvHandle.for_dir(tmp_path / "v")

    with pytest.raises(dataclasses.FrozenInstanceError):
        handle.venv_dir = tmp_path / "other"  # type: ignore[misc]
