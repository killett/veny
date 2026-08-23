#!/usr/bin/env python
"""Old-vs-new behavioural differential for phase 3e of the veny re-architecture.

Phase 3e cut ``src/veny/cli.py`` from 1,064 lines to ~200 by moving the run
into ``pipeline.py`` and the state object into ``run_options.py``. A green unit
suite cannot see a regression in a move of that size, because the tests move
with the code. Phase 3d's driver could not see it either: it called
``list_packages``, ``setup_virtualenv`` and ``find_match_dir_in_cache``
*directly*, so nothing it did depended on how ``main()`` wires its arguments --
which is exactly why 27 of ``main()``'s arguments went unpinned there. This
driver drives ``veny.cli.main()`` itself, through argv, in both trees.

How to run it, and against what base::

    git archive 08622a8 src/veny | tar -x -C /tmp/old-veny
    pixi run python scripts/differential_3e.py /tmp/old-veny > /tmp/old.txt
    pixi run python scripts/differential_3e.py /workspace    > /tmp/new.txt
    diff /tmp/old.txt /tmp/new.txt

``08622a8`` is the phase-3e branch point ("docs: record 3d's merge to main and
the whole-branch review's fix wave"). The argument is a *tree root* holding
``src/veny``; it is inserted with ``sys.path.insert``, never through
``PYTHONPATH``, because ``pixi.toml``'s ``[activation.env]`` sets
``PYTHONPATH = "src"`` and would silently overwrite it, testing the live source
twice. The first line of output is ``veny.cli.__file__``, so the captured
evidence itself shows which tree ran.

This is a script, not a test. It is deliberately NOT wired into pytest: it
compares two trees, only one of which exists inside any given checkout.

The two trees are differently shaped, and the driver reaches the same behaviour
through different module paths in each: ``cli.list_packages`` /
``cli.setup_virtualenv`` / the god-object class ``cli`` used to export as
``Options`` before, ``pipeline.*`` and ``run_options.Options`` after. ``Tree``
below carries that bridge, the way 3d's did. Everything is driven through
``cli.main()``, so the bridge is only needed for installing stand-ins, never
for calling veny.

Seven layers are captured, each a separate ``cli.main()`` call with its own
argv, its own ``$HOME`` and its own working directory:

1. **A run with nothing missing.** A script importing only ``os``. Captures
   ``main()``'s return, every ``subprocess`` argv, and the log records at INFO
   and above (sorted, as the plan asks).
2. **A cache hit.** Five manifest-bearing folders in the cache: three that
   match at different timestamps *and different package counts*, one for the
   wrong interpreter, one whose manifest is missing the package its folder name
   advertises. Captures the chosen folder, the ordered
   ``read_manifest``/``satisfies`` sequence, the final state of the four
   ``args`` flags, and the argv the script was launched with. Three survivors
   rather than 3d's two: with two, ``latest``, ``oldest`` and ``smallest`` tie
   in pairs and swapping one ranking for another is invisible. Here
   ``latest`` -> the 04:04:04 folder, ``oldest`` -> the 02:02:02 folder,
   ``smallest`` -> the 03:03:03 folder, so all three are distinguishable.
3. **``--justprint``.** Captures the return, the full log output, and the
   argparse dest list -- which is where ``--full``'s deletion shows up.
4. **A cache miss that builds** (``--no-cache``). Captures the uv argv,
   the requirements file, the folder name built, and the announced launch.
5. **A build that fails.** The venv is built but cannot be verified, so
   ``setup_virtualenv`` returns False.
6. **A run started inside a virtual environment.**
7. **``--blank-slate -y``.** No script at all.

Layers 4-7 go beyond the three the plan requires. They are here because
deviations 3, 4, 5 and 6 below are invisible to the first three.

WHAT THE DIFF IS EXPECTED TO CONTAIN
------------------------------------

The comparison is *not* expected to be empty. These hunks are sanctioned by the
phase-3e plan; anything else is a regression:

0. The ``veny.cli.__file__`` and ``tree shape`` header lines differ by
   construction -- that is the evidence of which tree ran.
1. **``--full`` deleted** (flag, help text, all six branches). Visible in layer
   3's argparse dest list: the old tree has ``full``, the new one does not.
2. **A scriptless run is a usage error.** Not reached by these layers: layer 7
   passes ``--blank-slate``, which the old tree also handled. Listed in the
   report's "cannot see".
3. **The in-virtualenv branch reads ``VIRTUAL_ENV``/``sys.prefix``** instead of
   asserting an unset ``options.venv_dir``. Layer 6: the old tree raises
   AssertionError out of ``main()``; the new one checks the active environment
   and runs the script.
4. **``environment.uv_binary`` raises ``UvUnavailable`` instead of
   ``SystemExit``, and ``create_venv`` returns ``bool``** instead of letting
   CalledProcessError escape. Layer 5 reaches ``create_venv``'s success path
   only; the raising path is in the report's "cannot see".
5. **``--justprint`` and ``--blank-slate`` return a status through ``main()``**
   instead of ``sys.exit(0)`` inside the run. Layer 3: the old tree raises
   SystemExit(0) and never reaches ``logging.shutdown()``; the new one returns
   0 and does. Layer 7: the old tree raises SystemExit(0) and reaches neither
   ``ek.print_all_errors`` nor ``logging.shutdown()``; the new one reaches both.
6. **A failed venv build logs ``logging.critical`` and returns 1** instead of
   calling emmykit's critical-error helper with ``choose_breakpoint=True``,
   which opened a pdb prompt. Layer 5: the old tree records that helper call,
   the new one records a CRITICAL log record. (The helper is stubbed here --
   see the stand-ins below -- precisely because an unstubbed one would stop
   this driver in a debugger.)
7. **The elapsed-time baseline was restored to ``main``'s first statement.**
   This one must produce **no** diff: it was a regression the phase fixed
   before it landed. The clock below is what makes it observable -- see
   "Determinism" -- so a baseline that moved would shift every "Elapsed time"
   line in layers 1-6.

DETERMINISM
-----------

Enforced rather than hoped for. ``PYTHONHASHSEED=0`` is set inside this script
(re-execing once if the interpreter did not start with it),
``sys.dont_write_bytecode`` is set and every ``__pycache__`` under the tree is
deleted before the first import (a same-size source edit restored within the
same integer second otherwise serves the pre-restore behaviour), ``HOME`` and
the working directory are redirected per layer so neither ``~/veny`` nor the
repository is read or written, and every path that carries this run's own
temporary directory is replaced with a stable token before it is printed.

``datetime`` is replaced, in every veny module that imports it, with a counting
clock that starts again at each layer. That is not only noise suppression: it
makes the "Elapsed time" and "Runtime" lines a function of *how many* clock
reads happened before them, so deviation 7 -- a moved timing baseline -- is
something this diff can see rather than something it scrubs away.

STAND-INS
---------

Every boundary that would touch a real interpreter, a real network or a real
venv is replaced, at whichever module the tree keeps it in:

* ``subprocess.run`` / ``subprocess.check_call`` -- recorded, never run.
* ``environment.uv_binary`` -- a fixed ``<uv>`` token.
* ``alias_index.probe_interpreter``, ``alias_index.build``,
  ``stdlib_index.resolve`` -- fixed answers, arguments recorded.
* ``verify.check_packages_in_venv`` -- answered from a fixed set.
* ``verify.verify_and_repair_imports`` -- recorded and passed through; 3d's
  layer 2 already pinned the uv side of it.
* ``analysis.custom_modules.dict_of_custom_modules`` -- recorded, answers ``{}``.
  Unstubbed it walks the whole of ``sys.path``, which includes the tree under
  test, so its answer would differ between the trees for a reason that is not
  behaviour.
* ``emmykit``'s ``configure_logging``, ``print_all_errors``,
  ``save_options_to_json``, ``find_preferred_python_version``,
  ``prompt_then_confirm`` and ``my_critical_error`` -- recorded. Log records are
  captured from the root logger directly instead, so no timestamp ever reaches
  stdout.
* ``logging.shutdown`` -- recorded rather than run; running it would close the
  capture handler.

Diagnostics go to stderr. Only compared state goes to stdout.

What this driver still cannot see is recorded in the task report; it is not a
clean bill of health for ``main()``.
"""

