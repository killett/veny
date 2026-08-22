"""Characterization tests for veny's import classification, before it moves.

These pin what ``pipeline.split_imports`` and ``classify.add_dependencies`` do
*today*, so the extraction of ``veny/classify.py`` is a move rather than a
rewrite. (They were written against ``cli.add_dependencies``, which task 4
left with no production callers; the whole-branch review deleted that adapter
and repointed them here, assertions untouched.)
Every expected value here was obtained by running the code at ``d79eba4``,
never by reading it and predicting an answer.

The probe venv is stubbed in every test: ``environment.create_venv`` and
``environment.venv_build_interpreter`` (the module that owns every ``uv``
call since phase 3c task 2) and ``verify.check_packages_in_venv``. Nothing here
builds an environment, runs a subprocess, or touches the network -- the alias
indexes below are constructed with ``pypi=None`` and an unreachable cache
path, so resolution is fully determined by the test. The tests migrated from
``tests/test_split_imports.py`` in task 4 keep to the same rule: the one that
pins the probe venv's interpreter stubs ``subprocess.check_call`` and
inspects the uv command instead of running it.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from veny import (
    alias_index,
    classify,
    environment,
    pipeline,
    stdlib_index,
    verify,
)
from veny import settings as settings_module
from veny.alias_index import ResolvedImport
from veny.analysis.scan_state import ImportScan
from veny.state import Requirements

from .test_state_values import a_settings as _a_settings
from .test_state_values import a_target as _target


def _index(overrides: dict[str, str] | None = None) -> alias_index.AliasIndex:
    """Build an offline AliasIndex that resolves only from the given overrides.

    Args:
        overrides: import name -> pip name mapping to seed the index with.

    Returns:
        An AliasIndex with no PyPI client, no seed and an unreachable cache
        path, so nothing outside the test can influence a resolution.
    """
    return alias_index.AliasIndex(
        overrides=dict(overrides or {}),
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


class _RecordingIndex(alias_index.AliasIndex):
    """An offline AliasIndex that records every name it is asked to resolve.

    Attributes:
        resolved: Import names passed to resolve(), in call order.
    """

    def __init__(self, overrides: dict[str, str] | None = None) -> None:
        """Initialize an offline index that logs its resolve() calls.

        Args:
            overrides: import name -> pip name mapping to seed the index with.
        """
        base = _index(overrides)
        super().__init__(
            overrides=base.overrides,
            cache=base.cache,
            installed={},
            pypi=None,
            seed={},
        )
        self.resolved: list[str] = []

    def resolve(self, import_name: str) -> alias_index.Resolution:
        """Record the request, then resolve it exactly as the base class does.

        Args:
            import_name: The import name to resolve.

        Returns:
            The base class's Resolution for that name.
        """
        self.resolved.append(import_name)
        return super().resolve(import_name)


def _stub_probe(
    monkeypatch: pytest.MonkeyPatch, installed: frozenset[str] = frozenset()
) -> tuple[list[tuple[str, str]], list[str]]:
    """Replace the probe venv with recorders, so no environment is built.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
        installed:   Import names the fake probe venv reports as importable.

    Returns:
        A (created, probed) pair of lists, filled as split_imports runs:
        created gets one (venv_dir, interpreter) entry per probe venv build,
        probed gets the import name of every record handed to the venv check.
    """
    created: list[tuple[str, str]] = []
    probed: list[str] = []

    def fake_create_venv(target: object, python: str = "") -> bool:
        created.append((str(target), python))
        return True

    def fake_check(
        venv_python: object,
        *,
        record: ResolvedImport | None = None,
        uninstalled: object = frozenset(),
        source_names: object = frozenset(),
    ) -> bool:
        assert record is not None
        probed.append(record.import_name)
        return record.import_name in installed

    monkeypatch.setattr(environment, "create_venv", fake_create_venv)
    monkeypatch.setattr(
        environment, "venv_build_interpreter", lambda command: "/fake/python"
    )
    monkeypatch.setattr(verify, "check_packages_in_venv", fake_check)
    return created, probed


def _capture_split_imports_result(
    monkeypatch: pytest.MonkeyPatch,
) -> list[Requirements]:
    """Record every Requirements that classify.split_imports returns.

    pipeline.split_imports no longer copies ``result.installed`` onto Options --
    phase 3d task 8 deleted that write-only mirror -- so a test that needs to
    see which imports were classified as installed has to read it off the
    Requirements classify.split_imports itself produces, captured here as
    pipeline.split_imports calls it internally.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        A list that gains one Requirements per classify.split_imports call.
    """
    captured: list[Requirements] = []
    real_split_imports = classify.split_imports

    def _recording(*args: Any, **kwargs: Any) -> Requirements:
        result = real_split_imports(*args, **kwargs)
        captured.append(result)
        return result

    monkeypatch.setattr(classify, "split_imports", _recording)
    return captured


def test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A custom module is not probed, not resolved, and joins neither set.

    The three-way branch is what makes all_imports a strict superset of
    installed | uninstalled. Concrete bug this catches: drop the
    ``if imp in scan.custom_modules.keys()`` branch and the user's own
    local module falls through to the venv check, fails it, gets resolved
    against the alias index and lands in uninstalled_imports -- so veny asks
    pip to install the script sitting next to the one being run.
    """
    index = _RecordingIndex({"uninst": "uninst-pypi"})
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(
        all_imports={"mymod", "inst", "uninst"},
        custom_modules={"mymod": Path("/x/mymod.py")},
    )
    created, probed = _stub_probe(monkeypatch, installed=frozenset({"inst"}))
    results = _capture_split_imports_result(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=argparse.Namespace(),
        aliases=index,
        extra_requirements=extra_requirements,
    )

    assert results[-1].installed == {
        ResolvedImport(import_name="inst", pip_name="inst")
    }
    assert requirements.uninstalled == {
        ResolvedImport(import_name="uninst", pip_name="uninst-pypi")
    }
    # The custom module survives in all_imports but is in neither set, and was
    # never offered to the venv check or to the resolver.
    assert requirements.all_imports == {"mymod", "inst", "uninst"}
    assert sorted(probed) == ["inst", "uninst"]
    assert index.resolved == ["uninst"]
    assert len(created) == 1


