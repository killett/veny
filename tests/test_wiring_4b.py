"""Pin the arguments phase 4b's call sites carry, at the sites themselves.

Phase 4b replaced emmykit's options-JSON persistence with veny's own
``LastUsed`` record: one writer (``last_used.save``, at the end of
``pipeline.run``) and two readers (``pipeline.feeling_lucky`` for the
``--feeling-lucky`` shortcut, and the loader injected into
``cache_search.find_match_dir_in_cache``). The STANDING CHECK
(``scripts/wiring_sweep_4b.py``) measured every argument at every one of
those sites by substitution; the holes it found are closed here.

Two properties the rest of the suite cannot see, and which these tests exist
for:

* **Identity, not equality.** The record a run saves must be built from the
  handle that run actually used. Two freshly built values that happen to be
  equal prove nothing -- "a fresh one of the same type" is exactly the
  substitution these rows failed under.
* **Writer and readers agreeing with each other.** Each side has its own
  tests and each passes them while the pair is broken, because nothing else
  compares the filename ``save`` writes against the filename ``load`` reads.

The two record tests this phase's Task 2 wrote live in
``tests/test_wiring_4a.py`` next to the 4a rows they also cover
(``test_the_saved_record_carries_the_venv_the_run_actually_used`` and
``test_the_saved_record_names_the_post_rename_venv_dir``); the wiring index
cites them there rather than duplicating them here.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import emmykit as ek
import pytest

from veny import alias_index, cache_search, cli, last_used, pipeline, state
from veny.analysis import custom_modules

_REQUIREMENTS = state.Requirements(
    all_imports=frozenset({"thing"}),
    bad=frozenset(),
    installed=frozenset(),
    uninstalled=frozenset({alias_index.ResolvedImport("thing", "thing-pkg")}),
    seen_stdlib=frozenset(),
    extra_requirements={},
)


def _stub_boundaries(monkeypatch: pytest.MonkeyPatch, home: Path) -> list[list[str]]:
    """Stub every subprocess, clock and emmykit boundary a run crosses.

    Deliberately does NOT stub ``last_used``: the record is what these tests
    measure, so it is written and read for real, on disk.

    Args:
        monkeypatch: pytest's patcher.
        home: The directory to use as ``$HOME``, so ``my_dir`` lands there.

    Returns:
        The list every launched command is appended to, as a list of strings.
    """
    launched: list[list[str]] = []

    def record_run(command, *args, **kwargs):
        launched.append([os.fspath(part) for part in command])
        return subprocess.CompletedProcess(args=command, returncode=0)

    monkeypatch.setenv("HOME", os.fspath(home))
    monkeypatch.setattr(ek, "find_preferred_python_version", lambda: "python3")
    monkeypatch.setattr(ek, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(ek, "print_all_errors", lambda *a, **k: None)
    monkeypatch.setattr(logging, "shutdown", lambda: None)
    monkeypatch.setattr(subprocess, "run", record_run)
    monkeypatch.setattr(
        custom_modules, "dict_of_custom_modules", lambda settings, **kwargs: {}
    )
    monkeypatch.setattr(
        pipeline,
        "list_packages",
        lambda settings, scan, target, **kwargs: (scan, _REQUIREMENTS),
    )
    return launched


def _a_venv(venv_dir: Path) -> Path:
    """Create a directory that looks enough like a venv to be launched.

    ``last_used.load_venv_python`` refuses a recorded interpreter that is not
    a file on disk, so a test that wants the lucky path to fire has to put
    one there.

    Args:
        venv_dir: Where the environment lives.

    Returns:
        The interpreter inside it.
    """
    interpreter = venv_dir / "bin" / "python"
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.write_text("#!/bin/sh\n")
    interpreter.chmod(0o755)
    return interpreter


def test_the_saved_record_names_the_folder_the_run_ended_with(monkeypatch, tmp_path):
    """On a cache hit the record must name the folder the search handed back.

    Behaviour under test: ``last_used.save``'s ``LastUsed`` is built from the
    ``handle`` the run finished with, whichever branch produced it. The
    cache-hit branch rebinds ``handle`` from the cache search's answer, and
    no other test reads the record after a hit.

    Concrete bug this catches: building the record from anything other than
    the final handle -- the venv name the run *would* have built, or a handle
    captured before the branch rebinds it. The next run's pointer then names
    a directory this run never used (and, on the sibling rename path, one
    that no longer exists), and the failure is a silent cache miss rather
    than an error: every later run rebuilds from scratch and nothing says why.
    The rename half of the same property is pinned by
    ``test_wiring_4a::test_the_saved_record_names_the_post_rename_venv_dir``.

    How the expected value was determined: the cached directory is created by
    this test and handed back by the stubbed search, so it is the object the
    run consumed. The record read off disk is compared against *that* object,
    not against a path this test rebuilds by repeating pipeline's naming
    rules -- which is what makes the assertion an identity assertion.
    """
    home = tmp_path / "home"
    home.mkdir()
    script = tmp_path / "script.py"
    script.write_text("import thing\n")
    cached = home / "veny" / "myenv-py3.12-20200101-000000-thing-pkg"
    _a_venv(cached)
    would_have_built = home / "veny" / "myenv"
    launched = _stub_boundaries(monkeypatch, home)
    monkeypatch.setattr(sys, "argv", ["veny", "--rawlog", os.fspath(script)])
    handed_back: list[Path] = []
    targets: list[state.Target] = []

    def search_spy(args, **kwargs):
        handed_back.append(cached)
        return cached

    def setup_spy(settings, target, requirements, **kwargs):
        raise AssertionError("the cache hit must not reach setup_virtualenv")

    def capture_target(settings, scan, target, **kwargs):
        targets.append(target)
        return scan, _REQUIREMENTS

    monkeypatch.setattr(pipeline, "list_packages", capture_target)
    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", search_spy)
    monkeypatch.setattr(pipeline, "setup_virtualenv", setup_spy)

    assert cli.main() == 0

    record = last_used.load(
        script_dir=targets[0].script_dir,
        python_script=targets[0].python_script,
        my_name="veny",
        rawlog=True,
    )
    assert record is not None
    # The folder the search returned, not the one a fresh build would name.
    assert record.venv_dir == handed_back[0]
    assert record.venv_dir != would_have_built
    assert record.venv_python == handed_back[0] / "bin" / "python"
    # The stamp is the one this run's Target carries, not a fresh clock read:
    # it is the only thing in the record that says which run wrote it.
    assert record.timestamp == targets[0].timestamp
    # ...and it is the interpreter the run actually launched the script with.
    # The last command is the script launch; earlier ones are the alias
    # index's probe of the build interpreter.
    assert launched[-1] == [
        os.fspath(record.venv_python),
        os.fspath(script.resolve()),
    ]


def test_the_cache_search_is_handed_the_record_for_this_script(monkeypatch, tmp_path):
    """The injected loader must read the record beside the script, not the cwd's.

    Behaviour under test: the whole chain from ``pipeline.run``'s lambda
    through ``_load_last_used`` and ``last_used.load`` to the filename
    ``last_used.record_path`` spells -- exercised by calling the callable the
    run handed ``find_match_dir_in_cache`` and reading what it returns.

    Concrete bug this catches: deriving the reader's ``script_dir`` or
    ``python_script`` from the working directory (``settings.cwd``) rather
    than from the target. A script run from another directory then never
    finds its own record, so the last-used pass silently never wins and every
    such run falls through to "latest". A decoy record sits in the working
    directory, so that bug returns the *wrong* environment rather than None
    -- an assertion on "not None" would not see it.

    How the expected value was determined: both records are written here by
    ``last_used.save`` with paths chosen by hand, and the run is driven from a
    third directory that holds neither. The loader's answer is compared
    against the one written beside the script.
    """
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    script = project / "script.py"
    script.write_text("import thing\n")
    beside_the_script = home / "veny" / "the-right-one"
    in_the_cwd = home / "veny" / "the-decoy"
    for folder in (beside_the_script, in_the_cwd):
        _a_venv(folder)
    last_used.save(
        state.LastUsed(
            venv_dir=beside_the_script,
            venv_python=beside_the_script / "bin" / "python",
            timestamp="20200101-000000",
        ),
        script_dir=project,
        python_script=script,
        my_name="veny",
    )
    # The same script name, recorded in the directory veny is *run* from.
    last_used.save(
        state.LastUsed(
            venv_dir=in_the_cwd,
            venv_python=in_the_cwd / "bin" / "python",
            timestamp="20200101-000000",
        ),
        script_dir=workdir,
        python_script=workdir / "script.py",
        my_name="veny",
    )
    _stub_boundaries(monkeypatch, home)
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(sys, "argv", ["veny", "--rawlog", os.fspath(script)])
    loaders: list[Any] = []

    def search_spy(args, *, load_last_used, **kwargs):
        loaders.append(load_last_used)
        return None

    monkeypatch.setattr(cache_search, "find_match_dir_in_cache", search_spy)
    monkeypatch.setattr(
        pipeline,
        "setup_virtualenv",
        lambda settings, target, requirements, **kwargs: (requirements, None, False),
    )

    cli.main()

    assert len(loaders) == 1
    record = loaders[0]()
    assert record is not None
    assert record.venv_dir == beside_the_script
    assert record.venv_python == beside_the_script / "bin" / "python"
    # Not the decoy: a reader built from the cwd would find that one and
    # hand the run an environment belonging to a different script.
    assert record.venv_dir != in_the_cwd


def test_feeling_lucky_reads_the_same_record_the_run_writes(monkeypatch, tmp_path):
    """The writer and the lucky reader must agree, end to end, on one file.

    Behaviour under test: ``last_used.save`` at the end of ``pipeline.run``
    and ``last_used.load_venv_python`` at the top of ``pipeline.feeling_lucky``
    naming the same file for the same script -- measured by driving one
    ordinary run and then a second, lucky one against the same script.

    Concrete bug this catches: the writer and the reader disagreeing about
    the record's filename -- one spelling it with ``my_name`` and the other
    without, or one taking the script's directory and the other its full
    path. Each side keeps passing its own tests, because each side's tests
    call ``record_path`` for both halves; nothing else in the suite writes
    with one and reads with the other. The user-visible failure is that
    ``--feeling-lucky`` never once succeeds, on any script, and silently
    falls through to a full analysis run.

    How the expected value was determined: the interpreter asserted on is the
    one the *first* run's handle carried, captured from the spy that built
    it -- not a path this test spells out a second time. That is what makes
    it an identity assertion rather than an equality between two values the
    test constructed.
    """
    home = tmp_path / "home"
    home.mkdir()
    script = tmp_path / "script.py"
    script.write_text("import thing\n")
    built = home / "veny" / "myenv-py3.12-20200101-000000-thing-pkg"
    launched = _stub_boundaries(monkeypatch, home)
    monkeypatch.setattr(
        sys, "argv", ["veny", "--rawlog", "--no-cache", os.fspath(script)]
    )
    handles: list[state.VenvHandle] = []

    def setup_spy(settings, target, requirements, **kwargs):
        _a_venv(built)
        handle = state.VenvHandle.for_dir(built)
        handles.append(handle)
        return requirements, handle, True

    monkeypatch.setattr(pipeline, "setup_virtualenv", setup_spy)

    assert cli.main() == 0
    assert len(handles) == 1

    # Second run: same script, --feeling-lucky. Nothing below
    # feeling_lucky may be reached -- if the reader misses the record, the
    # run falls through to a full analysis, and this is what says so.
    def forbidden(*args, **kwargs):
        raise AssertionError("the lucky run must not reach pipeline.run")

    monkeypatch.setattr(pipeline, "run", forbidden)
    monkeypatch.setattr(
        sys, "argv", ["veny", "--rawlog", "--feeling-lucky", os.fspath(script)]
    )
    launched.clear()

    assert cli.main() == 0

    # The interpreter the first run recorded, by identity with the handle
    # that run built -- not a path spelled out again here.
    assert launched == [
        [os.fspath(handles[0].venv_python), os.fspath(script.resolve())]
    ]


# --- The diagnostics a degraded record produces -------------------------
#
# Every one of these paths already returns None, and
# tests/test_last_used.py pins that. What the sweep found open is the
# *explanation*: the message text and the filename it names. Without them a
# record veny silently ignores is indistinguishable from no record at all,
# and the user's --feeling-lucky simply stops working with nothing to read.


@pytest.mark.parametrize(
    ("payload", "complaint"),
    [
        ("[1, 2]", "is not an object"),
        (json.dumps({"timestamp": "20200101-000000"}), "names no environment"),
        (json.dumps({"venv_dir": "", "venv_python": ""}), "names an empty path"),
    ],
    ids=["not-an-object", "no-environment", "empty-path"],
)
def test_a_degraded_record_says_what_is_wrong_and_names_the_file(
    tmp_path, caplog, payload, complaint
):
    """Each degraded shape logs its own complaint, naming the record's path.

    Behaviour under test: the three ``logging.info`` calls in
    ``last_used.load`` between "read the file" and "return None".

    Concrete bug this catches: the three messages collapsed into one (or
    interpolating the script rather than the record), so a user whose record
    is a leftover from a hand-edit cannot tell which file to delete. All
    three shapes return None either way, which is why the existing
    ``test_a_damaged_record_is_none_and_not_a_crash`` cannot see this.

    How the expected value was determined: the complaint strings are read off
    the three branches' contracts (each names a different defect), and the
    path is the one ``record_path`` returns for this script -- computed here
    by calling it, which is also the filename the writer uses.
    """
    script = tmp_path / "thing.py"
    path = last_used.record_path(tmp_path, script, "veny")
    path.write_text(payload, encoding="utf-8")

    with caplog.at_level(logging.INFO):
        record = last_used.load(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=False
        )

    assert record is None
    assert f"Last-used record {os.fspath(path)} {complaint}." in caplog.text


@pytest.mark.parametrize(
    ("payload", "wrong_field"),
    [
        ({"venv_dir": 5, "venv_python": "/a/bin/python"}, "venv_dir"),
        ({"venv_dir": "/a", "venv_python": ["/a/bin/python"]}, "venv_python"),
    ],
    ids=["venv_dir-a-number", "venv_python-a-list"],
)
def test_a_record_whose_path_is_not_a_string_is_refused(
    tmp_path, caplog, payload, wrong_field
):
    """Either path being a JSON number or list makes the whole record no record.

    Behaviour under test: the two ``isinstance(..., str)`` guards in
    ``last_used.load``, which stand between a hand-edited or foreign-written
    file and ``ek.ensure_path``. They are exercised one at a time on purpose:
    with both fields wrong, either guard alone still catches it, so a test
    that corrupts both cannot tell whether both guards are live.

    Concrete bug this catches: widening or dropping one of the two checks. A
    ``venv_dir`` of ``5`` is truthy, so the emptiness guard below waves it
    through, and ``ek.ensure_path(5)`` raises a TypeError out of the first
    line of an ordinary run -- veny falling over on a corrupt cache pointer
    instead of quietly rebuilding.

    How the expected value was determined: the contract in ``load``'s
    docstring -- every degraded input is "no record", never an exception.
    """
    assert wrong_field in payload
    script = tmp_path / "thing.py"
    path = last_used.record_path(tmp_path, script, "veny")
    path.write_text(json.dumps(payload), encoding="utf-8")

    with caplog.at_level(logging.INFO):
        record = last_used.load(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=False
        )

    assert record is None
    assert f"Last-used record {os.fspath(path)} names no environment." in caplog.text


def test_a_record_whose_timestamp_is_not_a_string_still_loads(tmp_path):
    """A non-string timestamp becomes "", and the record is still usable.

    Behaviour under test: the ``timestamp if isinstance(timestamp, str)
    else ""`` conditional -- the one field ``load`` repairs rather than
    rejects, because nothing selects on it.

    Concrete bug this catches: dropping the guard, which puts an ``int`` on
    a field typed ``str``. It survives the load, reaches ``save`` on the next
    run through ``LastUsed``, and only fails there -- a type error one run
    away from the file that caused it. Rejecting the whole record instead
    would be the opposite bug: a usable venv pointer thrown away over a
    diagnostic field.

    How the expected value was determined: ``LastUsed.timestamp``'s
    documented type (``str``) and ``load``'s "every degraded input is
    tolerated" contract; the two paths are given values that must survive.
    """
    script = tmp_path / "thing.py"
    venv = tmp_path / "myenv-1"
    last_used.record_path(tmp_path, script, "veny").write_text(
        json.dumps(
            {
                "venv_dir": os.fspath(venv),
                "venv_python": os.fspath(venv / "bin" / "python"),
                "timestamp": 20200101,
            }
        ),
        encoding="utf-8",
    )

    record = last_used.load(
        script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
    )

    assert record is not None
    assert record.timestamp == ""
    assert record.venv_dir == venv


def test_a_record_survives_a_venv_path_that_is_not_ascii(tmp_path):
    """A non-ASCII venv path survives the write, the read and the file check.

    Behaviour under test: the JSON round trip in ``save``/``load`` for a
    directory name outside ASCII, and ``load_venv_python``'s existence check
    against it.

    Concrete bug this catches: escaping, quoting or normalising the paths on
    the way through the record -- anything that returns a *different* string
    than went in names a directory that does not exist, so --feeling-lucky
    silently never fires for any user whose project or home directory is not
    ASCII, and no ASCII-only fixture can see it.

    Explicitly NOT what this pins: the ``encoding="utf-8"`` arguments on
    either side. ``json.dumps`` escapes non-ASCII by default, so the bytes on
    disk are ASCII whatever is in the paths, and no payload can tell utf-8
    from latin-1. The sweep records those two arguments as open for that
    reason.

    How the expected value was determined: the round trip -- what is saved
    must come back as the same path object.
    """
    script = tmp_path / "thing.py"
    venv = tmp_path / "myenv-日本語-Ünïcøde"
    interpreter = _a_venv(venv)
    last_used.save(
        state.LastUsed(venv, interpreter, "20200101-000000"),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )

    record = last_used.load(
        script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
    )

    assert record is not None
    assert record.venv_dir == venv
    assert record.venv_python == interpreter
    assert (
        last_used.load_venv_python(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
        )
        == interpreter
    )


def test_the_lucky_reader_says_when_there_is_no_record_at_all(tmp_path, caplog):
    """No record: load_venv_python says so rather than returning None silently.

    Behaviour under test: the first of ``load_venv_python``'s three log
    lines, which is the only one a first-ever run on a script reaches.

    Concrete bug this catches: deleting the line, which leaves a
    ``--feeling-lucky`` run that found nothing indistinguishable in the log
    from one that was never asked for.

    How the expected value was determined: the message is the contract of
    that branch -- "no record, so no venv_python"; the directory is empty by
    construction, so nothing else could be reported.
    """
    script = tmp_path / "thing.py"

    with caplog.at_level(logging.INFO):
        result = last_used.load_venv_python(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=False
        )

    assert result is None
    assert "No last used record found, so no venv_python to return." in caplog.text


def test_the_lucky_reader_names_the_interpreter_it_will_not_use(tmp_path, caplog):
    """A recorded interpreter that is gone is named in the warning.

    Behaviour under test: the ``os.fspath(record.venv_python)`` interpolated
    into ``load_venv_python``'s warning.

    Concrete bug this catches: warning without naming the path (or naming
    the record file instead of the interpreter). The user is told an
    environment vanished and not which one, on a machine that may hold
    dozens of cached venvs. The existing
    ``test_load_venv_python_is_none_when_the_interpreter_is_gone`` asserts
    only the "no longer valid" fragment, so the path could be dropped
    without failing it.

    How the expected value was determined: the interpreter path this test
    wrote into the record.
    """
    script = tmp_path / "thing.py"
    gone = tmp_path / "deleted-env" / "bin" / "python"
    last_used.save(
        state.LastUsed(gone.parent.parent, gone, "20200101-000000"),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )

    with caplog.at_level(logging.WARNING):
        result = last_used.load_venv_python(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=False
        )

    assert result is None
    assert f"Last used venv_python {os.fspath(gone)} is no longer valid." in caplog.text


def test_the_lucky_reader_names_the_interpreter_it_found(tmp_path, caplog):
    """The success line names the interpreter --feeling-lucky is about to use.

    Behaviour under test: the last of ``load_venv_python``'s three log lines,
    the only trace an ordinary lucky run leaves of which environment it
    picked.

    Concrete bug this catches: dropping the line or interpolating
    ``venv_dir`` instead. --feeling-lucky prints nothing of its own on
    success, so this is the whole of the answer to "which python did that
    run use?" -- the first question asked when a lucky run behaves unlike a
    normal one.

    How the expected value was determined: the interpreter path this test
    created and recorded.
    """
    script = tmp_path / "thing.py"
    interpreter = _a_venv(tmp_path / "myenv-1")
    last_used.save(
        state.LastUsed(interpreter.parent.parent, interpreter, "20200101-000000"),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )

    with caplog.at_level(logging.INFO):
        result = last_used.load_venv_python(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=False
        )

    assert result == interpreter
    assert f"Last used venv_python found: {os.fspath(interpreter)}" in caplog.text


def test_feeling_lucky_says_so_when_there_is_no_record(monkeypatch, tmp_path, capsys):
    """With no record, the lucky path says why it is carrying on as normal.

    Behaviour under test: ``feeling_lucky``'s second ``print``. It prints
    rather than logs because logging is not configured yet, which is also
    why no caplog-based test can see it.

    Concrete bug this catches: dropping the message, which turns "there was
    no environment to reuse" into a --feeling-lucky run that looks exactly
    like an ordinary slow one, with no hint that the flag did nothing.

    How the expected value was determined: the sentence is the branch's
    contract; the record is absent by construction.
    """
    script = tmp_path / "thing.py"
    script.write_text("import thing\n")
    args = argparse.Namespace(feeling_lucky=True)
    target = state.Target(
        python_script=script,
        script_dir=tmp_path,
        script_args=(),
        python_command="python3",
        timestamp="20200101-000000",
    )

    assert pipeline.feeling_lucky(args, target, my_name="veny", rawlog=False) is None

    assert (
        "No luck: no last used virtual environment found. "
        "Running the script as normal." in capsys.readouterr().out
    )


def test_feeling_lucky_reports_a_script_that_failed(monkeypatch, tmp_path, capsys):
    """A lucky run whose script fails says so, with the status.

    Behaviour under test: ``feeling_lucky``'s first ``print``, guarded by a
    non-zero return and by ``rawlog``.

    Concrete bug this catches: dropping the line, which loses the only
    report of a failure on the lucky path -- veny returns the status but
    prints nothing, and a script that died silently looks like one that
    succeeded silently.

    How the expected value was determined: the status is the one the stubbed
    launch returns (3, chosen so it cannot be confused with 0 or 1), and the
    sentence is the branch's contract.
    """
    script = tmp_path / "thing.py"
    script.write_text("import thing\n")
    interpreter = _a_venv(tmp_path / "myenv-1")
    last_used.save(
        state.LastUsed(interpreter.parent.parent, interpreter, "20200101-000000"),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, *a, **k: subprocess.CompletedProcess(
            args=command, returncode=3
        ),
    )
    args = argparse.Namespace(feeling_lucky=True)
    target = state.Target(
        python_script=script,
        script_dir=tmp_path,
        script_args=(),
        python_command="python3",
        timestamp="20200101-000000",
    )

    assert pipeline.feeling_lucky(args, target, my_name="veny", rawlog=False) == 3

    assert "Script exited with status 3" in capsys.readouterr().out


def test_the_last_used_pass_is_skipped_when_smallest_is_asked_for_too(tmp_path, caplog):
    """--smallest --last-used together must not consult the record at all.

    Behaviour under test: the ``not getattr(args, "smallest", False)`` term
    guarding the last-used pass. It is live for exactly one combination:
    with ``--smallest`` alone the pass is already off (``explicit`` is true
    and ``last_used`` is false), so only both flags together reach it.

    Concrete bug this catches: dropping the term, which lets the recorded
    venv win over the smallest one the user explicitly asked for -- and,
    because the recorded venv usually satisfies the run, ``--smallest``
    would appear to do nothing whenever a record exists.

    How the expected value was determined: the flag's contract. The loader
    is a spy that records being called, so the assertion is on whether the
    pass ran, not on which folder came back.
    """
    calls: list[int] = []

    def loader():
        calls.append(1)
        return None

    with caplog.at_level(logging.INFO):
        chosen = cache_search.find_match_dir_in_cache(
            argparse.Namespace(last_used=True, smallest=True),
            my_dir=tmp_path,
            venv_name="myenv",
            uninstalled=set(),
            extra_requirements={},
            source_names=frozenset(),
            tag="3.12",
            rawlog=True,
            load_last_used=loader,
        )

    assert calls == []
    assert chosen is None


def test_a_pointer_that_does_not_match_says_it_is_trying_the_latest(tmp_path, caplog):
    """A spent last-used pass announces the fall-through to "latest".

    Behaviour under test: the ``logging.info`` between the last-used pass and
    the ranking pass -- the line that explains why a run with a perfectly
    good record still went looking.

    Concrete bug this catches: dropping the line, which makes a stale
    pointer indistinguishable in the log from no pointer at all. Every
    ``_search``-based test in ``tests/test_cache_search.py`` passes
    ``rawlog=True``, so none of them can see this message.

    How the expected value was determined: the sentence is the branch's
    contract, and the pointer names a directory that does not exist, so the
    fall-through is forced.
    """
    with caplog.at_level(logging.INFO):
        chosen = cache_search.find_match_dir_in_cache(
            argparse.Namespace(),
            my_dir=tmp_path,
            venv_name="myenv",
            uninstalled=set(),
            extra_requirements={},
            source_names=frozenset(),
            tag="3.12",
            rawlog=False,
            load_last_used=lambda: state.LastUsed(
                tmp_path / "gone",
                tmp_path / "gone" / "bin" / "python",
                "20200101-000000",
            ),
        )

    assert chosen is None
    assert "Trying to load the latest matching venv now." in caplog.text
