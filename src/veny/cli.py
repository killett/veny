#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), ChatGPT 5 Thinking (it/its), and GitHub Copilot (it/its).
from __future__ import (
    annotations,
)  # For Python 3.7+ compatibility with type annotations

import argparse
import datetime as dt
import logging
import sys

from . import __version__ as __version__
from . import alias_index

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
from . import environment, json_types, pipeline, run_options, settings

# An import name paired with the pip package that provides it. Defined in
# alias_index, which imports nothing of veny's, and re-exported here because
# veny is where it is used. Its JSON handlers live in json_types.
ResolvedImport = alias_index.ResolvedImport

# Registers veny's own types with emmykit's JSON registry. At module scope, not
# inside main(), so that anything importing veny -- including every test -- gets
# the same serialization behaviour production does. The call is idempotent.
json_types.register_types()


# Phase 3e moved the class itself to run_options.py so pipeline.py can be
# handed one without importing the module above it. This name stays for the
# suite's references -- 49 spelled `cli.Options` and 24 spelled `veny.Options`,
# re-measured on 2026-08-21 -- and dies with the class in phase 4b.
Options = run_options.Options


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


def main() -> int:
    """Parse the command line, run veny, and map the result to an exit status.

    Returns:
        The wrapped script's exit status; 0 when nothing was meant to run
        (--justprint, --blank-slate); 1 when veny could not find or build an
        environment; 2 for a usage error. On the ordinary path -- the one that
        goes through pipeline.run -- a child killed by a signal is reported as
        128 + signal rather than as a negative status, which the shell would
        wrap around to the wrong number. --feeling-lucky does NOT get that
        normalization: it returns pipeline.feeling_lucky's status directly, so
        a lucky run killed by SIGKILL still returns -9. That asymmetry is
        pre-existing behaviour, unchanged by phase 3e and deliberately left
        alone by its whole-branch review; see PROGRESS.md's deferred items.
    """
    start_time = dt.datetime.now()
    options = Options()
    parse_arguments(options)
    options.rawlog = getattr(options.args, "rawlog", False)
    # The run's invariants, built exactly once and handed down. `home` is a
    # construction detail rather than a field: it exists only to derive
    # my_dir. `log_mode` stays on Options because ek.configure_logging below
    # is the only reader.
    run_settings = settings.Settings(
        my_name=options.my_name,
        my_dir=options.home / options.my_name,
        cwd=options.cwd,
        venv_name="myenv",
        stay_out_list=settings.DEFAULT_STAY_OUT_LIST,
        search_above_this_dir=True,
        rawlog=options.rawlog,
        known_bad_imports=settings.DEFAULT_KNOWN_BAD_IMPORTS,
        also_needs=settings.DEFAULT_ALSO_NEEDS,
        extra_requirements_file="extra_requirements.txt",
    )
    memory_handler = None
    try:
        target = pipeline.resolve_target(options.args)
        lucky_status = pipeline.feeling_lucky(
            options.args,
            target,
            my_name=options.my_name,
            rawlog=options.rawlog,
        )
        if lucky_status is not None:
            return lucky_status
        memory_handler = ek.configure_logging(
            options.my_name, log_level=options.log_mode, rawlog=options.rawlog
        )
        script_exit_code = pipeline.run(
            run_settings, options.args, options, target, start_time=start_time
        )
    except pipeline.UsageError as exc:
        logging.info("%s", exc)
        return 2
    except pipeline.VenvBuildFailed as exc:
        logging.error("%s", exc)
        return 1
    except environment.UvUnavailable as exc:
        # Printed rather than logged: uv can be missing before
        # ek.configure_logging has run, and this is the message veny's
        # SystemExit used to put on stderr. It stays byte-identical, and so
        # does the status -- users have both in their shell history.
        print(str(exc), file=sys.stderr)
        return 1
    ek.print_all_errors(memory_handler, options.rawlog)
    logging.shutdown()
    # A script killed by a signal yields a negative returncode (e.g. -9 for
    # SIGKILL). Exiting a process with a negative status wraps around to the
    # wrong shell status (-9 becomes 247), so normalize to the conventional
    # 128 + signal number (-9 becomes 137) instead.
    if script_exit_code < 0:
        script_exit_code = 128 - script_exit_code
    return script_exit_code
