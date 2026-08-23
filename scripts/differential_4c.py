#!/usr/bin/env python
"""Old-vs-new behavioural differential for phase 4c of the veny re-architecture.

Phase 4c is four small, unrelated behaviour changes, none of which touches a
module boundary the way 3d-3e or 4a-4b did:

1. **The in-virtualenv guard.** ``last_used.is_virtualenv`` -- ``sys.prefix !=
   sys.base_prefix`` -- is deleted. ``last_used.active_virtualenv_dir`` now
   returns ``Path | None``, reading only ``VIRTUAL_ENV``, and
   ``pipeline.run``'s middle branch takes it by walrus:
   ``elif (active_venv := last_used.active_virtualenv_dir()) is not None:``.
   ``uv tool install veny`` puts veny's own interpreter inside a virtualenv
   permanently, so the old check was true on every run regardless of what the
   user had activated; a missing import under that install dead-ended at
   "Please deactivate the current virtual environment and run the script
   again." with the cache search unreachable behind it. (USER RULING,
   2026-08-20.)
2. **``--feeling-lucky``'s missing signal normalization.** ``cli._shell_status``
   now owns the ``128 - returncode`` arithmetic that the ordinary path already
   had, and both of ``main()``'s exit points use it. A lucky run whose child
   is killed by SIGKILL used to return ``-9`` straight from
   ``pipeline.feeling_lucky``'s status; it now returns ``137``, matching every
   other path.
3. **``-y`` reaches ``blank_slate``.** ``pipeline.blank_slate`` reads
   ``args.yes`` -- the dest argparse actually writes for ``-y``/``--yes`` --
   instead of ``args.y``, which argparse never wrote. ``--blank-slate -y``
   used to prompt anyway; it no longer does.
4. **Every launch announces itself.** All four ``run_script`` call sites now
   pass ``announce=True`` (one already did); the other three log
   ``Running command: ...`` before running, unless ``--rawlog``.

A green unit suite cannot see any of this, for the same reason it could not
see 4a's or 4b's changes: the tests moved with the code in the same commits
that changed it, and none of these four is the kind of thing a single-process
assertion states on its own -- two of them are differences in *when* a
function that already existed gets called (the walrus vs. the two-step
check), one is an arithmetic normalization that only shows up for a negative
number, and one is a logging side effect.

This driver reuses phase 4b's harness wholesale, the way 4b reused 4a's and
4a reused 3e's -- ``scripts/differential_4b.py`` already drives
``veny.cli.main()`` through argv in two trees, with a counting clock, a fixed
hash seed, a purged bytecode cache, a stand-in at every subprocess, network
and venv boundary, and (its own addition) a fixed one-file-per-script
last-used record with a spy on both its readers. All eighteen of 4b's layers
run here unchanged; none of them was built to exercise what this phase
changed, but two of them incidentally do -- layers 7 and 18 already drive
``--blank-slate -y``, so change 3 (the prompt) moves them too -- and the
announce lines (change 4) land wherever any inherited layer launches
something. What this file adds is:

* **Four layers, one per sanctioned change** (19-22, numbered on from 4b's
  18): an activated environment (19), the tool-install shape (20, the layer
  the whole phase exists for), ``--feeling-lucky`` killed by a signal (21),
  and ``--blank-slate -y`` with the prompt made to matter (22). Each builds
  its own environment rather than inheriting the driver's, because ``pixi
  run`` sets ``PYTHONPATH=src`` *and* means ``sys.prefix == sys.base_prefix``
  with no ``VIRTUAL_ENV`` -- the one shape layers 19 and 20 must each escape
  on purpose.
* **A local, two-call-wide spy on ``active_virtualenv_dir``**, installed and
  removed around one ``harness.drive()`` each in layers 19 and 20, that
  prints what the function answered and the *type* of that answer. Installed
  globally instead, it would fire on every layer with a missing import, most
  of which never reach the old tree's equivalent call at all (the old
  function is gated behind ``is_virtualenv()`` first) -- a flood of
  ``-> None`` notes on layers this phase never touched. Without the type
  half of the probe, M2 below is invisible: ``environment.venv_python_for``'s
  ``ek.ensure_dir`` accepts a ``str`` exactly as readily as a ``Path``, so a
  regression that drops ``ek.ensure_path`` on the way out changes no message,
  no argv and no status. 4b paid for this same lesson with its own M2.
* **The old tree's real ``is_virtualenv``, reinstated for layer 20 only.**
  4b's harness stubs ``last_used.is_virtualenv`` globally to
  ``lambda: harness.in_virtualenv`` (a boolean the harness controls), which
  is enough for layer 19's "an activated environment" and for 4b's inherited
  layer 6, but layer 20 needs the *real* ``sys.prefix != sys.base_prefix``
  check, because M1 below mutates ``sys.prefix`` reading, not the harness's
  flag, and a probe that only reads the flag would not see it. The real
  function is captured before the harness's stand-ins are installed --
  ``getattr(last_used, "is_virtualenv", None)``, so the file imports against
  the new tree too, where the attribute does not exist until the harness's
  own stub creates it a few lines later -- and swapped back in only for the
  duration of layer 20.
* **``respin_stand_ins`` retired to ``install_repair_switch_and_parse_spy``.**
  4b's version bridged two shapes of ``cli.parse_arguments`` -- ``(options)
  -> None`` before phase 4b, ``() -> Namespace`` after -- and restored the
  real ``ek.save_options_to_json`` so the old side of *that* phase's diff
  still wrote a record. Both trees this phase compares are post-4b: the
  parse shape does not move, and nothing calls ``ek.save_options_to_json``
  any more in either tree, so both a TypeError-tolerant spy and the
  restoration it was paired with are dead weight. What survives is the
  repair-rename switch (``harness.repair_renames``), which the inherited
  last-used layers (14-18) and this phase's own layer 21 still need, and a
  plain record of the parsed ``Namespace`` for layer 2's flag report.

How to run it, and against what base::

    git archive 9af1f09 src/veny | tar -x -C /tmp/old-veny-4c
    pixi run python scripts/differential_4c.py /tmp/old-veny-4c > /tmp/old.txt
    pixi run python scripts/differential_4c.py /workspace      > /tmp/new.txt
    diff -u /tmp/old.txt /tmp/new.txt

``9af1f09`` is ``main`` immediately before this phase ("docs: write plan 4c,
the last of the phase-4 behaviour changes"; a docs-only commit -- the branch
point for source is identical to its parent, ``f7b11fc``). ``git archive``
into a scratch directory, never ``git checkout`` inside this working tree:
a prior session's checkout-and-back sequence left files from an intermediate
commit stuck in the tree, restoring content HEAD had already deleted. The
argument is a *tree root* holding ``src/veny``; it is inserted with
``sys.path.insert``, never through ``PYTHONPATH``, because ``pixi.toml``'s
``[activation.env]`` sets ``PYTHONPATH = "src"`` and would silently overwrite
it, testing the live source twice and producing a meaningless empty diff.

WHAT THE DIFF IS EXPECTED TO CONTAIN
------------------------------------

Measured 2026-08-23: **132 lines, 9 hunks**. Every hunk is one of five
things; anything else is a regression.

0. The ``veny.cli.__file__`` header line, by construction -- it is the
   evidence of which tree ran. (Hunk 1.)
1. **The deactivate-message dead end becoming a cache search.** Layer 20: the
   old tree logs "Already in a virtual environment.", then "The current
   virtual environment does not have all the required packages.", then
   "Please deactivate the current virtual environment and run the script
   again.", and ``find_match_dir_in_cache reached: False``. The new tree logs
   neither "Already in a virtual environment." nor the deactivate message,
   goes straight to the cache search, and ``find_match_dir_in_cache reached``
   is ``True``.
2. **The lucky status.** Layer 21: ``main(): 'returned -9'`` on the old tree,
   ``main(): 'returned 137'`` on the new one.
3. **The prompt.** Layers 7, 18 (inherited, both already drive
   ``--blank-slate -y``) and 22 (this phase's own): the old tree's captured
   calls include ``ek.prompt_then_confirm(...)``; the new tree's do not.
   Layer 22 additionally shows ``~/veny survived: True`` on the old tree
   (the harness's stub is made to decline for this one layer, so a real
   prompt now has a real consequence) against ``False`` on the new one, where
   ``-y`` skips the prompt and the deletion always happens.
4. **The announce lines.** Everywhere a launch happens without ``--rawlog``:
   a new ``Running command: ...`` log line on the new tree, at every layer
   whose run reaches ``run_script`` through one of the three sites that did
   not already pass ``announce=True`` (the ordinary "everything already
   installed" launch, the in-a-virtualenv launch, and the lucky-path launch).
   Measured at layers 1, 6, 16 and 19. The fourth site -- the cache-hit
   launch -- already had it, so layers that only exercise that one (2, 4, 14,
   15, 17, 18, 20) show no line 4 hunk, even though 20's own launch goes
   through it too.

MUTATION EVIDENCE
-----------------

Five deliberate regressions, measured 2026-08-23 against a clean diff of
**132 lines**. The kill signal is the second column, not the first: a
mutation can change what a line says without changing how many lines the
diff has -- M3, M4 and M5 below all *shrink* it, because each one makes the
new tree behave more like the old one at the spot it touches, not less.

=====================================================  ====  =========
Regression                                              Diff   vs clean
=====================================================  ====  =========
Clean tree                                               132          0
M1 the guard reads ``sys.prefix`` again                  540        508
M2 ``active_virtualenv_dir`` returns a ``str``            141          9
M3 ``_shell_status`` skipped on the lucky return          124         10
M4 ``-y`` read from the wrong dest again                  101         39
M5 ``announce=True`` dropped from the three new sites      98          44
Reverted                                                  132          0
=====================================================  ====  =========

Each was introduced in the live tree with a single ``Edit``, measured against
the unchanged old-tree capture, reverted with ``git checkout -- <file>``
(never a manual undo), and re-measured; ``git diff`` was empty afterwards and
the number returned to 132 every time. "vs clean" is
``diff <old-vs-clean-new> <old-vs-mutant-new>``'s own differing-line count,
with each side's ``+++`` header (which carries this machine's capture
timestamp and would otherwise add two meaningless differing lines to every
row) stripped first.

* **M1's blast radius is wide.** ``active_virtualenv_dir`` returning
  ``Path(sys.prefix)`` instead of ``None`` whenever ``VIRTUAL_ENV`` is unset
  makes the walrus true on *every* layer that reaches it with a missing
  import and no ``VIRTUAL_ENV`` of its own -- not just layer 20, which exists
  to name the shape cleanly, but layers 1, 3, 4, 5 and more besides, each of
  which starts logging "Already in a virtual environment." and, depending on
  ``harness.bulk_check``, either the deactivate message or a launch through a
  path that used to be the cache search. Layer 20 gives the single cleanest
  reading of it; the mutation is not confined there.
* **M2 was a no-op until the type probe existed**, the same lesson 4b's own
  M2 taught it a phase earlier: ``environment.venv_python_for``'s
  ``ek.ensure_dir`` takes a ``str`` exactly as readily as a ``Path``, so
  without the ``-> ... (str)`` note in layer 19 (M2 only touches the
  ``VIRTUAL_ENV``-declared branch, which layer 20's unset scenario never
  reaches) the regression changes no message, no argv, and no status
  main() returns. All nine differing lines are the one real hunk this adds:
  a ``@@`` header, six lines of context, and the changed answer/type pair.
* **M3 is invisible everywhere but layer 21.** Every other lucky layer in
  this file uses a non-negative ``harness.script_status`` (4a's layer 10 has
  no record at all; 4b's layer 16 uses the harness default, 7), and
  ``_shell_status`` is the identity function for a non-negative input, so
  only the one layer built to return ``-9`` can tell M3 apart from a clean
  tree. The diff *shrinks* (132 -> 124) because the one hunk M3 removes --
  layer 21's ``-9`` vs. ``137`` -- is bigger than the ``@@`` header noise its
  removal shifts elsewhere.
* **M4 removes the prompt hunks at three layers, not one.** ``blank_slate``
  reading ``args.y`` again makes the confirmation prompt fire on the new tree
  too, at every layer that drives ``--blank-slate -y`` -- the two inherited
  from 4b (7, 18) as well as this phase's own 22 -- so all three of category
  3's hunks collapse at once, plus layer 22's ``prompt issued`` /
  ``~/veny survived`` lines flip back to matching the old tree. Diff shrinks,
  132 -> 101.
* **M5 removes every announce line at once**, because it is one edit applied
  at all three sites this phase touched: every "Running command: ..." line
  category 4 added disappears together, at layers 1, 6, 16 and 19. Layer 20's
  own launch survives M5 -- it goes through the fourth, pre-existing
  ``announce=True`` site (the cache-hit launch), which this mutation does not
  touch. Diff shrinks furthest of the five, 132 -> 98.

THE LIVE TWO-RUN CHECK
-----------------------

Not run from this file. Task 8 of this phase's plan is a live end-to-end
check in a real virtualenv, run from a real shell -- the one shape this
driver cannot itself construct, because ``pixi run`` always has ``sys.prefix
== sys.base_prefix`` and no ``VIRTUAL_ENV``, and this driver must not run
under ``pixi run`` for that check. See that task's own report for the
transcript.

RESIDUAL RISK
-------------

What this driver still cannot see. 4b's docstring carried sixteen items; one
of them -- "the in-virtualenv branch under a tool install" -- is exactly what
layer 20 now drives, so it is retired rather than renumbered past. The
remaining fifteen are renumbered 1-15 below, unchanged in substance; 16-19
are this phase's own additions.

1. **A second interpreter.** Every layer runs with one Python, so
   ``stdlib_index.resolve``'s fallback and the ``python_command`` that reaches
   ``venv_build_interpreter`` are compared only in their default shape.
2. **The alias index's disk cache and session-rejection store.** Stubbed at
   ``alias_index.build``, so ``AliasIndex``'s mutability -- the design's one
   deliberate exception to the frozen rule -- is never exercised here.
3. **The real scanner over a real tree.** ``dict_of_custom_modules`` is
   stubbed, so the seeding phase 4a's Task 4 rests on is compared only through
   the empty case.
4. **``ImportScan`` accumulation across a deep import graph.** The layers use
   one- and two-import scripts.
5. **Manifest content.** The folder *name* is compared; the JSON inside the
   venv is not.
6. **Two of the three latent defects 3e recorded were still live at 4b's
   close; both are closed now.** ``-y``/``--yes`` not reaching
   ``blank_slate`` was defect 1, closed by this phase's Task 3. ``run_script``'s
   dead ``rawlog`` at three of its four call sites was defect 3, closed by
   this phase's Task 4. Defect 2 -- a missing script leaving
   ``FileNotFoundError`` uncaught -- was already fixed by phase 4a's Task 1,
   before 4b's own docstring was written; 4b's list said "three ... still
   live" and named two, which double-counted the closed one. This phase
   started with **two** live, not three, and closes both.
7. **Concurrency.** One process, one run at a time.
8. **A degraded record.** ``last_used.load`` has five "no record" branches --
   unreadable, not JSON, not an object, either path missing, either path
   empty. Unit tests cover them; no layer here writes a corrupt record.
9. **A non-atomic write.** ``last_used.save`` is ``write_text``, not
   write-then-rename, so a run killed mid-write leaves a truncated record.
10. **The forged pre-4b record.** Layer 17's is hand-built by
    ``write_old_format_record`` with six keys, not the three a real 4b-era
    record has.
11. **The pip-name rename is off in layers 14-16 and 21.** 4a's stand-in
    renames every repaired package to ``<name>-repaired``, which is turned
    off in the layers whose whole subject is a second run reusing the
    first's environment -- now including layer 21, whose seed run must
    survive its own lucky follow-up.
12. **Long lists in the record are elided at eight items.**
13. **One record, one script, one directory.**
14. **``~/veny`` never holds a real virtual environment.** ``uv venv`` is a
    stand-in; the record's ``venv_python`` is proved followable, not proved
    to be an interpreter.
15. **The driver's record filter mirrors the code under test.**
    ``record_files`` uses ``--blank-slate``'s own four-part rule.
16. **``args`` still does not round-trip onto disk.** 4b's fourth user ruling
    (``find_match_dir_in_cache`` no longer writing ``args.latest``/
    ``args.last_used`` onto the namespace) was one of that phase's own
    sanctioned hunks, not a residual-risk item, but the gap it left is
    unaffected by this phase and worth naming here: layer 2's four flag
    lines are still read off the ``Namespace`` this driver captures itself,
    not off anything on disk. New this phase.
17. **``sys.prefix`` is monkeypatched only for the harness's own process.**
    Layer 20 changes ``sys.prefix`` in-process; it does not fork or exec, so
    anything that reads ``sys.executable`` or resolves the interpreter by
    querying the OS rather than the ``sys`` module would not see the fake
    prefix. Nothing veny does happens to do that today.
18. **``harness.in_virtualenv`` and the real ``is_virtualenv`` can now
    disagree, and layer 19 relies on the harness's flag rather than the real
    check.** Layer 19 sets ``harness.in_virtualenv = True`` to drive the old
    tree's stubbed gate, the same way 4b's inherited layer 6 does; it does
    not restore the real function the way layer 20 does, because layer 19's
    subject is ``active_virtualenv_dir``, which both trees answer for real
    either way. A regression in the *old* tree's real ``is_virtualenv``
    itself would not be caught by layer 19 -- only by layer 20, and only for
    the one input (``sys.prefix`` patched, ``VIRTUAL_ENV`` unset) it drives.
19. **The active environment layers (19, 20) never actually launch a real
    interpreter.** ``check_packages_in_venv`` is the harness's fixed-answer
    stub in both, so "the active environment has the package" and "it does
    not" are asserted by ``harness.bulk_check``, never discovered by probing
    a real ``site-packages``.

This is a script, not a test. It is deliberately NOT wired into pytest: it
compares two trees, only one of which exists inside any given checkout.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load_4b() -> Any:
    """Import the phase-4b driver as a module, whatever the working directory.

    Returns:
        The imported module. Importing it also imports phases 4a's and 3e's,
        which 4b exposes as its ``D4A`` and ``D3E`` attributes.
    """
    spec = importlib.util.spec_from_file_location(
        "differential_4b", _HERE / "differential_4b.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit("cannot import scripts/differential_4b.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["differential_4b"] = module
    spec.loader.exec_module(module)
    return module


D4B = _load_4b()
D4A = D4B.D4A
D3E = D4B.D3E


# ---------------------------------------------------------------------------
# What's retired from 4b's stand-in wiring, and what replaces it
# ---------------------------------------------------------------------------


def install_repair_switch_and_parse_spy(
    tree: Any, harness: Any, *, real_parse: Any
) -> None:
    """Install the repair-rename switch, and record parsed args for layer 2.

    4b's ``respin_stand_ins`` bridged two shapes of ``cli.parse_arguments`` --
    ``(options) -> None`` before that phase, ``() -> Namespace`` after -- and
    restored the real ``ek.save_options_to_json``, because that phase's old
    tree still called it and 3e's stand-in had stubbed it to a note. Both
    trees this phase compares are post-4b: the parse shape does not move
    again, and nothing calls ``ek.save_options_to_json`` in either tree any
    more, so both the shape bridge and the restoration are dead weight and
    are not carried forward. What survives:

    * The repair-rename switch (``harness.repair_renames``), which 4b's
      inherited layers 14-18 and this phase's own layer 21 still need --
      those layers' whole subject is a second run reusing an earlier one's
      environment, which 4a's rename-every-repair stand-in would defeat.
    * A plain record of the parsed ``Namespace`` on ``harness.options``, for
      layer 2's report of the four selection flags.

    Args:
        tree:       3e's Tree.
        harness:    3e's Harness, already wired.
        real_parse: ``cli.parse_arguments`` as it was before this call.
    """
    renaming_repair = tree.verify.verify_and_repair_imports

    def switchable_repair(**kwargs: Any) -> Any:
        """Rename the repaired pip name, or not, by the harness's policy.

        Returns:
            The repair pass's records, renamed or as they came in.
        """
        renamed = renaming_repair(**kwargs)
        if getattr(harness, "repair_renames", True):
            return renamed
        return frozenset(kwargs["uninstalled"])

    tree.verify.verify_and_repair_imports = switchable_repair

    def spy_parse(*args: Any, **kwargs: Any) -> Any:
        """Parse for real, and publish the result.

        Returns:
            Whatever the real parser returned, unchanged.
        """
        result = real_parse(*args, **kwargs)
        harness.options = SimpleNamespace(args=result)
        return result

    tree.cli.parse_arguments = spy_parse


# ---------------------------------------------------------------------------
# Layers 19-22: one per sanctioned change
# ---------------------------------------------------------------------------


def layer_nineteen_activated_environment(
    harness: Any, tree: Any, workdir: Path
) -> None:
    """Layer 19: an activated environment, where both trees are expected to agree.

    ``VIRTUAL_ENV`` set to a directory the layer creates, running a script
    with a missing import. This is the direction sanctioned change 1
    preserves -- the old reader's own docstring called ``sys.prefix`` "the
    fallback" and ``VIRTUAL_ENV`` the primary signal -- so both trees should
    take the middle branch of ``pipeline.run`` and report the same
    environment. Layer 20 is where they diverge.

    ``harness.in_virtualenv`` drives the old tree's stubbed
    ``is_virtualenv()`` the same way 4b's inherited layer 6 does; this layer
    is not testing that gate; it is testing what ``active_virtualenv_dir``
    answers once the gate has already said yes, on both trees, for real.

    Args:
        harness: 3e's Harness, already wired.
        tree:    3e's Tree.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 19: an activated environment (VIRTUAL_ENV set) ===")
    layer_dir = workdir / "layer19"
    _, cwd = harness.begin(layer_dir)
    harness.in_virtualenv = True
    harness.bulk_check = True
    active = layer_dir / "active-venv"
    (active / "bin").mkdir(parents=True, exist_ok=True)
    os.environ["VIRTUAL_ENV"] = os.fspath(active)
    script = D3E.a_script(cwd, "needs_yaml.py", "import yaml\nprint(yaml)\n")
    argv = [os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  VIRTUAL_ENV: {harness.scrub(os.environ['VIRTUAL_ENV'])}")

    real_active_dir = tree.last_used.active_virtualenv_dir

    def spy_active_dir(*args: Any, **kwargs: Any) -> Any:
        """Answer for real, then note the answer and its type.

        Returns:
            Whatever the real function returned, unchanged.
        """
        result = real_active_dir(*args, **kwargs)
        harness.note(
            f"last_used.active_virtualenv_dir() -> {D4B.describe(harness, result)}"
        )
        return result

    tree.last_used.active_virtualenv_dir = spy_active_dir
    try:
        print(f"  main(): {harness.drive(argv)}")
    finally:
        tree.last_used.active_virtualenv_dir = real_active_dir
    harness.dump()


def layer_twenty_tool_install_shape(
    harness: Any, tree: Any, workdir: Path, *, real_is_virtualenv: Any
) -> None:
    """Layer 20: the tool-install shape -- the layer the whole phase exists for.

    ``VIRTUAL_ENV`` unset, ``sys.prefix`` monkeypatched away from
    ``sys.base_prefix``: what ``uv tool install veny`` looks like to the
    guard, whether or not the user has activated anything of their own.

    Old tree: ``is_virtualenv()`` reads ``sys.prefix != sys.base_prefix`` and
    finds it true, so the middle branch runs; ``active_virtualenv_dir()``
    finds no ``VIRTUAL_ENV`` and falls back to ``Path(sys.prefix)`` -- veny's
    own borrowed environment, which does not have the target's packages --
    and the run dead-ends at "Please deactivate the current virtual
    environment and run the script again." with status 1.
    ``cache_search.find_match_dir_in_cache`` is never called.

    New tree: ``active_virtualenv_dir()`` reads no ``VIRTUAL_ENV`` and
    returns ``None`` outright, regardless of ``sys.prefix``. The walrus is
    false, the middle branch is skipped, and
    ``cache_search.find_match_dir_in_cache`` runs against the same usable
    cache layer 2 already proved it can search, and finds the same folder.

    The bulk "does this venv have everything" check is faked to fail for
    exactly one interpreter path -- the borrowed prefix -- and to answer
    ``harness.bulk_check`` (True here) for every other one. A single global
    ``harness.bulk_check = False`` would have been simpler, but
    ``check_venv_dir`` calls the very same stub while scoring the cache
    folders on the new tree's path, and a global False would fail every
    cached folder too, forcing the new side into a full "build from scratch"
    attempt the harness cannot carry to a real interpreter -- losing the
    clean "same folder layer 2 found" reading this layer exists to give.

    The real ``is_virtualenv`` is reinstated for the old tree only for the
    duration of this layer: 4b's harness stubs it globally to
    ``lambda: harness.in_virtualenv``, a flag ``sys.prefix`` does not touch,
    so without this swap M1 (``active_virtualenv_dir`` reading ``sys.prefix``
    again) would have nothing here to make visible on the old side, and this
    layer's whole "old tree really reads sys.prefix" claim would be
    unverified.

    Args:
        harness:            3e's Harness, already wired.
        tree:                3e's Tree.
        workdir:             The scratch directory this run owns.
        real_is_virtualenv: The old tree's real ``is_virtualenv``, captured
                            before the harness's stand-ins overwrote it, or
                            ``None`` on a tree that never had the attribute.
    """
    print(
        "=== LAYER 20: the tool-install shape "
        "(VIRTUAL_ENV unset, sys.prefix != sys.base_prefix) ==="
    )
    home, cwd = harness.begin(workdir / "layer20")
    my_dir = home / "veny"
    my_dir.mkdir(parents=True, exist_ok=True)
    D4B.a_usable_cache(tree, harness, my_dir)
    harness.bulk_check = True
    os.environ.pop("VIRTUAL_ENV", None)
    fake_prefix = workdir / "layer20-fake-tool-install-prefix"
    fake_prefix.mkdir(parents=True, exist_ok=True)
    script = D3E.a_script(cwd, "needs_yaml.py", "import yaml\nprint(yaml)\n")
    argv = [os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  VIRTUAL_ENV set: {'VIRTUAL_ENV' in os.environ}")

    stub_is_virtualenv = getattr(tree.last_used, "is_virtualenv", None)
    if real_is_virtualenv is not None:
        tree.last_used.is_virtualenv = real_is_virtualenv
    real_active_dir = tree.last_used.active_virtualenv_dir
    real_find_match = tree.cache_search.find_match_dir_in_cache
    real_check_packages = tree.verify.check_packages_in_venv
    reached: list[str] = []

    def spy_active_dir(*args: Any, **kwargs: Any) -> Any:
        """Answer for real, then note the answer and its type.

        Returns:
            Whatever the real function returned, unchanged.
        """
        result = real_active_dir(*args, **kwargs)
        harness.note(
            f"last_used.active_virtualenv_dir() -> {D4B.describe(harness, result)}"
        )
        return result

    def spy_find_match(*args: Any, **kwargs: Any) -> Any:
        """Record that the cache search was reached, then search for real.

        Returns:
            Whatever the real search returned, unchanged.
        """
        reached.append("find_match_dir_in_cache")
        return real_find_match(*args, **kwargs)

    def only_the_borrowed_venv_lacks_packages(venv_python: Any, **kwargs: Any) -> Any:
        """Fail the bulk check for the borrowed prefix only.

        Every other interpreter path is scored the ordinary way -- the fake
        stand-in answering ``harness.bulk_check`` -- so a cached folder that
        would satisfy the run still does.

        Returns:
            False for the borrowed prefix; the real stand-in's answer for
            anything else.
        """
        if Path(venv_python).is_relative_to(fake_prefix):
            harness.note(
                "verify.check_packages_in_venv(venv_python="
                f"{harness.scrub(os.fspath(venv_python))}, borrowed=True) -> False"
            )
            return False
        return real_check_packages(venv_python, **kwargs)

    tree.last_used.active_virtualenv_dir = spy_active_dir
    tree.cache_search.find_match_dir_in_cache = spy_find_match
    tree.verify.check_packages_in_venv = only_the_borrowed_venv_lacks_packages
    original_prefix = sys.prefix
    sys.prefix = os.fspath(fake_prefix)
    try:
        print(f"  sys.prefix != sys.base_prefix: {sys.prefix != sys.base_prefix}")
        print(f"  main(): {harness.drive(argv)}")
    finally:
        sys.prefix = original_prefix
        tree.last_used.active_virtualenv_dir = real_active_dir
        tree.cache_search.find_match_dir_in_cache = real_find_match
        tree.verify.check_packages_in_venv = real_check_packages
        if stub_is_virtualenv is not None:
            tree.last_used.is_virtualenv = stub_is_virtualenv
    print(f"  find_match_dir_in_cache reached: {bool(reached)}")
    harness.dump()


def layer_twenty_one_lucky_killed_by_signal(harness: Any, workdir: Path) -> None:
    """Layer 21: --feeling-lucky, whose child is killed by a signal.

    A seed run first, so a real record exists to be lucky about (mirrors 4b's
    layer 16); the lucky run's stand-in script then reports
    ``harness.script_status = -9``, standing in for a child killed by
    SIGKILL. Old tree: ``main()`` returns ``pipeline.feeling_lucky``'s status
    unchanged, ``-9``. New tree: ``main()`` applies ``cli._shell_status`` on
    this path too, since phase 4c, so ``-9`` becomes ``128 - (-9) = 137``,
    the same status a script killed the same way would get on any other
    path.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 21: --feeling-lucky, killed by a signal ===")
    layer_dir = workdir / "layer21"
    _, cwd = harness.begin(layer_dir)
    harness.repair_renames = False
    script = D3E.a_script(cwd, "lucky.py", "import yaml\nprint(yaml)\n")
    seed = ["--no-cache", os.fspath(script)]
    print(f"  seeding argv: {[harness.scrub(part) for part in seed]}")
    print(f"  seeding main(): {harness.drive(seed)}")
    D4B.print_record_names(harness, cwd)

    _, cwd = harness.begin(layer_dir)
    harness.repair_renames = False
    harness.script_status = -9
    argv = ["--feeling-lucky", os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    harness.repair_renames = True
    harness.dump()


def layer_twenty_two_blank_slate_dash_y(harness: Any, workdir: Path) -> None:
    """Layer 22: --blank-slate -y, where the prompt has a real consequence.

    4b's inherited layers 7 and 18 already drive ``--blank-slate -y``, but
    both answer the confirmation prompt "yes" whenever it fires (the
    harness's global stand-in), so both trees end up deleting the directory
    either way -- the only visible difference there is whether the
    ``ek.prompt_then_confirm(...)`` note appears at all, a cosmetic
    difference in a captured call list. This layer swaps that stand-in for a
    local one that answers "no" instead, for the duration of this layer only,
    so a real prompt has a real, measurable consequence: whether ``~/veny``
    survives.

    Old tree: ``blank_slate`` reads ``getattr(args, "y", False)``, which
    argparse never wrote, so it is always ``False`` regardless of ``-y``; the
    prompt fires, this layer's stand-in declines, and ``~/veny`` survives.
    New tree: ``blank_slate`` reads ``args.yes``, which ``-y`` sets ``True``;
    the prompt never fires, and ``~/veny`` is deleted unconditionally.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 22: --blank-slate -y (a prompt that matters) ===")
    home, cwd = harness.begin(workdir / "layer22")
    my_dir = home / "veny"
    (my_dir / "myenv-3.12-20260101-010101").mkdir(parents=True, exist_ok=True)

    ek: Any = importlib.import_module("emmykit")
    real_confirm = ek.prompt_then_confirm
    prompted: list[str] = []

    def declining_confirm(prompt: str) -> bool:
        """Record the prompt, then decline it.

        Returns:
            False, always -- so a real prompt has a real consequence here.
        """
        prompted.append(prompt)
        harness.note(f"ek.prompt_then_confirm({prompt!r})")
        return False

    ek.prompt_then_confirm = declining_confirm
    try:
        argv = ["--blank-slate", "-y"]
        print(f"  argv: {argv}")
        print(f"  main(): {harness.drive(argv)}")
    finally:
        ek.prompt_then_confirm = real_confirm
    print(f"  prompt issued: {bool(prompted)}")
    print(f"  ~/veny survived: {my_dir.is_dir()}")
    harness.dump()


def main() -> int:
    """Capture every layer against the tree named on the command line.

    Returns:
        Zero on success; 2 when the tree root is missing or unusable.
    """
    if len(sys.argv) < 2:
        print("usage: differential_4c.py <tree-root>")
        return 2
    root = Path(sys.argv[1]).resolve()
    if not (root / "src" / "veny").is_dir():
        print(f"no src/veny under {root}")
        return 2

    sys.dont_write_bytecode = True
    purged = D3E.purge_pycache(root / "src")
    sys.path.insert(0, str(root / "src"))

    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="veny-4c-") as scratch:
        workdir = Path(scratch).resolve()
        # Before the first veny import: the pre-4b state object reads
        # Path.home() at construction, and ~/veny must be neither read nor
        # written.
        (workdir / "home").mkdir()
        os.environ["HOME"] = os.fspath(workdir / "home")
        tree = D4B.a_tree()
        print(f"veny.cli.__file__: {tree.cli.__file__}")
        print(f"tree shape: {'split (3e)' if tree.split else 'monolithic (pre-3e)'}")
        print(f"PYTHONHASHSEED: {os.environ.get('PYTHONHASHSEED')}", file=sys.stderr)
        print(f"__pycache__ directories purged: {purged}", file=sys.stderr)

        # Captured before the harness's stand-ins run: on the old tree this
        # is the real sys.prefix-reading function; on the new tree the
        # attribute does not exist yet, so this is None. Either way the file
        # imports and runs against both trees.
        real_parse = tree.cli.parse_arguments
        real_is_virtualenv = getattr(tree.last_used, "is_virtualenv", None)

        harness = D3E.Harness(tree, workdir)
        D3E.install_stand_ins(tree, harness)
        D4A.tighten_stand_ins(tree, harness)
        install_repair_switch_and_parse_spy(tree, harness, real_parse=real_parse)
        D4B.spy_on_the_readers(tree, harness)
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
        root_logger.addHandler(D3E.CaptureHandler(harness))
        root_logger.setLevel(logging.INFO)

        try:
            D3E.layer_one(harness, workdir)
            D4B.layer_two_4b(harness, tree, workdir)
            D3E.layer_three(harness, workdir)
            D4B.layer_four_4b(harness, workdir)
            D3E.layer_five(harness, workdir)
            D3E.layer_six(harness, workdir)
            D3E.layer_seven(harness, workdir)
            D4A.layer_eight_a_directory(harness, workdir)
            D4A.layer_nine_a_missing_script(harness, workdir)
            D4A.layer_ten_feeling_lucky_cold(harness, workdir)
            D4A.layer_eleven_reqs(harness, workdir)
            D4A.layer_twelve_rawlog(harness, workdir)
            D4A.layer_thirteen_not_a_python_file(harness, workdir)
            layer_dir = D4B.layer_fourteen_writes_a_record(harness, workdir)
            D4B.layer_fifteen_reads_it_back(harness, layer_dir)
            D4B.layer_sixteen_lucky_with_a_record(harness, workdir)
            D4B.layer_seventeen_lucky_with_only_an_old_record(harness, tree, workdir)
            D4B.layer_eighteen_blank_slate_with_a_record(harness, workdir)
            layer_nineteen_activated_environment(harness, tree, workdir)
            layer_twenty_tool_install_shape(
                harness, tree, workdir, real_is_virtualenv=real_is_virtualenv
            )
            layer_twenty_one_lucky_killed_by_signal(harness, workdir)
            layer_twenty_two_blank_slate_dash_y(harness, workdir)
        finally:
            os.chdir(original_cwd)
    return 0


def reexec_with_fixed_hash_seed() -> None:
    """Restart this process with PYTHONHASHSEED=0 if it did not start that way.

    3e's, 4a's and 4b's versions each re-exec their own ``__file__``, so
    calling any of them from here would run that phase's layers instead of
    these. This one re-execs *this* file, and uses its own marker so an
    earlier phase's re-exec already in the environment cannot be mistaken for
    this one's.
    """
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    if os.environ.get("VENY_DIFFERENTIAL_4C_REEXEC") == "1":
        print(
            "WARNING: could not fix PYTHONHASHSEED; orderings may vary",
            file=sys.stderr,
        )
        return
    os.environ["PYTHONHASHSEED"] = "0"
    os.environ["VENY_DIFFERENTIAL_4C_REEXEC"] = "1"
    os.execv(sys.executable, [sys.executable, "-B", __file__, *sys.argv[1:]])


if __name__ == "__main__":
    reexec_with_fixed_hash_seed()
    raise SystemExit(main())
