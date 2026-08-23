"""The run: analyze, classify, acquire an environment, run the script.

This module owns sequencing and is the only one that knows the order. Every
module below it does one thing and is handed what it needs; `cli.py` above it
parses argv and maps what happens here onto an exit status.

Each stage is handed the values it needs and hands back its product: `Settings`
for the run's invariants, `Target` for what is being run, `ImportScan` for what
the scan found, `Requirements` for what classification decided, and
`VenvHandle` for the environment. Nothing here writes its product onto the
object it was handed -- the one exception is `ImportScan`, which is an
accumulator by design and which `analysis/scan.py` mutates in place as it
walks. Phase 4a introduced those values and phase 4b deleted the per-run state
object they replaced, so this module now carries no carrier at all.

Persistence is veny's own too: `run` writes a `state.LastUsed` record through
`last_used.save`, and both readers -- `_load_last_used` for the cache search's
last-used pass and `feeling_lucky` for the `--feeling-lucky` shortcut -- take
that record back.

Everything here calls its collaborators through the module object
(`verify.check_packages_in_venv(...)`, never `from .verify import ...`), which
is what lets a test replace one boundary without rebuilding the world.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import logging
import os
import re
import shlex  # For safely quoting shell commands
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping

import emmykit as ek

from . import (
    alias_index,
    cache_search,
    classify,
    environment,
    last_used,
    state,
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


def build_alias_index(
    settings: Settings, args: argparse.Namespace, python_command: str
) -> alias_index.AliasIndex:
    """Rebuild the alias index against the interpreter that will run the user's script.

    An index built before the target interpreter is known is tagged with
    *veny's own* interpreter version; leaving that in place would let a cache
    entry recorded under one Python version short-circuit resolution for a
    target on another.

    Args:
        settings: The run's invariants; reads my_dir
        args: The parsed command line; reads the --offline flag.
        python_command: The interpreter the resolver probes.

    Returns:
        An index for the target interpreter, offline if the user asked for it.

    Raises:
        AliasOverrideError: If the override file exists but cannot be read.
    """
    return alias_index.build(
        python_command,
        settings.my_dir,
        offline=getattr(args, "offline", False),
    )


def find_imports_in_script(
    settings: Settings,
    scan: ImportScan,
    first_path: str | os.PathLike[str],
    *,
    is_stdlib: Callable[[str], bool],
) -> None:
    """Scan a script for imports, accumulating into the given ImportScan.

    The scan is mutated in place rather than returned: analysis/scan.py only
    ever calls .add / .append / `d[k] = v` on it and never rebinds a field,
    and it recurses through the script's local modules relying on all seven
    fields carrying across those calls.

    Seeding is why the scan is passed in rather than built here.
    dict_of_custom_modules() fills scan.custom_modules before list_packages
    ever reaches this function, and the scanner reads that dict to tell a
    local module from a PyPI package -- an empty one makes every local module
    look like a package veny should pip install.

    The Settings is passed in for the same reason. Building a second one was
    what made four of its five fields dead at this call site: the scanner
    reads only `rawlog`, while the other consumer reads the other four.

    Args:
        settings: The run's invariants; the scanner reads rawlog.
        scan: The accumulator to write into.
        first_path: The script to scan.
        is_stdlib: Predicate answering whether a name is standard library.
    """
    analysis_scan.find_imports_in_script(
        settings, first_path, is_stdlib=is_stdlib, scan=scan
    )


def warn_about_system_packages(scan: ImportScan) -> None:
    """Warn once for each standard-library import that needs an OS package.

    Args:
        scan: The run's ImportScan; reads seen_stdlib_imports.
    """
    for name, system_package in stdlib_index.hints_for(
        scan.seen_stdlib_imports
    ).items():
        logging.warning(
            "%s is in the standard library but needs the %s system package "
            "before it will import.",
            name,
            system_package,
        )


@contextlib.contextmanager
def _probe_venv(target: state.Target) -> Iterator[Callable[[str], bool]]:
    """Build a throwaway venv and yield a predicate that imports names in it.

    A context manager, not a plain callable, because classification must only
    pay for the environment once it knows there is something to classify: a run
    with no imports leaves this unentered and builds nothing.

    Args:
        target: The run's Target; reads python_command.

    Yields:
        A predicate answering whether one import name imports in the venv.

    Raises:
        VenvBuildFailed: uv refused to build the throwaway environment, so
            there is no environment to answer the question in at all.
    """
    with tempfile.TemporaryDirectory() as venv_dir:
        if not environment.create_venv(
            venv_dir, environment.venv_build_interpreter(target.python_command)
        ):
            raise VenvBuildFailed(
                "Could not build the throwaway environment used to check which "
                "imports are already available."
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


def split_imports(
    settings: Settings,
    scan: ImportScan,
    target: state.Target,
    *,
    args: argparse.Namespace,
    aliases: alias_index.AliasIndex,
    extra_requirements: Mapping[str, str | None],
) -> state.Requirements:
    """Classify the scan's imports and return the result.

    A value, not an accumulator: nothing downstream writes to it. The
    copy-back onto the old `Options` this used to end with is gone, along
    with the frozenset-to-set conversions it did so that later stages could
    mutate that object's uninstalled-imports set in place.
    verify_and_repair_imports' result is folded in with dataclasses.replace
    instead.

    Args:
        settings: The run's invariants; supplies known_bad_imports,
            also_needs and rawlog.
        scan: What the scan found. Read, never written.
        target: The run's Target; the probe environment is built against its
            python_command.
        args: The parsed command line; reads --reqs.
        aliases: The alias index. Mutable and injected by design -- it is a
            cache with disk backing plus a separate session-rejection store.
        extra_requirements: The --reqs file's entries, or {}.

    Returns:
        What classification decided about this run's imports.
    """
    return classify.split_imports(
        scan,
        aliases=aliases,
        known_bad_imports=settings.known_bad_imports,
        also_needs=settings.also_needs,
        extra_requirements=extra_requirements,
        use_reqs=getattr(args, "reqs", False),
        probe=_probe_venv(target),
        rawlog=settings.rawlog,
    )


def list_packages(
    settings: Settings,
    scan: ImportScan,
    target: state.Target,
    *,
    args: argparse.Namespace,
    aliases: alias_index.AliasIndex,
    extra_requirements: Mapping[str, str | None],
    is_stdlib: Callable[[str], bool],
) -> tuple[ImportScan, state.Requirements]:
    """Scan the target script for imports, then classify them.

    Folder scanning was deleted here on 2026-08-21 (user ruling). It had been
    unreachable since 3e deleted --full: the script path is produced in
    exactly one production place, resolve_target, and that goes through
    ek.ensure_file, which refuses a directory. The only test that reached the
    directory arms did so by writing the script path onto the old per-run
    state object directly.

    Args:
        settings: The run's invariants; reads rawlog.
        scan: The accumulator, already seeded with the custom-module dict.
        target: The run's Target; supplies the script to scan.
        args: The parsed command line; reads --reqs.
        aliases: The run's alias index.
        extra_requirements: The --reqs file's entries, or {}.
        is_stdlib: Predicate answering whether a name is standard library.

    Returns:
        The filled ImportScan -- the same object, so callers read a value
        rather than reaching back into what they passed -- and what
        classification decided about it.

    Raises:
        UsageError: The target is not a Python script veny can read.
    """
    python_file = target.python_script
    if not ek.safe_is_file(python_file) or not ek.is_python_script(python_file):
        raise UsageError(f"'{os.fspath(python_file)}' is not a valid Python script.")
    if not settings.rawlog:
        logging.info("Processing a single Python script: %s", os.fspath(python_file))
    find_imports_in_script(settings, scan, python_file, is_stdlib=is_stdlib)

    # Filter out invalid imports before splitting. This is the one field
    # rebound rather than mutated in place, and it is safe only because the
    # scanner has finished by now -- do not move the filter earlier.
    scan.all_imports = {
        imp for imp in scan.all_imports if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", imp)
    }

    requirements = split_imports(
        settings,
        scan,
        target,
        args=args,
        aliases=aliases,
        extra_requirements=extra_requirements,
    )
    return scan, requirements


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
        announce: True logs the command before running it. Every call site
            passes True since phase 4c; the default stays False so a new
            caller has to say what it wants.

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


def resolve_target(args: argparse.Namespace) -> state.Target | None:
    """Resolve the script argument into a Target.

    The script path is resolved strictly, so a name that does not exist fails
    here rather than three stages later. Its parent becomes script_dir -- the
    directory every later stage searches for custom modules and last-used
    records.

    Args:
        args: The parsed command line. Reads `script` and `script_args`.

    Returns:
        The run's Target, or None when no script was named. A scriptless run
        is not an error here; `run` decides whether the mode flags allow it.

    Raises:
        UsageError: The positional argument is a directory, or is not a file
            veny can read. Both used to travel out of main() as tracebacks.
    """
    script_string = getattr(args, "script", None)
    if script_string is None:
        return None
    try:
        python_script = ek.ensure_file(script_string, raise_on_empty=True).resolve(
            strict=True
        )
    except IsADirectoryError as exc:
        # veny runs a script, not a tree. Folder scanning was deleted in
        # phase 4a (user ruling, 2026-08-21): --full was its only producer of
        # a directory, and 3e's deletion of --full made every directory arm
        # unreachable. IsADirectoryError is a subclass of OSError, so this
        # clause must stay above the next one.
        raise UsageError(
            f"{script_string} is a directory. veny runs a single Python "
            f"script; name the script itself."
        ) from exc
    except (OSError, ValueError) as exc:
        # ek.ensure_file raises FileNotFoundError for a missing path and
        # ValueError for a symlink or an empty file. All three reached the
        # user as a traceback before phase 4a.
        raise UsageError(f"{script_string} is not a file veny can run.") from exc
    script_dir = python_script.parent.absolute()
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Directory where the script to run is located: %s", os.fspath(script_dir)
        )
    return state.Target(
        python_script=python_script,
        script_dir=script_dir,
        script_args=tuple(getattr(args, "script_args", []) or []),
        python_command="",
        timestamp=dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
    )


def feeling_lucky(
    args: argparse.Namespace,
    target: state.Target | None,
    *,
    my_name: str,
    rawlog: bool,
) -> int | None:
    """Try the previous run's virtual environment without analyzing anything.

    This runs before logging is configured, which is why it reports with
    `print()` rather than `logging`: --feeling-lucky's whole point is to reach
    the user's script with as little of veny in the way as possible.

    Args:
        args: The parsed command line; reads the --feeling-lucky flag.
        target: The run's Target, or None for a scriptless run.
        my_name: The program's own name, for the record's filename.
        rawlog: True suppresses veny's own commentary.

    Returns:
        The script's exit status if the lucky path ran it, or None meaning
        "no luck, carry on with the normal run".
    """
    if not getattr(args, "feeling_lucky", False) or target is None:
        return None
    last_used_venv_python = last_used.load_venv_python(
        script_dir=target.script_dir,
        python_script=target.python_script,
        my_name=my_name,
        rawlog=rawlog,
    )
    if last_used_venv_python:
        returncode = run_script(
            last_used_venv_python,
            target.python_script,
            list(target.script_args),
            rawlog=rawlog,
            announce=True,
        )
        if returncode != 0 and not rawlog:
            print(f"Script exited with status {returncode}")
        return returncode
    if not rawlog:
        print(
            "No luck: no last used virtual environment found. Running the script as normal."
        )
    return None


def blank_slate(settings: Settings, args: argparse.Namespace) -> int:
    """Delete veny's state directory and its own dotfiles in the current directory.

    The filter is four OR'd name tests rather than a glob so that only files
    veny wrote can be removed: the user's own .json files in the working
    directory must survive.

    Args:
        settings: The run's invariants; reads my_name, my_dir and cwd.
        args: The parsed command line; reads the --yes flag.

    Returns:
        0, whether the user confirmed or declined -- both are a complete run
        that was never going to launch a script.
    """
    if not args.yes:
        if not ek.prompt_then_confirm(
            f"Are you sure you want to delete everything in ~/{settings.my_name}/"
            f" and all {settings.my_name} .json files in the current directory? (y/n) "
        ):
            logging.info("Exiting without deleting anything.")
            return 0
    logging.info(
        "Deleting everything in ~/%s/ and all %s .out and .err and .json and .pkl files in the current directory.",
        settings.my_name,
        settings.my_name,
    )
    shutil.rmtree(settings.my_dir, ignore_errors=True)
    for file in settings.cwd.iterdir():
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Checking %s", file)
        if ek.safe_is_file(file):
            if (
                (
                    file.name.startswith(f".{settings.my_name}-")
                    and file.suffix.casefold() == ".out"
                )
                or (
                    file.name.startswith(f".{settings.my_name}-")
                    and file.suffix.casefold() == ".err"
                )
                or (
                    file.name.startswith(f".{settings.my_name}_custom_modules_")
                    and file.suffix.casefold() == ".pkl"
                )
                or (
                    file.name.startswith(".")
                    and f"-{settings.my_name}-" in file.name
                    and file.suffix.casefold() == ".json"
                )
            ):
                try:
                    logging.info("Deleting %s", file)
                    file.unlink()
                except BaseException:
                    logging.exception("Error deleting %s", file)
    return 0


def report(
    settings: Settings, scan: ImportScan, requirements: state.Requirements
) -> None:
    """Log what the scan and classification found, unless --rawlog silenced it.

    Args:
        settings: The run's invariants; reads rawlog.
        scan: What the scan found; reads samedir_files and subfolders.
        requirements: What classification decided; reads uninstalled and bad.
    """
    if not settings.rawlog:
        # Report the import names, which are what the user wrote in their source.
        logging.info(
            "Uninstalled imports: %s",
            sorted(record.import_name for record in requirements.uninstalled),
        )
        if requirements.bad:
            logging.warning("Bad imports: %s", set(requirements.bad))
        warn_about_system_packages(scan)
        if scan.samedir_files:
            logging.info(
                "Imported files in the same directory as the script: %s",
                list(map(os.fspath, scan.samedir_files)),
            )
        if scan.subfolders:
            logging.info("Imported subfolders: %s", scan.subfolders)


def _load_last_used(
    target: state.Target,
    *,
    my_name: str,
    rawlog: bool,
) -> state.LastUsed | None:
    """Load the previous run's record, for the cache search's last-used pass.

    find_match_dir_in_cache takes this as an injected callable rather than
    reaching for last_used itself, so nothing below pipeline has to know
    where the record lives.

    Args:
        target:  The run's Target; supplies script_dir and python_script.
        my_name: The program's own name, for the record's filename.
        rawlog:  True suppresses veny's own commentary.

    Returns:
        The previous run's record, or None when there is no usable one.
    """
    return last_used.load(
        script_dir=target.script_dir,
        python_script=target.python_script,
        my_name=my_name,
        rawlog=rawlog,
    )


def setup_virtualenv(
    settings: Settings,
    target: state.Target,
    requirements: state.Requirements,
    *,
    args: argparse.Namespace,
    aliases: alias_index.AliasIndex,
    stdlib: stdlib_index.StdlibIndex,
) -> tuple[state.Requirements, state.VenvHandle | None, bool]:
    """Setup a virtual environment and install packages.

    Args:
        settings: The run's invariants; supplies my_dir, venv_name and rawlog.
        target: The run's Target; supplies python_command and timestamp.
        requirements: What classification decided. Read for what to install,
            and returned again with the repair pass folded in.
        args: The parsed command line; reads --reqs.
        aliases: The alias index the repair pass records its findings in.
        stdlib: The run's standard-library index, for the interpreter tag.

    Returns:
        Three values: the requirements after the repair pass; the handle for
        the environment, or None if there is no usable one -- uv refused to
        build it, or a requirement could not be made importable in it, which
        is what `setup_virtualenv` returning False used to mean and what
        `pipeline.run` reports as status 1; and whether every requirement
        installed, which `run` needs separately because it decides the
        "failed-" rename even on the success path.
    """
    # The folder name is a cheap prefilter for the cache search; veny_manifest.json
    # inside the venv is the authority. venv_cache owns the encoding so a
    # hyphenated pip name cannot be mistaken for a field separator.
    run_tag = cache_search.interpreter_tag(stdlib)
    folder_name = venv_cache.build_folder_name(
        venv_name=settings.venv_name,
        interpreter_tag=run_tag,
        timestamp=target.timestamp,
        pip_names=[record.pip_name for record in requirements.uninstalled],
    )
    # Create a virtual environment directory that starts with "failed" in case the process fails. Only remove the "failed" part if this process completes successfully.
    handle = state.VenvHandle.for_dir(settings.my_dir / f"failed-{folder_name}")

    if not settings.rawlog:
        logging.info("Creating virtual environment...")
    if not environment.create_venv(
        handle.venv_dir, environment.venv_build_interpreter(target.python_command)
    ):
        logging.error(
            "uv could not create the virtual environment at %s.", handle.venv_dir
        )
        return requirements, None, False
    if not settings.rawlog:
        logging.info("Virtual environment created.")

    # `uv venv` refuses to build into a directory that already exists AND is
    # non-empty. VenvHandle.for_dir above already created the directory
    # (mkdir), so the requirements file must not land inside it until
    # create_venv has already succeeded against that (empty) directory --
    # writing it earlier made every fresh build crash with CalledProcessError.
    environment.write_requirements_file_with_extras(
        handle.requirements_file,
        (record.pip_name for record in requirements.uninstalled),
        requirements.extra_requirements,
    )

    result = environment.run_uv_pip(
        handle.venv_python, "install", "-r", os.fspath(handle.requirements_file)
    )
    install_succeeded = result is not None and result.returncode == 0
    if not install_succeeded:
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
        set(requirements.all_imports),
        requirements.extra_requirements,
        getattr(args, "reqs", False),
    )
    # The two "load-bearing" re-narrowing asserts that stood here are gone:
    # VenvHandle's fields are non-optional Paths, so there is nothing left for
    # mypy to lose across the intervening calls.
    #
    # What follows is a rebind, not a mutation: Requirements is a value, so
    # the pre-repair one still describes what was first attempted. The
    # manifest below is written from the post-repair value on purpose -- it
    # must record what really provided each import.
    requirements = dataclasses.replace(
        requirements,
        uninstalled=frozenset(
            verify.verify_and_repair_imports(
                venv_python=handle.venv_python,
                requirements_file=handle.requirements_file,
                uninstalled=set(requirements.uninstalled),
                extra_requirements=requirements.extra_requirements,
                source_names=source_names,
                index=aliases,
                rawlog=settings.rawlog,
            )
        ),
    )
    # The manifest records the venv's final state, so it is written after any
    # repair -- it must describe what really provided each import, not what was
    # first attempted.
    handle = state.VenvHandle.for_dir(
        cache_search.record_venv_state(
            handle.venv_dir,
            venv_python=handle.venv_python,
            venv_name=settings.venv_name,
            timestamp=target.timestamp,
            run_tag=run_tag,
            python_command=target.python_command,
            uninstalled=set(requirements.uninstalled),
            extra_requirements=requirements.extra_requirements,
            rawlog=settings.rawlog,
        )
    )
    # Check that all packages can be imported in the venv.
    all_importable = verify.check_packages_in_venv(
        environment.venv_python_for(handle.venv_dir),
        uninstalled=set(requirements.uninstalled),
        source_names=source_names,
    )
    return requirements, (handle if all_importable else None), install_succeeded


def run(
    settings: Settings,
    args: argparse.Namespace,
    target: state.Target | None,
    *,
    start_time: dt.datetime | None = None,
) -> int:
    """Execute the run these values describe and return the script's status.

    Args:
        settings: The run's invariants, built once in cli.main.
        args: The parsed command line.
        target: What is being run, or None for a scriptless invocation --
            which only --blank-slate excuses.
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
        environment.UvUnavailable: veny has no uv to build an environment
            with. Raised below this layer and left to travel: `cli.main` owns
            what it costs.
    """
    start_time = start_time or dt.datetime.now()
    script_exit_code = 0

    # emmykit annotates this as str | None while documenting "" for "absent";
    # `or ""` pins the documented spelling at the two boundaries that are
    # typed str, and stdlib_index.resolve below still gets the raw value,
    # because it maps None and the running interpreter to the same index.
    python_command = ek.find_preferred_python_version()
    if target is not None:
        target = dataclasses.replace(target, python_command=python_command or "")
    if python_command:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(
                "Python %s is available at: %s", ek.PY_VERSION, python_command
            )
    else:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Python %s is not available.", ek.PY_VERSION)
    stdlib = stdlib_index.resolve(python_command)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Standard library index: %d names from Python %d.%d (source: %s)",
            len(stdlib.names),
            stdlib.python_version[0],
            stdlib.python_version[1],
            stdlib.source,
        )
    # This must happen before anything resolves, i.e. before list_packages() below.
    aliases = build_alias_index(settings, args, python_command or "")
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Alias index: %d overrides, %d cached names, tagged %s",
            len(aliases.overrides),
            len(aliases.cache.entries),
            aliases.cache.interpreter_tag,
        )

    if not ek.safe_is_dir(settings.my_dir):
        if not settings.rawlog:
            logging.info(
                "Directory %s does not exist yet, so it is being created.",
                settings.my_dir,
            )
        settings.my_dir.mkdir(parents=True, exist_ok=True)

    if target is not None:
        pass  # If a script was provided as an argument, skip the rest of these checks.
    elif getattr(args, "blank_slate", False):
        return blank_slate(settings, args)
    else:
        raise UsageError(
            "You must specify either a script to run or --blank-slate (be "
            "careful using --blank-slate because it deletes all cached virtual "
            "environments, among other things!)."
        )

    extra_requirements: Mapping[str, str | None] = {}
    if getattr(args, "reqs", False):
        extra_requirements = environment.parse_extra_requirements(
            settings.extra_requirements_file, rawlog=settings.rawlog
        )
        if not settings.rawlog:
            logging.info(
                "Loaded extra requirements from ./%s: %s",
                settings.extra_requirements_file,
                extra_requirements,
            )

    time1 = dt.datetime.now()
    scan = ImportScan(
        custom_modules=custom_modules.dict_of_custom_modules(
            settings,
            use_cache=not getattr(args, "rc", False)
            and not getattr(args, "no_cache", False),
        )
    )
    time2 = dt.datetime.now()
    elapsed_time = time2 - time1
    if not settings.rawlog:
        logging.info("dict_of_custom_modules() took %s", elapsed_time)

    start_list_packages_time = dt.datetime.now()
    elapsed_time = start_list_packages_time - start_time
    if not settings.rawlog:
        logging.info("Elapsed time: %s", elapsed_time)

    scan, requirements = list_packages(
        settings,
        scan,
        target,
        args=args,
        aliases=aliases,
        extra_requirements=extra_requirements,
        is_stdlib=stdlib.__contains__,
    )

    report(settings, scan, requirements)

    if getattr(args, "justprint", False):
        return 0

    if not requirements.uninstalled:
        if not settings.rawlog:
            logging.info("All required packages are already installed.")
        start_raw_time = dt.datetime.now()
        script_exit_code = run_script(
            sys.executable,
            target.python_script,
            list(target.script_args),
            rawlog=settings.rawlog,
            announce=True,
        )
        elapsed_raw_time = dt.datetime.now() - start_raw_time
        if not settings.rawlog:
            logging.info("Runtime: %s", elapsed_raw_time)
    elif (active_venv := last_used.active_virtualenv_dir()) is not None:
        if not settings.rawlog:
            logging.info("Already in a virtual environment.")
        if verify.check_packages_in_venv(
            environment.venv_python_for(active_venv),
            uninstalled=set(requirements.uninstalled),
            source_names=verify.source_import_names(
                set(requirements.all_imports),
                requirements.extra_requirements,
                getattr(args, "reqs", False),
            ),
        ):
            start_raw_time = dt.datetime.now()
            script_exit_code = run_script(
                sys.executable,
                target.python_script,
                list(target.script_args),
                rawlog=settings.rawlog,
                announce=True,
            )
            elapsed_raw_time = dt.datetime.now() - start_raw_time
            if not settings.rawlog:
                logging.info("Runtime: %s", elapsed_raw_time)
        else:
            logging.error(
                "The current virtual environment does not have all the required packages."
            )
            if not settings.rawlog:
                logging.info(
                    "Please deactivate the current virtual environment and run the script again."
                )
            script_exit_code = 1
    else:
        handle: state.VenvHandle | None = None
        install_succeeded = False
        if getattr(args, "no_cache", False):
            match_dir = None
        else:
            match_dir = cache_search.find_match_dir_in_cache(
                args,
                my_dir=settings.my_dir,
                venv_name=settings.venv_name,
                uninstalled=set(requirements.uninstalled),
                extra_requirements=requirements.extra_requirements,
                source_names=verify.source_import_names(
                    set(requirements.all_imports),
                    requirements.extra_requirements,
                    getattr(args, "reqs", False),
                ),
                tag=cache_search.interpreter_tag(stdlib),
                rawlog=settings.rawlog,
                load_last_used=lambda: _load_last_used(
                    target, my_name=settings.my_name, rawlog=settings.rawlog
                ),
            )
        if match_dir is None:
            if not settings.rawlog:
                logging.info(
                    "Creating new virtual environment '%s'...", settings.venv_name
                )
            requirements, handle, install_succeeded = setup_virtualenv(
                settings,
                target,
                requirements,
                args=args,
                aliases=aliases,
                stdlib=stdlib,
            )
            if handle is None:
                # This was emmykit's critical-error helper, called with
                # choose_breakpoint=True: it logged this same message at this
                # same level and then opened a pdb prompt -- a debugger in the
                # user's face on a failed build, and a BdbQuit traceback
                # wherever stdin is not a tty. The status below is the whole of
                # what veny needed from it, and cli.main owns the exit. (Named
                # obliquely on purpose: the phase's exit sweep greps this tree
                # for that helper's name.)
                logging.critical("Failed to create a virtual environment.")
                script_exit_code = 1
        else:
            if not settings.rawlog:
                logging.info("Using existing virtual environment: %s", match_dir)
            handle = state.VenvHandle.for_dir(match_dir)
            # A reused venv never carries a "failed-" prefix -- the cache
            # search only offers folders that dropped it -- and
            # setup_virtualenv never ran, which is what left
            # install_succeeded False on the state object here before phase 4a.
            install_succeeded = False

        if handle is not None:
            start_venv_time = dt.datetime.now()
            elapsed_time = start_venv_time - start_time
            if not settings.rawlog:
                logging.info("Elapsed time: %s", elapsed_time)
            script_exit_code = run_script(
                handle.venv_python,
                target.python_script,
                list(target.script_args),
                rawlog=settings.rawlog,
                announce=True,
            )
            end_time = dt.datetime.now()
            elapsed_time = end_time - start_venv_time
            if not settings.rawlog:
                logging.info(
                    "Elapsed time since activating virtual environment: %s",
                    elapsed_time,
                )
            if script_exit_code != 0 and not settings.rawlog:
                logging.error("Script exited with status %d", script_exit_code)
            if handle.venv_dir.name.startswith("failed-") and install_succeeded:
                # If the program has made it to this point, it has run successfully, so the venv directory can be renamed because it DIDN'T fail.
                handle = state.VenvHandle.for_dir(
                    cache_search.rename_venv(
                        handle.venv_dir,
                        handle.venv_dir.name.removeprefix("failed-"),
                    )
                )

            # What the next run needs, and nothing else: which environment
            # ran this script and which interpreter is inside it. Written
            # after the failed- rename above, so the recorded folder is the
            # one that exists on disk.
            last_used.save(
                state.LastUsed(
                    venv_dir=handle.venv_dir,
                    venv_python=handle.venv_python,
                    timestamp=target.timestamp,
                ),
                script_dir=target.script_dir,
                python_script=target.python_script,
                my_name=settings.my_name,
            )

    return script_exit_code
