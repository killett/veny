#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), ChatGPT 5 Thinking (it/its), and GitHub Copilot (it/its).
from __future__ import annotations  # For Python 3.7+ compatibility with type annotations
import os
import sys
import subprocess
import datetime as dt
import argparse
import ast
import json
import re
import shutil
import venv
import pickle
from pathlib     import Path  # Preferred over os.path for path manipulations.
from typing      import Any
import logging
import tempfile
import shlex  # For safely quoting shell commands
from functools   import lru_cache  # For caching results of expensive function calls
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from . import alias_index
from . import stdlib_index
from . import __version__ as __version__
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
        super().__init__()                  # Call the parent class's __init__ method from emmykit
        self.log_mode:                      int = logging.INFO  # Use --debug to change to logging.DEBUG.
        self.search_above_this_dir:        bool = True
        self.my_name:                       str = "veny"  # Fixed: the installed command's name, not whatever argv[0] happens to be.
        self.home:                         Path = Path.home()  # User's home directory
        # The "my_dir" is NOT the directory where this script is located.
        # Instead, it's the directory where this script will store its virtual environments and packages.
        self.my_dir:                       Path = self.home / self.my_name
        self.python_command:                str = ""
        self.cwd:                          Path = Path.cwd().expanduser().resolve(strict=True)
        self.venv_name:                     str = "myenv"  # Can NOT include dashes ("-")
        self.packages_dir:                 Path = self.my_dir / "packages"
        self.test_dir:                     Path = self.my_dir / "test"
        # Both sets hold ResolvedImport records, so every consumer can pick the
        # right name instead of guessing which kind of string it was handed.
        self.uninstalled_imports: set[alias_index.ResolvedImport] = set()
        self.installed_imports:   set[alias_index.ResolvedImport] = set()
        self.bad_imports:              set[str] = set()
        self.all_imports:              set[str] = set()
        self.total_imports:                 int = 0
        self.custom_modules:    dict[str, Path] = {}  # Maps custom module names to their file Paths
        self.subfolders:              list[str] = []
        self.samedir_files:          list[Path] = []
        self.pip_list:                list[str] = []
        self.loaded_custom_modules:    set[str] = set()
        self.timestamp:                     str = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.sys_path_hints:          set[Path] = set()  # Filled by SysPathVisitor
        self.python_script:         Path | None = None
        self.script_name:                   str = ""  # python_script without the .py extension
        self.script_dir:            Path | None = None
        self.script_args:             list[str] = []
        self.options_json_filepath: Path | None = None
        # Before 2025-08-10 at 22:49:00, paths were stored as strings. After that date, they were stored as pathlib.Path objects. Any .pkl files created before that date have their paths converted to pathlib.Path objects when loaded. Any .json files created before that date are ignored when loading last-used options.
        self.pathlibcutoff:                        str = "20250810-224900"
        self.current_pip_version:                  str = ""
        self.new_pip_version:                      str = ""
        self.venv_dir:                     Path | None = None
        self.venv_python:                  Path | None = None
        self.venv_pip:                     Path | None = None
        self.requirements_file:            Path | None = None
        self.extra_requirements: dict[str, str | None] = {}
        self.extra_requirements_file:              str = "extra_requirements.txt"
        self.download_script_path:         Path | None = None
        self.simultaneous_success:                bool = False
        self.max_checks:                           int = 10  # Maximum number of times to check any repeated process.
        self.check_interval:                       int =  5  # Number of seconds to wait between checks.
        self.rawlog:                              bool = False
        self.pipreqs_available:                   bool = False
        self.read_files:                    list[Path] = []  # List of files read       by the Python script.
        self.write_files:                   list[Path] = []  # List of files written    by the Python script.
        self.download_urls:                 list[Path] = []  # List of  URLs downloaded by the Python script.
        self.upload_urls:                   list[Path] = []  # List of  URLs uploaded   by the Python script.
        self.current_method_name:                  str = ""  # Name of the current method being executed.
        # Some imports also need other packages to be installed. Both the keys and
        # the values are *import* names: they are matched against and resolved
        # through options.aliases, which turns e.g. "netCDF4" into pip's "netcdf4".
        self.also_needs: dict[str, list[str]] = {
            "xarray"  : ["dask", "netCDF4", "h5netcdf"],
            "litellm" : ["tenacity"],
            # NOT PIP PACKAGES: "pyautogui": ["scrot", "python3-tk"]
            # Add more packages and their dependencies here
        }
        # Standard-library membership is derived from a real interpreter, never hardcoded.
        # Replaced in main() once options.python_command is known, so that truth comes from
        # the interpreter that will actually run the user's script. See
        # docs/superpowers/specs/2026-08-12-stdlib-index-design.md
        self.stdlib: stdlib_index.StdlibIndex = stdlib_index.for_running_interpreter()
        self.seen_stdlib_imports:    set[str] = set()  # Standard-library imports that were skipped
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
        self.known_bad_imports: set[str] = {"snakeClass", "GPUampcor", "pathfinding_salvo_rework",
                                            "DQN", "bayesOpt", "non_existent_module"}
        # List of unusual imports that are not standard library modules or packages.
        self.unusual_imports: list[str] = ["a", "an", "dl", "the", "it", "x", "xx", "above", "another", "__builtin__", "within"]
        # List of directories to stay out of when searching for local custom imports because they're filled with standard library modules or other irrelevant files.
        self.stay_out_list: list[str] = ["myenv", ".venv", "anaconda3", "miniconda3", "miniforge3",
                                         ".conda", os.sep+"lib"+os.sep, ".vscode"]

    def set_venv_dir(self, venv_dir: str | os.PathLike[str]) -> None:
        """Set the directory for the virtual environment."""
        p = ek.ensure_path(venv_dir)
        self.venv_dir             = p
        self.venv_python          = p / "bin" / "python"  # Do NOT resolve() this symlink path
        self.venv_pip             = p / "bin" / "pip"     # Do NOT resolve() this symlink path
        self.requirements_file    = p / "requirements.txt"
        self.download_script_path = p / "download_packages.sh"
        p.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist


def parse_arguments(options: Options) -> None:
    """
    Parse command-line arguments.

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
    parser = argparse.ArgumentParser(prog="veny", description="Run a python script with optional flags.")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--feeling-lucky", action="store_true",
                        help="NOT FINISHED!!! Don't analyze imports, just try to run the script with the last used virtual environment. If that fails, try the latest virtual environment which has all the packages needed now.")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Run this program in debug mode, which prints additional debug messages.")
    parser.add_argument("--blank-slate", action="store_true",
                        help=f"Delete ~/{options.my_name}/ and all {options.my_name} .out and .err and .json and .pkl files in the current directory.")
    parser.add_argument("--full", action="store_true",
                        help="Build a virtual environment (venv) that can run every python script in the current directory. Cannot be used with a python script argument.")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Automatically say yes to any prompts to allow this program to run without the need for user interaction.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Don't search the cache. Instead, create a new virtual environment. Also, refresh the custom modules cache and the pip list.")
    parser.add_argument("--latest", action="store_true",
                        help="Load the latest cached venv which has all the packages needed now.")
    parser.add_argument("--oldest", action="store_true",
                        help="Load the oldest cached venv which has all the packages needed now.")
    parser.add_argument("--last-used", action="store_true",
                        help="Load the last used cached venv, but if that fails try the latest cached venv which has all the packages needed now.")
    parser.add_argument("--smallest", action="store_true",
                        help="Load the smallest cached venv (with the fewest packages) which has all the packages needed now.")
    parser.add_argument("--rc", action="store_true",
                        help="Refresh the custom modules cache and the pip list.")
    parser.add_argument("--reqs", action="store_true",
                        help="Read the extra_requirements.txt file in the current directory and install the packages listed there (with specific versions if present in the file) into the venv (along with the other packages needed to run the script as determined elsewhere in this program).")
    parser.add_argument("--rawlog", action="store_true",
                        help=f"Do not add timestamps or INFO level to log messages, and do not add extra INFO level log statements. Just produce the same output that would be seen when running the program without {options.my_name}.")
    parser.add_argument("--justprint", action="store_true",
                        help="Don't run the script, just print its package requirements.")
    parser.add_argument("--offline", action="store_true",
                        help="Never contact PyPI while working out which package provides an import. Import names are resolved from the override file, the cache, the target interpreter's installed packages and the built-in exceptions only.")
    parser.add_argument("script", nargs="?",
                        help="The script to run.")
    parser.add_argument("script_args", nargs=argparse.REMAINDER,
                        help="Optional arguments for the python script.")

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
    return alias_index.build(options.python_command, options.my_dir,
                             offline=getattr(options.args, "offline", False))


def main() -> None:
    """Main function."""
    start_time = dt.datetime.now()
    script_exit_code = 0
    options: Options = Options()
    parse_arguments(options)
    script_string       = getattr(options.args, "script",       None)
    options.script_args = getattr(options.args, "script_args",    [])
    options.rawlog      = getattr(options.args, "rawlog",      False)
    if script_string is None:
        options.python_script = None
    else:
        options.python_script = ek.ensure_file(script_string, raise_on_empty=True).resolve(strict=True)
        options.script_dir    = options.python_script.parent.absolute()
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Directory where the script to run is located: %s", os.fspath(options.script_dir))

    if getattr(options.args, "feeling_lucky", False) and options.python_script:
        last_used_venv_python = load_last_used_venv_python(options)
        if last_used_venv_python:
            command_list = [os.fspath(last_used_venv_python), os.fspath(options.python_script)] + options.script_args
            result = subprocess.run(command_list)
            if result.returncode != 0 and not options.rawlog:
                print(f"Error running script: {result.stderr}")
            sys.exit(result.returncode)
        else:
            if not options.rawlog: print("No luck: no last used virtual environment found. Running the script as normal.")

    memory_handler = ek.configure_logging(options.my_name, log_level=options.log_mode,
                                          rawlog=options.rawlog)

    options.python_command = ek.find_preferred_python_version()
    if options.python_command:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Python %s is available at: %s", ek.PY_VERSION, options.python_command)
    else:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Python %s is not available.", ek.PY_VERSION)
    options.stdlib = stdlib_index.resolve(options.python_command)
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug(
        "Standard library index: %d names from Python %d.%d (source: %s)",
        len(options.stdlib.names), options.stdlib.python_version[0],
        options.stdlib.python_version[1], options.stdlib.source)
    # This must happen before anything resolves, i.e. before list_packages() below.
    options.aliases = build_alias_index(options)
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug(
        "Alias index: %d overrides, %d cached names, tagged %s",
        len(options.aliases.overrides), len(options.aliases.cache.entries),
        options.aliases.cache.interpreter_tag)

    if not ek.safe_is_dir(options.my_dir):
        if not options.rawlog: logging.info("Directory %s does not exist yet, so it is being created.", options.my_dir)
        options.my_dir.mkdir(parents=True, exist_ok=True)
    if not ek.safe_is_dir(options.packages_dir):
        if not options.rawlog: logging.info("Directory %s does not exist yet, so it is being created.", options.packages_dir)
        options.packages_dir.mkdir(parents=True, exist_ok=True)

    if getattr(options.args, "full", False) and options.python_script:
        ek.my_critical_error("Full mode is not supported with a script argument.")
    elif options.python_script:
        pass  # If a script was provided as an argument, skip the rest of these checks.
    elif getattr(options.args, "blank_slate", False):
        if not getattr(options.args, "y", False):
            if not ek.prompt_then_confirm(f"Are you sure you want to delete everything in ~/{options.my_name}/"
                                          f" and all {options.my_name} .json files in the current directory? (y/n) "):
                logging.info("Exiting without deleting anything.")
                sys.exit(0)
        logging.info("Deleting everything in ~/%s/ and all %s .out and .err and .json and .pkl files in the current directory.",
                     options.my_name, options.my_name)
        shutil.rmtree(options.my_dir, ignore_errors=True)
        for file in options.cwd.iterdir():
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Checking %s", file)
            if ek.safe_is_file(file):
                if (file.name.startswith(f".{options.my_name}-")                      and file.suffix.casefold() == ".out" ) or \
                   (file.name.startswith(f".{options.my_name}-")                      and file.suffix.casefold() == ".err" ) or \
                   (file.name.startswith(f".{options.my_name}_custom_modules_")       and file.suffix.casefold() == ".pkl" ) or \
                   (file.name.startswith(".") and f"-{options.my_name}-" in file.name and file.suffix.casefold() == ".json"):
                    try:
                        logging.info("Deleting %s", file)
                        file.unlink()
                    except BaseException:
                        logging.exception("Error deleting %s", file)
        sys.exit(0)
    elif getattr(options.args, "full", False):  # implied by now: and not options.python_script:
        options.python_script = options.cwd
    else:
        logging.info("You must specify either a script to run or one of these arguments: alias, manual, blank-slate (be careful using blank-slate because it deletes all cached virtual environments, among other things!).")

    if getattr(options.args, "reqs", False):
        parse_extra_requirements(options)
        if not options.rawlog:
            logging.info("Loaded extra requirements from ./%s: %s", options.extra_requirements_file, options.extra_requirements)

    time1 = dt.datetime.now()
    options.custom_modules = dict_of_custom_modules(options)
    time2 = dt.datetime.now()
    elapsed_time = time2 - time1
    if not options.rawlog: logging.info("dict_of_custom_modules() took %s", elapsed_time)

    # Look for files in options.my_dir that start with pip_list and load the most recent one.
    options.pip_list = []
    pip_list_files = sorted([f for f in options.my_dir.iterdir() if f.name.startswith("pip_list")], reverse=True)
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("pip_list_files = %s", " ".join(os.fspath(f) for f in pip_list_files))
    # If --rc was not specified, look for a text file with the pip list the last time this script was run.
    if not getattr(options.args, "rc", False) and pip_list_files:
        try:
            with open(options.my_dir / pip_list_files[0], "r") as file:
                for line in file:
                    options.pip_list.append(line.strip())
        except BaseException:
            logging.error(f"Error reading {pip_list_files[0]}")

    start_list_packages_time = dt.datetime.now()
    elapsed_time = start_list_packages_time - start_time
    if not options.rawlog: logging.info("Elapsed time: %s", elapsed_time)

    try:
        import pipreqs
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("pipreqs is available, so it will be used.")
        options.pipreqs_available = True
    except ImportError:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("pipreqs is not available. Try installing it with 'pip install pipreqs'.")
        options.pipreqs_available = False

    list_packages(options)

    if not options.rawlog:
        # Report the import names, which are what the user wrote in their source.
        logging.info("Uninstalled imports: %s",
                     sorted(record.import_name for record in options.uninstalled_imports))
        if options.bad_imports:
            logging.warning("Bad imports: %s", options.bad_imports)
        warn_about_system_packages(options)
        if options.samedir_files:
            logging.info("Imported files in the same directory as the script: %s", list(map(os.fspath, options.samedir_files)))
        if options.subfolders:
            logging.info("Imported subfolders: %s", options.subfolders)

    if getattr(options.args, "justprint", False):
        ek.print_all_errors(memory_handler, options.rawlog)
        sys.exit(0)

    if not options.uninstalled_imports:
        if not options.rawlog: logging.info("All required packages are already installed.")
        start_raw_time = dt.datetime.now()
        result = subprocess.run([sys.executable, os.fspath(options.python_script)] + options.script_args)
        script_exit_code = result.returncode
        elapsed_raw_time = dt.datetime.now() - start_raw_time
        if not options.rawlog: logging.info("Runtime: %s", elapsed_raw_time)
    elif is_virtualenv():
        if not options.rawlog: logging.info("Already in a virtual environment.")
        if check_packages_in_venv(options):
            start_raw_time = dt.datetime.now()
            result = subprocess.run([sys.executable, os.fspath(options.python_script)] + options.script_args)
            script_exit_code = result.returncode
            elapsed_raw_time = dt.datetime.now() - start_raw_time
            if not options.rawlog: logging.info("Runtime: %s", elapsed_raw_time)
        else:
            logging.error("The current virtual environment does not have all the required packages.")
            if not options.rawlog: logging.info("Please deactivate the current virtual environment and run the script again.")
    else:
        if getattr(options.args, "no_cache", False):
            match_dir = None
        else:
            match_dir = find_match_dir_in_cache(options)
        if match_dir is None:
            if not options.rawlog: logging.info("Creating new virtual environment '%s'...", options.venv_name)
            if setup_virtualenv(options):
                match_dir        = options.venv_dir
                created_new_venv = True
            else:
                ek.my_critical_error("Failed to create a virtual environment.", choose_breakpoint=True)
        else:
            if not options.rawlog: logging.info("Using existing virtual environment: %s", match_dir)
            created_new_venv = False

        if match_dir:
            options.set_venv_dir(match_dir)
            start_venv_time = dt.datetime.now()
            elapsed_time    = start_venv_time - start_time
            if not options.rawlog: logging.info("Elapsed time: %s", elapsed_time)
            if not getattr(options.args, "full", False):
                command_list = [os.fspath(options.venv_python), os.fspath(options.python_script)] + \
                               [str(arg) for arg in options.script_args]
                if not options.rawlog: logging.info("Running command: %s", " ".join(shlex.quote(arg) for arg in command_list))
                result       = subprocess.run(command_list)
                end_time     = dt.datetime.now()
                elapsed_time = end_time - start_venv_time
                if not options.rawlog: logging.info("Elapsed time since activating virtual environment: %s",
                                                    elapsed_time)
                if result.returncode != 0 and not options.rawlog:
                    logging.error("Error running script: %s", result.stderr)
                script_exit_code = result.returncode
            if options.venv_dir.name.startswith("failed-") and options.simultaneous_success:
                # If the program has made it to this point, it has run successfully, so the venv directory can be renamed because it DIDN'T fail.
                rename_venv(options, options.venv_dir.name.removeprefix("failed-"))

            ek.save_options_to_json(options)

            if getattr(options.args, "full", False):
                built_or_found = "built" if created_new_venv else "found"
                logging.info("Successfully %s a virtual environment that can run all python scripts in %s.\n"
                             "Use this virtual environment:\n%s", built_or_found, options.script_dir, options.venv_dir)

    ek.print_all_errors(memory_handler, options.rawlog)
    logging.shutdown()
    sys.exit(script_exit_code)


def _literal_str(expr_node: ast.AST) -> str | None:
    """Extract a string from an AST node if it is a literal string."""
    if isinstance(expr_node, ast.Constant) and isinstance(expr_node.value, str):
        return expr_node.value
    return None


def get_evaluated_arg(expr_node: ast.AST, default: str = "") -> str:
    """
    Safely pull a string out of an AST node via safe_eval(), or return default.
    """
    val = safe_eval(ast.unparse(expr_node))
    if isinstance(val, str):
        return val
    return default


def _record_IO(options: Options, file_content: str,
               attr: str, target: str, node: ast.Call) -> None:
    """
    Record an IO operation by appending a target to an options attribute
    and logging the operation.

    Args:
        options:      Options object containing attributes for file operations.
        file_content: The content of the file being analyzed.
        attr:         The attribute of options to append the target to (e.g., 'read_files').
        target:       The target file or directory being read/written.
        node:         The AST node representing the operation.

    Returns:
        None, but logs the operation and appends the target to the specified attribute.

    Raises:
        None, but logs an error if the target is not a string or if the node does not have a source segment.
    """
    snippet = ast.get_source_segment(file_content, node) or ""
    if not options.rawlog: logging.info("I/O operation → %s: %r (line %d: %s - found by %s)",
                                        attr, target, node.lineno, snippet.strip(),
                                        ek.return_method_name(levels_up=2))
    if target not in getattr(options, attr):
        getattr(options, attr).append(target)


def _get_full_attr_name(node: ast.AST) -> str | None:
    """
    Recursively walk an ast.Name/ast.Attribute chain
    and return its full dotted name, e.g.:
    Name(id='ZipFile')         -> 'ZipFile'
    Attribute(Name('zipfile'), 'ZipFile')       -> 'zipfile.ZipFile'
    Attribute(Attribute(Name('pkg'), 'zipfile'), 'ZipFile')
        -> 'pkg.zipfile.ZipFile'
    Returns None on anything else.

    Args:
        node: The AST node to analyze, which can be a Name or Attribute.

    Returns:
        A string representing the full dotted name of the node, or None if the node is not a Name or Attribute.

    Raises:
        None, but logs an error if the node is not a Name or Attribute.
    """
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        parent = _get_full_attr_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def unpack_method_call(node: ast.Call) -> tuple[ast.Call, str] | None:
    """
    If 'node' is a call of the form (<something>()).<method>(...),
    return (inner_call, method_name).  Otherwise return None.
    """
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    inner = func.value
    if not isinstance(inner, ast.Call):
        return None
    return inner, func.attr


class FileOperationsVisitor(ast.NodeVisitor):
    """Visitor to find file read/write operations in the AST."""

    def __init__(self, options: Options, file_content: str) -> None:
        """Initialize the visitor with options and file content."""
        super().__init__()
        self.options = options
        self.file_content = file_content

    def visit_Call(self, node: ast.Call) -> None:
        """Visit Call nodes to find file operations."""
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("FileVisiting Call node: %s", ast.dump(node))
        if self._process_open(        node): return
        if self._process_pathlib(     node): return
        if self._process_shutil(      node): return
        if self._process_os_open(     node): return
        if self._process_subprocess(  node): return
        if self._process_ctypes_api(  node): return
        if self._process_zipfile(     node): return
        if self._process_tarfile(     node): return
        if self._process_pandas(      node): return
        if self._process_numpy(       node): return
        if self._process_netcdf4(     node): return
        if self._process_xarray(      node): return
        if self._process_json(        node): return
        if self._process_csv(         node): return
        if self._process_yaml(        node): return
        if self._process_configparser(node): return
        if self._process_h5py(        node): return
        if self._process_pillow(      node): return
        if self._process_wave(        node): return
        if self._process_soundfile(   node): return
        if self._process_sqlite(      node): return
        if self._process_gzip(        node): return
        if self._process_bz2(         node): return
        if self._process_unknown_open(node): return
        if self._process_generic_file(node): return
        self.generic_visit(           node)  # Keep digging into the AST

    def _process_open(self, node: ast.Call) -> bool:
        """Process open(...) calls."""
        # Only examine open(...) - (the 'and node.args' protects against calls without arguments)
        if (isinstance(node.func, ast.Name) and node.func.id == "open" and node.args):
            # Extract filename via safe_eval (never raises—returns None on unsupported)
            filename = safe_eval(ast.unparse(node.args[0]))
            for kw in node.keywords:
                if kw.arg == "file":
                    maybe = safe_eval(ast.unparse(kw.value))
                    if maybe:
                        filename = maybe
            # only proceed if we got a real string
            if isinstance(filename, str):
                # Extract mode from positional arg[1] or keyword "mode"
                mode = _literal_str(node.args[1]) if len(node.args) > 1 else None
                for kw in node.keywords:
                    if kw.arg == "mode":
                        maybe = _literal_str(kw.value)
                        if maybe:
                            mode = maybe
                # Default to "r" if not specified and remove "b" if present
                # because we don't care about binary mode.
                mode = (mode or "r").replace("b", "")
                if "r" in mode:
                    _record_IO(self.options, self.file_content, "read_files",
                               filename, node)
                elif any(m in mode for m in ("w", "a", "x")):
                    _record_IO(self.options, self.file_content, "write_files",
                               filename, node)
                return True
        return False

    def _process_pathlib(self, node: ast.Call) -> bool:
        """Process pathlib.Path(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Call)
                and isinstance(node.func.value.func, ast.Attribute)
                and isinstance(node.func.value.func.value, ast.Name)
                and node.func.value.func.value.id == "pathlib"
                and node.func.value.func.attr     == "Path"):
            method = node.func.attr
            # first arg to Path(...) is the filename: evaluate it fully
            if not node.func.value.args:
                return False
            filename = safe_eval(ast.unparse(node.func.value.args[0]))
            if not isinstance(filename, str):
                return False
            # classify
            if method in ("read_text", "read_bytes"):
                _record_IO(self.options, self.file_content, "read_files",
                           filename, node)
                return True
            elif method in ("write_text", "write_bytes", "open"):
                _record_IO(self.options, self.file_content, "write_files",
                           filename, node)
                return True
        return False

    def _process_shutil(self, node: ast.Call) -> bool:
        """Process shutil operations like copy, move, etc."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "shutil"
                and node.func.attr in ("copy", "copy2", "move", "copytree", "rmtree")
                and len(node.args) >= 2):
            src = safe_eval(ast.unparse(node.args[0]))
            dst = safe_eval(ast.unparse(node.args[1]))
            if isinstance(src, str):
                _record_IO(self.options, self.file_content,  "read_files",
                           src, node)
                return True
            if isinstance(dst, str):
                _record_IO(self.options, self.file_content, "write_files",
                           dst, node)
                return True
        return False

    def _process_os_open(self, node: ast.Call) -> bool:
        """Detect os.open(path, flags, [mode]) and record read/write based on flags."""
        if not (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr     == "open"
            and node.args
        ):
            return False
        # 2) Extract the filename literal
        filename = safe_eval(ast.unparse(node.args[0]))
        if not isinstance(filename, str):
            return False
        # 3) Parse the flags argument into (can_read, can_write)

        def _parse_flags(fn: ast.AST) -> tuple[bool, bool]:
            """Parse the flags AST node to determine read/write capabilities."""
            # base case: os.O_RDONLY, O_WRONLY, O_RDWR, O_CREAT, O_TRUNC, O_APPEND, O_EXCL
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "os":
                f = fn.attr
                if f == "O_RDONLY":
                    return (True, False)
                if f == "O_WRONLY":
                    return (False, True)
                if f == "O_RDWR":
                    return (True, True)
                if f in ("O_CREAT", "O_TRUNC", "O_APPEND", "O_EXCL"):
                    return (False, True)
            # recursive for bitwise ORs: os.O_CREAT | os.O_WRONLY, etc.
            if isinstance(fn, ast.BinOp) and isinstance(fn.op, ast.BitOr):
                left  = _parse_flags(fn.left)
                right = _parse_flags(fn.right)
                return (left[0] or right[0], left[1] or right[1])
            # anything else: assume both
            return (True, True)

        flags_node = node.args[1] if len(node.args) > 1 else None
        can_read, can_write = _parse_flags(flags_node) if flags_node else (True, False)
        # 4) Record into the right lists
        if can_read:
            _record_IO(self.options, self.file_content, "read_files",
                       filename, node)
            return True
        if can_write:
            _record_IO(self.options, self.file_content, "write_files",
                       filename, node)
            return True
        return False

    def _process_subprocess(self, node: ast.Call) -> bool:
        """
        Detect calls that invoke an external shell to read/write files via redirection:
        - subprocess.run()/Popen()/call()/check_output()/etc. with shell=True
        - os.system(), os.popen()

        Parses any ">", ">>" or "<" in the literal command string to pull out filenames.
        """
        # 1) Identify the call as subprocess.* or os.system/os.popen
        is_sub = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.func.attr in (
                "run", "Popen", "call",
                "check_output", "check_call",
                "getoutput", "getstatusoutput"
            )
        )
        is_os  = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr in ("system", "popen")
        )
        if not (is_sub or is_os):
            return False

        # 2) Extract the command string (only literal strings get caught)
        cmd = None
        # subprocess: only when shell=True will redirection fire
        if is_sub:
            shell_kw = next(
                (kw for kw in node.keywords
                if kw.arg == "shell"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, bool)
                and kw.value.value),
                None
            )
            if not shell_kw:
                return False
            # look for literal command in args or keywords
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                cmd = node.args[0].value
            else:
                for kw in node.keywords:
                    if kw.arg in ("args", "command") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        cmd = kw.value.value
                        break

        # os.system / os.popen always use a shell string
        if is_os:
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                cmd = node.args[0].value

        if not cmd:
            return False

        # 3) Scan the command for >, >>, and < redirections
        #    and record each filename we see
        for m in re.finditer(r'(?:^|\s)([<>]{1,2})\s*(\S+)', cmd):
            op, raw = m.groups()
            # strip any trailing shell punctuation
            filename = raw.rstrip(";|&")
            if not filename:
                continue
            attr = "write_files" if ">" in op else "read_files"
            _record_IO(self.options, self.file_content, attr,
                       filename, node)
            return True
        # If we reach here, no redirection was found
        return False

    def _process_ctypes_api(self, node: ast.Call) -> bool:
        """
        Detect direct libc open calls via ctypes (CDLL/pydll/...)
        and record the path literals passed to open/fopen as writes.
        """
        # 1) Must be an attribute call, e.g. (<something>).open(...)
        if not isinstance(node.func, ast.Attribute):
            return False

        # 2) The "something" must itself be a ctypes loader call:
        loader = node.func.value
        if not (
            isinstance(loader, ast.Call)
            and isinstance(loader.func, ast.Attribute)
            and isinstance(loader.func.value, ast.Name)
            and loader.func.value.id == "ctypes"
            and loader.func.attr in ("CDLL", "pydll", "windll", "oledll")
        ):
            return False

        # 3) We only care about open/fopen here (write‐only creation)
        fn = node.func.attr
        if fn not in ("open", "fopen"):
            return False

        # 4) Extract the filename literal from the first argument
        if not node.args:
            return False
        path_node = node.args[0]
        path = _literal_str(path_node)
        if not path:
            return False

        # 5) Record it as a write
        _record_IO(self.options, self.file_content, "write_files",
                   path, node)
        return True

    def _process_zipfile(self, node: ast.Call) -> bool:
        """Process zipfile.ZipFile(...) calls like extract, extractall, open."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        full_ctor = _get_full_attr_name(inner_call.func)
        if full_ctor is None or (full_ctor != "ZipFile" and not full_ctor.endswith("zipfile.ZipFile")):
            return False

        filename = get_evaluated_arg(inner_call.args[0])
        mode     = get_evaluated_arg(inner_call.args[1], default="r")
        if not isinstance(filename, str):
            return False

        if mode.startswith("r") and method in ("extract", "extractall", "open"):
            _record_IO(self.options, self.file_content, "read_files",
                       filename, node)
            return True
        elif mode.startswith(("w", "x", "a")):
            _record_IO(self.options, self.file_content, "write_files",
                       filename, node)
            return True
        return False

    def _process_tarfile(self, node: ast.Call) -> bool:
        """Process tarfile.open(...) calls like extract, extractall, open."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "tarfile"
                and node.func.attr     == "open"
                and node.args):
            filename = _literal_str(node.args[0])
            mode     = _literal_str(node.args[1]) if len(node.args) > 1 else "r"
            if filename:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               filename, node)
                    return True
                elif mode[0] in ("w", "a", "x"):
                    _record_IO(self.options, self.file_content, "write_files",
                               filename, node)
                    return True
        return False

    def _process_pandas(self, node: ast.Call) -> bool:
        """Process pandas.read_csv/excel, DataFrame.to_csv/excel calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("pd", "pandas")):
            fn = node.func.attr
            url = None
            if fn.startswith("read_") and node.args:
                url = _literal_str(node.args[0])
            elif fn.startswith("to_") and node.args:
                url = _literal_str(node.args[0])
            for kw in node.keywords:
                if kw.arg in ("filepath_or_buffer", "path", "path_or_buf"):
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                if fn.startswith("read_"):
                    _record_IO(self.options, self.file_content, "read_files",
                               url, node)
                    return True
                elif fn.startswith("to_"):
                    _record_IO(self.options, self.file_content, "write_files",
                               url, node)
                    return True
        return False

    def _process_numpy(self, node: ast.Call) -> bool:
        """Process numpy.load, save, savez, savez_compressed calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("np", "numpy")):
            fn = node.func.attr
            if fn in ("load",) and node.args:
                path = _literal_str(node.args[0])
                if path:
                    _record_IO(self.options, self.file_content, "read_files",
                               path, node)
            elif fn in ("save", "savez", "savez_compressed") and node.args:
                path = _literal_str(node.args[0])
                if path:
                    _record_IO(self.options, self.file_content, "write_files",
                               path, node)
                    return True
        return False

    def _process_netcdf4(self, node: ast.Call) -> bool:
        """Process netCDF4.Dataset(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "netCDF4"
                and node.func.attr == "Dataset"
                and node.args):
            filename = _literal_str(node.args[0])
            mode     = _literal_str(node.args[1]) if len(node.args) > 1 else "r"
            if filename:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               filename, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               filename, node)
                return True
        return False

    def _process_xarray(self, node: ast.Call) -> bool:
        """Process xarray.open_dataset/open_dataarray, to_netcdf calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("xr", "xarray")):
            fn = node.func.attr
            if fn in ("open_dataset", "open_dataarray") and node.args:
                path = _literal_str(node.args[0])
                if path:
                    _record_IO(self.options, self.file_content, "read_files",
                               path, node)
            elif fn == "to_netcdf" and node.args:
                path = _literal_str(node.args[0])
                for kw in node.keywords:
                    if kw.arg == "path":
                        maybe = _literal_str(kw.value)
                        if maybe:
                            path = maybe
                if path:
                    _record_IO(self.options, self.file_content, "write_files",
                               path, node)
                    return True
        return False

    def _process_json(self, node: ast.Call) -> bool:
        """Process json.load, loads, dump, dumps calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "json"
                and node.func.attr in ("load", "loads", "dump", "dumps")
                and node.args):
            target = _literal_str(node.args[0])
            if target:
                if node.func.attr.startswith("load"):
                    _record_IO(self.options, self.file_content, "read_files",
                               target, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               target, node)
                return True
        return False

    def _process_csv(self, node: ast.Call) -> bool:
        """Process csv.reader, writer calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "csv"
                and node.func.attr in ("reader", "writer")
                and node.args):
            target = _literal_str(node.args[0])
            if target:
                if node.func.attr == "reader":
                    _record_IO(self.options, self.file_content,  "read_files",
                               target, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               target, node)
                return True
        return False

    def _process_yaml(self, node: ast.Call) -> bool:
        """Process yaml.safe_load, load, dump calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("yaml", "ruamel.yaml")
                and node.func.attr in ("safe_load", "load", "dump")
                and node.args):
            target = _literal_str(node.args[-1])
            if target:
                if node.func.attr in ("safe_load", "load"):
                    _record_IO(self.options, self.file_content,  "read_files",
                               target, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               target, node)
                return True
        return False

    def _process_configparser(self, node: ast.Call) -> bool:
        """Process configparser.ConfigParser(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Call)
                and isinstance(node.func.value.func, ast.Attribute)
                and isinstance(node.func.value.func.value, ast.Name)
                and node.func.value.func.value.id == "configparser"
                and node.func.value.func.attr == "ConfigParser"):  # constructor
            mode_call = node.func.attr
            if mode_call == "read" and node.args:
                fp = _literal_str(node.args[0])
                if fp:
                    _record_IO(self.options, self.file_content, "read_files",
                               fp, node)
                    return True
            elif mode_call == "write" and node.args:
                fp = _literal_str(node.args[0])
                if fp:
                    _record_IO(self.options, self.file_content, "write_files",
                               fp, node)
                    return True
        return False

    def _process_h5py(self, node: ast.Call) -> bool:
        """Process h5py.File(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "h5py"
                and node.func.attr == "File"
                and node.args):
            fn = _literal_str(node.args[0])
            mode = _literal_str(node.args[1]) if len(node.args) > 1 else "r"
            if fn:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               fn, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               fn, node)
                return True
        return False

    def _process_pillow(self, node: ast.Call) -> bool:
        """Process PIL.Image.open, save calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "Image"):
            if node.func.attr == "open" and node.args:
                fp = _literal_str(node.args[0])
                if fp:
                    _record_IO(self.options, self.file_content, "read_files",
                               fp, node)
                    return True
            elif node.func.attr == "save" and node.args:
                fp = _literal_str(node.args[0])
                if fp:
                    _record_IO(self.options, self.file_content, "write_files",
                               fp, node)
                    return True
        return False

    def _process_wave(self, node: ast.Call) -> bool:
        """Process wave.open(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "wave"
                and node.func.attr == "open"
                and node.args):
            fn = _literal_str(node.args[0])
            mode = _literal_str(node.args[1]) if len(node.args) > 1 else "rb"
            if fn:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               fn, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               fn, node)
                return True
        return False

    def _process_soundfile(self, node: ast.Call) -> bool:
        """Process soundfile.read, write calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "soundfile"
                and node.func.attr in ("read", "write")
                and node.args):
            fn = _literal_str(node.args[0])
            if fn:
                if node.func.attr == "read":
                    _record_IO(self.options, self.file_content, "read_files",
                               fn, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               fn, node)
                return True
        return False

    def _process_sqlite(self, node: ast.Call) -> bool:
        """Process sqlite3.connect(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "sqlite3"
                and node.func.attr == "connect"
                and node.args):
            fn = _literal_str(node.args[0])
            if fn:
                _record_IO(self.options, self.file_content, "read_files",
                           fn, node)
                return True
        return False

    def _process_gzip(self, node: ast.Call) -> bool:
        """Process gzip.open(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "gzip"
                and node.func.attr == "open"
                and node.args):
            fn = _literal_str(node.args[0])
            mode = _literal_str(node.args[1]) if len(node.args) > 1 else "rb"
            if fn:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               fn, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               fn, node)
                return True
        return False

    def _process_bz2(self, node: ast.Call) -> bool:
        """Process bz2.open(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "bz2"
                and node.func.attr == "open"
                and node.args):
            fn = _literal_str(node.args[0])
            mode = _literal_str(node.args[1]) if len(node.args) > 1 else "rb"
            if fn:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               fn, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               fn, node)
                return True
        return False

    _KNOWN_OPEN_MODULES = {
        "open",       # built-in open (covered by _process_open)
        "pathlib",    # pathlib.Path.open
        "os",         # os.open
        "zipfile",    # zipfile.ZipFile()
        "tarfile",    # tarfile.open
        "gzip", "bz2"  # gzip.open, bz2.open
    }

    def _process_unknown_open(self, node: ast.Call) -> bool:
        """
        Heuristic catch-all for any MODULE.open(path, mode) calls
        on unknown modules that we haven't explicitly handled.
        """
        # 1) Must look like MODULE.open(...)
        if not (isinstance(node.func, ast.Attribute)
                and node.func.attr == "open"
                and node.args
                and isinstance(node.func.value, ast.Name)):
            return False

        mod = node.func.value.id
        # 2) Skip the ones we already handle
        if mod in self._KNOWN_OPEN_MODULES:
            return False

        # 3) Extract filename literal
        filename = _literal_str(node.args[0])
        if not filename:
            return False

        # 4) Extract mode literal if present
        mode = _literal_str(node.args[1]) if len(node.args) > 1 else None
        for kw in node.keywords:
            if kw.arg == "mode":
                maybe = _literal_str(kw.value)
                if maybe:
                    mode = maybe

        # 5) Default to "r", strip binary flag
        mode = (mode or "r").replace("b", "")

        # 6) Record
        if "r" in mode:
            _record_IO(self.options, self.file_content, "read_files",
                       filename, node)
            return True
        elif any(m in mode for m in ("w", "a", "x")):
            _record_IO(self.options, self.file_content, "write_files",
                       filename, node)
            return True
        return False

    def _process_generic_file(self, node: ast.Call) -> bool:
        """
        Heuristic fallback: if a function call takes a string literal
        that *looks* like a path, and the function name contains
        typical I/O verbs, record it.
        """
        # Must have at least one literal-string arg:
        if not node.args:
            return False
        candidate = _literal_str(node.args[0])
        if not candidate:
            return False

        # Check for path-like content:
        has_path_chars = any(sep in candidate for sep in ("/", "\\"))
        has_ext = "." in candidate and len(candidate.rsplit(".", 1)[-1]) <= 5
        if not (has_path_chars or has_ext):
            return False

        # Look for I/O-related function names:
        fn = None
        if isinstance(node.func, ast.Name):
            fn = node.func.id.casefold()
        elif isinstance(node.func, ast.Attribute):
            fn = node.func.attr.casefold()

        if fn and any(verb in fn for verb in ("open", "read", "write", "load", "save")):
            # If we see "read" or "load" in the name, treat it as read:
            mode = "read"       if any(fn.startswith(v) for v in ("read", "load")) else "write"
            attr = "read_files" if mode == "read"                                 else "write_files"
            _record_IO(self.options, self.file_content, attr,
                       candidate, node)
            return True
        return False