from __future__ import annotations

import datetime as dt
import importlib
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_HASH_SEED_MARKER = "VENY_DIFFERENTIAL_REEXEC"
# What tempfile.TemporaryDirectory calls a directory it names itself.
_THROWAWAY_NAME = r"tmp[A-Za-z0-9_]+"


def reexec_with_fixed_hash_seed() -> None:
    """Restart this process with ``PYTHONHASHSEED=0`` if it did not start that way.

    Set iteration order is part of what the argv capture observes: a driver
    that iterates a set without a fixed seed produces different orderings
    between two runs of the *same* tree, which reads as a regression that is
    not there. The seed has to be in the environment before the interpreter
    starts, so the only way to guarantee it from inside the script is to
    re-exec once.
    """
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    if os.environ.get(_HASH_SEED_MARKER) == "1":
        # Already re-execed once and the seed still is not what we asked for.
        # Say so rather than looping forever.
        print(
            "WARNING: could not fix PYTHONHASHSEED; orderings may vary",
            file=sys.stderr,
        )
        return
    os.environ["PYTHONHASHSEED"] = "0"
    os.environ[_HASH_SEED_MARKER] = "1"
    os.execv(sys.executable, [sys.executable, "-B", __file__, *sys.argv[1:]])


def purge_pycache(root: Path) -> int:
    """Delete every ``__pycache__`` directory under a tree.

    Args:
        root: The tree to sweep.

    Returns:
        How many directories were removed.
    """
    removed = 0
    for path in sorted(root.rglob("__pycache__")):
        shutil.rmtree(path, ignore_errors=True)
        removed += 1
    return removed


