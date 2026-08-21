"""The per-run state object, on its way out.

`Options` is the 48-attribute god object the re-architecture retires. It lives
here rather than in `cli.py` for one reason: `pipeline.py` is handed one, and a
module may not import the module above it. Phase 4 deletes this file when the
frozen `Settings`, `Target`, `VenvHandle` and `LastUsed` dataclasses replace it;
nothing new should be added here in the meantime.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import emmykit as ek

from . import alias_index, stdlib_index


class Options(ek.Options):
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        super().__init__()  # Call the parent class's __init__ method from emmykit
        self.log_mode: int = logging.INFO  # Use --debug to change to logging.DEBUG.
        self.search_above_this_dir: bool = True
        self.my_name: str = "veny"  # Fixed: the installed command's name, not whatever argv[0] happens to be.
        self.home: Path = Path.home()  # User's home directory
        # The "my_dir" is NOT the directory where this script is located.
        # Instead, it's the directory where this script will store its virtual environments and packages.
        self.my_dir: Path = self.home / self.my_name
        self.cwd: Path = Path.cwd().expanduser().resolve(strict=True)
        self.venv_name: str = "myenv"  # Can NOT include dashes ("-")
        # Both sets hold ResolvedImport records, so every consumer can pick the
        # right name instead of guessing which kind of string it was handed.
        self.uninstalled_imports: set[alias_index.ResolvedImport] = set()
        self.bad_imports: set[str] = set()
        self.all_imports: set[str] = set()
        self.total_imports: int = 0
        self.custom_modules: dict[
            str, Path
        ] = {}  # Maps custom module names to their file Paths
        self.subfolders: list[str] = []
        self.samedir_files: list[Path] = []
        self.loaded_custom_modules: set[str] = set()
        self.sys_path_hints: set[Path] = set()  # Filled by SysPathVisitor
        # The three fields ek.save_options_to_json builds its filename from,
        # alongside my_name. Target owns them for the run; pipeline.run copies
        # them across just before the save, because emmykit's writer is typed
        # against ek.Options rather than against a payload. Phase 4b drops the
        # coupling -- veny writes its own LastUsed record -- and these go with
        # it. Nothing else may read them.
        self.python_script: Path | None = None
        self.script_dir: Path | None = None
        self.timestamp: str = ""
        self.options_json_filepath: Path | None = None
        # Before 2025-08-10 at 22:49:00, paths were stored as strings. After that date, they were stored as pathlib.Path objects. Any .pkl files created before that date have their paths converted to pathlib.Path objects when loaded. Any .json files created before that date are ignored when loading last-used options.
        self.pathlibcutoff: str = "20250810-224900"
        self.current_pip_version: str = ""
        self.new_pip_version: str = ""
        self.venv_dir: Path | None = None
        self.venv_python: Path | None = None
        self.requirements_file: Path | None = None
        self.extra_requirements: dict[str, str | None] = {}
        self.extra_requirements_file: str = "extra_requirements.txt"
        self.install_succeeded: bool = False
        self.max_checks: int = (
            10  # Maximum number of times to check any repeated process.
        )
        self.check_interval: int = 5  # Number of seconds to wait between checks.
        self.rawlog: bool = False
        # Some imports also need other packages to be installed. Both the keys and
        # the values are *import* names: they are matched against and resolved
        # through options.aliases, which turns e.g. "netCDF4" into pip's "netcdf4".
        self.also_needs: dict[str, list[str]] = {
            "xarray": ["dask", "netCDF4", "h5netcdf"],
            "litellm": ["tenacity"],
            # NOT PIP PACKAGES: "pyautogui": ["scrot", "python3-tk"]
            # Add more packages and their dependencies here
        }
        # Standard-library membership is derived from a real interpreter, never hardcoded.
        # Replaced in run() once the target's python_command is known, so that truth comes from
        # the interpreter that will actually run the user's script. See
        # docs/superpowers/specs/2026-08-12-stdlib-index-design.md
        self.stdlib: stdlib_index.StdlibIndex = stdlib_index.for_running_interpreter()
        self.seen_stdlib_imports: set[str] = (
            set()
        )  # Standard-library imports that were skipped
        # Import-name-to-pip-name resolution. Replaced in main() once
        # the target's python_command is known, so the resolver probes the
        # interpreter that will actually run the user's script. empty()
        # rather than build() here: Options() is constructed before
        # python_command is known and in every test, and build() spawns a
        # probe subprocess. See
        # docs/superpowers/specs/2026-08-12-module-alias-resolver-design.md
        self.aliases: alias_index.AliasIndex = alias_index.empty(self.my_dir)
        # Project-specific module names that are not on PyPI and never will be. Python 2
        # names and system-package cases now live in stdlib_index.py instead.
        self.known_bad_imports: set[str] = {
            "snakeClass",
            "GPUampcor",
            "pathfinding_salvo_rework",
            "DQN",
            "bayesOpt",
            "non_existent_module",
        }
        # List of unusual imports that are not standard library modules or packages.
        self.unusual_imports: list[str] = [
            "a",
            "an",
            "dl",
            "the",
            "it",
            "x",
            "xx",
            "above",
            "another",
            "__builtin__",
            "within",
        ]
        # List of directories to stay out of when searching for local custom imports because they're filled with standard library modules or other irrelevant files.
        self.stay_out_list: list[str] = [
            "myenv",
            ".venv",
            "anaconda3",
            "miniconda3",
            "miniforge3",
            ".conda",
            os.sep + "lib" + os.sep,
            ".vscode",
        ]

    def set_venv_dir(self, venv_dir: str | os.PathLike[str]) -> None:
        """Set the directory for the virtual environment."""
        p = ek.ensure_path(venv_dir)
        self.venv_dir = p
        self.venv_python = p / "bin" / "python"  # Do NOT resolve() this symlink path
        self.requirements_file = p / "requirements.txt"
        p.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist
