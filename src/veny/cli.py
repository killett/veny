#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), ChatGPT 5 Thinking (it/its), and GitHub Copilot (it/its).
from __future__ import (
    annotations,
)  # For Python 3.7+ compatibility with type annotations

import argparse
import contextlib
import datetime as dt
import json
import logging
import os
import re
import shlex  # For safely quoting shell commands
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path  # Preferred over os.path for path manipulations.

from . import __version__ as __version__
from . import alias_index, stdlib_index
from .settings import Settings

try:
    import emmykit as ek
except ImportError as exc:  # stdlib only: none of emmykit's helpers exist yet.
    raise SystemExit(
        "veny requires the emmykit package (>=0.4.0), which is not installed.\n"
        "Install it with:  pip install 'emmykit>=0.4.0'"
    ) from exc
if not hasattr(ek, "register_json_type"):
    raise SystemExit(
        f"veny requires emmykit >= 0.4.0; found {getattr(ek, '__version__', 'unknown')}.\n"
        f"Upgrade it with:  pip install -U 'emmykit>=0.4.0'"
    )
from . import classify, environment, json_types, last_used, venv_cache, verify
from .analysis import scan as analysis_scan
from .analysis.custom_modules import dict_of_custom_modules
from .analysis.scan_state import ImportScan

# An import name paired with the pip package that provides it. Defined in
# alias_index, which imports nothing of veny's, and re-exported here because
# veny is where it is used. Its JSON handlers live in json_types.
ResolvedImport = alias_index.ResolvedImport

# Registers veny's own types with emmykit's JSON registry. At module scope, not
# inside main(), so that anything importing veny -- including every test -- gets
# the same serialization behaviour production does. The call is idempotent.
json_types.register_types()


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
        self.python_command: str = ""
        self.cwd: Path = Path.cwd().expanduser().resolve(strict=True)
        self.venv_name: str = "myenv"  # Can NOT include dashes ("-")
        # Both sets hold ResolvedImport records, so every consumer can pick the
        # right name instead of guessing which kind of string it was handed.
        self.uninstalled_imports: set[alias_index.ResolvedImport] = set()
        self.installed_imports: set[alias_index.ResolvedImport] = set()
        self.bad_imports: set[str] = set()
        self.all_imports: set[str] = set()
        self.total_imports: int = 0
        self.custom_modules: dict[
            str, Path
        ] = {}  # Maps custom module names to their file Paths
        self.subfolders: list[str] = []
        self.samedir_files: list[Path] = []
        self.loaded_custom_modules: set[str] = set()
        self.timestamp: str = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.sys_path_hints: set[Path] = set()  # Filled by SysPathVisitor
        self.python_script: Path | None = None
        self.script_name: str = ""  # python_script without the .py extension
        self.script_dir: Path | None = None
        self.script_args: list[str] = []
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
        # Replaced in main() once options.python_command is known, so that truth comes from
        # the interpreter that will actually run the user's script. See
        # docs/superpowers/specs/2026-08-12-stdlib-index-design.md
        self.stdlib: stdlib_index.StdlibIndex = stdlib_index.for_running_interpreter()
        self.seen_stdlib_imports: set[str] = (
            set()
        )  # Standard-library imports that were skipped
        # Import-name-to-pip-name resolution. Replaced in main() once
        # options.python_command is known, so the resolver probes the
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


def parse_arguments(options: Options) -> None:
    """Parse command-line arguments.

    Args:
        options: Options object to store parsed arguments. Contains:
            - my_name:             Name of the program.
            - log_mode:            Logging mode (default is logging.INFO).
            - args:                Parsed arguments will be stored here.

    Returns:
        None, but updates options.args with parsed arguments.

    Raises:
        SystemExit: If the "-version" flag is provided, the program will print the version and exit.
        ValueError: If any of the arguments are invalid.
    """
    parser = argparse.ArgumentParser(
        prog="veny", description="Run a python script with optional flags."
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--feeling-lucky",
        action="store_true",
        help="NOT FINISHED!!! Don't analyze imports, just try to run the script with the last used virtual environment. If that fails, try the latest virtual environment which has all the packages needed now.",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Run this program in debug mode, which prints additional debug messages.",
    )
    parser.add_argument(
        "--blank-slate",
        action="store_true",
        help=f"Delete ~/{options.my_name}/ and all {options.my_name} .out and .err and .json and .pkl files in the current directory.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Build a virtual environment (venv) that can run every python script in the current directory. Cannot be used with a python script argument.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Automatically say yes to any prompts to allow this program to run without the need for user interaction.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Don't search the cache. Instead, create a new virtual environment. Also, refresh the custom modules cache.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Load the latest cached venv which has all the packages needed now.",
    )
    parser.add_argument(
        "--oldest",
        action="store_true",
        help="Load the oldest cached venv which has all the packages needed now.",
    )
    parser.add_argument(
        "--last-used",
        action="store_true",
        help="Load the last used cached venv, but if that fails try the latest cached venv which has all the packages needed now.",
    )
    parser.add_argument(
        "--smallest",
        action="store_true",
        help="Load the smallest cached venv (with the fewest packages) which has all the packages needed now.",
    )
    parser.add_argument(
        "--rc",
        action="store_true",
        help="Refresh the custom modules cache.",
    )
    parser.add_argument(
        "--reqs",
        action="store_true",
        help="Read the extra_requirements.txt file in the current directory and install the packages listed there (with specific versions if present in the file) into the venv (along with the other packages needed to run the script as determined elsewhere in this program).",
    )
    parser.add_argument(
        "--rawlog",
        action="store_true",
        help=f"Do not add timestamps or INFO level to log messages, and do not add extra INFO level log statements. Just produce the same output that would be seen when running the program without {options.my_name}.",
    )
    parser.add_argument(
        "--justprint",
        action="store_true",
        help="Don't run the script, just print its package requirements.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Never contact PyPI while working out which package provides an import. Import names are resolved from the override file, the cache, the target interpreter's installed packages and the built-in exceptions only.",
    )
    parser.add_argument("script", nargs="?", help="The script to run.")
    parser.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="Optional arguments for the python script.",
    )

    # If no arguments are provided, print a short guide
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    # Otherwise, parse the arguments and store them in options.args for later use.
    options.args = parser.parse_args()

    if getattr(options.args, "debug", False):
        options.log_mode = logging.DEBUG