class Tree:
    """The veny modules of one source tree, with the shape differences bridged.

    Attributes:
        split:         True when this tree has ``veny.pipeline`` -- that is,
                       when it is a post-3e tree.
        cli:           ``veny.cli``.
        pipeline:      ``veny.pipeline`` on a split tree, else ``veny.cli``.
        run_options:   ``veny.run_options`` on a split tree, else ``veny.cli``.
        alias_index:   ``veny.alias_index``.
        environment:   ``veny.environment``.
        stdlib_index:  ``veny.stdlib_index``.
        venv_cache:    ``veny.venv_cache``.
        cache_search:  ``veny.cache_search``.
        verify:        ``veny.verify``.
        last_used:     ``veny.last_used``.
        custom_modules: ``veny.analysis.custom_modules``.
    """

    def __init__(self) -> None:
        """Import the modules this tree has, and record which shape it is."""
        self.split: bool = importlib.util.find_spec("veny.pipeline") is not None
        self.cli: Any = importlib.import_module("veny.cli")
        self.pipeline: Any = (
            importlib.import_module("veny.pipeline") if self.split else self.cli
        )
        self.run_options: Any = (
            importlib.import_module("veny.run_options") if self.split else self.cli
        )
        self.alias_index: Any = importlib.import_module("veny.alias_index")
        self.environment: Any = importlib.import_module("veny.environment")
        self.stdlib_index: Any = importlib.import_module("veny.stdlib_index")
        self.venv_cache: Any = importlib.import_module("veny.venv_cache")
        self.cache_search: Any = importlib.import_module("veny.cache_search")
        self.verify: Any = importlib.import_module("veny.verify")
        self.last_used: Any = importlib.import_module("veny.last_used")
        self.custom_modules: Any = importlib.import_module(
            "veny.analysis.custom_modules"
        )


# ---------------------------------------------------------------------------
# Fixed inputs. Nothing below reads the machine's own state.
# ---------------------------------------------------------------------------

STDLIB_NAMES = frozenset(
    {"os", "sys", "json", "re", "pathlib", "logging", "argparse", "xml", "typing"}
)
SEED = {
    "yaml": "PyYAML",
    "np": "numpy",
    "numpy": "numpy",
    "cv2": "opencv-python",
    "requests": "requests",
    "netCDF4": "netcdf4",
    "dask": "dask",
    "h5netcdf": "h5netcdf",
    "xarray": "xarray",
}
# What the throwaway classification probe reports as already importable. "yaml"
# is deliberately absent: it is the one import the driven runs are missing.
IMPORTABLE_IN_PROBE = frozenset({"requests"})
# What a stand-in script run reports. Not 0 and not 1, so that "the child's
# status was returned" is distinguishable from both "success" and "veny's own
# failure status".
SCRIPT_STATUS = 7

CLOCK_EPOCH = dt.datetime(2026, 1, 1, 0, 0, 0)


class Clock:
    """A counting clock, so every duration veny logs is a fixed number.

    Attributes:
        reads: How many times ``now()`` has been called since the last reset.
    """

    def __init__(self) -> None:
        """Start at the epoch with no reads."""
        self.reads = 0

    def reset(self) -> None:
        """Start counting again, so each layer's timings stand alone."""
        self.reads = 0

    def now(self) -> dt.datetime:
        """Return the next instant, one second after the previous one.

        Returns:
            The epoch plus one second per read so far.
        """
        self.reads += 1
        return CLOCK_EPOCH + dt.timedelta(seconds=self.reads)


CLOCK = Clock()


class CountingDateTime(dt.datetime):
    """``datetime.datetime`` with ``now()`` answered by the counting clock."""

    @classmethod
    def now(cls, tz: dt.tzinfo | None = None) -> dt.datetime:  # type: ignore[override]
        """Return the counting clock's next instant.

        Args:
            tz: Ignored; present because the real signature accepts it.

        Returns:
            The next instant from the shared clock.
        """
        return CLOCK.now()


class CountingDatetimeModule:
    """A stand-in for the ``datetime`` module, with only ``now()`` changed.

    Attributes:
        datetime:  The counting subclass, which still has strptime/strftime.
        timedelta: The real one.
        date:      The real one.
        time:      The real one.
        timezone:  The real one.
    """

    datetime = CountingDateTime
    timedelta = dt.timedelta
    date = dt.date
    time = dt.time
    timezone = dt.timezone


# ---------------------------------------------------------------------------
# The harness: one set of stand-ins, reset between layers.
# ---------------------------------------------------------------------------


