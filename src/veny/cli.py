#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), ChatGPT 5 Thinking (it/its), and GitHub Copilot (it/its).
from __future__ import (
    annotations,
)  # For Python 3.7+ compatibility with type annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path
from typing import Final

from . import __version__ as __version__
from . import alias_index

try:
    import emmykit as ek
except ImportError as exc:  # stdlib only: none of emmykit's helpers exist yet.
    raise SystemExit(
        "veny requires the emmykit package (>=0.4.0), which is not installed.\n"
        "Install it with:  pip install 'emmykit>=0.4.0'"
    ) from exc

_MINIMUM_EMMYKIT: Final[tuple[int, int, int]] = (0, 4, 0)


def _emmykit_version() -> tuple[int, ...]:
    """The installed emmykit's version, as far as it can be read.

    Returns:
        The leading numeric components of ``ek.__version__``, or an empty
        tuple when it is absent or unreadable -- which compares less than any
        real version, so an emmykit that will not say what it is is refused.
    """
    parts: list[int] = []
    for piece in str(getattr(ek, "__version__", "")).split("."):
        digits = ""
        for character in piece:
            if not character.isdigit():
                break
            digits += character
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


if _emmykit_version() < _MINIMUM_EMMYKIT:
    raise SystemExit(
        f"veny requires emmykit >= 0.4.0; found {getattr(ek, '__version__', 'unknown')}.\n"
        f"Upgrade it with:  pip install -U 'emmykit>=0.4.0'"
    )
# Below the version guard on purpose: an emmykit too old to trust should not
# even see the rest of veny's modules imported.
from . import environment, pipeline, settings  # noqa: E402

# An import name paired with the pip package that provides it. Defined in
# alias_index, which imports nothing of veny's, and re-exported here because
# veny is where it is used.
ResolvedImport = alias_index.ResolvedImport

# The installed command's name, fixed rather than derived from argv[0]: under
# `python -m veny` the stem is "__main__", which would move every venv, log
# and last-used record veny owns from ~/veny to ~/__main__. Pinned by
# test_state_directory_ignores_argv0.
MY_NAME: Final[str] = "veny"


def parse_arguments() -> argparse.Namespace:
    """Parse the command line.

    Returns:
        The parsed arguments. `--help` with no arguments at all prints the
        guide and exits 0 rather than returning.

    Raises:
        SystemExit: --version or a bare invocation; argparse's own behaviour.
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
        help=f"Delete ~/{MY_NAME}/ and all {MY_NAME} .out and .err and .json and .pkl files in the current directory.",
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
        help=f"Do not add timestamps or INFO level to log messages, and do not add extra INFO level log statements. Just produce the same output that would be seen when running the program without {MY_NAME}.",
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

    return parser.parse_args()


def _shell_status(script_exit_code: int) -> int:
    """Map a child's returncode onto the status veny exits with.

    A script killed by a signal yields a negative returncode (e.g. -9 for
    SIGKILL). Exiting a process with a negative status wraps around to the
    wrong shell status (-9 becomes 247), so it is reported as the
    conventional 128 + signal number (-9 becomes 137) instead.

    One function rather than two copies of the arithmetic: until phase 4c
    the --feeling-lucky path returned from the middle of main() and skipped
    the tail that did this, so the same signal produced two different
    statuses depending on one flag.

    Args:
        script_exit_code: The child's returncode, negative if it was killed.

    Returns:
        The status veny should exit with.
    """
    if script_exit_code < 0:
        return 128 - script_exit_code
    return script_exit_code


def main() -> int:
    """Parse the command line, run veny, and map the result to an exit status.

    Returns:
        The wrapped script's exit status; 0 when nothing was meant to run
        (--justprint, --blank-slate); 1 when veny could not find or build an
        environment; 2 for a usage error. A child killed by a signal is
        reported as 128 + signal rather than as a negative status, which the
        shell would wrap around to the wrong number -- on every path,
        --feeling-lucky included, since phase 4c.
    """
    start_time = dt.datetime.now()
    args = parse_arguments()
    rawlog = args.rawlog
    # Only ek.configure_logging below reads this, so it is a local rather
    # than a field on anything.
    log_mode = logging.DEBUG if args.debug else logging.INFO
    # The run's invariants, built exactly once and handed down. Home is a
    # construction detail rather than a field: it exists only to derive
    # my_dir.
    run_settings = settings.Settings(
        my_name=MY_NAME,
        my_dir=Path.home() / MY_NAME,
        cwd=Path.cwd().expanduser().resolve(strict=True),
        venv_name="myenv",
        stay_out_list=settings.DEFAULT_STAY_OUT_LIST,
        search_above_this_dir=True,
        rawlog=rawlog,
        known_bad_imports=settings.DEFAULT_KNOWN_BAD_IMPORTS,
        also_needs=settings.DEFAULT_ALSO_NEEDS,
        extra_requirements_file="extra_requirements.txt",
    )
    memory_handler = None
    try:
        target = pipeline.resolve_target(args)
        lucky_status = pipeline.feeling_lucky(
            args,
            target,
            my_name=MY_NAME,
            rawlog=rawlog,
        )
        if lucky_status is not None:
            return _shell_status(lucky_status)
        memory_handler = ek.configure_logging(
            MY_NAME, log_level=log_mode, rawlog=rawlog
        )
        script_exit_code = pipeline.run(
            run_settings, args, target, start_time=start_time
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
    ek.print_all_errors(memory_handler, rawlog)
    logging.shutdown()
    return _shell_status(script_exit_code)