class TopLevelFileOperationsVisitor(FileOperationsVisitor):
    """
    Only look at calls at module scope — never descend into function defs.
    For classes, only inspect statements in the class body that are not defs or sub-classes.
    This is to avoid collecting file operations from within function bodies or class methods.
    """

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit FunctionDef nodes to find file operations. In practice,
        drop into nothing: stops recursion into function bodies"""
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit AsyncFunctionDef nodes to find file operations. In practice,
        drop into nothing: stops recursion into function bodies"""
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit ClassDef nodes to find file operations. In practice,
        only inspect statements in the class body that are not defs or sub-classes."""
        for stmt in node.body:
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(stmt)


class NetworkOperationsVisitor(ast.NodeVisitor):
    """Visitor to find network operations in the AST."""

    def __init__(self, options: Options, file_content: str) -> None:
        """Initialize the visitor with options and file content."""
        super().__init__()
        self.options = options
        self.file_content = file_content

    def visit_Call(self, node: ast.Call) -> None:
        """Visit Call nodes to find network operations."""
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("NetworkVisiting Call node: %s", ast.dump(node))
        if self._process_requests(       node): return
        if self._process_urllib(         node): return
        if self._process_ftp(            node): return
        if self._process_httpx(          node): return
        if self._process_aiohttp(        node): return
        if self._process_socket(         node): return
        if self._process_http_client(    node): return
        if self._process_urllib3(        node): return
        if self._process_smtplib(        node): return
        if self._process_imaplib(        node): return
        if self._process_boto3(          node): return
        if self._process_paramiko(       node): return
        if self._process_requests_ftp(   node): return
        if self._process_websockets(     node): return
        if self._process_socketio(       node): return
        if self._process_mqtt(           node): return
        if self._process_grpc(           node): return
        if self._process_psycopg2(       node): return
        if self._process_redis(          node): return
        # if self._process_generic_network(node): return  # Too many false positives!
        self.generic_visit(              node)  # Keep digging into the AST

    def _process_requests(self, node: ast.Call) -> bool:
        """Process requests.get/post/put/...(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.args  # protect against calls without arguments
                and node.func.value.id == "requests"
                and node.func.attr in ("get", "options", "head", "post",
                                    "put", "patch", "delete")):
            # Extract URL from arg[0] or keyword "url"
            url = _literal_str(node.args[0])
            for kw in node.keywords:
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                if node.func.attr == "get":
                    _record_IO(self.options, self.file_content, "download_urls",
                               url, node)
                else:
                    _record_IO(self.options, self.file_content,   "upload_urls",
                               url, node)
                return True
        return False

    def _process_urllib(self, node: ast.Call) -> bool:
        """Process urllib.request.urlopen(...) and urllib.request.Request(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and node.args  # protect against calls without arguments
                and isinstance(node.func.value, ast.Attribute)
                and node.func.attr in ("urlopen", "Request")):
            url = _literal_str(node.args[0])
            for kw in node.keywords:
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                _record_IO(self.options, self.file_content, "download_urls",
                           url, node)
                return True
        return False

    def _process_ftp(self, node: ast.Call) -> bool:
        """Process ftplib.FTP.retrbinary/storbinary/retrlines/storlines(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Call)
                and isinstance(node.func.value.func, ast.Attribute)
                and isinstance(node.func.value.func.value, ast.Name)
                and node.func.value.func.value.id == "ftplib"
                and node.func.value.func.attr == "FTP"
                and node.args):
            cmd = _literal_str(node.args[0])
            if not cmd:
                return False
            parts = cmd.split()
            if len(parts) < 2:
                return False
            filename = parts[1]
            op = node.func.attr.casefold()
            if op in ("retrbinary", "retrlines"):
                # remote-to-local: treat as read
                _record_IO(self.options, self.file_content,  "read_files",
                           filename, node)
                return True
            elif op in ("storbinary", "storlines"):
                # local-to-remote: treat as write
                _record_IO(self.options, self.file_content, "write_files",
                           filename, node)
                return True
        return False

    def _process_httpx(self, node: ast.Call) -> bool:
        """Process httpx.get/post/put/...(...) and httpx.request(method, url) calls."""
        # httpx.get/post/...() and httpx.request(method, url)
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "httpx"
                and node.func.attr in ("get", "options", "head", "post", "put", "patch", "delete")
                and node.args):
            url = _literal_str(node.args[0])
            for kw in node.keywords:
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                if node.func.attr == "get":
                    _record_IO(self.options, self.file_content, "download_urls",
                               url, node)
                else:
                    _record_IO(self.options, self.file_content,   "upload_urls",
                               url, node)
                return True
        # handle httpx.request(method, url)
        elif (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "httpx"
                and node.func.attr == "request"
                and node.args and len(node.args) >= 2):
            method = _literal_str(node.args[0])
            url = _literal_str(node.args[1])
            for kw in node.keywords:
                if kw.arg == "method":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        method = maybe
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                method = (method or "").casefold()
                if method == "get":
                    _record_IO(self.options, self.file_content, "download_urls",
                               url, node)
                else:
                    _record_IO(self.options, self.file_content,   "upload_urls",
                               url, node)
                return True
        return False

    def _process_aiohttp(self, node: ast.Call) -> bool:
        """Process aiohttp.request(...) and session.get/post/... calls."""
        # static aiohttp.request
        if (isinstance(node.func, ast.Name)
                and node.func.id == "request"
                and node.args and len(node.args) >= 2):
            method = _literal_str(node.args[0])
            url = _literal_str(node.args[1])
            for kw in node.keywords:
                if kw.arg == "method":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        method = maybe
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                method = (method or "").casefold()
                if method == "get":
                    _record_IO(self.options, self.file_content, "download_urls",
                               url, node)
                else:
                    _record_IO(self.options, self.file_content,   "upload_urls",
                               url, node)
                return True
        # session-based calls: session.get/post/etc.
        elif (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.attr in ("get", "options", "head", "post", "put", "patch", "delete")
                and node.args):
            # e.g. session.get(url)
            url = _literal_str(node.args[0])
            for kw in node.keywords:
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                if node.func.attr == "get":
                    _record_IO(self.options, self.file_content, "download_urls",
                               url, node)
                else:
                    _record_IO(self.options, self.file_content,   "upload_urls",
                               url, node)
                return True
        return False

    def _process_socket(self, node: ast.Call) -> bool:
        """Process socket operations like create_connection, connect, send, recv."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "socket"
                and node.func.attr in ("create_connection", "connect", "send", "recv")
                and node.args):
            # for connect/create_connection, the first arg is (host, port)
            snippet = ast.get_source_segment(self.file_content, node) or ""
            _record_IO(self.options, self.file_content, "download_urls"
                       if node.func.attr in ("recv",) else "upload_urls",
                       snippet.strip(), node)
            return True
        return False

    def _process_http_client(self, node: ast.Call) -> bool:
        """Process http.client HTTPConnection().request calls."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method_name = unpacked

        full_name = _get_full_attr_name(inner_call.func)
        if full_name is None or not (
            full_name == "HTTPConnection"
            or full_name.endswith(".HTTPConnection")
        ):
            return False

        if method_name != "request" or len(inner_call.args) < 2:
            return False

        method = _literal_str(inner_call.args[0]) or ""
        url = _literal_str(inner_call.args[1]) or ""
        kind = "download_urls" if method.casefold() == "get" else "upload_urls"
        _record_IO(self.options, self.file_content, kind,
                   url, node)
        return True

    def _process_urllib3(self, node: ast.Call) -> bool:
        """Process urllib3 requests (PoolManager().request)."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method_name = unpacked

        full_name = _get_full_attr_name(inner_call.func)
        # must be exactly "PoolManager" or end with ".PoolManager"
        if full_name is None or not (
            full_name == "PoolManager"
            or full_name.endswith(".PoolManager")
        ):
            return False

        if method_name != "request" or len(inner_call.args) < 2:
            return False

        method = _literal_str(inner_call.args[0]) or ""
        url = _literal_str(inner_call.args[1]) or ""
        kind = "download_urls" if method.casefold() == "get" else "upload_urls"
        _record_IO(self.options, self.file_content, kind,
                   url, node)
        return True

    def _process_smtplib(self, node: ast.Call) -> bool:
        """Process smtplib SMTP.sendmail calls."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        # Match the constructor
        ctor = inner_call.func
        full_name = _get_full_attr_name(ctor)
        if full_name is None or not (
            full_name == "SMTP"
            or full_name.endswith("smtplib.SMTP")
        ):
            return False

        # Only sendmail + ≥3 args
        if method != "sendmail" or len(inner_call.args) < 3:
            return False

        to_addrs = ast.get_source_segment(self.file_content, inner_call.args[1]) or ""
        _record_IO(self.options, self.file_content, "upload_urls",
                   to_addrs, node)
        return True

    def _process_imaplib(self, node: ast.Call) -> bool:
        """Process imaplib operations (IMAP4/IMAP4_SSL().fetch/login/select)."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        full_name = _get_full_attr_name(inner_call.func)
        if full_name is None or not (
            full_name in ("IMAP4", "IMAP4_SSL")
            or full_name.endswith(".IMAP4")
            or full_name.endswith(".IMAP4_SSL")
        ):
            return False

        if method not in ("fetch", "login", "select") or not inner_call.args:
            return False

        snippet = ast.get_source_segment(self.file_content, inner_call.args[0]) or ""
        _record_IO(self.options, self.file_content, "download_urls",
                   snippet, node)
        return True

    def _process_boto3(self, node: ast.Call) -> bool:
        """Process boto3 S3 operations (...client().download_file/upload_file)."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        full_name = _get_full_attr_name(inner_call.func)
        # must be exactly "client" or end with ".client"
        if full_name is None or not (
            full_name == "client"
            or full_name.endswith(".client")
        ):
            return False

        if method not in ("download_file", "upload_file") or len(inner_call.args) < 3:
            return False

        fn = _literal_str(inner_call.args[2])
        if not fn:
            return False

        kind = "download_urls" if method == "download_file" else "upload_urls"
        _record_IO(self.options, self.file_content, kind,
                   fn, node)
        return True

    def _process_paramiko(self, node: ast.Call) -> bool:
        """Process paramiko SFTP operations (...open_sftp().get/put...)."""
        # 1) unpack the method call
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        # 2) match the constructor name
        full_name = _get_full_attr_name(inner_call.func)
        if full_name is None or not (
            full_name == "open_sftp"
            or full_name.endswith(".open_sftp")
        ):
            return False

        # 3) only handle .get or .put
        if method not in ("get", "put"):
            return False

        # 4) extract the local filename argument
        local = get_evaluated_arg(inner_call.args[1] if method == "get" else inner_call.args[0])
        if not local:
            return False

        # 5) record I/O
        kind = "download_urls" if method == "get" else "upload_urls"
        _record_IO(self.options, self.file_content, kind,
                   local, node)
        return True

    def _process_requests_ftp(self, node: ast.Call) -> bool:
        """Process requests_ftp operations."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "requests_ftp"
            and node.func.attr in ("get", "post", "put", "delete")
            and node.args
        ):
            url = _literal_str(node.args[0])
            if url:
                kind = "download_urls" if node.func.attr == "get" else "upload_urls"
                _record_IO(self.options, self.file_content, kind,
                           url, node)
                return True
        return False

    def _process_websockets(self, node: ast.Call) -> bool:
        """Process websockets.connect(...) calls."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "websockets"
            and node.func.attr == "connect"
            and node.args
        ):
            url = _literal_str(node.args[0])
            if url:
                _record_IO(self.options, self.file_content, "download_urls",
                           url, node)
                return True
        return False

    def _process_socketio(self, node: ast.Call) -> bool:
        """Process socketio.Client().connect(...) or emit(...) calls."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        full_name = _get_full_attr_name(inner_call.func)
        if full_name is None or not (
            full_name == "Client"
            or full_name.endswith(".Client")
        ):
            return False

        if method not in ("connect", "emit") or not inner_call.args:
            return False

        target = _literal_str(inner_call.args[0])
        if not target:
            return False

        kind = "download_urls" if method == "connect" else "upload_urls"
        _record_IO(self.options, self.file_content, kind,
                   target, node)
        return True

    def _process_mqtt(self, node: ast.Call) -> bool:
        """Process paho.mqtt.client.Client().connect(...) calls."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Attribute)
            and node.func.value.func.attr == "Client"
            and node.func.attr in ("connect", "publish", "subscribe")
            and node.args
        ):
            # first arg for connect is host, for others topic
            target = _literal_str(node.args[0])
            if target:
                kind = "download_urls" if node.func.attr == "subscribe" else "upload_urls"
                _record_IO(self.options, self.file_content, kind,
                           target, node)
                return True
        return False

    def _process_grpc(self, node: ast.Call) -> bool:
        """Process grpc.insecure_channel(...) or grpc.secure_channel(...) calls."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "grpc"
            and node.func.attr in ("insecure_channel", "secure_channel")
            and node.args
        ):
            target = _literal_str(node.args[0])
            if target:
                _record_IO(self.options, self.file_content, "download_urls",
                           target, node)
                return True
        return False

    def _process_psycopg2(self, node: ast.Call) -> bool:
        """Process psycopg2.connect(...) calls."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "psycopg2"
            and node.func.attr == "connect"
            and node.args
        ):
            target = _literal_str(node.args[0])
            if target:
                _record_IO(self.options, self.file_content, "download_urls",
                           target, node)
                return True
        return False

    def _process_redis(self, node: ast.Call) -> bool:
        """Process redis.Redis(...) calls."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "redis"
            and node.func.attr == "Redis"
        ):
            # look for host kwarg
            host = None
            for kw in node.keywords:
                if kw.arg == "host":
                    host = _literal_str(kw.value)
            if host:
                _record_IO(self.options, self.file_content, "download_urls",
                           host, node)
                return True
        return False

    def _process_generic_network(self, node: ast.Call) -> bool:
        """
        Heuristic fallback: if a call's first argument is a string literal
        that looks like a URL (http:// or https://), record it.
        """
        if not node.args:
            return False
        candidate = _literal_str(node.args[0])
        if not candidate:
            return False

        # Simple URL check:
        if candidate.startswith(("http://", "https://", "ftp://")):
            # If the function name starts with "get", assume download:
            fn = node.func.attr.casefold() if isinstance(node.func, ast.Attribute) else ""
            kind = "download_urls" if fn.startswith("get") else "upload_urls"
            _record_IO(self.options, self.file_content, kind,
                       candidate, node)
            return True
        return False


class TopLevelNetworkOperationsVisitor(NetworkOperationsVisitor):
    """
    Only look at calls at module scope — never descend into function defs.
    For classes, only inspect statements in the class body that are not defs or sub-classes.
    This is to avoid collecting network operations from within function bodies or class methods.
    """

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit FunctionDef nodes to find file operations. In practice,
        drop into nothing: stops recursion into function bodies."""
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit AsyncFunctionDef nodes to find file operations. In practice,
        drop into nothing: stops recursion into function bodies."""
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit ClassDef nodes to find file operations. In practice,
        only inspect statements in the class body that are not defs or sub-classes."""
        for stmt in node.body:
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(stmt)


# ---- pathlib class sets ----
PATHLIB_CONCRETE = {"Path", "PosixPath", "WindowsPath"}
PATHLIB_PURE     = {"PurePath", "PurePosixPath", "PureWindowsPath"}
PATHLIB_ALL      = PATHLIB_CONCRETE | PATHLIB_PURE


def collect_pathlib_aliases(module: ast.Module) -> set[str]:
    """
    Return the set of local names that refer to pathlib classes (Path/PosixPath/WindowsPath and Pure*).
    Handles aliasing via 'as'.
    Works even if imports are nested; we just scan the whole tree.
    """
    aliases: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
            for alias in node.names:
                if alias.name in PATHLIB_ALL:
                    aliases.add(alias.asname or alias.name)
    return aliases


def is_pathlib_ctor(fn: ast.AST, pathlib_aliases: set[str], allow_pure: bool) -> bool:
    """
    True if 'fn' is a constructor for a pathlib *Path* type.
    - When allow_pure=False, only concrete (filesystem) paths are allowed.
    - When allow_pure=True, accept both concrete and pure paths.
    """
    allowed = PATHLIB_CONCRETE | (PATHLIB_PURE if allow_pure else set())

    # Case: Name (possibly aliased import) e.g., Path(...), P(...), PurePath(...)
    if isinstance(fn, ast.Name):
        if fn.id in allowed or fn.id in pathlib_aliases:
            return True

    # Case: attribute like pathlib.Path(...), pathlib.PurePath(...)
    if (
        isinstance(fn, ast.Attribute)
        and isinstance(fn.value, ast.Name)
        and fn.value.id == "pathlib"
        and fn.attr in allowed
    ):
        return True

    return False


def transform_call(node: ast.Call, pathlib_aliases: set[str]) -> str | None:
    """
    Return a replacement string if this call matches one of our handled patterns,
    or None to leave it unchanged.
    """

    # Handle: pathlib.Path(...).resolve()/absolute()
    if isinstance(node.func, ast.Attribute) and node.func.attr in {"resolve", "absolute"}:
        func = node.func
        if isinstance(func.value, ast.Call):
            inner = func.value
            if is_pathlib_ctor(inner.func, pathlib_aliases, allow_pure=False) and len(inner.args) == 1:
                arg = _safe_eval_node(inner.args[0], pathlib_aliases=pathlib_aliases)
                if isinstance(arg, str):
                    # Recompute using canonical 'Path' and same method name
                    return str(getattr(Path(arg), func.attr)())

    # Handle: pathlib.Path(...).joinpath(...)
    if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
        func = node.func
        if isinstance(func.value, ast.Call):
            inner = func.value
            if is_pathlib_ctor(inner.func, pathlib_aliases, allow_pure=True) and len(inner.args) == 1:
                base  =  _safe_eval_node(inner.args[0], pathlib_aliases=pathlib_aliases)
                parts = [_safe_eval_node(a,             pathlib_aliases=pathlib_aliases) for a in node.args]
                if isinstance(base, str) and all(isinstance(p, str) for p in parts):
                    return os.fspath(Path(base).joinpath(*parts))

    return None


def _safe_eval_node(node: ast.AST, pathlib_aliases: set[str] | None = None) -> Any:
    """
    Recursively evaluate a restricted subset of AST nodes:
    - Constants (strings, numbers, booleans, None)
    - Lists, tuples, dicts
    - os.getcwd()
    - os.path.(abspath|join|dirname|realpath)(<literal strings>)
    - pathlib.Path(<literal strings>).(resolve|absolute)() and .joinpath(<literal strings>...)
    - The "/" operator for joining pathlib Paths.

    Args:
        node:            The AST node to evaluate.
        pathlib_aliases: Optional set of local names that refer to pathlib classes.
    
    Returns:
        The evaluated Python object.
    
    Raises:
        ValueError: If the node contains unsupported syntax.
    """
    aliases = pathlib_aliases or set()
    # --- support "/" operator for path-like objects ---
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left  = _safe_eval_node(node.left, pathlib_aliases=aliases)
        right = _safe_eval_node(node.right, pathlib_aliases=aliases)
        # accept strings or any PathLike (Path, etc.)
        if isinstance(left, (str, os.PathLike)) and isinstance(right, (str, os.PathLike)):
            # Path(left) / right → Path; str(...) to get the string path
            return os.fspath(Path(left) / right)
        raise ValueError(f"Unsupported path division: {ast.unparse(node)}")

    # --- literals ---
    if isinstance(node, ast.Constant):
        # Python 3.8+: Constant covers str, int, float, bool, None
        return node.value

    # --- composite literals ---
    if isinstance(node, ast.List):
        return [_safe_eval_node(elt, pathlib_aliases=aliases) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_safe_eval_node(elt, pathlib_aliases=aliases) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _safe_eval_node(k, pathlib_aliases=aliases): _safe_eval_node(v, pathlib_aliases=aliases)
            for k, v in zip(node.keys, node.values)
        }

    # --- calls ---
    if isinstance(node, ast.Call):
        func = node.func

        # os.getcwd()
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and func.attr == "getcwd"
            and len(node.args) == 0
        ):
            return os.getcwd()

        # os.path.* calls
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "path"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "os"
        ):
            method = func.attr
            allowed = {"abspath", "join", "dirname", "realpath"}
            if method in allowed:
                arg_vals = [_safe_eval_node(arg, pathlib_aliases=aliases) for arg in node.args]
                if all(isinstance(v, str) for v in arg_vals):
                    path_fn = getattr(os.path, method)
                    return path_fn(*arg_vals)

        # pathlib.Path(...).resolve()/absolute()
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"resolve", "absolute"}:
            func = node.func
            if isinstance(func.value, ast.Call):
                inner = func.value
                if is_pathlib_ctor(inner.func, aliases, allow_pure=False) and len(inner.args) == 1:
                    arg = _safe_eval_node(inner.args[0], pathlib_aliases=aliases)
                    if isinstance(arg, str):
                        # Recompute using canonical 'Path' and same method name
                        return os.fspath(getattr(Path(arg), func.attr)())

        # pathlib.Path(...).joinpath(...)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
            func = node.func
            if isinstance(func.value, ast.Call):
                inner = func.value
                if is_pathlib_ctor(inner.func, aliases, allow_pure=True) and len(inner.args) == 1:
                    base  =  _safe_eval_node(inner.args[0], pathlib_aliases=aliases)
                    parts = [_safe_eval_node(a,             pathlib_aliases=aliases) for a in node.args]
                    if isinstance(base, str) and all(isinstance(p, str) for p in parts):
                        return os.fspath(Path(base).joinpath(*parts))

        # unsupported call
        raise ValueError(f"Unsupported call: {ast.unparse(node)}")

    # anything else is disallowed
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def safe_eval(expr: str, pathlib_aliases: set[str] | None = None) -> Any | None:
    """
    Safely evaluate a Python expression string containing only:
        - literals (str, int, float, bool, None)
        - lists, tuples, dicts of the above
        - os.getcwd()
        - os.path.(abspath|join|dirname|realpath)(<literal strings>)
        - pathlib.Path(<literal strings>).(resolve|absolute)() and
          .joinpath(<literal strings>...) and the "/" operator for joining paths.
        - The "/" operator for joining pathlib Paths.

    Args:
        expr:            The expression string to evaluate.
        pathlib_aliases: Optional set of local names that refer to pathlib classes.

    Returns:
        The evaluated Python object, or None on unsupported syntax.

    Raises:
        None: All errors are caught and None is returned.
    """
    try:
        # Parse in "eval" mode so we get an Expression node
        tree = ast.parse(expr, mode="eval")
        return _safe_eval_node(tree.body, pathlib_aliases=pathlib_aliases)  # tree.body is the root expr
    except (SyntaxError, ValueError) as e:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("%s: Unsupported expression: %r: %s", ek.return_method_name(), expr, e)
        return None


