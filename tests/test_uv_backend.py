"""Pin how veny locates the uv binary it drives its environment layer with."""

import argparse
import dataclasses
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from veny import (
    alias_index,
    cache_search,
    cli,
    environment,
    pipeline,
    stdlib_index,
    verify,
)

from .test_state_values import a_requirements as _a_requirements
from .test_state_values import a_settings as _a_settings
from .test_state_values import a_target as _target


def test_the_packaged_uv_is_preferred_over_the_one_on_path(monkeypatch):
    """The uv installed alongside veny wins; PATH is never consulted."""
    fake = type(sys)("uv")
    fake.find_uv_bin = lambda: "/packaged/uv"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uv", fake)
    monkeypatch.setattr(shutil, "which", lambda _name: "/on/path/uv")
    environment.uv_binary.cache_clear()

    assert environment.uv_binary() == "/packaged/uv"


def test_a_path_uv_is_used_when_the_package_is_missing(monkeypatch, caplog):
    """Without the package, PATH serves -- and veny says the version is unpinned."""
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: "/on/path/uv")
    environment.uv_binary.cache_clear()

    assert environment.uv_binary() == "/on/path/uv"
    assert "not pinned" in caplog.text


def test_uv_binary_raises_a_veny_error_rather_than_exiting(monkeypatch):
    """With no uv anywhere, uv_binary raises UvUnavailable, not SystemExit.

    Behaviour under test: design amendment 4's resolution. Concrete bug this
    catches: SystemExit from a library module cannot be handled by a caller
    that wants to report and continue, and it bypasses cli.main's status
    mapping entirely -- the design's exit table is unenforceable while any
    module below cli can exit on its own. Expected message obtained from the
    current text, which must not change: users have it in their shell history.

    The failure names the command that fixes it, not just a traceback. uv_binary
    is functools.cache'd and this call raises, so nothing is memoized: the cache
    is left empty (the state cache_clear itself produces) for the tests after
    this one.
    """
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    environment.uv_binary.cache_clear()

    with pytest.raises(environment.UvUnavailable) as caught:
        environment.uv_binary()
    assert "uv tool install veny" in str(caught.value)


def test_create_venv_reports_failure_instead_of_raising(monkeypatch, tmp_path):
    """A uv that exits non-zero makes create_venv return False.

    Concrete bug this catches: letting CalledProcessError escape means a
    failed build reaches the user as a traceback, and setup_virtualenv's
    "Failed to create a virtual environment" path -- which exists and is
    tested -- is unreachable. Expected value obtained from the new contract:
    False means "no environment", the same shape run_uv_pip already uses.
    """
    monkeypatch.setattr(environment, "uv_binary", lambda: "/packaged/uv")

    def failing_check_call(command):
        raise subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(subprocess, "check_call", failing_check_call)

    assert environment.create_venv(tmp_path / "venv") is False


def test_create_venv_reports_success_when_uv_returns_zero(monkeypatch, tmp_path):
    """The success half of the same contract: a uv that exits 0 gives True.

    Concrete bug this catches: a create_venv that returned False (or None)
    unconditionally would satisfy the failure test above while making every
    build path report "Failed to create a virtual environment" -- both call
    sites now branch on this value, so the true answer has to be pinned too.
    """
    monkeypatch.setattr(environment, "uv_binary", lambda: "/packaged/uv")
    monkeypatch.setattr(subprocess, "check_call", lambda command: 0)

    assert environment.create_venv(tmp_path / "venv") is True


