"""Walk a script and the local modules it reaches, collecting imports.

Breadth-first: analyze a file, enqueue every local module its top-level
imports resolve to, repeat. Then build the call graph and keep only the
imports the reachable code actually uses.
"""

import ast
import collections
import logging
import os
from collections.abc import Callable
from pathlib import Path

import emmykit as ek

from ..settings import Settings
from .call_graph import (
    ModuleInfo,
    build_call_graph,
    collect_used_imports,
    split_function_name,
)
from .imports import ImportFunctionCollector, SysPathVisitor, process_import
from .literals import collect_pathlib_aliases
from .scan_state import ImportScan


def _analyze_module(
    settings: Settings,
    scan: ImportScan,
    module_path: Path,
    modules_info: dict[str, ModuleInfo],
    do_sys_path_scan: bool,
) -> tuple[str, ModuleInfo] | None:
    """Read, parse, and analyze one module file.

    - Optionally scans for sys.path mutations (current behavior: only for the first loop).
    - Updates modules_info.

    Args:
        settings:         Settings object containing the run's fixed configuration. Contains:
            - settings.rawlog:        Whether to suppress veny's own commentary.
        scan:             ImportScan accumulating what this run has discovered. Contains:
            - scan.custom_modules:    Dictionary mapping custom module names to their file paths.
            - scan.sys_path_hints:    Set of Path objects representing directories to add to sys.path.
        module_path:      Path to the module file to analyze.
        modules_info:     Dictionary mapping module keys to ModuleInfo objects.
        do_sys_path_scan: Whether to scan for sys.path mutations in this module.

    Returns:
        (module_key, module_info) or None on failure.
    """
    module_path = ek.ensure_path(module_path)
    module_key = os.fspath(module_path.resolve())

    file_content = ek.my_fopen(module_path, rawlog=settings.rawlog)
    if not file_content:
        logging.error(f"Could not read file: {module_path}")
        return None

    try:
        tree = ast.parse(file_content, module_key)
    except Exception:
        logging.error(f"Failed to parse the file: {module_path}")
        return None

    collector = ImportFunctionCollector(scan, module_key, module_path)
    collector.visit(tree)

    # Keep behavior identical: only the first loop does sys.path scanning.
    if do_sys_path_scan:
        aliases = collect_pathlib_aliases(tree)
        spv = SysPathVisitor(aliases)
        spv.visit(tree)
        base_dir = module_path.parent
        for p in spv.paths:
            if not p:
                continue
            P = (
                (base_dir / p).expanduser().resolve()
                if not os.path.isabs(p)
                else Path(p).expanduser().resolve()
            )
            if ek.safe_is_dir(P):
                scan.sys_path_hints.add(P)

    module_info = collector.module_info
    module_info.base_classes = collector.base_classes
    modules_info[module_key] = module_info
    return module_key, module_info


def _module_file(path: Path) -> Path | None:
    """The file a local import actually runs.

    Args:
        path: A local module's file, or a local package's directory.

    Returns:
        The file itself, a package directory's __init__.py, or None when
        path is neither.
    """
    if ek.safe_is_file(path):
        return path
    init_py = path / "__init__.py"
    if ek.safe_is_dir(path) and ek.safe_is_file(init_py):
        return init_py
    return None


def _enqueue_top_level_imports(
    scan: ImportScan,
    module_path: Path,
    import_names: set[str],
    processed_paths: set[Path],
    modules_to_process: collections.deque[Path],
    *,
    is_stdlib: Callable[[str], bool],
) -> None:
    """Resolve a module's top-level imports and enqueue any new local modules.

    Newly found local modules and packages go onto the queue; a package goes
    on as its directory, which the queue opens through its __init__.py.
    """
    for import_name in import_names:
        if is_stdlib(import_name):
            scan.seen_stdlib_imports.add(import_name)
            continue  # Skip standard modules
        resolved = process_import(scan, import_name, module_path, is_stdlib=is_stdlib)
        if not resolved:
            scan.all_imports.add(import_name)
            continue
        possible_module_file_path = scan.custom_modules.get(import_name)
        if possible_module_file_path is None:
            continue
        actual_module_file_path = ek.ensure_path(possible_module_file_path)
        if _module_file(actual_module_file_path) is not None:
            if (
                actual_module_file_path not in processed_paths
                and actual_module_file_path not in modules_to_process
            ):
                modules_to_process.append(actual_module_file_path)


