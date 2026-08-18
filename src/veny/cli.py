#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), ChatGPT 5 Thinking (it/its), and GitHub Copilot (it/its).
from __future__ import (
    annotations,
)  # For Python 3.7+ compatibility with type annotations

import argparse
import datetime as dt
import functools
import json
import logging
import os
import re
import shlex  # For safely quoting shell commands
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
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
from . import json_types, venv_cache
from .analysis import scan as analysis_scan
from .analysis.custom_modules import dict_of_custom_modules


@functools.cache
def uv_binary() -> str:
    """Return the uv executable veny drives its environment layer with.

    Prefers the binary shipped by the ``uv`` PyPI package, which is installed
    alongside veny and so carries a version pinned with veny's own. Falls back
    to whatever is on PATH, which resolves by luck -- the weakness that retired
    the shell-alias install -- and is only preferable to failing outright.

    Returns:
        A path or command name to invoke uv with.

    Raises:
        SystemExit: If neither the packaged binary nor PATH yields a uv.
    """
    try:
        import uv
    except ImportError:
        pass
    else:
        return os.fspath(uv.find_uv_bin())
    on_path = shutil.which("uv")
    if on_path:
        logging.warning(
            "Using the uv found on PATH (%s). The uv package is not installed "
            "alongside veny, so its version is not pinned to veny's.",
            on_path,
        )
        return on_path
    raise SystemExit(
        "veny requires uv, which is not installed and is not on PATH.\n"
        "Reinstall veny with:  uv tool install veny"
    )


def create_venv(target: str | os.PathLike[str], python: str = "") -> None:
    """Create a virtual environment at target using uv.

    No pip is seeded: veny drives installs through uv, and a script that
    installs into the environment veny built for it is working against veny.

    Args:
        target: Directory to create the environment in.
        python: Interpreter for uv to build against. Empty means uv chooses.

    Raises:
        subprocess.CalledProcessError: If uv could not create the environment.
    """
    command = [uv_binary(), "venv", os.fspath(target)]
    if python:
        command += ["--python", python]
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Creating venv: %s", " ".join(shlex.quote(str(arg)) for arg in command)
        )
    subprocess.check_call(command)


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
        last_used_venv_python = load_last_used_venv_python(options)
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
        parse_extra_requirements(options)
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
    elif is_virtualenv():
        if not options.rawlog:
            logging.info("Already in a virtual environment.")
        if check_packages_in_venv(options):
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
    these fields off Options. Phase 3c and 3e retire the copy-back by giving
    those consumers the ImportScan directly.

    get_all_imports() calls this once per file in a directory scan and relies
    on the seven fields accumulating across calls (it resets only
    options.all_imports, to an empty set, before its loop). So this merges
    the scan's results into options rather than overwriting them: the set and
    dict fields are unioned in, and the two list fields are appended to
    without duplicating an entry options already has -- the same dedup
    process_import itself applies when it appends to a fresh ImportScan.

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
    scan = analysis_scan.find_imports_in_script(
        settings, first_path, is_stdlib=options.stdlib.__contains__
    )
    options.all_imports |= scan.all_imports
    options.custom_modules.update(scan.custom_modules)
    options.loaded_custom_modules |= scan.loaded_custom_modules
    for samedir_file in scan.samedir_files:
        if samedir_file not in options.samedir_files:
            options.samedir_files.append(samedir_file)
    for subfolder in scan.subfolders:
        if subfolder not in options.subfolders:
            options.subfolders.append(subfolder)
    options.sys_path_hints |= scan.sys_path_hints
    options.seen_stdlib_imports |= scan.seen_stdlib_imports


def resolve_records(
    options: Options, import_names: Iterable[str]
) -> set[ResolvedImport]:
    """Resolve import names into records carrying their pip names.

    Args:
        options:      Options object; reads options.aliases.
        import_names: Import names as they would be written in source.

    Returns:
        One record per name. A name the index cannot resolve keeps its own
        spelling as the pip name, because no evidence is not the same as
        contrary evidence.
    """
    records: set[ResolvedImport] = set()
    for name in import_names:
        resolution = options.aliases.resolve(name)
        primary = resolution.candidates[0].pip_name if resolution.candidates else name
        records.add(ResolvedImport(import_name=name, pip_name=primary))
    return records


def requirement_records(pip_names: Iterable[str]) -> set[ResolvedImport]:
    """Wrap pip names from a requirements file as records.

    These arrive already as pip names, and nothing maps a pip name back to an
    import name, so the same string is the best available answer for both.

    Args:
        pip_names: Package names as written in the extra requirements file.

    Returns:
        One record per name, with import_name == pip_name.
    """
    return {ResolvedImport(import_name=name, pip_name=name) for name in pip_names}


def add_dependencies(options: Options) -> None:
    """Add dependencies for uninstalled imports."""
    # Create a copy to iterate over since we'll be modifying the set
    initial_packages = options.uninstalled_imports.copy()

    for record in initial_packages:
        if record.import_name in options.also_needs:
            dependencies = options.also_needs[record.import_name]
            if not options.rawlog:
                logging.info(
                    "Adding dependencies for %s: %s", record.import_name, dependencies
                )
            options.uninstalled_imports.update(resolve_records(options, dependencies))

    # Handle nested dependencies by repeating this process until no new dependencies are added.
    added = True
    while added:
        added = False
        current_packages = options.uninstalled_imports.copy()
        for record in current_packages:
            if record.import_name in options.also_needs:
                dependencies = options.also_needs[record.import_name]
                new_dependencies = (
                    resolve_records(options, dependencies) - options.uninstalled_imports
                )
                if new_dependencies:
                    if not options.rawlog:
                        logging.info(
                            "Adding nested dependencies for %s: %s",
                            record.import_name,
                            sorted(r.import_name for r in new_dependencies),
                        )
                    options.uninstalled_imports.update(new_dependencies)
                    added = True


