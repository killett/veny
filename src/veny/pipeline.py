"""The run: analyze, classify, acquire an environment, run the script.

This module owns sequencing and is the only one that knows the order. Every
module below it does one thing and is handed what it needs; `cli.py` above it
parses argv and maps what happens here onto an exit status.

It is handed the run's `Options` object and hands back a status. That is
transitional: `Options` is the god object the re-architecture retires, and
phase 4 replaces it with the frozen `Settings`, `Target`, `VenvHandle` and
`Requirements` values each stage actually needs. Until then this module is
where the bridge code lives -- the `ImportScan` seeding, the classification
copy-back -- rather than in `cli.py`, so that the modules under it never see
an `Options` at all.

Everything here calls its collaborators through the module object
(`verify.check_packages_in_venv(...)`, never `from .verify import ...`), which
is what lets a test replace one boundary without rebuilding the world.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import os
import re
import shlex  # For safely quoting shell commands
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import emmykit as ek

from . import (
    alias_index,
    cache_search,
    classify,
    environment,
    last_used,
    run_options,
    stdlib_index,
    venv_cache,
    verify,
)
from .analysis import custom_modules
from .analysis import scan as analysis_scan
from .analysis.scan_state import ImportScan
from .settings import Settings


class UsageError(Exception):
    """The command line asked for something veny cannot act on.

    Raised where the old code logged a message and then fell through into an
    assert. `cli.main` catches it, logs the message and returns 2 -- the
    design's usage status.
    """


class VenvBuildFailed(Exception):
    """A virtual environment veny needed could not be created.

    `environment.create_venv` reports failure rather than raising (phase 3e
    took exit ownership back into `cli.py`), and the probe environment has no
    fallback: without it, classification cannot answer "is this importable
    already?" at all. `cli.main` catches this and returns 1.
    """


def build_alias_index(options: run_options.Options) -> alias_index.AliasIndex:
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


def find_imports_in_script(
    options: run_options.Options, first_path: str | os.PathLike[str]
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


def warn_about_system_packages(options: run_options.Options) -> None:
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
def _probe_venv(options: run_options.Options) -> Iterator[Callable[[str], bool]]:
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
                record=alias_index.ResolvedImport(
                    import_name=import_name, pip_name=import_name
                ),
            )

        yield is_importable


def split_imports(options: run_options.Options) -> None:
    """Adapter: run classification and copy its product back onto Options.

    The copy-back is total -- these four fields are the complete set the old
    split_imports wrote. See the plan's "Why the ImportScan bridge is not
    touched" section: classify reads the scan and writes nothing through it,
    so nothing here depends on in-place mutation. Each frozenset becomes a set
    again on the way back, because later stages (verify_and_repair_imports)
    still mutate options.uninstalled_imports.

    Args:
        options: Options object; the four classification fields are replaced.
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
    options.uninstalled_imports = set(result.uninstalled)
    options.total_imports = result.total_imports


