#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), ChatGPT 5 Thinking (it/its), and GitHub Copilot (it/its).
from __future__ import (
    annotations,
)  # For Python 3.7+ compatibility with type annotations

import argparse
import datetime as dt
import logging
import os
import shlex  # For safely quoting shell commands
import shutil
import subprocess
import sys

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
from . import (
    cache_search,
    environment,
    json_types,
    last_used,
    pipeline,
    run_options,
    venv_cache,
    verify,
)
from .analysis.custom_modules import dict_of_custom_modules

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
# suite's 42 `cli.Options` references and dies with the class in phase 4.
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


def _load_last_used(options: Options) -> ek.Options | None:
    """Load the previous run's options JSON, for the cache search's last-used pass.

    find_match_dir_in_cache takes this as an injected callable rather than
    reaching for last_used itself, so nothing below cli has to know what an
    Options is. The two asserts stay on this side of the injection and still
    fire only when the loader is actually called -- that is, only on the
    last-used branch, exactly where find_match_dir_in_cache used to carry them.

    Args:
        options: Options object; reads options.script_dir, options.python_script,
                 options.pathlibcutoff and options.rawlog.

    Returns:
        The previous run's options, or None when there is no usable last-used
        JSON in the script's directory.
    """
    assert options.script_dir is not None, "options.script_dir must be set"
    assert options.python_script is not None, "options.python_script must be set"
    return last_used.load_last_used_options(
        options,
        script_dir=options.script_dir,
        python_script=options.python_script,
        pathlibcutoff=options.pathlibcutoff,
        rawlog=options.rawlog,
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
    options.aliases = pipeline.build_alias_index(options)
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

    pipeline.list_packages(options)

    if not options.rawlog:
        # Report the import names, which are what the user wrote in their source.
        logging.info(
            "Uninstalled imports: %s",
            sorted(record.import_name for record in options.uninstalled_imports),
        )
        if options.bad_imports:
            logging.warning("Bad imports: %s", options.bad_imports)
        pipeline.warn_about_system_packages(options)
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
            match_dir = cache_search.find_match_dir_in_cache(
                options.args,
                my_dir=options.my_dir,
                venv_name=options.venv_name,
                uninstalled=options.uninstalled_imports,
                extra_requirements=options.extra_requirements,
                source_names=verify.source_import_names(
                    options.all_imports,
                    options.extra_requirements,
                    getattr(options.args, "reqs", False),
                ),
                tag=cache_search.interpreter_tag(options.stdlib),
                rawlog=options.rawlog,
                load_last_used=lambda: _load_last_used(options),
            )
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
            assert options.venv_dir is not None, "options.venv_dir must be set"
            if (
                options.venv_dir.name.startswith("failed-")
                and options.install_succeeded
            ):
                # If the program has made it to this point, it has run successfully, so the venv directory can be renamed because it DIDN'T fail.
                options.set_venv_dir(
                    cache_search.rename_venv(
                        options.venv_dir,
                        options.venv_dir.name.removeprefix("failed-"),
                    )
                )

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


def setup_virtualenv(options: Options) -> bool:
    """Setup a virtual environment and install packages."""
    # The folder name is a cheap prefilter for the cache search; veny_manifest.json
    # inside the venv is the authority. venv_cache owns the encoding so a
    # hyphenated pip name cannot be mistaken for a field separator.
    run_tag = cache_search.interpreter_tag(options.stdlib)
    folder_name = venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=run_tag,
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
    # Re-narrows: mypy loses the narrowing established above across the
    # intervening environment.run_uv_pip / logging / verify.source_import_names
    # calls, so this looks redundant but is load-bearing.
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
    assert options.venv_dir is not None, "options.venv_dir must be set"
    options.set_venv_dir(
        cache_search.record_venv_state(
            options.venv_dir,
            venv_python=options.venv_python,
            venv_name=options.venv_name,
            timestamp=options.timestamp,
            run_tag=run_tag,
            python_command=options.python_command,
            uninstalled=options.uninstalled_imports,
            extra_requirements=options.extra_requirements,
            rawlog=options.rawlog,
        )
    )
    # Check that all packages can be imported in the venv.
    assert options.venv_dir is not None, "options.venv_dir must be set"
    return verify.check_packages_in_venv(
        environment.venv_python_for(options.venv_dir),
        uninstalled=options.uninstalled_imports,
        source_names=source_names,
    )
