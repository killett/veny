#!/usr/bin/env python
"""Old-vs-new behavioural differential for phase 3d of the veny re-architecture.

Phase 3d moved ~1,100 lines out of ``src/veny/cli.py`` into ``verify.py``,
``cache_search.py`` and ``last_used.py``. A green unit suite cannot see a
regression in that kind of move, because the tests move with the code. This
driver runs the *same* three observable behaviours against two source trees and
prints them in a fixed, sorted form, so ``diff`` is the whole verdict.

HISTORICAL: this driver compares trees at or before 08622a8. Phase 3e
moved list_packages, setup_virtualenv and _load_last_used to pipeline.py,
so it does not run against a tree after that commit. scripts/differential_3e.py
supersedes it.

How to run it, and against what base::

    git archive 313e800 src/veny | tar -x -C /tmp/old-veny
    pixi run python scripts/differential_3d.py /tmp/old-veny > /tmp/old.txt
    pixi run python scripts/differential_3d.py /workspace    > /tmp/new.txt
    diff /tmp/old.txt /tmp/new.txt

``313e800`` is the phase-3d branch point ("docs: record 3c's merge to main and
the whole-branch review's findings"), NOT ``dc1c3c4`` -- that was 3c's. The
argument is a *tree root* holding ``src/veny``; it is inserted with
``sys.path.insert``, never through ``PYTHONPATH``, because ``pixi.toml``'s
``[activation.env]`` sets ``PYTHONPATH = "src"`` and would silently overwrite
it, testing the live source twice. The first line of output is
``veny.cli.__file__``, so the captured evidence itself shows which tree ran.

This is a script, not a test. It is deliberately NOT wired into pytest: it
compares two trees, only one of which exists inside any given checkout.

Three layers are captured:

1. **Classification state** over a nine-script corpus, written to a throwaway
   directory: every field ``list_packages`` leaves on ``Options``.
2. **The argv handed to uv**, captured at the ``subprocess`` boundary, plus the
   ``requirements.txt`` those commands are pointed at, plus what
   ``environment.install_into_venv`` *returned* under three subprocess
   outcomes -- one of which is ``returncode=0``. 3c's driver always returned 1
   and discarded the value, which left that success predicate uncompared.
3. **The cache-search decision**: which folder ``find_match_dir_in_cache``
   returns out of four manifest-bearing candidates (two matching at different
   timestamps, one for the wrong interpreter, one whose manifest is missing a
   package), the ordered sequence of ``venv_cache.read_manifest`` /
   ``venv_cache.satisfies`` calls made while deciding, and the final state of
   the four ``args`` flags. Two candidates survive rather than one so that
   which *ranking* function ran (latest / oldest / smallest) is observable in
   the chosen folder.

Layer 3 is *expected* to differ in its call sequence, and only there: task 7
deliberately stopped re-reading and re-matching the winning candidate's
manifest (design ledger item 2). The chosen folder and the final flag state
must still be identical. Layers 1 and 2 must come back empty.

Determinism is enforced rather than hoped for: ``PYTHONHASHSEED=0`` is set
inside this script (re-execing once if the interpreter did not start with it),
``sys.dont_write_bytecode`` is set and every ``__pycache__`` under the tree is
deleted before the first import (a same-size source edit restored within the
same integer second otherwise serves the pre-restore behaviour), ``HOME`` is
redirected to a throwaway directory so ``~/veny`` is neither read nor written,
the alias index is offline with a fixed seed, the standard-library index is a
fixed frozenset rather than a probe of whatever interpreter is running, and
every collection is sorted before it is printed.

What this driver still cannot see is recorded in the task report; it is not a
clean bill of health for the whole uv path.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_HASH_SEED_MARKER = "VENY_DIFFERENTIAL_REEXEC"


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
        split:        True when this tree has ``veny.cache_search`` -- that is,
                      when it is a post-3d tree.
        cli:          ``veny.cli``.
        alias_index:  ``veny.alias_index``.
        environment:  ``veny.environment``.
        stdlib_index: ``veny.stdlib_index``.
        venv_cache:   ``veny.venv_cache``.
        verify:       ``veny.verify`` on a split tree, else ``veny.cli``.
        cache_search: ``veny.cache_search`` on a split tree, else ``veny.cli``.
    """

    def __init__(self) -> None:
        """Import the modules this tree has, and record which shape it is."""
        self.split: bool = importlib.util.find_spec("veny.cache_search") is not None
        self.cli: Any = importlib.import_module("veny.cli")
        self.alias_index: Any = importlib.import_module("veny.alias_index")
        self.environment: Any = importlib.import_module("veny.environment")
        self.stdlib_index: Any = importlib.import_module("veny.stdlib_index")
        self.venv_cache: Any = importlib.import_module("veny.venv_cache")
        self.verify: Any = (
            importlib.import_module("veny.verify") if self.split else self.cli
        )
        self.cache_search: Any = (
            importlib.import_module("veny.cache_search") if self.split else self.cli
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
# What the throwaway probe venv reports as already importable.
IMPORTABLE_IN_PROBE = frozenset({"requests", "yaml"})

CORPUS: dict[str, str] = {
    "01_stdlib_only.py": "import os\nimport sys\nprint(os.getcwd(), sys.platform)\n",
    "02_third_party.py": "import yaml\nprint(yaml.safe_load('a: 1'))\n",
    "03_dotted.py": "import xml.etree.ElementTree\nimport os.path\nprint(os.path.sep)\n",
    "04_from_import.py": "from requests import get\nfrom json import loads\nprint(get, loads)\n",
    "05_aliased.py": "import numpy as np\nimport yaml as y\nprint(np, y)\n",
    "06_python2_only.py": "import httplib\nimport urllib2\nprint(httplib, urllib2)\n",
    "07_samedir_sibling.py": "import sibling\nimport yaml\nprint(sibling, yaml)\n",
    "08_subpackage.py": "import subpkg.inner\nimport requests\nprint(subpkg.inner, requests)\n",
    "09_guarded_and_syspath.py": (
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.append(str(Path('/opt/libs') / 'extra'))\n"
        "try:\n"
        "    import cv2\n"
        "except ImportError:\n"
        "    cv2 = None\n"
        "import xarray\n"
        "print(cv2, xarray)\n"
    ),
}


def write_corpus(root: Path) -> list[Path]:
    """Write the nine-script corpus, plus the sibling and subpackage it imports.

    Args:
        root: An empty directory to write into.

    Returns:
        The corpus scripts, in name order.
    """
    (root / "sibling.py").write_text("VALUE = 1\n")
    subpkg = root / "subpkg"
    subpkg.mkdir()
    (subpkg / "__init__.py").write_text("")
    (subpkg / "inner.py").write_text("INNER = 2\n")
    scripts = []
    for name in sorted(CORPUS):
        path = root / name
        path.write_text(CORPUS[name])
        scripts.append(path)
    return scripts


class FakeSubprocess:
    """Stands in for the ``subprocess`` module at veny's only two entry points.

    Every command veny would run is recorded rather than executed. A command
    whose last argument is a Python snippet (``-c``) is answered with the JSON
    an interpreter probe expects; anything else is a uv invocation, answered
    with whatever return code the current policy says.

    Attributes:
        commands: Every command recorded, in call order.
        returncode: What the next uv command reports.
        raise_oserror: When True, the next uv command raises OSError instead.
    """

    def __init__(self) -> None:
        """Start with nothing recorded and a successful uv."""
        self.commands: list[list[str]] = []
        self.returncode: int = 0
        self.raise_oserror: bool = False

    def run(self, command: Any, *args: Any, **kwargs: Any) -> Any:
        """Record a command and answer it without running anything.

        Args:
            command: The argv list veny built.
            *args:   Ignored; present because callers pass positionally.
            **kwargs: Ignored; present because callers pass keywords.

        Returns:
            A CompletedProcess-shaped object.

        Raises:
            OSError: When the current policy says the command cannot run.
        """
        argv = [str(part) for part in command]
        self.commands.append(argv)
        if "-c" in argv:
            payload = json.dumps({"python": [3, 12], "versions": {}})
            return SimpleNamespace(args=argv, returncode=0, stdout=payload, stderr="")
        if self.raise_oserror:
            raise OSError("differential: uv cannot be executed")
        return SimpleNamespace(
            args=argv, returncode=self.returncode, stdout="", stderr=""
        )

    def check_call(self, command: Any, *args: Any, **kwargs: Any) -> int:
        """Record a command that veny expects to raise on failure.

        Args:
            command: The argv list veny built.
            *args:   Ignored.
            **kwargs: Ignored.

        Returns:
            Zero, always: the differential never simulates a failed build here.
        """
        self.commands.append([str(part) for part in command])
        return 0


def install_fakes(tree: Tree, fake: FakeSubprocess) -> None:
    """Replace every boundary that would touch a real interpreter or network.

    The import-level check is replaced rather than driven, because its subject
    is a real venv this driver never builds; the differential's subject is the
    wiring around it. The interpreter probe is pinned to a fixed answer for the
    same reason. Both are patched at whichever module the tree keeps them in.

    Args:
        tree: The loaded tree.
        fake: The subprocess stand-in to install.
    """
    subprocess.run = fake.run  # type: ignore[assignment]
    subprocess.check_call = fake.check_call  # type: ignore[assignment]
    tree.alias_index.probe_interpreter = lambda python, timeout=30.0: ("3.12", {})

    if tree.split:

        def check_new(
            venv_python: Any,
            *,
            record: Any = None,
            uninstalled: Any = frozenset(),
            source_names: Any = frozenset(),
        ) -> bool:
            """Answer one record from a fixed set; answer the bulk branch yes."""
            if record is not None:
                return bool(record.import_name in IMPORTABLE_IN_PROBE)
            return True

        tree.verify.check_packages_in_venv = check_new
    else:

        def check_old(
            options: Any,
            record: Any = None,
            venv_dir: Any = None,
            source_names: Any = None,
        ) -> bool:
            """The same answer, through the pre-3d signature."""
            if record is not None:
                return bool(record.import_name in IMPORTABLE_IN_PROBE)
            return True

        tree.cli.check_packages_in_venv = check_old


def an_options(tree: Tree, my_dir: Path) -> Any:
    """Build an Options with every machine-dependent field pinned.

    Args:
        tree:   The loaded tree.
        my_dir: The throwaway directory standing in for ``~/veny``.

    Returns:
        A fresh Options object.
    """
    options = tree.cli.Options()
    options.my_dir = my_dir
    options.python_command = ""
    options.rawlog = True
    options.timestamp = "20260101-010101"
    options.venv_name = "myenv"
    options.custom_modules = {}
    options.stdlib = tree.stdlib_index.StdlibIndex(
        names=STDLIB_NAMES, python_version=(3, 12), source="differential"
    )
    options.aliases = tree.alias_index.AliasIndex(
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
    options.args = SimpleNamespace(
        full=False,
        reqs=False,
        no_cache=False,
        rc=False,
        latest=False,
        oldest=False,
        last_used=False,
        smallest=False,
    )
    return options


def sorted_records(records: Any) -> list[str]:
    """Render a set of ResolvedImport records as sorted ``import -> pip`` lines.

    Args:
        records: Any iterable of records.

    Returns:
        The rendered lines, sorted.
    """
    return sorted(f"{r.import_name} -> {r.pip_name}" for r in records)


# ---------------------------------------------------------------------------
# Layer 1: classification state
# ---------------------------------------------------------------------------


def layer_one(tree: Tree, workdir: Path) -> None:
    """Print the classification state for every script in the corpus.

    ``options.installed_imports`` is deliberately not printed: it was a
    write-only field with no reader anywhere, deleted by task 8, so it is not
    classification state that anything consumes. Every other field
    ``list_packages`` leaves behind is printed, and a field missing from one
    tree prints as ``<absent>`` rather than being skipped.

    Args:
        tree:    The loaded tree.
        workdir: A scratch directory this run owns.
    """
    print("=== LAYER 1: classification state ===")
    corpus_dir = workdir / "corpus"
    corpus_dir.mkdir()
    scripts = write_corpus(corpus_dir)
    fields = (
        "all_imports",
        "bad_imports",
        "seen_stdlib_imports",
        "loaded_custom_modules",
        "subfolders",
    )
    for script in scripts:
        options = an_options(tree, workdir / "my_dir")
        options.python_script = script
        options.script_dir = script.parent
        tree.cli.list_packages(options)
        print(f"--- {script.name} ---")
        print(f"  total_imports: {options.total_imports}")
        print(f"  uninstalled: {sorted_records(options.uninstalled_imports)}")
        for field in fields:
            if not hasattr(options, field):
                print(f"  {field}: <absent>")
                continue
            print(f"  {field}: {sorted(str(v) for v in getattr(options, field))}")
        print(f"  samedir_files: {sorted(p.name for p in options.samedir_files)}")
        print(
            "  sys_path_hints: "
            f"{sorted(str(p) for p in getattr(options, 'sys_path_hints', ()))}"
        )


# ---------------------------------------------------------------------------
# Layer 2: the argv handed to uv, and install_into_venv's own answer
# ---------------------------------------------------------------------------


def layer_two(tree: Tree, workdir: Path, fake: FakeSubprocess) -> None:
    """Print the whole uv boundary of one build, and install_into_venv's answer.

    Captured: every uv command the build issues, the requirements.txt those
    commands are pointed at, and what ``environment.install_into_venv``
    returned under three different subprocess outcomes.

    Args:
        tree:    The loaded tree.
        workdir: A scratch directory this run owns.
        fake:    The installed subprocess stand-in.
    """
    print("=== LAYER 2: the argv handed to uv ===")
    my_dir = workdir / "uv_my_dir"
    my_dir.mkdir()
    options = an_options(tree, my_dir)
    options.uninstalled_imports = {
        tree.alias_index.ResolvedImport(import_name="yaml", pip_name="PyYAML"),
        tree.alias_index.ResolvedImport(import_name="np", pip_name="numpy"),
        tree.alias_index.ResolvedImport(
            import_name="ruamel.yaml", pip_name="ruamel-yaml"
        ),
    }
    options.all_imports = {"yaml", "np", "ruamel.yaml"}
    options.extra_requirements = {"numpy": ">=1.26", "extra-pkg": None}
    fake.commands.clear()
    fake.returncode = 0
    built = tree.cli.setup_virtualenv(options)
    print(f"  setup_virtualenv returned: {built}")
    print(f"  install_succeeded: {options.install_succeeded}")
    for command in fake.commands:
        # The venv directory carries this run's own temporary path, which
        # differs between the two runs by construction; replace it with a
        # stable token so only the *shape* of the command is compared.
        rendered = [part.replace(str(workdir), "<workdir>") for part in command]
        print(f"  argv: {rendered}")
    requirements = options.requirements_file
    if requirements is not None and Path(requirements).is_file():
        print(f"  requirements.txt: {Path(requirements).read_text().splitlines()}")
    else:
        print("  requirements.txt: <not written>")

    print("  -- install_into_venv's own answer --")
    venv_python = my_dir / "probe" / "bin" / "python"
    for label, returncode, raises in (
        ("returncode=0", 0, False),
        ("returncode=1", 1, False),
        ("raises OSError", 0, True),
    ):
        fake.commands.clear()
        fake.returncode = returncode
        fake.raise_oserror = raises
        answer = tree.environment.install_into_venv(venv_python, "some-pkg")
        fake.raise_oserror = False
        rendered_commands = [
            [part.replace(str(workdir), "<workdir>") for part in command]
            for command in fake.commands
        ]
        print(f"  {label}: returned {answer!r}; argv {rendered_commands}")
    fake.returncode = 0


# ---------------------------------------------------------------------------
# Layer 3: the cache-search decision
# ---------------------------------------------------------------------------


def build_fake_cache(tree: Tree, my_dir: Path) -> None:
    """Write four manifest-bearing venv folders into a throwaway cache.

    Two match this run outright, at different timestamps; one is for another
    interpreter; one carries a manifest missing a package its folder name
    advertises, so it survives the cheap name filter and is rejected only once
    its manifest is read.

    The second *surviving* folder is what makes the ranking functions
    observable. With a single survivor, latest_venv, oldest_venv and
    smallest_venv all return the same folder, and swapping one for another is a
    change this capture cannot see -- measured: a latest_venv -> oldest_venv
    mutation left the diff unmoved. With two, the chosen folder names which
    ranking ran.

    Args:
        tree:   The loaded tree.
        my_dir: The throwaway directory standing in for ``~/veny``.
    """

    def a_folder(tag: str, timestamp: str, packages: list[Any]) -> None:
        """Write one cached venv folder with the manifest it advertises."""
        name = tree.venv_cache.build_folder_name(
            venv_name="myenv",
            interpreter_tag=tag,
            timestamp=timestamp,
            pip_names=["thing-pkg"],
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

    record = tree.venv_cache.PackageRecord
    thing = [record("thing", "thing-pkg", "2.5.0", None)]
    # Two survivors, so latest != oldest and the ranking function is visible.
    a_folder("3.12", "20260101-040404", thing)
    a_folder("3.12", "20260101-030303", thing)
    a_folder("3.11", "20260101-020202", thing)
    a_folder("3.12", "20260101-010101", [record("other", "other-pkg", "1.0.0", None)])


def layer_three(tree: Tree, workdir: Path) -> None:
    """Print which cached venv is chosen, how it was decided, and the flag state.

    Args:
        tree:    The loaded tree.
        workdir: A scratch directory this run owns.
    """
    print("=== LAYER 3: the cache-search decision ===")
    my_dir = workdir / "cache_my_dir"
    my_dir.mkdir()
    script_dir = workdir / "cache_script_dir"
    script_dir.mkdir()
    script = script_dir / "thing.py"
    script.write_text("import thing\n")
    build_fake_cache(tree, my_dir)

    options = an_options(tree, my_dir)
    options.python_script = script
    options.script_dir = script_dir
    options.uninstalled_imports = {
        tree.alias_index.ResolvedImport(import_name="thing", pip_name="thing-pkg")
    }
    options.all_imports = {"thing"}
    options.extra_requirements = {"thing-pkg": ">=2.0"}

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
    try:
        chosen = find_match(tree, options)
    finally:
        tree.venv_cache.read_manifest = real_read
        tree.venv_cache.satisfies = real_satisfies

    print(f"  chosen folder: {Path(chosen).name if chosen is not None else None}")
    print("  call sequence:")
    for entry in sequence:
        print(f"    {entry}")
    for flag in ("latest", "oldest", "last_used", "smallest"):
        print(f"  args.{flag}: {getattr(options.args, flag, '<absent>')}")


def find_match(tree: Tree, options: Any) -> Any:
    """Run the cache search through whichever signature this tree has.

    Args:
        tree:    The loaded tree.
        options: The run to search for.

    Returns:
        The chosen venv directory, or None.
    """
    if not tree.split:
        return tree.cli.find_match_dir_in_cache(options)
    return tree.cache_search.find_match_dir_in_cache(
        options.args,
        my_dir=options.my_dir,
        venv_name=options.venv_name,
        uninstalled=options.uninstalled_imports,
        extra_requirements=options.extra_requirements,
        source_names=tree.verify.source_import_names(
            options.all_imports,
            options.extra_requirements,
            getattr(options.args, "reqs", False),
        ),
        tag=tree.cache_search.interpreter_tag(options.stdlib),
        rawlog=options.rawlog,
        load_last_used=lambda: tree.cli._load_last_used(options),
    )


def main() -> int:
    """Capture all three layers against the tree named on the command line.

    Returns:
        Zero on success; 2 when the tree root is missing or unusable.
    """
    if len(sys.argv) < 2:
        print("usage: differential_3d.py <tree-root>")
        return 2
    root = Path(sys.argv[1]).resolve()
    package = root / "src" / "veny"
    if not package.is_dir():
        print(f"no src/veny under {root}")
        return 2

    # veny logs paths that carry this run's own temporary directory, and
    # logging.exception writes tracebacks naming this file. None of it is the
    # subject of the comparison, and all of it would differ between two runs.
    logging.disable(logging.CRITICAL)

    sys.dont_write_bytecode = True
    purged = purge_pycache(root / "src")
    sys.path.insert(0, str(root / "src"))

    with tempfile.TemporaryDirectory(prefix="veny-differential-") as scratch:
        workdir = Path(scratch)
        # Before the first veny import: Options() reads Path.home() at
        # construction, and ~/veny must be neither read nor written.
        os.environ["HOME"] = str(workdir / "home")
        (workdir / "home").mkdir()
        tree = Tree()
        print(f"veny.cli.__file__: {tree.cli.__file__}")
        print(f"tree shape: {'split (3d)' if tree.split else 'monolithic (pre-3d)'}")
        # Diagnostics, not observations: the purge count depends on whether
        # this tree happened to have been imported recently, so on stdout it
        # would put a spurious third hunk in the documented diff. They go to
        # stderr, where they are still captured next to the run.
        print(f"PYTHONHASHSEED: {os.environ.get('PYTHONHASHSEED')}", file=sys.stderr)
        print(f"__pycache__ directories purged: {purged}", file=sys.stderr)
        fake = FakeSubprocess()
        install_fakes(tree, fake)
        layer_one(tree, workdir)
        layer_two(tree, workdir, fake)
        layer_three(tree, workdir)
    return 0


if __name__ == "__main__":
    reexec_with_fixed_hash_seed()
    sys.exit(main())