def test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt(
    monkeypatch, tmp_path
):
    """setup_virtualenv must not write requirements.txt into handle.venv_dir
    until create_venv has already built the environment there.

    VenvHandle.for_dir (called by setup_virtualenv before either
    write_requirements_file_with_extras or create_venv run) creates
    handle.venv_dir with mkdir(exist_ok=True), so create_venv always sees a
    directory that already exists. `uv venv` tolerates an existing directory
    only while it is empty -- it refuses (CalledProcessError) once anything
    has been written into it. If write_requirements_file_with_extras ran
    before create_venv, as it used to, the requirements.txt it writes would
    make that directory non-empty and this test's call into the real
    `create_venv` (real `uv venv` subprocess, not stubbed) would raise instead
    of returning, failing this test. Only the parts of setup_virtualenv that
    would need the network or a probed venv interpreter (the actual package
    install, import verification/repair, and manifest recording) are stubbed.
    """
    requirements = _a_requirements(
        uninstalled=frozenset(
            {cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")}
        )
    )
    monkeypatch.setattr(
        environment,
        "run_uv_pip",
        lambda venv_python, *args: subprocess.CompletedProcess(
            args=list(args), returncode=0
        ),
    )
    # verify_and_repair_imports now returns the final records instead of
    # writing them back onto options, so the no-op stub has to hand back what
    # it was given -- setup_virtualenv assigns the result.
    monkeypatch.setattr(
        verify,
        "verify_and_repair_imports",
        lambda *, uninstalled, **kwargs: frozenset(uninstalled),
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: True)
    # record_venv_state returns the (possibly renamed) venv directory now, and
    # setup_virtualenv feeds that return value straight to VenvHandle.for_dir.
    # A stub returning None would call for_dir(None) and mkdir a path built from
    # it, so the stub hands back the directory it was given.
    monkeypatch.setattr(
        cache_search, "record_venv_state", lambda venv_dir, **kwargs: venv_dir
    )

    settings = _a_settings(my_dir=tmp_path)
    target = _target()
    _, handle, _ = pipeline.setup_virtualenv(
        settings,
        target,
        requirements,
        args=argparse.Namespace(),
        aliases=alias_index.empty(tmp_path),
        stdlib=stdlib_index.for_running_interpreter(),
    )

    assert handle is not None
    assert (handle.venv_dir / "requirements.txt").read_text() == "thing-pkg\n"
    assert (handle.venv_dir / "bin" / "python").exists()


def test_setup_virtualenv_writes_the_extra_requirements_version_specifiers(
    monkeypatch, tmp_path
):
    """The specifiers parsed out of --reqs must reach the requirements.txt that
    setup_virtualenv writes, not just the argv `uv pip install -r` is given.

    Phase 3c task 2 turned an implicit `options.extra_requirements` read inside
    write_requirements_file_with_extras into an explicit argument at this call
    site, which created a mis-wiring nothing could see: task 5's differential
    pins `-r requirements.txt` in the uv argv but never that file's contents.

    Concrete bug this catches: pass `{}` (or any other mapping) instead of
    `options.extra_requirements` here and requirements.txt reads a bare
    `thing-pkg`. uv then resolves whatever the newest release is, silently
    discarding the `thing-pkg>=2.0` pin the user wrote in their requirements
    file -- the one thing --reqs exists to honour. The expected text comes from
    write_requirements_file_with_extras' contract (sorted pip names, one per
    line, a specifier appended only where extra_requirements supplies a
    non-empty one), not from re-running the writer.
    """
    requirements = _a_requirements(
        uninstalled=frozenset(
            {
                cli.ResolvedImport(import_name="thing", pip_name="thing-pkg"),
                cli.ResolvedImport(import_name="zeta", pip_name="zeta-pkg"),
            }
        ),
        extra_requirements={"thing-pkg": ">=2.0"},
    )
    # The venv itself is a subprocess boundary and is not what this test is
    # about; VenvHandle.for_dir has already created the directory the file lands in.
    monkeypatch.setattr(environment, "create_venv", lambda target, python="": True)
    monkeypatch.setattr(
        environment,
        "run_uv_pip",
        lambda venv_python, *args: subprocess.CompletedProcess(
            args=list(args), returncode=0
        ),
    )
    # verify_and_repair_imports now returns the final records instead of
    # writing them back onto options, so the no-op stub has to hand back what
    # it was given -- setup_virtualenv assigns the result.
    monkeypatch.setattr(
        verify,
        "verify_and_repair_imports",
        lambda *, uninstalled, **kwargs: frozenset(uninstalled),
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: True)
    # record_venv_state returns the (possibly renamed) venv directory now, and
    # setup_virtualenv feeds that return value straight to VenvHandle.for_dir.
    # A stub returning None would call for_dir(None) and mkdir a path built from
    # it, so the stub hands back the directory it was given.
    monkeypatch.setattr(
        cache_search, "record_venv_state", lambda venv_dir, **kwargs: venv_dir
    )

    settings = _a_settings(my_dir=tmp_path)
    target = _target()
    _, handle, _ = pipeline.setup_virtualenv(
        settings,
        target,
        requirements,
        args=argparse.Namespace(),
        aliases=alias_index.empty(tmp_path),
        stdlib=stdlib_index.for_running_interpreter(),
    )

    assert handle is not None
    assert (
        handle.venv_dir / "requirements.txt"
    ).read_text() == "thing-pkg>=2.0\nzeta-pkg\n"


def test_setup_virtualenv_reports_failure_when_uv_refuses_to_build(
    monkeypatch, tmp_path, caplog
):
    """A create_venv that returns False stops setup_virtualenv, which says so.

    Behaviour under test: the consuming half of phase 3e task 7's contract --
    create_venv reports rather than raises, which is only an improvement if
    its caller reads the report. Concrete bug this catches: leaving the call
    as a bare `environment.create_venv(...)` (its shape before this task)
    makes a refused build invisible. setup_virtualenv would carry on writing
    requirements.txt into a directory holding no environment, `uv pip install
    --python <venv>/bin/python` would fail against an interpreter that does
    not exist, and setup_virtualenv would still return True -- so
    pipeline.run's "Failed to create a virtual environment" path never runs
    and veny reports success for a run that built nothing. Expected values
    obtained from the new contract: False means "no environment", and the
    message names the directory so the user can see which build was refused.
    """
    settings, args, aliases, stdlib, target, requirements = _a_wired_run(tmp_path)
    _stub_the_venv_away(monkeypatch)
    monkeypatch.setattr(environment, "create_venv", lambda target, python="": False)

    with caplog.at_level(logging.ERROR):
        _, handle, _ = pipeline.setup_virtualenv(
            settings,
            target,
            requirements,
            args=args,
            aliases=aliases,
            stdlib=stdlib,
        )

    # No handle at all: there is no usable environment, which is what
    # setup_virtualenv returning False used to mean.
    assert handle is None
    # The refused directory is named in the message, and is where the
    # requirements file would have landed. The handle is gone, so the path is
    # rebuilt from what for_dir was given.
    refused = tmp_path / "failed-wiredenv-py3.12-20260101-010203-thing-pkg"
    assert f"uv could not create the virtual environment at {refused}." in caplog.text
    # The early return has to happen *before* the requirements file is written:
    # writing it would leave a directory that looks like a half-built venv.
    assert not (refused / "requirements.txt").exists()


def test_create_venv_is_given_a_resolved_interpreter_path_not_a_bare_command(
    monkeypatch, tmp_path
):
    """venv_build_interpreter's result, as create_venv passes it to uv, must be
    an absolute path -- never a bare command name like "python3".

    `uv venv --python python3` does not mean "the python3 on PATH": uv treats a
    bare name as a request and resolves it through its own interpreter
    discovery order, which was measured (with no veny involved) to pick a
    different Python (3.12) than the one `python3 -m venv` -- what veny did
    before the uv migration -- used to build with (3.13). That silently builds
    the venv against a different interpreter than the one imports were
    classified against. If venv_build_interpreter regressed to returning
    the target's python_command unresolved, this test would see the bare "python3"
    in the captured uv command instead of the absolute path shutil.which
    resolves it to.
    """
    target = _target(python_command="python3")
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/resolved/bin/python3" if name == "python3" else None,
    )
    monkeypatch.setattr(environment, "uv_binary", lambda: "/packaged/uv")
    captured: list[list[str]] = []
    monkeypatch.setattr(
        subprocess, "check_call", lambda command: captured.append(command)
    )

    python = environment.venv_build_interpreter(target.python_command)
    environment.create_venv(tmp_path / "target", python)

    assert captured == [
        [
            "/packaged/uv",
            "venv",
            str(tmp_path / "target"),
            "--python",
            "/resolved/bin/python3",
        ]
    ]