class SysPathVisitor(ast.NodeVisitor):
    """Visitor class to extract sys.path modifications."""

    def __init__(self, pathlib_aliases: set[str] | None = None) -> None:
        """Initialize the sys.path visitor."""
        self.paths = set()
        self._aliases = pathlib_aliases or set()

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit an assignment statement and check if it's modifying sys.path."""
        if node.targets and isinstance(node.targets[0], ast.Attribute) and \
        isinstance(node.targets[0].value, ast.Name) and \
        node.targets[0].value.id == "sys" and \
        node.targets[0].attr     == "path":
            paths = safe_eval(ast.unparse(node.value), pathlib_aliases=self._aliases)
            if isinstance(paths, list):
                for path in paths:
                    self.paths.add(path)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Visit a function call and check if it's modifying sys.path."""
        if isinstance(node.func,             ast.Attribute) and \
           isinstance(node.func.value,       ast.Attribute) and \
           isinstance(node.func.value.value, ast.Name     ) and \
           node.func.value.value.id == "sys" and \
           node.func.value.attr == "path" and \
           node.func.attr in {"append", "insert"}:
            if node.args and (path := safe_eval(ast.unparse(node.args[-1]), pathlib_aliases=self._aliases)):
                self.paths.add(path)
        self.generic_visit(node)


def process_import(options: Options, module_name: str, file_path: str | os.PathLike[str]) -> bool:
    """Process an import by checking if it's a local custom module or a standard import, and handle it accordingly."""
    if module_name in options.stdlib:
        options.seen_stdlib_imports.add(module_name)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Skipping standard library import: %s", module_name)
        return False

    file_path = ek.ensure_file(file_path)

    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Processing import: %s from file %s", module_name, file_path)

    base_dir        = file_path.parent
    module_path_str = module_name.replace(".", os.sep)

    # Avoid loopback to the same file
    if module_name == file_path.stem:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Avoiding loopback to the same file: %s", module_name)
        return False
    if module_name == "pipreqs" and f"{options.my_name}.py" in str(file_path):
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Avoiding loopback to pipreqs in %s.py", options.my_name)
        return False
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Constructed module path: %s", module_path_str)

    # Check if the import is a .py file in the same directory
    potential_file_path = (base_dir / f"{module_path_str}.py").expanduser().resolve()
    if ek.safe_is_file(potential_file_path) and potential_file_path not in options.samedir_files:
        options.custom_modules[module_name] = potential_file_path
        options.loaded_custom_modules.add(module_name)
        options.samedir_files.append(potential_file_path)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Added same directory file: %s", potential_file_path)
        return True

    # Check if the import is a package (directory with __init__.py)
    potential_dir_path = (base_dir / module_path_str).expanduser().resolve()
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Constructed potential directory path: %s", potential_dir_path)
    if ek.safe_is_dir(potential_dir_path) and ek.safe_is_file(potential_dir_path / "__init__.py") and module_path_str not in options.subfolders:
        options.custom_modules[module_name] = potential_dir_path
        options.loaded_custom_modules.add(module_name)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Resolved local package to: %s", potential_dir_path)
        options.subfolders.append(module_path_str)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Added subfolder: %s", module_path_str)
        return True

    # Check if this module is in the custom_modules dictionary.
    if module_name in options.custom_modules:
        module_file = options.custom_modules[module_name]
        if module_name not in options.loaded_custom_modules:
            options.loaded_custom_modules.add(module_name)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Resolved via custom_modules: %s → %s", module_name, module_file)
        return True

    # --- fall back to sys.path hints (folders added at runtime) ---
    for root in getattr(options, "sys_path_hints", set()):
        # Look for a single-file module
        candidate = (root / f"{module_path_str}.py").expanduser().resolve()
        if ek.safe_is_file(candidate):
            options.custom_modules[module_name] = candidate
            options.loaded_custom_modules.add(module_name)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Resolved via sys.path hint (file): %s → %s", module_name, candidate)
            return True

        # Look for a package dir with __init__.py
        pkg = (root / module_path_str).expanduser().resolve()
        if ek.safe_is_dir(pkg) and ek.safe_is_file(pkg / "__init__.py"):
            options.custom_modules[module_name] = pkg
            options.loaded_custom_modules.add(module_name)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Resolved via sys.path hint (package): %s → %s", module_name, pkg)
            return True

    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Could not resolve local import, treating as external: %s", module_name)
    return False


class FunctionInfo:
    """Class to hold information about a function."""

    def __init__(self, function_name: str, node: ast.FunctionDef) -> None:
        """Initialize the function information, storing its AST node too."""
        self.function_name:            str = function_name
        self.ast_node:     ast.FunctionDef = node
        self.imports_in_function: set[str] = set()
        self.function_calls:      set[str] = set()


class ModuleInfo:
    """Class to hold information about a module."""

    def __init__(self, module_name: str) -> None:
        """Initialize the module information."""
        self.module_name:                   str = module_name
        self.top_level_imports:        set[str] = set()
        self.functions: dict[str, FunctionInfo] = {}
        self.top_level_calls:          set[str] = set()
        self.aliases:            dict[str, str] = {}
        self.classes:                  set[str] = set()
        self.base_classes: dict[str, list[str]] = {}


