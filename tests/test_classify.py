"""Characterization tests for veny's import classification, before it moves.

These pin what ``cli.split_imports`` and ``classify.add_dependencies`` do
*today*, so the extraction of ``veny/classify.py`` is a move rather than a
rewrite. (They were written against ``cli.add_dependencies``, which task 4
left with no production callers; the whole-branch review deleted that adapter
and repointed them here, assertions untouched.)
Every expected value here was obtained by running the code at ``d79eba4``,
never by reading it and predicting an answer.

The probe venv is stubbed in every test: ``environment.create_venv`` and
``environment.venv_build_interpreter`` (the module that owns every ``uv``
call since phase 3c task 2) and ``cli.check_packages_in_venv``. Nothing here
builds an environment, runs a subprocess, or touches the network -- the alias
indexes below are constructed with ``pypi=None`` and an unreachable cache
path, so resolution is fully determined by the test. The tests migrated from
``tests/test_split_imports.py`` in task 4 keep to the same rule: the one that
pins the probe venv's interpreter stubs ``subprocess.check_call`` and
inspects the uv command instead of running it.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest

from veny import alias_index, classify, cli, environment, stdlib_index
from veny.alias_index import ResolvedImport


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

    def fake_create_venv(target: object, python: str = "") -> None:
        created.append((str(target), python))

    def fake_check(
        options: cli.Options,
        record: ResolvedImport | None = None,
        venv_dir: object = None,
        source_names: object = None,
    ) -> bool:
        assert record is not None
        probed.append(record.import_name)
        return record.import_name in installed

    monkeypatch.setattr(environment, "create_venv", fake_create_venv)
    monkeypatch.setattr(
        environment, "venv_build_interpreter", lambda command: "/fake/python"
    )
    monkeypatch.setattr(cli, "check_packages_in_venv", fake_check)
    return created, probed


def test_a_custom_module_is_classified_as_neither_installed_nor_uninstalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A custom module is not probed, not resolved, and joins neither set.

    The three-way branch is what makes all_imports a strict superset of
    installed | uninstalled. Concrete bug this catches: drop the
    ``if imp in options.custom_modules.keys()`` branch and the user's own
    local module falls through to the venv check, fails it, gets resolved
    against the alias index and lands in uninstalled_imports -- so veny asks
    pip to install the script sitting next to the one being run.
    """
    options = cli.Options()
    index = _RecordingIndex({"uninst": "uninst-pypi"})
    options.aliases = index
    options.all_imports = {"mymod", "inst", "uninst"}
    options.custom_modules = {"mymod": Path("/x/mymod.py")}
    created, probed = _stub_probe(monkeypatch, installed=frozenset({"inst"}))

    cli.split_imports(options)

    assert options.installed_imports == {
        ResolvedImport(import_name="inst", pip_name="inst")
    }
    assert options.uninstalled_imports == {
        ResolvedImport(import_name="uninst", pip_name="uninst-pypi")
    }
    # The custom module survives in all_imports but is in neither set, and was
    # never offered to the venv check or to the resolver.
    assert options.all_imports == {"mymod", "inst", "uninst"}
    assert sorted(probed) == ["inst", "uninst"]
    assert index.resolved == ["uninst"]
    assert len(created) == 1


def test_no_source_imports_means_no_probe_venv_is_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing to classify, split_imports returns before building a venv.

    Concrete bug this catches: delete the ``if not options.total_imports:
    return`` early return and the empty run walks on into the formatting
    widths, where ``max(len(imp) for imp in options.all_imports)`` raises
    ValueError on the empty set -- and, were that survivable, would pay for a
    real ``uv venv`` on a run with no imports at all.
    """
    options = cli.Options()
    options.aliases = _RecordingIndex()
    options.all_imports = set()
    created, probed = _stub_probe(monkeypatch)

    cli.split_imports(options)

    assert created == []
    assert probed == []
    assert options.total_imports == 0
    assert options.installed_imports == set()
    assert options.uninstalled_imports == set()


def test_a_run_whose_every_import_is_bad_builds_no_probe_venv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad imports are subtracted before the count, so an all-bad run stops early.

    Concrete bug this catches: move the ``all_imports -= bad_imports``
    subtraction after ``total_imports = len(options.all_imports)`` and this
    run reports two imports, builds a probe venv, and asks it about
    ``httplib`` -- a Python 2 name that can only ever fail.
    """
    options = cli.Options()
    options.aliases = _RecordingIndex()
    options.all_imports = {"httplib", "DQN"}
    created, probed = _stub_probe(monkeypatch)

    cli.split_imports(options)

    assert options.bad_imports == {"httplib", "DQN"}
    assert options.all_imports == set()
    assert options.total_imports == 0
    assert created == []
    assert probed == []


