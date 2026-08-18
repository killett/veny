"""The call graph of a scanned script, and what each function reaches.

An import inside a function only matters if that function is actually
reachable from the script's entry point, so this records who calls whom and
walks the result.
"""

import ast
import logging


class FunctionInfo:
    """Class to hold information about a function."""

    def __init__(self, function_name: str, node: ast.FunctionDef) -> None:
        """Initialize the function information, storing its AST node too."""
        self.function_name: str = function_name
        self.ast_node: ast.FunctionDef = node
        self.imports_in_function: set[str] = set()
        self.function_calls: set[str] = set()


class ModuleInfo:
    """Class to hold information about a module."""

    def __init__(self, module_name: str) -> None:
        """Initialize the module information."""
        self.module_name: str = module_name
        self.top_level_imports: set[str] = set()
        self.functions: dict[str, FunctionInfo] = {}
        self.top_level_calls: set[str] = set()
        self.aliases: dict[str, str] = {}
        self.classes: set[str] = set()
        self.base_classes: dict[str, list[str]] = {}


_SEP: str = "::"  # Path-safe separator to distinguish class methods


def split_function_name(called_func: str, default_module: str) -> tuple[str, str]:
    """Split a fully qualified function id into (module_key, func_part).

    Preferred separator is _SEP (path-safe). Fall back to the first dot
    for legacy strings that still look like 'module.func'.
    """
    if _SEP in called_func:
        m, f = called_func.split(_SEP, 1)
        return m, f
    # legacy fallback
    parts = called_func.split(".")
    if len(parts) > 1:
        return parts[0], ".".join(parts[1:])
    return default_module, called_func


def _resolve(name: str, alias_to_key: dict[str, str] | None) -> str:
    """Resolve an alias-based module name to its file-path-based key."""
    return alias_to_key.get(name, name) if alias_to_key else name


def build_call_graph(
    modules_info: dict[str, ModuleInfo], alias_to_key: dict[str, str] | None = None
) -> dict[str, set[str]]:
    """Build a call graph from the function calls in the modules."""
    call_graph = {}
    for module_key, module_info in modules_info.items():
        for func_name, func_info in module_info.functions.items():
            full_func_name = f"{module_key}{_SEP}{func_name}"
            call_graph[full_func_name] = set()
            for called_func in func_info.function_calls:
                called_module, called_name = split_function_name(
                    called_func, module_key
                )
                called_module = _resolve(called_module, alias_to_key)

                # If target looks like Class.method and isn't present, try the base class.
                if called_module in modules_info:
                    mi = modules_info[called_module]
                    if "." in called_name:
                        cls, meth = called_name.split(".", 1)
                        if called_name not in mi.functions and cls in mi.base_classes:
                            bases = mi.base_classes.get(cls, [])
                            if bases:
                                base = bases[0]
                                if base in mi.classes:
                                    called_full_name = (
                                        f"{called_module}{_SEP}{base}.{meth}"
                                    )
                                else:
                                    if "." in base:
                                        base_mod, base_sym = base.split(".", 1)
                                        called_full_name = f"{_resolve(base_mod, alias_to_key)}{_SEP}{base_sym}.{meth}"
                                    else:
                                        called_full_name = f"{base}{_SEP}{meth}"
                                call_graph[full_func_name].add(called_full_name)
                                continue

                # Check if called_name is a class in the module
                if (
                    called_module in modules_info
                    and called_name in modules_info[called_module].classes
                ):
                    called_full_name = f"{called_module}{_SEP}{called_name}.__init__"
                else:
                    called_full_name = f"{called_module}{_SEP}{called_name}"
                call_graph[full_func_name].add(called_full_name)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Call graph constructed:")
    for func, calls in call_graph.items():
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("%s calls: %s", func, calls)
    return call_graph


def collect_used_imports(
    start_module: str,
    start_func: str,
    call_graph: dict[str, set[str]],
    modules_info: dict[str, ModuleInfo],
    visited: set[str] | None = None,
    alias_to_key: dict[str, str] | None = None,
) -> set[str]:
    """Collect all imports used in a function and its callees.

    Args:
        start_module: The module where the function is defined.
        start_func:   The function name to start collecting imports from.
        call_graph:   A dictionary representing the call graph of functions.
        modules_info: A dictionary mapping module keys to ModuleInfo objects.
        visited:      A set of fully qualified function names that have already been visited.
        alias_to_key: A dictionary mapping module aliases to their file-path-based keys.

    Returns:
        A set of import statements used in the function and its callees.
    """
    if visited is None:
        visited = set()
    # Resolve alias-based module name to file-path-based key
    start_module = _resolve(start_module, alias_to_key)
    full_func_name: str = f"{start_module}{_SEP}{start_func}"
    if full_func_name in visited:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Already visited %s, skipping.", full_func_name)
        return set()
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Visiting function: %s", full_func_name)
    visited.add(full_func_name)
    imports: set[str] = set()
    module_info = modules_info.get(start_module)
    if module_info:
        func_info = module_info.functions.get(start_func)
        if func_info:
            if func_info.imports_in_function:
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(
                        "Function %s imports: %s",
                        full_func_name,
                        func_info.imports_in_function,
                    )
            imports.update(func_info.imports_in_function)
    # Follow resolved edges from the call graph:
    edges = call_graph.get(full_func_name, set())
    for called_full in edges:
        called_module, called_name = split_function_name(called_full, start_module)
        imports.update(
            collect_used_imports(
                called_module,
                called_name,
                call_graph,
                modules_info,
                visited,
                alias_to_key,
            )
        )
    return imports