def build_alias_index(options: Options) -> alias_index.AliasIndex:
    """Rebuild the alias index against the interpreter that will run the user's script.

    Options() seeds it with alias_index.empty(), whose cache is tagged with
    *veny's own* interpreter version; leaving that in place would let a cache
    entry recorded under one Python version short-circuit resolution for a
    target on another.

    Args:
        options: Options object; reads options.python_command, options.my_dir
                 and the --offline flag.

    Returns:
        An index for the target interpreter, offline if the user asked for it.

    Raises:
        AliasOverrideError: If the override file exists but cannot be read.
    """
    return alias_index.build(
        options.python_command,
        options.my_dir,
        offline=getattr(options.args, "offline", False),
    )


def main() -> int:
    """Main function.

    Returns:
        The wrapped script's exit status: 0 when no script was meant to run
        (``--justprint``, ``--full``), and 1 when veny could not run the
        script.
    """
    start_time = dt.datetime.now()
    script_exit_code = 0
    options: Options = Options()
    parse_arguments(options)
    script_string = getattr(options.args, "script", None)
    options.script_args = getattr(options.args, "script_args", [])
    options.rawlog = getattr(options.args, "rawlog", False)
    if script_string is None:
        options.python_script = None
    else:
        options.python_script = ek.ensure_file(
            script_string, raise_on_empty=True
        ).resolve(strict=True)
        options.script_dir = options.python_script.parent.absolute()
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(
                "Directory where the script to run is located: %s",
                os.fspath(options.script_dir),
            )

    if getattr(options.args, "feeling_lucky", False) and options.python_script:
        assert options.script_dir is not None, "options.script_dir must be set"
        last_used_venv_python = last_used.load_last_used_venv_python(
            options,
            script_dir=options.script_dir,
            python_script=options.python_script,
            pathlibcutoff=options.pathlibcutoff,
            rawlog=options.rawlog,
        )
        if last_used_venv_python:
            command_list = [
                os.fspath(last_used_venv_python),
                os.fspath(options.python_script),
            ] + options.script_args
            result = subprocess.run(command_list)
            if result.returncode != 0 and not options.rawlog:
                print(f"Script exited with status {result.returncode}")
            sys.exit(result.returncode)
        else:
            if not options.rawlog:
                print(
                    "No luck: no last used virtual environment found. Running the script as normal."
                )

    memory_handler = ek.configure_logging(
        options.my_name, log_level=options.log_mode, rawlog=options.rawlog
    )

    options.python_command = ek.find_preferred_python_version()
    if options.python_command:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(
                "Python %s is available at: %s", ek.PY_VERSION, options.python_command
            )
    else:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Python %s is not available.", ek.PY_VERSION)
    options.stdlib = stdlib_index.resolve(options.python_command)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Standard library index: %d names from Python %d.%d (source: %s)",
            len(options.stdlib.names),
            options.stdlib.python_version[0],
            options.stdlib.python_version[1],
            options.stdlib.source,
        )
    # This must happen before anything resolves, i.e. before list_packages() below.
    options.aliases = build_alias_index(options)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Alias index: %d overrides, %d cached names, tagged %s",
            len(options.aliases.overrides),
            len(options.aliases.cache.entries),
            options.aliases.cache.interpreter_tag,
        )

    if not ek.safe_is_dir(options.my_dir):
        if not options.rawlog:
            logging.info(
                "Directory %s does not exist yet, so it is being created.",
                options.my_dir,
            )
        options.my_dir.mkdir(parents=True, exist_ok=True)

    if getattr(options.args, "full", False) and options.python_script:
        ek.my_critical_error("Full mode is not supported with a script argument.")
    elif options.python_script:
        pass  # If a script was provided as an argument, skip the rest of these checks.
    elif getattr(options.args, "blank_slate", False):
        if not getattr(options.args, "y", False):
            if not ek.prompt_then_confirm(
                f"Are you sure you want to delete everything in ~/{options.my_name}/"
                f" and all {options.my_name} .json files in the current directory? (y/n) "
            ):
                logging.info("Exiting without deleting anything.")
                sys.exit(0)
        logging.info(
            "Deleting everything in ~/%s/ and all %s .out and .err and .json and .pkl files in the current directory.",
            options.my_name,
            options.my_name,
        )
        shutil.rmtree(options.my_dir, ignore_errors=True)
        for file in options.cwd.iterdir():
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug("Checking %s", file)
            if ek.safe_is_file(file):
                if (
                    (
                        file.name.startswith(f".{options.my_name}-")
                        and file.suffix.casefold() == ".out"
                    )
                    or (
                        file.name.startswith(f".{options.my_name}-")
                        and file.suffix.casefold() == ".err"
                    )
                    or (
                        file.name.startswith(f".{options.my_name}_custom_modules_")
                        and file.suffix.casefold() == ".pkl"
                    )
                    or (
                        file.name.startswith(".")
                        and f"-{options.my_name}-" in file.name
                        and file.suffix.casefold() == ".json"
                    )
                ):
                    try:
                        logging.info("Deleting %s", file)
                        file.unlink()
                    except BaseException:
                        logging.exception("Error deleting %s", file)
        sys.exit(0)
    elif getattr(
        options.args, "full", False
    ):  # implied by now: and not options.python_script:
        options.python_script = options.cwd
    else:
        logging.info(
            "You must specify either a script to run or one of these arguments: --full, --blank-slate (be careful using --blank-slate because it deletes all cached virtual environments, among other things!)."
        )

    if getattr(options.args, "reqs", False):
        options.extra_requirements = environment.parse_extra_requirements(
            options.extra_requirements_file, rawlog=options.rawlog
        )
        if not options.rawlog:
            logging.info(
                "Loaded extra requirements from ./%s: %s",
                options.extra_requirements_file,
                options.extra_requirements,
            )

    time1 = dt.datetime.now()
    settings = Settings(
        my_name=options.my_name,
        cwd=options.cwd,
        stay_out_list=tuple(options.stay_out_list),
        search_above_this_dir=options.search_above_this_dir,
        rawlog=options.rawlog,
    )
    options.custom_modules = dict_of_custom_modules(
        settings,
        use_cache=not getattr(options.args, "rc", False)
        and not getattr(options.args, "no_cache", False),
    )
    time2 = dt.datetime.now()
    elapsed_time = time2 - time1
    if not options.rawlog:
        logging.info("dict_of_custom_modules() took %s", elapsed_time)

    start_list_packages_time = dt.datetime.now()
    elapsed_time = start_list_packages_time - start_time
    if not options.rawlog:
        logging.info("Elapsed time: %s", elapsed_time)

    list_packages(options)

    if not options.rawlog:
        # Report the import names, which are what the user wrote in their source.
        logging.info(
            "Uninstalled imports: %s",
            sorted(record.import_name for record in options.uninstalled_imports),
        )
        if options.bad_imports:
            logging.warning("Bad imports: %s", options.bad_imports)
        warn_about_system_packages(options)
        if options.samedir_files:
            logging.info(
                "Imported files in the same directory as the script: %s",
                list(map(os.fspath, options.samedir_files)),
            )
        if options.subfolders:
            logging.info("Imported subfolders: %s", options.subfolders)

    if getattr(options.args, "justprint", False):
        ek.print_all_errors(memory_handler, options.rawlog)
        sys.exit(0)

    if not options.uninstalled_imports:
        if not options.rawlog:
            logging.info("All required packages are already installed.")
        start_raw_time = dt.datetime.now()
        result = subprocess.run(
            [sys.executable, os.fspath(options.python_script)] + options.script_args
        )
        script_exit_code = result.returncode
        elapsed_raw_time = dt.datetime.now() - start_raw_time
        if not options.rawlog:
            logging.info("Runtime: %s", elapsed_raw_time)
    elif last_used.is_virtualenv():
        if not options.rawlog:
            logging.info("Already in a virtual environment.")
        assert options.venv_dir is not None, "options.venv_dir must be set"
        if verify.check_packages_in_venv(
            environment.venv_python_for(options.venv_dir),
            uninstalled=options.uninstalled_imports,
            source_names=verify.source_import_names(
                options.all_imports,
                options.extra_requirements,
                getattr(options.args, "reqs", False),
            ),
        ):
            start_raw_time = dt.datetime.now()
            result = subprocess.run(
                [sys.executable, os.fspath(options.python_script)] + options.script_args
            )
            script_exit_code = result.returncode
            elapsed_raw_time = dt.datetime.now() - start_raw_time
            if not options.rawlog:
                logging.info("Runtime: %s", elapsed_raw_time)
        else:
            logging.error(
                "The current virtual environment does not have all the required packages."
            )
            if not options.rawlog:
                logging.info(
                    "Please deactivate the current virtual environment and run the script again."
                )
            script_exit_code = 1
    else:
        if getattr(options.args, "no_cache", False):
            match_dir = None
        else:
            match_dir = find_match_dir_in_cache(options)
        if match_dir is None:
            if not options.rawlog:
                logging.info(
                    "Creating new virtual environment '%s'...", options.venv_name
                )
            if setup_virtualenv(options):
                match_dir = options.venv_dir
                created_new_venv = True
            else:
                ek.my_critical_error(
                    "Failed to create a virtual environment.", choose_breakpoint=True
                )
                script_exit_code = 1
        else:
            if not options.rawlog:
                logging.info("Using existing virtual environment: %s", match_dir)
            created_new_venv = False

        if match_dir:
            options.set_venv_dir(match_dir)
            start_venv_time = dt.datetime.now()
            elapsed_time = start_venv_time - start_time
            if not options.rawlog:
                logging.info("Elapsed time: %s", elapsed_time)
            if not getattr(options.args, "full", False):
                command_list = [
                    os.fspath(options.venv_python),
                    os.fspath(options.python_script),
                ] + [str(arg) for arg in options.script_args]
                if not options.rawlog:
                    logging.info(
                        "Running command: %s",
                        " ".join(shlex.quote(arg) for arg in command_list),
                    )
                result = subprocess.run(command_list)
                end_time = dt.datetime.now()
                elapsed_time = end_time - start_venv_time
                if not options.rawlog:
                    logging.info(
                        "Elapsed time since activating virtual environment: %s",
                        elapsed_time,
                    )
                if result.returncode != 0 and not options.rawlog:
                    logging.error("Script exited with status %d", result.returncode)
                script_exit_code = result.returncode
            if (
                options.venv_dir.name.startswith("failed-")
                and options.install_succeeded
            ):
                # If the program has made it to this point, it has run successfully, so the venv directory can be renamed because it DIDN'T fail.
                rename_venv(options, options.venv_dir.name.removeprefix("failed-"))

            ek.save_options_to_json(options)

            if getattr(options.args, "full", False):
                built_or_found = "built" if created_new_venv else "found"
                logging.info(
                    "Successfully %s a virtual environment that can run all python scripts in %s.\n"
                    "Use this virtual environment:\n%s",
                    built_or_found,
                    options.script_dir,
                    options.venv_dir,
                )

    ek.print_all_errors(memory_handler, options.rawlog)
    logging.shutdown()
    # A script killed by a signal yields a negative returncode (e.g. -9 for
    # SIGKILL). Exiting a process with a negative status wraps around to the
    # wrong shell status (-9 becomes 247), so normalize to the conventional
    # 128 + signal number (-9 becomes 137) instead.
    if script_exit_code < 0:
        script_exit_code = 128 - script_exit_code
    return script_exit_code


