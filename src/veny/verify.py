"""Prove what a virtual environment really provides, and repair what it does not.

Nothing here has heard of ``Options``: each function takes the paths, names
and flags it actually reads. It sits above ``environment`` because it installs,
uninstalls and rewrites ``requirements.txt`` through that module, and below
``cli``, which drives it.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path

from . import alias_index, environment
from .alias_index import ResolvedImport

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

_SHARED_LIBRARY_PATTERN = re.compile(
    r"[\w.+-]+\.(?:so(?:\.[\w.]+)?|dylib|dll)", re.IGNORECASE
)


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
    return "\n".join(
        line.removeprefix("Import error: ")
        for line in output.splitlines()
        if line.startswith("Import error: ")
    )


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
            names.update(
                alias_index.normalize_pip_name(name)
                for name in listed.split(",")
                if name
            )
    return frozenset(names)


def import_outcome_in_venv(
    venv_python: str | os.PathLike[str], import_name: str
) -> ImportOutcome:
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
        venv_python: The venv interpreter to run the import in.
        import_name: The import name to try, as written in the user's source.

    Returns:
        The outcome, carrying the rejection kind any failure warrants.
    """
    imported, output = run_import_check_in_venv(
        venv_python, [[import_name]], report_providers=True
    )
    if imported:
        return ImportOutcome(
            imported=True,
            rejection_kind="",
            detail="",
            providers=import_providers(output),
        )
    detail = import_error_detail(output)
    if not any(marker in detail for marker in MACHINE_SCOPED_IMPORT_MARKERS):
        return ImportOutcome(
            imported=False, rejection_kind="import_failed", detail=detail
        )
    library = _SHARED_LIBRARY_PATTERN.search(detail)
    logging.warning(
        "%s is installed but will not import on this machine: %s. That is a "
        "missing system library (%s), not the wrong package -- install the "
        "operating-system package that provides it. veny will not hold this "
        "against the package.",
        import_name,
        detail,
        library.group(0) if library else "unknown",
    )
    return ImportOutcome(
        imported=False, rejection_kind="import_unavailable", detail=detail
    )


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
    return any(
        alias_index.normalize_pip_name(name) == wanted for name in outcome.providers
    )


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
            candidate.pip_name,
            resolution.import_name,
            candidate.evidence,
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
                logging.debug(
                    "Not caching %s -> %s: the venv credits %s with providing it.",
                    resolution.import_name,
                    candidate.pip_name,
                    sorted(outcome.providers)
                    if isinstance(outcome, ImportOutcome)
                    else "something else",
                )
            return candidate
        logging.debug(
            "%s installed but did not provide %s; removing it.",
            candidate.pip_name,
            resolution.import_name,
        )
        uninstaller(candidate.pip_name)
        index.reject(
            resolution.import_name,
            candidate.pip_name,
            outcome.rejection_kind
            if isinstance(outcome, ImportOutcome)
            else "import_failed",
        )
    return None


def run_import_check_in_venv(
    venv_python: str | os.PathLike[str],
    alternatives: list[list[str]],
    report_providers: bool = False,
) -> tuple[bool, str]:
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
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("check_packages_in_venv stdout:\n%s", result.stdout)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("check_packages_in_venv stderr:\n%s", result.stderr)
    return "packages imported successfully" in result.stdout, result.stdout


def source_import_names(
    all_imports: AbstractSet[str],
    extra_requirements: Mapping[str, str | None],
    use_reqs: bool,
) -> set[str]:
    """Return the import names that were actually written in the user's source.

    Only these can be verified by importing them. requirement_records() (--reqs)
    and resolve_records() (dependencies) both produce records whose import_name
    is really a pip name -- "opencv-python", not "cv2" -- because a requirements
    line is a pip name and nothing maps it backwards. import_module() can never
    succeed on one of those, so treating its failure as evidence would condemn a
    package that installed perfectly well.

    Args:
        all_imports:        Every import name the analysis collected.
        extra_requirements: The --reqs entries, pip name -> version specifier.
        use_reqs:           Whether this run was given a requirements file.

    Returns:
        The import names found in the analysed scripts.
    """
    names = set(all_imports)
    if use_reqs:
        # split_imports() folds the requirements file's entries into
        # all_imports, but those are pip spellings, not import names.
        names -= set(extra_requirements)
    return names


