import logging
import subprocess
import sys
from pathlib import Path

import emmykit as ek

from veny import (
    alias_index,
    cache_search,
    environment,
    pipeline,
    state,
    venv_cache,
    verify,
)
from veny import cli as veny
from veny.analysis.imports import process_import
from veny.analysis.scan import _enqueue_top_level_imports
from veny.analysis.scan_state import ImportScan

from .test_state_values import a_requirements as _a_requirements
from .test_state_values import a_settings as _a_settings
from .test_state_values import a_target as _target


def test_tkinter_produces_one_system_package_warning(caplog):
    scan = ImportScan(seen_stdlib_imports={"tkinter", "os"})
    with caplog.at_level(logging.WARNING):
        pipeline.warn_about_system_packages(scan)
    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 1
    assert "tkinter" in messages[0]
    assert "python3-tk" in messages[0]


def test_no_warning_when_no_hint_module_was_seen(caplog):
    scan = ImportScan(seen_stdlib_imports={"os", "sys"})
    with caplog.at_level(logging.WARNING):
        pipeline.warn_about_system_packages(scan)
    assert caplog.records == []


def test_process_import_records_a_stdlib_skip(tmp_path):
    options = veny.Options()
    script = tmp_path / "user_script.py"
    script.write_text("import tkinter\n")
    # process_import takes an ImportScan and an injected is_stdlib predicate.
    # Phase 4a stopped seeding that scan from Options -- the seven fields are
    # the scan's own now -- so the assertion below reads the scan directly.
    scan = ImportScan()

    assert (
        process_import(scan, "tkinter", script, is_stdlib=options.stdlib.__contains__)
        is False
    )
    assert "tkinter" in scan.seen_stdlib_imports


def test_enqueue_top_level_imports_records_stdlib_and_skips_enqueue(tmp_path):
    from collections import deque

    options = veny.Options()
    module_path = tmp_path / "user_script.py"
    module_path.write_text("import tkinter\n")
    processed_paths: set[Path] = set()
    modules_to_process: deque[Path] = deque()
    scan = ImportScan()

    _enqueue_top_level_imports(
        scan,
        module_path,
        {"tkinter"},
        processed_paths,
        modules_to_process,
        is_stdlib=options.stdlib.__contains__,
    )

    assert "tkinter" in scan.seen_stdlib_imports
    assert len(modules_to_process) == 0


def test_options_no_longer_carries_an_alias_table():
    # The whole point of the change: the 1,219-line literal is gone, and with
    # it the reverse map whose {v: k} inversion silently dropped every import
    # name that shared a pip name with another.
    options = veny.Options()
    assert not hasattr(options, "module_aliases")
    assert not hasattr(options, "reversed_module_aliases")


def test_options_alias_index_is_offline_and_unprobed():
    # Options() is built in every test and on every --help run, before the
    # target interpreter is even known. If this were alias_index.build(), each
    # construction would fork a probe subprocess and open PyPI sockets.
    options = veny.Options()
    assert isinstance(options.aliases, alias_index.AliasIndex)
    assert options.aliases.pypi is None
    assert options.aliases.installed == {}


def test_resolved_import_record_carries_both_names():
    # The old code put pip names in one set and import names in another, so
    # every consumer had to guess which kind of string it held.
    record = veny.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    assert record.import_name == "cv2"
    assert record.pip_name == "opencv-python"


def test_the_offline_argument_keeps_the_index_off_the_network(monkeypatch, tmp_path):
    # build() has taken an offline flag since it was written and nothing ever
    # passed True, so there was no way to stop veny opening PyPI sockets --
    # on a plane, behind a blocked index, or in a sandbox without egress.
    options = veny.Options()
    options.my_dir = tmp_path
    monkeypatch.setattr(sys, "argv", ["veny.py", "--offline", "script.py"])

    veny.parse_arguments(options)

    assert options.args.offline is True
    assert (
        pipeline.build_alias_index(_a_settings(my_dir=tmp_path), options.args, "").pypi
        is None
    )