class ImportFunctionCollector(ast.NodeVisitor):
    """Visitor class to collect function and import information from a module."""

    def __init__(self, options: Options, module_name: str,
                 file_path: str | os.PathLike[str]) -> None:
        """Initialize the import function collector."""
        self.module_info:                      ModuleInfo = ModuleInfo(module_name)
        self.current_function:                 str | None = None
        self.current_class:                    str | None = None
        self.aliases:                      dict[str, str] = {}
        self.options:                             Options = options
        self.file_path:                              Path = ek.ensure_path(file_path)
        self.base_classes:           dict[str, list[str]] = {}
        self.attr_types: defaultdict[str, dict[str, str]] = defaultdict(dict)  # {class_name: {attr_name: "QualifiedTypeName"}}
        self._param_types:                 dict[str, str] = {}  # param name -> "QualifiedTypeName"

    def visit_Import(self, node: ast.Import) -> None:
        """Visit an import statement and add the imported module to the module's list of imports."""
        for alias in node.names:
            name               = alias.asname or alias.name
            full_name          = alias.name
            top_level_package  = full_name.split(".")[0]
            self.aliases[name] = full_name
            if self.current_function:
                self.module_info.functions[self.current_function].imports_in_function.add(top_level_package)
            else:
                self.module_info.top_level_imports.add(top_level_package)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit an import from statement and add the imported module to the module's list of imports."""
        module = node.module or ""
        # Extract the top-level package
        top_level_package = module.split(".")[0] if module else ""
        for alias in node.names:
            full_name = f"{module}.{alias.name}" if module else alias.name
            name = alias.asname or alias.name
            self.aliases[name] = full_name
            if self.current_function:
                self.module_info.functions[self.current_function].imports_in_function.add(top_level_package)
            else:
                self.module_info.top_level_imports.add(top_level_package)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit a function definition and add it to the module's list of functions."""
        func_name = node.name
        if self.current_class:
            func_name = f"{self.current_class}.{func_name}"
        self.module_info.functions[func_name] = FunctionInfo(func_name, node)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Added function: %s to module %s", func_name, self.module_info.module_name)
        prev_function         = self.current_function
        self.current_function = func_name
        # Track parameter annotations (only while inside this function)
        self._param_types = {}
        for a in node.args.args:
            if a.annotation is not None:
                t = self._type_name(a.annotation)
                if t:
                    self._param_types[a.arg] = t
        self.generic_visit(node)
        self.current_function = prev_function
        self._param_types = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class definition and set the current class."""
        self.module_info.classes.add(node.name)
        prev_class = self.current_class
        self.current_class = node.name

        # Record base classes before visiting the body
        base_class_names = []
        for base in node.bases:
            base_name = self.get_full_name(base)
            if base_name:
                parts = base_name.split(".")
                if parts and parts[0] in self.aliases:
                    alias_target = self.aliases[parts[0]]
                    base_name = alias_target + "." + ".".join(parts[1:])
                base_class_names.append(base_name)
        self.base_classes[node.name] = base_class_names
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Recorded base classes for %s: %s", node.name, self.base_classes[node.name])
        # Now that base_classes is set, visit the class body
        self.generic_visit(node)
        self.current_class = prev_class

    def _qual(self, tail: str) -> str:
        """Prepend the current module name + '_SEP' to the input string."""
        return f"{self.module_info.module_name}{_SEP}{tail}"

    def extract_module_name_from_import(self, node: ast.Call) -> str | None:
        """Extract the module name from a dynamic import using __import__."""
        if node.args:
            module_arg = node.args[0]
            if isinstance(module_arg, ast.Constant) and isinstance(module_arg.value, str):
                module_name = module_arg.value.split(".")[0]  # Get top-level package
                return module_name
            else:
                # Handle cases where module name cannot be resolved
                logging.error(f"Cannot resolve dynamic import with non-constant module name: {ast.unparse(node)}")
                return None
        else:
            logging.error(f"No arguments provided to __import__(): {ast.unparse(node)}")
            return None

    def _record_call(self, qualified: str) -> None:
        """Record a function call, either in the current function or at the top level."""
        if self.current_function:
            self.module_info.functions[self.current_function].function_calls.add(qualified)
        else:
            self.module_info.top_level_calls.add(qualified)

    def _maybe_alias(self, name: str) -> str:
        """Replace the first part of 'name' with its alias if it exists."""
        parts = name.split(".")
        if parts and parts[0] in self.aliases:
            parts[0] = self.aliases[parts[0]]
        return ".".join(parts)

    def _maybe_record_func_ref(self, node: ast.AST) -> None:
        """If 'node' looks like a reference to a function, record it as a call."""
        ref = self.get_full_name(node)
        if not ref:
            return
        # Case 1: plain name referring to a function defined in this module
        if "." not in ref and ref in self.module_info.functions:
            self._record_call(ref)
            return
        # Case 2: class defined here passed as a constructor -> treat as __init__
        if "." not in ref and ref in self.module_info.classes:
            self._record_call(self._qual(f"{ref}.__init__"))
            return
        # Case 3: qualified like other_module.func
        if "." in ref:
            qualified = self._maybe_alias(ref)
            self._record_call(qualified)
            return

    def visit_Call(self, node: ast.Call) -> None:
        """Visit a function call and add it to the function's list of calls."""
        func_name = self.get_full_name(node.func)
        original_func_name = func_name
        # Resolve self.<attr>.<method> to the attribute's type
        if func_name and self.current_class:
            parts = func_name.split(".")
            # Pattern: CurrentClass.<attr>.<method>[.<more>]
            if len(parts) >= 3 and parts[0] == self.current_class:
                attr = parts[1]
                method_tail = ".".join(parts[2:])
                t = self.attr_types.get(self.current_class, {}).get(attr)
                if t:
                    # Qualify local classes with the current module
                    if t in self.module_info.classes:
                        func_name = self._qual(f"{t}.{method_tail}")
                    else:
                        # t might already be qualified by an alias (e.g., "ek.LLMs")
                        func_name = f"{t}.{method_tail}"
        if func_name:
            parts = func_name.split(".")
            if parts[0] in self.module_info.classes:
                # It's a class from this module
                if func_name in self.module_info.classes:
                    # func_name is exactly the class name, treat as constructor
                    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("%s is identified as a class. Converting to __init__ call.", func_name)
                    func_name = self._qual(f"{func_name}.__init__")
                else:
                    # It's a method/attribute call on a class from this module
                    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("%s is a method/attribute on a class from the same module. Qualifying with module name.", func_name)
                    func_name = self._qual(func_name)
            else:
                if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("%s is not a class, leaving as-is.", func_name)
            # If func_name corresponds to a class in this module, treat it as calling __init__
            if func_name in self.module_info.classes:
                func_name = f"{func_name}.__init__"
            # Handle dynamic imports
            if func_name == "__import__":
                module_name = self.extract_module_name_from_import(node)
                if module_name:
                    if self.current_function:
                        self.module_info.functions[self.current_function].imports_in_function.add(module_name)
                    else:
                        self.module_info.top_level_imports.add(module_name)
                else:
                    logging.warning("Cannot resolve dynamic import: %s", ast.unparse(node))
            # Handle importlib.import_module(...)
            elif func_name == "importlib.import_module":
                abs_name = self.extract_module_name_from_importlib_import_module(node)
                if abs_name:
                    self._register_import_name(abs_name)
                else:
                    logging.warning("Cannot resolve importlib.import_module call: %s", ast.unparse(node))
            # Handle importlib.util.spec_from_file_location(...)
            elif func_name == "importlib.util.spec_from_file_location":
                res = self.extract_from_importlib_spec_from_file_location(node)
                if res:
                    mod, loc = res
                    self._register_import_name(mod)
                    if loc:
                        self._register_constant_path_for_module(mod, loc)
            # Handle importlib.machinery.SourceFileLoader(...).load_module()
            # We match either the constructor itself or the chained .load_module():
            elif func_name == "importlib.machinery.SourceFileLoader":
                res = self.extract_from_importlib_sourcefileloader(node)
                if res:
                    mod, loc = res
                    self._register_import_name(mod)
                    if loc:
                        self._register_constant_path_for_module(mod, loc)
            # Also catch the chained call: importlib.machinery.SourceFileLoader(...).load_module()
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "load_module":
                # node.func.value should be the Call to SourceFileLoader(...)
                loader_call = node.func.value
                if isinstance(loader_call, ast.Call):
                    callee = self.get_full_name(loader_call.func)
                    if callee == "importlib.machinery.SourceFileLoader":
                        res = self.extract_from_importlib_sourcefileloader(loader_call)
                        if res:
                            mod, loc = res
                            self._register_import_name(mod)
                            if loc:
                                self._register_constant_path_for_module(mod, loc)
                        else:
                            logging.warning("Cannot resolve SourceFileLoader(...).load_module() call: %s", ast.unparse(node))
            elif func_name.startswith("super."):
                # Handle super calls
                _, method_name = func_name.split(".", 1)
                if self.current_class and self.current_class in self.base_classes:
                    base_classes = self.base_classes[self.current_class]
                    if base_classes:
                        base_class = base_classes[0]  # Assuming single inheritance
                        func_name = f"{base_class}.{method_name}"
                self._record_call(func_name)
            else:
                # Normal calls
                self._record_call(func_name)
        for a in node.args:
            self._maybe_record_func_ref(a)
        for kw in node.keywords:
            if kw.value is not None:
                self._maybe_record_func_ref(kw.value)
        self.generic_visit(node)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Call found: original func_name=%s, resolved func_name=%s", original_func_name, func_name)
        if self.current_function:
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Adding function call %s to %s", func_name, self.current_function)
        else:
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Adding top-level call: %s", func_name)

    def get_full_name(self, node: ast.AST) -> str | None:
        """Get the full name of a node, including any aliases."""
        if isinstance(node, ast.Name):  # Handle variable names
            if node.id in ("self", "cls"):  # Handle class methods
                if self.current_class:
                    return self.current_class
                else:
                    return node.id
            elif node.id == "super":  # Handle super() calls
                return "super"
            else:
                return self.aliases.get(node.id, node.id)
        elif isinstance(node, ast.Attribute):  # Handle attribute access
            value = self.get_full_name(node.value)
            return f"{value}.{node.attr}" if value else node.attr
        elif isinstance(node, ast.Call):  # Handle super() calls
            func_name = self.get_full_name(node.func)
            return func_name
        return None

    def _type_name(self, node: ast.AST) -> str | None:
        """
        Extract a string type name from an annotation or qualified name.
        Handles Name or Attribute, using aliases when needed.
        """
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self._type_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """
        Visit an annotated assignment and record attribute types.
        e.g. self.options: Options = options
        """
        if (
            self.current_class and
            isinstance(node.target, ast.Attribute) and
            isinstance(node.target.value, ast.Name) and
            node.target.value.id == "self"
        ):
            t = self._type_name(node.annotation)
            if t:
                self.attr_types[self.current_class][node.target.attr] = t
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """
        Visit an assignment and try to infer attribute types from RHS.
        e.g. self.options = options   (infer type from param annotation if possible)
        """
        for tgt in node.targets:
            if (
                self.current_class and
                isinstance(tgt, ast.Attribute) and
                isinstance(tgt.value, ast.Name) and
                tgt.value.id == "self"
            ):
                # Try to infer type from RHS if RHS is a Name that matches a typed param
                if isinstance(node.value, ast.Name):
                    pname = node.value.id
                    t = self._param_types.get(pname)
                    if t:
                        self.attr_types[self.current_class][tgt.attr] = t
        self.generic_visit(node)

    # --- Importlib helpers -------------------------------------------------

    def _const_str(self, node: ast.AST) -> str | None:
        """Return node.value if the node is a constant string; else None."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _resolve_relative_module(self, name: str, package: str | None) -> str | None:
        """
        Resolve 'name' that may start with dots against an absolute 'package'.
        Mirrors importlib semantics roughly; for our purposes we only need to
        resolve to a package string to feed the rest of the pipeline.
        """
        if not name:
            return None
        if not name.startswith("."):
            return name  # already absolute
        if not package:
            return None  # cannot resolve without a package
        # Count leading dots
        i = 0
        while i < len(name) and name[i] == ".":
            i += 1
        # Climb up 'i-1' levels from package
        pkg_parts = package.split(".")
        if i - 1 > len(pkg_parts):
            return None
        base = ".".join(pkg_parts[: len(pkg_parts) - (i - 1)])
        tail = name[i:]
        return f"{base}.{tail}" if tail else base

    def _register_import_name(self, module_name: str) -> None:
        """
        Record an import for the current function (or top-level) using the
        top-level package (to match your existing pipeline).
        """
        top_level = module_name.split(".")[0] if module_name else None
        if not top_level:
            return
        if self.current_function:
            self.module_info.functions[self.current_function].imports_in_function.add(top_level)
        else:
            self.module_info.top_level_imports.add(top_level)

    def _register_constant_path_for_module(self, module_name: str, path_str: str) -> None:
        """
        Best-effort: if we get a constant file path for a dynamically loaded module,
        map it immediately so later phases can resolve it as a local module.
        """
        try:
            # Resolve relative to the file we're analyzing
            base_dir = self.file_path.parent
            p = (base_dir / path_str).expanduser().resolve() if not os.path.isabs(path_str) else Path(path_str).expanduser().resolve()
        except Exception as e:
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Failed to resolve path %s given base_dir %s: %s", path_str, os.fspath(base_dir), e)
            return
        # Only accept .py files or a directory with __init__.py
        if p.suffix == ".py" and ek.safe_exists(p):
            self.options.custom_modules[module_name] = p
        elif ek.safe_is_dir(p) and ek.safe_exists(p / "__init__.py"):
            self.options.custom_modules[module_name] = p

    def extract_module_name_from_importlib_import_module(self, node: ast.Call) -> str | None:
        """
        Handle importlib.import_module(name, package=None) and aliased import_module().
        Only constant strings are supported.
        """
        if not node.args:
            return None
        name = self._const_str(node.args[0])
        if name is None:
            logging.error(f"Cannot resolve import_module with non-constant name: {ast.unparse(node)}")
            return None
        pkg = None
        if len(node.args) >= 2:
            pkg = self._const_str(node.args[1])
        else:
            for kw in node.keywords or []:
                if kw.arg == "package":
                    pkg = self._const_str(kw.value)
        if name.startswith("."):
            abs_name = self._resolve_relative_module(name, pkg)
            if abs_name is None:
                logging.error(f"Cannot resolve relative import_module without constant package: {ast.unparse(node)}")
                return None
            return abs_name
        return name

    def extract_from_importlib_spec_from_file_location(self, node: ast.Call) -> tuple[str, str] | None:
        """
        Handle importlib.util.spec_from_file_location(name, location, ...).
        Returns (module_name, location_path) if both are constant strings.
        """
        if len(node.args) < 2:
            return None
        mod = self._const_str(node.args[0])
        loc = self._const_str(node.args[1])
        if mod is None:
            logging.error(f"Cannot resolve spec_from_file_location with non-constant module name: {ast.unparse(node)}")
            return None
        if loc is None:
            # We can still record the import name, just no path to register
            return (mod, None)
        return (mod, loc)

    def extract_from_importlib_sourcefileloader(self, node: ast.Call) -> tuple[str, str] | None:
        """
        Handle importlib.machinery.SourceFileLoader(name, path).
        Returns (module_name, path) if both are constant strings.
        """
        if len(node.args) < 2:
            return None
        mod = self._const_str(node.args[0])
        loc = self._const_str(node.args[1])
        if mod is None:
            logging.error(f"Cannot resolve SourceFileLoader with non-constant module name: {ast.unparse(node)}")
            return None
        if loc is None:
            return (mod, None)
        return (mod, loc)


_SEP: str = "::"  # Path-safe separator to distinguish class methods


def split_function_name(called_func: str, default_module: str) -> tuple[str, str]:
    """
    Split a fully qualified function id into (module_key, func_part).

    Preferred separator is _SEP (path-safe). Fall back to the first dot
    for legacy strings that still look like 'module.func'.
    """
    if _SEP in called_func:
        m, f = called_func.split(_SEP, 1)
        return m, f
    # legacy fallback
    parts = called_func.split(".")
    if len(parts) > 1:
        return parts[0], ".".join(parts[1:])
    return default_module, called_func


def _resolve(name: str, alias_to_key: dict[str, str] | None) -> str:
    """Resolve an alias-based module name to its file-path-based key."""
    return alias_to_key.get(name, name) if alias_to_key else name


def build_call_graph(modules_info: dict[str, ModuleInfo],
                     alias_to_key: dict[str, str] | None = None) -> dict[str, set[str]]:
    """Build a call graph from the function calls in the modules."""
    call_graph = {}
    for module_key, module_info in modules_info.items():
        for func_name, func_info in module_info.functions.items():
            full_func_name = f"{module_key}{_SEP}{func_name}"
            call_graph[full_func_name] = set()
            for called_func in func_info.function_calls:
                called_module, called_name = split_function_name(called_func, module_key)
                called_module = _resolve(called_module, alias_to_key)

                # If target looks like Class.method and isn't present, try the base class.
                if called_module in modules_info:
                    mi = modules_info[called_module]
                    if "." in called_name:
                        cls, meth = called_name.split(".", 1)
                        if called_name not in mi.functions and cls in mi.base_classes:
                            bases = mi.base_classes.get(cls, [])
                            if bases:
                                base = bases[0]
                                if base in mi.classes:
                                    called_full_name = f"{called_module}{_SEP}{base}.{meth}"
                                else:
                                    if "." in base:
                                        base_mod, base_sym = base.split(".", 1)
                                        called_full_name = f"{_resolve(base_mod, alias_to_key)}{_SEP}{base_sym}.{meth}"
                                    else:
                                        called_full_name = f"{base}{_SEP}{meth}"
                                call_graph[full_func_name].add(called_full_name)
                                continue

                # Check if called_name is a class in the module
                if called_module in modules_info and called_name in modules_info[called_module].classes:
                    called_full_name = f"{called_module}{_SEP}{called_name}.__init__"
                else:
                    called_full_name = f"{called_module}{_SEP}{called_name}"
                call_graph[full_func_name].add(called_full_name)
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Call graph constructed:")
    for func, calls in call_graph.items():
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("%s calls: %s", func, calls)
    return call_graph


def collect_used_imports(start_module: str, start_func: str,
                         call_graph:   dict[str, set[str]],
                         modules_info: dict[str, ModuleInfo],
                         visited: set[str] | None = None,
                         alias_to_key: dict[str, str] | None = None) -> set[str]:
    """
    Collect all imports used in a function and its callees.
    

    Args:
        start_module: The module where the function is defined.
        start_func:   The function name to start collecting imports from.
        call_graph:   A dictionary representing the call graph of functions.
        modules_info: A dictionary mapping module keys to ModuleInfo objects.
        visited:      A set of fully qualified function names that have already been visited.
        alias_to_key: A dictionary mapping module aliases to their file-path-based keys.

    Returns:
        A set of import statements used in the function and its callees.
    """
    if visited is None:
        visited = set()
    # Resolve alias-based module name to file-path-based key
    start_module        = _resolve(start_module, alias_to_key)
    full_func_name: str = f"{start_module}{_SEP}{start_func}"
    if full_func_name in visited:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Already visited %s, skipping.", full_func_name)
        return set()
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Visiting function: %s", full_func_name)
    visited.add(full_func_name)
    imports: set[str] = set()
    module_info       = modules_info.get(start_module)
    if module_info:
        func_info = module_info.functions.get(start_func)
        if func_info:
            if func_info.imports_in_function:
                if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Function %s imports: %s", full_func_name, func_info.imports_in_function)
            imports.update(func_info.imports_in_function)
    # Follow resolved edges from the call graph:
    edges = call_graph.get(full_func_name, set())
    for called_full in edges:
        called_module, called_name = split_function_name(called_full, start_module)
        imports.update(collect_used_imports(called_module, called_name, call_graph,
                                            modules_info, visited, alias_to_key))
    return imports


def _analyze_module(options:          Options,
                    module_path:      Path,
                    modules_info:     dict[str, ModuleInfo],
                    module_contents:  dict[str, str],
                    module_trees:     dict[str, ast.AST],
                    do_sys_path_scan: bool) -> tuple[str, ModuleInfo] | None:
    """
    Read, parse, and analyze one module file.
    - Optionally scans for sys.path mutations (current behavior: only for the first loop).
    - Updates modules_info / module_contents / module_trees.

    Args:
        options:          Options object containing configuration and state. Contains:
            - options.stdlib:           StdlibIndex of the target interpreter's standard library.
            - options.custom_modules:   Dictionary mapping custom module names to their file paths.
            - options.sys_path_hints:   Set of Path objects representing directories to add to sys.path.
            - options.rawlog:           Boolean indicating whether to log raw file contents.
        module_path:      Path to the module file to analyze.
        modules_info:     Dictionary mapping module keys to ModuleInfo objects.
        module_contents:  Dictionary mapping module keys to their source code.
        module_trees:     Dictionary mapping module keys to their ASTs.
        do_sys_path_scan: Whether to scan for sys.path mutations in this module.

    Returns:
        (module_key, module_info) or None on failure.
    """
    module_path = ek.ensure_path(module_path)
    module_key  = os.fspath(module_path.resolve())

    file_content = ek.my_fopen(module_path, rawlog=options.rawlog)
    if not file_content:
        logging.error(f"Could not read file: {module_path}")
        return None

    try:
        tree = ast.parse(file_content, module_key)
    except Exception:
        logging.error(f"Failed to parse the file: {module_path}")
        return None

    module_contents[module_key] = file_content
    module_trees[   module_key] = tree

    collector = ImportFunctionCollector(options, module_key, module_path)
    collector.visit(tree)

    # Keep behavior identical: only the first loop does sys.path scanning.
    if do_sys_path_scan:
        aliases = collect_pathlib_aliases(tree)
        spv = SysPathVisitor(aliases)
        spv.visit(tree)
        base_dir = module_path.parent
        for p in spv.paths:
            if not p:
                continue
            P = (base_dir / p).expanduser().resolve() if not os.path.isabs(p) else Path(p).expanduser().resolve()
            if ek.safe_is_dir(P):
                options.sys_path_hints.add(P)

    module_info = collector.module_info
    module_info.base_classes = collector.base_classes
    modules_info[module_key] = module_info
    return module_key, module_info


def _enqueue_top_level_imports(options:           Options,
                               module_path:          Path,
                               import_names:     set[str],
                               processed_paths: set[Path],
                               modules_to_process: "collections.deque[Path]") -> None:
    """
    Given top-level imports for a module, run your existing resolution logic and
    enqueue any newly found local modules/packages for the first pass queue.
    """
    for import_name in import_names:
        if import_name in options.stdlib:
            options.seen_stdlib_imports.add(import_name)
            continue  # Skip standard modules
        resolved = process_import(options, import_name, module_path)
        if not resolved:
            options.all_imports.add(import_name)
            continue
        possible_module_file_path = options.custom_modules.get(import_name)
        if possible_module_file_path is None:
            continue
        actual_module_file_path = ek.ensure_path(possible_module_file_path)
        if ek.safe_is_file(actual_module_file_path):
            if actual_module_file_path not in processed_paths and actual_module_file_path not in modules_to_process:
                modules_to_process.append(actual_module_file_path)


def find_imports_and_IO_in_script(options: Options, first_path: str | os.PathLike[str]) -> None:
    """
    Find all imports and I/O in the script (including functions and classes
    that it imports from its dependencies.)

    Args:
        options:    Options object containing paths to the python script and custom modules.
        first_path: Path to the Python script to analyze for imports and I/O.

    Returns:
        None - modifies options to include all imports and I/O operations found in the script.

    Raises:
        FileNotFoundError: If the first_path does not exist.
        IsADirectoryError: If the first_path exists but is a directory.
        ValueError:        If the first_path exists but is not a regular file.
    """
    from collections import deque  # Allows for efficient first in, first out processing of modules
    first_path = ek.ensure_file(first_path)
    if not ek.is_python_script(first_path) or not ek.compile_code(first_path):
        logging.error(f"Skipping invalid Python script: {first_path}")
        return
    options.read_files                  = []
    options.write_files                 = []
    options.download_urls               = []
    options.upload_urls                 = []
    processed_paths:          set[Path] = set()
    modules_info: dict[str, ModuleInfo] = {}
    modules_to_process:     deque[Path] = deque([first_path])
    module_contents:     dict[str, str] = {}
    module_trees:    dict[str, ast.AST] = {}
    while modules_to_process:
        module_path = modules_to_process.popleft()  # first in, first out
        if not options.rawlog: logging.info("Processing module: %s where %s", module_path, type(module_path))
        if ek.safe_is_dir(module_path):
            pkg_dir = module_path
            init_py = pkg_dir / "__init__.py"
            if ek.safe_is_file(init_py):
                # 1) Parse the package __init__.py
                module_path = init_py
                # 2) Also enqueue all other .py modules in that same folder
                for p in pkg_dir.iterdir():
                    if ek.is_python_script(p) and p.name != "__init__.py":
                        if p not in modules_to_process and p not in processed_paths:
                            modules_to_process.append(p)
            else:
                logging.error(f"No __init__.py in package directory {pkg_dir}, skipping.")
                continue
        elif not ek.safe_is_file(module_path):
            logging.error(f"Skipping {module_path} because it is not a file or directory.")
            continue
        if module_path in processed_paths:
            continue
        processed_paths.add(module_path)
        result = _analyze_module(options, module_path, modules_info, module_contents,
                                 module_trees, do_sys_path_scan=True)
        if result is None:
            continue
        module_key, module_info = result
        _enqueue_top_level_imports(
            options, module_path,
            module_info.top_level_imports,
            processed_paths,
            modules_to_process,
        )
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Modules processed so far:")
    for module_key, m_info in modules_info.items():
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Module: %s, Classes: %s, Functions: %s", module_key, m_info.classes, list(m_info.functions.keys()))

    # Build alias → file-path-key mapping for local modules
    _alias_to_key: dict[str, str] = {}
    for _mod_name, _mod_path in options.custom_modules.items():
        _p = ek.ensure_path(_mod_path)
        if ek.safe_is_file(_p):
            _alias_to_key[_mod_name] = os.fspath(_p.resolve())

    # Now build the call graph
    call_graph = build_call_graph(modules_info, alias_to_key=_alias_to_key)

    # Collect used imports starting from the first module
    used_imports:  set[str] = set()
    visited_funcs: set[str] = set()

    def collect_imports_from_module(module_key: str) -> None:
        """Recursively collect used imports from a module."""
        module_info = modules_info[module_key]
        used_imports.update(module_info.top_level_imports)
        for func_name in module_info.top_level_calls:
            called_module, called_name = split_function_name(func_name, module_key)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Collecting used imports for module '%s' and func_name '%s'", called_module, called_name)
            used_imports.update(
                collect_used_imports(
                    called_module,  # Use the extracted module name
                    called_name,    # Use the extracted function name
                    call_graph,
                    modules_info,
                    visited_funcs,
                    _alias_to_key
                )
            )
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Used imports collected from '%s' in '%s': %s", called_name, called_module, used_imports)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Used imports after collecting from module %s: %s", module_key, used_imports)

    # Scan the *initial* script (first_path) everywhere:
    first_module_key = os.fspath(first_path.resolve())
    collect_imports_from_module(first_module_key)
    init_src  = module_contents[first_module_key]
    init_tree = module_trees[   first_module_key]

    FileOperationsVisitor(options,    init_src).visit(init_tree)
    NetworkOperationsVisitor(options, init_src).visit(init_tree)

    # Now process used imports and recursively dive into any new local modules.
    processed_used_imports: set[str] = set()
    new_modules_found = True
    while new_modules_found:
        new_modules_found = False
        for import_name in used_imports.copy():
            # Skip built-ins or any we've already handled this round
            if import_name in options.stdlib:
                options.seen_stdlib_imports.add(import_name)
                continue
            if import_name in processed_used_imports:
                continue
            processed_used_imports.add(import_name)
            process_import(options, import_name, first_path)
            if import_name in options.custom_modules:
                # It's a known local module that we haven't processed yet
                module_file_path = ek.ensure_path(options.custom_modules[import_name])
                if not ek.safe_is_file(module_file_path):
                    logging.error(f"Custom module path for {import_name} is not a file: {module_file_path}")
                    continue
                new_module_key = os.fspath(module_file_path.resolve())
                if new_module_key in modules_info or \
                   module_file_path in processed_paths or \
                   module_file_path in modules_to_process:
                    # Already parsed, but still trace its top-level calls
                    if new_module_key in modules_info:
                        old_size = len(used_imports)
                        collect_imports_from_module(new_module_key)
                        if len(used_imports) > old_size:
                            new_modules_found = True
                    continue  # don't re-analyze
                modules_to_process.append(module_file_path)
                new_modules_found = True
                result = _analyze_module(options, module_file_path, modules_info,
                                         module_contents, module_trees, do_sys_path_scan=False)
                if result is None:
                    continue
                new_module_key, module_info = result
                # Rebuild alias map and call graph with the new module included
                _p = ek.ensure_path(module_file_path)
                if ek.safe_is_file(_p):
                    _alias_to_key[import_name] = os.fspath(_p.resolve())
                call_graph = build_call_graph(modules_info, _alias_to_key)
                collect_imports_from_module(new_module_key)
                _enqueue_top_level_imports(options, module_file_path,
                                           module_info.top_level_imports,
                                           processed_paths,
                                           modules_to_process)
            else:
                # If not a local module, add to options.all_imports
                options.all_imports.add(import_name)
    # For every *other* local module, do:
    #   (1) top-level only, plus
    #   (2) only in the function bodies that actually got visited
    for module_key, src in module_contents.items():
        if module_key == first_module_key:
            continue
        # Record any I/O at module scope
        TopLevelFileOperationsVisitor(options,    src).visit(module_trees[module_key])
        TopLevelNetworkOperationsVisitor(options, src).visit(module_trees[module_key])
        # Record any I/O in each reachable function or class method
        for full in visited_funcs:
            mod, func = split_function_name(full, default_module="")
            if _resolve(mod, _alias_to_key) != module_key:
                continue
            func_info = modules_info[mod].functions.get(func)
            if not func_info:
                continue
            func_src  = src
            func_node = func_info.ast_node
            # run your original visitor on that one FunctionDef
            FileOperationsVisitor(options,    func_src).visit(func_node)
            NetworkOperationsVisitor(options, func_src).visit(func_node)
    if not options.rawlog:
        discovered_operations = []
        if any([options.read_files, options.write_files]):
            discovered_operations.append("file")
        if any([options.download_urls, options.upload_urls]):
            discovered_operations.append("network")
        if discovered_operations:
            logging.info("Found %s operations:", " and ".join(discovered_operations))
            if options.read_files:
                logging.info("Files read:\n"    + "\n".join(os.fspath(f) for f in options.read_files))
            if options.write_files:
                logging.info("Files written:\n" + "\n".join(os.fspath(f) for f in options.write_files))
            if options.download_urls:
                logging.info("Download URLs:\n" + "\n".join(os.fspath(u) for u in options.download_urls))
            if options.upload_urls:
                logging.info("Upload URLs:\n"   + "\n".join(os.fspath(u) for u in options.upload_urls))
        else:
            logging.info("Found no file or network operations in the python script (%s) or custom modules (%s).",
                         options.python_script, ", ".join(options.loaded_custom_modules))


def resolve_records(options: Options, import_names: Iterable[str]) -> set[ResolvedImport]:
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
                logging.info("Adding dependencies for %s: %s", record.import_name, dependencies)
            options.uninstalled_imports.update(resolve_records(options, dependencies))

    # Handle nested dependencies by repeating this process until no new dependencies are added.
    added = True
    while added:
        added = False
        current_packages = options.uninstalled_imports.copy()
        for record in current_packages:
            if record.import_name in options.also_needs:
                dependencies = options.also_needs[record.import_name]
                new_dependencies = resolve_records(options, dependencies) - options.uninstalled_imports
                if new_dependencies:
                    if not options.rawlog:
                        logging.info("Adding nested dependencies for %s: %s", record.import_name,
                                     sorted(r.import_name for r in new_dependencies))
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

_SHARED_LIBRARY_PATTERN = re.compile(r"[\w.+-]+\.(?:so(?:\.[\w.]+)?|dylib|dll)",
                                     re.IGNORECASE)


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
    return "\n".join(line.removeprefix("Import error: ") for line in output.splitlines()
                     if line.startswith("Import error: "))


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
            names.update(alias_index.normalize_pip_name(name) for name in listed.split(",") if name)
    return frozenset(names)


def import_outcome_in_venv(options: Options, import_name: str,
                           venv_dir: str | os.PathLike[str] | None = None) -> ImportOutcome:
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
    imported, output = run_import_check_in_venv(venv_python_for(options, venv_dir),
                                                [[import_name]], report_providers=True)
    if imported:
        return ImportOutcome(imported=True, rejection_kind="", detail="",
                             providers=import_providers(output))
    detail = import_error_detail(output)
    if not any(marker in detail for marker in MACHINE_SCOPED_IMPORT_MARKERS):
        return ImportOutcome(imported=False, rejection_kind="import_failed", detail=detail)
    library = _SHARED_LIBRARY_PATTERN.search(detail)
    logging.warning("%s is installed but will not import on this machine: %s. That is a "
                    "missing system library (%s), not the wrong package -- install the "
                    "operating-system package that provides it. veny will not hold this "
                    "against the package.",
                    import_name, detail, library.group(0) if library else "unknown")
    return ImportOutcome(imported=False, rejection_kind="import_unavailable", detail=detail)


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
    return any(alias_index.normalize_pip_name(name) == wanted for name in outcome.providers)


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
            candidate.pip_name, resolution.import_name, candidate.evidence,
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
                logging.debug("Not caching %s -> %s: the venv credits %s with providing it.",
                              resolution.import_name, candidate.pip_name,
                              sorted(outcome.providers) if isinstance(outcome, ImportOutcome)
                              else "something else")
            return candidate
        logging.debug(
            "%s installed but did not provide %s; removing it.",
            candidate.pip_name, resolution.import_name,
        )
        uninstaller(candidate.pip_name)
        index.reject(resolution.import_name, candidate.pip_name,
                     outcome.rejection_kind if isinstance(outcome, ImportOutcome) else "import_failed")
    return None


def venv_python_for(options: Options, venv_dir: str | os.PathLike[str] | None = None) -> Path:
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


def run_import_check_in_venv(venv_python: Path, alternatives: list[list[str]],
                             report_providers: bool = False) -> tuple[bool, str]:
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
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("check_packages_in_venv stdout:\n%s", result.stdout)
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("check_packages_in_venv stderr:\n%s", result.stderr)
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


def check_packages_in_venv(options: Options, record: ResolvedImport | None = None,
                           venv_dir: str | os.PathLike[str] | None = None,
                           source_names: set[str] | None = None) -> bool:
    """
    Check if packages can be imported in the specified virtual environment.

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
        use_pip_list(options)
        # Ask the venv what it actually has, instead of import-checking every
        # record under its pip spelling: requirement_records() sets
        # import_name == pip_name for --reqs entries (a requirements line is
        # a pip name and nothing maps it backwards), and import_module()
        # always fails on a pip spelling like "opencv-python". Probing once
        # here and inverting the result answers "what does this distribution
        # actually import as?" from the installed artifact, covering every
        # distribution rather than only what a curated table happened to know.
        _, venv_distributions = alias_index.probe_interpreter(venv_python)
        import_names_by_dist = alias_index.import_names_by_distribution(venv_distributions)
        if source_names is None:
            source_names = source_import_names(options)
        alternatives = []
        for entry in sorted(options.uninstalled_imports, key=lambda r: r.import_name):
            top_levels = import_names_by_dist.get(alias_index.normalize_pip_name(entry.pip_name))
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
            if entry.import_name in source_names or (top_levels and entry.import_name in top_levels):
                alternatives.append([entry.import_name])
            elif top_levels:
                alternatives.append(sorted(top_levels))
            else:
                alternatives.append([entry.import_name])
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Packages to check in venv: %s", alternatives)
    imported, _ = run_import_check_in_venv(venv_python, alternatives)
    return imported