def _a_wired_run(tmp_path):
    """Build the Settings, args, aliases, stdlib index and Target whose every setup_virtualenv argument is distinguishable.

    Each field carries a value no other field could supply -- a venv name, a
    timestamp, an interpreter tag, a pip name, an import name and a --reqs
    spelling that are all different strings -- so a call site that reaches for
    the wrong one cannot produce the expected result by coincidence.

    Returns:
        The Settings, the args, the aliases, the stdlib index, the Target and
        the Requirements, in that order.
    """
    settings = _a_settings(my_dir=tmp_path, venv_name="wiredenv", rawlog=True)
    target = _target(
        timestamp="20260101-010203",
        python_command="python-under-test-not-on-path",
    )
    stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )
    requirements = _a_requirements(
        uninstalled=frozenset(
            {cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")}
        ),
        all_imports=frozenset({"thing", "extra-pkg"}),
        extra_requirements={"extra-pkg": ">=2.0"},
    )
    args = argparse.Namespace(reqs=True)
    aliases = alias_index.AliasIndex(
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
    return settings, args, aliases, stdlib, target, requirements


def _stub_the_venv_away(monkeypatch, uninstalled_after_repair=None):
    """Stub every subprocess-backed step of setup_virtualenv, returning the spies."""
    created: list[tuple[object, str]] = []

    def fake_create_venv(target: object, python: str = "") -> bool:
        """Record the build request and report the success uv would report."""
        created.append((target, python))
        return True

    monkeypatch.setattr(environment, "create_venv", fake_create_venv)
    monkeypatch.setattr(
        environment,
        "run_uv_pip",
        lambda venv_python, *args: subprocess.CompletedProcess(
            args=list(args), returncode=0
        ),
    )
    monkeypatch.setattr(
        verify,
        "verify_and_repair_imports",
        lambda *, uninstalled, **kwargs: frozenset(
            uninstalled
            if uninstalled_after_repair is None
            else uninstalled_after_repair
        ),
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: True)
    monkeypatch.setattr(
        cache_search, "record_venv_state", lambda venv_dir, **kwargs: venv_dir
    )
    return created


def test_the_venv_folder_name_and_build_interpreter_come_from_this_run(
    monkeypatch, tmp_path
):
    """The cache prefilter name and the building interpreter are built from this run's own fields.

    Measured by substitution, all five of these left the whole suite green:
    `interpreter_tag=""` and a hardcoded run_tag at build_folder_name,
    `venv_name`/`timestamp` replaced by literals, `pip_names=[]`, and
    `venv_build_interpreter("")` at create_venv. Concrete bugs this catches:
    a folder name that does not list the packages the venv holds is a
    prefilter that rejects the venv on the next run (a silent rebuild every
    time), and an empty python_command makes uv build against the interpreter
    running veny rather than the one imports were classified against -- the
    exact defect PROGRESS records from phase 2 task 9, where a script
    importing `cgi` was classified installed under 3.12 and died under 3.13.
    """
    settings, args, aliases, stdlib, target, requirements = _a_wired_run(tmp_path)
    created = _stub_the_venv_away(monkeypatch)

    _, handle, _ = pipeline.setup_virtualenv(
        settings,
        target,
        requirements,
        args=args,
        aliases=aliases,
        stdlib=stdlib,
    )

    assert handle is not None
    assert handle.venv_dir.name == "failed-wiredenv-py3.12-20260101-010203-thing-pkg"
    assert created == [
        (handle.venv_dir, environment.venv_build_interpreter(target.python_command))
    ]
    # Not sys.executable: an empty python_command would silently resolve to it.
    assert created[0][1] == "python-under-test-not-on-path"


def test_verify_and_repair_imports_is_handed_the_whole_description_of_the_run(
    monkeypatch, tmp_path
):
    """Every one of the seven arguments must come from this run, not a default.

    Measured by substitution: six of the seven (all but `index`) could be
    replaced with an empty/wrong value and all 338 tests stayed green. This
    is the call that decides which imports get repaired and what
    requirements.txt is rewritten to, so `uninstalled=frozenset()` skips
    repair entirely and reports success on a venv that cannot import what the
    script needs, and `source_names=frozenset()` makes the bulk check
    fail-open on the distribution's whole top-level name list (the shape
    PROGRESS records under "a check that widens what counts as a pass").

    source_names is asserted to be `{"thing"}`: `extra-pkg` is in all_imports
    but is a --reqs pip spelling, so source_import_names must drop it. That
    pins the three arguments of the source_import_names call too.
    """
    settings, args, aliases, stdlib, target, requirements = _a_wired_run(tmp_path)
    _stub_the_venv_away(monkeypatch)
    seen: list[dict[str, object]] = []

    def spy(**kwargs):
        seen.append(kwargs)
        return frozenset(kwargs["uninstalled"])

    monkeypatch.setattr(verify, "verify_and_repair_imports", spy)

    assert (
        pipeline.setup_virtualenv(
            settings,
            target,
            requirements,
            args=args,
            aliases=aliases,
            stdlib=stdlib,
        )[1]
        is not None
    )

    # Literal paths, not handle.venv_python / options.requirements_file:
    # setup_virtualenv derives those two paths itself (via VenvHandle.for_dir), so
    # asserting against them would compare the call site to its own output and
    # pass however the folder name was built.
    built = tmp_path / "failed-wiredenv-py3.12-20260101-010203-thing-pkg"
    assert len(seen) == 1
    assert seen[0] == {
        "venv_python": built / "bin" / "python",
        "requirements_file": built / "requirements.txt",
        "uninstalled": {cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")},
        "extra_requirements": {"extra-pkg": ">=2.0"},
        "source_names": {"thing"},
        "index": aliases,
        "rawlog": True,
    }


def test_the_manifest_and_the_final_check_describe_the_venv_after_repair(
    monkeypatch, tmp_path
):
    """record_venv_state, the final import check and uv all get the repaired state.

    verify_and_repair_imports can replace a record whose pip name was wrong,
    and setup_virtualenv folds its result back into the Requirements it
    returns, with dataclasses.replace. Everything after it -- the manifest, the
    folder-name refresh inside record_venv_state, and the check that decides
    whether this venv drops its "failed-" prefix -- must therefore describe
    the repaired set, not the set the install was attempted with.

    Measured by substitution: eight of record_venv_state's nine arguments and
    all three of the final check's could be emptied with all 338 tests green.
    Concrete bug this catches: `uninstalled=frozenset()` at record_venv_state
    writes a manifest listing no packages, so the next run reads that
    manifest, finds nothing it needs, and rebuilds the environment from
    scratch every single time.
    """
    settings, args, aliases, stdlib, target, requirements = _a_wired_run(tmp_path)
    repaired = {cli.ResolvedImport(import_name="thing", pip_name="repaired-pkg")}
    _stub_the_venv_away(monkeypatch, uninstalled_after_repair=repaired)
    recorded: list[dict[str, object]] = []
    checked: list[dict[str, object]] = []
    uv_calls: list[tuple[object, tuple[str, ...]]] = []

    def uv_spy(venv_python, *args):
        uv_calls.append((venv_python, args))
        return subprocess.CompletedProcess(args=list(args), returncode=0)

    monkeypatch.setattr(environment, "run_uv_pip", uv_spy)

    def record_spy(venv_dir, **kwargs):
        recorded.append({"venv_dir": venv_dir, **kwargs})
        return venv_dir

    def check_spy(venv_python, **kwargs):
        checked.append({"venv_python": venv_python, **kwargs})
        return True

    monkeypatch.setattr(cache_search, "record_venv_state", record_spy)
    monkeypatch.setattr(verify, "check_packages_in_venv", check_spy)

    assert (
        pipeline.setup_virtualenv(
            settings,
            target,
            requirements,
            args=args,
            aliases=aliases,
            stdlib=stdlib,
        )[1]
        is not None
    )

    # Literal paths, not handle.venv_dir / handle.venv_python, for the same
    # reason the sibling test above spells them out: record_spy echoes its
    # venv_dir argument back and setup_virtualenv assigns that echo to
    # handle.venv_dir (via VenvHandle.for_dir), so asserting against options.* here
    # would compare the call site to its own output and pass however the
    # folder name was built. Measured: a wrong `timestamp=` at
    # setup_virtualenv's build_folder_name left this test green before this
    # was spelled out.
    built = tmp_path / "failed-wiredenv-py3.12-20260101-010203-thing-pkg"
    assert uv_calls == [
        (
            built / "bin" / "python",
            ("install", "-r", os.fspath(built / "requirements.txt")),
        )
    ]
    assert recorded == [
        {
            "venv_dir": built,
            "venv_python": built / "bin" / "python",
            "venv_name": "wiredenv",
            "timestamp": "20260101-010203",
            "run_tag": "3.12",
            "python_command": "python-under-test-not-on-path",
            "uninstalled": repaired,
            "extra_requirements": {"extra-pkg": ">=2.0"},
            "rawlog": True,
        }
    ]
    assert checked == [
        {
            "venv_python": built / "bin" / "python",
            "uninstalled": repaired,
            "source_names": {"thing"},
        }
    ]


def _a_repair_that_succeeds(monkeypatch):
    """Wire setup_virtualenv so the real repair pass runs and finds a winner.

    Only the subprocess boundaries are replaced: the bulk import check fails
    (so the per-record repair branch is entered), the venv's metadata knows
    nothing (so the failed candidate is treated as never installed), the
    per-record import check fails, and the ranked search hands back a winner.
    verify_and_repair_imports and repair_unsatisfied_import themselves --
    including the line that names the winner -- are the real ones.
    """
    monkeypatch.setattr(environment, "create_venv", lambda target, python="": True)
    monkeypatch.setattr(
        environment,
        "run_uv_pip",
        lambda venv_python, *args: subprocess.CompletedProcess(
            args=list(args), returncode=0
        ),
    )
    monkeypatch.setattr(
        cache_search, "record_venv_state", lambda venv_dir, **kwargs: venv_dir
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: False)
    monkeypatch.setattr(alias_index, "probe_interpreter", lambda venv_python: ({}, {}))
    monkeypatch.setattr(
        verify,
        "import_outcome_in_venv",
        lambda venv_python, import_name: verify.ImportOutcome(
            imported=False,
            rejection_kind="import_failed",
            detail="No module named thing",
            providers=frozenset(),
        ),
    )
    monkeypatch.setattr(
        verify,
        "resolve_and_verify",
        lambda resolution, index, **kwargs: alias_index.Candidate(
            pip_name="repaired-pkg",
            source=alias_index.Source.SEED,
            evidence="the seed named it",
        ),
    )


def test_setup_virtualenv_lets_the_repair_pass_name_the_package_it_settled_on(
    monkeypatch, tmp_path, caplog
):
    """setup_virtualenv must carry this run's rawlog into verify_and_repair_imports.

    Behaviour under test: the fourth of phase 3d's five open `rawlog` holes,
    which moved from cli.py into pipeline.setup_virtualenv. 3d left it open
    because the line rawlog controls fires only when a repair happens, and
    every existing setup_virtualenv driver stubs the repair pass out and then
    asserts the `rawlog` value the stub was handed -- which a hardcoded
    `rawlog=True` supplies for free. This drives the real pass and reads the
    record instead.

    Concrete bug this catches: `rawlog=True` hardcoded at this call site
    silences the only line telling the user that the package veny installed
    was not the one that provided their import. The substitution happens
    anyway; the requirements.txt in the venv changes underneath them; and the
    sole surviving trace is an entry in the alias cache they never see.
    Expected message obtained from repair_unsatisfied_import's contract:
    "<pip name> provides the import <import name> (<evidence>)".
    """
    settings, args, aliases, stdlib, target, requirements = _a_wired_run(tmp_path)
    settings = dataclasses.replace(settings, rawlog=False)
    _a_repair_that_succeeds(monkeypatch)

    with caplog.at_level(logging.INFO):
        _, handle, _ = pipeline.setup_virtualenv(
            settings,
            target,
            requirements,
            args=args,
            aliases=aliases,
            stdlib=stdlib,
        )

    assert "repaired-pkg provides the import thing (the seed named it)" in caplog.text

    # The other direction: a --rawlog run must stay quiet, so a hardcoded
    # rawlog=False at this call site dies too.
    caplog.clear()
    quiet_settings, quiet_args, quiet_aliases, quiet_stdlib, target, requirements = (
        _a_wired_run(tmp_path)
    )
    quiet_settings = dataclasses.replace(quiet_settings, rawlog=True)
    _a_repair_that_succeeds(monkeypatch)

    with caplog.at_level(logging.INFO):
        _, handle, _ = pipeline.setup_virtualenv(
            quiet_settings,
            target,
            requirements,
            args=quiet_args,
            aliases=quiet_aliases,
            stdlib=quiet_stdlib,
        )

    assert "provides the import" not in caplog.text


def _a_manifest_pass_that_renames(monkeypatch, tmp_path, repaired):
    """Wire setup_virtualenv so the real record_venv_state runs and renames.

    The repair replaces the pip name the folder was named after, so the name
    record_venv_state computes no longer matches the folder on disk and the
    rename branch -- the one carrying the rawlog-guarded line -- is taken.
    Only the venv probe is replaced; record_venv_state, rename_venv and the
    manifest write are the real ones, against a real directory.
    """
    monkeypatch.setattr(environment, "create_venv", lambda target, python="": True)
    monkeypatch.setattr(
        environment,
        "run_uv_pip",
        lambda venv_python, *args: subprocess.CompletedProcess(
            args=list(args), returncode=0
        ),
    )
    monkeypatch.setattr(
        verify,
        "verify_and_repair_imports",
        lambda **kwargs: frozenset(repaired),
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: True)
    monkeypatch.setattr(
        cache_search, "installed_state_in_venv", lambda venv_python: ({}, "3.12")
    )


def test_setup_virtualenv_lets_the_manifest_pass_explain_a_rename(
    monkeypatch, tmp_path, caplog
):
    """setup_virtualenv must carry this run's rawlog into record_venv_state.

    Behaviour under test: the fifth of phase 3d's five open `rawlog` holes,
    which moved from cli.py into pipeline.setup_virtualenv. 3d left it open
    because the line rawlog controls fires only when the venv's folder name
    has drifted from what its contents warrant, and every existing driver
    stubs record_venv_state out. Here the repair pass returns a record with a
    different pip name, which is exactly what makes the folder name drift, so
    the real record_venv_state takes its rename branch.

    Concrete bug this catches: `rawlog=True` hardcoded at this call site
    silences the only notice that veny renamed the directory the user's
    environment lives in. The folder they were told about a moment earlier no
    longer exists under that name, and nothing on a normal run says so.
    Expected message obtained from record_venv_state's contract: it names the
    folder it is renaming to.
    """
    repaired = {cli.ResolvedImport(import_name="thing", pip_name="repaired-pkg")}
    settings, args, aliases, stdlib, target, requirements = _a_wired_run(
        tmp_path / "normal"
    )
    settings = dataclasses.replace(settings, rawlog=False)
    _a_manifest_pass_that_renames(monkeypatch, tmp_path, repaired)

    with caplog.at_level(logging.INFO):
        _, handle, _ = pipeline.setup_virtualenv(
            settings,
            target,
            requirements,
            args=args,
            aliases=aliases,
            stdlib=stdlib,
        )

    assert (
        "renaming it to failed-wiredenv-py3.12-20260101-010203-repaired-pkg"
        in caplog.text
    )

    # The other direction: --rawlog must reach it, so a hardcoded rawlog=False
    # at this call site dies too.
    caplog.clear()
    quiet_settings, quiet_args, quiet_aliases, quiet_stdlib, target, requirements = (
        _a_wired_run(tmp_path / "raw")
    )
    quiet_settings = dataclasses.replace(quiet_settings, rawlog=True)
    _a_manifest_pass_that_renames(monkeypatch, tmp_path, repaired)

    with caplog.at_level(logging.INFO):
        _, handle, _ = pipeline.setup_virtualenv(
            quiet_settings,
            target,
            requirements,
            args=quiet_args,
            aliases=quiet_aliases,
            stdlib=quiet_stdlib,
        )

    assert "renaming it to" not in caplog.text
