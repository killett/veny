"""Find the local modules a script imports that are not on PyPI."""

import datetime as dt
import logging
import os
import pickle
import sys
from functools import lru_cache
from pathlib import Path

import emmykit as ek

from ..settings import Settings

STANDARD_LIB_PATHS: tuple[Path, ...] = (
    Path("/") / "usr" / "lib",
    Path("/") / "usr" / "local" / "lib",
    Path("/") / "usr" / "lib64",
    Path("/") / "usr" / "local" / "lib64",
)

STANDARD_LIB_NAMES: tuple[str, ...] = ("lib", "lib64")


def is_standard_path(settings: Settings, path: str | os.PathLike[str]) -> bool:
    """Check if the given path is a standard system path or part of a virtual environment."""
    p = ek.ensure_path(path)
    # Check if path is inside standard system paths
    for std_path in STANDARD_LIB_PATHS:
        if p.is_relative_to(std_path):  # Python 3.9+
            return True
    # Check if path contains anything in stay_out_list
    p_str = os.fspath(p)
    if any(s in p_str for s in settings.stay_out_list):
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


def only_search_here_filename_boolean(
    filename: str | os.PathLike[str], thestring: str
) -> bool:
    """Check if the given filename contains thestring, which is used to determine if the search is limited to the current directory."""
    return thestring in os.fspath(filename)


def search_anywhere_filename_boolean(
    filename: str | os.PathLike[str], thestring: str
) -> bool:
    """Check if the given filename does NOT contain thestring. By default, those files are assumed to have been created by searching above the current directory."""
    return thestring not in os.fspath(filename)


def only_search_here_path_boolean(
    settings: Settings, path: str | os.PathLike[str]
) -> bool:
    """Check if the given path is in the current directory."""
    return Path(path).absolute().is_relative_to(settings.cwd)


def search_anywhere_path_boolean(
    settings: Settings, path: str | os.PathLike[str]
) -> bool:
    """Return True regardless.

    Takes the same two parameters as its `only_search_here_path_boolean`
    sibling, unused, on purpose: the two are interchangeable through
    `dict_of_custom_modules`'s strategy dispatch, which calls whichever one
    it selected with the same argument list. Do not drop these parameters.
    """
    return True


