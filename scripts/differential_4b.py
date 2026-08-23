#!/usr/bin/env python
"""Old-vs-new behavioural differential for phase 4b of the veny re-architecture.

Phase 4b replaced emmykit's options-JSON persistence with veny's own record.
Before it, a successful run serialised the whole per-run ``Options`` object
into the user's script directory under a per-run filename, and the next run
globbed that directory, sorted the matches by a timestamp parsed out of the
filename and handed the newest back to emmykit's loader. After it, veny writes
a three-key ``state.LastUsed`` payload to one fixed filename per script and
reads that one name back. The god object, the JSON type registry and the
pickle pathlib cutoff went with it.

A green unit suite cannot see a regression in a change of that size, because
the tests move with the code, and because the part that matters most -- what
lands on the user's disk and what the *next* run makes of it -- is a two-run
property that no single-process test asserts.

This driver reuses phase 4a's harness, which reuses phase 3e's, rather than
reimplementing either. 3e's drives ``veny.cli.main()`` through argv with a
counting clock, a fixed hash seed, a purged bytecode cache and a stand-in at
every subprocess, network and venv boundary; 4a's tightens four of those
stand-ins and adds six layers. All thirteen of 4a's layers run here, two of
them rewritten. What this file adds is:

* **Five layers 4a did not drive**, one per thing this phase changed: the run
  that writes a record (14, which prints the filename and the whole payload),
  a second run in the same directory that reads it back (15),
  ``--feeling-lucky`` with a record the tree wrote itself (16),
  ``--feeling-lucky`` where the only record is a pre-4b one (17, the
  sanctioned fallback), and ``--blank-slate`` over a directory holding both
  formats (18).
* **A probe on the two last-used readers**, noting the environment the answer
  names *and the type of that path*. Without it, dropping ``ek.ensure_path``
  on the way out of ``last_used.load`` is invisible: a ``str`` reaches
  ``run_script``, ``check_venv_dir`` and ``safe_is_file``, and all three
  accept it. M2 below is the measurement that says so.
* **Two 3e stand-ins undone.** ``cli.parse_arguments`` changed shape --
  ``(options) -> None`` became ``() -> Namespace`` -- so 3e's one-positional
  spy raises ``TypeError`` out of every layer against the new tree. And
  ``ek.save_options_to_json`` was stubbed to a note, which would have left the
  old tree writing no record at all: the read-back layers would have found
  nothing in *both* trees and called two cold runs equal. The real writer is
  restored, so the two formats are compared as files.
* **A rewritten layer 2 and layer 4.** Both read the chosen venv folder off
  ``options.venv_dir``. Phase 4b deleted the object it lived on, so against
  the new tree that line reports ``None`` and compares nothing -- 4a's own
  warning about layer 4, one phase later. Layer 2 reports the record the run
  wrote instead; layer 4's folder is already named in its requirements report.

How to run it, and against what base::

    git archive cf2ded4 src/veny | tar -x -C /tmp/old-veny
    pixi run python scripts/differential_4b.py /tmp/old-veny > /tmp/old.txt
    pixi run python scripts/differential_4b.py /workspace    > /tmp/new.txt
    diff -u /tmp/old.txt /tmp/new.txt

``cf2ded4`` is the phase-4b branch point ("Merge branch 'state-model-values':
phase 4a of the veny re-architecture"). The argument is a *tree root* holding
``src/veny``; it is inserted with ``sys.path.insert``, never through
``PYTHONPATH``, because ``pixi.toml``'s ``[activation.env]`` sets
``PYTHONPATH = "src"`` and would silently overwrite it, testing the live
source twice and producing a meaningless empty diff.

WHAT THE DIFF IS EXPECTED TO CONTAIN
------------------------------------

Measured 2026-08-22: **240 lines, eleven hunks**. Every hunk is one of six
things; anything else is a regression.

0. The ``veny.cli.__file__`` header line, by construction -- it is the
   evidence of which tree ran. (Hunk 1.)
1. **The record's filename.** ``.needs_yaml.py-veny-last-used-on-<stamp>.json``
   becomes ``.needs_yaml.py-veny-last-used.json``: one fixed file per script,
   not one per run (user ruling, 2026-08-21). (Hunks 2, 4, 7, 8, 10, 11.)
2. **The record's payload.** Layer 14 prints it in full. The old side is 76
   lines of emmykit-tagged ``Options.__dict__`` -- the parsed argparse
   namespace, ``log_mode``, ``home``, ``cwd``, ``shell``, ``rc_file``, the
   alias-index summary, ``pathlibcutoff``, the record's own path, and the
   running interpreter's whole standard-library index. The new side is three
   keys: ``venv_dir``, ``venv_python``, ``timestamp``. (Hunk 7.)
3. **The readers' own messages.** "No previous JSON files found in the script
   directory." becomes "No usable last-used record for <script>."; "No last
   used options found, so no venv_python to return." becomes "...no last used
   record found..."; and emmykit's "options loaded from <file>" disappears,
   because emmykit's loader is no longer called. (Hunks 2, 3, 5, 6, 9, 11.)
4. **The one fallback for a directory holding only a pre-4b record.** Layer
   17. The old tree globs, finds the whole-``Options`` JSON, follows it and
   runs the script from the environment it names, never touching the cache.
   The new tree reads one fixed filename, does not find it, prints "No luck",
   and the ordinary run takes over -- where the cache scan picks the same
   folder and runs the same script to the same status 7. Old records are
   ignored, not migrated (user ruling, 2026-08-21). (Hunk 11.)
5. **``find_match_dir_in_cache`` no longer writes onto the namespace.**
   ``args.latest`` reads True after a default run on the old tree and False on
   the new one: the selection policy's ``args.latest = True`` /
   ``args.last_used = False`` writes are locals now. This is the phase's
   fourth user ruling and it *is* part of the diff, which the task brief's
   list of three sanctioned hunks did not say. It was only ever observable
   because ``args`` was serialised into the options JSON -- it is inside the
   old side of hunk 7 as well, under ``"args"``. (Hunk 2.)

MUTATION EVIDENCE
-----------------

A differential that cannot fail proves nothing. Five deliberate regressions,
measured 2026-08-22 against a clean diff of **240 lines**. Diff size alone is
a blunt instrument here -- a mutation that renames a file changes the *content*
of a line the diff already carried without changing how many lines there are --
so the kill signal is the second column: how many lines of the diff moved away
from the clean one.

======================================================  ====  ==========
Regression                                              Diff  vs clean
======================================================  ====  ==========
Clean tree                                               240           0
M1 the record's filename loses its leading dot           236          34
M2 ``str`` instead of ``Path`` on read                   251          17
M3 the record written before the ``failed-`` rename      282          58
M4 the cache search's last-used pointer ignored          339         149
M5 the record never written at all                       279          81
Reverted                                                 240           0
======================================================  ====  ==========

Each was introduced in the live tree, measured, reverted from a copy taken
before the edit (never ``git checkout``), and re-measured; ``git diff`` was
empty afterwards and the number returned to 240.

Two of them taught the driver something:

* **M2 was a no-op until the reader probe existed.** Of the 17 lines it
  moves, only 6 are substantive -- ``last_used ... reader ->`` notes; the
  rest are 5 ``@@`` hunk headers and 6 lines of surrounding context.
  ``ek.ensure_path`` on the way out of
  ``last_used.load`` changes no message veny prints, no argv it builds and no
  status it returns, because ``run_script``, ``check_venv_dir`` and
  ``safe_is_file`` all accept a ``str``. Without ``spy_on_the_readers`` the
  differential would have called that regression clean -- 4a's
  ``tighten_stand_ins`` lesson repeating: a weak probe does not make a driver
  wrong, it makes it silent.
* **M1 shrinks the diff.** Dropping the leading dot makes the record invisible
  to ``--blank-slate``'s filter *and* to this driver's report, so the mutant's
  output loses lines rather than gaining them. A reviewer watching only for
  "the number went up" would miss it. That is why the table carries both
  columns.

M1 is also the mutation the source docstring predicts: ``record_path`` says the
name "still starts with a dot and still contains ``-{my_name}-``, which is what
--blank-slate's filter matches on", and layer 18 is there to hold it to that.

THE LIVE TWO-RUN CHECK
----------------------

Run from a real shell on 2026-08-22, not from a test. ``pixi run`` sets
``PYTHONPATH=src`` relative to *its own* working directory, so the runs are
``pixi run bash -c 'cd /tmp/venytest && PYTHONPATH=/workspace/src python -m
veny hello.py'`` -- setting the variable after activation, since activation
overwrites anything set before it. ``hello.py`` is ``import yaml`` plus a
print.

* **Run 1** -- exit 0, ``ok 6.0.3`` on the terminal. Logged "No usable
  last-used record for /tmp/venytest/hello.py.", then "Trying to load the
  latest matching venv now.", then "Found 4 matching venv folders in the
  cache." and "Using existing virtual environment:
  /home/claudeuser/veny/myenv-py3.13-20260819-220857-pyyaml".
* **The record appeared**, as one file, ``.hello.py-veny-last-used.json``::

      {
          "venv_dir": "/home/claudeuser/veny/myenv-py3.13-20260819-220857-pyyaml",
          "venv_python": "/home/claudeuser/veny/myenv-py3.13-20260819-220857-pyyaml/bin/python",
          "timestamp": "20260822-142846"
      }

* **Run 2** -- exit 0, ``ok 6.0.3``. It reused that environment through the
  record: no "No usable last-used record", no "Trying to load the latest
  matching venv now.", no "Checking the cache for a virtual environment..."
  and no "Found N matching venv folders". Straight from "Uninstalled imports:
  ['yaml']" to "Using existing virtual environment:
  /home/claudeuser/veny/myenv-py3.13-20260819-220857-pyyaml". The pointer
  answered; the scan never ran.
* **Record deleted, run 3** -- exit 0, ``ok 6.0.3``, no traceback. Back to
  "No usable last-used record ... Trying to load the latest matching venv now
  ... Found 4 matching venv folders ... Using existing virtual environment",
  and a fresh record written with a new timestamp (``20260822-142913``).
* **``--feeling-lucky`` with the record present** -- exit 0, "Last used
  venv_python found: .../bin/python" and then the script's own output, with no
  scan, no classification and no log configuration in between.
* **``--feeling-lucky`` with the record renamed to the pre-4b shape**
  (``.hello.py-veny-last-used-on-20260822-142913.json``) -- exit 0. The
  pointer missed, the ordinary run took over, the cache scan answered with the
  same environment. The live confirmation of hunk 4.

**Install shape: the pixi environment**, where ``sys.prefix ==
sys.base_prefix`` is True and ``last_used.is_virtualenv()`` is therefore
False. The middle branch of ``pipeline.run`` -- the one that runs the user's
script with the *active* environment rather than a cached one -- was not
exercised by any of these runs. That branch is phase 4c's, and 4c's live run
must not use this shape.

RESIDUAL RISK
-------------

What this driver still cannot see. Items 1-8 are 4a's, all still open; 9-16
are this phase's.

1. **A second interpreter.** Every layer runs with one Python, so
   ``stdlib_index.resolve``'s fallback and the ``python_command`` that reaches
   ``venv_build_interpreter`` are compared only in their default shape.
2. **The in-virtualenv branch under a tool install.** 3e's layer 6 forces
   ``sys.prefix != sys.base_prefix``, but the guard's real-world behaviour --
   veny installed by ``uv tool install``, where it is *always* True -- is
   phase 4c's, and neither an in-process layer nor the live check above
   reproduces it.
3. **The alias index's disk cache and session-rejection store.** Stubbed at
   ``alias_index.build``, so ``AliasIndex``'s mutability -- the design's one
   deliberate exception to the frozen rule -- is never exercised here.
4. **The real scanner over a real tree.** ``dict_of_custom_modules`` is
   stubbed, so the seeding phase 4a's Task 4 rests on is compared only through
   the empty case.
5. **``ImportScan`` accumulation across a deep import graph.** The layers use
   one- and two-import scripts.
6. **Manifest content.** The folder *name* is compared; the JSON inside the
   venv is not.
7. **Two of the three latent defects 3e recorded, still live.** ``-y``/
   ``--yes`` still never reaches ``blank_slate`` -- ``pipeline.blank_slate``
   reads ``getattr(args, "y", False)`` and argparse writes ``yes`` -- so
   layer 18 above goes through the confirmation prompt, which the harness
   answers yes to. ``run_script(rawlog=...)`` is still dead at three of its
   four call sites, because ``rawlog`` is read only in
   ``if announce and not rawlog`` and only one site passes
   ``announce=True``. Both are unchanged by 4b. The third, a missing script
   leaving ``FileNotFoundError`` travelling uncaught out of ``main``, was
   fixed by phase 4a's Task 1 and is no longer live.
8. **Concurrency.** One process, one run at a time.
9. **A degraded record.** ``last_used.load`` has five "no record" branches --
   unreadable, not JSON, not an object, either path missing, either path
   empty. Unit tests cover them; no layer here writes a corrupt record, so
   none of the five is compared against what the old tree did with the same
   file.
10. **A non-atomic write.** ``last_used.save`` is ``write_text``, not
    write-then-rename, so a run killed mid-write leaves a truncated record.
    Item 9's branches are what would catch it and item 8 is why no layer can
    produce it.
11. **The forged pre-4b record.** Layer 14's old-side record is written by the
    real ``ek.save_options_to_json``, but layer 17's is hand-built by
    ``write_old_format_record`` with six keys. A real user's record holds
    every key layer 14 prints; a fallback that keyed off one of the others
    would not be caught here.
12. **The pip-name rename is off in layers 14-16.** 4a's stand-in renames
    every repaired package to ``<name>-repaired``, which makes discarding the
    repair pass's result visible (4a's M3) but also means a venv one run
    builds can never satisfy the next -- fatal for layers whose whole subject
    is the second run. ``harness.repair_renames`` turns it off there and only
    there. Those three layers therefore cannot catch 4a's M3.
13. **Long lists in the record are elided at eight items.** The pre-4b payload
    embeds the running interpreter's stdlib index; printed in full it is 350
    of the diff's lines and a different 350 on a machine with a different
    Python. Only the old side has such a list, and the old side cannot
    regress, but a future record with a long list would be compared only by
    its length.
14. **One record, one script, one directory.** No layer puts two scripts'
    records in one directory, or a record belonging to a different script
    beside the one under test, so "reads one *named* file" is compared only
    where the name is unambiguous.
15. **``~/veny`` never holds a real virtual environment.** ``uv venv`` is a
    stand-in and the ``bin/python`` inside every cached folder is a file or a
    symlink this driver made, so the record's ``venv_python`` is proved
    followable, not proved to be an interpreter.
16. **The driver's record filter mirrors the code under test.**
    ``record_files`` uses ``--blank-slate``'s own four-part rule, so a record
    written outside that rule is reported as *absent* rather than as
    *differently named* -- which is exactly how M1 reads, and why its diff
    shrinks instead of growing.

This is a script, not a test. It is deliberately NOT wired into pytest: it
compares two trees, only one of which exists inside any given checkout.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load_4a() -> Any:
    """Import the phase-4a driver as a module, whatever the working directory.

    Returns:
        The imported module. Importing it also imports phase 3e's driver,
        which 4a exposes as its ``D3E`` attribute.
    """
    spec = importlib.util.spec_from_file_location(
        "differential_4a", _HERE / "differential_4a.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit("cannot import scripts/differential_4a.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["differential_4a"] = module
    spec.loader.exec_module(module)
    return module


D4A = _load_4a()
D3E = D4A.D3E

# What a hand-written pre-4b record is stamped with. Before the phase, veny
# wrote one JSON per successful run and globbed for the newest; the reader
# ignored anything stamped before ``pathlibcutoff`` (20250810-224900), so this
# has to be after it for the old tree to see the file at all.
OLD_FORMAT_STAMP = "20260101-010101"


def a_tree() -> Any:
    """Load 3e's Tree, on a tree that may no longer have ``run_options``.

    ``Tree.__init__`` imports ``veny.run_options`` by name whenever the tree
    is post-3e. Phase 4b deleted that module, so against the new tree the
    import raises before a single layer runs. A placeholder module is put in
    its place, and it is deliberately empty: the only thing 3e does with the
    attribute is ``hasattr(module, "dt")`` for the counting-clock swap, which
    an empty module correctly answers False to. Nothing in either tree
    *imports* it -- if anything ever did, the placeholder would be visible as
    an ``AttributeError`` rather than as a silent success.

    Returns:
        The loaded Tree.
    """
    if importlib.util.find_spec("veny.run_options") is None:
        sys.modules["veny.run_options"] = types.ModuleType("veny.run_options")
    return D3E.Tree()


# ---------------------------------------------------------------------------
# Reporting the record, which is the whole of what this phase changed
# ---------------------------------------------------------------------------


def record_files(script_dir: Path) -> list[Path]:
    """Every last-used record veny left in a script's directory.

    The filter is the one ``--blank-slate`` uses -- a dotfile whose name holds
    ``-veny-`` and whose suffix is ``.json`` -- so that both the pre-4b
    filename (``.x.py-veny-last-used-on-<stamp>.json``) and 4b's
    (``.x.py-veny-last-used.json``) are found by one rule rather than by two
    that could each be wrong in its own direction.

    Args:
        script_dir: The directory the script lives in.

    Returns:
        The records found, sorted by name.
    """
    return sorted(
        path
        for path in script_dir.iterdir()
        if path.is_file()
        and path.name.startswith(".")
        and "-veny-" in path.name
        and path.suffix.casefold() == ".json"
    )


def print_record_names(harness: Any, script_dir: Path) -> None:
    """Print which records the run left behind, without their contents.

    Args:
        harness:    3e's Harness, for path scrubbing.
        script_dir: The directory the script lives in.
    """
    names = [harness.scrub(path.name) for path in record_files(script_dir)]
    print(f"  last-used records: {names}")


ELISION_THRESHOLD = 8


def elide_long_lists(value: Any) -> Any:
    """Replace any list longer than a handful with a count of what it held.

    The pre-4b payload is the whole per-run state object, and one of its
    fields is the *running interpreter's* standard-library index -- 300-odd
    module names, and a different 300-odd on a machine with a different
    Python. Printed in full it is 350 of the diff's lines, all of them saying
    the same one thing, and it would move the measured diff size from machine
    to machine. Elided to a count, the fact survives ("veny used to serialise
    its stdlib index into the user's script directory") and the number stops
    depending on whose laptop ran it.

    Args:
        value: A decoded JSON value.

    Returns:
        The same value with long lists replaced by an elision marker.
    """
    if isinstance(value, dict):
        return {key: elide_long_lists(item) for key, item in value.items()}
    if isinstance(value, list):
        if len(value) > ELISION_THRESHOLD:
            return f"<{len(value)} items elided by the differential>"
        return [elide_long_lists(item) for item in value]
    return value


def print_record_contents(harness: Any, script_dir: Path) -> None:
    """Print every record the run left behind, name and payload.

    Both trees are asked the same question -- "what did you write, and what is
    in it" -- rather than each being asked about its own format, so the answer
    is a difference rather than a gap.

    Args:
        harness:    3e's Harness, for path scrubbing.
        script_dir: The directory the script lives in.
    """
    for path in record_files(script_dir):
        print(f"  record {harness.scrub(path.name)}:")
        payload = elide_long_lists(json.loads(path.read_text(encoding="utf-8")))
        rendered = harness.scrub(json.dumps(payload, indent=4, sort_keys=False))
        for line in rendered.splitlines():
            print(f"    {line}")


def write_old_format_record(
    script_dir: Path,
    python_script: Path,
    venv_dir: Path,
) -> Path:
    """Write a pre-4b whole-``Options`` record by hand.

    This is what every user with a veny habit already has in their script
    directories: one JSON per successful run, named ``last-used-on-<stamp>``,
    holding emmykit's tagged serialisation of the whole per-run state object.
    The new tree must ignore it -- user ruling, 2026-08-21, old records are
    ignored, not migrated -- which is only observable if a real one exists.

    Args:
        script_dir:    Where the record goes.
        python_script: The script it belongs to.
        venv_dir:      The environment it points at.

    Returns:
        The path written.
    """
    ek: Any = importlib.import_module("emmykit")
    path = (
        script_dir / f".{python_script.name}-veny-last-used-on-{OLD_FORMAT_STAMP}.json"
    )
    payload = ek.to_jsonable(
        {
            "my_name": "veny",
            "timestamp": OLD_FORMAT_STAMP,
            "python_script": python_script,
            "script_dir": script_dir,
            "venv_dir": venv_dir,
            "venv_python": venv_dir / "bin" / "python",
        },
        roundtrip=True,
    )
    path.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")
    return path


def a_usable_cache(tree: Any, harness: Any, my_dir: Path) -> None:
    """Build 3e's five-folder cache and give every folder a real interpreter.

    3e's cache is manifests only: no folder in it holds a ``bin/python``, so a
    record pointing into one is rejected by ``ek.safe_is_file`` before either
    tree gets as far as comparing formats. The layers that drive the last-used
    pointer need the pointer to be followable.

    Args:
        tree:    3e's Tree.
        harness: 3e's Harness, already wired.
        my_dir:  The throwaway directory standing in for ``~/veny``.
    """
    D3E.build_fake_cache(tree, my_dir)
    for folder in sorted(my_dir.iterdir()):
        if not folder.is_dir():
            continue
        interpreter = folder / "bin" / "python"
        interpreter.parent.mkdir(parents=True, exist_ok=True)
        if not interpreter.exists():
            interpreter.write_text("#!/bin/sh\n")
    harness.note(
        f"differential: gave {len(sorted(my_dir.iterdir()))} cached venvs a bin/python"
    )


# ---------------------------------------------------------------------------
# The stand-ins this phase needs on top of 3e's and 4a's
# ---------------------------------------------------------------------------


def describe(harness: Any, value: Any) -> str:
    """Render one path-shaped value with its type.

    The type is the point. ``ek.ensure_path`` on the way out of the reader is
    a one-line coercion whose absence changes no message veny prints, no argv
    it builds and no status it returns -- a ``str`` reaches ``run_script``,
    ``check_venv_dir`` and ``safe_is_file`` and all three accept it. It is
    only observable at all if something asks what type came back.

    Args:
        harness: 3e's Harness, for path scrubbing.
        value:   What the reader answered with.

    Returns:
        The scrubbed value and its type name, or ``None``.
    """
    if value is None:
        return "None"
    return f"{harness.scrub(os.fspath(value))} ({type(value).__name__})"


def spy_on_the_readers(tree: Any, harness: Any) -> None:
    """Record what the last-used readers answer, under one name in both trees.

    The two trees spell these differently -- ``load_last_used_options`` and
    ``load_last_used_venv_python`` before the phase, ``load`` and
    ``load_venv_python`` after -- and they answer with different types, an
    ``ek.Options`` against a ``state.LastUsed``. Noting the *type of the
    answer* would therefore differ for a reason that is not behaviour, so
    what is noted is the environment the answer names and the type of that
    path, which both trees can answer identically.

    Args:
        tree:    3e's Tree.
        harness: 3e's Harness, already wired.
    """
    module = tree.last_used
    record_name = "load" if hasattr(module, "load") else "load_last_used_options"
    python_name = (
        "load_venv_python"
        if hasattr(module, "load_venv_python")
        else "load_last_used_venv_python"
    )
    real_record = getattr(module, record_name)
    real_python = getattr(module, python_name)

    def spy_record(*args: Any, **kwargs: Any) -> Any:
        """Read the record for real, then note the environment it names.

        Returns:
            Whatever the real reader returned, unchanged.
        """
        result = real_record(*args, **kwargs)
        venv_dir = getattr(result, "venv_dir", None)
        harness.note(
            f"last_used record reader -> venv_dir={describe(harness, venv_dir)}"
        )
        return result

    def spy_python(*args: Any, **kwargs: Any) -> Any:
        """Read the interpreter for real, then note it and its type.

        Returns:
            Whatever the real reader returned, unchanged.
        """
        result = real_python(*args, **kwargs)
        harness.note(f"last_used interpreter reader -> {describe(harness, result)}")
        return result

    setattr(module, record_name, spy_record)
    setattr(module, python_name, spy_python)


def respin_stand_ins(
    tree: Any,
    harness: Any,
    *,
    real_parse: Any,
    real_save_options: Any,
) -> None:
    """Undo the two 3e stand-ins that phase 4b moved out from under.

    Both were written against a tree whose ``cli.parse_arguments`` took the
    per-run state object and whose persistence went through emmykit:

    * ``parse_arguments`` is ``parse_arguments(options) -> None`` on the old
      tree and ``parse_arguments() -> Namespace`` on the new one, so 3e's spy
      -- which takes exactly one positional -- raises ``TypeError`` out of
      ``main()`` in every layer against the new tree. The replacement takes
      either shape and publishes the same thing from both: a shim carrying the
      argparse namespace as ``.args``, which is all any layer here reads.
    * ``ek.save_options_to_json`` was stubbed to a note. Stubbed, the old tree
      writes no record at all, and every layer that reads one back would find
      nothing in *both* trees -- the driver would compare two cold runs and
      call them equal. The real writer is restored, so the old tree really
      leaves its whole-``Options`` JSON on disk and the two formats can be
      compared as files.

    Args:
        tree:              3e's Tree.
        harness:           3e's Harness, already wired.
        real_parse:        ``cli.parse_arguments`` as it was before 3e's
                           stand-ins were installed.
        real_save_options: ``ek.save_options_to_json`` likewise.
    """
    ek: Any = importlib.import_module("emmykit")
    ek.save_options_to_json = real_save_options

    renaming_repair = tree.verify.verify_and_repair_imports

    def switchable_repair(**kwargs: Any) -> Any:
        """Rename the repaired pip name, or not, by the harness's policy.

        4a's stand-in renames every repaired package to ``<name>-repaired`` so
        that discarding the repair pass's result is visible. The side effect
        is that a venv built by one run can never satisfy the next one: its
        manifest advertises a package no later run asks for. That is fine for
        every 4a layer and fatal for this phase's, whose whole subject is a
        second run reusing the first run's environment. The rename stays on
        everywhere 4a had it and is turned off only in the layers that need
        one run's venv to still be usable by the next.

        Returns:
            The repair pass's records, renamed or as they came in.
        """
        renamed = renaming_repair(**kwargs)
        if getattr(harness, "repair_renames", True):
            return renamed
        return frozenset(kwargs["uninstalled"])

    tree.verify.verify_and_repair_imports = switchable_repair

    def spy_parse(*args: Any, **kwargs: Any) -> Any:
        """Parse for real in whichever shape this tree has, and publish it.

        Returns:
            Whatever the real parser returned, unchanged.
        """
        result = real_parse(*args, **kwargs)
        parsed = args[0].args if args else result
        harness.options = SimpleNamespace(args=parsed)
        return result

    tree.cli.parse_arguments = spy_parse


# ---------------------------------------------------------------------------
# Layers 4a's report read off the deleted state object
# ---------------------------------------------------------------------------


def layer_two_4b(harness: Any, tree: Any, workdir: Path) -> None:
    """A cache hit: which folder wins, how it was decided, and what launched.

    3e's version of this layer read the chosen folder off ``options.venv_dir``
    and the four selection flags off ``options.args``. Phase 4b deleted the
    object the first came from, so that line reports ``None`` against the new
    tree and compares nothing; the folder is read out of the record the run
    wrote instead, which both trees answer.

    The four flag lines stay, and they *do* differ: the phase's fourth user
    ruling stopped ``find_match_dir_in_cache`` writing its selection decisions
    back onto the namespace. Keeping the probe is the point -- that difference
    used to reach disk inside the options JSON.

    Args:
        harness: 3e's Harness, already wired.
        tree:    3e's Tree.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 2: a cache hit ===")
    home, cwd = harness.begin(workdir / "layer2")
    my_dir = home / "veny"
    my_dir.mkdir(parents=True, exist_ok=True)
    a_usable_cache(tree, harness, my_dir)
    script = D3E.a_script(cwd, "needs_yaml.py", "import yaml\nprint(yaml)\n")

    sequence: list[str] = []
    real_read = tree.venv_cache.read_manifest
    real_satisfies = tree.venv_cache.satisfies

    def spy_read(venv_dir: Any) -> Any:
        """Record which folder's manifest is read, then read it.

        Returns:
            The manifest the real reader returned.
        """
        sequence.append(f"read_manifest({Path(venv_dir).name})")
        return real_read(venv_dir)

    def spy_satisfies(manifest: Any, *args: Any, **kwargs: Any) -> Any:
        """Record which manifest is matched, then match it.

        Returns:
            What the real matcher answered.
        """
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
    print("  call sequence:")
    for entry in sequence:
        print(f"    {entry}")
    for flag in ("latest", "oldest", "last_used", "smallest"):
        print(
            f"  args.{flag} after the run: {getattr(harness.options.args, flag, '<absent>')}"
        )
    print_record_names(harness, cwd)
    harness.dump()


def layer_four_4b(harness: Any, workdir: Path) -> None:
    """A cache miss that builds, reported without the deleted state object.

    4a's rewrite of this layer already read the requirements file off disk
    rather than off the Options; the one line it still read from there -- the
    venv folder name -- is dropped, because the folder is named in the
    requirements report and in the record the run wrote.

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
    home = Path(os.environ["HOME"]) / "veny"
    written = sorted(
        (p.parent.name, p.read_text().splitlines())
        for p in home.glob("*/requirements.txt")
    )
    print(f"  requirements.txt on disk: {written}")
    print_record_names(harness, cwd)
    harness.dump()


# ---------------------------------------------------------------------------
# What phase 4b changed
# ---------------------------------------------------------------------------


def layer_fourteen_writes_a_record(harness: Any, workdir: Path) -> Path:
    """The write: one run, and the record it leaves in the script's directory.

    This is the phase in one layer. The old tree hands the whole per-run state
    object to ``ek.save_options_to_json``, which builds a per-run filename off
    three of its fields and serialises its entire ``__dict__``; the new tree
    writes ``last_used.save``'s three-key payload to one fixed filename.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.

    Returns:
        The layer's directory, so the next layer can re-enter it.
    """
    print("=== LAYER 14: the run that writes the record ===")
    layer_dir = workdir / "layer14"
    _, cwd = harness.begin(layer_dir)
    harness.repair_renames = False
    script = D3E.a_script(cwd, "needs_yaml.py", "import yaml\nprint(yaml)\n")
    argv = ["--no-cache", os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    print_record_names(harness, cwd)
    print_record_contents(harness, cwd)
    harness.dump()
    return layer_dir


def layer_fifteen_reads_it_back(harness: Any, layer_dir: Path) -> None:
    """The read: a second run in the same directory, with the record present.

    Re-enters layer 14's directory rather than building a fresh one, so the
    record under test is one this tree really wrote in this run -- not one the
    driver forged, which would be the driver's opinion of the format rather
    than the tree's.

    With no selection flag, ``find_match_dir_in_cache``'s first pass is the
    last-used pointer. A hit is visible as "Using existing virtual
    environment" naming the folder layer 14 built, with no cache scan before
    it.

    Args:
        harness:   3e's Harness, already wired.
        layer_dir: Layer 14's directory, re-entered.
    """
    print("=== LAYER 15: the second run, reading the record back ===")
    _, cwd = harness.begin(layer_dir)
    harness.repair_renames = False
    script = cwd / "needs_yaml.py"
    argv = [os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(
        f"  records before the run: {[harness.scrub(p.name) for p in record_files(cwd)]}"
    )
    print(f"  main(): {harness.drive(argv)}")
    print_record_names(harness, cwd)
    harness.dump()


def layer_sixteen_lucky_with_a_record(harness: Any, workdir: Path) -> None:
    """``--feeling-lucky`` with a record this tree wrote itself.

    4a's layer 10 drives the flag with *no* record, which compares only the
    early "no luck" return. This drives the hit: one ordinary run to leave a
    record, then the lucky run that follows the pointer straight to the
    interpreter without scanning, classifying or building anything.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 16: --feeling-lucky with a record ===")
    layer_dir = workdir / "layer16"
    _, cwd = harness.begin(layer_dir)
    harness.repair_renames = False
    script = D3E.a_script(cwd, "lucky.py", "import yaml\nprint(yaml)\n")
    seed = ["--no-cache", os.fspath(script)]
    print(f"  seeding argv: {[harness.scrub(part) for part in seed]}")
    print(f"  seeding main(): {harness.drive(seed)}")
    print_record_names(harness, cwd)

    _, cwd = harness.begin(layer_dir)
    harness.repair_renames = False
    argv = ["--feeling-lucky", os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    harness.repair_renames = True
    harness.dump()


def layer_seventeen_lucky_with_only_an_old_record(
    harness: Any, tree: Any, workdir: Path
) -> None:
    """``--feeling-lucky`` where the only record is a pre-4b one.

    The sanctioned fallback, and the one place a user with a veny habit sees
    this phase: the old tree globs, finds the whole-``Options`` JSON and runs
    the script from the environment it names, never touching the cache. The
    new tree reads one fixed filename, does not find it, says so, and lets the
    ordinary run take over -- where the cache scan answers with the same
    environment. Same script, same status, reached two ways.

    The record points at the folder ``--latest`` would pick, so that "the
    pointer answered" and "the scan answered" are distinguishable by the route
    in the capture rather than only by the outcome.

    Args:
        harness: 3e's Harness, already wired.
        tree:    3e's Tree.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 17: --feeling-lucky with only a pre-4b record ===")
    home, cwd = harness.begin(workdir / "layer17")
    harness.repair_renames = True
    my_dir = home / "veny"
    my_dir.mkdir(parents=True, exist_ok=True)
    a_usable_cache(tree, harness, my_dir)
    script = D3E.a_script(cwd, "lucky.py", "import yaml\nprint(yaml)\n")
    newest = my_dir / tree.venv_cache.build_folder_name(
        venv_name="myenv",
        interpreter_tag="3.12",
        timestamp="20260101-040404",
        pip_names=["PyYAML", "filler-one", "filler-two", "filler-three"],
    )
    stale = write_old_format_record(cwd, script, newest)
    print(f"  pre-4b record: {harness.scrub(stale.name)}")
    print(f"  it points at: {harness.scrub(os.fspath(newest))}")
    argv = ["--feeling-lucky", os.fspath(script)]
    print(f"  argv: {[harness.scrub(part) for part in argv]}")
    print(f"  main(): {harness.drive(argv)}")
    print_record_names(harness, cwd)
    harness.dump()


def layer_eighteen_blank_slate_with_a_record(harness: Any, workdir: Path) -> None:
    """``--blank-slate`` in a directory holding records of both formats.

    ``blank_slate``'s filter is four OR'd name tests, not a glob, and the one
    that matches records asks for a dotfile whose name holds ``-veny-`` and
    whose suffix is ``.json``. 4b changed the filename that filter has to
    match. A new name that fell outside it would leave the user's records
    behind forever, and no unit test of ``blank_slate`` would notice, because
    the tests write the filenames they expect.

    Args:
        harness: 3e's Harness, already wired.
        workdir: The scratch directory this run owns.
    """
    print("=== LAYER 18: --blank-slate over both record formats ===")
    home, cwd = harness.begin(workdir / "layer18")
    my_dir = home / "veny"
    my_dir.mkdir(parents=True, exist_ok=True)
    script = D3E.a_script(cwd, "keeper.py", "import yaml\n")
    write_old_format_record(cwd, script, my_dir / "myenv-3.12-20260101-010101")
    (cwd / ".keeper.py-veny-last-used.json").write_text(
        json.dumps({"venv_dir": "x", "venv_python": "y", "timestamp": "z"}) + "\n"
    )
    (cwd / "keep_me.json").write_text("{}\n")
    argv = ["--blank-slate", "-y"]
    print(f"  argv: {argv}")
    print(f"  cwd before: {sorted(p.name for p in cwd.iterdir())}")
    print(f"  main(): {harness.drive(argv)}")
    print(f"  cwd afterwards: {sorted(p.name for p in cwd.iterdir())}")
    harness.dump(sort_logs=True)


def main() -> int:
    """Capture every layer against the tree named on the command line.

    Returns:
        Zero on success; 2 when the tree root is missing or unusable.
    """
    if len(sys.argv) < 2:
        print("usage: differential_4b.py <tree-root>")
        return 2
    root = Path(sys.argv[1]).resolve()
    if not (root / "src" / "veny").is_dir():
        print(f"no src/veny under {root}")
        return 2

    sys.dont_write_bytecode = True
    purged = D3E.purge_pycache(root / "src")
    sys.path.insert(0, str(root / "src"))

    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="veny-4b-") as scratch:
        workdir = Path(scratch).resolve()
        # Before the first veny import: the pre-4b state object reads
        # Path.home() at construction, and ~/veny must be neither read nor
        # written.
        (workdir / "home").mkdir()
        os.environ["HOME"] = os.fspath(workdir / "home")
        tree = a_tree()
        print(f"veny.cli.__file__: {tree.cli.__file__}")
        print(f"tree shape: {'split (3e)' if tree.split else 'monolithic (pre-3e)'}")
        print(f"PYTHONHASHSEED: {os.environ.get('PYTHONHASHSEED')}", file=sys.stderr)
        print(f"__pycache__ directories purged: {purged}", file=sys.stderr)

        ek: Any = importlib.import_module("emmykit")
        real_parse = tree.cli.parse_arguments
        real_save_options = ek.save_options_to_json

        harness = D3E.Harness(tree, workdir)
        D3E.install_stand_ins(tree, harness)
        D4A.tighten_stand_ins(tree, harness)
        respin_stand_ins(
            tree,
            harness,
            real_parse=real_parse,
            real_save_options=real_save_options,
        )
        spy_on_the_readers(tree, harness)
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
        root_logger.addHandler(D3E.CaptureHandler(harness))
        root_logger.setLevel(logging.INFO)

        try:
            D3E.layer_one(harness, workdir)
            layer_two_4b(harness, tree, workdir)
            D3E.layer_three(harness, workdir)
            layer_four_4b(harness, workdir)
            D3E.layer_five(harness, workdir)
            D3E.layer_six(harness, workdir)
            D3E.layer_seven(harness, workdir)
            D4A.layer_eight_a_directory(harness, workdir)
            D4A.layer_nine_a_missing_script(harness, workdir)
            D4A.layer_ten_feeling_lucky_cold(harness, workdir)
            D4A.layer_eleven_reqs(harness, workdir)
            D4A.layer_twelve_rawlog(harness, workdir)
            D4A.layer_thirteen_not_a_python_file(harness, workdir)
            layer_dir = layer_fourteen_writes_a_record(harness, workdir)
            layer_fifteen_reads_it_back(harness, layer_dir)
            layer_sixteen_lucky_with_a_record(harness, workdir)
            layer_seventeen_lucky_with_only_an_old_record(harness, tree, workdir)
            layer_eighteen_blank_slate_with_a_record(harness, workdir)
        finally:
            os.chdir(original_cwd)
    return 0


def reexec_with_fixed_hash_seed() -> None:
    """Restart this process with PYTHONHASHSEED=0 if it did not start that way.

    3e's and 4a's versions each re-exec their own ``__file__``, so calling
    either from here would run that phase's layers instead of these. This one
    re-execs *this* file, and uses its own marker so a 4a re-exec already in
    the environment cannot be mistaken for this one's.
    """
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    if os.environ.get("VENY_DIFFERENTIAL_4B_REEXEC") == "1":
        print(
            "WARNING: could not fix PYTHONHASHSEED; orderings may vary",
            file=sys.stderr,
        )
        return
    os.environ["PYTHONHASHSEED"] = "0"
    os.environ["VENY_DIFFERENTIAL_4B_REEXEC"] = "1"
    os.execv(sys.executable, [sys.executable, "-B", __file__, *sys.argv[1:]])


if __name__ == "__main__":
    reexec_with_fixed_hash_seed()
    raise SystemExit(main())