def _compute_bad_imports(all_imports: set[str], known_bad: set[str],
                         py2_only: frozenset[str]) -> set[str]:
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
    for name, system_package in stdlib_index.hints_for(options.seen_stdlib_imports).items():
        logging.warning("%s is in the standard library but needs the %s system package "
                        "before it will import.", name, system_package)


def split_imports(options: Options) -> None:
    """Split imports into installed, uninstalled, and bad imports."""
    options.bad_imports = _compute_bad_imports(options.all_imports, options.known_bad_imports,
                                               stdlib_index.PYTHON2_ONLY)
    if options.bad_imports:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Identified bad imports: %s", options.bad_imports)
    options.all_imports = options.all_imports - options.bad_imports
    options.installed_imports   = set()
    options.uninstalled_imports = set()
    if getattr(options.args, "reqs", False):
        options.all_imports = options.all_imports.union(options.extra_requirements.keys())
    options.total_imports = len(options.all_imports)
    if not options.total_imports:
        if not options.rawlog: logging.info("No imports found.")
        return

    max_length = max(len(imp) for imp in options.all_imports)  # Longest import name length, used for formatting
    max_digits = len(str(len(options.all_imports)))  # Maximum number of digits in import count, also used for formatting

    with tempfile.TemporaryDirectory() as venv_dir:
        venv.create(venv_dir, with_pip=True)
        for i, imp in enumerate(options.all_imports, 1):
            # The import name is all either check below needs, and resolution is
            # deliberately not done yet: see the else branch.
            record = ResolvedImport(import_name=imp, pip_name=imp)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Checking if import %s is installed or uninstalled", imp)
            if imp in options.custom_modules.keys():
                if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Custom module %s has path %s", imp, os.fspath(options.custom_modules[imp]))
                status_str = f"{ek.ANSI_CYAN}YES - custom module{ek.ANSI_RESET}"
            elif check_packages_in_venv(options, record=record,
                                        venv_dir=venv_dir):
                if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Module %s can be imported in venv", imp)
                status_str = f"{ek.ANSI_GREEN}YES -     installed{ek.ANSI_RESET}"
                # The pip name is left as the import name here because nothing
                # needs it: an installed import is never handed to pip. If
                # use_pip_list() later reclassifies this record, it resolves it.
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
                primary = resolution.candidates[0].pip_name if resolution.candidates else imp
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug("Resolved import %s to candidates %s", imp,
                                  [c.pip_name for c in resolution.candidates])
                if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Import %s is not installed and not a custom module", imp)
                status_str = " NO - NOT installed"
                options.uninstalled_imports.add(ResolvedImport(import_name=imp, pip_name=primary))
            if not options.rawlog:
                logging.info("Checking import %-*s : %*d/%d - %s",
                             max_length,  # width for imp (left-aligned)
                             imp,
                             max_digits,  # width for i (right-aligned)
                             i, options.total_imports, status_str)
    if getattr(options.args, "reqs", False):
        options.uninstalled_imports = options.uninstalled_imports.union(requirement_records(options.extra_requirements.keys()))
    add_dependencies(options)
    return


def list_packages(options: Options) -> None:
    """
    Examine command line arguments to determine if we're looking at a directory or a single python script. List all installed and uninstalled packages that are imported in that directory or python script. Return these sets inside the options object.

    Args:
        options: Options object containing command line arguments and settings. Contains:
            - python_script:           Path to the Python script or directory to analyze.
            - rawlog:                  Boolean indicating if raw logging is enabled.
            - pipreqs_available:       Boolean indicating if pipreqs is available for
                                       generating requirements.
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
    assert options.script_dir    is not None, "options.script_dir must be set"
    if getattr(options.args, "full", False):
        if not options.rawlog: logging.info("Building a virtual environment that can run every python script in %s", os.fspath(options.script_dir))

    if isinstance(options.python_script, (str, Path)):
        options.python_script         = ek.ensure_path(options.python_script)
        options.loaded_custom_modules = set()
        if ek.safe_is_file(options.python_script):
            if ek.is_python_script(options.python_script):
                if not options.rawlog: logging.info("Processing a single Python script: %s", os.fspath(options.python_script))
                python_file = options.python_script
                options.all_imports = set()
                find_imports_and_IO_in_script(options, python_file)
            else:
                raise ValueError(f"'{os.fspath(options.python_script)}' is not a valid Python script.")
        elif ek.safe_is_dir(options.python_script):
            if not options.rawlog: logging.info("Processing an entire folder of Python scripts: %s",
                                                os.fspath(options.python_script))
            python_dir = options.python_script
            if options.pipreqs_available:
                if not options.rawlog: logging.info("Using pipreqs to generate requirements.")
                generate_requirements(options.python_script)
                with open(python_dir / "requirements.txt", "r") as f:
                    options.all_imports = set(line.strip() for line in f)
            else:
                if not options.rawlog: logging.info("Using custom script to find imports.")
                get_all_imports(options, options.python_script)
        else:
            raise FileNotFoundError(f"The file or directory {os.fspath(options.python_script)} does not exist.")
    else:
        raise ValueError(f"Unexpected type for options.python_script: {type(options.python_script)}")

    # Filter out invalid imports before splitting
    options.all_imports = {imp for imp in options.all_imports if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', imp)}

    split_imports(options)


def stayed_out_dir(options: Options, p: str | os.PathLike[str]) -> bool:
    """Check if the parent directory of path p contains any substrings from the stay_out_list."""
    p          = ek.ensure_path(p)
    parent_str = os.fspath(p.parent)
    return any(sub in parent_str for sub in options.stay_out_list)


def get_all_imports(options: Options, directory: str | os.PathLike[str]) -> None:
    """Get all imports from all Python scripts in a directory."""
    directory = ek.ensure_path(directory)
    options.all_imports = set()
    # Build one iterator of candidate files (recursive)
    candidates = (p for p in directory.rglob("*") if ek.safe_is_file(p) and not stayed_out_dir(options, p))
    # If you want a progress denominator that matches what you'll actually process:
    total_files     = sum(1 for p in candidates if ek.is_python_script(p))
    max_digits      = len(str(total_files))  # For formatting progress output
    processed_files = 0
    # Recreate the iterator (generators are single-use)
    candidates = (p for p in directory.rglob("*") if ek.safe_is_file(p) and not stayed_out_dir(options, p))
    for file_path in candidates:
        if ek.is_python_script(file_path):
            find_imports_and_IO_in_script(options, file_path)
            processed_files += 1
            if not options.rawlog:
                # OLD: logging.info(f"Processing file {processed_files:>{max_digits}}/{total_files} : {file_path}")
                logging.info("Processing file %*d/%d : %s",
                             max_digits, processed_files, total_files, file_path)
    if not options.rawlog: logging.info("Finished processing files in %s", os.fspath(directory))


def generate_requirements(directory: str | os.PathLike[str]) -> None:
    """Generate a requirements file using pipreqs."""
    try:
        pipreqs.generate_requirements(directory)
    except (pipreqs.PipreqsError, pipreqs.PipreqsWarning) as e:
        raise ValueError(f"Error generating requirements file in {directory}: {e}") from e


def download_packages(options: Options) -> bool:
    """Install packages in a virtual environment."""
    download_script = f"""#!/bin/bash
    source {options.venv_dir}/bin/activate

    # Upgrade pip
    echo "Upgrading pip..."
    pip install --upgrade pip

    # Ensure setuptools and wheel are available locally
    if ls {options.packages_dir}/setuptools-*.whl 1> /dev/null 2>&1; then
        echo "Local setuptools files found."
    else
        echo "Downloading setuptools..."
        {options.venv_pip} download --only-binary=:all: setuptools -d {options.packages_dir}
    fi

    if ls {options.packages_dir}/wheel-*.whl 1> /dev/null 2>&1; then
        echo "Local wheel files found."
    else
        echo "Downloading wheel..."
        {options.venv_pip} download --only-binary=:all: wheel -d {options.packages_dir}
    fi

    # Download required packages
    echo "Downloading packages..."
    {options.venv_pip} download -r {options.requirements_file} -d {options.packages_dir}"""

    try:
        assert options.download_script_path is not None, "Download script path is not set."
        if not options.rawlog: logging.info("Writing download script to %s", options.download_script_path)
        options.download_script_path.write_text(download_script, encoding=ek.DEFAULT_ENCODING)
        options.download_script_path.chmod(0o755)
        # Run the initial download script and capture the output
        result = ek.my_popen([options.download_script_path])
        return result.returncode == 0
    except OSError:
        logging.exception("Error writing or executing download script.")
        return False


def install_packages_simultaneously(options: Options) -> bool:
    """Install all packages simultaneously in the virtual environment."""
    # Construct the install command
    install_command = [
        options.venv_python, "-m", "pip", "install",
        "--no-index", "--find-links", options.packages_dir,
        "-r", options.requirements_file
    ]
    if not options.rawlog: logging.info("Installing all packages simultaneously...")
    # Run the command and capture the output line by line using ek.my_popen
    result = ek.my_popen(install_command)
    if result.returncode == 0:
        if not options.rawlog: logging.info("All packages installed successfully.")
        return True
    else:
        logging.error("Failed to install some packages.")
        return False


def install_packages_individually(options: Options) -> bool:
    """Install packages individually in the virtual environment."""
    failed_packages = []
    # pip is being invoked, so this is the one place that wants the pip name.
    for record in options.uninstalled_imports:
        if not install_package(record.pip_name, options):
            failed_packages.append(record.pip_name)

    if failed_packages:
        logging.error("Failed to install the following packages: %s", ", ".join(sorted(failed_packages)))
        return False
    else:
        if not options.rawlog: logging.info("All packages installed successfully.")
        return True


def install_package(package_name: str, options: Options) -> bool:
    """Install a single package and return the success status (True if successful, False otherwise)."""
    assert options.venv_python  is not None, "Virtual environment Python executable is not set."
    assert options.packages_dir is not None, "Packages directory is not set."
    the_command = [os.fspath(options.venv_python), "-m", "pip", "install", package_name,
                   "--no-index", "--find-links", os.fspath(options.packages_dir)]
    logging.info("Running pip install: %s", " ".join(shlex.quote(str(arg)) for arg in the_command))
    result = subprocess.run(the_command, capture_output=True, text=True)
    if not options.rawlog: logging.info(result.stdout)
    if result.stderr:
        logging.error(result.stderr)
    if result.returncode != 0:
        # Use pip to download files for package_name to options.packages_dir
        download_command = [os.fspath(options.venv_python), "-m", "pip", "download", "--dest",
                            os.fspath(options.packages_dir), package_name]
        download_result = subprocess.run(download_command, capture_output=True, text=True)
        if download_result.returncode != 0:
            ek.my_critical_error(f"Failed to download {package_name}. Error: {download_result.stderr}")
        # Use pip to install package_name from the file that was just downloaded to options.packages_dir
        install_command = [os.fspath(options.venv_python), "-m", "pip", "install", "--no-index",
                           "--find-links", os.fspath(options.packages_dir), package_name]
        install_result = subprocess.run(install_command, capture_output=True, text=True)
        if install_result.returncode != 0:
            logging.error("Failed to install %s. Error: %s", package_name, install_result.stderr)
        else:
            if not options.rawlog: logging.info("Successfully installed %s", package_name)
        return result.returncode == 0
    return result.returncode == 0


def recover_pip_versions(output: str, options: Options) -> None:
    """Parse the output to recover the current and new pip versions."""
    if hasattr(output, "read"):
        output = output.read()
    current_version_pattern = re.compile(r"Current pip version: (.+)")
    new_version_pattern     = re.compile(r"New     pip version: (.+)")

    current_version_match = current_version_pattern.search(output)
    new_version_match     = new_version_pattern.search(    output)

    if current_version_match:
        options.current_pip_version = current_version_match.group(1)
        if not options.rawlog: logging.info("Recovered current pip version: %s", options.current_pip_version)
    else:
        logging.warning("Failed to recover current pip version from output.")

    if new_version_match:
        options.new_pip_version = new_version_match.group(1)
        if not options.rawlog: logging.info("Recovered new pip version: %s", options.new_pip_version)
    else:
        logging.warning("Failed to recover new pip version from output.")


def venv_build_interpreter(options: Options) -> str:
    """Return the interpreter that should create the virtual environment.

    options.python_command is what stdlib and alias resolution were probed
    against, so it is what the venv must be built with; building with
    sys.executable instead classifies imports for one Python and installs them
    for another. find_preferred_python_version() returns "" when the preferred
    Python is absent from PATH, and only then does the running interpreter serve.

    Args:
        options: Options object; reads options.python_command.

    Returns:
        A path or command name for the interpreter to build with.
    """
    return options.python_command or sys.executable


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


def use_pip_list(options: Options) -> None:
    """Use the pip list command to find all installed packages and use that pip list to modify the uninstalled and installed imports. Add packages from the options.extra_requirements dictionary if "--reqs" is specified as a runtime argument."""
    # Add packages from the options.extra_requirements dictionary if "--reqs" is specified as a runtime argument.
    if getattr(options.args, "reqs", False):
        options.uninstalled_imports = options.uninstalled_imports.union(requirement_records(options.extra_requirements.keys()))
    if len(options.pip_list) == 0:
        # Create virtual environment
        venv.create(options.test_dir, with_pip=True)
        python_executable = options.test_dir / "bin" / "python"

        # Run custom list command using the Python executable from the virtual environment
        list_command_script = """
