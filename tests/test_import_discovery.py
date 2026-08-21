"""Pin which imports veny's scan discovers, independent of I/O recording."""

import argparse
import contextlib
import logging
import sys
from pathlib import Path

import pytest

from veny import alias_index, cli, pipeline


def _scan(script: Path, custom_modules: dict[str, Path]) -> cli.Options:
    """Run the import scan over one script and return the populated options.

    Args:
        script:         The Python file to analyze.
        custom_modules: Local module name to file path, as main() would supply.

    Returns:
        The Options object the scan wrote its findings into.
    """
    options = cli.Options()
    options.rawlog = True
    options.python_script = script
    options.script_dir = script.parent
    options.custom_modules = custom_modules
    pipeline.find_imports_in_script(options, script)
    return options


def test_the_scan_adapter_lets_the_scanner_name_the_files_it_opens(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """find_imports_in_script builds the Settings the scanner logs through.

    `rawlog` is one of five fields pipeline.find_imports_in_script copies onto the
    Settings it hands analysis.scan. Measured 2026-08-19 across all 17
    `rawlog=` sites in cli/cache_search/last_used/verify: substituting the
    wrong-but-type-correct `True` left 16 of them with the whole suite green,
    this one included -- every scan test here sets rawlog=True and asserts on
    the imports found, never on a log record.

    Concrete bug this catches: `rawlog=True` in that Settings and the
    "Processing module: X" line vanishes for every file the scan walks into.
    That line is what tells a user which of their own local modules veny
    followed an import into -- the only visible trace of the recursive walk,
    and the first thing to look at when the scan reports an import from a
    file nobody expected it to open.
    """
    helper = tmp_path / "helper.py"
    helper.write_text("import numpy\n")
    script = tmp_path / "s.py"
    script.write_text("import helper\n\nhelper\n")
    options = cli.Options()
    options.rawlog = False
    options.python_script = script
    options.script_dir = tmp_path
    options.custom_modules = {"helper": helper}

    with caplog.at_level(logging.INFO):
        pipeline.find_imports_in_script(options, script)

    assert options.all_imports == {"numpy"}
    assert f"Processing module: {script}" in caplog.text

    # And the other direction: a run that asked for raw logging must stay
    # quiet, so a hardcoded `rawlog=False` in that Settings is caught too.
    caplog.clear()
    quiet = cli.Options()
    quiet.rawlog = True
    quiet.python_script = script
    quiet.script_dir = tmp_path
    quiet.custom_modules = {"helper": helper}

    with caplog.at_level(logging.INFO):
        pipeline.find_imports_in_script(quiet, script)

    assert "Processing module:" not in caplog.text


def test_function_body_import_in_a_custom_module_is_discovered(
    tmp_path: Path,
) -> None:
    """An import inside a called function of a local module still counts."""
    helper = tmp_path / "helper.py"
    helper.write_text(
        "import numpy\n\n\ndef h():\n    import pandas\n\n    return pandas\n"
    )
    script = tmp_path / "s.py"
    script.write_text(
        "import requests\n"
        "import helper\n\n\n"
        "def main():\n"
        "    requests.get('https://example.com')\n"
        "    return helper.h()\n\n\n"
        "main()\n"
    )

    options = _scan(script, {"helper": helper})

    assert options.all_imports == {"numpy", "pandas", "requests"}
    assert options.loaded_custom_modules == {"helper"}


def test_standard_library_imports_are_not_reported_as_needing_install(
    tmp_path: Path,
) -> None:
    """Stdlib names are recorded as seen, never as imports to install."""
    script = tmp_path / "s.py"
    script.write_text("import os\nimport json\nimport requests\n\nprint(os, json)\n")

    options = _scan(script, {})

    assert options.all_imports == {"requests"}
    assert {"os", "json"} <= options.seen_stdlib_imports


def test_a_script_with_no_third_party_imports_yields_an_empty_import_set(
    tmp_path: Path,
) -> None:
    """The empty case is empty -- nothing is seeded into the import set."""
    script = tmp_path / "s.py"
    script.write_text("import sys\n\nprint(sys.version)\n")

    options = _scan(script, {})

    assert options.all_imports == set()


def test_a_prepopulated_custom_module_outside_the_script_dir_is_recognized(
    tmp_path: Path,
) -> None:
    """options.custom_modules is seeded before the scan is ever reached.

    dict_of_custom_modules() populates options.custom_modules before
    list_packages() reaches find_imports_in_script -- the scanner must see
    that prior state from its very first call. faraway.py lives outside the
    script's own directory and is not a package, so the only way it can
    resolve is through the prepopulated custom_modules map, never through
    the same-directory or sys.path-hint fallbacks process_import also tries.
    """
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    faraway = other_dir / "faraway.py"
    faraway.write_text("def go():\n    return 1\n")

    script_dir = tmp_path / "proj"
    script_dir.mkdir()
    script = script_dir / "s.py"
    script.write_text("import faraway\n\nfaraway.go()\n")

    options = _scan(script, {"faraway": faraway})

    assert options.all_imports == set()
    assert options.loaded_custom_modules == {"faraway"}


def _a_run_that_can_classify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> cli.Options:
    """An Options list_packages can be driven with, off the network and off uv.

    Only two boundaries are replaced: the throwaway probe environment (a uv
    subprocess) and the alias index's network access. The scan, the directory
    walk, the stay-out filter and the classification copy-back are all real.
    """
    options = cli.Options()
    options.rawlog = False
    options.aliases = alias_index.empty(tmp_path / "index")
    # Not the default list: a substitution that reaches for a fresh Options
    # would still exclude "myenv", and would look correct.
    options.stay_out_list = ["keepout"]
    monkeypatch.setattr(
        pipeline,
        "_probe_venv",
        lambda options: contextlib.nullcontext(lambda import_name: False),
    )
    return options


def test_list_packages_scans_one_script_and_classifies_what_it_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """list_packages must scan the script it was given and hand the result to classification.

    Behaviour under test: the single-file branch of the analysis driver phase
    3e moved into pipeline.py, end to end -- the path resolution, the two
    file-shape questions, the scan call and the classification copy-back.
    Measured by substitution: every argument on this branch could be replaced
    with a wrong path (or the classification handed a throwaway Options) and
    the whole suite stayed green, because nothing drove list_packages at all.

    Concrete bugs this catches: scanning a path other than the one the user
    named finds another script's imports, so veny builds an environment for
    the wrong program; handing the classification copy-back a different
    Options leaves options.uninstalled_imports empty, so veny decides nothing
    needs installing and runs the script under an interpreter that cannot
    import what it needs. `extra-pkg` is asserted absent because --reqs was
    not given: use_reqs must be read from the flag, not assumed true.
    """
    project = tmp_path / "proj"
    project.mkdir()
    script = project / "s.py"
    script.write_text("import requests\n")
    options = _a_run_that_can_classify(tmp_path, monkeypatch)
    options.python_script = script
    options.script_dir = project
    options.extra_requirements = {"extra-pkg": ">=2.0"}

    with caplog.at_level(logging.INFO):
        pipeline.list_packages(options)

    assert f"Processing a single Python script: {script}" in caplog.text
    # Exactly {"requests"}: extra-pkg is an extra requirement, and without
    # --reqs it must not be folded into the imports the script needs.
    assert options.all_imports == {"requests"}
    assert {record.import_name for record in options.uninstalled_imports} == {
        "requests"
    }


def test_report_warns_about_a_standard_library_import_that_needs_a_system_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """report must pass this run's own scan findings to the system-package warning.

    Behaviour under test: the one call report makes into another function of
    the pipeline. Measured by substitution: handing
    warn_about_system_packages a fresh Options left the whole suite green,
    because the only test of that warning calls it directly.

    Concrete bug this catches: the warning consulting anything other than the
    names this scan actually skipped, which silences the single line telling
    a user that `import tkinter` will keep failing until they install a
    package pip cannot provide -- the failure mode that looks like a veny bug
    and is not.
    """
    project = tmp_path / "proj"
    project.mkdir()
    script = project / "s.py"
    script.write_text("import tkinter\n")
    options = _a_run_that_can_classify(tmp_path, monkeypatch)
    options.python_script = script
    options.script_dir = project
    pipeline.list_packages(options)

    with caplog.at_level(logging.INFO):
        pipeline.report(options)

    assert "tkinter is in the standard library but needs the" in caplog.text


def test_the_scan_records_the_local_files_folders_and_sys_path_it_followed(
    tmp_path: Path,
) -> None:
    """The scan's three bookkeeping fields must be the run's own objects, not fresh ones.

    Behaviour under test: three of the seven fields
    pipeline.find_imports_in_script hands the scanner as its ImportScan.
    Measured by substitution: replacing samedir_files, subfolders or
    sys_path_hints with a fresh empty container left the whole suite green --
    every scan test asserted on all_imports and nothing else, so the scanner
    happily wrote its findings into an object the run then threw away.

    Concrete bug this catches: the accumulation those three fields exist for.
    The scanner recurses through the script's local modules, calling itself
    once per reachable file, and relies on all seven fields carrying across
    those calls; a fresh container per call resets them, so a module already
    resolved is resolved again -- and
    the report at the end of the run lists none of the local files or package
    folders the scan actually followed, which is the only place a user sees
    that veny read their own code rather than just their imports.
    """
    project = tmp_path / "proj"
    package = project / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (project / "beside.py").write_text("import requests\n")
    hint_dir = tmp_path / "hinted"
    hint_dir.mkdir()
    script = project / "s.py"
    script.write_text(
        "import sys\n"
        f"sys.path.append({str(hint_dir)!r})\n"
        "import beside\n"
        "import pkg\n\n"
        "print(beside, pkg)\n"
    )

    options = _scan(script, {})

    assert options.samedir_files == [project / "beside.py"]
    assert options.subfolders == ["pkg"]
    assert hint_dir in options.sys_path_hints


def test_a_directory_argument_is_a_usage_error_not_a_traceback(tmp_path: Path) -> None:
    """A directory positional must come back as veny's usage status.

    Behaviour under test: what resolve_target does with a positional argument
    that names a directory rather than a file.

    Concrete bug this catches: resolve_target goes through ek.ensure_file,
    which raises IsADirectoryError, and nothing catches it -- so before this
    change `veny somedir/` was a traceback out of main() rather than a
    status. Folder scanning was the only thing that ever made a directory
    meaningful here, and 3e's deletion of --full removed its only producer.
    """
    options = cli.Options()
    options.args = argparse.Namespace(script=str(tmp_path), script_args=[])

    with pytest.raises(pipeline.UsageError) as excinfo:
        pipeline.resolve_target(options)

    assert str(tmp_path) in str(excinfo.value)


def test_a_missing_script_is_a_usage_error_not_a_traceback(tmp_path: Path) -> None:
    """A script that does not exist must come back as veny's usage status.

    Behaviour under test: what resolve_target does with a positional argument
    naming a path that is not there.

    Concrete bug this catches: `.resolve(strict=True)` raises
    FileNotFoundError out of resolve_target and nothing catches it, so
    `veny /no/such/script.py` printed a traceback instead of a message.
    Recorded as latent defect 2 in PROGRESS.md; this closes it.
    """
    options = cli.Options()
    missing = tmp_path / "no_such_script.py"
    options.args = argparse.Namespace(script=str(missing), script_args=[])

    with pytest.raises(pipeline.UsageError) as excinfo:
        pipeline.resolve_target(options)

    assert "no_such_script.py" in str(excinfo.value)


def test_a_directory_argument_returns_status_2_through_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: the usage error must reach the shell as 2, not as a crash.

    Behaviour under test: the whole path from argv to exit status for a
    directory positional.

    Concrete bug this catches: raising anything cli.main does not catch --
    IsADirectoryError, or a bare ValueError -- propagates out of main() and
    the shell sees a Python traceback and status 1. Only pipeline.UsageError
    maps to veny's usage status of 2.
    """
    monkeypatch.setattr(sys, "argv", ["veny", str(tmp_path)])

    assert cli.main() == 2


def test_a_missing_script_returns_status_2_through_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: a script that is not there must reach the shell as 2.

    Behaviour under test: the whole path from argv to exit status when the
    positional names nothing.

    Concrete bug this catches: FileNotFoundError is not IsADirectoryError, so
    a fix that catches only the directory case leaves this one travelling
    uncaught out of main() -- the shape latent defect 2 recorded. Only
    pipeline.UsageError maps to veny's usage status of 2.
    """
    monkeypatch.setattr(sys, "argv", ["veny", str(tmp_path / "no_such_script.py")])

    assert cli.main() == 2