# Import errors that are facts about *this machine*, not about the package: the
# distribution installed and contains the module, but the native code it links
# against will not load here. The same release imports fine once the
# operating-system package is installed, so such a failure must never be
# remembered as a fault of the package. stdlib_index.NEEDS_SYSTEM_PACKAGE models
# the same class of problem and answers it with a report rather than a
# suppression; so does this.
#
# "undefined symbol" is deliberately included even though it also catches
# native-ABI mismatches (a wheel built against a different numpy, say), which are
# not strictly a missing system library. That errs toward retrying the next
# candidate rather than durably suppressing this one, which is the safe
# direction: the cost of a wrong guess here is one wasted attempt, while the cost
# in the other direction is permanent suppression of a correct package.
MACHINE_SCOPED_IMPORT_MARKERS: tuple[str, ...] = (
    "cannot open shared object file",
    "undefined symbol",
    "DLL load failed",
)

_SHARED_LIBRARY_PATTERN = re.compile(
    r"[\w.+-]+\.(?:so(?:\.[\w.]+)?|dylib|dll)", re.IGNORECASE
)


@dataclass(frozen=True)
class ImportOutcome:
    """The result of asking a venv to import one name.

    It reports what provided the import, not only that it imported, because
    those are different questions and only the venv can answer the first one.
    Everything that writes a cache entry needs the answer: "the import works" is
    not "this package provided it", and a cache entry outranks every tier except
    OVERRIDE on every later run.

    Attributes:
        imported:       Whether the import succeeded.
        rejection_kind: The alias_index rejection kind a failure warrants --
                        "import_failed" when the package does not contain the
                        module, "import_unavailable" when this machine cannot
                        load it. Empty when the import succeeded.
        detail:         The ImportError text, for reporting.
        providers:      The distributions the venv credits with providing the
                        import, PEP 503 normalized. Empty when the import failed,
                        or when the venv's metadata does not know.
    """

    imported: bool
    rejection_kind: str
    detail: str
    providers: frozenset[str] = frozenset()


def import_error_detail(output: str) -> str:
    """Pull the ImportError text out of a venv import check's stdout.

    Args:
        output: The check's stdout.

    Returns:
        The reported import errors, one per line, or an empty string.
    """
    return "\n".join(
        line.removeprefix("Import error: ")
        for line in output.splitlines()
        if line.startswith("Import error: ")
    )


def import_providers(output: str) -> frozenset[str]:
    """Return the distributions a venv import check credited with the import.

    Args:
        output: The check's stdout.

    Returns:
        The distribution names, PEP 503 normalized so they can be compared with
        a candidate's pip name. Empty when the check reported none.
    """
    names: set[str] = set()
    for line in output.splitlines():
        if line.startswith("Provided by: "):
            _, _, listed = line.removeprefix("Provided by: ").partition(": ")
            names.update(
                alias_index.normalize_pip_name(name)
                for name in listed.split(",")
                if name
            )
    return frozenset(names)


def import_outcome_in_venv(
    options: Options, import_name: str, venv_dir: str | os.PathLike[str] | None = None
) -> ImportOutcome:
    """Import one name inside the venv and classify any failure.

    "Installed but does not contain this module" and "installed, contains it,
    but this machine cannot load it" look identical from a boolean check, and
    only the first is a fact about the package. Persisting the second suppresses
    the correct package on this machine forever -- including after the user
    installs the missing system library.

    A successful import also reports which distributions the venv credits with
    providing it, because "the import works" is not "this package provided it".

    A machine-scoped failure is reported to the user, naming the library, because
    an unexplained dead end is the worst of the available outcomes.

    Args:
        options:     Options object containing settings and paths.
        import_name: The import name to try, as written in the user's source.
        venv_dir:    Optional venv to check in. Defaults to options.venv_dir.

    Returns:
        The outcome, carrying the rejection kind any failure warrants.
    """
    imported, output = run_import_check_in_venv(
        venv_python_for(options, venv_dir), [[import_name]], report_providers=True
    )
    if imported:
        return ImportOutcome(
            imported=True,
            rejection_kind="",
            detail="",
            providers=import_providers(output),
        )
    detail = import_error_detail(output)
    if not any(marker in detail for marker in MACHINE_SCOPED_IMPORT_MARKERS):
        return ImportOutcome(
            imported=False, rejection_kind="import_failed", detail=detail
        )
    library = _SHARED_LIBRARY_PATTERN.search(detail)
    logging.warning(
        "%s is installed but will not import on this machine: %s. That is a "
        "missing system library (%s), not the wrong package -- install the "
        "operating-system package that provides it. veny will not hold this "
        "against the package.",
        import_name,
        detail,
        library.group(0) if library else "unknown",
    )
    return ImportOutcome(
        imported=False, rejection_kind="import_unavailable", detail=detail
    )


