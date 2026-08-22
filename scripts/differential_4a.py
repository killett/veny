#!/usr/bin/env python
"""Old-vs-new behavioural differential for phase 4a of the veny re-architecture.

Phase 4a replaced the ``Options`` god object's readers with five values --
``Settings``, ``Target``, ``ImportScan``, ``Requirements`` and ``VenvHandle``.
A green unit suite cannot see a regression in a change of that size, because
the tests move with the code: every one of them was repointed onto the new
values in the same commits that introduced them.

This driver reuses phase 3e's harness wholesale rather than reimplementing it.
``scripts/differential_3e.py`` already drives ``veny.cli.main()`` through argv
in two trees, with a counting clock, a fixed hash seed, a purged bytecode cache
and a stand-in at every subprocess, network and venv boundary -- and it runs
unmodified against the 4a tree, which is itself evidence that ``main()``'s
observable surface did not move. What this file adds is:

* **Four layers 3e did not drive**, each aimed at something 4a changed or was
  told to leave alone: a directory argument (Task 1's sanctioned change), a
  script that does not exist (latent defect 2, closed by the same task),
  ``--feeling-lucky`` with no last-used record (3e residual-risk item 1: no
  layer set that flag at all), and ``--reqs``.
* **A rewritten layer 4 report.** 3e read ``install_succeeded`` and
  ``requirements_file`` off the Options. Both left it in Task 6 --
  ``install_succeeded`` is a return value now and ``requirements_file`` lives
  on the ``VenvHandle`` -- so 3e's version reports ``<absent>`` and
  ``<not written>`` against the new tree, losing the coverage rather than
  showing a difference. This one reads the requirements file off disk, which
  both trees can answer.

How to run it, and against what base::

    git archive 4d1846c src/veny | tar -x -C /tmp/old-veny
    pixi run python scripts/differential_4a.py /tmp/old-veny > /tmp/old.txt
    pixi run python scripts/differential_4a.py /workspace    > /tmp/new.txt
    diff -u /tmp/old.txt /tmp/new.txt

``4d1846c`` is the phase-4a branch point ("Merge branch
'pipeline-and-cli-slimming': phase 3e of the veny re-architecture"). The
argument is a *tree root* holding ``src/veny``; it is inserted with
``sys.path.insert``, never through ``PYTHONPATH``, because ``pixi.toml``'s
``[activation.env]`` sets ``PYTHONPATH = "src"`` and would silently overwrite
it, testing the live source twice.

WHAT THE DIFF IS EXPECTED TO CONTAIN
------------------------------------

Not empty. These hunks are sanctioned; anything else is a regression:

0. The ``veny.cli.__file__`` header line, by construction -- it is the evidence
   of which tree ran.
1. **A directory argument is a usage error** (Task 1, user ruling 2026-08-21).
   Layer 8: the old tree raises ``IsADirectoryError`` out of ``main()``; the
   new one logs a message and returns 2.
2. **A missing script is a usage error** (Task 1, closing latent defect 2).
   Layer 9: the old tree raises ``FileNotFoundError``; the new one returns 2.
3. **``install_succeeded`` is no longer on the Options.** Layer 4 reports it as
   ``<absent>`` on the new tree. It is a return value from
   ``setup_virtualenv`` now; the rename decision it feeds is compared through
   the venv folder name instead, which both trees print.

MUTATION EVIDENCE
-----------------

A differential that cannot fail proves nothing. Five deliberate regressions,
one per value object, measured 2026-08-21 against a clean diff of **29 lines**
(three hunks, 10 differing lines):

===================================================  ==========
Regression                                           Diff lines
===================================================  ==========
Clean tree                                                   29
M1 ``Target.python_command`` never filled                   216
M2 a second ``Settings`` with ``rawlog`` hardcoded           37
M3 the repair pass's ``Requirements`` discarded             197
M4 ``VenvHandle`` resolves the interpreter symlink           92
M5 the ``ImportScan`` not seeded                            353
Reverted                                                     29
===================================================  ==========

The first run of this driver caught only M5: 3e's stand-ins answered ``""``
for the interpreter, passed the repair pass's input straight through, and
built no ``bin/python`` symlink, so M1, M3 and M4 were all no-ops against it
and every layer ran with ``rawlog=False`` so M2 was invisible.
``tighten_stand_ins`` below is what fixed that, and the numbers above are from
after it. A weak stand-in does not make a driver wrong; it makes it silent,
which is worse.

WHAT THIS FOUND
---------------

One regression, before the phase merged, that the unit suite could not see:
Task 6 moved ``venv_dir`` and ``venv_python`` onto the frozen ``VenvHandle``
and deleted them from ``Options``. Nothing read them off ``Options`` any more,
so 439 tests stayed green -- but ``ek.save_options_to_json`` serializes that
object's ``__dict__``, so the last-used record silently stopped containing a
venv at all, and ``load_last_used_venv_python``'s ``hasattr`` check would have
answered False for every script, forever. Both fields were restored as
persistence payload, written from the handle at the save.
``test_wiring_4a::test_the_saved_record_carries_the_venv_the_run_actually_used``
now closes it in-process.

RESIDUAL RISK
-------------

What this driver still cannot see. Phase 4b and 4c inherit every item.

1. **A second interpreter.** Every layer runs with one Python, so
   ``stdlib_index.resolve``'s fallback and the ``python_command`` that reaches
   ``venv_build_interpreter`` are compared only in their default shape.
2. **The in-virtualenv branch under a tool install.** 3e's layer 6 forces
   ``sys.prefix != sys.base_prefix``, but the guard's real-world behaviour --
   veny installed by ``uv tool install``, where it is *always* True -- is
   phase 4c's, and no in-process layer reproduces it.
3. **The alias index's disk cache and session-rejection store.** Stubbed at
   ``alias_index.build``, so ``AliasIndex``'s mutability -- the design's one
   deliberate exception to the frozen rule -- is never exercised here.
4. **The real scanner over a real tree.** ``dict_of_custom_modules`` is stubbed
   (it would walk the tree under test and answer differently in each tree for a
   reason that is not behaviour), so the seeding phase 4a's Task 4 rests on is
   compared only through the empty case.
5. **``ImportScan`` accumulation across a deep import graph.** The layers use
   one- and two-import scripts; the recursion that the seven scan fields exist
   for is not driven.
6. **Manifest content.** The folder *name* is compared; the JSON inside the
   venv is not, so a ``record_venv_state`` argument that changed the manifest
   without changing the name is invisible.
7. **The three latent defects 3e recorded.** ``-y``/``--yes`` still never
   reaches ``blank_slate`` (the ``getattr`` reads ``y``, argparse writes
   ``yes``); ``run_script(rawlog=…)`` is still dead at three of four sites.
   Both are unchanged by 4a and outside these layers.
8. **Concurrency.** One process, one run at a time.

This is a script, not a test. It is deliberately NOT wired into pytest: it
compares two trees, only one of which exists inside any given checkout.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load_3e() -> Any:
    """Import the phase-3e driver as a module, whatever the working directory.

    Returns:
        The imported module.
    """
    spec = importlib.util.spec_from_file_location(
        "differential_3e", _HERE / "differential_3e.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit("cannot import scripts/differential_3e.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["differential_3e"] = module
    spec.loader.exec_module(module)
    return module


D3E = _load_3e()


def tighten_stand_ins(tree: Any, harness: Any) -> None:
    """Make four of phase 4a's value objects observable in the diff.

    3e's stand-ins were chosen for a phase that moved code between modules.
    Against 4a they are too loose: measured 2026-08-21, four of five
    deliberate regressions -- one per value object -- left the diff at exactly
    29 lines. Each was invisible for its own reason, and each is fixed here:

    * ``ek.find_preferred_python_version`` answered ``""``, so
      ``Target.python_command`` was empty in every layer and dropping the
      ``dataclasses.replace`` that fills it changed nothing. It now answers a
      distinctive command, which reaches ``venv_build_interpreter`` and the uv
      argv.
    * ``verify.verify_and_repair_imports`` passed its input straight through,
      so discarding its result was a no-op. It now returns a *changed* record
      set, which the manifest and the folder name carry.
    * ``uv venv`` created nothing, so ``venv_python`` never pointed at a real
      symlink and ``.resolve()`` on it was a no-op. It now builds a real
      ``bin/python`` symlink into a base interpreter outside the venv.
    * The layers all ran with ``rawlog=False``, so a hardcoded ``rawlog=False``
      inside the scan adapter was invisible. Layer 12 below drives ``--rawlog``.

    Args:
        tree: 3e's Tree, naming the modules in whichever shape this tree has.
        harness: 3e's Harness, already wired.
    """
    ek: Any = importlib.import_module("emmykit")

    ek.find_preferred_python_version = lambda: "the-runs-own-python"

    real_repair = tree.verify.verify_and_repair_imports

    def repairing_repair(**kwargs: Any) -> Any:
        """Record as 3e did, but hand back a record the input did not contain.

        A pass-through stub cannot tell "the result was folded back in" from
        "the result was thrown away". Renaming the pip name makes the
        difference reach the manifest and the folder name.
        """
        real_repair(**kwargs)
        return frozenset(
            type(record)(
                import_name=record.import_name,
                pip_name=f"{record.pip_name}-repaired",
            )
            for record in kwargs["uninstalled"]
        )

    tree.verify.verify_and_repair_imports = repairing_repair

    base_bin = harness.workdir / "base-interpreter" / "bin"
    base_bin.mkdir(parents=True, exist_ok=True)
    base_python = base_bin / "python3"
    if not base_python.exists():
        base_python.write_text("#!/bin/sh\n")

    real_check_call = subprocess.check_call

    def building_check_call(command: Any, *args: Any, **kwargs: Any) -> int:
        """Record as 3e did, then build a venv shaped like a real one.

        `uv venv <dir>` really does leave a ``bin/python`` symlink pointing at
        the base interpreter. Without one, ``.resolve()`` on that path is the
        identity and a handle that wrongly resolves it is indistinguishable
        from one that does not.
        """
        status = real_check_call(command, *args, **kwargs)
        argv = [str(part) for part in command]
        if len(argv) >= 3 and argv[1] == "venv":
            venv_bin = Path(argv[2]) / "bin"
            venv_bin.mkdir(parents=True, exist_ok=True)
            link = venv_bin / "python"
            if not link.exists():
                link.symlink_to(base_python)
        return status

    subprocess.check_call = building_check_call  # type: ignore[assignment]


def layer_twelve_rawlog(harness: Any, workdir: Path) -> None:
    """--rawlog, so the flag that silences veny is compared in both states.

    Every 3e layer runs with rawlog False, which makes a hardcoded
    ``rawlog=False`` anywhere below cli.py invisible -- including inside the
    scan adapter phase 4a rewrote.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 12: --rawlog ===")
    _, cwd = harness.begin(workdir / "layer12")
    script = D3E.a_script(cwd, "needs_yaml.py", "import yaml\n")
    argv = ["--rawlog", "--no-cache", os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    harness.dump()


def layer_four_rewritten(harness: Any, workdir: Path) -> None:
    """A cache miss that builds, reported without reading the Options.

    3e's version read ``install_succeeded`` and ``requirements_file`` off the
    Options. Task 6 moved both -- the first is a return value, the second is a
    ``VenvHandle`` field -- so that version reports ``<absent>`` against the
    new tree and compares nothing. This one reads the requirements file off
    disk, under whichever folder the run ended up with, which both trees can
    answer identically.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 4: a cache miss that builds ===")
    _, cwd = harness.begin(workdir / "layer4")
    script = D3E.a_script(cwd, "needs_yaml.py", "import yaml\nprint(yaml)\n")
    argv = ["--no-cache", os.fspath(script), "positional"]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    options = harness.options
    venv_dir = getattr(options, "venv_dir", None)
    print(f"  venv folder: {Path(venv_dir).name if venv_dir is not None else None}")
    # Off disk, not off the Options: the run may have renamed the directory
    # out from under the "failed-" prefix, so both candidates are checked and
    # whichever exists is reported.
    home = Path(os.environ["HOME"]) / "veny"
    written = sorted(
        (p.parent.name, p.read_text().splitlines())
        for p in home.glob("*/requirements.txt")
    )
    print(f"  requirements.txt on disk: {written}")
    harness.dump()


def layer_eight_a_directory(harness: Any, workdir: Path) -> None:
    """A directory as the positional argument.

    Task 1's sanctioned change, and the whole of what the folder-scanning
    deletion is observable as: the old tree lets ``IsADirectoryError`` out of
    ``main()``, the new one logs a message and returns 2.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 8: a directory as the script argument ===")
    _, cwd = harness.begin(workdir / "layer8")
    a_folder = cwd / "a_folder"
    a_folder.mkdir()
    D3E.a_script(a_folder, "inside.py", "import yaml\n")
    argv = [os.fspath(a_folder)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    harness.dump()


def layer_nine_a_missing_script(harness: Any, workdir: Path) -> None:
    """A positional naming a path that is not there.

    Latent defect 2, which Task 1 closed in the same stroke: the old tree lets
    ``FileNotFoundError`` out of ``main()``, the new one returns 2.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 9: a script that does not exist ===")
    _, cwd = harness.begin(workdir / "layer9")
    argv = [os.fspath(cwd / "no_such_script.py")]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    harness.dump()


def layer_ten_feeling_lucky_cold(harness: Any, workdir: Path) -> None:
    """--feeling-lucky with no last-used record in the script's directory.

    3e's residual-risk item 1: no layer set this flag at all, so its whole
    early-return path was uncompared. It runs before ``ek.configure_logging``
    and reports with ``print()`` rather than ``logging``, which is why the
    stdout of the run itself matters here.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 10: --feeling-lucky, no record ===")
    _, cwd = harness.begin(workdir / "layer10")
    script = D3E.a_script(cwd, "lucky.py", "import yaml\n")
    argv = ["--feeling-lucky", os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    harness.dump()


def layer_eleven_reqs(harness: Any, workdir: Path) -> None:
    """--reqs, so the extra-requirements mapping reaches classification.

    Phase 4a turned that mapping from an Options field into an argument
    threaded through ``list_packages`` and ``split_imports``. A layer that
    never sets --reqs compares only the empty case.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 11: --reqs ===")
    _, cwd = harness.begin(workdir / "layer11")
    script = D3E.a_script(cwd, "needs_yaml.py", "import yaml\n")
    (cwd / "extra_requirements.txt").write_text("rich>=13.0\n")
    argv = ["--no-cache", "--reqs", os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    home = Path(os.environ["HOME"]) / "veny"
    written = sorted(
        (p.parent.name, p.read_text().splitlines())
        for p in home.glob("*/requirements.txt")
    )
    print(f"  requirements.txt on disk: {written}")
    harness.dump()


def main() -> int:
    """Capture every layer against the tree named on the command line.

    Returns:
        Zero on success; 2 when the tree root is missing or unusable.
    """
    if len(sys.argv) < 2:
        print("usage: differential_4a.py <tree-root>")
        return 2
    root = Path(sys.argv[1]).resolve()
    if not (root / "src" / "veny").is_dir():
        print(f"no src/veny under {root}")
        return 2

    sys.dont_write_bytecode = True
    purged = D3E.purge_pycache(root / "src")
    sys.path.insert(0, str(root / "src"))

    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="veny-4a-") as scratch:
        workdir = Path(scratch).resolve()
        # Before the first veny import: Options() reads Path.home() at
        # construction, and ~/veny must be neither read nor written.
        (workdir / "home").mkdir()
        os.environ["HOME"] = os.fspath(workdir / "home")
        tree = D3E.Tree()
        print(f"veny.cli.__file__: {tree.cli.__file__}")
        print(f"tree shape: {'split (3e)' if tree.split else 'monolithic (pre-3e)'}")
        print(f"PYTHONHASHSEED: {os.environ.get('PYTHONHASHSEED')}", file=sys.stderr)
        print(f"__pycache__ directories purged: {purged}", file=sys.stderr)

        harness = D3E.Harness(tree, workdir)
        D3E.install_stand_ins(tree, harness)
        tighten_stand_ins(tree, harness)
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
        root_logger.addHandler(D3E.CaptureHandler(harness))
        root_logger.setLevel(logging.INFO)

        try:
            D3E.layer_one(harness, workdir)
            D3E.layer_two(harness, tree, workdir)
            D3E.layer_three(harness, workdir)
            layer_four_rewritten(harness, workdir)
            D3E.layer_five(harness, workdir)
            D3E.layer_six(harness, workdir)
            D3E.layer_seven(harness, workdir)
            layer_eight_a_directory(harness, workdir)
            layer_nine_a_missing_script(harness, workdir)
            layer_ten_feeling_lucky_cold(harness, workdir)
            layer_eleven_reqs(harness, workdir)
            layer_twelve_rawlog(harness, workdir)
        finally:
            os.chdir(original_cwd)
    return 0


def reexec_with_fixed_hash_seed() -> None:
    """Restart this process with PYTHONHASHSEED=0 if it did not start that way.

    3e's version of this re-execs ``differential_3e.__file__``, so calling it
    from here would silently run 3e's layers instead of these -- measured
    2026-08-21, when it did exactly that and produced an eleven-layer script's
    seven-layer output. This one re-execs *this* file.
    """
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    if os.environ.get("VENY_DIFFERENTIAL_4A_REEXEC") == "1":
        print(
            "WARNING: could not fix PYTHONHASHSEED; orderings may vary",
            file=sys.stderr,
        )
        return
    os.environ["PYTHONHASHSEED"] = "0"
    os.environ["VENY_DIFFERENTIAL_4A_REEXEC"] = "1"
    os.execv(sys.executable, [sys.executable, "-B", __file__, *sys.argv[1:]])


if __name__ == "__main__":
    reexec_with_fixed_hash_seed()
    raise SystemExit(main())