class Harness:
    """Every boundary veny would cross, recorded instead of crossed.

    Attributes:
        tree:            The loaded tree.
        workdir:         The scratch directory this whole run owns.
        commands:        Every argv veny handed to subprocess, in call order.
        calls:           Every stand-in call, in call order.
        records:         Every log record at INFO and above, in emit order.
        options:         The live Options of the most recent run.
        script_status:   What a stand-in script run reports.
        uv_returncode:   What a stand-in uv command reports.
        create_venv_ok:  False makes ``uv venv`` fail.
        bulk_check:      What ``check_packages_in_venv`` answers with no record.
        in_virtualenv:   What ``last_used.is_virtualenv`` answers.
        substitutions:   Literal path replacements applied before printing.
    """

    def __init__(self, tree: Tree, workdir: Path) -> None:
        """Start with nothing recorded and every policy at its default.

        Args:
            tree:    The loaded tree.
            workdir: The scratch directory this run owns.
        """
        self.tree = tree
        self.workdir = workdir
        self.commands: list[list[str]] = []
        self.calls: list[str] = []
        self.records: list[str] = []
        self.options: Any = None
        self.script_status: int = SCRIPT_STATUS
        self.uv_returncode: int = 0
        self.create_venv_ok: bool = True
        self.bulk_check: bool = True
        self.in_virtualenv: bool = False
        self.substitutions: list[tuple[str, str]] = []

    # -- recording -------------------------------------------------------

    def scrub(self, text: str) -> str:
        """Replace every path that belongs to this run with a stable token.

        Args:
            text: Anything about to be printed.

        Returns:
            The same text with this run's own directories tokenised.
        """
        for literal, token in sorted(
            self.substitutions, key=lambda pair: len(pair[0]), reverse=True
        ):
            text = text.replace(literal, token)
        # tempfile.TemporaryDirectory names the throwaway classification probe
        # venv, and that name is random by design. The pattern is assembled
        # rather than written out so that no literal names the system temp
        # directory, which the security linter reads as a hardcoded path.
        prefix = re.escape(os.path.join(tempfile.gettempdir(), ""))
        return re.sub(prefix + _THROWAWAY_NAME, "<tmpdir>", text)

    def note(self, text: str) -> None:
        """Record one stand-in call.

        Args:
            text: How the call should read in the capture.
        """
        self.calls.append(self.scrub(text))

    def begin(self, layer_dir: Path) -> tuple[Path, Path]:
        """Reset every recording, and give this layer a fresh HOME and cwd.

        Args:
            layer_dir: The directory this layer owns.

        Returns:
            The layer's home directory and its working directory.
        """
        self.commands = []
        self.calls = []
        self.records = []
        self.options = None
        self.script_status = SCRIPT_STATUS
        self.uv_returncode = 0
        self.create_venv_ok = True
        self.bulk_check = True
        self.in_virtualenv = False
        home = layer_dir / "home"
        cwd = layer_dir / "cwd"
        home.mkdir(parents=True, exist_ok=True)
        cwd.mkdir(parents=True, exist_ok=True)
        os.environ["HOME"] = os.fspath(home)
        os.environ.pop("VIRTUAL_ENV", None)
        os.chdir(cwd)
        self.substitutions = [
            (os.fspath(home), "<home>"),
            (os.fspath(cwd), "<cwd>"),
            (os.fspath(layer_dir), "<layer>"),
            (os.fspath(self.workdir), "<workdir>"),
            (sys.executable, "<sys.executable>"),
        ]
        return home, cwd

    def drive(self, argv: list[str]) -> str:
        """Run ``cli.main()`` with one argv and say what came back.

        Args:
            argv: Everything after the program name.

        Returns:
            A one-line rendering of the return value or the exception.
        """
        sys.argv = ["veny", *argv]
        CLOCK.reset()
        try:
            status = self.tree.cli.main()
        except SystemExit as exc:
            return f"raised SystemExit({exc.code!r})"
        except Exception as exc:
            # Deliberately broad: an exception escaping main() is one of the
            # things being compared (the pre-3e tree lets an AssertionError out
            # of the in-virtualenv branch), so it is captured, not handled.
            return f"raised {type(exc).__name__}: {self.scrub(str(exc))}"
        return f"returned {status!r}"

    # -- the subprocess boundary -----------------------------------------

    def run(self, command: Any, *args: Any, **kwargs: Any) -> Any:
        """Record a command and answer it without running anything.

        Args:
            command:  The argv list veny built.
            *args:    Ignored; present because callers pass positionally.
            **kwargs: Ignored; present because callers pass keywords.

        Returns:
            A CompletedProcess-shaped object.
        """
        argv = [str(part) for part in command]
        self.commands.append(argv)
        if argv and argv[0] == "<uv>":
            stderr = "" if self.uv_returncode == 0 else "differential: uv refused"
            return SimpleNamespace(
                args=argv, returncode=self.uv_returncode, stdout="", stderr=stderr
            )
        if "-c" in argv:
            payload = json.dumps({"python": [3, 12], "versions": {}})
            return SimpleNamespace(args=argv, returncode=0, stdout=payload, stderr="")
        return SimpleNamespace(
            args=argv, returncode=self.script_status, stdout="", stderr=""
        )

    def check_call(self, command: Any, *args: Any, **kwargs: Any) -> int:
        """Record a command that veny expects to raise on failure.

        Args:
            command:  The argv list veny built.
            *args:    Ignored.
            **kwargs: Ignored.

        Returns:
            Zero when the current policy says the build succeeds.

        Raises:
            subprocess.CalledProcessError: When it says it does not.
        """
        argv = [str(part) for part in command]
        self.commands.append(argv)
        if not self.create_venv_ok:
            raise subprocess.CalledProcessError(1, argv)
        return 0

    # -- printing --------------------------------------------------------

    def dump(self, *, sort_logs: bool = False) -> None:
        """Print everything this layer recorded.

        Args:
            sort_logs: True sorts the log records instead of keeping emit
                order. Used where the order is a directory-iteration order
                rather than veny's own sequencing.
        """
        print("  -- stand-in calls --")
        for entry in self.calls:
            print(f"    {entry}")
        print("  -- subprocess argv --")
        for command in self.commands:
            print(f"    {[self.scrub(part) for part in command]}")
        print("  -- log records --")
        lines = [self.scrub(line) for line in self.records]
        for line in sorted(lines) if sort_logs else lines:
            print(f"    {line}")