import importlib.metadata
import pkgutil
import sys

def list_installed_packages():
    installed_packages = [dist.metadata["Name"] for dist in importlib.metadata.distributions()]
    return installed_packages

def list_available_modules():
    available_modules = [module.name for module in pkgutil.iter_modules()]
    return available_modules

def list_builtin_modules():
    builtin_modules = sys.builtin_module_names
    return builtin_modules

installed_packages = list_installed_packages()
available_modules = list_available_modules()
builtin_modules = list_builtin_modules()

print("\\n".join(installed_packages + available_modules + list(builtin_modules)))
"""

        list_command = [os.fspath(python_executable), "-c", list_command_script]

        try:
            result = subprocess.run(list_command, check=True, capture_output=True, text=True)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Output:\n%s", result.stdout)
        except subprocess.CalledProcessError as e:
            logging.exception("%s\nException type: %s", e, type(e).__name__)

        # Use regular expressions to find all package names
        options.pip_list = re.findall(r'^[^\s]+', result.stdout, re.MULTILINE)
        options.pip_list = [pkg for pkg in options.pip_list if pkg != "Package" and not all(c == "-" for c in pkg)]
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("\noptions.pip_list = %s", options.pip_list)

        pip_list_filename = options.my_dir / f"pip_list_{options.timestamp}.txt"
        pip_list_filename.write_text("\n".join(options.pip_list), encoding=ek.DEFAULT_ENCODING)

    # options.pip_list holds distribution names, module names and builtin module
    # names all mixed together, so it is matched against the import name -- which
    # is exactly what the pre-record code compared, since installed_imports used
    # to hold import names.
    known_names = set(options.pip_list)
    stale_records = {record for record in options.installed_imports
                     if record.import_name not in known_names}
    # These records are about to be handed to pip, and split_imports() leaves an
    # installed record's pip_name as its import name because nothing needed it
    # until now. This is the moment it does, so resolve it here -- otherwise pip
    # is asked to install "cv2".
    new_uninstalled_imports = resolve_records(options, {record.import_name for record in stale_records})
    options.uninstalled_imports = options.uninstalled_imports.union(new_uninstalled_imports)
    if options.uninstalled_imports:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug(
            "new_uninstalled_imports = %s",
            sorted(record.import_name for record in new_uninstalled_imports))
    # Remove the records as they were, not as they were re-resolved: resolution
    # may have changed the pip_name, and a set difference on the new records
    # would then leave the old ones behind in installed_imports.
    options.installed_imports = options.installed_imports - stale_records
    # Once again, add packages from the options.extra_requirements dictionary if "--reqs" is specified as a runtime argument. (Do this again, just in case they got removed from the uninstalled_imports set above.)
    if getattr(options.args, "reqs", False):
        options.uninstalled_imports = options.uninstalled_imports.union(requirement_records(options.extra_requirements.keys()))


def parse_extra_requirements(options: Options) -> None:
    """
    Parse an extra requirements file and return a dictionary of package names (and version specifiers, if present).
    The file should have one package per line, optionally with version specifiers (e.g., 'package>=1.0').
    Lines starting with '#' are treated as comments and ignored.
    
    Args:
        options: Options object containing the path to the extra requirements file.
    
    Returns:
        None. A dictionary where keys are package names and values are version specifiers is added
        to the options object as extra_requirements.
    """
    options.extra_requirements = {}
    file_content = ek.my_fopen(options.extra_requirements_file, suppress_errors=True, rawlog=options.rawlog)
    if not file_content:
        return
    # Regular expression to capture package name and version specifier
    pattern = re.compile(r'^\s*([A-Za-z0-9_\-\.]+)\s*(.*)$')
    for line in file_content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            match = pattern.match(line)
            if match:
                package                             = match.group(1)
                version_spec                        = match.group(2).strip() if match.group(2) else ""
                options.extra_requirements[package] = version_spec


def write_requirements_file_with_extras(options: Options) -> None:
    """Write the requirements file with the extra requirements added."""
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Writing packages to %s", options.requirements_file)
    assert options.requirements_file   is not None, "options.requirements_file must be set"
    assert options.uninstalled_imports is not None, "options.uninstalled_imports must be set"
    assert options.extra_requirements  is not None, "options.extra_requirements must be set"
    with open(options.requirements_file, "w") as f:
        # Write the packages in alphabetical order so the requirements file is
        # deterministic. pip reads this file, so it gets the pip names.
        for package in sorted(record.pip_name for record in options.uninstalled_imports):
            if package in options.extra_requirements:
                version_spec = options.extra_requirements[package]
                if version_spec:
                    f.write(f"{package}{version_spec}\n")
                else:
                    f.write(f"{package}\n")
            else:
                f.write(f"{package}\n")


def run_pip_in_venv(options: Options, *args: str) -> subprocess.CompletedProcess[str] | None:
    """Run one pip command inside the venv without ever raising.

    Every caller here is on a verification path, where the whole point is to
    report what happened rather than to end the run, so a missing interpreter or
    an unrunnable pip is reported as "no result" instead of an exception.

    Args:
        options: Options object; reads options.venv_python.
        *args:   The pip arguments, e.g. "install", "cv2".

    Returns:
        The completed process, or None if pip could not be run at all.
    """
    if options.venv_python is None:
        logging.error("Cannot run pip %s: no virtual environment interpreter is set.", args[0])
        return None
    the_command = [os.fspath(options.venv_python), "-m", "pip", *args]
    logging.info("Running pip: %s", " ".join(shlex.quote(str(arg)) for arg in the_command))
    try:
        return subprocess.run(the_command, capture_output=True, text=True,  # noqa: S603
                              check=False)
    except OSError:
        logging.exception("Could not run pip %s.", args[0])
        return None


def install_into_venv(options: Options, pip_name: str) -> bool:
    """Install one package into the venv, reporting failure instead of ending the run.

    install_package(), the batch path's installer, calls ek.my_critical_error()
    -- which exits -- when a download fails. Verifying one import must never be
    able to kill the whole run, so this installer reports False for every
    failure instead. It offers the wheels already downloaded to packages_dir but,
    unlike the batch install, does not pass --no-index: a candidate reached by
    the verification loop is by definition one that was never downloaded.

    Args:
        options:  Options object; reads options.venv_python and options.packages_dir.
        pip_name: The package to install.

    Returns:
        True if pip reported success.
    """
    local_wheels = ["--find-links", os.fspath(options.packages_dir)] if options.packages_dir else []
    result = run_pip_in_venv(options, "install", pip_name, *local_wheels)
    if result is None:
        return False
    if result.returncode != 0:
        logging.error("Failed to install %s. Error: %s", pip_name, result.stderr.strip())
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
    result = run_pip_in_venv(options, "uninstall", "-y", pip_name)
    if result is not None and result.returncode != 0:
        logging.warning("Could not uninstall %s. Error: %s", pip_name, result.stderr.strip())


def repair_unsatisfied_import(options: Options, record: ResolvedImport,
                              installed_distributions: dict[str, frozenset[str]],
                              outcome: ImportOutcome) -> ResolvedImport:
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
        options.aliases.reject(record.import_name, record.pip_name, outcome.rejection_kind)
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

    winner = resolve_and_verify(options.aliases.resolve(record.import_name), options.aliases,
                                installer=installer, importer=importer, uninstaller=uninstaller)
    if winner is None:
        logging.error("Could not find a package that provides the import %s.", record.import_name)
        return record
    if not options.rawlog:
        logging.info("%s provides the import %s (%s).",
                     winner.pip_name, record.import_name, winner.evidence)
    return ResolvedImport(import_name=record.import_name, pip_name=winner.pip_name)


def confirm_if_attributable(options: Options, record: ResolvedImport,
                            installed_distributions: dict[str, frozenset[str]]) -> None:
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
    top_levels = installed_distributions.get(alias_index.normalize_pip_name(record.pip_name))
    if top_levels is not None and record.import_name in top_levels:
        options.aliases.confirm(record.import_name, record.pip_name)
    elif logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Not caching %s -> %s: the venv imports %s but does not attribute "
                      "it to that distribution (it declares %s).",
                      record.import_name, record.pip_name, record.import_name,
                      sorted(top_levels) if top_levels else "nothing")


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
    records = [record for record in sorted(options.uninstalled_imports, key=lambda r: r.import_name)
               if record.import_name in from_source]
    if not records:
        return
    # One probe, used by both branches: the bulk branch needs it to attribute a
    # passing import to the distribution that actually provided it, and the
    # repair branch needs it to tell "installed but does not provide this" from
    # "never installed at all".
    _, venv_distributions   = alias_index.probe_interpreter(options.venv_python)
    installed_distributions = alias_index.import_names_by_distribution(venv_distributions)
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
        replacement = repair_unsatisfied_import(options, record, installed_distributions, outcome)
        if replacement != record:
            repaired[record] = replacement
    if repaired:
        options.uninstalled_imports = (options.uninstalled_imports - set(repaired)) | set(repaired.values())
        # Keep the venv's own requirements.txt describing what is really installed.
        write_requirements_file_with_extras(options)


_VERSION_PROBE_CODE = (
    "import json\n"
    "from importlib.metadata import distributions\n"
    "print(json.dumps({d.metadata['Name']: d.version for d in distributions()"
    " if d.metadata['Name']}))\n"
)


def installed_versions_in_venv(options: Options) -> dict[str, str]:
    """Ask a virtual environment which versions it actually has.

    This is what the manifest records, rather than what was requested or what
    pip printed: only the venv itself knows what ended up installed, including
    versions pip chose for unpinned packages.

    Args:
        options: Options object; reads options.venv_python, which callers must
                 have already set -- a None value is a caller-contract error
                 and asserts rather than returning empty.

    Returns:
        A mapping of normalized pip name to version. Empty if the probe could
        not be run or its output could not be read -- a version veny could not
        read is recorded as unknown, which makes any later pin check on that
        package fail closed.
    """
    assert options.venv_python is not None, "Virtual environment Python executable is not set."
    command = [os.fspath(options.venv_python), "-c", _VERSION_PROBE_CODE]
    try:
        result = subprocess.run(command, capture_output=True, text=True,  # noqa: S603
                                check=False, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        logging.warning("Could not list installed versions in the venv (%s).", exc)
        return {}
    if result.returncode != 0:
        logging.warning("Could not list installed versions in the venv: %s", result.stderr.strip())
        return {}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logging.warning("Could not read the installed versions reported by the venv (%s).", exc)
        return {}
    return {venv_cache.normalize_pip_name(name): str(version)
            for name, version in payload.items()}


def manifest_for(options: Options, versions: dict[str, str]) -> venv_cache.Manifest:
    """Build the manifest describing a finished virtual environment.

    Args:
        options:  Options object; reads options.uninstalled_imports (after any
                  repairs), options.extra_requirements, and the interpreter.
        versions: Installed versions, keyed by normalized pip name.

    Returns:
        The manifest to write into the venv.
    """
    # extra_requirements is keyed by whatever spelling the user typed on the
    # command line, which need not match record.pip_name's spelling -- the
    # versions dict a line below is already keyed normalized, so this lookup
    # must be too. Normalized once here rather than per record.
    normalized_requirements = {venv_cache.normalize_pip_name(name): spec
                               for name, spec in options.extra_requirements.items()}
    packages = tuple(
        venv_cache.PackageRecord(
            import_name=record.import_name,
            pip_name=record.pip_name,
            installed_version=versions.get(venv_cache.normalize_pip_name(record.pip_name)),
            requested_spec=normalized_requirements.get(venv_cache.normalize_pip_name(record.pip_name)),
        )
        for record in sorted(options.uninstalled_imports, key=lambda r: r.pip_name)
    )
    return venv_cache.Manifest(
        schema_version=venv_cache.SCHEMA_VERSION,
        created=options.timestamp,
        veny_version=__version__,
        interpreter_tag=interpreter_tag(options),
        interpreter_path=venv_build_interpreter(options),
        packages=packages,
    )


def record_venv_state(options: Options) -> None:
    """Rename the venv if repairs changed its packages, then write its manifest.

    verify_and_repair_imports can replace a record whose pip_name was wrong, so
    the folder name written before installing may list a package the venv does
    not have. The name is only a prefilter, but a stale one rejects a venv the
    manifest would accept -- so the name is brought back into agreement first.

    Args:
        options: Options object; reads the final records and updates
                 options.venv_dir if a rename happens.

    Returns:
        None.
    """
    assert options.venv_dir is not None, "options.venv_dir must be set"
    wanted_name = venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=interpreter_tag(options),
        timestamp=options.timestamp,
        pip_names=[record.pip_name for record in options.uninstalled_imports],
    )
    prefix       = "failed-" if options.venv_dir.name.startswith("failed-") else ""
    if options.venv_dir.name != prefix + wanted_name:
        if not options.rawlog:
            logging.info("Repairs changed this venv's packages; renaming it to %s.",
                         prefix + wanted_name)
        rename_venv(options, prefix + wanted_name)
    venv_cache.write_manifest(options.venv_dir, manifest_for(options, installed_versions_in_venv(options)))


def setup_virtualenv(options: Options) -> bool:
    """Setup a virtual environment and install packages."""
    use_pip_list(options)
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

    write_requirements_file_with_extras(options)

    if not options.rawlog: logging.info("Creating virtual environment...")
    assert options.venv_dir is not None, "options.venv_dir must be set"
    subprocess.check_call([venv_build_interpreter(options), "-m", "venv", os.fspath(options.venv_dir)])
    if not options.rawlog: logging.info("Virtual environment created.")

    # Activate virtual environment and install wheel
    assert options.venv_pip is not None, "options.venv_pip must be set"
    install_command = [os.fspath(options.venv_pip), "install", "wheel"]
    logging.info("Running pip install: %s", " ".join(shlex.quote(str(arg)) for arg in install_command))
    subprocess.run(install_command, check=True)
    if not options.rawlog: logging.info("Wheel installed in the virtual environment.")

    download_packages(options)
    if install_packages_simultaneously(options):
        options.simultaneous_success = True
    else:
        options.simultaneous_success = False  # This is redundant, but it's here for clarity. The 'failed' part of the venv_dir will not be removed if this is False.
        logging.error("Failed to install packages simultaneously. Trying to install packages individually to see which fail, but this venv folder will still have 'failed-' in its name...")
        if not install_packages_individually(options):
            logging.error("Failed to install packages individually.")

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

    A venv records its own location in pyvenv.cfg and in the download script, so
    a rename that touches only the directory leaves a venv that points at a path
    that no longer exists. Two callers need this: dropping the "failed-" prefix
    once a run succeeds, and re-naming a venv whose package list changed when
    verify_and_repair_imports repaired a wrongly resolved pip name.

    Args:
        options:  Options object; reads and updates options.venv_dir.
        new_name: The directory's new name, not a path.

    Returns:
        None. Failure to rewrite a recorded path is logged, not raised: the venv
        has already moved and the run continues.
    """
    assert options.venv_dir is not None, "options.venv_dir must be set"
    old_dir  = options.venv_dir
    new_dir  = old_dir.with_name(new_name)
    if new_dir == old_dir:
        return
    old_dir.rename(new_dir)
    options.set_venv_dir(new_dir)
    assert options.download_script_path is not None, "options.download_script_path must be set"
    for path in (options.venv_dir / "pyvenv.cfg", options.download_script_path):
        try:
            contents = path.read_text()
        except OSError as exc:
            logging.warning("Could not read %s after renaming the venv (%s).", path, exc)
            continue
        updated = contents.replace(old_dir.name, new_dir.name)
        if updated == contents:
            continue
        try:
            path.write_text(updated)
        except OSError as exc:
            logging.warning("Could not update %s after renaming the venv (%s).", path, exc)


def is_virtualenv() -> bool:
    """Check if currently running in a virtual environment."""
    return sys.prefix != sys.base_prefix


def load_last_used_options(options: Options) -> Options | None:
    """Look for the most recent JSON file in the script directory that matches the script name and load it into a new Options object. Ignore any JSON files created before the options.pathlibcutoff timestamp."""
    assert options.script_dir    is not None, "options.script_dir must be set"
    assert options.python_script is not None, "options.python_script must be set"
    pattern = re.compile(r"last-used-on-(\d{8}-\d{6})")
    json_files = [
        f
        for f in options.script_dir.iterdir()
        if f.name.startswith("." + options.python_script.name)
        and f.suffix.casefold() == ".json"
        and (m := pattern.search(f.name))        # extract timestamp
        and m.group(1) >= options.pathlibcutoff  # compare as strings
    ]
    if not json_files:
        if not options.rawlog: logging.info("No previous JSON files found in the script directory.")
        return None
    if len(json_files) > 1:
        json_files.sort(key=lambda x: dt.datetime.strptime(x.name.split("-")[-2] + x.name.split("-")[-1].replace(".json", ""), "%Y%m%d%H%M%S"), reverse=True)
    return ek.load_options_from_json(options, options.script_dir / json_files[0])