def test_no_source_imports_means_no_probe_venv_is_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing to classify, split_imports returns before building a venv.

    Concrete bug this catches: delete the ``if not total_imports:
    return`` early return and the empty run walks on into the formatting
    widths, where ``max(len(imp) for imp in all_imports)`` raises
    ValueError on the empty set -- and, were that survivable, would pay for a
    real ``uv venv`` on a run with no imports at all.
    """
    aliases = _RecordingIndex()
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports=set())
    created, probed = _stub_probe(monkeypatch)
    results = _capture_split_imports_result(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=argparse.Namespace(),
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert created == []
    assert probed == []
    assert len(requirements.all_imports) == 0
    assert results[-1].installed == set()
    assert requirements.uninstalled == set()


def test_a_run_whose_every_import_is_bad_builds_no_probe_venv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad imports are subtracted before the count, so an all-bad run stops early.

    Concrete bug this catches: move the ``all_imports -= bad_imports``
    subtraction after ``total_imports = len(all_imports)`` and this
    run reports two imports, builds a probe venv, and asks it about
    ``httplib`` -- a Python 2 name that can only ever fail.
    """
    aliases = _RecordingIndex()
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports={"httplib", "DQN"})
    created, probed = _stub_probe(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=argparse.Namespace(),
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert requirements.bad == {"httplib", "DQN"}
    assert requirements.all_imports == set()
    assert len(requirements.all_imports) == 0
    assert created == []
    assert probed == []


def test_bad_imports_never_reach_the_probe_venv_or_the_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad imports leave all_imports and are never probed or resolved.

    Concrete bug this catches: drop the ``all_imports -
    requirements.bad`` assignment and ``httplib``, ``_private`` and the
    project's known-bad ``DQN`` are all probed, resolved through the alias
    index, and handed to pip as install targets.
    """
    index = _RecordingIndex({"widgetlib": "widget-lib-pypi"})
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports={"httplib", "_private", "DQN", "widgetlib"})
    created, probed = _stub_probe(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=argparse.Namespace(),
        aliases=index,
        extra_requirements=extra_requirements,
    )

    assert requirements.bad == {"httplib", "_private", "DQN"}
    assert requirements.all_imports == {"widgetlib"}
    assert len(requirements.all_imports) == 1
    assert probed == ["widgetlib"]
    assert index.resolved == ["widgetlib"]
    assert requirements.uninstalled == {
        ResolvedImport(import_name="widgetlib", pip_name="widget-lib-pypi")
    }
    assert len(created) == 1


def test_reqs_requirements_are_counted_before_the_zero_import_early_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--reqs names join all_imports before the count, so they alone build the probe.

    Concrete bug this catches: take ``total_imports = len(all_imports)``
    before folding ``extra_requirements`` in, and a run with no source imports
    but a populated requirements file returns at the early return -- the
    requirements are never probed, never classified, and silently install
    nothing.
    """
    aliases = _RecordingIndex()
    scan = ImportScan(all_imports=set())
    extra_requirements = {"requests": None, "rich": "==13.0"}
    args = argparse.Namespace(reqs=True)
    created, probed = _stub_probe(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=args,
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert requirements.all_imports == {"requests", "rich"}
    assert len(requirements.all_imports) == 2
    assert len(created) == 1
    assert sorted(probed) == ["requests", "rich"]


def test_reqs_records_are_unioned_in_after_the_loop_with_import_name_as_pip_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement names are added again after the loop, spelled as pip sees them.

    A requirements file already holds pip names, and nothing maps a pip name
    back to an import name, so requirement_records keeps the file's own
    spelling on both halves of the record. Measured today: the same name
    therefore yields *two* records when the alias index renames it -- the
    resolved one from the classification loop and the verbatim one from the
    file. Concrete bug this catches: swap requirement_records for
    resolve_records (or fold the requirements in before the loop instead of
    after) and the verbatim record disappears, so the exact string the user
    pinned in extra_requirements.txt is never the string handed to pip.
    """
    aliases = _RecordingIndex({"widgetlib": "widget-lib-pypi"})
    scan = ImportScan(all_imports=set())
    extra_requirements = {"widgetlib": None}
    args = argparse.Namespace(reqs=True)
    _stub_probe(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=args,
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert requirements.uninstalled == {
        ResolvedImport(import_name="widgetlib", pip_name="widget-lib-pypi"),
        ResolvedImport(import_name="widgetlib", pip_name="widgetlib"),
    }


def test_a_requirement_already_importable_in_the_probe_is_recorded_in_both_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The post-loop --reqs union ignores what the probe venv found.

    Measured today: a requirement the probe venv can already import is filed
    as installed *and* re-added as uninstalled, because the union after the
    loop is unconditional. Concrete bug this catches: make the union
    conditional on the probe result (e.g. subtract installed_imports) and this
    record vanishes from uninstalled_imports -- which would drop a package the
    user explicitly pinned from the requirements file veny writes.
    """
    aliases = _RecordingIndex()
    scan = ImportScan(all_imports=set())
    extra_requirements = {"reqonly": None}
    args = argparse.Namespace(reqs=True)
    _stub_probe(monkeypatch, installed=frozenset({"reqonly"}))
    results = _capture_split_imports_result(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=args,
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert results[-1].installed == {
        ResolvedImport(import_name="reqonly", pip_name="reqonly")
    }
    assert requirements.uninstalled == {
        ResolvedImport(import_name="reqonly", pip_name="reqonly")
    }


def test_total_imports_equals_the_size_of_all_imports_when_split_imports_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counter and the set agree on exit, with every branch exercised at once.

    One run carrying a custom module, an installed import, an uninstalled
    import, a bad import and a --reqs requirement. Concrete bug this catches:
    any later step that mutates all_imports after the count is taken -- adding
    the requirement names after ``total_imports`` is read, or subtracting bad
    imports there -- makes the progress display count to the wrong total and
    breaks the equality task 4 turns into a property.
    """
    aliases = _RecordingIndex({"uninst": "uninst-pypi"})
    scan = ImportScan(
        all_imports={"mymod", "inst", "uninst", "httplib"},
        custom_modules={"mymod": Path("/x/mymod.py")},
    )
    extra_requirements = {"reqpkg": None}
    args = argparse.Namespace(reqs=True)
    _stub_probe(monkeypatch, installed=frozenset({"inst"}))
    results = _capture_split_imports_result(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=args,
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert requirements.all_imports == {"mymod", "inst", "uninst", "reqpkg"}
    assert len(requirements.all_imports) == 4
    # all_imports is a strict superset of the two classified sets: the custom
    # module is in neither, and the bad import is in none of the three.
    classified = {record.import_name for record in results[-1].installed} | {
        record.import_name for record in requirements.uninstalled
    }
    assert classified == {"inst", "uninst", "reqpkg"}
    assert classified < requirements.all_imports


def test_add_dependencies_expands_a_nested_dependency_chain_to_a_fixed_point() -> None:
    """also_needs is followed transitively until nothing new is added.

    Concrete bug this catches: delete the ``while added:`` loop that follows
    the first pass and only the direct dependency ``b`` is added -- ``c`` and
    ``d`` are never installed, so a package pulled in as a dependency of a
    dependency is missing from the venv veny reports as complete.
    """
    expanded = classify.add_dependencies(
        {ResolvedImport(import_name="a", pip_name="a")},
        also_needs={"a": ["b"], "b": ["c"], "c": ["d"]},
        aliases=_index(),
        rawlog=False,
    )

    assert expanded == {
        ResolvedImport(import_name="a", pip_name="a"),
        ResolvedImport(import_name="b", pip_name="b"),
        ResolvedImport(import_name="c", pip_name="c"),
        ResolvedImport(import_name="d", pip_name="d"),
    }


def test_add_dependencies_resolves_dependency_names_through_the_alias_index() -> None:
    """A dependency's pip name is the resolved one, not the bare import name.

    Concrete bug this catches: add the dependency as
    ``ResolvedImport(import_name=name, pip_name=name)`` instead of routing it
    through resolve_records and veny runs ``pip install widgetlib`` for a
    package whose distribution is named ``widget-lib-pypi`` -- the exact
    failure the import-name/pip-name split exists to prevent (Options'
    also_needs comment states both keys and values are *import* names).
    """
    expanded = classify.add_dependencies(
        {ResolvedImport(import_name="toplevel", pip_name="toplevel")},
        also_needs={"toplevel": ["widgetlib"]},
        aliases=_index({"widgetlib": "widget-lib-pypi"}),
        rawlog=False,
    )

    assert expanded == {
        ResolvedImport(import_name="toplevel", pip_name="toplevel"),
        ResolvedImport(import_name="widgetlib", pip_name="widget-lib-pypi"),
    }


def test_add_dependencies_matches_also_needs_on_the_import_name_not_the_pip_name() -> (
    None
):
    """also_needs is keyed by import name; a pip-name key matches nothing.

    Concrete bug this catches: key the lookup on ``record.pip_name`` and every
    entry in the shipped also_needs table (``xarray``, ``litellm`` -- import
    names) stops matching for any record whose pip name differs, while a
    table written in pip names would start matching. Either way the wrong set
    of dependencies is installed.
    """
    expanded = classify.add_dependencies(
        {ResolvedImport(import_name="widgetlib", pip_name="widget-lib-pypi")},
        also_needs={"widget-lib-pypi": ["dep"]},
        aliases=_index(),
        rawlog=False,
    )

    assert expanded == {
        ResolvedImport(import_name="widgetlib", pip_name="widget-lib-pypi")
    }


def test_split_imports_expands_also_needs_onto_the_uninstalled_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run's also_needs table reaches classification through pipeline.split_imports.

    The three tests above drive ``classify.add_dependencies`` directly, so
    none of them touches the wiring that hands it ``options.also_needs``.
    This one goes the whole way through the adapter production uses.

    Concrete bug this catches: pass ``also_needs={}`` (or drop the argument)
    at ``pipeline.split_imports``' call into ``classify.split_imports`` and every
    dependency veny's shipped table declares silently stops being installed --
    the venv is reported complete while the package that makes ``uninst``
    usable is absent. The chain is nested on purpose: no entry in veny's own
    shipped also_needs table (``settings.DEFAULT_ALSO_NEEDS``) is, so the
    ``while added`` fixed point is otherwise never exercised on the path a
    user takes.
    """
    aliases = _index({"uninst": "uninst-pypi", "deepdep": "deep-dep-pypi"})
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports={"uninst"})
    settings = _a_settings(
        rawlog=False,
        also_needs={"uninst": ("depmod",), "depmod": ("deepdep",)},
    )
    _stub_probe(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        settings,
        scan,
        target,
        args=argparse.Namespace(),
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert requirements.uninstalled == {
        ResolvedImport(import_name="uninst", pip_name="uninst-pypi"),
        ResolvedImport(import_name="depmod", pip_name="depmod"),
        ResolvedImport(import_name="deepdep", pip_name="deep-dep-pypi"),
    }
    # The dependencies are records only -- they are not source imports, so they
    # never join all_imports and never change the run's count.
    assert requirements.all_imports == {"uninst"}


# --- Migrated from tests/test_split_imports.py by phase 3c task 4. ---------
# These pin the same behaviour they always did; only their call sites moved
# with the code. The three _compute_bad_imports tests now name classify's
# copy of the function, and the three that patched the *stdlib* venv.create
# -- which production stopped calling when task 2 extracted environment.py,
# so they had been building a real uv venv on every run -- now patch
# environment.create_venv, the function pipeline._probe_venv actually calls.


def test_python2_name_is_classified_bad():
    bad = classify._compute_bad_imports(
        {"httplib", "numpy"}, set(), stdlib_index.PYTHON2_ONLY
    )
    assert bad == {"httplib"}


def test_leading_underscore_name_is_classified_bad():
    bad = classify._compute_bad_imports({"_private_thing", "numpy"}, set(), frozenset())
    assert bad == {"_private_thing"}


def test_ordinary_import_is_not_classified_bad():
    bad = classify._compute_bad_imports(
        {"numpy", "xarray"}, {"DQN"}, stdlib_index.PYTHON2_ONLY
    )
    assert bad == set()


def test_seaborn_tkinter_and_msvcrt_are_no_longer_blocked():
    blocked = settings_module.DEFAULT_KNOWN_BAD_IMPORTS
    assert blocked == {
        "snakeClass",
        "GPUampcor",
        "pathfinding_salvo_rework",
        "DQN",
        "bayesOpt",
        "non_existent_module",
    }


def test_split_imports_wires_python2_table_end_to_end():
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports={"httplib", "_private_thing"})
    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=argparse.Namespace(),
        aliases=_index(),
        extra_requirements=extra_requirements,
    )
    assert requirements.bad == {"httplib", "_private_thing"}
    assert requirements.all_imports == set()


def test_split_imports_stores_both_names_on_the_record(monkeypatch):
    # The bug this retires: split_imports used to add the *pip* name to
    # uninstalled_imports, so downstream import checks were handed
    # "widget-lib-pypi" when they needed "widgetlib".
    aliases = _index({"widgetlib": "widget-lib-pypi"})
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports={"widgetlib"})
    _stub_probe(monkeypatch)
    results = _capture_split_imports_result(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=argparse.Namespace(),
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert requirements.uninstalled == {
        ResolvedImport(import_name="widgetlib", pip_name="widget-lib-pypi")
    }
    assert results[-1].installed == set()


def test_split_imports_falls_back_to_the_import_name_when_nothing_resolves(monkeypatch):
    # An unresolvable import must still be recorded, not crash on
    # candidates[0] and not vanish from the install list.
    aliases = _index({})
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports={"mysterylib"})
    _stub_probe(monkeypatch)

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=argparse.Namespace(),
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert requirements.uninstalled == {
        ResolvedImport(import_name="mysterylib", pip_name="mysterylib")
    }


