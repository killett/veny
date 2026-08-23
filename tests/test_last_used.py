"""Characterize the last-used record now that it lives in veny.last_used.

Phase 4b Task 3 deleted the two emmykit-typed readers this file used to
cover. ``load_last_used_options`` globbed the script's directory for
``.<script>-veny-last-used-on-<stamp>.json`` files, sorted them and rebuilt
an ``ek.Options`` from the newest one that cleared ``pathlibcutoff``; the
tests for the glob, the sort and the cutoff went with it, because a reader
that names one fixed file has no glob to get wrong, no sort to reverse and
no pre-2025 format to reject on a timestamp (it cannot decode those payloads
at all -- see ``test_a_record_written_by_an_earlier_veny_is_ignored``).
What is left here is the record itself, ``load`` / ``load_venv_python``, and
the two call sites in ``pipeline`` that reach them.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pytest

from veny import last_used, pipeline, state

from .test_state_values import a_settings
from .test_state_values import a_target as _target


def _a_script(tmp_path: Path) -> Path:
    """A real script inside tmp_path, for the record to be named after.

    Args:
        tmp_path: The directory the script (and its record) lives in.

    Returns:
        The script's path.
    """
    script = tmp_path / "thing.py"
    script.write_text("import yaml\n")
    return script


def test_the_venv_python_loader_lets_the_record_search_explain_itself(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """load_venv_python must pass the caller's rawlog down, not a constant.

    It has two voices on a miss: its own ("No last used record found, so no
    venv_python to return.") and the one from ``load``, which it delegates to
    and which is the only one that says *which* script found nothing. The
    second is the one this call site's `rawlog` argument controls.

    Measured 2026-08-19 across all 17 `rawlog=` sites in
    cli/cache_search/last_used/verify: substituting the wrong-but-type-correct
    `True` -- covered by the STANDING CHECK's own stated method -- left 16 of
    them green, this one included, because nothing in the suite read a log
    record from this path.

    Concrete bug this catches: `rawlog=True` here, and a --feeling-lucky run
    that finds nothing reports only that it found nothing, never that the
    script's directory holds no record at all (as opposed to holding one
    whose interpreter has been deleted, which has its own line).
    """
    script = _a_script(tmp_path)

    with caplog.at_level(logging.INFO):
        assert (
            last_used.load_venv_python(
                script_dir=tmp_path,
                python_script=script,
                my_name="veny",
                rawlog=False,
            )
            is None
        )

    assert f"No usable last-used record for {os.fspath(script)}." in caplog.text

    # And the other direction: a run that asked for raw logging must stay
    # quiet, so a hardcoded `rawlog=False` at that call site is caught too.
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert (
            last_used.load_venv_python(
                script_dir=tmp_path,
                python_script=script,
                my_name="veny",
                rawlog=True,
            )
            is None
        )

    assert "No usable last-used record" not in caplog.text


def test_active_virtualenv_dir_prefers_the_environment_variable(monkeypatch, tmp_path):
    """VIRTUAL_ENV names the environment the user activated.

    Behaviour under test: which directory veny checks when it is run from
    inside a virtualenv. Concrete bug this catches: reading sys.prefix first
    would report veny's *own* environment when veny is installed as a uv tool
    and invoked from inside a different activated venv -- veny would then
    check the wrong environment's packages and report a confident, wrong
    answer. Expected value obtained from the virtualenv activation contract:
    the activate script exports VIRTUAL_ENV.
    """
    monkeypatch.setenv("VIRTUAL_ENV", os.fspath(tmp_path / "activated"))

    assert last_used.active_virtualenv_dir() == tmp_path / "activated"


def test_active_virtualenv_dir_is_none_when_nothing_is_activated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No VIRTUAL_ENV means no activated environment, whatever sys.prefix says.

    A bug that would make this fail: answering from sys.prefix, the way veny
    did until phase 4c. veny's own documented install (`uv tool install veny`)
    puts veny inside a virtualenv, so a sys.prefix answer is True on every
    such install -- and pipeline.run then import-checks veny's own tool venv,
    fails, and tells the user to deactivate an environment they never
    activated, with the cache search unreachable behind it.
    """
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(sys, "prefix", "/fake/venv")
    monkeypatch.setattr(sys, "base_prefix", "/fake/base")

    assert last_used.active_virtualenv_dir() is None


def test_active_virtualenv_dir_is_none_when_the_variable_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty VIRTUAL_ENV is not an activated environment.

    A bug that would make this fail: `os.environ.get("VIRTUAL_ENV") is not
    None` instead of a truthiness test, which would make an exported-but-empty
    variable name Path("") -- the current working directory -- as the
    environment to import-check.
    """
    monkeypatch.setenv("VIRTUAL_ENV", "")

    assert last_used.active_virtualenv_dir() is None


def test_active_virtualenv_dir_answers_with_a_path_not_a_string(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The answer is a Path, because its caller joins bin/python onto it.

    A bug that would make this fail: returning the raw environment string.
    environment.venv_python_for does `venv_dir / "bin" / "python"`, which
    raises TypeError on a str -- but only on the branch this value reaches,
    which no other test in this file drives.
    """
    monkeypatch.setenv("VIRTUAL_ENV", os.fspath(tmp_path / "activated"))

    answer = last_used.active_virtualenv_dir()

    assert isinstance(answer, Path)
    assert answer == tmp_path / "activated"