def find_imports_in_script(
    options: Options, first_path: str | os.PathLike[str]
) -> None:
    """Scan a script for imports and record what was found on options.

    A bridge, not a design: analysis/scan.py returns an ImportScan, while
    list_packages, split_imports and warn_about_system_packages all still read
    these fields off Options. Phase 3c and 3e retire this bridge by giving
    those consumers the ImportScan directly.

    The seven fields below are handed to the scanner by reference, not by
    value -- the same dict/set/list objects options already holds, not
    copies -- and the scanner only ever mutates them in place (.add,
    .append, `d[k] = v`); it never rebinds one of them to a new object. So
    what the scanner writes through `scan` is visible through `options`
    immediately, with no copy-back step needed afterwards. This is also why
    the scanner must be *seeded* with this call, not just read afterwards:
    dict_of_custom_modules() populates options.custom_modules before
    list_packages() ever reaches this function, and get_all_imports() calls
    this once per file in a directory scan, relying on all seven fields
    (not just all_imports) accumulating across calls. Passing options'
    own objects in as `scan` is what makes both of those work.

    Args:
        options: The run's Options; the seven scan fields are updated in place.
        first_path: The script to scan.
    """
    settings = Settings(
        my_name=options.my_name,
        cwd=options.cwd,
        stay_out_list=tuple(options.stay_out_list),
        search_above_this_dir=options.search_above_this_dir,
        rawlog=options.rawlog,
    )
    scan = ImportScan(
        all_imports=options.all_imports,
        custom_modules=options.custom_modules,
        loaded_custom_modules=options.loaded_custom_modules,
        samedir_files=options.samedir_files,
        subfolders=options.subfolders,
        sys_path_hints=options.sys_path_hints,
        seen_stdlib_imports=options.seen_stdlib_imports,
    )
    analysis_scan.find_imports_in_script(
        settings, first_path, is_stdlib=options.stdlib.__contains__, scan=scan
    )