def test_split_imports_probe_venv_is_given_the_classified_interpreter(monkeypatch):
    """split_imports' probe venv must be built with the interpreter imports
    were classified against, not whatever uv's own discovery order picks.

    Before this fix, split_imports called create_venv(venv_dir) with no
    interpreter argument. `uv venv` with no --python resolves through uv's
    own discovery order, which was measured to disagree with the interpreter
    veny classified imports against (uv picked 3.12 while PATH's python3 was
    3.13). A stdlib module removed in 3.13 (e.g. `cgi`) then imports
    successfully in the mismatched 3.12 probe venv and gets marked
    "installed", even though it is not installed -- and not installable --
    for the interpreter the venv is actually built with. If this regresses
    to create_venv(venv_dir) with no second argument, the captured uv
    command below carries no --python flag at all and this test fails.
    """
    target = _target(python_command="python3")
    aliases = _index({})
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports={"widgetlib"})
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
    monkeypatch.setattr(verify, "check_packages_in_venv", lambda *a, **k: False)

    pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=argparse.Namespace(),
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert len(captured) == 1, "expected exactly one probe venv build"
    probe_command = captured[0]
    assert "--python" in probe_command
    python_index = probe_command.index("--python")
    assert probe_command[python_index + 1] == "/resolved/bin/python3"