def load_last_used_venv_dir(options: Options) -> Path | None:
    """Look for the most recent JSON file in the script directory that matches the script name and return the venv_dir from it."""
    last_used_options = load_last_used_options(options)
    if not last_used_options:
        if not options.rawlog: logging.info("No last used options found, so no venv directory to return.")
        return None
    elif not hasattr(last_used_options, "venv_dir"):
        if not options.rawlog: logging.info("Last used options do not have a venv_dir attribute.")
        return None
    elif last_used_options.venv_dir is None:
        if not options.rawlog: logging.info("Last used venv directory is None.")
        return None
    elif not ek.safe_is_dir(last_used_options.venv_dir):
        if not options.rawlog: logging.warning("Last used venv directory %s is no longer valid.",
                                               os.fspath(last_used_options.venv_dir))
        return None
    else:
        if not options.rawlog: logging.info("Last used venv directory found: %s",
                                            os.fspath(last_used_options.venv_dir))
        return last_used_options.venv_dir


def load_last_used_venv_python(options: Options) -> Path | None:
    """
    Look for the most recent JSON file in the script directory that matches the script name and return the venv_python from it.
    
    Args:
        options: Options object containing settings and paths.
    
    Returns:
        The Path object of the last used venv_python, or None if not found or invalid.
    """
    last_used_options = load_last_used_options(options)
    if not last_used_options:
        if not options.rawlog: logging.info("No last used options found, so no venv_python to return.")
        return None
    elif not hasattr(last_used_options, "venv_python"):
        if not options.rawlog: logging.info("Last used options do not have a venv_python attribute.")
        return None
    elif last_used_options.venv_python is None:
        if not options.rawlog: logging.info("Last used venv_python is None.")
        return None
    elif not ek.safe_is_file(last_used_options.venv_python):
        if not options.rawlog: logging.warning("Last used venv_python %s is no longer valid.",
                                               os.fspath(last_used_options.venv_python))
        return None
    else:
        if not options.rawlog: logging.info("Last used venv_python found: %s",
                                            os.fspath(last_used_options.venv_python))
        return last_used_options.venv_python


def latest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None:
    """
    Return the folder Path that has the latest timestamp.
    
    Args:
        final_venv_folders: A dictionary where keys are folder paths (as strings or
                            os.PathLike objects) and values are dictionaries containing
                            metadata about each folder, including a 'timestamp' key.
    
    Returns:
        The Path object of the folder with the latest timestamp, or None if no valid
        folder is found.
    """
    latest_folder:   Path | None = None
    latest_timestamp: int | None = None
    for folder, data in final_venv_folders.items():
        if latest_timestamp is None or data['timestamp'] > latest_timestamp:
            latest_timestamp = data['timestamp']
            latest_folder    = folder
    return latest_folder


def oldest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None:
    """
    Return the folder Path that has the oldest timestamp.

    Args:
        final_venv_folders: A dictionary where keys are folder paths (as strings or
                            os.PathLike objects) and values are dictionaries containing
                            metadata about each folder, including a 'timestamp' key.
    
    Returns:
        The Path object of the folder with the oldest timestamp, or None if no valid
        folder is found.
    """
    oldest_folder:   Path | None = None
    oldest_timestamp: int | None = None
    for folder, data in final_venv_folders.items():
        if oldest_timestamp is None or data['timestamp'] < oldest_timestamp:
            oldest_timestamp = data['timestamp']
            oldest_folder    = folder
    return oldest_folder


def smallest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None:
    """
    Return the folder Path that has the fewest packages.

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
        if smallest_num_packages is None or data['num_packages'] < smallest_num_packages:
            smallest_num_packages = data['num_packages']
            smallest_folder       = folder
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
            logging.info("The cached venv directory %s is no longer there.", os.fspath(venv_dir))
        return False
    manifest = venv_cache.read_manifest(venv_dir)
    if manifest is None:
        if not options.rawlog:
            logging.info("The cached venv directory %s has no readable manifest.",
                         os.fspath(venv_dir))
        return False
    result = venv_cache.satisfies(manifest, wanted_packages(options), interpreter_tag(options))
    if not result.matched:
        if not options.rawlog:
            logging.info("The cached venv directory %s cannot be used because %s.",
                         os.fspath(venv_dir), result.reason)
        return False
    # The manifest says the packages are there; this confirms the imports
    # really import. source_names is passed explicitly -- redundant with
    # check_packages_in_venv's own default today, since both read off this
    # same options -- so that this call site still names the live run's
    # source imports as what governs even if that default ever changes.
    if check_packages_in_venv(options, venv_dir=venv_dir,
                              source_names=source_import_names(options)):
        return True
    logging.error("The cached venv directory %s failed check_packages_in_venv.",
                  os.fspath(venv_dir))
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
    normalized_requirements = {venv_cache.normalize_pip_name(name): spec
                               for name, spec in options.extra_requirements.items()}
    return [venv_cache.Wanted(pip_name=record.pip_name,
                              spec=normalized_requirements.get(venv_cache.normalize_pip_name(record.pip_name)))
            for record in sorted(options.uninstalled_imports, key=lambda r: r.pip_name)]


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

    folder:   Path
    parsed:   venv_cache.FolderName
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
    tag    = interpreter_tag(options)
    wanted = wanted_packages(options)
    names  = [item.pip_name for item in wanted]
    matches: list[CacheCandidate] = []
    for folder in folders:
        parsed = venv_cache.parse_folder_name(folder.name)
        if parsed is None:
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug("Skipping %s: not a venv folder name veny wrote.", os.fspath(folder))
            continue
        if parsed.interpreter_tag != tag or not venv_cache.name_allows(parsed, names):
            continue
        manifest = venv_cache.read_manifest(folder)
        if manifest is None:
            if not options.rawlog:
                logging.info("Skipping the cached venv %s: it has no readable manifest.",
                             os.fspath(folder))
            continue
        result = venv_cache.satisfies(manifest, wanted, tag)
        if not result.matched:
            if not options.rawlog:
                logging.info("Skipping the cached venv %s because %s.",
                             os.fspath(folder), result.reason)
            continue
        matches.append(CacheCandidate(folder=folder, parsed=parsed, manifest=manifest))
    return matches


def find_match_dir_in_cache(options: Options) -> Path | None:
    """
    Try to find a matching virtual environment directory in the cache.

    Args:
        options: Options object containing the necessary parameters.

    Returns:
        The path to the matching virtual environment directory if found, otherwise None.

    Raises:
        None, but logs errors if the combination of flags is invalid, if no matching venv is found,
        or if the cached venv is invalid.
    """
    if not getattr(options.args, "latest",    False) and \
       not getattr(options.args, "oldest",    False) and \
       not getattr(options.args, "last_used", False) and \
       not getattr(options.args, "smallest",  False):
        options.args.last_used = True  # If no flags are set, then the default is to load the last used venv in the cache
    if     getattr(options.args, "last_used", False) and \
       not getattr(options.args, "latest",    False) and \
       not getattr(options.args, "smallest",  False):
        options_last_used = load_last_used_options(options)
        # venv_dir is declared in veny.Options.__init__, not in the base
        # emmykit.Options that load_last_used_options builds from, so a
        # last-used JSON written without that key must not raise here.
        venv_dir_last_used = getattr(options_last_used, "venv_dir", None)
        if options_last_used is not None and venv_dir_last_used is not None \
           and check_venv_dir(options, venv_dir_last_used):
            return ek.ensure_path(venv_dir_last_used)
        else:
            if not options.rawlog: logging.info("Trying to load the latest matching venv now.")
        options.args.latest    = True  # If that didn't work, try to load the latest venv in the cache
        options.args.last_used = False  # And set this to False because it failed
    if not options.rawlog: logging.info("Checking the cache for a virtual environment with all the required packages...")
    all_venv_folders = [f for f in options.my_dir.iterdir()
                        if ek.safe_is_dir(f) and f.name.startswith(options.venv_name)]
    final_venv_folders: dict[Path, dict[str, int]] = {}
    for candidate in cache_candidates(options, all_venv_folders):
        final_venv_folders[candidate.folder] = {"timestamp"    : int(candidate.parsed.timestamp.replace("-", "")),
                                                "num_packages" : len(candidate.manifest.packages)}
    if not final_venv_folders:
        if not options.rawlog: logging.info("No matching venv folders found in the cache.")
    else:
        if not options.rawlog: logging.info("Found %d matching venv folders in the cache.",
                                            len(final_venv_folders))
        if     getattr(options.args, "latest",    False) and \
           not getattr(options.args, "oldest",    False) and \
           not getattr(options.args, "last_used", False) and \
           not getattr(options.args, "smallest",  False):
            # Return the latest venv in the cache which has all the packages needed now
            latest_venv_folder: Path | None = latest_venv(final_venv_folders)
            if latest_venv_folder is None:
                if not options.rawlog:
                    logging.error("Could not determine the latest venv folder from the cache.")
                return None
            if check_venv_dir(options, latest_venv_folder):
                return latest_venv_folder
            if not options.rawlog:
                logging.error("The latest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
            return None
        elif        getattr(options.args, "oldest",    False) and \
                not getattr(options.args, "latest",    False) and \
                not getattr(options.args, "last_used", False) and \
                not getattr(options.args, "smallest",  False):
            # Return the oldest venv in the cache which has all the packages needed now
            oldest_venv_folder: Path | None = oldest_venv(final_venv_folders)
            if oldest_venv_folder is None:
                if not options.rawlog:
                    logging.error("Could not determine the oldest venv folder from the cache.")
                return None
            if check_venv_dir(options, oldest_venv_folder):
                return oldest_venv_folder
            if not options.rawlog:
                logging.error("The oldest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
            return None
        elif        getattr(options.args, "smallest",  False) and \
                not getattr(options.args, "latest",    False) and \
                not getattr(options.args, "oldest",    False) and \
                not getattr(options.args, "last_used", False):
            # Return the smallest venv in the cache which has all the packages needed now
            smallest_venv_folder: Path | None = smallest_venv(final_venv_folders)
            if smallest_venv_folder is None:
                if not options.rawlog:
                    logging.error("Could not determine the smallest venv folder from the cache.")
                return None
            if check_venv_dir(options, smallest_venv_folder):
                return smallest_venv_folder
            if not options.rawlog:
                logging.error("The smallest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
            return None
        else:  # This should never happen
            logging.error(f"Invalid combination of flags!\n"
                          f"{getattr(options.args, 'latest',    False) = }\n"
                          f"{getattr(options.args, 'oldest',    False) = }\n"
                          f"{getattr(options.args, 'last_used', False) = }\n"
                          f"{getattr(options.args, 'smallest',  False) = }")
    return None


STANDARD_LIB_PATHS: tuple[Path, ...] = (Path("/") / "usr" / "lib",
                                        Path("/") / "usr" / "local" / "lib",
                                        Path("/") / "usr" / "lib64",
                                        Path("/") / "usr" / "local" / "lib64")

STANDARD_LIB_NAMES: tuple[str, ...] = ("lib", "lib64")


def is_standard_path(options: Options, path: str | os.PathLike[str]) -> bool:
    """Check if the given path is a standard system path or part of a virtual environment."""
    p = ek.ensure_path(path)
    # Check if path is inside standard system paths
    for std_path in STANDARD_LIB_PATHS:
        if p.is_relative_to(std_path):  # Python 3.9+
            return True
    # Check if path contains anything in stay_out_list
    p_str = os.fspath(p)
    if any(s in p_str for s in options.stay_out_list):
        return True
    # Check for Virtualenv-style paths:
    # .../lib/python*/site-packages or .../lib64/python*/site-packages
    if "site-packages" in p_str:
        parts = p.parts
        for i in range(len(parts) - 1):
            comp = parts[i]
            if comp in STANDARD_LIB_NAMES:
                nxt = parts[i + 1]
                if nxt.startswith("python"):  # also matches "python"
                    return True
    return False


def only_search_here_filename_boolean(filename: str | os.PathLike[str], thestring: str) -> bool:
    """Check if the given filename contains thestring, which is used to determine if the search is limited to the current directory."""
    return thestring in os.fspath(filename)


def search_anywhere_filename_boolean(filename: str | os.PathLike[str], thestring: str) -> bool:
    """Check if the given filename does NOT contain thestring. By default, those files are assumed to have been created by searching above the current directory."""
    return thestring not in os.fspath(filename)


def only_search_here_path_boolean(options: Options, path: str | os.PathLike[str]) -> bool:
    """Check if the given path is in the current directory."""
    return Path(path).absolute().is_relative_to(options.cwd)


def search_anywhere_path_boolean(options: Options, path: str | os.PathLike[str]) -> bool:
    """Return True regardless."""
    return True


def dict_of_custom_modules(options: Options) -> dict[str, Path]:
    """Create (or load) a dictionary of all local custom modules in the non-standard sys.path directories and their associated filepaths."""
    # If --rc and --no-cache were not specified, look for a pickle file with the custom modules dictionary the last time this script was run.

    # I.f.f. options.search_above_this_dir is True, then search above the current directory for custom modules.
    # Either way, only load custom module pickle files that searched in the same places as requested.
    search_above_text_to_match = "only_search_here_"  # For legacy reasons, custom module pickle files are assumed to have searched above the current directory unless this text is present in the filename.
    if options.search_above_this_dir:
        search_above_text_to_write = "_"  # This will be added to the filename of the custom modules pickle file.
        search_constraint_filename_boolean = search_anywhere_filename_boolean
        search_constraint_path_boolean     = search_anywhere_path_boolean
    else:
        search_above_text_to_write = search_above_text_to_match  # This will be added to the filename of the custom modules pickle file.
        search_constraint_filename_boolean = only_search_here_filename_boolean
        search_constraint_path_boolean     = only_search_here_path_boolean

    log = logging.getLogger()  # Prebind the logger to avoid repeated global lookups in hot loop
    if log.isEnabledFor(logging.DEBUG): logging.debug("Searching for custom modules pickle files with constraint: search_above_text_to_match = %s",
                  search_above_text_to_match)
    if not getattr(options.args, "rc",       False) and \
       not getattr(options.args, "no_cache", False):
        try:
            potential_files = [file for file in options.cwd.iterdir()
                               if file.name.startswith(f".{options.my_name}_custom_modules_") and
                                  file.suffix.casefold() == ".pkl" and
                                  ek.COMPUTER_NAME in file.name and
                                  search_constraint_filename_boolean(file.name, search_above_text_to_match)]
            if not potential_files:
                if not options.rawlog:
                    logging.info("No existing custom modules pickle files found in the current directory.")
            else:
                # If multiple files are found, pick the most recent one based on the timestamp in the filename.
                potential_files_with_timestamps: list[tuple[Path, str]] = [
                    (file, ts)
                    for file in potential_files
                    if (ts := ek.extract_timestamp(file.name)) is not None
                ]
                if not potential_files_with_timestamps:
                    if not options.rawlog:
                        logging.info("No valid timestamps found in custom modules pickle filenames.")
                else:
                    # Sort by timestamp descending
                    potential_files_with_timestamps.sort(key=lambda x: x[1], reverse=True)
                    most_recent_file = potential_files_with_timestamps[0][0]
                    most_recent_timestamp = potential_files_with_timestamps[0][1]
                    if not options.rawlog:
                        logging.info("Loading custom modules from most recent pickle file: %s", most_recent_file)
                    with open(most_recent_file, "rb") as f:
                        loaded_modules = pickle.load(f)
                    if most_recent_timestamp < options.pathlibcutoff:
                        if not options.rawlog:
                            logging.info("Custom modules file %s is from date %s "
                                         "which is older than the point when "
                                         "paths were stored as Paths (which happened on %s). "
                                         "Converting all paths to pathlib.Path objects.",
                                         most_recent_file, most_recent_timestamp, options.pathlibcutoff)
                        normalized: dict[str, Path] = {k: ek.ensure_path(v) for k, v in loaded_modules.items()}
                    else:
                        # If the pickle already contains Paths, narrow the type for mypy
                        normalized = {k: (v if isinstance(v, Path) else ek.ensure_path(v)) for k, v in loaded_modules.items()}
                    return normalized
        except Exception:
            logging.exception("Error loading custom modules from pickle file.")
            logging.error("Falling back to regenerating the custom modules dictionary from sys.path.")

    custom_modules: dict[str, Path] = {}
    package_dirs:         set[Path] = set()  # directories confirmed to be packages

    # Use lru_cache to speed up repeated calls to is_standard_path()
    @lru_cache(maxsize=8192)
    def _is_std_path_cached(p: str | os.PathLike[str]) -> bool:
        """Check if a path is a standard library path. Cached for speed."""
        return is_standard_path(options, p)

    # Prebind a few globals/attributes to locals before os.walk to cut repeated global lookups:
    is_std       = _is_std_path_cached
    endswith_ext = ek.PYTHON_EXTENSIONS
    safe_is_file = ek.safe_is_file
    safe_is_dir  = ek.safe_is_dir

    if log.isEnabledFor(logging.DEBUG): logging.debug("Generating custom modules dictionary from sys.path...")
    for path in map(Path, sys.path):
        if not is_std(path) and safe_is_dir(path) and search_constraint_path_boolean(options, path):
            if log.isEnabledFor(logging.DEBUG): logging.debug("Checking path: %s", path)

            # Prebind a few globals/attributes to locals before os.walk to cut repeated global lookups:
            setdefault_mod   = custom_modules.setdefault
            package_dirs_add = package_dirs.add
            # Suppress any remaining (permissions related?) walking errors with onerror = ... None
            for root, dirs, files in os.walk(path, topdown=True, onerror=(lambda e: None)):
                root_path = Path(root)
                # If the root itself is standard, skip the whole subtree immediately
                if is_std(root_path):
                    dirs[:] = []  # stop descending
                    continue
                # PRUNE: remove standard subdirs in-place to avoid descending into them
                # Also collect package dirs (those with __init__.py) while we're here
                kept_dirs = []
                for d in dirs:
                    if d == "__pycache__":
                        continue
                    pkg = root_path / d
                    if is_std(pkg):
                        continue  # prune
                    kept_dirs.append(d)
                    if safe_is_file(pkg / "__init__.py"):
                        package_dirs_add(pkg)
                        # prefer packages; first occurrence wins
                        setdefault_mod(d, pkg)
                dirs[:] = kept_dirs  # apply pruning
                # Files: skip quickly by filename; only build Path when needed
                for fname in files:
                    fl = fname.casefold()
                    # fast extension + __init__ checks (exactly final extension)
                    if not fl.endswith(endswith_ext):
                        continue
                    if fl == "__init__.py":
                        continue
                    fpath = root_path / fname
                    if is_std(fpath):
                        continue
                    # if file lives inside a known package dir, skip (package already recorded)
                    if fpath.parent in package_dirs:
                        continue
                    setdefault_mod(fpath.stem, fpath)

    # Now save to a pickle file:
    current_time = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    custom_filename = f".{options.my_name}_custom_modules_{ek.COMPUTER_NAME}{search_above_text_to_write}{current_time}.pkl"
    with open(custom_filename, "wb") as f_out:
        if not options.rawlog:
            logging.info("Saving custom modules to %s", custom_filename)
        pickle.dump(custom_modules, f_out, protocol=pickle.HIGHEST_PROTOCOL)  # Use highest protocol for efficiency because we don't need backward compatibility for caching purposes
    return custom_modules


if __name__ == "__main__":
    main()