def test_the_last_used_adapter_returns_the_record_this_run_is_entitled_to(
    tmp_path: Path,
) -> None:
    """pipeline._load_last_used must return this script's own record.

    This drives the adapter for real, against records written into the
    script's own directory. Which venv_dir comes back is the observable, and
    it is decided by all three of the keyword arguments the adapter builds:
    a wrong script_dir or python_script finds no file at all, and a wrong
    my_name names a different file in the same directory -- so the directory
    here holds a decoy record under another program's name as well as this
    run's own.

    Concrete bug this catches: the adapter reading some other script's
    record, which hands the cache search a pointer to an environment built
    for different imports. check_venv_dir rejects it, so nothing crashes --
    the run simply falls through to "latest" forever and the last-used
    pointer never wins.
    """
    script = _a_script(tmp_path)
    last_used.save(
        state.LastUsed(
            tmp_path / "ours", tmp_path / "ours" / "bin" / "python", "20260202-020202"
        ),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )
    last_used.save(
        state.LastUsed(
            tmp_path / "theirs",
            tmp_path / "theirs" / "bin" / "python",
            "20260303-030303",
        ),
        script_dir=tmp_path,
        python_script=script,
        my_name="someone-else",
    )

    loaded = pipeline._load_last_used(
        _target(python_script=script, script_dir=tmp_path),
        my_name="veny",
        rawlog=True,
    )

    assert loaded is not None
    assert loaded.venv_dir == tmp_path / "ours"

    # And the other direction: a script whose directory holds no record of
    # its own is a miss, not the neighbouring script's record.
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    other_script = other_dir / "thing.py"
    other_script.write_text("import yaml\n")

    assert (
        pipeline._load_last_used(
            _target(python_script=other_script, script_dir=other_dir),
            my_name="veny",
            rawlog=True,
        )
        is None
    )