def check_packages_in_venv(
    venv_python: str | os.PathLike[str],
    *,
    record: ResolvedImport | None = None,
    uninstalled: AbstractSet[ResolvedImport] = frozenset(),
    source_names: AbstractSet[str] = frozenset(),
) -> bool:
    """Check if packages can be imported in the specified virtual environment.

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
        venv_python:  The venv interpreter to run the import checks in.
        record:       Optional resolved import to check. If None, checks every
                      record in `uninstalled`.
        uninstalled:  The records the bulk branch checks. Ignored when `record`
                      is given.
        source_names: The import names known to come from the user's source, as
                      source_import_names() computes them. Every caller supplies
                      this; the empty default is not a "work it out yourself"
                      fallback, and passing an empty set for a run that has
                      source imports is a mis-wiring the bulk branch cannot
                      detect (it silently widens each check to the
                      distribution's whole top-level list).

    Returns:
        bool:       True if all packages can be imported successfully, False otherwise.

    Raises:
        None:       This function does not raise exceptions, but logs errors if the import fails.
    """
    if record is not None:
        # alternatives: one name per entry to try; passes if any one imports.
        alternatives = [[record.import_name]]
    else:
        # Ask the venv what it actually has, instead of import-checking every
        # record under its pip spelling: requirement_records() sets
        # import_name == pip_name for --reqs entries (a requirements line is
        # a pip name and nothing maps it backwards), and import_module()
        # always fails on a pip spelling like "opencv-python". Probing once
        # here and inverting the result answers "what does this distribution
        # actually import as?" from the installed artifact, covering every
        # distribution rather than only what a curated table happened to know.
        _, venv_distributions = alias_index.probe_interpreter(venv_python)
        import_names_by_dist = alias_index.import_names_by_distribution(
            venv_distributions
        )
        alternatives = []
        for entry in sorted(uninstalled, key=lambda r: r.import_name):
            top_levels = import_names_by_dist.get(
                alias_index.normalize_pip_name(entry.pip_name)
            )
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
            if entry.import_name in source_names or (
                top_levels and entry.import_name in top_levels
            ):
                alternatives.append([entry.import_name])
            elif top_levels:
                alternatives.append(sorted(top_levels))
            else:
                alternatives.append([entry.import_name])
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Packages to check in venv: %s", alternatives)
    imported, _ = run_import_check_in_venv(venv_python, alternatives)
    return imported


def repair_unsatisfied_import(
    record: ResolvedImport,
    installed_distributions: dict[str, frozenset[str]],
    outcome: ImportOutcome,
    *,
    venv_python: str | os.PathLike[str],
    index: alias_index.AliasIndex,
    rawlog: bool,
) -> ResolvedImport:
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
        record:                  The record whose import name the venv does not provide.
        installed_distributions: Normalized distribution name -> the import names
                                 it provides, from the venv's own metadata.
        outcome:                 Why the import failed, from import_outcome_in_venv.
        venv_python:             The venv interpreter to install into and import from.
        index:                   The AliasIndex to resolve against and record in.
        rawlog:                  Whether the run suppresses informational logging.

    Returns:
        A record naming the package that actually provided the import, or the
        original record unchanged when nothing did.
    """
    if alias_index.normalize_pip_name(record.pip_name) in installed_distributions:
        environment.uninstall_from_venv(venv_python, record.pip_name)
        index.reject(record.import_name, record.pip_name, outcome.rejection_kind)
    else:
        index.reject(record.import_name, record.pip_name, "install_failed")

    def installer(pip_name: str) -> bool:
        """Install a candidate, returning success rather than raising."""
        return environment.install_into_venv(venv_python, pip_name)

    def importer(import_name: str) -> ImportOutcome:
        """Report whether the *import* name now imports inside the venv, and why not."""
        return import_outcome_in_venv(venv_python, import_name)

    def uninstaller(pip_name: str) -> None:
        """Remove a candidate that installed without providing the import."""
        environment.uninstall_from_venv(venv_python, pip_name)

    winner = resolve_and_verify(
        index.resolve(record.import_name),
        index,
        installer=installer,
        importer=importer,
        uninstaller=uninstaller,
    )
    if winner is None:
        logging.error(
            "Could not find a package that provides the import %s.", record.import_name
        )
        return record
    if not rawlog:
        logging.info(
            "%s provides the import %s (%s).",
            winner.pip_name,
            record.import_name,
            winner.evidence,
        )
    return ResolvedImport(import_name=record.import_name, pip_name=winner.pip_name)


def confirm_if_attributable(
    record: ResolvedImport,
    installed_distributions: dict[str, frozenset[str]],
    index: alias_index.AliasIndex,
) -> None:
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
    dependency-injected and has no venv metadata to probe with.

    Args:
        record:                  The record whose import was just verified.
        installed_distributions: Normalized distribution name -> the import names
                                 it provides, from the venv's own metadata.
        index:                   The AliasIndex to record the confirmation in.
    """
    top_levels = installed_distributions.get(
        alias_index.normalize_pip_name(record.pip_name)
    )
    if top_levels is not None and record.import_name in top_levels:
        index.confirm(record.import_name, record.pip_name)
    elif logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Not caching %s -> %s: the venv imports %s but does not attribute "
            "it to that distribution (it declares %s).",
            record.import_name,
            record.pip_name,
            record.import_name,
            sorted(top_levels) if top_levels else "nothing",
        )