def dict_of_custom_modules(settings: Settings, *, use_cache: bool) -> dict[str, Path]:
    """Create (or load) a dictionary of all local custom modules in the non-standard sys.path directories and their associated filepaths.

    Args:
        settings: The frozen run invariants this discovery reads.
        use_cache: Whether to look for and reuse a pickle file left by a
            previous run. The call site derives this from the `--rc` and
            `--no-cache` flags; this function never sees flags itself.

    Returns:
        A mapping of local module name to its file path.
    """
    # If use_cache is True, look for a pickle file with the custom modules dictionary from the last time this script was run.

    # I.f.f. settings.search_above_this_dir is True, then search above the current directory for custom modules.
    # Either way, only load custom module pickle files that searched in the same places as requested.
    search_above_text_to_match = "only_search_here_"  # For legacy reasons, custom module pickle files are assumed to have searched above the current directory unless this text is present in the filename.
    if settings.search_above_this_dir:
        search_above_text_to_write = (
            "_"  # This will be added to the filename of the custom modules pickle file.
        )
        search_constraint_filename_boolean = search_anywhere_filename_boolean
        search_constraint_path_boolean = search_anywhere_path_boolean
    else:
        search_above_text_to_write = search_above_text_to_match  # This will be added to the filename of the custom modules pickle file.
        search_constraint_filename_boolean = only_search_here_filename_boolean
        search_constraint_path_boolean = only_search_here_path_boolean

    log = (
        logging.getLogger()
    )  # Prebind the logger to avoid repeated global lookups in hot loop
    if log.isEnabledFor(logging.DEBUG):
        logging.debug(
            "Searching for custom modules pickle files with constraint: search_above_text_to_match = %s",
            search_above_text_to_match,
        )
    if use_cache:
        try:
            potential_files = [
                file
                for file in settings.cwd.iterdir()
                if file.name.startswith(f".{settings.my_name}_custom_modules_")
                and file.suffix.casefold() == ".pkl"
                and ek.COMPUTER_NAME in file.name
                and search_constraint_filename_boolean(
                    file.name, search_above_text_to_match
                )
            ]
            if not potential_files:
                if not settings.rawlog:
                    logging.info(
                        "No existing custom modules pickle files found in the current directory."
                    )
            else:
                # If multiple files are found, pick the most recent one based on the timestamp in the filename.
                potential_files_with_timestamps: list[tuple[Path, str]] = [
                    (file, ts)
                    for file in potential_files
                    if (ts := ek.extract_timestamp(file.name)) is not None
                ]
                if not potential_files_with_timestamps:
                    if not settings.rawlog:
                        logging.info(
                            "No valid timestamps found in custom modules pickle filenames."
                        )
                else:
                    # Sort by timestamp descending
                    potential_files_with_timestamps.sort(
                        key=lambda x: x[1], reverse=True
                    )
                    most_recent_file = potential_files_with_timestamps[0][0]
                    if not settings.rawlog:
                        logging.info(
                            "Loading custom modules from most recent pickle file: %s",
                            most_recent_file,
                        )
                    with open(most_recent_file, "rb") as f:
                        # This pickle is veny's own module cache, written and read
                        # by veny alone -- not untrusted input.
                        loaded_modules = pickle.load(f)  # noqa: S301
                    # Pickles written before 2025-08-10 hold str, later ones
                    # hold Path; ek.ensure_path answers for both, which is why
                    # the date comparison that used to pick between two arms
                    # was deleted with veny's other pathlib cutoff.
                    normalized: dict[str, Path] = {
                        k: (v if isinstance(v, Path) else ek.ensure_path(v))
                        for k, v in loaded_modules.items()
                    }
                    return normalized
        except Exception:
            logging.exception("Error loading custom modules from pickle file.")
            logging.error(
                "Falling back to regenerating the custom modules dictionary from sys.path."
            )

    custom_modules: dict[str, Path] = {}
    package_dirs: set[Path] = set()  # directories confirmed to be packages

    # Use lru_cache to speed up repeated calls to is_standard_path()
    @lru_cache(maxsize=8192)
    def _is_std_path_cached(p: str | os.PathLike[str]) -> bool:
        """Check if a path is a standard library path. Cached for speed."""
        return is_standard_path(settings, p)

    # Prebind a few globals/attributes to locals before os.walk to cut repeated global lookups:
    is_std = _is_std_path_cached
    endswith_ext = ek.PYTHON_EXTENSIONS
    safe_is_file = ek.safe_is_file
    safe_is_dir = ek.safe_is_dir

    if log.isEnabledFor(logging.DEBUG):
        logging.debug("Generating custom modules dictionary from sys.path...")
    for path in map(Path, sys.path):
        if (
            not is_std(path)
            and safe_is_dir(path)
            and search_constraint_path_boolean(settings, path)
        ):
            if log.isEnabledFor(logging.DEBUG):
                logging.debug("Checking path: %s", path)

            # Prebind a few globals/attributes to locals before os.walk to cut repeated global lookups:
            setdefault_mod = custom_modules.setdefault
            package_dirs_add = package_dirs.add
            # Suppress any remaining (permissions related?) walking errors with onerror = ... None
            for root, dirs, files in os.walk(
                path, topdown=True, onerror=(lambda e: None)
            ):
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
    custom_filename = f".{settings.my_name}_custom_modules_{ek.COMPUTER_NAME}{search_above_text_to_write}{current_time}.pkl"
    with open(custom_filename, "wb") as f_out:
        if not settings.rawlog:
            logging.info("Saving custom modules to %s", custom_filename)
        pickle.dump(
            custom_modules, f_out, protocol=pickle.HIGHEST_PROTOCOL
        )  # Use highest protocol for efficiency because we don't need backward compatibility for caching purposes
    return custom_modules