def _process_queue(
    settings: Settings,
    scan: ImportScan,
    modules_to_process: collections.deque[Path],
    processed_paths: set[Path],
    modules_info: dict[str, ModuleInfo],
    *,
    is_stdlib: Callable[[str], bool],
    do_sys_path_scan: bool,
) -> None:
    """Analyze every module on the queue, and every local module they import.

    Each module's top-level local imports are queued as it is analyzed, so the
    queue drains to a fixed point: everything local that the queued modules
    reach through top-level imports gets analyzed too. Both of the scan's
    passes use this, so a module first reached from inside a function is
    followed exactly as one reached from the top level is.

    Args:
        settings:           The run's fixed configuration.
        scan:               ImportScan accumulating what this run discovers.
        modules_to_process: The queue to drain: module files, or package
                            directories whose __init__.py is parsed.
        processed_paths:    Paths already analyzed this scan; updated.
        modules_info:       Module key to ModuleInfo; updated.
        is_stdlib:          Predicate returning True for standard-library names.
        do_sys_path_scan:   Whether to scan each module for sys.path mutations.
    """
    while modules_to_process:
        module_path = modules_to_process.popleft()  # first in, first out
        if not settings.rawlog:
            logging.info(
                "Processing module: %s where %s", module_path, type(module_path)
            )
        if ek.safe_is_dir(module_path):
            pkg_dir = module_path
            init_py = pkg_dir / "__init__.py"
            if ek.safe_is_file(init_py):
                # 1) Parse the package __init__.py
                module_path = init_py
                # 2) Also enqueue all other .py modules in that same folder
                for p in pkg_dir.iterdir():
                    if ek.is_python_script(p) and p.name != "__init__.py":
                        if p not in modules_to_process and p not in processed_paths:
                            modules_to_process.append(p)
            else:
                logging.error(
                    f"No __init__.py in package directory {pkg_dir}, skipping."
                )
                continue
        elif not ek.safe_is_file(module_path):
            logging.error(
                f"Skipping {module_path} because it is not a file or directory."
            )
            continue
        if module_path in processed_paths:
            continue
        processed_paths.add(module_path)
        result = _analyze_module(
            settings,
            scan,
            module_path,
            modules_info,
            do_sys_path_scan=do_sys_path_scan,
        )
        if result is None:
            continue
        module_key, module_info = result
        _enqueue_top_level_imports(
            scan,
            module_path,
            module_info.top_level_imports,
            processed_paths,
            modules_to_process,
            is_stdlib=is_stdlib,
        )


def _alias_map(scan: ImportScan) -> dict[str, str]:
    """Map each local module's import name to its module key.

    Args:
        scan: The scan whose custom_modules to map.

    Returns:
        Import name to the resolved file path the call graph keys modules by
        -- for a package, its __init__.py.
    """
    alias_to_key: dict[str, str] = {}
    for mod_name, mod_path in scan.custom_modules.items():
        module_file = _module_file(ek.ensure_path(mod_path))
        if module_file is not None:
            alias_to_key[mod_name] = os.fspath(module_file.resolve())
    return alias_to_key