def test_the_classification_adapter_lets_classify_report_each_import(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """pipeline.split_imports must hand classify this run's rawlog, not a constant.

    Measured 2026-08-19 across all 17 `rawlog=` sites in
    cli/cache_search/last_used/verify: substituting the wrong-but-type-correct
    `True` -- a value the STANDING CHECK's own stated method covers -- left 16
    of them with the whole suite green, this one included, because every test
    that reaches this adapter asserts on the classification it returns and
    none reads a log record.

    Concrete bug this catches: `rawlog=True` here silences the per-import
    "Checking import X : n/N - YES/NO" running commentary, which is the only
    thing veny prints while the slowest part of a cold run (a PyPI lookup per
    unresolved name) is happening. A user watching a stalled terminal has no
    way to tell which import it is stuck on.
    """
    aliases = _index({"uninst": "uninst-pypi"})
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports={"uninst"})
    _stub_probe(monkeypatch)

    with caplog.at_level(logging.INFO):
        target = _target()
        pipeline.split_imports(
            _a_settings(rawlog=False),
            scan,
            target,
            args=argparse.Namespace(),
            aliases=aliases,
            extra_requirements=extra_requirements,
        )

    assert "Checking import uninst" in caplog.text

    # And the other direction: a run that asked for raw logging must stay
    # quiet, so a hardcoded `rawlog=False` at that call site is caught too.
    caplog.clear()
    quiet_aliases = _index({"uninst": "uninst-pypi"})
    scan = ImportScan(all_imports={"uninst"})

    with caplog.at_level(logging.INFO):
        pipeline.split_imports(
            _a_settings(rawlog=True),
            scan,
            target,
            args=argparse.Namespace(),
            aliases=quiet_aliases,
            extra_requirements=extra_requirements,
        )

    assert "Checking import" not in caplog.text