def warn_about_system_packages(options: Options) -> None:
    """Warn once for each standard-library import that needs an operating-system package.

    Args:
        options: Options object; reads options.seen_stdlib_imports.
    """
    for name, system_package in stdlib_index.hints_for(
        options.seen_stdlib_imports
    ).items():
        logging.warning(
            "%s is in the standard library but needs the %s system package "
            "before it will import.",
            name,
            system_package,
        )


@contextlib.contextmanager
def _probe_venv(options: Options) -> Iterator[Callable[[str], bool]]:
    """Build a throwaway venv and yield a predicate that imports names in it.

    A context manager, not a plain callable, because classification must only
    pay for the environment once it knows there is something to classify: a run
    with no imports leaves this unentered and builds nothing.

    Args:
        options: Options object; reads options.python_command.

    Yields:
        A predicate answering whether one import name imports in the venv.
    """
    with tempfile.TemporaryDirectory() as venv_dir:
        environment.create_venv(
            venv_dir, environment.venv_build_interpreter(options.python_command)
        )

        def is_importable(import_name: str) -> bool:
            """Report whether one import name imports in the probe venv.

            Args:
                import_name: The name as it would be written in source.

            Returns:
                True if the probe venv can import it.
            """
            return verify.check_packages_in_venv(
                environment.venv_python_for(venv_dir),
                record=ResolvedImport(import_name=import_name, pip_name=import_name),
            )

        yield is_importable


def split_imports(options: Options) -> None:
    """Adapter: run classification and copy its product back onto Options.

    The copy-back is total -- these five fields are the complete set the old
    split_imports wrote. See the plan's "Why the ImportScan bridge is not
    touched" section: classify reads the scan and writes nothing through it,
    so nothing here depends on in-place mutation. Each frozenset becomes a set
    again on the way back, because later stages (verify_and_repair_imports)
    still mutate options.uninstalled_imports.

    Args:
        options: Options object; the five classification fields are replaced.
    """
    scan = ImportScan(
        all_imports=options.all_imports,
        custom_modules=options.custom_modules,
        loaded_custom_modules=options.loaded_custom_modules,
        samedir_files=options.samedir_files,
        subfolders=options.subfolders,
        sys_path_hints=options.sys_path_hints,
        seen_stdlib_imports=options.seen_stdlib_imports,
    )
    result = classify.split_imports(
        scan,
        aliases=options.aliases,
        known_bad_imports=options.known_bad_imports,
        also_needs=options.also_needs,
        extra_requirements=options.extra_requirements,
        use_reqs=getattr(options.args, "reqs", False),
        probe=_probe_venv(options),
        rawlog=options.rawlog,
    )
    options.all_imports = set(result.all_imports)
    options.bad_imports = set(result.bad)
    options.installed_imports = set(result.installed)
    options.uninstalled_imports = set(result.uninstalled)
    options.total_imports = result.total_imports


def list_packages(options: Options) -> None:
    """Examine command line arguments to determine if we're looking at a directory or a single python script. List all installed and uninstalled packages that are imported in that directory or python script. Return these sets inside the options object.

    Args:
        options: Options object containing command line arguments and settings. Contains:
            - python_script:           Path to the Python script or directory to analyze.
            - rawlog:                  Boolean indicating if raw logging is enabled.
            - script_dir:              Directory containing the script, used for logging.
            - all_imports:             Set to be populated with all imports found.
            - installed_imports:       Set to be populated with ResolvedImport records.
            - uninstalled_imports:     Set to be populated with ResolvedImport records.
            - known_bad_imports:       Set of known bad imports to filter out.
            - stdlib:                  StdlibIndex used to skip standard library imports.
            - custom_modules:          Dictionary mapping custom module names to their file paths.
            - aliases:                 AliasIndex resolving import names to pip names
                                       (e.g., 'cv2' -> 'opencv-python').
            - also_needs:              Dictionary mapping import names to their dependencies.

    Returns:
        None - modifies options to include all imports found in the specified Python script or directory.

    Raises:
        ValueError:        If the provided path is not a valid Python script or directory.
        FileNotFoundError: If the specified file or directory does not exist.
    """
    assert options.python_script is not None, "options.python_script must be set"
    assert options.script_dir is not None, "options.script_dir must be set"
    if getattr(options.args, "full", False):
        if not options.rawlog:
            logging.info(
                "Building a virtual environment that can run every python script in %s",
                os.fspath(options.script_dir),
            )

    if isinstance(options.python_script, (str, Path)):
        options.python_script = ek.ensure_path(options.python_script)
        options.loaded_custom_modules = set()
        if ek.safe_is_file(options.python_script):
            if ek.is_python_script(options.python_script):
                if not options.rawlog:
                    logging.info(
                        "Processing a single Python script: %s",
                        os.fspath(options.python_script),
                    )
                python_file = options.python_script
                options.all_imports = set()
                find_imports_in_script(options, python_file)
            else:
                raise ValueError(
                    f"'{os.fspath(options.python_script)}' is not a valid Python script."
                )
        elif ek.safe_is_dir(options.python_script):
            if not options.rawlog:
                logging.info(
                    "Processing an entire folder of Python scripts: %s",
                    os.fspath(options.python_script),
                )
            get_all_imports(options, options.python_script)
        else:
            raise FileNotFoundError(
                f"The file or directory {os.fspath(options.python_script)} does not exist."
            )
    else:
        raise ValueError(
            f"Unexpected type for options.python_script: {type(options.python_script)}"
        )

    # Filter out invalid imports before splitting
    options.all_imports = {
        imp for imp in options.all_imports if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", imp)
    }

    split_imports(options)