def find_imports_in_script(
    settings: Settings,
    first_path: str | os.PathLike[str],
    *,
    is_stdlib: Callable[[str], bool],
    scan: ImportScan | None = None,
) -> ImportScan:
    """Find all imports in the script.

    Includes functions and classes that it imports from its dependencies.

    Args:
        settings:   Settings object containing the run's fixed configuration.
        first_path: Path to the Python script to analyze for imports.
        is_stdlib:  Predicate returning True for names in the target
                    interpreter's standard library.
        scan:       Prior state to keep scanning into, e.g. a caller's
                    already-populated custom_modules map. Defaults to a
                    fresh, empty ImportScan.

    Returns:
        The scan argument (or a fresh ImportScan if none was given),
        populated with everything found in the script.

    Raises:
        FileNotFoundError: If the first_path does not exist.
        IsADirectoryError: If the first_path exists but is a directory.
        ValueError:        If the first_path exists but is not a regular file.
    """
    scan = scan if scan is not None else ImportScan()
    first_path = ek.ensure_file(first_path)
    if not ek.is_python_script(first_path) or not ek.compile_code(first_path):
        logging.error(f"Skipping invalid Python script: {first_path}")
        return scan
    processed_paths: set[Path] = set()
    modules_info: dict[str, ModuleInfo] = {}
    modules_to_process: collections.deque[Path] = collections.deque([first_path])
    _process_queue(
        settings,
        scan,
        modules_to_process,
        processed_paths,
        modules_info,
        is_stdlib=is_stdlib,
        do_sys_path_scan=True,
    )
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Modules processed so far:")
    for module_key, m_info in modules_info.items():
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(
                "Module: %s, Classes: %s, Functions: %s",
                module_key,
                m_info.classes,
                list(m_info.functions.keys()),
            )

    # Build alias → file-path-key mapping for local modules
    _alias_to_key = _alias_map(scan)

    # Now build the call graph
    call_graph = build_call_graph(modules_info, alias_to_key=_alias_to_key)

    # Collect used imports starting from the first module
    used_imports: set[str] = set()
    visited_funcs: set[str] = set()

    def collect_imports_from_module(module_key: str) -> None:
        """Recursively collect used imports from a module."""
        module_info = modules_info[module_key]
        used_imports.update(module_info.top_level_imports)
        for func_name in module_info.top_level_calls:
            called_module, called_name = split_function_name(func_name, module_key)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(
                    "Collecting used imports for module '%s' and func_name '%s'",
                    called_module,
                    called_name,
                )
            used_imports.update(
                collect_used_imports(
                    called_module,  # Use the extracted module name
                    called_name,  # Use the extracted function name
                    call_graph,
                    modules_info,
                    visited_funcs,
                    _alias_to_key,
                )
            )
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(
                    "Used imports collected from '%s' in '%s': %s",
                    called_name,
                    called_module,
                    used_imports,
                )
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(
                "Used imports after collecting from module %s: %s",
                module_key,
                used_imports,
            )

    # Scan the *initial* script (first_path) everywhere:
    first_module_key = os.fspath(first_path.resolve())
    collect_imports_from_module(first_module_key)

    # Now process used imports and recursively dive into any new local modules.
    processed_used_imports: set[str] = set()
    new_modules_found = True
    while new_modules_found:
        new_modules_found = False
        for import_name in used_imports.copy():
            # Skip built-ins or any we've already handled this round
            if is_stdlib(import_name):
                scan.seen_stdlib_imports.add(import_name)
                continue
            if import_name in processed_used_imports:
                continue
            processed_used_imports.add(import_name)
            process_import(scan, import_name, first_path, is_stdlib=is_stdlib)
            if import_name in scan.custom_modules:
                # It's a known local module that we haven't processed yet
                module_file_path = ek.ensure_path(scan.custom_modules[import_name])
                module_file = _module_file(module_file_path)
                if module_file is None:
                    logging.error(
                        f"Custom module path for {import_name} is neither a file nor a package: {module_file_path}"
                    )
                    continue
                new_module_key = os.fspath(module_file.resolve())
                if new_module_key not in modules_info:
                    # Reached for the first time, from inside a function:
                    # analyze it and every local module it imports, as the
                    # first pass would have. (The first pass's queue is empty
                    # by now, so "queued" can never stand in for "analyzed".)
                    modules_to_process.append(module_file_path)
                    _process_queue(
                        settings,
                        scan,
                        modules_to_process,
                        processed_paths,
                        modules_info,
                        is_stdlib=is_stdlib,
                        do_sys_path_scan=False,
                    )
                    if new_module_key not in modules_info:
                        continue  # It would not parse.
                    # Rebuild alias map and call graph with the new modules included
                    _alias_to_key = _alias_map(scan)
                    call_graph = build_call_graph(modules_info, _alias_to_key)
                    new_modules_found = True
                # Trace its top-level calls
                old_size = len(used_imports)
                collect_imports_from_module(new_module_key)
                if len(used_imports) > old_size:
                    new_modules_found = True
            else:
                # If not a local module, add to scan.all_imports
                scan.all_imports.add(import_name)

    return scan