def _credited_with_the_import(outcome: bool | ImportOutcome, pip_name: str) -> bool:
    """Return True if the import may be recorded as provided by pip_name.

    A bool importer carries no attribution at all, so it is taken at its word --
    that is the contract its callers were written against, and narrowing it would
    silently stop them caching anything.

    Args:
        outcome:  What the importer reported.
        pip_name: The candidate that was just installed.

    Returns:
        Whether the evidence supports crediting pip_name with the import.
    """
    if not isinstance(outcome, ImportOutcome):
        return True
    wanted = alias_index.normalize_pip_name(pip_name)
    return any(
        alias_index.normalize_pip_name(name) == wanted for name in outcome.providers
    )


def resolve_and_verify(
    resolution: alias_index.Resolution,
    index: alias_index.AliasIndex,
    installer: Callable[[str], bool],
    importer: Callable[[str], bool | ImportOutcome],
    uninstaller: Callable[[str], None],
    max_attempts: int = 3,
) -> alias_index.Candidate | None:
    """Install candidates in rank order until one actually provides the import.

    The resolver produces ranked guesses; only installing and importing proves
    one right. A candidate that installs without providing the import name is
    uninstalled, so a rejected package cannot pollute the environment or shadow
    the correct one on a later attempt.

    An importer that returns an ImportOutcome also says *why* a failure happened,
    and that decides whether the rejection is remembered: a package that does not
    contain the module is a durable fact, while one this machine cannot load is
    not. A plain bool importer is still accepted and is read as the durable kind.

    Args:
        resolution:   The ranked candidates for one import name.
        index:        The AliasIndex to record the outcome in.
        installer:    Installs a pip name, returning True on success.
        importer:     Returns whether the import name now imports, as a bool or
                      as an ImportOutcome carrying the rejection kind to use.
        uninstaller:  Removes a pip name that was installed but rejected.
        max_attempts: How many candidates to try before giving up.

    Returns:
        The verified candidate, or None if none of the attempts worked.
    """
    for candidate in resolution.candidates[:max_attempts]:
        logging.debug(
            "Trying %s for import %s (%s)",
            candidate.pip_name,
            resolution.import_name,
            candidate.evidence,
        )
        if not installer(candidate.pip_name):
            index.reject(resolution.import_name, candidate.pip_name, "install_failed")
            continue
        outcome = importer(resolution.import_name)
        if outcome.imported if isinstance(outcome, ImportOutcome) else outcome:
            # The import works, so this candidate is the answer for this run
            # either way. Whether it is written down depends on whether the venv
            # credits *it* with providing the import: a candidate can drag in a
            # transitive dependency that satisfies the import, and caching that
            # is the same durable misinformation confirm_if_attributable()
            # refuses to write on the other two paths.
            if _credited_with_the_import(outcome, candidate.pip_name):
                index.confirm(resolution.import_name, candidate.pip_name)
            else:
                logging.debug(
                    "Not caching %s -> %s: the venv credits %s with providing it.",
                    resolution.import_name,
                    candidate.pip_name,
                    sorted(outcome.providers)
                    if isinstance(outcome, ImportOutcome)
                    else "something else",
                )
            return candidate
        logging.debug(
            "%s installed but did not provide %s; removing it.",
            candidate.pip_name,
            resolution.import_name,
        )
        uninstaller(candidate.pip_name)
        index.reject(
            resolution.import_name,
            candidate.pip_name,
            outcome.rejection_kind
            if isinstance(outcome, ImportOutcome)
            else "import_failed",
        )
    return None


def venv_python_for(
    options: Options, venv_dir: str | os.PathLike[str] | None = None
) -> Path:
    """Return the interpreter inside a virtual environment.

    Args:
        options:  Options object; used when venv_dir is None.
        venv_dir: The venv to look in, or None to use options.venv_dir.

    Returns:
        The path to that venv's python.
    """
    if venv_dir is None:
        assert options.venv_dir is not None, "options.venv_dir must be set"
        venv_dir = options.venv_dir
    else:
        venv_dir = ek.ensure_dir(venv_dir)
    if sys.platform == "win32":
        return (venv_dir / "Scripts" / "python.exe").absolute()
    # Do NOT use resolve() here because this is a symlink and resolve() would break it
    return (venv_dir / "bin" / "python").absolute()


def run_import_check_in_venv(
    venv_python: Path, alternatives: list[list[str]], report_providers: bool = False
) -> tuple[bool, str]:
    """Ask a venv's own interpreter to import each group of alternative names.

    Args:
        venv_python:      The venv interpreter to run the check in.
        alternatives:     One group per thing to check. A group passes if any one
                          of its names imports.
        report_providers: Also report which distributions the venv credits with
                          each successful import. Off by default because only the
                          verification path needs it, and it costs a
                          packages_distributions() scan inside the venv.

    Returns:
        Whether every group imported, and the check's stdout -- which carries the
        ImportError text behind each failure, so a caller can tell a package that
        does not contain the module from one that is present but unusable on this
        machine. Discarding that text is what made a missing system library look
        like a fault of the package.
    """
    python_code = f"""
import sys
from importlib import import_module
report_providers = {report_providers!r}
providers = {{}}
if report_providers:
    try:
        from importlib.metadata import packages_distributions
        providers = packages_distributions()
    except Exception:
        providers = {{}}
successes = []
failures = []
details = []
counter = 0
for alternatives in {alternatives!r}:
    counter += 1
    ok = False
    for package in alternatives:
        try:
            import_module(package)
            ok = True
            break
        except ImportError as exc:
            details.append(package + ": " + str(exc))
            continue
    if ok:
        successes.append(alternatives[0])
        if report_providers:
            print("Provided by: " + package + ": " + ",".join(providers.get(package, [])))
    else:
        failures.append(alternatives[0])
if failures:
    print("Failed packages: " + ", ".join(failures))
    for detail in details:
        print("Import error: " + detail)
    sys.exit(1)
elif len(successes) != counter:
    print(f"Warning: No failures, but only recorded {{len(successes)}} successes out of {{counter}}.")
    sys.exit(2)
else:
    print(f"All {{len(successes)}} (out of {{counter}}) packages imported successfully.")
    sys.exit(0)
"""
    the_command = [os.fspath(venv_python), "-c", python_code]
    result = subprocess.run(the_command, capture_output=True, text=True, check=False)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("check_packages_in_venv stdout:\n%s", result.stdout)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("check_packages_in_venv stderr:\n%s", result.stderr)
    return "packages imported successfully" in result.stdout, result.stdout