class CaptureHandler(logging.Handler):
    """Collects log records into the harness instead of formatting them."""

    def __init__(self, harness: Harness) -> None:
        """Attach to one harness.

        Args:
            harness: Where the records go.
        """
        super().__init__(level=logging.INFO)
        self.harness = harness

    def emit(self, record: logging.LogRecord) -> None:
        """Record one message.

        Args:
            record: The record logging is emitting.
        """
        self.harness.records.append(f"{record.levelname}: {record.getMessage()}")


# ---------------------------------------------------------------------------
# Installing the stand-ins
# ---------------------------------------------------------------------------


def a_stdlib_index(tree: Tree) -> Any:
    """Build the fixed standard-library index both trees are given.

    Args:
        tree: The loaded tree.

    Returns:
        A StdlibIndex over a fixed name set.
    """
    return tree.stdlib_index.StdlibIndex(
        names=STDLIB_NAMES, python_version=(3, 12), source="differential"
    )


def an_alias_index(tree: Tree, my_dir: Path) -> Any:
    """Build the fixed alias index both trees are given.

    Args:
        tree:   The loaded tree.
        my_dir: The throwaway directory standing in for ``~/veny``.

    Returns:
        An offline AliasIndex seeded with a fixed mapping.
    """
    return tree.alias_index.AliasIndex(
        overrides={},
        cache=tree.alias_index.AliasCache(
            path=my_dir / "unused_alias_cache.json",
            interpreter_tag="3.12",
            entries={},
            rejections={},
        ),
        installed={},
        pypi=None,
        seed=dict(SEED),
    )


