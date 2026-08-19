"""Pin how veny locates the uv binary it drives its environment layer with."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from veny import alias_index, cache_search, cli, environment, stdlib_index, verify


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


def test_no_uv_anywhere_exits_with_an_install_message(monkeypatch):
    """The failure names the command that fixes it, not just a traceback."""
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    environment.uv_binary.cache_clear()

    with pytest.raises(SystemExit) as caught:
        environment.uv_binary()
    assert "uv tool install veny" in str(caught.value)


def test_setup_virtualenv_builds_the_venv_before_writing_requirements_txt(
    monkeypatch, tmp_path
):
    """setup_virtualenv must not write requirements.txt into options.venv_dir
    until create_venv has already built the environment there.

    Options.set_venv_dir (called by setup_virtualenv before either
    write_requirements_file_with_extras or create_venv run) creates
    options.venv_dir with mkdir(exist_ok=True), so create_venv always sees a
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
    options = cli.Options()
    options.my_dir = tmp_path
    options.uninstalled_imports = {
        cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")
    }
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
    # setup_virtualenv feeds that return value straight to options.set_venv_dir.
    # A stub returning None would set_venv_dir(None) and mkdir a path built from
    # it, so the stub hands back the directory it was given.
    monkeypatch.setattr(
        cache_search, "record_venv_state", lambda venv_dir, **kwargs: venv_dir
    )

    assert cli.setup_virtualenv(options) is True

    assert options.venv_dir is not None
    assert (options.venv_dir / "requirements.txt").read_text() == "thing-pkg\n"
    assert (options.venv_dir / "bin" / "python").exists()


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
    options = cli.Options()
    options.my_dir = tmp_path
    options.uninstalled_imports = {
        cli.ResolvedImport(import_name="thing", pip_name="thing-pkg"),
        cli.ResolvedImport(import_name="zeta", pip_name="zeta-pkg"),
    }
    options.extra_requirements = {"thing-pkg": ">=2.0"}
    # The venv itself is a subprocess boundary and is not what this test is
    # about; set_venv_dir has already created the directory the file lands in.
    monkeypatch.setattr(environment, "create_venv", lambda target, python="": None)
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
    # setup_virtualenv feeds that return value straight to options.set_venv_dir.
    # A stub returning None would set_venv_dir(None) and mkdir a path built from
    # it, so the stub hands back the directory it was given.
    monkeypatch.setattr(
        cache_search, "record_venv_state", lambda venv_dir, **kwargs: venv_dir
    )

    cli.setup_virtualenv(options)

    assert options.venv_dir is not None
    assert (
        options.venv_dir / "requirements.txt"
    ).read_text() == "thing-pkg>=2.0\nzeta-pkg\n"


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
    options.python_command unresolved, this test would see the bare "python3"
    in the captured uv command instead of the absolute path shutil.which
    resolves it to.
    """
    options = cli.Options()
    options.python_command = "python3"
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

    python = environment.venv_build_interpreter(options.python_command)
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
    """Build an Options whose every setup_virtualenv argument is distinguishable.

    Each field carries a value no other field could supply -- a venv name, a
    timestamp, an interpreter tag, a pip name, an import name and a --reqs
    spelling that are all different strings -- so a call site that reaches for
    the wrong one cannot produce the expected result by coincidence.
    """
    options = cli.Options()
    options.my_dir = tmp_path
    options.venv_name = "wiredenv"
    options.timestamp = "20260101-010203"
    options.python_command = "python-under-test-not-on-path"
    options.stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )
    options.uninstalled_imports = {
        cli.ResolvedImport(import_name="thing", pip_name="thing-pkg")
    }
    options.all_imports = {"thing", "extra-pkg"}
    options.extra_requirements = {"extra-pkg": ">=2.0"}
    options.args = argparse.Namespace(reqs=True)
    options.rawlog = True
    options.aliases = alias_index.AliasIndex(
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
    return options


def _stub_the_venv_away(monkeypatch, uninstalled_after_repair=None):
    """Stub every subprocess-backed step of setup_virtualenv, returning the spies."""
    created: list[tuple[object, str]] = []
    monkeypatch.setattr(
        environment,
        "create_venv",
        lambda target, python="": created.append((target, python)),
    )
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
    options = _a_wired_run(tmp_path)
    created = _stub_the_venv_away(monkeypatch)

    assert cli.setup_virtualenv(options) is True

    assert options.venv_dir is not None
    assert options.venv_dir.name == "failed-wiredenv-py3.12-20260101-010203-thing-pkg"
    assert created == [
        (options.venv_dir, environment.venv_build_interpreter(options.python_command))
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
    options = _a_wired_run(tmp_path)
    _stub_the_venv_away(monkeypatch)
    seen: list[dict[str, object]] = []

    def spy(**kwargs):
        seen.append(kwargs)
        return frozenset(kwargs["uninstalled"])

    monkeypatch.setattr(verify, "verify_and_repair_imports", spy)

    assert cli.setup_virtualenv(options) is True

    # Literal paths, not options.venv_python / options.requirements_file:
    # setup_virtualenv writes those two fields itself (via set_venv_dir), so
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
        "index": options.aliases,
        "rawlog": True,
    }


def test_the_manifest_and_the_final_check_describe_the_venv_after_repair(
    monkeypatch, tmp_path
):
    """record_venv_state, the final import check and uv all get the repaired state.

    verify_and_repair_imports can replace a record whose pip name was wrong,
    and setup_virtualenv assigns its result back onto
    options.uninstalled_imports. Everything after it -- the manifest, the
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
    options = _a_wired_run(tmp_path)
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

    assert cli.setup_virtualenv(options) is True

    # Literal paths, not options.venv_dir / options.venv_python, for the same
    # reason the sibling test above spells them out: record_spy echoes its
    # venv_dir argument back and setup_virtualenv assigns that echo to
    # options.venv_dir (via set_venv_dir), so asserting against options.* here
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