def source_import_names(options: Options) -> set[str]:
    """Return the import names that were actually written in the user's source.

    Only these can be verified by importing them. requirement_records() (--reqs)
    and resolve_records() (dependencies) both produce records whose import_name
    is really a pip name -- "opencv-python", not "cv2" -- because a requirements
    line is a pip name and nothing maps it backwards. import_module() can never
    succeed on one of those, so treating its failure as evidence would condemn a
    package that installed perfectly well.

    Args:
        options: Options object; reads options.all_imports, options.args and
                 options.extra_requirements.

    Returns:
        The import names found in the analysed scripts.
    """
    names = set(options.all_imports)
    if getattr(options.args, "reqs", False):
        # split_imports() folds the requirements file's entries into
        # all_imports, but those are pip spellings, not import names.
        names -= set(options.extra_requirements)
    return names


def check_packages_in_venv(
    options: Options,
    record: ResolvedImport | None = None,
    venv_dir: str | os.PathLike[str] | None = None,
    source_names: set[str] | None = None,
) -> bool:
    """Check if packages can be imported in the specified virtual environment.

    This runs import_module() inside the venv, so it always wants the *import*
    name, never the pip name. Reading it off the record is what retires the old
    reverse-alias inversion, which lost every import name that shared a pip name
    with another and silently returned the pip name for anything it did not know.

    With no record (the bulk branch), it probes the venv's own interpreter once
    for its installed distributions. A record naming an import the user actually
    wrote -- or one the installed distribution declares -- is checked under that
    name alone: that exact name is what has to import, and widening it to the
    distribution's other top-level names would be fail-open (setuptools declares
    _distutils_hack, which imports whether or not setuptools does). Only a record
    carrying a pip spelling rather than an import name (a --reqs line, a
    dependency name) is checked against the distribution's declared top-level
    names, any one of which passing is a pass -- that metadata is all there is
    to go on for such a record. When the venv's metadata does not know the
    distribution, or the probe degrades, it falls back to record.import_name --
    the check is never skipped.

    Args:
        options:      Options object containing settings and paths.
        record:       Optional resolved import to check. If None, checks all uninstalled imports.
        venv_dir:     Optional path to the virtual environment directory. If None, uses options.venv_dir.
        source_names: Optional import names known to come from the user's source.
                      Defaults to options' own source_import_names(). check_venv_dir()
                      passes this explicitly, to pin the live run's names as what
                      governs its own call site rather than relying on the default.

    Returns:
        bool:       True if all packages can be imported successfully, False otherwise.

    Raises:
        None:       This function does not raise exceptions, but logs errors if the import fails.
    """
    venv_python = venv_python_for(options, venv_dir)
    if record is not None:
        # alternatives: one name per entry to try; passes if any one imports.
        alternatives = [[record.import_name]]
    else:
        # Ask the venv what it actually has, instead of import-checking every
        # record under its pip spelling: requirement_records() sets
        # import_name == pip_name for --reqs entries (a requirements line is
        # a pip name and nothing maps it backwards), and import_module()
        # always fails on a pip spelling like "opencv-python". Probing once
        # here and inverting the result answers "what does this distribution
        # actually import as?" from the installed artifact, covering every
        # distribution rather than only what a curated table happened to know.
        _, venv_distributions = alias_index.probe_interpreter(venv_python)
        import_names_by_dist = alias_index.import_names_by_distribution(
            venv_distributions
        )
        if source_names is None:
            source_names = source_import_names(options)
        alternatives = []
        for entry in sorted(options.uninstalled_imports, key=lambda r: r.import_name):
            top_levels = import_names_by_dist.get(
                alias_index.normalize_pip_name(entry.pip_name)
            )
            # A name the user wrote is what must import, full stop -- checking
            # the whole top-level list of whatever its pip_name happened to
            # install is fail-open twice over: a wrongly resolved pip_name
            # passes on the name it does provide, and setuptools passes on
            # _distutils_hack whether or not setuptools itself imports. The
            # metadata is consulted as a second way of recognising a source
            # name, and is the sole answer only for a record carrying a pip
            # spelling instead of an import name (a --reqs line, a dependency
            # name). Distribution not found, or the probe degraded to an empty
            # mapping: fall back to the import_name -- today's behaviour.
            # Never skip the check.
            if entry.import_name in source_names or (
                top_levels and entry.import_name in top_levels
            ):
                alternatives.append([entry.import_name])
            elif top_levels:
                alternatives.append(sorted(top_levels))
            else:
                alternatives.append([entry.import_name])
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Packages to check in venv: %s", alternatives)
    imported, _ = run_import_check_in_venv(venv_python, alternatives)
    return imported