def test_the_last_used_adapter_hands_over_this_runs_script_and_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The same four arguments again, this time read off the call itself.

    Secondary to the behavioural test above, and kept because one of the four
    is invisible to it: rawlog, which only decides whether the "No usable
    last-used record" line is logged.

    Concrete bug this catches: a wrong `script_dir` looks in a directory that
    holds no last-used record, so the cache search silently falls through to
    "latest" on every run and the last-used pointer never wins.
    """
    target = _target(
        python_script=tmp_path / "scripts" / "thing.py",
        script_dir=tmp_path / "scripts",
    )
    seen: list[dict[str, object]] = []
    sentinel = state.LastUsed(
        tmp_path / "env", tmp_path / "env" / "bin" / "python", "20260202-020202"
    )

    def spy(**kwargs: object) -> state.LastUsed:
        seen.append(kwargs)
        return sentinel

    monkeypatch.setattr(last_used, "load", spy)

    assert pipeline._load_last_used(target, my_name="veny", rawlog=True) is sentinel
    assert seen == [
        {
            "script_dir": tmp_path / "scripts",
            "python_script": tmp_path / "scripts" / "thing.py",
            "my_name": "veny",
            "rawlog": True,
        }
    ]


# --- The new record. Behaviour under test, and the bug each test would catch.


def test_a_saved_record_is_read_back_as_the_same_paths(tmp_path):
    # Bug caught: a reader that hands back the JSON strings instead of Paths.
    # Every consumer compares against a Path or feeds ek.safe_is_file, and a
    # str fails both silently in the second case.
    script = tmp_path / "thing.py"
    script.write_text("import yaml\n")
    record = state.LastUsed(
        venv_dir=tmp_path / "myenv-1",
        venv_python=tmp_path / "myenv-1" / "bin" / "python",
        timestamp="20260202-020202",
    )

    last_used.save(record, script_dir=tmp_path, python_script=script, my_name="veny")
    loaded = last_used.load(
        script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
    )

    assert loaded == record
    assert loaded is not None
    assert isinstance(loaded.venv_dir, Path)
    assert isinstance(loaded.venv_python, Path)


def test_the_record_is_named_for_the_script_and_the_program(tmp_path):
    # Bug caught: a filename that omits the script's name, which would make
    # two scripts in one directory share -- and overwrite -- one record.
    script = tmp_path / "thing.py"

    path = last_used.record_path(tmp_path, script, "veny")

    assert path == tmp_path / ".thing.py-veny-last-used.json"


def test_a_second_save_overwrites_rather_than_accumulating(tmp_path):
    # Bug caught: reinstating the per-run timestamped filename, which is what
    # littered the user's script directory with one JSON per run.
    script = tmp_path / "thing.py"
    first = state.LastUsed(
        tmp_path / "old", tmp_path / "old" / "python", "20260101-010101"
    )
    second = state.LastUsed(
        tmp_path / "new", tmp_path / "new" / "python", "20260202-020202"
    )

    last_used.save(first, script_dir=tmp_path, python_script=script, my_name="veny")
    last_used.save(second, script_dir=tmp_path, python_script=script, my_name="veny")

    assert [p.name for p in tmp_path.glob(".thing.py-veny*")] == [
        ".thing.py-veny-last-used.json"
    ]
    loaded = last_used.load(
        script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
    )
    assert loaded is not None
    assert loaded.venv_dir == tmp_path / "new"


def test_a_missing_record_is_none_and_not_an_error(tmp_path):
    # Bug caught: letting FileNotFoundError out of the reader, which reaches
    # main() as a traceback on every first run of every script.
    assert (
        last_used.load(
            script_dir=tmp_path,
            python_script=tmp_path / "thing.py",
            my_name="veny",
            rawlog=True,
        )
        is None
    )


def test_a_record_written_by_an_earlier_veny_is_ignored(tmp_path):
    # Bug caught: a reader that globs the directory instead of naming one
    # file would pick up the old whole-Options dumps, whose tagged payload
    # this phase deliberately stopped being able to decode. User ruling
    # 2026-08-21: ignore them, do not migrate them.
    script = tmp_path / "thing.py"
    (tmp_path / ".thing.py-veny-last-used-on-20260101-010101.json").write_text(
        json.dumps(
            {
                "venv_dir": {"__type__": "path", "value": str(tmp_path / "old")},
                "venv_python": {
                    "__type__": "path",
                    "value": str(tmp_path / "old" / "python"),
                },
                "pathlibcutoff": "20250810-224900",
            }
        ),
        encoding="utf-8",
    )

    assert (
        last_used.load(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
        )
        is None
    )


@pytest.mark.parametrize(
    "text",
    [
        "{not json",  # invalid JSON
        "[]",  # valid JSON, wrong shape
        json.dumps({"venv_dir": "/a"}),  # venv_python missing
        json.dumps({"venv_dir": "", "venv_python": ""}),  # present but empty
    ],
    ids=["invalid", "not-an-object", "missing-key", "empty-values"],
)
def test_a_damaged_record_is_none_and_not_a_crash(tmp_path, text):
    # Bug caught: JSONDecodeError, TypeError or KeyError escaping into main --
    # or, worse, a LastUsed carrying Path("") that every later check treats as
    # a real directory.
    script = tmp_path / "thing.py"
    last_used.record_path(tmp_path, script, "veny").write_text(text, encoding="utf-8")

    assert (
        last_used.load(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
        )
        is None
    )


def test_load_venv_python_returns_the_recorded_interpreter(tmp_path):
    # Bug caught: dropping the existence check, which would hand
    # --feeling-lucky a deleted interpreter and turn a clean fallback into a
    # FileNotFoundError from subprocess.
    script = tmp_path / "thing.py"
    interpreter = tmp_path / "myenv-1" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("#!/bin/sh\n")
    last_used.save(
        state.LastUsed(interpreter.parent.parent, interpreter, "20260202-020202"),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )

    assert (
        last_used.load_venv_python(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=True
        )
        == interpreter
    )


def test_load_venv_python_is_none_when_the_interpreter_is_gone(tmp_path, caplog):
    # Bug caught: returning a Path to a deleted venv, which is the whole
    # reason the old reader called ek.safe_is_file.
    script = tmp_path / "thing.py"
    gone = tmp_path / "deleted-env" / "bin" / "python"
    last_used.save(
        state.LastUsed(gone.parent.parent, gone, "20260202-020202"),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )

    with caplog.at_level(logging.WARNING):
        result = last_used.load_venv_python(
            script_dir=tmp_path, python_script=script, my_name="veny", rawlog=False
        )

    assert result is None
    assert "no longer valid" in caplog.text


def test_blank_slate_deletes_the_new_last_used_record(tmp_path, monkeypatch):
    # Bug caught: a record filename that no longer matches blank_slate's
    # ".{...}-veny-...json" test, which would leave veny's own dotfiles behind
    # after the user asked for a clean slate.
    script = tmp_path / "thing.py"
    record = last_used.save(
        state.LastUsed(
            tmp_path / "env", tmp_path / "env" / "python", "20260202-020202"
        ),
        script_dir=tmp_path,
        python_script=script,
        my_name="veny",
    )
    assert record.exists()
    settings_for_run = a_settings(my_dir=tmp_path / "veny-home", cwd=tmp_path)

    pipeline.blank_slate(settings_for_run, argparse.Namespace(y=True))

    assert not record.exists()