def install_stand_ins(tree: Tree, harness: Harness) -> None:
    """Replace every boundary that would touch the machine, in both shapes.

    Args:
        tree:    The loaded tree.
        harness: The harness the stand-ins record into.
    """
    # Annotated Any deliberately: these attributes are replaced below, and
    # mypy will not let a ModuleType be written through.
    ek: Any = importlib.import_module("emmykit")

    subprocess.run = harness.run  # type: ignore[assignment]
    subprocess.check_call = harness.check_call  # type: ignore[assignment]

    def fake_shutdown(handler_list: Any = None) -> None:
        """Record the shutdown call rather than closing the capture handler."""
        harness.note("logging.shutdown()")

    logging.shutdown = fake_shutdown  # type: ignore[assignment]

    tree.environment.uv_binary = lambda: "<uv>"
    tree.alias_index.probe_interpreter = lambda python, timeout=30.0: ("3.12", {})
    tree.last_used.is_virtualenv = lambda: harness.in_virtualenv

    def fake_build(python_command: Any, my_dir: Any, *, offline: bool = False) -> Any:
        """Answer with the fixed index, recording how main() asked for it."""
        harness.note(
            f"alias_index.build(python_command={python_command!r}, "
            f"my_dir={os.fspath(my_dir)}, offline={offline})"
        )
        return an_alias_index(tree, Path(my_dir))

    tree.alias_index.build = fake_build

    def fake_resolve(python_command: Any = "") -> Any:
        """Answer with the fixed stdlib index, recording the interpreter asked for."""
        harness.note(f"stdlib_index.resolve({python_command!r})")
        return a_stdlib_index(tree)

    tree.stdlib_index.resolve = fake_resolve

    def fake_check(
        venv_python: Any,
        *,
        record: Any = None,
        uninstalled: Any = frozenset(),
        source_names: Any = frozenset(),
    ) -> bool:
        """Answer one record from a fixed set; answer the bulk branch by policy."""
        if record is not None:
            return bool(record.import_name in IMPORTABLE_IN_PROBE)
        harness.note(
            f"verify.check_packages_in_venv(venv_python={harness.scrub(os.fspath(venv_python))}, "
            f"uninstalled={sorted(r.import_name for r in uninstalled)}, "
            f"source_names={sorted(source_names)}) -> {harness.bulk_check}"
        )
        return harness.bulk_check

    tree.verify.check_packages_in_venv = fake_check

    def fake_repair(
        *,
        venv_python: Any,
        requirements_file: Any,
        uninstalled: Any,
        extra_requirements: Any,
        source_names: Any,
        index: Any,
        rawlog: bool,
    ) -> Any:
        """Record the repair pass's arguments and pass its input straight through."""
        harness.note(
            f"verify.verify_and_repair_imports(venv_python="
            f"{harness.scrub(os.fspath(venv_python))}, "
            f"uninstalled={sorted(r.import_name for r in uninstalled)}, "
            f"extra_requirements={dict(sorted(extra_requirements.items()))}, "
            f"source_names={sorted(source_names)}, rawlog={rawlog})"
        )
        return frozenset(uninstalled)

    tree.verify.verify_and_repair_imports = fake_repair

    def fake_custom_modules(settings: Any, *, use_cache: bool) -> dict[str, Path]:
        """Record the settings and the cache decision; discover nothing."""
        harness.note(
            f"dict_of_custom_modules(use_cache={use_cache}, "
            f"my_name={settings.my_name!r}, cwd={harness.scrub(os.fspath(settings.cwd))}, "
            f"search_above_this_dir={settings.search_above_this_dir}, "
            f"rawlog={settings.rawlog})"
        )
        return {}

    tree.custom_modules.dict_of_custom_modules = fake_custom_modules
    if hasattr(tree.cli, "dict_of_custom_modules"):
        # The pre-3e tree imported the name into cli's own namespace.
        tree.cli.dict_of_custom_modules = fake_custom_modules

    real_parse = tree.cli.parse_arguments

    def spy_parse(options: Any) -> None:
        """Parse for real, then keep a handle on the run's own Options."""
        real_parse(options)
        harness.options = options

    tree.cli.parse_arguments = spy_parse

    def fake_configure_logging(
        basename: str, log_level: Any = logging.INFO, rawlog: bool = False, **kw: Any
    ) -> str:
        """Record how main() configured logging; leave the capture handler alone."""
        harness.note(
            f"ek.configure_logging(basename={basename!r}, "
            f"log_level={logging.getLevelName(log_level)}, rawlog={rawlog})"
        )
        return "<memory-handler>"

    ek.configure_logging = fake_configure_logging
    ek.print_all_errors = lambda handler, rawlog=False: harness.note(
        f"ek.print_all_errors(handler={handler!r}, rawlog={rawlog})"
    )
    ek.save_options_to_json = lambda options: harness.note(
        "ek.save_options_to_json(venv_dir="
        f"{harness.scrub(os.fspath(options.venv_dir)) if options.venv_dir else None})"
    )
    ek.find_preferred_python_version = lambda: ""

    def fake_confirm(prompt: str) -> bool:
        """Record the prompt the user would have seen and answer yes."""
        harness.note(f"ek.prompt_then_confirm({prompt!r})")
        return True

    ek.prompt_then_confirm = fake_confirm

    def fake_critical_error(
        message: str = "A critical error occurred.",
        choose_breakpoint: bool = False,
        exit_code: int = 1,
    ) -> None:
        """Record emmykit's critical-error helper instead of running it.

        Unstubbed, the pre-3e tree's one call to this passes
        ``choose_breakpoint=True``, which opens a pdb prompt -- it would stop
        this driver in a debugger. Recording the call is also the evidence for
        deviation 6: the post-3e tree logs instead of calling it at all.
        """
        harness.note(
            f"ek.my_critical_error({message!r}, choose_breakpoint={choose_breakpoint}, "
            f"exit_code={exit_code})"
        )

    ek.my_critical_error = fake_critical_error

    for module in (tree.cli, tree.pipeline, tree.run_options, tree.last_used):
        if hasattr(module, "dt"):
            module.dt = CountingDatetimeModule


# ---------------------------------------------------------------------------
# The layers
# ---------------------------------------------------------------------------


def a_script(directory: Path, name: str, body: str) -> Path:
    """Write one script for a layer to drive.

    Args:
        directory: Where it goes.
        name:      Its filename.
        body:      Its source.

    Returns:
        The script's path.
    """
    path = directory / name
    path.write_text(body)
    return path