def _compute_bad_imports(
    all_imports: set[str], known_bad: set[str], py2_only: frozenset[str]
) -> set[str]:
    """Return the imports that must never be handed to pip.

    Args:
        all_imports: Every import name found in the analysed scripts.
        known_bad:   Project-specific names that are not on PyPI.
        py2_only:    Python 2 standard-library names, from stdlib_index.

    Returns:
        The subset of all_imports that pip must not be asked to install.
    """
    bad = (known_bad | py2_only) & all_imports
    bad.update({imp for imp in all_imports if imp.startswith("_")})
    return bad


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


def split_imports(options: Options) -> None:
    """Split imports into installed, uninstalled, and bad imports."""
    options.bad_imports = _compute_bad_imports(
        options.all_imports, options.known_bad_imports, stdlib_index.PYTHON2_ONLY
    )
    if options.bad_imports:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Identified bad imports: %s", options.bad_imports)
    options.all_imports = options.all_imports - options.bad_imports
    options.installed_imports = set()
    options.uninstalled_imports = set()
    if getattr(options.args, "reqs", False):
        options.all_imports = options.all_imports.union(
            options.extra_requirements.keys()
        )
    options.total_imports = len(options.all_imports)
    if not options.total_imports:
        if not options.rawlog:
            logging.info("No imports found.")
        return

    max_length = max(
        len(imp) for imp in options.all_imports
    )  # Longest import name length, used for formatting
    max_digits = len(
        str(len(options.all_imports))
    )  # Maximum number of digits in import count, also used for formatting

    with tempfile.TemporaryDirectory() as venv_dir:
        create_venv(venv_dir, venv_build_interpreter(options))
        for i, imp in enumerate(options.all_imports, 1):
            # The import name is all either check below needs, and resolution is
            # deliberately not done yet: see the else branch.
            record = ResolvedImport(import_name=imp, pip_name=imp)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug("Checking if import %s is installed or uninstalled", imp)
            if imp in options.custom_modules.keys():
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(
                        "Custom module %s has path %s",
                        imp,
                        os.fspath(options.custom_modules[imp]),
                    )
                status_str = f"{ek.ANSI_CYAN}YES - custom module{ek.ANSI_RESET}"
            elif check_packages_in_venv(options, record=record, venv_dir=venv_dir):
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug("Module %s can be imported in venv", imp)
                status_str = f"{ek.ANSI_GREEN}YES -     installed{ek.ANSI_RESET}"
                # The pip name is left as the import name here because nothing
                # needs it: an installed import is never handed to pip, and
                # nothing downstream re-resolves it.
                options.installed_imports.add(record)
            else:
                # Only a genuinely uninstalled import needs a pip name, so this
                # is where resolution belongs. Resolving before the two checks
                # above charged every import up to six PyPI project lookups (the
                # name plus five mutations), each a metadata request plus up to
                # two ranged wheel reads -- for local modules and already
                # installed packages that never needed one.
                resolution = options.aliases.resolve(imp)
                # No candidate at all means no evidence either way, not a bad
                # name, so fall back to the import name and let pip have its say.
                primary = (
                    resolution.candidates[0].pip_name if resolution.candidates else imp
                )
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(
                        "Resolved import %s to candidates %s",
                        imp,
                        [c.pip_name for c in resolution.candidates],
                    )
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(
                        "Import %s is not installed and not a custom module", imp
                    )
                status_str = " NO - NOT installed"
                options.uninstalled_imports.add(
                    ResolvedImport(import_name=imp, pip_name=primary)
                )
            if not options.rawlog:
                logging.info(
                    "Checking import %-*s : %*d/%d - %s",
                    max_length,  # width for imp (left-aligned)
                    imp,
                    max_digits,  # width for i (right-aligned)
                    i,
                    options.total_imports,
                    status_str,
                )
    if getattr(options.args, "reqs", False):
        options.uninstalled_imports = options.uninstalled_imports.union(
            requirement_records(options.extra_requirements.keys())
        )
    add_dependencies(options)
    return


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


def venv_build_interpreter(options: Options) -> str:
    """Return the interpreter that should create the virtual environment.

    options.python_command is what stdlib and alias resolution were probed
    against, so it is what the venv must be built with; building with
    sys.executable instead classifies imports for one Python and installs them
    for another. find_preferred_python_version() returns "" when the preferred
    Python is absent from PATH, and only then does the running interpreter serve.

    The result is resolved to an absolute path with shutil.which() before it is
    returned. A bare command name like "python3" is not safe to hand to `uv
    venv --python`: uv treats a bare name as a request and resolves it through
    its own interpreter discovery order, which is not guaranteed to agree with
    (and was measured to disagree with) whichever "python3" PATH resolves to --
    silently building the venv against a different interpreter than the one
    imports were classified against. Resolving here, rather than only in
    create_venv, also fixes the manifest's interpreter_path field (see
    manifest_for), where an absolute path is strictly more useful than a bare
    name.

    Args:
        options: Options object; reads options.python_command.

    Returns:
        An absolute path to the interpreter to build with, when shutil.which()
        can resolve one. Falls back to the unresolved command/path (today's
        pre-fix behaviour) if it cannot -- logged, because the invariant above
        is no longer guaranteed to hold for that run.
    """
    command = options.python_command or sys.executable
    resolved = shutil.which(command)
    if resolved is None:
        logging.warning(
            "Could not resolve interpreter %r to an absolute path; passing it "
            "to uv unresolved. uv's own interpreter discovery may then choose "
            "a different Python than the one imports were classified against.",
            command,
        )
        return command
    return resolved


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


