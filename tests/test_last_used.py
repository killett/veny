"""Characterize the last-used record now that it lives in veny.last_used.

Fixtures write records via ``ek.save_options_to_json`` rather than hand-rolled
JSON. ``ek.load_options_from_json`` round-trips tagged values (a bare JSON
string does not decode back into a ``Path``), and
``load_last_used_venv_python`` both calls ``ek.safe_is_file`` on the recorded
value and compares it for equality against a real ``Path`` in the happy-path
test below — a fixture that skipped the tagging would silently test the
wrong thing (a str never equals a Path, and would never reliably satisfy a
filesystem-path predicate the way a Path does). So every fixture here builds
a real ``cli.Options`` object, sets the field(s) under test on it, and saves
it with ``ek.save_options_to_json``, letting the library do the tagging
instead of transcribing its format by hand.

Measured (not transcribed): building an ``Options`` with ``python_script`` =
``tmp_path / "thing.py"``, ``script_dir`` = ``tmp_path`` and ``timestamp`` =
``"20260202-020202"``, then calling ``ek.save_options_to_json(options)`` and
printing ``options.options_json_filepath.name``, produces:

    .thing.py-veny-last-used-on-20260202-020202.json

which satisfies both of ``load_last_used_options``'s filters: the
``.thing.py`` prefix (``"." + options.python_script.name``) and the
``last-used-on-(\\d{8}-\\d{6})`` regex.
"""

import sys
from pathlib import Path

import emmykit as ek
import pytest

from veny import cli, last_used


def _write_record(tmp_path: Path, script: Path, stamp: str, **fields: object) -> Path:
    """Write one last-used options JSON the loader will recognise.

    Args:
        tmp_path: The directory the loader scans (also options.script_dir).
        script:   The script Path the record belongs to.
        stamp:    The "YYYYmmdd-HHMMSS" the filename carries (options.timestamp).
        **fields: Extra attributes (e.g. venv_dir=..., venv_python=...) set on
                  the Options object before saving, so they round-trip through
                  ek.save_options_to_json / ek.load_options_from_json with
                  their real types (e.g. Path, not str).

    Returns:
        The path written.
    """
    options = cli.Options()
    options.python_script = script
    options.script_dir = tmp_path
    options.timestamp = stamp
    for key, value in fields.items():
        setattr(options, key, value)
    ek.save_options_to_json(options)
    assert options.options_json_filepath is not None
    return options.options_json_filepath


def _options_for(tmp_path: Path) -> tuple[cli.Options, Path]:
    """An Options pointed at a real script inside tmp_path.

    Returns both the Options and the script Path (rather than making callers
    read it back off ``options.python_script``, which mypy sees as
    ``Path | None``) since every caller needs a definitely-not-None Path to
    hand to ``_write_record``.
    """
    script = tmp_path / "thing.py"
    script.write_text("import yaml\n")
    options = cli.Options()
    options.python_script = script
    options.script_dir = tmp_path
    return options, script


def test_the_most_recent_matching_json_wins(tmp_path: Path) -> None:
    """Two candidates, and the newer timestamp is the one loaded.

    A bug that would make this fail: dropping the reverse=True on the sort,
    which would resurrect the oldest venv on every run and quietly stop the
    cache from ever advancing.

    Expected value: the venv_dir recorded in the *newer* file. Obtained by
    running the current loader against both files, not by reading the sort
    key.
    """
    options, script = _options_for(tmp_path)
    _write_record(
        tmp_path,
        script,
        "20260101-010101",
        venv_dir=tmp_path / "older",
    )
    _write_record(
        tmp_path,
        script,
        "20260202-020202",
        venv_dir=tmp_path / "newer",
    )
    loaded = last_used.load_last_used_options(
        options,
        script_dir=tmp_path,
        python_script=script,
        pathlibcutoff=options.pathlibcutoff,
        rawlog=options.rawlog,
    )
    assert loaded is not None
    assert getattr(loaded, "venv_dir", None) == tmp_path / "newer"


def test_a_json_older_than_the_pathlib_cutoff_is_ignored(tmp_path: Path) -> None:
    """Pre-cutoff files stored paths as strings and must not be loaded.

    A bug that would make this fail: comparing the timestamps as numbers, or
    dropping the `>= options.pathlibcutoff` term, which would feed str-typed
    paths into code that calls Path methods on them. The cutoff is
    "20250810-224900" (cli.py's Options default).
    """
    options, script = _options_for(tmp_path)
    _write_record(
        tmp_path,
        script,
        "20250101-000000",
        venv_dir=tmp_path / "ancient",
    )
    assert (
        last_used.load_last_used_options(
            options,
            script_dir=tmp_path,
            python_script=script,
            pathlibcutoff=options.pathlibcutoff,
            rawlog=options.rawlog,
        )
        is None
    )