def stayed_out_dir(options: Options, p: str | os.PathLike[str]) -> bool:
    """Check if the parent directory of path p contains any substrings from the stay_out_list."""
    p = ek.ensure_path(p)
    parent_str = os.fspath(p.parent)
    return any(sub in parent_str for sub in options.stay_out_list)


def get_all_imports(options: Options, directory: str | os.PathLike[str]) -> None:
    """Get all imports from all Python scripts in a directory."""
    directory = ek.ensure_path(directory)
    options.all_imports = set()
    # Build one iterator of candidate files (recursive)
    candidates = (
        p
        for p in directory.rglob("*")
        if ek.safe_is_file(p) and not stayed_out_dir(options, p)
    )
    # If you want a progress denominator that matches what you'll actually process:
    total_files = sum(1 for p in candidates if ek.is_python_script(p))
    max_digits = len(str(total_files))  # For formatting progress output
    processed_files = 0
    # Recreate the iterator (generators are single-use)
    candidates = (
        p
        for p in directory.rglob("*")
        if ek.safe_is_file(p) and not stayed_out_dir(options, p)
    )
    for file_path in candidates:
        if ek.is_python_script(file_path):
            find_imports_in_script(options, file_path)
            processed_files += 1
            if not options.rawlog:
                # OLD: logging.info(f"Processing file {processed_files:>{max_digits}}/{total_files} : {file_path}")
                logging.info(
                    "Processing file %*d/%d : %s",
                    max_digits,
                    processed_files,
                    total_files,
                    file_path,
                )
    if not options.rawlog:
        logging.info("Finished processing files in %s", os.fspath(directory))


def interpreter_tag(options: Options) -> str:
    """Return the "major.minor" tag of the interpreter this run is classified against.

    Taken from the standard-library index rather than probed again, so the tag in
    a venv's folder name, the tag in its manifest, and the version whose stdlib
    names decided what needed installing can never disagree.

    Args:
        options: Options object; reads options.stdlib.

    Returns:
        A tag such as "3.12".
    """
    major, minor = options.stdlib.python_version
    return f"{major}.{minor}"


_VERSION_PROBE_CODE = (
    "import json, sys\n"
    "from importlib.metadata import distributions\n"
    "print(json.dumps({"
    "'python': list(sys.version_info[:2]),"
    " 'versions': {d.metadata['Name']: d.version for d in distributions()"
    " if d.metadata['Name']}}))\n"
)


def installed_state_in_venv(options: Options) -> tuple[dict[str, str], str]:
    """Ask a virtual environment which versions and interpreter it actually has.

    This is what the manifest records, rather than what was requested or what
    pip printed: only the venv itself knows what ended up installed, including
    versions pip chose for unpinned packages, and which interpreter it was
    actually built with.

    Args:
        options: Options object; reads options.venv_python, which callers must
                 have already set -- a None value is a caller-contract error
                 and asserts rather than returning empty.

    Returns:
        A tuple of (versions, tag). versions maps normalized pip name to
        version, empty if the probe could not be run or its output could not
        be read -- a version veny could not read is recorded as unknown,
        which makes any later pin check on that package fail closed. tag is
        the venv's own "major.minor", or "" if the probe could not be run.
    """
    assert options.venv_python is not None, (
        "Virtual environment Python executable is not set."
    )
    command = [os.fspath(options.venv_python), "-c", _VERSION_PROBE_CODE]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,  # noqa: S603
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logging.warning("Could not list installed versions in the venv (%s).", exc)
        return {}, ""
    if result.returncode != 0:
        logging.warning(
            "Could not list installed versions in the venv: %s", result.stderr.strip()
        )
        return {}, ""
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logging.warning(
            "Could not read the installed versions reported by the venv (%s).", exc
        )
        return {}, ""
    return (
        {
            venv_cache.normalize_pip_name(name): str(version)
            for name, version in payload.get("versions", {}).items()
        },
        ".".join(str(part) for part in payload.get("python", [])),
    )


def manifest_for(
    options: Options, versions: dict[str, str], venv_tag: str = ""
) -> venv_cache.Manifest:
    """Build the manifest describing a finished virtual environment.

    Args:
        options:  Options object; reads options.uninstalled_imports (after any
                  repairs), options.extra_requirements, and the interpreter.
        versions: Installed versions, keyed by normalized pip name.
        venv_tag: The "major.minor" the venv's own interpreter reported. Empty
                  when the probe could not run, in which case the run's own
                  tag serves -- the pre-existing behaviour, and the only case
                  where the tag can still disagree with interpreter_path.

    Returns:
        The manifest to write into the venv.
    """
    # extra_requirements is keyed by whatever spelling the user typed on the
    # command line, which need not match record.pip_name's spelling -- the
    # versions dict a line below is already keyed normalized, so this lookup
    # must be too. Normalized once here rather than per record.
    normalized_requirements = {
        venv_cache.normalize_pip_name(name): spec
        for name, spec in options.extra_requirements.items()
    }
    packages = tuple(
        venv_cache.PackageRecord(
            import_name=record.import_name,
            pip_name=record.pip_name,
            installed_version=versions.get(
                venv_cache.normalize_pip_name(record.pip_name)
            ),
            requested_spec=normalized_requirements.get(
                venv_cache.normalize_pip_name(record.pip_name)
            ),
        )
        for record in sorted(options.uninstalled_imports, key=lambda r: r.pip_name)
    )
    return venv_cache.Manifest(
        schema_version=venv_cache.SCHEMA_VERSION,
        created=options.timestamp,
        veny_version=__version__,
        interpreter_tag=venv_tag or interpreter_tag(options),
        interpreter_path=environment.venv_build_interpreter(options.python_command),
        packages=packages,
    )