def parse_extra_requirements(options: Options) -> None:
    """Parse an extra requirements file into a dict of package names.

    Values are the version specifiers where present. The file should have one
    package per line, optionally with a specifier (e.g., 'package>=1.0').
    Lines starting with '#' are treated as comments and ignored.

    Args:
        options: Options object containing the path to the extra requirements file.

    Returns:
        None. A dictionary where keys are package names and values are version specifiers is added
        to the options object as extra_requirements.
    """
    options.extra_requirements = {}
    file_content = ek.my_fopen(
        options.extra_requirements_file, suppress_errors=True, rawlog=options.rawlog
    )
    if not file_content:
        return
    # Regular expression to capture package name and version specifier
    pattern = re.compile(r"^\s*([A-Za-z0-9_\-\.]+)\s*(.*)$")
    for line in file_content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            match = pattern.match(line)
            if match:
                package = match.group(1)
                version_spec = match.group(2).strip() if match.group(2) else ""
                options.extra_requirements[package] = version_spec


def write_requirements_file_with_extras(options: Options) -> None:
    """Write the requirements file with the extra requirements added."""
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Writing packages to %s", options.requirements_file)
    assert options.requirements_file is not None, (
        "options.requirements_file must be set"
    )
    assert options.uninstalled_imports is not None, (
        "options.uninstalled_imports must be set"
    )
    assert options.extra_requirements is not None, (
        "options.extra_requirements must be set"
    )
    with open(options.requirements_file, "w") as f:
        # Write the packages in alphabetical order so the requirements file is
        # deterministic. pip reads this file, so it gets the pip names.
        for package in sorted(
            record.pip_name for record in options.uninstalled_imports
        ):
            if package in options.extra_requirements:
                version_spec = options.extra_requirements[package]
                if version_spec:
                    f.write(f"{package}{version_spec}\n")
                else:
                    f.write(f"{package}\n")
            else:
                f.write(f"{package}\n")


def run_uv_pip(options: Options, *args: str) -> subprocess.CompletedProcess[str] | None:
    """Run one uv pip command against the venv without ever raising.

    Every caller is on a verification path, where the point is to report what
    happened rather than to end the run, so a missing interpreter or an
    unrunnable uv is reported as "no result" instead of an exception.

    Args:
        options: Options object; reads options.venv_python.
        *args:   The uv pip arguments, e.g. "install", "cv2".

    Returns:
        The completed process, or None if uv could not be run at all.
    """
    if options.venv_python is None:
        logging.error(
            "Cannot run uv pip %s: no virtual environment interpreter is set.",
            args[0],
        )
        return None
    the_command = [
        uv_binary(),
        "pip",
        args[0],
        "--python",
        os.fspath(options.venv_python),
        *args[1:],
    ]
    logging.info(
        "Running uv: %s", " ".join(shlex.quote(str(arg)) for arg in the_command)
    )
    try:
        return subprocess.run(
            the_command,
            capture_output=True,
            text=True,  # noqa: S603
            check=False,
        )
    except OSError:
        logging.exception("Could not run uv pip %s.", args[0])
        return None


def install_into_venv(options: Options, pip_name: str) -> bool:
    """Install one package into the venv, reporting failure instead of ending the run.

    The batch install is a single uv invocation that either succeeds or leaves
    the venv marked failed; this installer serves the verification loop instead,
    where one candidate failing must never end the run, so every failure is
    reported as False.

    Args:
        options:  Options object; reads options.venv_python.
        pip_name: The package to install.

    Returns:
        True if uv reported success.
    """
    result = run_uv_pip(options, "install", pip_name)
    if result is None:
        return False
    if result.returncode != 0:
        logging.error(
            "Failed to install %s. Error: %s", pip_name, result.stderr.strip()
        )
        return False
    return True


def uninstall_from_venv(options: Options, pip_name: str) -> None:
    """Remove a package that installed but did not provide the import it was tried for.

    Leaving it behind pollutes the venv and can shadow the correct package on a
    later attempt.

    Args:
        options:  Options object; reads options.venv_python.
        pip_name: The package to remove.
    """
    result = run_uv_pip(options, "uninstall", pip_name)
    if result is not None and result.returncode != 0:
        logging.warning(
            "Could not uninstall %s. Error: %s", pip_name, result.stderr.strip()
        )