def test_the_index_reaches_pypi_by_default(monkeypatch, tmp_path):
    # The flag must be opt-in: defaulting to offline would silently drop the
    # only tier that can resolve a name veny has never seen before.
    options = veny.Options()
    options.my_dir = tmp_path
    monkeypatch.setattr(sys, "argv", ["veny.py", "script.py"])

    veny.parse_arguments(options)

    assert options.args.offline is False
    assert (
        pipeline.build_alias_index(_a_settings(my_dir=tmp_path), options.args, "").pypi
        is not None
    )


def _run_check_against_fake_venv(monkeypatch, importable: set[str], errors=None):
    """Simulate a real venv by executing the generated script for real.

    The generated script's own pass/fail logic (including the "any
    alternative may import" branching) runs unmodified; only
    ``importlib.import_module`` is stubbed, succeeding exactly for names in
    ``importable``. This exercises the actual boolean outcome, not just the
    names embedded in the source.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
        importable: Names that "import" successfully in the fake venv.
        errors: Optional import name -> ImportError message, for the cases where
            *why* an import failed is what is under test.
    """
    import contextlib
    import importlib
    import io

    def fake_import_module(name: str) -> None:
        if name not in importable:
            raise ImportError((errors or {}).get(name, name))

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    def fake_run(command, *args, **kwargs):
        source = command[-1]
        buf = io.StringIO()
        exit_code = 0
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(source, "<fake-venv-check>", "exec"), {})
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        return subprocess.CompletedProcess(
            command, exit_code, stdout=buf.getvalue(), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_check_venv_dir_rejects_a_manifest_match_whose_import_does_not_actually_import(
    monkeypatch, tmp_path
):
    # The manifest can say a package is there while the venv is actually
    # broken (a half-finished install, a corrupted site-packages). check_venv_dir
    # must not stop at the manifest match -- it has to run the same import-level
    # confirmation check_packages_in_venv performs, and reject the venv when
    # that fails, even though venv_cache.satisfies() alone would have accepted it.
    cached_dir = tmp_path / "cached-venv"
    cached_dir.mkdir()
    record = veny.ResolvedImport(import_name="thing", pip_name="thing-pkg")
    options = veny.Options()
    requirements = _a_requirements(
        all_imports=frozenset({"thing"}), uninstalled=frozenset({record})
    )
    venv_cache.write_manifest(
        cached_dir,
        venv_cache.Manifest(
            schema_version=venv_cache.SCHEMA_VERSION,
            created="20260814-091500",
            veny_version="0.2.2",
            interpreter_tag=cache_search.interpreter_tag(options.stdlib),
            interpreter_path="/usr/bin/python3",
            packages=(venv_cache.PackageRecord("thing", "thing-pkg", "1.0.0", None),),
        ),
    )
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python, timeout=30.0: ("3.12", {"thing": ["thing-pkg"]}),
    )
    # The manifest matches (same pip name, same interpreter tag) but nothing
    # actually imports in this venv.
    _run_check_against_fake_venv(monkeypatch, importable=set())

    assert (
        cache_search.check_venv_dir(
            cached_dir,
            wanted=cache_search.wanted_packages(
                set(requirements.uninstalled), requirements.extra_requirements
            ),
            tag=cache_search.interpreter_tag(options.stdlib),
            uninstalled=set(requirements.uninstalled),
            source_names=verify.source_import_names(
                set(requirements.all_imports),
                requirements.extra_requirements,
                getattr(options.args, "reqs", False),
            ),
            rawlog=True,
        )
        is False
    )