def record_venv_state(options: Options) -> None:
    """Rename the venv if its folder name has drifted, then write its manifest.

    Two things can make the folder name written before installing wrong by the
    time this runs. verify_and_repair_imports can replace a record whose
    pip_name was wrong, so the name may list a package the venv does not have.
    And the folder name is built from the run's stdlib tag
    (interpreter_tag(options)) before the venv exists, while the manifest uses
    the venv's own probed tag -- if the probe interpreter degrades (or uv's
    resolution disagreed with what veny classified against), those two tags
    can differ. Either way the name is only a prefilter, but a stale one
    rejects a venv the manifest would accept -- so the name is brought back
    into agreement with the manifest here, using the same tag the manifest is
    about to record.

    Args:
        options: Options object; reads the final records and updates
                 options.venv_dir if a rename happens.

    Returns:
        None.
    """
    assert options.venv_dir is not None, "options.venv_dir must be set"
    # Probed here, before build_folder_name, so the folder name and the
    # manifest can never disagree on which interpreter tag they record: both
    # come from this one call. Falls back to the run's own tag when the probe
    # could not run (empty venv_tag), matching manifest_for's fallback below.
    versions, venv_tag = installed_state_in_venv(options)
    wanted_name = venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=venv_tag or interpreter_tag(options),
        timestamp=options.timestamp,
        pip_names=[record.pip_name for record in options.uninstalled_imports],
    )
    prefix = "failed-" if options.venv_dir.name.startswith("failed-") else ""
    if options.venv_dir.name != prefix + wanted_name:
        if not options.rawlog:
            logging.info(
                "This venv's packages or interpreter tag no longer match its "
                "folder name; renaming it to %s.",
                prefix + wanted_name,
            )
        rename_venv(options, prefix + wanted_name)
    venv_cache.write_manifest(
        options.venv_dir, manifest_for(options, versions, venv_tag)
    )


def setup_virtualenv(options: Options) -> bool:
    """Setup a virtual environment and install packages."""
    # The folder name is a cheap prefilter for the cache search; veny_manifest.json
    # inside the venv is the authority. venv_cache owns the encoding so a
    # hyphenated pip name cannot be mistaken for a field separator.
    folder_name = venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=interpreter_tag(options),
        timestamp=options.timestamp,
        pip_names=[record.pip_name for record in options.uninstalled_imports],
    )
    # Create a virtual environment directory that starts with "failed" in case the process fails. Only remove the "failed" part if this process completes successfully.
    options.set_venv_dir(options.my_dir / f"failed-{folder_name}")

    if not options.rawlog:
        logging.info("Creating virtual environment...")
    assert options.venv_dir is not None, "options.venv_dir must be set"
    environment.create_venv(
        options.venv_dir, environment.venv_build_interpreter(options.python_command)
    )
    if not options.rawlog:
        logging.info("Virtual environment created.")

    # `uv venv` refuses to build into a directory that already exists AND is
    # non-empty. set_venv_dir above already created options.venv_dir (mkdir),
    # so the requirements file must not land inside it until create_venv has
    # already succeeded against that (empty) directory -- writing it earlier
    # made every fresh build crash with CalledProcessError.
    assert options.requirements_file is not None, (
        "options.requirements_file must be set"
    )
    assert options.uninstalled_imports is not None, (
        "options.uninstalled_imports must be set"
    )
    assert options.extra_requirements is not None, (
        "options.extra_requirements must be set"
    )
    environment.write_requirements_file_with_extras(
        options.requirements_file,
        (record.pip_name for record in options.uninstalled_imports),
        options.extra_requirements,
    )

    result = environment.run_uv_pip(
        options.venv_python, "install", "-r", os.fspath(options.requirements_file)
    )
    options.install_succeeded = result is not None and result.returncode == 0
    if not options.install_succeeded:
        # uv names the package it could not satisfy, so there is nothing an
        # individual sweep would add. The venv keeps its "failed-" prefix, and
        # verify_and_repair_imports below gets its turn on what did install.
        logging.error(
            "uv could not install every requirement; this venv folder keeps its "
            "'failed-' prefix.%s",
            f" uv reported:\n{result.stderr.strip()}" if result is not None else "",
        )

    # Verify each import the user wrote, repairing the ones the install did not
    # satisfy, before the check that decides whether this venv gets to drop its
    # "failed-" prefix. This is also the only place that ever writes the alias
    # cache, so it must run on the successful path too, not just on failure.
    source_names = verify.source_import_names(
        options.all_imports,
        options.extra_requirements,
        getattr(options.args, "reqs", False),
    )
    assert options.requirements_file is not None, (
        "options.requirements_file must be set"
    )
    assert options.venv_python is not None, "options.venv_python must be set"
    options.uninstalled_imports = set(
        verify.verify_and_repair_imports(
            venv_python=options.venv_python,
            requirements_file=options.requirements_file,
            uninstalled=options.uninstalled_imports,
            extra_requirements=options.extra_requirements,
            source_names=source_names,
            index=options.aliases,
            rawlog=options.rawlog,
        )
    )
    # The manifest records the venv's final state, so it is written after any
    # repair -- it must describe what really provided each import, not what was
    # first attempted.
    record_venv_state(options)
    # Check that all packages can be imported in the venv.
    assert options.venv_dir is not None, "options.venv_dir must be set"
    return verify.check_packages_in_venv(
        environment.venv_python_for(options.venv_dir),
        uninstalled=options.uninstalled_imports,
        source_names=source_names,
    )


def rename_venv(options: Options, new_name: str) -> None:
    """Rename a virtual environment directory and fix the paths recorded inside it.

    A stdlib-built venv records its own location in pyvenv.cfg (uv-built venvs
    do not), so a rename that touches only the directory can leave a venv that
    points at a path that no longer exists. Two callers need this: dropping the
    "failed-" prefix once a run succeeds, and re-naming a venv whose package
    list changed when verify_and_repair_imports repaired a wrongly resolved pip
    name.

    Args:
        options:  Options object; reads and updates options.venv_dir.
        new_name: The directory's new name, not a path.

    Returns:
        None. Failure to rewrite a recorded path is logged, not raised: the venv
        has already moved and the run continues.
    """
    assert options.venv_dir is not None, "options.venv_dir must be set"
    old_dir = options.venv_dir
    new_dir = old_dir.with_name(new_name)
    if new_dir == old_dir:
        return
    old_dir.rename(new_dir)
    options.set_venv_dir(new_dir)
    for path in (options.venv_dir / "pyvenv.cfg",):
        try:
            contents = path.read_text()
        except OSError as exc:
            logging.warning(
                "Could not read %s after renaming the venv (%s).", path, exc
            )
            continue
        updated = contents.replace(old_dir.name, new_dir.name)
        if updated == contents:
            continue
        try:
            path.write_text(updated)
        except OSError as exc:
            logging.warning(
                "Could not update %s after renaming the venv (%s).", path, exc
            )