def repair_unsatisfied_import(
    options: Options,
    record: ResolvedImport,
    installed_distributions: dict[str, frozenset[str]],
    outcome: ImportOutcome,
) -> ResolvedImport:
    """Try the remaining ranked candidates for an import the venv does not provide.

    The candidate that just failed is recorded first, and which kind of failure
    it was matters. A pip name the venv's metadata does not know never installed
    at all, which may be a network blip and is deliberately not remembered.
    A pip name the metadata does know installed, and then either does not contain
    the module (a durable fact about the package, remembered) or contains it but
    will not load here for want of a system library (a fact about the machine,
    not remembered -- see ImportOutcome). Recording it before re-resolving is
    also what removes a remembered failure from the ranked list that comes back,
    so the next attempt is genuinely a different project.

    The uninstall happens either way: a package that cannot be imported here is
    no use here, and the next candidate may well be the one that works (opencv's
    headless build needs no libGL).

    Args:
        options:                 Options object; reads and updates options.aliases.
        record:                  The record whose import name the venv does not provide.
        installed_distributions: Normalized distribution name -> the import names
                                 it provides, from the venv's own metadata.
        outcome:                 Why the import failed, from import_outcome_in_venv.

    Returns:
        A record naming the package that actually provided the import, or the
        original record unchanged when nothing did.
    """
    if alias_index.normalize_pip_name(record.pip_name) in installed_distributions:
        uninstall_from_venv(options, record.pip_name)
        options.aliases.reject(
            record.import_name, record.pip_name, outcome.rejection_kind
        )
    else:
        options.aliases.reject(record.import_name, record.pip_name, "install_failed")

    def installer(pip_name: str) -> bool:
        """Install a candidate, returning success rather than raising."""
        return install_into_venv(options, pip_name)

    def importer(import_name: str) -> ImportOutcome:
        """Report whether the *import* name now imports inside the venv, and why not."""
        return import_outcome_in_venv(options, import_name)

    def uninstaller(pip_name: str) -> None:
        """Remove a candidate that installed without providing the import."""
        uninstall_from_venv(options, pip_name)

    winner = resolve_and_verify(
        options.aliases.resolve(record.import_name),
        options.aliases,
        installer=installer,
        importer=importer,
        uninstaller=uninstaller,
    )
    if winner is None:
        logging.error(
            "Could not find a package that provides the import %s.", record.import_name
        )
        return record
    if not options.rawlog:
        logging.info(
            "%s provides the import %s (%s).",
            winner.pip_name,
            record.import_name,
            winner.evidence,
        )
    return ResolvedImport(import_name=record.import_name, pip_name=winner.pip_name)


def confirm_if_attributable(
    options: Options,
    record: ResolvedImport,
    installed_distributions: dict[str, frozenset[str]],
) -> None:
    """Cache a verified import only if the venv says the record's package provided it.

    A passing import check proves the import *works*; it does not prove that
    record.pip_name is what provided it. The import may come from a transitive
    dependency, or from another requested distribution, while the record's own
    pip name resolved wrongly-but-installably. A cache entry outranks every tier
    except OVERRIDE on every later run, so confirming an attribution that was
    never established writes durable misinformation.

    This covers the two paths that verify an import veny did not itself just
    install: the bulk pass and the per-record check. The third path --
    resolve_and_verify(), which installs a candidate and then checks -- applies
    the same rule through ImportOutcome.providers, because it is
    dependency-injected and has no Options to probe the venv with.

    Args:
        options:                 Options object; reads options.aliases.
        record:                  The record whose import was just verified.
        installed_distributions: Normalized distribution name -> the import names
                                 it provides, from the venv's own metadata.
    """
    top_levels = installed_distributions.get(
        alias_index.normalize_pip_name(record.pip_name)
    )
    if top_levels is not None and record.import_name in top_levels:
        options.aliases.confirm(record.import_name, record.pip_name)
    elif logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Not caching %s -> %s: the venv imports %s but does not attribute "
            "it to that distribution (it declares %s).",
            record.import_name,
            record.pip_name,
            record.import_name,
            sorted(top_levels) if top_levels else "nothing",
        )


def verify_and_repair_imports(options: Options) -> None:
    """Record what the install actually provided, and repair what it did not.

    The batch install installs each record's pip_name -- candidates[0] and
    nothing else -- so without this pass a wrong first candidate is final:
    ranking past position 0 has no production effect, confirm() and reject() are
    never called, ~/veny/module_aliases_cache.json is never written, and two of
    the five evidence tiers (CACHE and the rejection filter) are unreachable in
    the shipped product.

    Only imports the user actually wrote are verified this way, because only
    those are import names; see source_import_names(). Nothing here aborts the
    run -- an import that cannot be satisfied is left exactly as it was, for
    check_packages_in_venv() to report honestly.

    Args:
        options: Options object; reads options.uninstalled_imports and
                 options.aliases, and replaces any record that was repaired.
    """
    from_source = source_import_names(options)
    records = [
        record
        for record in sorted(options.uninstalled_imports, key=lambda r: r.import_name)
        if record.import_name in from_source
    ]
    if not records:
        return
    # One probe, used by both branches: the bulk branch needs it to attribute a
    # passing import to the distribution that actually provided it, and the
    # repair branch needs it to tell "installed but does not provide this" from
    # "never installed at all".
    _, venv_distributions = alias_index.probe_interpreter(options.venv_python)
    installed_distributions = alias_index.import_names_by_distribution(
        venv_distributions
    )
    if check_packages_in_venv(options):
        # Every source-derived record is checked under its own import name, so
        # a bulk pass means each one of them really did import.
        for record in records:
            confirm_if_attributable(options, record, installed_distributions)
        return
    repaired: dict[ResolvedImport, ResolvedImport] = {}
    for record in records:
        # The outcome, not just a bool: whether a failure is remembered depends
        # on whether it was the package's fault or this machine's.
        outcome = import_outcome_in_venv(options, record.import_name)
        if outcome.imported:
            confirm_if_attributable(options, record, installed_distributions)
            continue
        replacement = repair_unsatisfied_import(
            options, record, installed_distributions, outcome
        )
        if replacement != record:
            repaired[record] = replacement
    if repaired:
        options.uninstalled_imports = (
            options.uninstalled_imports - set(repaired)
        ) | set(repaired.values())
        # Keep the venv's own requirements.txt describing what is really installed.
        write_requirements_file_with_extras(options)


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
        interpreter_path=venv_build_interpreter(options),
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
    create_venv(options.venv_dir, venv_build_interpreter(options))
    if not options.rawlog:
        logging.info("Virtual environment created.")

    # `uv venv` refuses to build into a directory that already exists AND is
    # non-empty. set_venv_dir above already created options.venv_dir (mkdir),
    # so the requirements file must not land inside it until create_venv has
    # already succeeded against that (empty) directory -- writing it earlier
    # made every fresh build crash with CalledProcessError.
    write_requirements_file_with_extras(options)

    assert options.requirements_file is not None, (
        "options.requirements_file must be set"
    )
    result = run_uv_pip(options, "install", "-r", os.fspath(options.requirements_file))
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
    verify_and_repair_imports(options)
    # The manifest records the venv's final state, so it is written after any
    # repair -- it must describe what really provided each import, not what was
    # first attempted.
    record_venv_state(options)
    # Check that all packages can be imported in the venv.
    return check_packages_in_venv(options)


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


