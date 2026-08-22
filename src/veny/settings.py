"""The invariants of one veny run, fixed once and never mutated."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

# Some imports also need other packages to be installed. Both the keys and the
# values are *import* names: they are matched against and resolved through the
# alias index, which turns e.g. "netCDF4" into pip's "netcdf4".
DEFAULT_ALSO_NEEDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "xarray": ("dask", "netCDF4", "h5netcdf"),
        "litellm": ("tenacity",),
        # NOT PIP PACKAGES: "pyautogui": ["scrot", "python3-tk"]
        # Add more packages and their dependencies here
    }
)

# Project-specific module names that are not on PyPI and never will be. Python 2
# names and system-package cases live in stdlib_index.py instead.
DEFAULT_KNOWN_BAD_IMPORTS: frozenset[str] = frozenset(
    {
        "snakeClass",
        "GPUampcor",
        "pathfinding_salvo_rework",
        "DQN",
        "bayesOpt",
        "non_existent_module",
    }
)

# Directories to stay out of when searching for local custom imports, because
# they are filled with standard library modules or other irrelevant files.
DEFAULT_STAY_OUT_LIST: tuple[str, ...] = (
    "myenv",
    ".venv",
    "anaconda3",
    "miniconda3",
    "miniforge3",
    ".conda",
    os.sep + "lib" + os.sep,
    ".vscode",
)


@dataclass(frozen=True)
class Settings:
    """Run invariants that no stage may change.

    Constructed exactly once, in cli.main, and handed down. Every collection
    field is an immutable type on purpose: freezing a dataclass freezes the
    bindings, not the objects behind them, and a stage that could .append to
    stay_out_list would silently change what every later stage searches.

    Three attributes the design rehomed here turned out to have no readers at
    all and were deleted instead (design amendment, 2026-08-21):
    `unusual_imports`, `max_checks` and `check_interval`. Two more are absent
    for a different reason: `home` exists only to derive `my_dir`, so it stays
    a construction detail in cli.py, and `log_mode` is read once, in cli.main,
    where it stays a local.

    Attributes:
        my_name:                 The installed command's name, "veny". Fixed,
                                 not whatever argv[0] happens to be.
        my_dir:                  Where veny keeps its cached environments.
        cwd:                     The directory veny was invoked from.
        venv_name:               The prefix every cached venv folder is built
                                 from. Must NOT contain a dash.
        stay_out_list:           Path fragments never searched for local modules.
        search_above_this_dir:   Whether to search above cwd for local modules.
        rawlog:                  Suppress veny's own commentary.
        known_bad_imports:       Names that must never be handed to pip.
        also_needs:              Import name to the further import names that
                                 installing it also requires.
        extra_requirements_file: The file --reqs reads, relative to cwd.
    """

    my_name: str
    my_dir: Path
    cwd: Path
    venv_name: str
    stay_out_list: tuple[str, ...]
    search_above_this_dir: bool
    rawlog: bool
    known_bad_imports: frozenset[str]
    also_needs: Mapping[str, tuple[str, ...]]
    extra_requirements_file: str
