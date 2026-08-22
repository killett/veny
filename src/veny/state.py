"""The products one veny run's stages hand to the next."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import emmykit as ek

from .alias_index import ResolvedImport


@dataclass(frozen=True)
class Target:
    """What this run is being asked to run.

    Frozen because the target is decided once, at the argparse boundary, and
    only read after that. `python_command` is the one field discovered later:
    `pipeline.run` rebinds the whole value with dataclasses.replace once
    ek.find_preferred_python_version() has answered, rather than leaving a
    mutable hole in an otherwise fixed value.

    script_args is a tuple rather than a list so that the run's own copy of
    the user's arguments cannot be appended to by a later stage. The launch
    paths call list(...) on it at the subprocess boundary.

    Attributes:
        python_script:  The script itself, resolved strictly.
        script_dir:     Its parent -- the directory later stages search for
                        custom modules and last-used records.
        script_args:    Everything after the script on veny's command line.
        python_command: The interpreter veny will build the venv against;
                        "" until `run` resolves it.
        timestamp:      The run's stamp, in the YYYYmmdd-HHMMSS format
                        venv_cache builds and parses cached folder names with.
    """

    python_script: Path
    script_dir: Path
    script_args: tuple[str, ...]
    python_command: str
    timestamp: str


@dataclass(frozen=True)
class Requirements:
    """What classification decided about one run's imports.

    Frozen because it is a product, not a workspace: classification computes
    it once and every later stage only reads it.

    `seen_stdlib` and `extra_requirements` are pass-throughs, not products.
    Classification neither computes nor changes them -- the first is copied
    off the scan and the second is the caller's own input -- and they travel
    here only because later stages (the manifest writer, the reporting block)
    need them alongside the classification itself.

    Attributes:
        all_imports:        Import names left to account for, after the bad
                            ones are subtracted and any --reqs names folded in.
        bad:                Names that must never be handed to pip.
        installed:          Records for imports the probe environment already
                            satisfies.
        uninstalled:        Records for imports that must be installed,
                            dependencies included.
        seen_stdlib:        Standard-library names the scan skipped
                            (pass-through, for reporting).
        extra_requirements: The --reqs file's entries, name to version
                            specifier (pass-through, for the manifest).
    """

    all_imports: frozenset[str]
    bad: frozenset[str]
    installed: frozenset[ResolvedImport]
    uninstalled: frozenset[ResolvedImport]
    seen_stdlib: frozenset[str]
    extra_requirements: Mapping[str, str | None]

    @property
    def total_imports(self) -> int:
        """The number of imports classification had to account for.

        Returns:
            The size of all_imports, which is what the progress display
            counts towards.
        """
        return len(self.all_imports)


@dataclass(frozen=True)
class VenvHandle:
    """One virtual environment, and the two paths derived wholly from it.

    Frozen because the three paths must move together: repointing venv_dir
    after a rename while venv_python still names the old directory is exactly
    the drift the old set_venv_dir's three coupled writes existed to prevent.
    A rename produces a new handle via for_dir, never an edit to this one.

    Attributes:
        venv_dir:          The environment's directory.
        venv_python:       Its interpreter. NOT resolved -- see for_dir.
        requirements_file: The requirements.txt written inside it.
    """

    venv_dir: Path
    venv_python: Path
    requirements_file: Path

    @classmethod
    def for_dir(cls, venv_dir: str | os.PathLike[str]) -> VenvHandle:
        """Derive a handle from a venv directory, creating the directory.

        The mkdir is not incidental: `uv venv` needs the directory to exist
        and be empty, which is also why nothing may write into it until
        environment.create_venv has succeeded against it.

        Args:
            venv_dir: Where the environment lives, or will.

        Returns:
            The handle for that directory.
        """
        p = ek.ensure_path(venv_dir)
        p.mkdir(parents=True, exist_ok=True)
        return cls(
            venv_dir=p,
            # Do NOT resolve() this symlink path: in a real venv it points at
            # the base interpreter, and a resolved path would run the system
            # python with none of the venv's packages.
            venv_python=p / "bin" / "python",
            requirements_file=p / "requirements.txt",
        )


@dataclass(frozen=True)
class LastUsed:
    """The one thing veny remembers between runs.

    Frozen, like every other product in this module: it is written once at
    the end of a successful run and only read on the next one.

    Phase 4b wrote this record itself rather than persisting emmykit's
    generic options bag, which is what coupled veny's per-run state to
    emmykit's reader and writer.
    The design's state-model listing puts LastUsed in settings.py; it lives
    here with its siblings instead, because settings.py holds the run's
    invariants and this is a product.

    Attributes:
        venv_dir:    The environment the last successful run used.
        venv_python: That environment's interpreter -- recorded rather than
                     derived, so a reader need not know how a venv is laid
                     out on this platform.
        timestamp:   The run's stamp, in the same "YYYYmmdd-HHMMSS" format
                     Target carries. Diagnostic: nothing selects on it now
                     that there is one record per script rather than one per
                     run.
    """

    venv_dir: Path
    venv_python: Path
    timestamp: str