def is_virtualenv() -> bool:
    """Check if currently running in a virtual environment."""
    return sys.prefix != sys.base_prefix


def load_last_used_options(options: Options) -> Options | None:
    """Look for the most recent JSON file in the script directory that matches the script name and load it into a new Options object. Ignore any JSON files created before the options.pathlibcutoff timestamp."""
    assert options.script_dir is not None, "options.script_dir must be set"
    assert options.python_script is not None, "options.python_script must be set"
    pattern = re.compile(r"last-used-on-(\d{8}-\d{6})")
    json_files = [
        f
        for f in options.script_dir.iterdir()
        if f.name.startswith("." + options.python_script.name)
        and f.suffix.casefold() == ".json"
        and (m := pattern.search(f.name))  # extract timestamp
        and m.group(1) >= options.pathlibcutoff  # compare as strings
    ]
    if not json_files:
        if not options.rawlog:
            logging.info("No previous JSON files found in the script directory.")
        return None
    if len(json_files) > 1:
        json_files.sort(
            key=lambda x: dt.datetime.strptime(
                x.name.split("-")[-2] + x.name.split("-")[-1].replace(".json", ""),
                "%Y%m%d%H%M%S",
            ),
            reverse=True,
        )
    return ek.load_options_from_json(options, options.script_dir / json_files[0])


def load_last_used_venv_dir(options: Options) -> Path | None:
    """Look for the most recent JSON file in the script directory that matches the script name and return the venv_dir from it."""
    last_used_options = load_last_used_options(options)
    if not last_used_options:
        if not options.rawlog:
            logging.info("No last used options found, so no venv directory to return.")
        return None
    elif not hasattr(last_used_options, "venv_dir"):
        if not options.rawlog:
            logging.info("Last used options do not have a venv_dir attribute.")
        return None
    elif last_used_options.venv_dir is None:
        if not options.rawlog:
            logging.info("Last used venv directory is None.")
        return None
    elif not ek.safe_is_dir(last_used_options.venv_dir):
        if not options.rawlog:
            logging.warning(
                "Last used venv directory %s is no longer valid.",
                os.fspath(last_used_options.venv_dir),
            )
        return None
    else:
        if not options.rawlog:
            logging.info(
                "Last used venv directory found: %s",
                os.fspath(last_used_options.venv_dir),
            )
        return last_used_options.venv_dir


def load_last_used_venv_python(options: Options) -> Path | None:
    """Look for the most recent JSON file in the script directory that matches the script name and return the venv_python from it.

    Args:
        options: Options object containing settings and paths.

    Returns:
        The Path object of the last used venv_python, or None if not found or invalid.
    """
    last_used_options = load_last_used_options(options)
    if not last_used_options:
        if not options.rawlog:
            logging.info("No last used options found, so no venv_python to return.")
        return None
    elif not hasattr(last_used_options, "venv_python"):
        if not options.rawlog:
            logging.info("Last used options do not have a venv_python attribute.")
        return None
    elif last_used_options.venv_python is None:
        if not options.rawlog:
            logging.info("Last used venv_python is None.")
        return None
    elif not ek.safe_is_file(last_used_options.venv_python):
        if not options.rawlog:
            logging.warning(
                "Last used venv_python %s is no longer valid.",
                os.fspath(last_used_options.venv_python),
            )
        return None
    else:
        if not options.rawlog:
            logging.info(
                "Last used venv_python found: %s",
                os.fspath(last_used_options.venv_python),
            )
        return last_used_options.venv_python


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
    # really import. source_names is passed explicitly -- redundant with
    # check_packages_in_venv's own default today, since both read off this
    # same options -- so that this call site still names the live run's
    # source imports as what governs even if that default ever changes.
    if check_packages_in_venv(
        options, venv_dir=venv_dir, source_names=source_import_names(options)
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
        options_last_used = load_last_used_options(options)
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