def list_packages(options: run_options.Options) -> None:
    """Examine command line arguments to determine if we're looking at a directory or a single python script. List all installed and uninstalled packages that are imported in that directory or python script. Return these sets inside the options object.

    Args:
        options: Options object containing command line arguments and settings. Contains:
            - python_script:           Path to the Python script or directory to analyze.
            - rawlog:                  Boolean indicating if raw logging is enabled.
            - script_dir:              Directory containing the script, used for logging.
            - all_imports:             Set to be populated with all imports found.
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


def stayed_out_dir(options: run_options.Options, p: str | os.PathLike[str]) -> bool:
    """Check if the parent directory of path p contains any substrings from the stay_out_list."""
    p = ek.ensure_path(p)
    parent_str = os.fspath(p.parent)
    return any(sub in parent_str for sub in options.stay_out_list)


def get_all_imports(
    options: run_options.Options, directory: str | os.PathLike[str]
) -> None:
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


def run_script(
    interpreter: str | os.PathLike[str],
    script: str | os.PathLike[str],
    script_args: list[str],
    *,
    rawlog: bool,
    announce: bool = False,
) -> int:
    """Run the user's script and return its exit status.

    Args:
        interpreter: The python to run it with.
        script: The script itself.
        script_args: Everything after the script on veny's command line.
        rawlog: True suppresses veny's own commentary, so the output is what
            the user would have seen without veny.
        announce: True logs the command before running it, as the venv path
            has always done and the bare-interpreter paths never have.

    Returns:
        The child's returncode, negative if it was killed by a signal.
    """
    command_list = [os.fspath(interpreter), os.fspath(script)] + [
        str(arg) for arg in script_args
    ]
    if announce and not rawlog:
        logging.info(
            "Running command: %s", " ".join(shlex.quote(arg) for arg in command_list)
        )
    result = subprocess.run(command_list)
    return result.returncode


def resolve_target(options: run_options.Options) -> None:
    """Resolve the script argument onto options.

    Lifted from main(). The script path is resolved strictly, so a name that
    does not exist fails here rather than three stages later, and its parent
    becomes options.script_dir -- the directory every later stage searches for
    custom modules and last-used records.

    A run with no script leaves options.python_script as None; whether that is
    an error depends on the mode flags, which `run` decides.

    Args:
        options: The run's Options; options.python_script and
                 options.script_dir are set from options.args.script.
    """
    script_string = getattr(options.args, "script", None)
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


def feeling_lucky(options: run_options.Options) -> int | None:
    """Try the previous run's virtual environment without analyzing anything.

    This runs before logging is configured, which is why it reports with
    `print()` rather than `logging`: --feeling-lucky's whole point is to reach
    the user's script with as little of veny in the way as possible.

    Args:
        options: The run's Options; reads the --feeling-lucky flag,
                 options.python_script, options.script_dir,
                 options.pathlibcutoff, options.script_args and
                 options.rawlog.

    Returns:
        The script's exit status if the lucky path ran it, or None meaning
        "no luck, carry on with the normal run".
    """
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
            returncode = run_script(
                last_used_venv_python,
                options.python_script,
                options.script_args,
                rawlog=options.rawlog,
            )
            if returncode != 0 and not options.rawlog:
                print(f"Script exited with status {returncode}")
            return returncode
        else:
            if not options.rawlog:
                print(
                    "No luck: no last used virtual environment found. Running the script as normal."
                )
    return None


def blank_slate(options: run_options.Options) -> int:
    """Delete veny's state directory and its own dotfiles in the current directory.

    The filter is four OR'd name tests rather than a glob so that only files
    veny wrote can be removed: the user's own .json files in the working
    directory must survive.

    Args:
        options: The run's Options; reads options.my_dir, options.my_name,
                 options.cwd and the -y flag.

    Returns:
        0, whether the user confirmed or declined -- both are a complete run
        that was never going to launch a script.
    """
    if not getattr(options.args, "y", False):
        if not ek.prompt_then_confirm(
            f"Are you sure you want to delete everything in ~/{options.my_name}/"
            f" and all {options.my_name} .json files in the current directory? (y/n) "
        ):
            logging.info("Exiting without deleting anything.")
            return 0
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
    return 0


def report(options: run_options.Options) -> None:
    """Log what the scan and classification found, unless --rawlog silenced it.

    Args:
        options: The run's Options; reads options.uninstalled_imports,
                 options.bad_imports, options.samedir_files,
                 options.subfolders and options.rawlog.
    """
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


def _load_last_used(options: run_options.Options) -> ek.Options | None:
    """Load the previous run's options JSON, for the cache search's last-used pass.

    find_match_dir_in_cache takes this as an injected callable rather than
    reaching for last_used itself, so nothing below pipeline has to know what
    an Options is. The two asserts stay on this side of the injection and still
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


def setup_virtualenv(options: run_options.Options) -> bool:
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


def run(options: run_options.Options, *, start_time: dt.datetime | None = None) -> int:
    """Execute the run described by options and return the script's status.

    Args:
        options: The run's state, with argv already parsed onto it.
        start_time: What the two "Elapsed time" lines are measured from.
            `cli.main` takes it before argparse, which is where the whole run
            has always been timed from; the default keeps `run` callable on
            its own, timing only itself.

    Returns:
        The wrapped script's exit status, or 0 when nothing was meant to run,
        or 1 when veny could not find or build an environment.

    Raises:
        UsageError: The command line asked for something veny cannot act on.
        VenvBuildFailed: A virtual environment could not be created.
    """
    start_time = start_time or dt.datetime.now()
    script_exit_code = 0

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

    if options.python_script:
        pass  # If a script was provided as an argument, skip the rest of these checks.
    elif getattr(options.args, "blank_slate", False):
        return blank_slate(options)
    else:
        raise UsageError(
            "You must specify either a script to run or --blank-slate (be "
            "careful using --blank-slate because it deletes all cached virtual "
            "environments, among other things!)."
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
    options.custom_modules = custom_modules.dict_of_custom_modules(
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

    report(options)

    if getattr(options.args, "justprint", False):
        return 0

    if not options.uninstalled_imports:
        if not options.rawlog:
            logging.info("All required packages are already installed.")
        start_raw_time = dt.datetime.now()
        script_exit_code = run_script(
            sys.executable,
            options.python_script,
            options.script_args,
            rawlog=options.rawlog,
        )
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
            script_exit_code = run_script(
                sys.executable,
                options.python_script,
                options.script_args,
                rawlog=options.rawlog,
            )
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
            else:
                ek.my_critical_error(
                    "Failed to create a virtual environment.", choose_breakpoint=True
                )
                script_exit_code = 1
        else:
            if not options.rawlog:
                logging.info("Using existing virtual environment: %s", match_dir)

        if match_dir:
            options.set_venv_dir(match_dir)
            start_venv_time = dt.datetime.now()
            elapsed_time = start_venv_time - start_time
            if not options.rawlog:
                logging.info("Elapsed time: %s", elapsed_time)
            script_exit_code = run_script(
                options.venv_python,
                options.python_script,
                options.script_args,
                rawlog=options.rawlog,
                announce=True,
            )
            end_time = dt.datetime.now()
            elapsed_time = end_time - start_venv_time
            if not options.rawlog:
                logging.info(
                    "Elapsed time since activating virtual environment: %s",
                    elapsed_time,
                )
            if script_exit_code != 0 and not options.rawlog:
                logging.error("Script exited with status %d", script_exit_code)
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

    return script_exit_code