def test_only_genuinely_uninstalled_imports_are_resolved(monkeypatch):
    # resolve() ran before both the custom-module check and the installed
    # check, so every import paid for resolution before veny knew whether it
    # needed a pip name at all. An unresolved name costs up to six PyPI project
    # lookups (the name plus five mutations), each a metadata request plus up
    # to two ranged wheel reads, at a 10 s read timeout. A local custom module
    # never needs a pip name, and neither does an import that is installed.
    index = _RecordingIndex({"missingthing": "missing-thing-pypi"})
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(
        all_imports={"mycustom", "alreadyhere", "missingthing"},
        custom_modules={"mycustom": Path("/nowhere/mycustom.py")},
    )
    _stub_probe(monkeypatch, installed=frozenset({"alreadyhere"}))

    target = _target()
    requirements = pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=argparse.Namespace(),
        aliases=index,
        extra_requirements=extra_requirements,
    )

    assert index.resolved == ["missingthing"]
    assert requirements.uninstalled == {
        ResolvedImport(import_name="missingthing", pip_name="missing-thing-pypi")
    }


def test_a_refused_probe_venv_stops_classification_instead_of_probing_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_venv returning False makes _probe_venv raise VenvBuildFailed.

    Behaviour under test: the second consumer of phase 3e task 7's bool
    contract. Concrete bug this catches: leaving the call as a bare
    `environment.create_venv(...)` means a refused probe build is never
    noticed, and the predicate goes on asking check_packages_in_venv about an
    interpreter path inside a directory that holds no environment.
    check_packages_in_venv does not catch OSError, so its subprocess.run dies
    with `FileNotFoundError: .../bin/python` -- measured by reverting this
    guard, which is exactly how this test fails -- and the user gets a
    traceback naming a temporary directory instead of a sentence naming the
    problem. Expected value obtained from the design's error handling: the
    probe has no fallback, so it raises the exception cli.main maps to 1
    rather than dying inside the predicate.

    check_packages_in_venv is deliberately left unstubbed: reaching it at all
    would mean the guard did not stop the probe, and the assertion below would
    not be what failed.
    """
    aliases = _index({})
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports={"widgetlib"})
    monkeypatch.setattr(environment, "create_venv", lambda target, python="": False)

    with pytest.raises(pipeline.VenvBuildFailed) as caught:
        target = _target()
        pipeline.split_imports(
            _a_settings(rawlog=False),
            scan,
            target,
            args=argparse.Namespace(),
            aliases=aliases,
            extra_requirements=extra_requirements,
        )

    assert "throwaway environment" in str(caught.value)


def test_the_probe_venv_is_asked_about_the_interpreter_it_just_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pipeline._probe_venv must check imports inside the venv it created, not elsewhere.

    _probe_venv creates a throwaway venv and closes over its directory; the
    is_importable predicate then builds an interpreter path from that same
    directory with environment.venv_python_for. Measured by substitution:
    both halves of that wiring -- the directory handed to create_venv and the
    interpreter handed to check_packages_in_venv -- could be replaced with a
    fixed foreign path and all 338 tests stayed green, because every other
    probe test stubs the check and ignores which interpreter it was given.

    Concrete bug this catches: the probe answers from the interpreter running
    veny instead of the empty throwaway venv, so every import already
    installed alongside veny is classified "installed" and never installed
    into the venv the user's script actually runs in -- the same class of
    defect as the 3.12/3.13 `cgi` mismatch PROGRESS records, but total rather
    than version-dependent.
    """
    aliases = _index({})
    extra_requirements: dict[str, str | None] = {}
    scan = ImportScan(all_imports={"widgetlib"})
    created: list[Path] = []
    asked: list[Path] = []

    def fake_create_venv(target: object, python: str = "") -> bool:
        """Record the probe venv's directory and report the build succeeded."""
        created.append(Path(str(target)))
        return True

    monkeypatch.setattr(environment, "create_venv", fake_create_venv)

    def fake_check(venv_python, *, record=None, **kwargs):
        assert record is not None, "the probe checks one record at a time"
        asked.append(Path(venv_python))
        return False

    monkeypatch.setattr(verify, "check_packages_in_venv", fake_check)

    target = _target()
    pipeline.split_imports(
        _a_settings(rawlog=False),
        scan,
        target,
        args=argparse.Namespace(),
        aliases=aliases,
        extra_requirements=extra_requirements,
    )

    assert len(created) == 1, "exactly one probe venv is built"
    # VenvHandle's documented shape, written out rather than read
    # back through venv_python_for -- the directory is gone by now.
    assert asked == [created[0] / "bin" / "python"]
