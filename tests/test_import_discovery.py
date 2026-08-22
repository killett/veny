"""Pin which imports veny's scan discovers, independent of I/O recording."""

import argparse
import contextlib
import logging
import os
import pickle
import sys
from pathlib import Path

import emmykit as ek
import pytest

from veny import alias_index, cli, pipeline, state, stdlib_index
from veny import settings as settings_module
from veny.analysis import custom_modules
from veny.analysis.scan_state import ImportScan

from .test_state_values import a_settings as _a_settings


@pytest.mark.parametrize(
    "timestamp",
    ["20240101-010101", "20260101-010101"],
    ids=["before-old-cutoff", "after-old-cutoff"],
)
def test_a_pickle_of_string_paths_loads_as_paths(
    tmp_path: Path, timestamp: str
) -> None:
    """A custom-modules pickle written with str paths loads back as Path values.

    Behaviour under test: dict_of_custom_modules() coerces every value it
    reads out of a cached pickle to a pathlib.Path, regardless of the
    timestamp encoded in the pickle's own filename.

    Concrete bug this catches: the removed date-comparison used to pick
    between two arms that both coerced str to Path -- one unconditionally,
    one only for values that were not already a Path. If the coercion were
    deleted along with the comparison (rather than just the comparison),
    this would come back with the plain str veny pickled, not a Path, and
    every consumer that compares these values against a Path -- like the
    same-directory import checks -- would silently stop matching. The two
    timestamps pin that the fix does not depend on the now-removed cutoff
    date: one predates the old cutoff, one postdates it, and both must
    coerce identically.
    """
    helper = tmp_path / "helper.py"
    cache = tmp_path / f".veny_custom_modules_{ek.COMPUTER_NAME}_{timestamp}.pkl"
    cache.write_bytes(pickle.dumps({"helper": str(helper)}))

    loaded = custom_modules.dict_of_custom_modules(
        _a_settings(cwd=tmp_path), use_cache=True
    )

    assert loaded == {"helper": helper}
    assert all(isinstance(v, Path) for v in loaded.values())


def _scan(script: Path, custom_modules: dict[str, Path]) -> ImportScan:
    """Run the import scan over one script and return what it found.

    Args:
        script:         The Python file to analyze.
        custom_modules: Local module name to file path, as the run would
                        supply -- the seeding the scanner reads to tell a
                        local module from a PyPI package.

    Returns:
        The ImportScan the scanner wrote its findings into.
    """
    scan = ImportScan(custom_modules=custom_modules)
    pipeline.find_imports_in_script(
        _a_settings(cwd=script.parent, rawlog=True),
        scan,
        script,
        is_stdlib=stdlib_index.for_running_interpreter().__contains__,
    )
    return scan


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
    scan = ImportScan(custom_modules={"helper": helper})

    with caplog.at_level(logging.INFO):
        pipeline.find_imports_in_script(
            _a_settings(cwd=tmp_path, rawlog=False),
            scan,
            script,
            is_stdlib=stdlib_index.for_running_interpreter().__contains__,
        )

    assert scan.all_imports == {"numpy"}
    assert f"Processing module: {script}" in caplog.text

    # And the other direction: a run that asked for raw logging must stay
    # quiet, so a hardcoded `rawlog=False` in that Settings is caught too.
    caplog.clear()
    quiet_scan = ImportScan(custom_modules={"helper": helper})

    with caplog.at_level(logging.INFO):
        pipeline.find_imports_in_script(
            _a_settings(cwd=tmp_path, rawlog=True),
            quiet_scan,
            script,
            is_stdlib=stdlib_index.for_running_interpreter().__contains__,
        )

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

    scan = _scan(script, {"helper": helper})

    assert scan.all_imports == {"numpy", "pandas", "requests"}
    assert scan.loaded_custom_modules == {"helper"}


def test_standard_library_imports_are_not_reported_as_needing_install(
    tmp_path: Path,
) -> None:
    """Stdlib names are recorded as seen, never as imports to install."""
    script = tmp_path / "s.py"
    script.write_text("import os\nimport json\nimport requests\n\nprint(os, json)\n")

    scan = _scan(script, {})

    assert scan.all_imports == {"requests"}
    assert {"os", "json"} <= scan.seen_stdlib_imports


def test_a_script_with_no_third_party_imports_yields_an_empty_import_set(
    tmp_path: Path,
) -> None:
    """The empty case is empty -- nothing is seeded into the import set."""
    script = tmp_path / "s.py"
    script.write_text("import sys\n\nprint(sys.version)\n")

    scan = _scan(script, {})

    assert scan.all_imports == set()