def latest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None:
    """Return the folder Path that has the latest timestamp.

    Args:
        final_venv_folders: A dictionary where keys are folder paths (as strings or
                            os.PathLike objects) and values are dictionaries containing
                            metadata about each folder, including a 'timestamp' key.

    Returns:
        The Path object of the folder with the latest timestamp, or None if no valid
        folder is found.
    """
    latest_folder: Path | None = None
    latest_timestamp: int | None = None
    for folder, data in final_venv_folders.items():
        if latest_timestamp is None or data["timestamp"] > latest_timestamp:
            latest_timestamp = data["timestamp"]
            latest_folder = folder
    return latest_folder


def oldest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None:
    """Return the folder Path that has the oldest timestamp.

    Args:
        final_venv_folders: A dictionary where keys are folder paths (as strings or
                            os.PathLike objects) and values are dictionaries containing
                            metadata about each folder, including a 'timestamp' key.

    Returns:
        The Path object of the folder with the oldest timestamp, or None if no valid
        folder is found.
    """
    oldest_folder: Path | None = None
    oldest_timestamp: int | None = None
    for folder, data in final_venv_folders.items():
        if oldest_timestamp is None or data["timestamp"] < oldest_timestamp:
            oldest_timestamp = data["timestamp"]
            oldest_folder = folder
    return oldest_folder


def smallest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None:
    """Return the folder Path that has the fewest packages.

    Args:
        final_venv_folders: A dictionary where keys are folder paths (as strings or
                            os.PathLike objects) and values are dictionaries containing
                            metadata about each folder, including a 'num_packages' key.

    Returns:
        The Path object of the folder with the fewest packages, or None if no valid
        folder is found.
    """
    smallest_folder: Path | None = None
    smallest_num_packages: int | None = None
    for folder, data in final_venv_folders.items():
        if (
            smallest_num_packages is None
            or data["num_packages"] < smallest_num_packages
        ):
            smallest_num_packages = data["num_packages"]
            smallest_folder = folder
    return smallest_folder


def check_venv_dir(options: Options, venv_dir: str | os.PathLike[str]) -> bool:
    """Check whether a cached venv directory can serve this run.

    The venv's own manifest is the authority. An options JSON written by an
    earlier run says what that run wanted, not what the venv holds, and its
    records compare by exact spelling -- so a venv built when "yaml" resolved to
    "PyYAML" was rejected by a run spelling it "pyyaml". Asking the manifest puts
    every candidate, last-used or not, through one comparison.

    Args:
        options:  Options object containing the current settings.
        venv_dir: The cached virtual environment directory.

    Returns:
        True if the venv holds what this run needs, for the right interpreter,
        and its imports really import.
    """
    venv_dir = ek.ensure_path(venv_dir)
    if not ek.safe_is_dir(venv_dir):
        if not options.rawlog:
            logging.info(
                "The cached venv directory %s is no longer there.", os.fspath(venv_dir)
            )
        return False
    manifest = venv_cache.read_manifest(venv_dir)
    if manifest is None:
        if not options.rawlog:
            logging.info(
                "The cached venv directory %s has no readable manifest.",
                os.fspath(venv_dir),
            )
        return False
    result = venv_cache.satisfies(
        manifest, wanted_packages(options), interpreter_tag(options)
    )
    if not result.matched:
        if not options.rawlog:
            logging.info(
                "The cached venv directory %s cannot be used because %s.",
                os.fspath(venv_dir),
                result.reason,
            )
        return False
    # The manifest says the packages are there; this confirms the imports
    # really import. source_names is now always passed explicitly: verify's
    # empty default cannot work it out for itself, and an empty set here would
    # silently widen every check to the distribution's whole top-level list.
    if verify.check_packages_in_venv(
        environment.venv_python_for(venv_dir),
        uninstalled=options.uninstalled_imports,
        source_names=verify.source_import_names(
            options.all_imports,
            options.extra_requirements,
            getattr(options.args, "reqs", False),
        ),
    ):
        return True
    logging.error(
        "The cached venv directory %s failed check_packages_in_venv.",
        os.fspath(venv_dir),
    )
    return False


def wanted_packages(options: Options) -> list[venv_cache.Wanted]:
    """Describe what this run needs, for matching against a cached venv.

    Args:
        options: Options object; reads options.uninstalled_imports and
                 options.extra_requirements.

    Returns:
        One entry per record, carrying its pip name and any --reqs spec.
    """
    # See manifest_for: extra_requirements' keys are user-typed spellings, not
    # necessarily record.pip_name's spelling, so the lookup must normalize both
    # sides. Built once per call rather than inside the list comprehension.
    normalized_requirements = {
        venv_cache.normalize_pip_name(name): spec
        for name, spec in options.extra_requirements.items()
    }
    return [
        venv_cache.Wanted(
            pip_name=record.pip_name,
            spec=normalized_requirements.get(
                venv_cache.normalize_pip_name(record.pip_name)
            ),
        )
        for record in sorted(options.uninstalled_imports, key=lambda r: r.pip_name)
    ]


@dataclass(frozen=True)
class CacheCandidate:
    """A cached venv folder that has already been parsed and read once.

    Carrying these along lets the ranking pass in find_match_dir_in_cache
    consume them directly instead of re-parsing the name and re-reading the
    manifest -- a second read that could only fail if the folder changed
    underneath the run, and had no correct response to that failure.

    Attributes:
        folder:   The cached venv directory.
        parsed:   The folder name, already parsed.
        manifest: The venv's manifest, already read.
    """

    folder: Path
    parsed: venv_cache.FolderName
    manifest: venv_cache.Manifest


