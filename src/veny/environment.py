"""The one place veny invokes ``uv``.

Every virtual environment veny builds, and every package it installs into one,
goes through this module. Nothing here is handed a per-run state object: each
function takes the paths, names and flags it actually reads, so the environment
layer can be driven -- and tested -- without building the run first.

It sits above the index layer and below ``cli``; it imports nothing of veny's.
"""

from __future__ import annotations

import functools
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

import emmykit as ek


class UvUnavailable(Exception):
    """veny cannot find a uv to drive its environment layer with.

    Raised rather than exited: `cli.py` owns every exit status (see the
    re-architecture design's error-handling section), so the module that
    discovers the problem reports it and the module that owns the process
    decides what it costs.
    """


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
        UvUnavailable: If neither the packaged binary nor PATH yields a uv.
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
    raise UvUnavailable(
        "veny requires uv, which is not installed and is not on PATH.\n"
        "Reinstall veny with:  uv tool install veny"
    )


def create_venv(target: str | os.PathLike[str], python: str = "") -> bool:
    """Create a virtual environment at target using uv.

    No pip is seeded: veny drives installs through uv, and a script that
    installs into the environment veny built for it is working against veny.

    Args:
        target: Directory to create the environment in.
        python: Interpreter for uv to build against. Empty means uv chooses.

    Returns:
        True if the environment was created. False means uv refused, and uv
        has already said why on stderr.
    """
    command = [uv_binary(), "venv", os.fspath(target)]
    if python:
        command += ["--python", python]
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Creating venv: %s", " ".join(shlex.quote(str(arg)) for arg in command)
        )
    try:
        subprocess.check_call(command)
    except subprocess.CalledProcessError:
        return False
    return True


def venv_python_for(venv_dir: str | os.PathLike[str]) -> Path:
    """Return the interpreter inside a virtual environment.

    Args:
        venv_dir: The venv to look in.

    Returns:
        The path to that venv's python.
    """
    venv_dir = ek.ensure_dir(venv_dir)
    if sys.platform == "win32":
        return (venv_dir / "Scripts" / "python.exe").absolute()
    # Do NOT use resolve() here because this is a symlink and resolve() would break it
    return (venv_dir / "bin" / "python").absolute()


def venv_build_interpreter(python_command: str) -> str:
    """Return the interpreter that should create the virtual environment.

    python_command is what stdlib and alias resolution were probed
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
        python_command: The interpreter command imports were classified
            against. Empty means the running interpreter serves.

    Returns:
        An absolute path to the interpreter to build with, when shutil.which()
        can resolve one. Falls back to the unresolved command/path (today's
        pre-fix behaviour) if it cannot -- logged, because the invariant above
        is no longer guaranteed to hold for that run.
    """
    command = python_command or sys.executable
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


def parse_extra_requirements(
    path: str | os.PathLike[str], *, rawlog: bool
) -> dict[str, str | None]:
    """Parse an extra requirements file into a dict of package names.

    Values are the version specifiers where present. The file should have one
    package per line, optionally with a specifier (e.g., 'package>=1.0').
    Lines starting with '#' are treated as comments and ignored.

    Args:
        path:   The path to the extra requirements file.
        rawlog: Whether the caller is running in raw-log mode, passed through
            to emmykit's reader.

    Returns:
        A dictionary where keys are package names and values are version
        specifiers. Empty when the file is missing or empty.
    """
    extra_requirements: dict[str, str | None] = {}
    file_content = ek.my_fopen(path, suppress_errors=True, rawlog=rawlog)
    if not file_content:
        return extra_requirements
    # Regular expression to capture package name and version specifier
    pattern = re.compile(r"^\s*([A-Za-z0-9_\-\.]+)\s*(.*)$")
    for line in file_content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            match = pattern.match(line)
            if match:
                package = match.group(1)
                version_spec = match.group(2).strip() if match.group(2) else ""
                extra_requirements[package] = version_spec
    return extra_requirements


def write_requirements_file_with_extras(
    requirements_file: str | os.PathLike[str],
    pip_names: Iterable[str],
    extra_requirements: Mapping[str, str | None],
) -> None:
    """Write the requirements file with the extra requirements added.

    Args:
        requirements_file:  The file to write.
        pip_names:          The pip names to write, in any order.
        extra_requirements: Version specifiers keyed by pip name, as
            parse_extra_requirements returns them.
    """
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Writing packages to %s", requirements_file)
    with open(requirements_file, "w") as f:
        # Write the packages in alphabetical order so the requirements file is
        # deterministic. pip reads this file, so it gets the pip names.
        for package in sorted(pip_names):
            if package in extra_requirements:
                version_spec = extra_requirements[package]
                if version_spec:
                    f.write(f"{package}{version_spec}\n")
                else:
                    f.write(f"{package}\n")
            else:
                f.write(f"{package}\n")


def run_uv_pip(
    venv_python: str | os.PathLike[str] | None, *args: str
) -> subprocess.CompletedProcess[str] | None:
    """Run one uv pip command against the venv without ever raising.

    Every caller is on a verification path, where the point is to report what
    happened rather than to end the run, so a missing interpreter or an
    unrunnable uv is reported as "no result" instead of an exception.

    Args:
        venv_python: The venv's interpreter, or None if none is set yet.
        *args:       The uv pip arguments, e.g. "install", "cv2".

    Returns:
        The completed process, or None if uv could not be run at all.
    """
    if venv_python is None:
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
        os.fspath(venv_python),
        *args[1:],
    ]
    logging.info(
        "Running uv: %s", " ".join(shlex.quote(str(arg)) for arg in the_command)
    )
    try:
        return subprocess.run(
            the_command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        logging.exception("Could not run uv pip %s.", args[0])
        return None


def install_into_venv(
    venv_python: str | os.PathLike[str] | None, pip_name: str
) -> bool:
    """Install one package into the venv, reporting failure instead of ending the run.

    The batch install is a single uv invocation that either succeeds or leaves
    the venv marked failed; this installer serves the verification loop instead,
    where one candidate failing must never end the run, so every failure is
    reported as False.

    Args:
        venv_python: The venv's interpreter, or None if none is set yet.
        pip_name:    The package to install.

    Returns:
        True if uv reported success.
    """
    result = run_uv_pip(venv_python, "install", pip_name)
    if result is None:
        return False
    if result.returncode != 0:
        logging.error(
            "Failed to install %s. Error: %s", pip_name, result.stderr.strip()
        )
        return False
    return True


def uninstall_from_venv(
    venv_python: str | os.PathLike[str] | None, pip_name: str
) -> None:
    """Remove a package that installed but did not provide the import it was tried for.

    Leaving it behind pollutes the venv and can shadow the correct package on a
    later attempt.

    Args:
        venv_python: The venv's interpreter, or None if none is set yet.
        pip_name:    The package to remove.
    """
    result = run_uv_pip(venv_python, "uninstall", pip_name)
    if result is not None and result.returncode != 0:
        logging.warning(
            "Could not uninstall %s. Error: %s", pip_name, result.stderr.strip()
        )
