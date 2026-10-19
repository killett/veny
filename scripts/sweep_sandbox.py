"""A throwaway copy of the tree for the wiring sweeps to mutate.

The sweeps substitute a wrong value for one argument at a time and run the
suite to see whether anything notices. Doing that to the repository's own
files is safe only for as long as the sweep lives to restore them: a run
killed mid-sweep (SIGKILL, a dead session) leaves the mutation in the working
tree, where the suite stays green by construction for every OPEN HOLE and the
next commit carries it. A copy has no such failure mode.
"""

import atexit
import shutil
import tempfile
from pathlib import Path

# Everything a test run reads: the package, the suite, the pytest
# configuration that puts src/ on the path, and scripts/ -- the suite
# tests the sweeps themselves. A copy missing any of them fails tests
# unrelated to the mutation, and every such failure would be scored as a
# kill.
COPIED: tuple[str, ...] = ("src", "tests", "scripts", "pyproject.toml")


def sandbox(repo: Path) -> Path:
    """Copy what a test run needs from repo into a fresh temporary directory.

    The copy is removed when the interpreter exits. A sweep killed before
    then leaves it in the temporary directory, never in the repository.

    Args:
        repo: The repository root to copy from.

    Returns:
        The copy's root, laid out like repo for the copied entries.
    """
    root = Path(tempfile.mkdtemp(prefix="wiring-sweep-"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    for name in COPIED:
        source = repo / name
        if source.is_dir():
            shutil.copytree(
                source, root / name, ignore=shutil.ignore_patterns("__pycache__")
            )
        else:
            shutil.copy2(source, root / name)
    return root