def cache_candidates(options: Options, folders: list[Path]) -> list[CacheCandidate]:
    """Filter cached venv folders down to those that can serve this run.

    The folder name is a cheap reject; veny_manifest.json is the decision. A
    folder with no readable manifest is skipped, which is what retires every
    virtual environment built before manifests existed.

    Args:
        options: Options object; reads the records, the specs, and the tag.
        folders: Candidate directories, already filtered by name prefix.

    Returns:
        The folders that match, in the order given, each paired with the
        parsed name and manifest already read while deciding.
    """
    tag = interpreter_tag(options)
    wanted = wanted_packages(options)
    names = [item.pip_name for item in wanted]
    matches: list[CacheCandidate] = []
    for folder in folders:
        parsed = venv_cache.parse_folder_name(folder.name)
        if parsed is None:
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(
                    "Skipping %s: not a venv folder name veny wrote.", os.fspath(folder)
                )
            continue
        if parsed.interpreter_tag != tag or not venv_cache.name_allows(parsed, names):
            continue
        manifest = venv_cache.read_manifest(folder)
        if manifest is None:
            if not options.rawlog:
                logging.info(
                    "Skipping the cached venv %s: it has no readable manifest.",
                    os.fspath(folder),
                )
            continue
        result = venv_cache.satisfies(manifest, wanted, tag)
        if not result.matched:
            if not options.rawlog:
                logging.info(
                    "Skipping the cached venv %s because %s.",
                    os.fspath(folder),
                    result.reason,
                )
            continue
        matches.append(CacheCandidate(folder=folder, parsed=parsed, manifest=manifest))
    return matches


def find_match_dir_in_cache(options: Options) -> Path | None:
    """Try to find a matching virtual environment directory in the cache.

    Args:
        options: Options object containing the necessary parameters.

    Returns:
        The path to the matching virtual environment directory if found, otherwise None.

    Raises:
        None, but logs errors if the combination of flags is invalid, if no matching venv is found,
        or if the cached venv is invalid.
    """
    if (
        not getattr(options.args, "latest", False)
        and not getattr(options.args, "oldest", False)
        and not getattr(options.args, "last_used", False)
        and not getattr(options.args, "smallest", False)
    ):
        options.args.last_used = True  # If no flags are set, then the default is to load the last used venv in the cache
    if (
        getattr(options.args, "last_used", False)
        and not getattr(options.args, "latest", False)
        and not getattr(options.args, "smallest", False)
    ):
        assert options.script_dir is not None, "options.script_dir must be set"
        assert options.python_script is not None, "options.python_script must be set"
        options_last_used = last_used.load_last_used_options(
            options,
            script_dir=options.script_dir,
            python_script=options.python_script,
            pathlibcutoff=options.pathlibcutoff,
            rawlog=options.rawlog,
        )
        # venv_dir is declared in veny.Options.__init__, not in the base
        # emmykit.Options that load_last_used_options builds from, so a
        # last-used JSON written without that key must not raise here.
        venv_dir_last_used = getattr(options_last_used, "venv_dir", None)
        if (
            options_last_used is not None
            and venv_dir_last_used is not None
            and check_venv_dir(options, venv_dir_last_used)
        ):
            return ek.ensure_path(venv_dir_last_used)
        else:
            if not options.rawlog:
                logging.info("Trying to load the latest matching venv now.")
        options.args.latest = (
            True  # If that didn't work, try to load the latest venv in the cache
        )
        options.args.last_used = False  # And set this to False because it failed
    if not options.rawlog:
        logging.info(
            "Checking the cache for a virtual environment with all the required packages..."
        )
    all_venv_folders = [
        f
        for f in options.my_dir.iterdir()
        if ek.safe_is_dir(f) and f.name.startswith(options.venv_name)
    ]
    final_venv_folders: dict[Path, dict[str, int]] = {}
    for candidate in cache_candidates(options, all_venv_folders):
        final_venv_folders[candidate.folder] = {
            "timestamp": int(candidate.parsed.timestamp.replace("-", "")),
            "num_packages": len(candidate.manifest.packages),
        }
    if not final_venv_folders:
        if not options.rawlog:
            logging.info("No matching venv folders found in the cache.")
    else:
        if not options.rawlog:
            logging.info(
                "Found %d matching venv folders in the cache.", len(final_venv_folders)
            )
        if (
            getattr(options.args, "latest", False)
            and not getattr(options.args, "oldest", False)
            and not getattr(options.args, "last_used", False)
            and not getattr(options.args, "smallest", False)
        ):
            # Return the latest venv in the cache which has all the packages needed now
            latest_venv_folder: Path | None = latest_venv(final_venv_folders)
            if latest_venv_folder is None:
                if not options.rawlog:
                    logging.error(
                        "Could not determine the latest venv folder from the cache."
                    )
                return None
            if check_venv_dir(options, latest_venv_folder):
                return latest_venv_folder
            if not options.rawlog:
                logging.error(
                    "The latest venv in the cache is invalid. Giving up on the cache and starting from scratch."
                )
            return None
        elif (
            getattr(options.args, "oldest", False)
            and not getattr(options.args, "latest", False)
            and not getattr(options.args, "last_used", False)
            and not getattr(options.args, "smallest", False)
        ):
            # Return the oldest venv in the cache which has all the packages needed now
            oldest_venv_folder: Path | None = oldest_venv(final_venv_folders)
            if oldest_venv_folder is None:
                if not options.rawlog:
                    logging.error(
                        "Could not determine the oldest venv folder from the cache."
                    )
                return None
            if check_venv_dir(options, oldest_venv_folder):
                return oldest_venv_folder
            if not options.rawlog:
                logging.error(
                    "The oldest venv in the cache is invalid. Giving up on the cache and starting from scratch."
                )
            return None
        elif (
            getattr(options.args, "smallest", False)
            and not getattr(options.args, "latest", False)
            and not getattr(options.args, "oldest", False)
            and not getattr(options.args, "last_used", False)
        ):
            # Return the smallest venv in the cache which has all the packages needed now
            smallest_venv_folder: Path | None = smallest_venv(final_venv_folders)
            if smallest_venv_folder is None:
                if not options.rawlog:
                    logging.error(
                        "Could not determine the smallest venv folder from the cache."
                    )
                return None
            if check_venv_dir(options, smallest_venv_folder):
                return smallest_venv_folder
            if not options.rawlog:
                logging.error(
                    "The smallest venv in the cache is invalid. Giving up on the cache and starting from scratch."
                )
            return None
        else:  # This should never happen
            logging.error(
                f"Invalid combination of flags!\n"
                f"{getattr(options.args, 'latest',    False) = }\n"
                f"{getattr(options.args, 'oldest',    False) = }\n"
                f"{getattr(options.args, 'last_used', False) = }\n"
                f"{getattr(options.args, 'smallest',  False) = }"
            )
    return None
