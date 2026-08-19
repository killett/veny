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
import logging
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import emmykit as ek

from . import alias_index, classify, environment, run_options, stdlib_index, verify
from .analysis import scan as analysis_scan
from .analysis.scan_state import ImportScan
from .settings import Settings


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