def test_bad_imports_never_reach_the_probe_venv_or_the_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad imports leave all_imports and are never probed or resolved.

    Concrete bug this catches: drop the ``options.all_imports -
    options.bad_imports`` assignment and ``httplib``, ``_private`` and the
    project's known-bad ``DQN`` are all probed, resolved through the alias
    index, and handed to pip as install targets.
    """
    options = cli.Options()
    index = _RecordingIndex({"widgetlib": "widget-lib-pypi"})
    options.aliases = index
    options.all_imports = {"httplib", "_private", "DQN", "widgetlib"}
    created, probed = _stub_probe(monkeypatch)

    cli.split_imports(options)

    assert options.bad_imports == {"httplib", "_private", "DQN"}
    assert options.all_imports == {"widgetlib"}
    assert options.total_imports == 1
    assert probed == ["widgetlib"]
    assert index.resolved == ["widgetlib"]
    assert options.uninstalled_imports == {
        ResolvedImport(import_name="widgetlib", pip_name="widget-lib-pypi")
    }
    assert len(created) == 1


def test_reqs_requirements_are_counted_before_the_zero_import_early_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--reqs names join all_imports before the count, so they alone build the probe.

    Concrete bug this catches: take ``total_imports = len(options.all_imports)``
    before folding ``extra_requirements`` in, and a run with no source imports
    but a populated requirements file returns at the early return -- the
    requirements are never probed, never classified, and silently install
    nothing.
    """
    options = cli.Options()
    options.aliases = _RecordingIndex()
    options.all_imports = set()
    options.extra_requirements = {"requests": None, "rich": "==13.0"}
    options.args = argparse.Namespace(reqs=True)
    created, probed = _stub_probe(monkeypatch)

    cli.split_imports(options)

    assert options.all_imports == {"requests", "rich"}
    assert options.total_imports == 2
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
    options = cli.Options()
    options.aliases = _RecordingIndex({"widgetlib": "widget-lib-pypi"})
    options.all_imports = set()
    options.extra_requirements = {"widgetlib": None}
    options.args = argparse.Namespace(reqs=True)
    _stub_probe(monkeypatch)

    cli.split_imports(options)

    assert options.uninstalled_imports == {
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
    options = cli.Options()
    options.aliases = _RecordingIndex()
    options.all_imports = set()
    options.extra_requirements = {"reqonly": None}
    options.args = argparse.Namespace(reqs=True)
    _stub_probe(monkeypatch, installed=frozenset({"reqonly"}))

    cli.split_imports(options)

    assert options.installed_imports == {
        ResolvedImport(import_name="reqonly", pip_name="reqonly")
    }
    assert options.uninstalled_imports == {
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
    options = cli.Options()
    options.aliases = _RecordingIndex({"uninst": "uninst-pypi"})
    options.all_imports = {"mymod", "inst", "uninst", "httplib"}
    options.custom_modules = {"mymod": Path("/x/mymod.py")}
    options.extra_requirements = {"reqpkg": None}
    options.args = argparse.Namespace(reqs=True)
    _stub_probe(monkeypatch, installed=frozenset({"inst"}))

    cli.split_imports(options)

    assert options.all_imports == {"mymod", "inst", "uninst", "reqpkg"}
    assert options.total_imports == 4
    assert options.total_imports == len(options.all_imports)
    # all_imports is a strict superset of the two classified sets: the custom
    # module is in neither, and the bad import is in none of the three.
    classified = {record.import_name for record in options.installed_imports} | {
        record.import_name for record in options.uninstalled_imports
    }
    assert classified == {"inst", "uninst", "reqpkg"}
    assert classified < options.all_imports


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
    """The run's also_needs table reaches classification through cli.split_imports.

    The three tests above drive ``classify.add_dependencies`` directly, so
    none of them touches the wiring that hands it ``options.also_needs``.
    This one goes the whole way through the adapter production uses.

    Concrete bug this catches: pass ``also_needs={}`` (or drop the argument)
    at ``cli.split_imports``' call into ``classify.split_imports`` and every
    dependency veny's shipped table declares silently stops being installed --
    the venv is reported complete while the package that makes ``uninst``
    usable is absent. The chain is nested on purpose: no entry in cli.py's own
    also_needs table is, so the ``while added`` fixed point is otherwise never
    exercised on the path a user takes.
    """
    options = cli.Options()
    options.aliases = _index({"uninst": "uninst-pypi", "deepdep": "deep-dep-pypi"})
    options.all_imports = {"uninst"}
    options.also_needs = {"uninst": ["depmod"], "depmod": ["deepdep"]}
    _stub_probe(monkeypatch)

    cli.split_imports(options)

    assert options.uninstalled_imports == {
        ResolvedImport(import_name="uninst", pip_name="uninst-pypi"),
        ResolvedImport(import_name="depmod", pip_name="depmod"),
        ResolvedImport(import_name="deepdep", pip_name="deep-dep-pypi"),
    }
    # The dependencies are records only -- they are not source imports, so they
    # never join all_imports and never change the run's count.
    assert options.all_imports == {"uninst"}


# --- Migrated from tests/test_split_imports.py by phase 3c task 4. ---------
# These pin the same behaviour they always did; only their call sites moved
# with the code. The three _compute_bad_imports tests now name classify's
# copy of the function, and the three that patched the *stdlib* venv.create
# -- which production stopped calling when task 2 extracted environment.py,
# so they had been building a real uv venv on every run -- now patch
# environment.create_venv, the function cli._probe_venv actually calls.


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
    blocked = cli.Options().known_bad_imports
    assert blocked == {
        "snakeClass",
        "GPUampcor",
        "pathfinding_salvo_rework",
        "DQN",
        "bayesOpt",
        "non_existent_module",
    }


def test_split_imports_wires_python2_table_end_to_end():
    options = cli.Options()
    options.all_imports = {"httplib", "_private_thing"}
    cli.split_imports(options)
    assert options.bad_imports == {"httplib", "_private_thing"}
    assert options.all_imports == set()


def test_split_imports_stores_both_names_on_the_record(monkeypatch):
    # The bug this retires: split_imports used to add the *pip* name to
    # uninstalled_imports, so downstream import checks were handed
    # "widget-lib-pypi" when they needed "widgetlib".
    options = cli.Options()
    options.aliases = _index({"widgetlib": "widget-lib-pypi"})
    options.all_imports = {"widgetlib"}
    monkeypatch.setattr(environment, "create_venv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "check_packages_in_venv", lambda *a, **k: False)

    cli.split_imports(options)

    assert options.uninstalled_imports == {
        ResolvedImport(import_name="widgetlib", pip_name="widget-lib-pypi")
    }
    assert options.installed_imports == set()


def test_split_imports_falls_back_to_the_import_name_when_nothing_resolves(monkeypatch):
    # An unresolvable import must still be recorded, not crash on
    # candidates[0] and not vanish from the install list.
    options = cli.Options()
    options.aliases = _index({})
    options.all_imports = {"mysterylib"}
    monkeypatch.setattr(environment, "create_venv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "check_packages_in_venv", lambda *a, **k: False)

    cli.split_imports(options)

    assert options.uninstalled_imports == {
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
    options = cli.Options()
    options.python_command = "python3"
    options.aliases = _index({})
    options.all_imports = {"widgetlib"}
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
    monkeypatch.setattr(cli, "check_packages_in_venv", lambda *a, **k: False)

    cli.split_imports(options)

    assert len(captured) == 1, "expected exactly one probe venv build"
    probe_command = captured[0]
    assert "--python" in probe_command
    python_index = probe_command.index("--python")
    assert probe_command[python_index + 1] == "/resolved/bin/python3"


class _CountingIndex:
    """Wraps an AliasIndex and records every import name resolution was asked for."""

    def __init__(self, inner):
        self.inner = inner
        self.resolved = []

    def resolve(self, import_name):
        self.resolved.append(import_name)
        return self.inner.resolve(import_name)


def test_only_genuinely_uninstalled_imports_are_resolved(monkeypatch):
    # resolve() ran before both the custom-module check and the installed
    # check, so every import paid for resolution before veny knew whether it
    # needed a pip name at all. An unresolved name costs up to six PyPI project
    # lookups (the name plus five mutations), each a metadata request plus up
    # to two ranged wheel reads, at a 10 s read timeout. A local custom module
    # never needs a pip name, and neither does an import that is installed.
    options = cli.Options()
    index = _CountingIndex(_index({"missingthing": "missing-thing-pypi"}))
    # _CountingIndex wraps an AliasIndex rather than subclassing one, which is
    # what options.aliases is annotated as; the cast is the annotation this
    # test needed to move without carrying a mypy error along with it.
    options.aliases = cast(alias_index.AliasIndex, index)
    options.all_imports = {"mycustom", "alreadyhere", "missingthing"}
    options.custom_modules = {"mycustom": Path("/nowhere/mycustom.py")}
    monkeypatch.setattr(environment, "create_venv", lambda *a, **k: None)
    monkeypatch.setattr(
        cli,
        "check_packages_in_venv",
        lambda opts, record=None, venv_dir=None: record.import_name == "alreadyhere",
    )

    cli.split_imports(options)

    assert index.resolved == ["missingthing"]
    assert options.uninstalled_imports == {
        ResolvedImport(import_name="missingthing", pip_name="missing-thing-pypi")
    }