def layer_one(harness: Harness, workdir: Path) -> None:
    """A run with nothing missing: the all-installed branch.

    Args:
        harness: The installed harness.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 1: a run with nothing missing ===")
    _, cwd = harness.begin(workdir / "layer1")
    script = a_script(cwd, "stdlib_only.py", "import os\nprint(os.sep)\n")
    argv = [os.fspath(script), "--flag", "value"]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    harness.dump(sort_logs=True)


def build_fake_cache(tree: Tree, my_dir: Path) -> None:
    """Write five manifest-bearing venv folders into a throwaway cache.

    Three match this run outright, at different timestamps *and* different
    package counts; one is for another interpreter; one carries a manifest
    missing the package its folder name advertises, so it survives the cheap
    name filter and is rejected only once its manifest is read.

    Three survivors, not 3d's two, is what makes all three ranking functions
    observable. With two, latest/oldest/smallest tie in pairs and swapping one
    for another is a change the capture cannot see. Here they name three
    different folders: latest -> 04:04:04, oldest -> 02:02:02,
    smallest -> 03:03:03 (one package where the others have three and four).

    Args:
        tree:   The loaded tree.
        my_dir: The throwaway directory standing in for ``~/veny``.
    """
    record = tree.venv_cache.PackageRecord

    def a_folder(tag: str, timestamp: str, packages: list[Any]) -> None:
        """Write one cached venv folder with the manifest it advertises."""
        name = tree.venv_cache.build_folder_name(
            venv_name="myenv",
            interpreter_tag=tag,
            timestamp=timestamp,
            pip_names=[item.pip_name for item in packages],
        )
        folder = my_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        tree.venv_cache.write_manifest(
            folder,
            tree.venv_cache.Manifest(
                schema_version=tree.venv_cache.SCHEMA_VERSION,
                created=timestamp,
                veny_version="0.2.2",
                interpreter_tag=tag,
                interpreter_path="/usr/bin/python3.12",
                packages=tuple(packages),
            ),
        )

    yaml = record("yaml", "PyYAML", "6.0.1", None)
    filler_one = record("fillerone", "filler-one", "1.0.0", None)
    filler_two = record("fillertwo", "filler-two", "1.0.0", None)
    filler_three = record("fillerthree", "filler-three", "1.0.0", None)
    # Four packages, newest: what --latest must pick.
    a_folder("3.12", "20260101-040404", [yaml, filler_one, filler_two, filler_three])
    # One package: what --smallest must pick.
    a_folder("3.12", "20260101-030303", [yaml])
    # Three packages, oldest: what --oldest must pick.
    a_folder("3.12", "20260101-020202", [yaml, filler_one, filler_two])
    # The wrong interpreter.
    a_folder("3.11", "20260101-050505", [yaml])
    # Advertises yaml in its folder name, but its manifest does not hold it.
    name = tree.venv_cache.build_folder_name(
        venv_name="myenv",
        interpreter_tag="3.12",
        timestamp="20260101-060606",
        pip_names=["PyYAML"],
    )
    folder = my_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    tree.venv_cache.write_manifest(
        folder,
        tree.venv_cache.Manifest(
            schema_version=tree.venv_cache.SCHEMA_VERSION,
            created="20260101-060606",
            veny_version="0.2.2",
            interpreter_tag="3.12",
            interpreter_path="/usr/bin/python3.12",
            packages=(filler_one,),
        ),
    )


def layer_two(harness: Harness, tree: Tree, workdir: Path) -> None:
    """A cache hit: which folder wins, how it was decided, and what launched.

    Args:
        harness: The installed harness.
        tree:    The loaded tree.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 2: a cache hit ===")
    home, cwd = harness.begin(workdir / "layer2")
    my_dir = home / "veny"
    my_dir.mkdir(parents=True, exist_ok=True)
    build_fake_cache(tree, my_dir)
    script = a_script(cwd, "needs_yaml.py", "import yaml\nprint(yaml)\n")

    sequence: list[str] = []
    real_read = tree.venv_cache.read_manifest
    real_satisfies = tree.venv_cache.satisfies

    def spy_read(venv_dir: Any) -> Any:
        """Record which folder's manifest is read, then read it."""
        sequence.append(f"read_manifest({Path(venv_dir).name})")
        return real_read(venv_dir)

    def spy_satisfies(manifest: Any, *args: Any, **kwargs: Any) -> Any:
        """Record which manifest is matched, then match it."""
        sequence.append(
            f"satisfies(tag={manifest.interpreter_tag}, created={manifest.created})"
        )
        return real_satisfies(manifest, *args, **kwargs)

    tree.venv_cache.read_manifest = spy_read
    tree.venv_cache.satisfies = spy_satisfies
    argv = [os.fspath(script)]
    try:
        outcome = harness.drive(argv)
    finally:
        tree.venv_cache.read_manifest = real_read
        tree.venv_cache.satisfies = real_satisfies

    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {outcome}")
    options = harness.options
    venv_dir = getattr(options, "venv_dir", None)
    print(f"  chosen folder: {Path(venv_dir).name if venv_dir is not None else None}")
    print("  call sequence:")
    for entry in sequence:
        print(f"    {entry}")
    for flag in ("latest", "oldest", "last_used", "smallest"):
        print(f"  args.{flag}: {getattr(options.args, flag, '<absent>')}")
    harness.dump()


def layer_three(harness: Harness, workdir: Path) -> None:
    """``--justprint``: the tail-order deviation, and the argparse surface.

    Args:
        harness: The installed harness.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 3: --justprint ===")
    _, cwd = harness.begin(workdir / "layer3")
    script = a_script(cwd, "needs_yaml.py", "import yaml\nimport os\nprint(yaml, os)\n")
    argv = ["--justprint", os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    print(f"  argparse dests: {sorted(vars(harness.options.args))}")
    harness.dump()


def layer_four(harness: Harness, workdir: Path) -> None:
    """A cache miss that builds: the uv argv, the folder name, the launch.

    Args:
        harness: The installed harness.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 4: a cache miss that builds ===")
    _, cwd = harness.begin(workdir / "layer4")
    script = a_script(cwd, "needs_yaml.py", "import yaml\nprint(yaml)\n")
    argv = ["--no-cache", os.fspath(script), "positional"]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    options = harness.options
    venv_dir = getattr(options, "venv_dir", None)
    print(f"  venv folder: {Path(venv_dir).name if venv_dir is not None else None}")
    print(f"  install_succeeded: {getattr(options, 'install_succeeded', '<absent>')}")
    requirements = getattr(options, "requirements_file", None)
    if requirements is not None and Path(requirements).is_file():
        print(f"  requirements.txt: {Path(requirements).read_text().splitlines()}")
    else:
        print("  requirements.txt: <not written>")
    harness.dump()