def test_a_prepopulated_custom_module_outside_the_script_dir_is_recognized(
    tmp_path: Path,
) -> None:
    """scan.custom_modules is seeded before the scan is ever reached.

    dict_of_custom_modules() populates scan.custom_modules before
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

    scan = _scan(script, {"faraway": faraway})

    assert scan.all_imports == set()
    assert scan.loaded_custom_modules == {"faraway"}


def _a_run_that_can_classify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[
    settings_module.Settings,
    argparse.Namespace,
    alias_index.AliasIndex,
    stdlib_index.StdlibIndex,
]:
    """A Settings, args, aliases and stdlib index list_packages can be driven with, off the network and off uv.

    Only two boundaries are replaced: the throwaway probe environment (a uv
    subprocess) and the alias index's network access. The scan, the stay-out
    filter and the classification copy-back are all real.

    Returns:
        The Settings, the args, the aliases and the stdlib index, in that
        order.
    """
    args = argparse.Namespace()
    aliases = alias_index.empty(tmp_path / "index")
    stdlib = stdlib_index.for_running_interpreter()
    # Not the default list: a substitution that reaches for a fresh Settings
    # would still exclude "myenv", and would look correct.
    settings = _a_settings(cwd=tmp_path, rawlog=False, stay_out_list=("keepout",))
    monkeypatch.setattr(
        pipeline,
        "_probe_venv",
        lambda target: contextlib.nullcontext(lambda import_name: False),
    )
    return settings, args, aliases, stdlib


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
    the wrong program; dropping the classification's result instead of
    returning it leaves requirements.uninstalled empty, so veny decides
    nothing needs installing and runs the script under an interpreter that cannot
    import what it needs. `extra-pkg` is asserted absent because --reqs was
    not given: use_reqs must be read from the flag, not assumed true.
    """
    project = tmp_path / "proj"
    project.mkdir()
    script = project / "s.py"
    script.write_text("import requests\n")
    settings, args, aliases, stdlib = _a_run_that_can_classify(tmp_path, monkeypatch)
    target = state.Target(
        python_script=script,
        script_dir=project,
        script_args=(),
        python_command="",
        timestamp="20260821-120000",
    )

    with caplog.at_level(logging.INFO):
        scan, requirements = pipeline.list_packages(
            settings,
            ImportScan(),
            target,
            args=args,
            aliases=aliases,
            extra_requirements={"extra-pkg": ">=2.0"},
            is_stdlib=stdlib.__contains__,
        )

    assert f"Processing a single Python script: {script}" in caplog.text
    # The scan comes back as a value, not as writes onto the Options.
    assert scan.all_imports == {"requests"}
    # Exactly {"requests"}: extra-pkg is an extra requirement, and without
    # --reqs it must not be folded into the imports the script needs.
    assert requirements.all_imports == {"requests"}
    assert {record.import_name for record in requirements.uninstalled} == {"requests"}


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
    settings, args, aliases, stdlib = _a_run_that_can_classify(tmp_path, monkeypatch)
    target = state.Target(
        python_script=script,
        script_dir=project,
        script_args=(),
        python_command="",
        timestamp="20260821-120000",
    )
    scan, requirements = pipeline.list_packages(
        settings,
        ImportScan(),
        target,
        args=args,
        aliases=aliases,
        extra_requirements={},
        is_stdlib=stdlib.__contains__,
    )

    with caplog.at_level(logging.INFO):
        pipeline.report(settings, scan, requirements)

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

    scan = _scan(script, {})

    assert scan.samedir_files == [project / "beside.py"]
    assert scan.subfolders == ["pkg"]
    assert hint_dir in scan.sys_path_hints


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
    args = argparse.Namespace(script=str(tmp_path), script_args=[])

    with pytest.raises(pipeline.UsageError) as excinfo:
        pipeline.resolve_target(args)

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
    missing = tmp_path / "no_such_script.py"
    args = argparse.Namespace(script=str(missing), script_args=[])

    with pytest.raises(pipeline.UsageError) as excinfo:
        pipeline.resolve_target(args)

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


def test_the_scan_list_packages_is_handed_is_the_one_it_fills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """list_packages must fill the seeded scan, not a fresh one of its own.

    Behaviour under test: that the ImportScan handed to list_packages is the
    object the scanner writes into, and the object list_packages returns.

    Concrete bug this catches: constructing a fresh ImportScan inside
    list_packages instead of threading the seeded one through. The scanner
    resolves a local import by looking the name up in scan.custom_modules,
    which dict_of_custom_modules filled before list_packages was ever
    reached; an empty dict makes every local module look like a PyPI package,
    so veny tries to pip install the user's own file. Expected values
    obtained by construction: one local helper, one real import.
    """
    helper = tmp_path / "my_helper.py"
    helper.write_text("import requests\n")
    script = tmp_path / "s.py"
    script.write_text("import my_helper\n\nmy_helper\n")
    settings, args, aliases, stdlib = _a_run_that_can_classify(tmp_path, monkeypatch)
    target = state.Target(
        python_script=script,
        script_dir=tmp_path,
        script_args=(),
        python_command="",
        timestamp="20260821-120000",
    )
    seeded = ImportScan(custom_modules={"my_helper": helper})

    returned, _ = pipeline.list_packages(
        settings,
        seeded,
        target,
        args=args,
        aliases=aliases,
        extra_requirements={},
        is_stdlib=stdlib.__contains__,
    )

    assert returned is seeded
    # The seeding was read: my_helper resolved to the local file rather than
    # being treated as a package, and the scan followed it to its own import.
    assert seeded.loaded_custom_modules == {"my_helper"}
    assert seeded.all_imports == {"requests"}


def test_a_file_that_is_not_python_is_a_usage_error_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real file that is not a Python script must come back as a status.

    Behaviour under test: what list_packages does when resolve_target let the
    path through -- ek.ensure_file accepts any file -- but the content is not
    a script.

    Concrete bug this catches: the ValueError this used to raise travelled
    uncaught out of main(), so `veny notes.txt` printed a traceback and
    exited 1. It is now pipeline.UsageError, which cli.main maps to 2. This
    is the third of phase 4a's sanctioned behaviour changes and the only one
    the plan did not name; it was found by the whole-branch review, and both
    trees were run to confirm the old status was 1 and the new one is 2.
    """
    not_python = tmp_path / "notes.txt"
    not_python.write_text("this is not python\n")
    monkeypatch.setattr(sys, "argv", ["veny", os.fspath(not_python)])

    assert cli.main() == 2