def test_no_matching_json_returns_none(tmp_path: Path) -> None:
    """An empty script directory yields None, not an exception."""
    options, script = _options_for(tmp_path)
    assert (
        last_used.load_last_used_options(
            options,
            script_dir=tmp_path,
            python_script=script,
            pathlibcutoff=options.pathlibcutoff,
            rawlog=options.rawlog,
        )
        is None
    )


def test_a_recorded_interpreter_that_no_longer_exists_returns_none(
    tmp_path: Path,
) -> None:
    """A deleted venv's interpreter is not offered to --feeling-lucky.

    A bug that would make this fail: dropping the ek.safe_is_file guard, which
    would hand main() a path to a missing interpreter and turn
    --feeling-lucky's fast path into a FileNotFoundError.
    """
    options, script = _options_for(tmp_path)
    _write_record(
        tmp_path,
        script,
        "20260202-020202",
        venv_python=tmp_path / "gone" / "bin" / "python",
    )
    assert (
        last_used.load_last_used_venv_python(
            options,
            script_dir=tmp_path,
            python_script=script,
            pathlibcutoff=options.pathlibcutoff,
            rawlog=options.rawlog,
        )
        is None
    )


def test_a_recorded_interpreter_that_exists_is_returned(tmp_path: Path) -> None:
    """The happy path, so the guard above cannot pass by always returning None."""
    options, script = _options_for(tmp_path)
    interpreter = tmp_path / "venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("")
    _write_record(
        tmp_path,
        script,
        "20260202-020202",
        venv_python=interpreter,
    )
    assert (
        last_used.load_last_used_venv_python(
            options,
            script_dir=tmp_path,
            python_script=script,
            pathlibcutoff=options.pathlibcutoff,
            rawlog=options.rawlog,
        )
        == interpreter
    )


def test_is_virtualenv_reflects_prefix_vs_base_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both branches of the sys.prefix / sys.base_prefix comparison are pinned.

    A bug that would make this fail: inverting the comparison (`==` instead
    of `!=`), or comparing the wrong pair of attributes (e.g. sys.prefix to
    itself, always True, or sys.base_prefix to itself, always False) — any
    of which would make veny take the already-in-a-virtualenv path on a bare
    interpreter and skip building a venv at all, or vice versa.

    Both branches are exercised so a mutation that only breaks one of them
    (e.g. hard-coding True) cannot slip through unnoticed.
    """
    monkeypatch.setattr(sys, "prefix", "/fake/venv")
    monkeypatch.setattr(sys, "base_prefix", "/fake/base")
    assert last_used.is_virtualenv() is True

    monkeypatch.setattr(sys, "prefix", "/fake/same")
    monkeypatch.setattr(sys, "base_prefix", "/fake/same")
    assert last_used.is_virtualenv() is False


def test_the_last_used_adapter_hands_over_this_runs_script_and_cutoff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """cli._load_last_used is the only place these five arguments are wired.

    load_last_used_options used to read them off the Options object it was
    given; the extraction turned four of them into explicit keyword arguments
    built at this one call site, and measured by substitution all five could
    be replaced with a wrong value while all 338 tests stayed green -- nothing
    drove cli._load_last_used at all.

    Concrete bug this catches: a wrong `script_dir` looks in a directory that
    holds no last-used JSON, so the cache search silently falls through to
    "latest" on every run and the last-used pointer never wins; a wrong
    `pathlibcutoff` (say a timestamp in the future) rejects every record ever
    written, with the same silent effect and no error anywhere.
    """
    options = cli.Options()
    options.script_dir = tmp_path / "scripts"
    options.python_script = tmp_path / "scripts" / "thing.py"
    options.rawlog = True
    seen: list[dict[str, object]] = []
    sentinel = ek.Options()

    def spy(passed_options, **kwargs):
        seen.append({"options": passed_options, **kwargs})
        return sentinel

    monkeypatch.setattr(last_used, "load_last_used_options", spy)

    assert cli._load_last_used(options) is sentinel
    assert seen == [
        {
            "options": options,
            "script_dir": tmp_path / "scripts",
            "python_script": tmp_path / "scripts" / "thing.py",
            "pathlibcutoff": options.pathlibcutoff,
            "rawlog": True,
        }
    ]
    # The cutoff is the class default, not a literal copied into this test:
    # a call site substituting any other value fails the equality above.
    assert options.pathlibcutoff == cli.Options().pathlibcutoff