def layer_five(harness: Harness, workdir: Path) -> None:
    """A build that cannot be verified: the failed-build report.

    Args:
        harness: The installed harness.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 5: a build that fails ===")
    _, cwd = harness.begin(workdir / "layer5")
    harness.bulk_check = False
    script = a_script(cwd, "needs_yaml.py", "import yaml\nprint(yaml)\n")
    argv = ["--no-cache", os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    harness.dump()


def layer_six(harness: Harness, workdir: Path) -> None:
    """A run started inside a virtual environment.

    Args:
        harness: The installed harness.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 6: already inside a virtual environment ===")
    layer_dir = workdir / "layer6"
    _, cwd = harness.begin(layer_dir)
    harness.in_virtualenv = True
    active = layer_dir / "active-venv"
    (active / "bin").mkdir(parents=True, exist_ok=True)
    os.environ["VIRTUAL_ENV"] = os.fspath(active)
    script = a_script(cwd, "needs_yaml.py", "import yaml\nprint(yaml)\n")
    argv = [os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  VIRTUAL_ENV: {harness.scrub(os.environ['VIRTUAL_ENV'])}")
    print(f"  main(): {harness.drive(argv)}")
    harness.dump()


def layer_seven(harness: Harness, workdir: Path) -> None:
    """``--blank-slate -y``: a complete run with no script at all.

    Args:
        harness: The installed harness.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 7: --blank-slate -y ===")
    home, cwd = harness.begin(workdir / "layer7")
    my_dir = home / "veny"
    my_dir.mkdir(parents=True, exist_ok=True)
    (my_dir / "myenv-3.12-20260101-010101").mkdir(parents=True, exist_ok=True)
    for name in (
        ".veny-run.out",
        ".veny-run.err",
        ".veny_custom_modules_host_20260101-010101.pkl",
        ".script.py-veny-last-used-on-20260101-010101.json",
        "keep_me.json",
        "keep_me.txt",
    ):
        (cwd / name).write_text("x\n")
    argv = ["--blank-slate", "-y"]
    print(f"  argv: {argv}")
    print(f"  main(): {harness.drive(argv)}")
    print(f"  my_dir still there: {my_dir.is_dir()}")
    print(f"  cwd afterwards: {sorted(p.name for p in cwd.iterdir())}")
    harness.dump(sort_logs=True)


def main() -> int:
    """Capture all seven layers against the tree named on the command line.

    Returns:
        Zero on success; 2 when the tree root is missing or unusable.
    """
    if len(sys.argv) < 2:
        print("usage: differential_3e.py <tree-root>")
        return 2
    root = Path(sys.argv[1]).resolve()
    package = root / "src" / "veny"
    if not package.is_dir():
        print(f"no src/veny under {root}")
        return 2

    sys.dont_write_bytecode = True
    purged = purge_pycache(root / "src")
    sys.path.insert(0, str(root / "src"))

    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="veny-3e-") as scratch:
        workdir = Path(scratch).resolve()
        # Before the first veny import: Options() reads Path.home() at
        # construction, and ~/veny must be neither read nor written.
        (workdir / "home").mkdir()
        os.environ["HOME"] = os.fspath(workdir / "home")
        tree = Tree()
        print(f"veny.cli.__file__: {tree.cli.__file__}")
        print(f"tree shape: {'split (3e)' if tree.split else 'monolithic (pre-3e)'}")
        # Diagnostics, not observations: the purge count depends on whether
        # this tree happened to have been imported recently, so on stdout it
        # would put a spurious hunk in the documented diff. They go to stderr,
        # where they are still captured next to the run.
        print(f"PYTHONHASHSEED: {os.environ.get('PYTHONHASHSEED')}", file=sys.stderr)
        print(f"__pycache__ directories purged: {purged}", file=sys.stderr)

        harness = Harness(tree, workdir)
        install_stand_ins(tree, harness)
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
        root_logger.addHandler(CaptureHandler(harness))
        root_logger.setLevel(logging.INFO)

        try:
            layer_one(harness, workdir)
            layer_two(harness, tree, workdir)
            layer_three(harness, workdir)
            layer_four(harness, workdir)
            layer_five(harness, workdir)
            layer_six(harness, workdir)
            layer_seven(harness, workdir)
        finally:
            os.chdir(original_cwd)
    return 0


if __name__ == "__main__":
    reexec_with_fixed_hash_seed()
    sys.exit(main())