def test_setup_virtualenv_verifies_every_import_before_reporting_success(
    monkeypatch, tmp_path
):
    # The seam this task exists to close: resolve_and_verify was built and
    # tested but never called from production, so the cache was never written
    # and two of the five evidence tiers were unreachable. Nothing inside
    # either function could catch that -- only a test of the join can.
    options = veny.Options()
    requirements = _a_requirements(
        uninstalled=frozenset(
            {veny.ResolvedImport(import_name="thing", pip_name="thing-pkg")}
        )
    )
    calls = []
    monkeypatch.setattr(
        environment, "write_requirements_file_with_extras", lambda *args: None
    )
    monkeypatch.setattr(subprocess, "check_call", lambda *a, **k: 0)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 0),
    )

    # Both stubs carry verify's real signatures rather than *args: the
    # keywords are how setup_virtualenv wires them now, and a stub that
    # swallowed everything would keep passing after a mis-wiring.
    def fake_verify(*, uninstalled, **kwargs):
        calls.append("verify")
        return frozenset(uninstalled)

    def fake_check(
        venv_python, *, record=None, uninstalled=frozenset(), source_names=frozenset()
    ):
        calls.append("check")
        return True

    monkeypatch.setattr(verify, "verify_and_repair_imports", fake_verify)
    monkeypatch.setattr(verify, "check_packages_in_venv", fake_check)
    # record_venv_state probes the venv's real interpreter for installed
    # versions, which this test's fake subprocess.run cannot answer -- it is
    # unrelated to the ordering this test checks, so it is stubbed out too.
    # It returns the (possibly renamed) venv directory now, which
    # setup_virtualenv feeds straight to VenvHandle.for_dir, so the stub
    # hands back the directory it was given rather than None.
    monkeypatch.setattr(
        cache_search, "record_venv_state", lambda venv_dir, **kwargs: venv_dir
    )

    assert (
        pipeline.setup_virtualenv(
            _a_settings(my_dir=tmp_path),
            _target(),
            requirements,
            args=options.args,
            aliases=options.aliases,
            stdlib=options.stdlib,
        )[1]
        is not None
    )
    # Verification has to happen before the gate that drops the "failed-"
    # prefix, or its repairs cannot affect the answer.
    assert calls == ["verify", "check"]


def test_the_repair_installer_reports_failure_instead_of_exiting(monkeypatch, tmp_path):
    # install_into_venv drives a single `uv pip install` and, on a nonzero
    # return code, logs the error and returns False rather than raising or
    # exiting. resolve_and_verify's installer must not be able to end the
    # run: one unverifiable import is not a reason to kill everything.
    handle = state.VenvHandle.for_dir(tmp_path / "venv")

    def fake_run(command, *args, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr="no such package"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert (
        environment.install_into_venv(handle.venv_python, "nonexistent-package")
        is False
    )


def test_resolved_import_still_round_trips_when_alias_index_is_lazy():
    # Making the import lazy must not quietly turn the ResolvedImport and
    # AliasIndex handlers into dead code that falls through to str().
    record = veny.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    assert ek.from_jsonable(ek.to_jsonable(record)) == record


def test_alias_index_is_serialized_as_structured_data():
    # Serializing via str()/repr() turns lookups into substring matching, which
    # silently returns wrong answers instead of raising.
    index = alias_index.AliasIndex(
        overrides={"cv2": "my-opencv"},
        cache=alias_index.AliasCache(
            path=Path("/tmp/none.json"),
            interpreter_tag="3.12",
            entries={},
            rejections={},
        ),
        installed={},
        pypi=None,
    )
    payload = ek.to_jsonable(index)
    assert isinstance(payload, dict)
    assert payload["overrides"] == {"cv2": "my-opencv"}
    assert payload["interpreter_tag"] == "3.12"
    assert payload["cache_path"] == "/tmp/none.json"
    assert payload["offline"] is True


def test_resolved_import_round_trips_through_json():
    # uninstalled_imports is written to the last-used options file, which
    # check_venv_dir still reads for its venv_dir pointer. Without a handler
    # each record stringifies to "ResolvedImport(import_name='cv2', ...)",
    # losing the structured data that the rest of the file depends on.
    record = veny.ResolvedImport(import_name="cv2", pip_name="opencv-python")
    restored = ek.from_jsonable(ek.to_jsonable({record}))
    assert restored == {record}
