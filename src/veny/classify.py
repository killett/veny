"""Decide, for one run's imports, which are installed, missing, or unusable.

Classification is a function: it reads an ImportScan and the run's tables and
returns a Requirements, without touching Options and without writing anything
back through the scan. The one environment-shaped thing it needs -- a probe
virtual environment to ask "does this import already work?" -- arrives as a
context manager, so the caller owns building and tearing it down and a run
with nothing to classify never opens one.

It sits above the index layer, alongside environment, and below cli.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from contextlib import AbstractContextManager

import emmykit as ek

from . import alias_index, stdlib_index
from .alias_index import ResolvedImport
from .analysis.scan_state import ImportScan
from .state import Requirements


def _compute_bad_imports(
    all_imports: set[str], known_bad: AbstractSet[str], py2_only: frozenset[str]
) -> set[str]:
    """Return the imports that must never be handed to pip.

    Args:
        all_imports: Every import name found in the analysed scripts.
        known_bad:   Project-specific names that are not on PyPI.
        py2_only:    Python 2 standard-library names, from stdlib_index.

    Returns:
        The subset of all_imports that pip must not be asked to install.
    """
    bad = set(known_bad | py2_only) & all_imports
    bad.update({imp for imp in all_imports if imp.startswith("_")})
    return bad


def resolve_records(
    aliases: alias_index.AliasIndex, import_names: Iterable[str]
) -> set[ResolvedImport]:
    """Resolve import names into records carrying their pip names.

    Args:
        aliases:      The run's alias index, used to resolve each name.
        import_names: Import names as they would be written in source.

    Returns:
        One record per name. A name the index cannot resolve keeps its own
        spelling as the pip name, because no evidence is not the same as
        contrary evidence.
    """
    records: set[ResolvedImport] = set()
    for name in import_names:
        resolution = aliases.resolve(name)
        primary = resolution.candidates[0].pip_name if resolution.candidates else name
        records.add(ResolvedImport(import_name=name, pip_name=primary))
    return records


def requirement_records(pip_names: Iterable[str]) -> set[ResolvedImport]:
    """Wrap pip names from a requirements file as records.

    These arrive already as pip names, and nothing maps a pip name back to an
    import name, so the same string is the best available answer for both.

    Args:
        pip_names: Package names as written in the extra requirements file.

    Returns:
        One record per name, with import_name == pip_name.
    """
    return {ResolvedImport(import_name=name, pip_name=name) for name in pip_names}


def add_dependencies(
    uninstalled: set[ResolvedImport],
    *,
    also_needs: Mapping[str, Sequence[str]],
    aliases: alias_index.AliasIndex,
    rawlog: bool,
) -> set[ResolvedImport]:
    """Add dependencies for uninstalled imports.

    Args:
        uninstalled: The records classified as needing installation. Updated
            in place, as the caller's own set, and returned.
        also_needs:  Import name to the import names it also needs.
        aliases:     The run's alias index, used to resolve dependency names.
        rawlog:      Suppress veny's own commentary.

    Returns:
        The same set, with every transitively required dependency added.
    """
    # Create a copy to iterate over since we'll be modifying the set
    initial_packages = uninstalled.copy()

    for record in initial_packages:
        if record.import_name in also_needs:
            dependencies = also_needs[record.import_name]
            if not rawlog:
                logging.info(
                    "Adding dependencies for %s: %s", record.import_name, dependencies
                )
            uninstalled.update(resolve_records(aliases, dependencies))

    # Handle nested dependencies by repeating this process until no new dependencies are added.
    added = True
    while added:
        added = False
        current_packages = uninstalled.copy()
        for record in current_packages:
            if record.import_name in also_needs:
                dependencies = also_needs[record.import_name]
                new_dependencies = resolve_records(aliases, dependencies) - uninstalled
                if new_dependencies:
                    if not rawlog:
                        logging.info(
                            "Adding nested dependencies for %s: %s",
                            record.import_name,
                            sorted(r.import_name for r in new_dependencies),
                        )
                    uninstalled.update(new_dependencies)
                    added = True
    return uninstalled


def split_imports(
    scan: ImportScan,
    *,
    aliases: alias_index.AliasIndex,
    known_bad_imports: AbstractSet[str],
    also_needs: Mapping[str, Sequence[str]],
    extra_requirements: Mapping[str, str | None],
    use_reqs: bool,
    probe: AbstractContextManager[Callable[[str], bool]],
    rawlog: bool,
) -> Requirements:
    """Split imports into installed, uninstalled, and bad imports.

    The scan is read, never written: `all_imports` and `custom_modules` are the
    only fields classification consults, and `seen_stdlib_imports` travels
    through to the result untouched.

    Args:
        scan:               What the import scan found.
        aliases:            The run's alias index, used to resolve pip names.
        known_bad_imports:  Project-specific names that are not on PyPI.
        also_needs:         Import name to the import names it also needs.
        extra_requirements: The --reqs file's entries, name to specifier.
        use_reqs:           Whether --reqs was given, so extra_requirements
                            count as imports to classify.
        probe:              Yields a predicate answering whether a name is
                            importable in a probe environment. Entered only
                            once there is something to classify, so a run with
                            no imports never pays for building one.
        rawlog:             Suppress veny's own commentary.

    Returns:
        What classification decided about this run's imports.
    """
    bad_imports = _compute_bad_imports(
        scan.all_imports, known_bad_imports, stdlib_index.PYTHON2_ONLY
    )
    if bad_imports:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Identified bad imports: %s", bad_imports)
    all_imports = scan.all_imports - bad_imports
    installed_imports: set[ResolvedImport] = set()
    uninstalled_imports: set[ResolvedImport] = set()
    if use_reqs:
        all_imports = all_imports.union(extra_requirements.keys())
    total_imports = len(all_imports)
    if not total_imports:
        if not rawlog:
            logging.info("No imports found.")
        return Requirements(
            all_imports=frozenset(all_imports),
            bad=frozenset(bad_imports),
            installed=frozenset(installed_imports),
            uninstalled=frozenset(uninstalled_imports),
            seen_stdlib=frozenset(scan.seen_stdlib_imports),
            extra_requirements=extra_requirements,
        )

    max_length = max(
        len(imp) for imp in all_imports
    )  # Longest import name length, used for formatting
    max_digits = len(
        str(len(all_imports))
    )  # Maximum number of digits in import count, also used for formatting

    with probe as is_importable:
        for i, imp in enumerate(all_imports, 1):
            # The import name is all either check below needs, and resolution is
            # deliberately not done yet: see the else branch.
            record = ResolvedImport(import_name=imp, pip_name=imp)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug("Checking if import %s is installed or uninstalled", imp)
            if imp in scan.custom_modules.keys():
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(
                        "Custom module %s has path %s",
                        imp,
                        os.fspath(scan.custom_modules[imp]),
                    )
                status_str = f"{ek.ANSI_CYAN}YES - custom module{ek.ANSI_RESET}"
            elif is_importable(imp):
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug("Module %s can be imported in venv", imp)
                status_str = f"{ek.ANSI_GREEN}YES -     installed{ek.ANSI_RESET}"
                # The pip name is left as the import name here because nothing
                # needs it: an installed import is never handed to pip, and
                # nothing downstream re-resolves it.
                installed_imports.add(record)
            else:
                # Only a genuinely uninstalled import needs a pip name, so this
                # is where resolution belongs. Resolving before the two checks
                # above charged every import up to six PyPI project lookups (the
                # name plus five mutations), each a metadata request plus up to
                # two ranged wheel reads -- for local modules and already
                # installed packages that never needed one.
                resolution = aliases.resolve(imp)
                # No candidate at all means no evidence either way, not a bad
                # name, so fall back to the import name and let pip have its say.
                primary = (
                    resolution.candidates[0].pip_name if resolution.candidates else imp
                )
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(
                        "Resolved import %s to candidates %s",
                        imp,
                        [c.pip_name for c in resolution.candidates],
                    )
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(
                        "Import %s is not installed and not a custom module", imp
                    )
                status_str = " NO - NOT installed"
                uninstalled_imports.add(
                    ResolvedImport(import_name=imp, pip_name=primary)
                )
            if not rawlog:
                logging.info(
                    "Checking import %-*s : %*d/%d - %s",
                    max_length,  # width for imp (left-aligned)
                    imp,
                    max_digits,  # width for i (right-aligned)
                    i,
                    total_imports,
                    status_str,
                )
    if use_reqs:
        uninstalled_imports = uninstalled_imports.union(
            requirement_records(extra_requirements.keys())
        )
    uninstalled_imports = add_dependencies(
        uninstalled_imports, also_needs=also_needs, aliases=aliases, rawlog=rawlog
    )
    return Requirements(
        all_imports=frozenset(all_imports),
        bad=frozenset(bad_imports),
        installed=frozenset(installed_imports),
        uninstalled=frozenset(uninstalled_imports),
        seen_stdlib=frozenset(scan.seen_stdlib_imports),
        extra_requirements=extra_requirements,
    )
