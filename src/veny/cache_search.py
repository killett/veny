"""Choose a cached virtual environment, and record the state of a fresh one."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path

import emmykit as ek

from . import __version__, environment, stdlib_index, venv_cache, verify
from .alias_index import ResolvedImport


def interpreter_tag(stdlib: stdlib_index.StdlibIndex) -> str:
    """Return the "major.minor" tag of the interpreter this run is classified against.

    Taken from the standard-library index rather than probed again, so the tag in
    a venv's folder name, the tag in its manifest, and the version whose stdlib
    names decided what needed installing can never disagree.

    Args:
        stdlib: The standard-library index this run classified against.

    Returns:
        A tag such as "3.12".
    """
    major, minor = stdlib.python_version
    return f"{major}.{minor}"


_VERSION_PROBE_CODE = (
    "import json, sys\n"
    "from importlib.metadata import distributions\n"
    "print(json.dumps({"
    "'python': list(sys.version_info[:2]),"
    " 'versions': {d.metadata['Name']: d.version for d in distributions()"
    " if d.metadata['Name']}}))\n"
)


def installed_state_in_venv(
    venv_python: str | os.PathLike[str],
) -> tuple[dict[str, str], str]:
    """Ask a virtual environment which versions and interpreter it actually has.

    This is what the manifest records, rather than what was requested or what
    pip printed: only the venv itself knows what ended up installed, including
    versions pip chose for unpinned packages, and which interpreter it was
    actually built with.

    Args:
        venv_python: The interpreter inside the virtual environment to probe.

    Returns:
        A tuple of (versions, tag). versions maps normalized pip name to
        version, empty if the probe could not be run or its output could not
        be read -- a version veny could not read is recorded as unknown,
        which makes any later pin check on that package fail closed. tag is
        the venv's own "major.minor", or "" if the probe could not be run.
    """
    command = [os.fspath(venv_python), "-c", _VERSION_PROBE_CODE]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
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
    *,
    uninstalled: AbstractSet[ResolvedImport],
    extra_requirements: Mapping[str, str | None],
    timestamp: str,
    python_command: str,
    run_tag: str,
    versions: dict[str, str],
    venv_tag: str = "",
) -> venv_cache.Manifest:
    """Build the manifest describing a finished virtual environment.

    Args:
        uninstalled:        The records this venv was built for, after any
                            repairs.
        extra_requirements: The --reqs entries, as the user spelled them.
        timestamp:          The run's timestamp, recorded as the venv's
                            creation time.
        python_command:     The interpreter the venv was built with.
        run_tag:            The run's own "major.minor", used when the venv
                            could not be probed.
        versions:           Installed versions, keyed by normalized pip name.
        venv_tag:           The "major.minor" the venv's own interpreter
                            reported. Empty when the probe could not run, in
                            which case the run's own tag serves -- the
                            pre-existing behaviour, and the only case where
                            the tag can still disagree with interpreter_path.

    Returns:
        The manifest to write into the venv.
    """
    # extra_requirements is keyed by whatever spelling the user typed on the
    # command line, which need not match record.pip_name's spelling -- the
    # versions dict a line below is already keyed normalized, so this lookup
    # must be too. Normalized once here rather than per record.
    normalized_requirements = {
        venv_cache.normalize_pip_name(name): spec
        for name, spec in extra_requirements.items()
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
        for record in sorted(uninstalled, key=lambda r: r.pip_name)
    )
    return venv_cache.Manifest(
        schema_version=venv_cache.SCHEMA_VERSION,
        created=timestamp,
        veny_version=__version__,
        interpreter_tag=venv_tag or run_tag,
        interpreter_path=environment.venv_build_interpreter(python_command),
        packages=packages,
    )


def rename_venv(venv_dir: Path, new_name: str) -> Path:
    """Rename a virtual environment directory and fix the paths recorded inside it.

    A stdlib-built venv records its own location in pyvenv.cfg (uv-built venvs
    do not), so a rename that touches only the directory can leave a venv that
    points at a path that no longer exists. Two callers need this: dropping the
    "failed-" prefix once a run succeeds, and re-naming a venv whose package
    list changed when verify_and_repair_imports repaired a wrongly resolved pip
    name.

    Args:
        venv_dir: The virtual environment directory to rename.
        new_name: The directory's new name, not a path.

    Returns:
        The directory the venv now lives in -- `venv_dir` itself when the name
        was already the wanted one. Callers own recording it. Failure to
        rewrite a recorded path is logged, not raised: the venv has already
        moved and the run continues.
    """
    old_dir = venv_dir
    new_dir = old_dir.with_name(new_name)
    if new_dir == old_dir:
        return venv_dir
    old_dir.rename(new_dir)
    path = new_dir / "pyvenv.cfg"
    try:
        contents = path.read_text()
    except OSError as exc:
        logging.warning("Could not read %s after renaming the venv (%s).", path, exc)
        return new_dir
    updated = contents.replace(old_dir.name, new_dir.name)
    if updated == contents:
        return new_dir
    try:
        path.write_text(updated)
    except OSError as exc:
        logging.warning("Could not update %s after renaming the venv (%s).", path, exc)
    return new_dir


def record_venv_state(
    venv_dir: Path,
    *,
    venv_python: str | os.PathLike[str],
    venv_name: str,
    timestamp: str,
    run_tag: str,
    python_command: str,
    uninstalled: AbstractSet[ResolvedImport],
    extra_requirements: Mapping[str, str | None],
    rawlog: bool,
) -> Path:
    """Rename the venv if its folder name has drifted, then write its manifest.

    Two things can make the folder name written before installing wrong by the
    time this runs. verify_and_repair_imports can replace a record whose
    pip_name was wrong, so the name may list a package the venv does not have.
    And the folder name is built from the run's stdlib tag (`run_tag`) before
    the venv exists, while the manifest uses the venv's own probed tag -- if
    the probe interpreter degrades (or uv's resolution disagreed with what veny
    classified against), those two tags can differ. Either way the name is only
    a prefilter, but a stale one rejects a venv the manifest would accept -- so
    the name is brought back into agreement with the manifest here, using the
    same tag the manifest is about to record.

    Args:
        venv_dir:           The virtual environment directory as it stands now.
        venv_python:        The interpreter inside that venv, for the probe.
        venv_name:          The base name every folder name is built from.
        timestamp:          The run's timestamp.
        run_tag:            The run's own "major.minor".
        python_command:     The interpreter the venv was built with.
        uninstalled:        The records this venv was built for, after repairs.
        extra_requirements: The --reqs entries, as the user spelled them.
        rawlog:             Whether informational logging is suppressed.

    Returns:
        The directory the venv now lives in -- a new one if the folder name had
        drifted. Callers own recording it.
    """
    # Probed here, before build_folder_name, so the folder name and the
    # manifest can never disagree on which interpreter tag they record: both
    # come from this one call. Falls back to the run's own tag when the probe
    # could not run (empty venv_tag), matching manifest_for's fallback below.
    versions, venv_tag = installed_state_in_venv(venv_python)
    wanted_name = venv_cache.build_folder_name(
        venv_name=venv_name,
        interpreter_tag=venv_tag or run_tag,
        timestamp=timestamp,
        pip_names=[record.pip_name for record in uninstalled],
    )
    prefix = "failed-" if venv_dir.name.startswith("failed-") else ""
    if venv_dir.name != prefix + wanted_name:
        if not rawlog:
            logging.info(
                "This venv's packages or interpreter tag no longer match its "
                "folder name; renaming it to %s.",
                prefix + wanted_name,
            )
        venv_dir = rename_venv(venv_dir, prefix + wanted_name)
    venv_cache.write_manifest(
        venv_dir,
        manifest_for(
            uninstalled=uninstalled,
            extra_requirements=extra_requirements,
            timestamp=timestamp,
            python_command=python_command,
            run_tag=run_tag,
            versions=versions,
            venv_tag=venv_tag,
        ),
    )
    return venv_dir


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


def wanted_packages(
    uninstalled: AbstractSet[ResolvedImport],
    extra_requirements: Mapping[str, str | None],
) -> list[venv_cache.Wanted]:
    """Describe what this run needs, for matching against a cached venv.

    Args:
        uninstalled:        The records this run needs a venv to provide.
        extra_requirements: The --reqs entries, as the user spelled them.

    Returns:
        One entry per record, carrying its pip name and any --reqs spec.
    """
    # See manifest_for: extra_requirements' keys are user-typed spellings, not
    # necessarily record.pip_name's spelling, so the lookup must normalize both
    # sides. Built once per call rather than inside the list comprehension.
    normalized_requirements = {
        venv_cache.normalize_pip_name(name): spec
        for name, spec in extra_requirements.items()
    }
    return [
        venv_cache.Wanted(
            pip_name=record.pip_name,
            spec=normalized_requirements.get(
                venv_cache.normalize_pip_name(record.pip_name)
            ),
        )
        for record in sorted(uninstalled, key=lambda r: r.pip_name)
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


def cache_candidates(
    folders: list[Path],
    *,
    wanted: list[venv_cache.Wanted],
    tag: str,
    rawlog: bool,
) -> list[CacheCandidate]:
    """Filter cached venv folders down to those that can serve this run.

    The folder name is a cheap reject; veny_manifest.json is the decision. A
    folder with no readable manifest is skipped, which is what retires every
    virtual environment built before manifests existed.

    Args:
        folders: Candidate directories, already filtered by name prefix.
        wanted:  What this run needs, from wanted_packages.
        tag:     The run's "major.minor" interpreter tag.
        rawlog:  Whether informational logging is suppressed.

    Returns:
        The folders that match, in the order given, each paired with the
        parsed name and manifest already read while deciding.
    """
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
            if not rawlog:
                logging.info(
                    "Skipping the cached venv %s: it has no readable manifest.",
                    os.fspath(folder),
                )
            continue
        result = venv_cache.satisfies(manifest, wanted, tag)
        if not result.matched:
            if not rawlog:
                logging.info(
                    "Skipping the cached venv %s because %s.",
                    os.fspath(folder),
                    result.reason,
                )
            continue
        matches.append(CacheCandidate(folder=folder, parsed=parsed, manifest=manifest))
    return matches


def check_venv_dir(
    venv_dir: str | os.PathLike[str],
    *,
    wanted: list[venv_cache.Wanted],
    tag: str,
    uninstalled: AbstractSet[ResolvedImport],
    source_names: AbstractSet[str],
    rawlog: bool,
    matched_manifest: venv_cache.Manifest | None = None,
) -> bool:
    """Check whether a cached venv directory can serve this run.

    The venv's own manifest is the authority. An options JSON written by an
    earlier run says what that run wanted, not what the venv holds, and its
    records compare by exact spelling -- so a venv built when "yaml" resolved to
    "PyYAML" was rejected by a run spelling it "pyyaml". Asking the manifest puts
    every candidate, last-used or not, through one comparison.

    Args:
        venv_dir:         The cached virtual environment directory.
        wanted:           What this run needs, from wanted_packages.
        tag:              The run's "major.minor" interpreter tag.
        uninstalled:      The records whose imports must really import.
        source_names:     The import names actually written in the user's
                          source.
        rawlog:           Whether informational logging is suppressed.
        matched_manifest: The venv's manifest, ALREADY read and ALREADY
                          checked against this same wanted/tag by
                          venv_cache.satisfies -- as cache_candidates does for
                          every folder it returns. When given, this call
                          trusts that check and goes straight to the
                          import-level confirmation: it neither re-reads the
                          manifest from disk nor calls satisfies again.
                          Passing a manifest that has NOT already passed that
                          same check (for instance one read directly from
                          disk without matching it first) silently skips the
                          match check entirely -- do not do that. Callers
                          with no such pre-matched manifest, such as the
                          last-used path, which has no CacheCandidate to hand
                          over, must leave this None; the manifest is then
                          read from venv_dir and checked with satisfies here,
                          exactly as when this parameter did not exist.

    Returns:
        True if the venv holds what this run needs, for the right interpreter,
        and its imports really import.
    """
    venv_dir = ek.ensure_path(venv_dir)
    if not ek.safe_is_dir(venv_dir):
        if not rawlog:
            logging.info(
                "The cached venv directory %s is no longer there.", os.fspath(venv_dir)
            )
        return False
    if matched_manifest is None:
        manifest = venv_cache.read_manifest(venv_dir)
        if manifest is None:
            if not rawlog:
                logging.info(
                    "The cached venv directory %s has no readable manifest.",
                    os.fspath(venv_dir),
                )
            return False
        result = venv_cache.satisfies(manifest, wanted, tag)
        if not result.matched:
            if not rawlog:
                logging.info(
                    "The cached venv directory %s cannot be used because %s.",
                    os.fspath(venv_dir),
                    result.reason,
                )
            return False
    # The manifest match is confirmed either just above, or already by the
    # caller's own satisfies() check when matched_manifest was supplied (see
    # the docstring -- that trust is the whole point of the parameter: it is
    # what lets the winning candidate's manifest be checked once, not twice).
    # This is the import-level confirmation: source_names is now always
    # passed explicitly, since verify's empty default cannot work it out for
    # itself, and an empty set here would silently widen every check to the
    # distribution's whole top-level list.
    if verify.check_packages_in_venv(
        environment.venv_python_for(venv_dir),
        uninstalled=uninstalled,
        source_names=source_names,
    ):
        return True
    logging.error(
        "The cached venv directory %s failed check_packages_in_venv.",
        os.fspath(venv_dir),
    )
    return False


def find_match_dir_in_cache(
    args: argparse.Namespace,
    *,
    my_dir: Path,
    venv_name: str,
    uninstalled: AbstractSet[ResolvedImport],
    extra_requirements: Mapping[str, str | None],
    source_names: AbstractSet[str],
    tag: str,
    rawlog: bool,
    load_last_used: Callable[[], ek.Options | None],
) -> Path | None:
    """Try to find a matching virtual environment directory in the cache.

    Args:
        args:               The parsed command-line arguments. Read *and
                            written*: the --latest/--last-used flags are
                            resolved in place, and those writes reach the
                            options JSON the run saves.
        my_dir:             The directory the cached venvs live in.
        venv_name:          The base name every cached folder starts with.
        uninstalled:        The records this run needs a venv to provide.
        extra_requirements: The --reqs entries, as the user spelled them.
        source_names:       The import names actually written in the source.
        tag:                The run's "major.minor" interpreter tag.
        rawlog:             Whether informational logging is suppressed.
        load_last_used:     Loads the previous run's options, or returns None
                            when there is no usable last-used JSON.

    Returns:
        The path to the matching virtual environment directory if found, otherwise None.

    Raises:
        None, but logs errors if the combination of flags is invalid, if no matching venv is found,
        or if the cached venv is invalid.
    """
    wanted = wanted_packages(uninstalled, extra_requirements)
    if (
        not getattr(args, "latest", False)
        and not getattr(args, "oldest", False)
        and not getattr(args, "last_used", False)
        and not getattr(args, "smallest", False)
    ):
        args.last_used = True  # If no flags are set, then the default is to load the last used venv in the cache
    if (
        getattr(args, "last_used", False)
        and not getattr(args, "latest", False)
        and not getattr(args, "smallest", False)
    ):
        options_last_used = load_last_used()
        # venv_dir is declared in veny.Options.__init__, not in the base
        # emmykit.Options that load_last_used_options builds from, so a
        # last-used JSON written without that key must not raise here.
        venv_dir_last_used = getattr(options_last_used, "venv_dir", None)
        if (
            options_last_used is not None
            and venv_dir_last_used is not None
            and check_venv_dir(
                venv_dir_last_used,
                wanted=wanted,
                tag=tag,
                uninstalled=uninstalled,
                source_names=source_names,
                rawlog=rawlog,
            )
        ):
            return ek.ensure_path(venv_dir_last_used)
        else:
            if not rawlog:
                logging.info("Trying to load the latest matching venv now.")
        args.latest = (
            True  # If that didn't work, try to load the latest venv in the cache
        )
        args.last_used = False  # And set this to False because it failed
    if not rawlog:
        logging.info(
            "Checking the cache for a virtual environment with all the required packages..."
        )
    all_venv_folders = [
        f
        for f in my_dir.iterdir()
        if ek.safe_is_dir(f) and f.name.startswith(venv_name)
    ]
    final_venv_folders: dict[Path, dict[str, int]] = {}
    candidates_by_folder: dict[Path, CacheCandidate] = {}
    for candidate in cache_candidates(
        all_venv_folders, wanted=wanted, tag=tag, rawlog=rawlog
    ):
        final_venv_folders[candidate.folder] = {
            "timestamp": int(candidate.parsed.timestamp.replace("-", "")),
            "num_packages": len(candidate.manifest.packages),
        }
        candidates_by_folder[candidate.folder] = candidate
    if not final_venv_folders:
        if not rawlog:
            logging.info("No matching venv folders found in the cache.")
    else:
        if not rawlog:
            logging.info(
                "Found %d matching venv folders in the cache.", len(final_venv_folders)
            )
        if (
            getattr(args, "latest", False)
            and not getattr(args, "oldest", False)
            and not getattr(args, "last_used", False)
            and not getattr(args, "smallest", False)
        ):
            # Return the latest venv in the cache which has all the packages needed now
            latest_venv_folder: Path | None = latest_venv(final_venv_folders)
            if latest_venv_folder is None:
                if not rawlog:
                    logging.error(
                        "Could not determine the latest venv folder from the cache."
                    )
                return None
            if check_venv_dir(
                latest_venv_folder,
                wanted=wanted,
                tag=tag,
                uninstalled=uninstalled,
                source_names=source_names,
                rawlog=rawlog,
                matched_manifest=candidates_by_folder[latest_venv_folder].manifest,
            ):
                return latest_venv_folder
            if not rawlog:
                logging.error(
                    "The latest venv in the cache is invalid. Giving up on the cache and starting from scratch."
                )
            return None
        elif (
            getattr(args, "oldest", False)
            and not getattr(args, "latest", False)
            and not getattr(args, "last_used", False)
            and not getattr(args, "smallest", False)
        ):
            # Return the oldest venv in the cache which has all the packages needed now
            oldest_venv_folder: Path | None = oldest_venv(final_venv_folders)
            if oldest_venv_folder is None:
                if not rawlog:
                    logging.error(
                        "Could not determine the oldest venv folder from the cache."
                    )
                return None
            if check_venv_dir(
                oldest_venv_folder,
                wanted=wanted,
                tag=tag,
                uninstalled=uninstalled,
                source_names=source_names,
                rawlog=rawlog,
                matched_manifest=candidates_by_folder[oldest_venv_folder].manifest,
            ):
                return oldest_venv_folder
            if not rawlog:
                logging.error(
                    "The oldest venv in the cache is invalid. Giving up on the cache and starting from scratch."
                )
            return None
        elif (
            getattr(args, "smallest", False)
            and not getattr(args, "latest", False)
            and not getattr(args, "oldest", False)
            and not getattr(args, "last_used", False)
        ):
            # Return the smallest venv in the cache which has all the packages needed now
            smallest_venv_folder: Path | None = smallest_venv(final_venv_folders)
            if smallest_venv_folder is None:
                if not rawlog:
                    logging.error(
                        "Could not determine the smallest venv folder from the cache."
                    )
                return None
            if check_venv_dir(
                smallest_venv_folder,
                wanted=wanted,
                tag=tag,
                uninstalled=uninstalled,
                source_names=source_names,
                rawlog=rawlog,
                matched_manifest=candidates_by_folder[smallest_venv_folder].manifest,
            ):
                return smallest_venv_folder
            if not rawlog:
                logging.error(
                    "The smallest venv in the cache is invalid. Giving up on the cache and starting from scratch."
                )
            return None
        else:  # This should never happen
            logging.error(
                f"Invalid combination of flags!\n"
                f"{getattr(args, 'latest',    False) = }\n"
                f"{getattr(args, 'oldest',    False) = }\n"
                f"{getattr(args, 'last_used', False) = }\n"
                f"{getattr(args, 'smallest',  False) = }"
            )
    return None