def verify_and_repair_imports(
    *,
    venv_python: str | os.PathLike[str],
    requirements_file: Path,
    uninstalled: AbstractSet[ResolvedImport],
    extra_requirements: Mapping[str, str | None],
    source_names: AbstractSet[str],
    index: alias_index.AliasIndex,
    rawlog: bool,
) -> frozenset[ResolvedImport]:
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
        venv_python:        The venv interpreter to verify, install and import in.
        requirements_file:  The venv's own requirements.txt, rewritten if a
                            repair changed which packages it holds.
        uninstalled:        The records the install was asked to provide.
        extra_requirements: The --reqs entries, kept in the rewritten file.
        source_names:       The import names from the user's own source, as
                            source_import_names() computes them. Only these are
                            verified; see source_import_names().
        index:              The AliasIndex to resolve against and record in.
        rawlog:             Whether the run suppresses informational logging.

    Returns:
        The final uninstalled records -- the input set with every repaired
        record replaced. Returned rather than written back onto a shared
        object, because the design's mutation direction is that each stage
        returns its product.
    """
    from_source = source_names
    records = [
        record
        for record in sorted(uninstalled, key=lambda r: r.import_name)
        if record.import_name in from_source
    ]
    if not records:
        return frozenset(uninstalled)
    # One probe, used by both branches: the bulk branch needs it to attribute a
    # passing import to the distribution that actually provided it, and the
    # repair branch needs it to tell "installed but does not provide this" from
    # "never installed at all".
    _, venv_distributions = alias_index.probe_interpreter(venv_python)
    installed_distributions = alias_index.import_names_by_distribution(
        venv_distributions
    )
    if check_packages_in_venv(
        venv_python, uninstalled=uninstalled, source_names=source_names
    ):
        # Every source-derived record is checked under its own import name, so
        # a bulk pass means each one of them really did import.
        for record in records:
            confirm_if_attributable(record, installed_distributions, index)
        return frozenset(uninstalled)
    repaired: dict[ResolvedImport, ResolvedImport] = {}
    for record in records:
        # The outcome, not just a bool: whether a failure is remembered depends
        # on whether it was the package's fault or this machine's.
        outcome = import_outcome_in_venv(venv_python, record.import_name)
        if outcome.imported:
            confirm_if_attributable(record, installed_distributions, index)
            continue
        replacement = repair_unsatisfied_import(
            record,
            installed_distributions,
            outcome,
            venv_python=venv_python,
            index=index,
            rawlog=rawlog,
        )
        if replacement != record:
            repaired[record] = replacement
    final = frozenset(uninstalled)
    if repaired:
        final = (final - frozenset(repaired)) | frozenset(repaired.values())
        # Keep the venv's own requirements.txt describing what is really installed.
        environment.write_requirements_file_with_extras(
            requirements_file,
            (record.pip_name for record in final),
            extra_requirements,
        )
    return final
