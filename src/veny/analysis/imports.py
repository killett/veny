"""Walk a module's AST and record what it imports, and from where.

Import names are normalized to their top-level component before anything
classifies them, so a dotted name never reaches the stdlib check verbatim.
"""

import ast
import logging
import os
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import emmykit as ek

from .call_graph import _SEP, FunctionInfo, ModuleInfo
from .literals import safe_eval
from .scan_state import ImportScan


class SysPathVisitor(ast.NodeVisitor):
    """Visitor class to extract sys.path modifications."""

    def __init__(self, pathlib_aliases: set[str] | None = None) -> None:
        """Initialize the sys.path visitor."""
        self.paths = set()
        self._aliases = pathlib_aliases or set()

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit an assignment statement and check if it's modifying sys.path."""
        if (
            node.targets
            and isinstance(node.targets[0], ast.Attribute)
            and isinstance(node.targets[0].value, ast.Name)
            and node.targets[0].value.id == "sys"
            and node.targets[0].attr == "path"
        ):
            paths = safe_eval(ast.unparse(node.value), pathlib_aliases=self._aliases)
            if isinstance(paths, list):
                for path in paths:
                    self.paths.add(path)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Visit a function call and check if it's modifying sys.path."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "sys"
            and node.func.value.attr == "path"
            and node.func.attr in {"append", "insert"}
        ):
            if node.args and (
                path := safe_eval(
                    ast.unparse(node.args[-1]), pathlib_aliases=self._aliases
                )
            ):
                self.paths.add(path)
        self.generic_visit(node)


def process_import(
    scan: ImportScan,
    module_name: str,
    file_path: str | os.PathLike[str],
    *,
    is_stdlib: Callable[[str], bool],
) -> bool:
    """Process an import by checking if it's a local custom module or a standard import, and handle it accordingly."""
    if is_stdlib(module_name):
        scan.seen_stdlib_imports.add(module_name)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Skipping standard library import: %s", module_name)
        return False

    file_path = ek.ensure_file(file_path)

    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Processing import: %s from file %s", module_name, file_path)

    base_dir = file_path.parent
    module_path_str = module_name.replace(".", os.sep)

    # Avoid loopback to the same file
    if module_name == file_path.stem:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Avoiding loopback to the same file: %s", module_name)
        return False
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Constructed module path: %s", module_path_str)

    # Check if the import is a .py file in the same directory
    potential_file_path = (base_dir / f"{module_path_str}.py").expanduser().resolve()
    if (
        ek.safe_is_file(potential_file_path)
        and potential_file_path not in scan.samedir_files
    ):
        scan.custom_modules[module_name] = potential_file_path
        scan.loaded_custom_modules.add(module_name)
        scan.samedir_files.append(potential_file_path)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Added same directory file: %s", potential_file_path)
        return True

    # Check if the import is a package (directory with __init__.py)
    potential_dir_path = (base_dir / module_path_str).expanduser().resolve()
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Constructed potential directory path: %s", potential_dir_path)
    if (
        ek.safe_is_dir(potential_dir_path)
        and ek.safe_is_file(potential_dir_path / "__init__.py")
        and module_path_str not in scan.subfolders
    ):
        scan.custom_modules[module_name] = potential_dir_path
        scan.loaded_custom_modules.add(module_name)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Resolved local package to: %s", potential_dir_path)
        scan.subfolders.append(module_path_str)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Added subfolder: %s", module_path_str)
        return True

    # Check if this module is in the custom_modules dictionary.
    if module_name in scan.custom_modules:
        module_file = scan.custom_modules[module_name]
        if module_name not in scan.loaded_custom_modules:
            scan.loaded_custom_modules.add(module_name)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(
                    "Resolved via custom_modules: %s → %s", module_name, module_file
                )
        return True

    # --- fall back to sys.path hints (folders added at runtime) ---
    for root in scan.sys_path_hints:
        # Look for a single-file module
        candidate = (root / f"{module_path_str}.py").expanduser().resolve()
        if ek.safe_is_file(candidate):
            scan.custom_modules[module_name] = candidate
            scan.loaded_custom_modules.add(module_name)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(
                    "Resolved via sys.path hint (file): %s → %s", module_name, candidate
                )
            return True

        # Look for a package dir with __init__.py
        pkg = (root / module_path_str).expanduser().resolve()
        if ek.safe_is_dir(pkg) and ek.safe_is_file(pkg / "__init__.py"):
            scan.custom_modules[module_name] = pkg
            scan.loaded_custom_modules.add(module_name)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(
                    "Resolved via sys.path hint (package): %s → %s", module_name, pkg
                )
            return True

    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(
            "Could not resolve local import, treating as external: %s", module_name
        )
    return False


class ImportFunctionCollector(ast.NodeVisitor):
    """Visitor class to collect function and import information from a module."""

    def __init__(
        self, scan: ImportScan, module_name: str, file_path: str | os.PathLike[str]
    ) -> None:
        """Initialize the import function collector."""
        self.module_info: ModuleInfo = ModuleInfo(module_name)
        self.current_function: str | None = None
        self.current_class: str | None = None
        self.aliases: dict[str, str] = {}
        self.scan: ImportScan = scan
        self.file_path: Path = ek.ensure_path(file_path)
        self.base_classes: dict[str, list[str]] = {}
        self.attr_types: defaultdict[str, dict[str, str]] = defaultdict(
            dict
        )  # {class_name: {attr_name: "QualifiedTypeName"}}
        self._param_types: dict[str, str] = {}  # param name -> "QualifiedTypeName"

    def visit_Import(self, node: ast.Import) -> None:
        """Visit an import statement and add the imported module to the module's list of imports."""
        for alias in node.names:
            name = alias.asname or alias.name
            full_name = alias.name
            top_level_package = full_name.split(".")[0]
            self.aliases[name] = full_name
            if self.current_function:
                self.module_info.functions[
                    self.current_function
                ].imports_in_function.add(top_level_package)
            else:
                self.module_info.top_level_imports.add(top_level_package)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit an import from statement and add the imported module to the module's list of imports."""
        module = node.module or ""
        # Extract the top-level package
        top_level_package = module.split(".")[0] if module else ""
        for alias in node.names:
            full_name = f"{module}.{alias.name}" if module else alias.name
            name = alias.asname or alias.name
            self.aliases[name] = full_name
            if self.current_function:
                self.module_info.functions[
                    self.current_function
                ].imports_in_function.add(top_level_package)
            else:
                self.module_info.top_level_imports.add(top_level_package)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit a function definition and add it to the module's list of functions."""
        func_name = node.name
        if self.current_class:
            func_name = f"{self.current_class}.{func_name}"
        self.module_info.functions[func_name] = FunctionInfo(func_name)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(
                "Added function: %s to module %s",
                func_name,
                self.module_info.module_name,
            )
        prev_function = self.current_function
        self.current_function = func_name
        # Track parameter annotations (only while inside this function)
        self._param_types = {}
        for a in node.args.args:
            if a.annotation is not None:
                t = self._type_name(a.annotation)
                if t:
                    self._param_types[a.arg] = t
        self.generic_visit(node)
        self.current_function = prev_function
        self._param_types = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class definition and set the current class."""
        self.module_info.classes.add(node.name)
        prev_class = self.current_class
        self.current_class = node.name

        # Record base classes before visiting the body
        base_class_names = []
        for base in node.bases:
            base_name = self.get_full_name(base)
            if base_name:
                parts = base_name.split(".")
                if parts and parts[0] in self.aliases:
                    alias_target = self.aliases[parts[0]]
                    base_name = alias_target + "." + ".".join(parts[1:])
                base_class_names.append(base_name)
        self.base_classes[node.name] = base_class_names
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(
                "Recorded base classes for %s: %s",
                node.name,
                self.base_classes[node.name],
            )
        # Now that base_classes is set, visit the class body
        self.generic_visit(node)
        self.current_class = prev_class

    def _qual(self, tail: str) -> str:
        """Prepend the current module name + '_SEP' to the input string."""
        return f"{self.module_info.module_name}{_SEP}{tail}"

    def extract_module_name_from_import(self, node: ast.Call) -> str | None:
        """Extract the module name from a dynamic import using __import__."""
        if node.args:
            module_arg = node.args[0]
            if isinstance(module_arg, ast.Constant) and isinstance(
                module_arg.value, str
            ):
                module_name = module_arg.value.split(".")[0]  # Get top-level package
                return module_name
            else:
                # Handle cases where module name cannot be resolved
                logging.error(
                    f"Cannot resolve dynamic import with non-constant module name: {ast.unparse(node)}"
                )
                return None
        else:
            logging.error(f"No arguments provided to __import__(): {ast.unparse(node)}")
            return None

    def _record_call(self, qualified: str) -> None:
        """Record a function call, either in the current function or at the top level."""
        if self.current_function:
            self.module_info.functions[self.current_function].function_calls.add(
                qualified
            )
        else:
            self.module_info.top_level_calls.add(qualified)

    def _maybe_alias(self, name: str) -> str:
        """Replace the first part of 'name' with its alias if it exists."""
        parts = name.split(".")
        if parts and parts[0] in self.aliases:
            parts[0] = self.aliases[parts[0]]
        return ".".join(parts)

    def _maybe_record_func_ref(self, node: ast.AST) -> None:
        """If 'node' looks like a reference to a function, record it as a call."""
        ref = self.get_full_name(node)
        if not ref:
            return
        # Case 1: plain name referring to a function defined in this module
        if "." not in ref and ref in self.module_info.functions:
            self._record_call(ref)
            return
        # Case 2: class defined here passed as a constructor -> treat as __init__
        if "." not in ref and ref in self.module_info.classes:
            self._record_call(self._qual(f"{ref}.__init__"))
            return
        # Case 3: qualified like other_module.func
        if "." in ref:
            qualified = self._maybe_alias(ref)
            self._record_call(qualified)
            return

    def visit_Call(self, node: ast.Call) -> None:
        """Visit a function call and add it to the function's list of calls."""
        func_name = self.get_full_name(node.func)
        original_func_name = func_name
        # Resolve self.<attr>.<method> to the attribute's type
        if func_name and self.current_class:
            parts = func_name.split(".")
            # Pattern: CurrentClass.<attr>.<method>[.<more>]
            if len(parts) >= 3 and parts[0] == self.current_class:
                attr = parts[1]
                method_tail = ".".join(parts[2:])
                t = self.attr_types.get(self.current_class, {}).get(attr)
                if t:
                    # Qualify local classes with the current module
                    if t in self.module_info.classes:
                        func_name = self._qual(f"{t}.{method_tail}")
                    else:
                        # t might already be qualified by an alias (e.g., "ek.LLMs")
                        func_name = f"{t}.{method_tail}"
        if func_name:
            parts = func_name.split(".")
            if parts[0] in self.module_info.classes:
                # It's a class from this module
                if func_name in self.module_info.classes:
                    # func_name is exactly the class name, treat as constructor
                    if logging.getLogger().isEnabledFor(logging.DEBUG):
                        logging.debug(
                            "%s is identified as a class. Converting to __init__ call.",
                            func_name,
                        )
                    func_name = self._qual(f"{func_name}.__init__")
                else:
                    # It's a method/attribute call on a class from this module
                    if logging.getLogger().isEnabledFor(logging.DEBUG):
                        logging.debug(
                            "%s is a method/attribute on a class from the same module. Qualifying with module name.",
                            func_name,
                        )
                    func_name = self._qual(func_name)
            else:
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug("%s is not a class, leaving as-is.", func_name)
            # If func_name corresponds to a class in this module, treat it as calling __init__
            if func_name in self.module_info.classes:
                func_name = f"{func_name}.__init__"
            # Handle dynamic imports
            if func_name == "__import__":
                module_name = self.extract_module_name_from_import(node)
                if module_name:
                    if self.current_function:
                        self.module_info.functions[
                            self.current_function
                        ].imports_in_function.add(module_name)
                    else:
                        self.module_info.top_level_imports.add(module_name)
                else:
                    logging.warning(
                        "Cannot resolve dynamic import: %s", ast.unparse(node)
                    )
            # Handle importlib.import_module(...)
            elif func_name == "importlib.import_module":
                abs_name = self.extract_module_name_from_importlib_import_module(node)
                if abs_name:
                    self._register_import_name(abs_name)
                else:
                    logging.warning(
                        "Cannot resolve importlib.import_module call: %s",
                        ast.unparse(node),
                    )
            # Handle importlib.util.spec_from_file_location(...)
            elif func_name == "importlib.util.spec_from_file_location":
                res = self.extract_from_importlib_spec_from_file_location(node)
                if res:
                    mod, loc = res
                    self._register_import_name(mod)
                    if loc:
                        self._register_constant_path_for_module(mod, loc)
            # Handle importlib.machinery.SourceFileLoader(...).load_module()
            # We match either the constructor itself or the chained .load_module():
            elif func_name == "importlib.machinery.SourceFileLoader":
                res = self.extract_from_importlib_sourcefileloader(node)
                if res:
                    mod, loc = res
                    self._register_import_name(mod)
                    if loc:
                        self._register_constant_path_for_module(mod, loc)
            # Also catch the chained call: importlib.machinery.SourceFileLoader(...).load_module()
            elif (
                isinstance(node.func, ast.Attribute) and node.func.attr == "load_module"
            ):
                # node.func.value should be the Call to SourceFileLoader(...)
                loader_call = node.func.value
                if isinstance(loader_call, ast.Call):
                    callee = self.get_full_name(loader_call.func)
                    if callee == "importlib.machinery.SourceFileLoader":
                        res = self.extract_from_importlib_sourcefileloader(loader_call)
                        if res:
                            mod, loc = res
                            self._register_import_name(mod)
                            if loc:
                                self._register_constant_path_for_module(mod, loc)
                        else:
                            logging.warning(
                                "Cannot resolve SourceFileLoader(...).load_module() call: %s",
                                ast.unparse(node),
                            )
            elif func_name.startswith("super."):
                # Handle super calls
                _, method_name = func_name.split(".", 1)
                if self.current_class and self.current_class in self.base_classes:
                    base_classes = self.base_classes[self.current_class]
                    if base_classes:
                        base_class = base_classes[0]  # Assuming single inheritance
                        func_name = f"{base_class}.{method_name}"
                self._record_call(func_name)
            else:
                # Normal calls
                self._record_call(func_name)
        for a in node.args:
            self._maybe_record_func_ref(a)
        for kw in node.keywords:
            if kw.value is not None:
                self._maybe_record_func_ref(kw.value)
        self.generic_visit(node)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(
                "Call found: original func_name=%s, resolved func_name=%s",
                original_func_name,
                func_name,
            )
        if self.current_function:
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(
                    "Adding function call %s to %s", func_name, self.current_function
                )
        else:
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug("Adding top-level call: %s", func_name)

    def get_full_name(self, node: ast.AST) -> str | None:
        """Get the full name of a node, including any aliases."""
        if isinstance(node, ast.Name):  # Handle variable names
            if node.id in ("self", "cls"):  # Handle class methods
                if self.current_class:
                    return self.current_class
                else:
                    return node.id
            elif node.id == "super":  # Handle super() calls
                return "super"
            else:
                return self.aliases.get(node.id, node.id)
        elif isinstance(node, ast.Attribute):  # Handle attribute access
            value = self.get_full_name(node.value)
            return f"{value}.{node.attr}" if value else node.attr
        elif isinstance(node, ast.Call):  # Handle super() calls
            func_name = self.get_full_name(node.func)
            return func_name
        return None

    def _type_name(self, node: ast.AST) -> str | None:
        """Extract a string type name from an annotation or qualified name.

        Handles Name or Attribute, using aliases when needed.
        """
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self._type_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Visit an annotated assignment and record attribute types.

        e.g. self.thing: Thing = thing.
        """
        if (
            self.current_class
            and isinstance(node.target, ast.Attribute)
            and isinstance(node.target.value, ast.Name)
            and node.target.value.id == "self"
        ):
            t = self._type_name(node.annotation)
            if t:
                self.attr_types[self.current_class][node.target.attr] = t
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit an assignment and try to infer attribute types from RHS.

        e.g. self.thing = thing   (infer type from param annotation if possible).
        """
        for tgt in node.targets:
            if (
                self.current_class
                and isinstance(tgt, ast.Attribute)
                and isinstance(tgt.value, ast.Name)
                and tgt.value.id == "self"
            ):
                # Try to infer type from RHS if RHS is a Name that matches a typed param
                if isinstance(node.value, ast.Name):
                    pname = node.value.id
                    t = self._param_types.get(pname)
                    if t:
                        self.attr_types[self.current_class][tgt.attr] = t
        self.generic_visit(node)

    # --- Importlib helpers -------------------------------------------------

    def _const_str(self, node: ast.AST) -> str | None:
        """Return node.value if the node is a constant string; else None."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _resolve_relative_module(self, name: str, package: str | None) -> str | None:
        """Resolve 'name' that may start with dots against an absolute 'package'.

        Mirrors importlib semantics roughly; for our purposes we only need to
        resolve to a package string to feed the rest of the pipeline.
        """
        if not name:
            return None
        if not name.startswith("."):
            return name  # already absolute
        if not package:
            return None  # cannot resolve without a package
        # Count leading dots
        i = 0
        while i < len(name) and name[i] == ".":
            i += 1
        # Climb up 'i-1' levels from package
        pkg_parts = package.split(".")
        if i - 1 > len(pkg_parts):
            return None
        base = ".".join(pkg_parts[: len(pkg_parts) - (i - 1)])
        tail = name[i:]
        return f"{base}.{tail}" if tail else base

    def _register_import_name(self, module_name: str) -> None:
        """Record an import for the current function, or for top level.

        Uses the top-level package, to match the existing pipeline.
        """
        top_level = module_name.split(".")[0] if module_name else None
        if not top_level:
            return
        if self.current_function:
            self.module_info.functions[self.current_function].imports_in_function.add(
                top_level
            )
        else:
            self.module_info.top_level_imports.add(top_level)

    def _register_constant_path_for_module(
        self, module_name: str, path_str: str
    ) -> None:
        """Map a dynamically loaded module to its constant file path.

        Best effort: mapping it immediately lets later phases resolve it as a
        local module.
        """
        try:
            # Resolve relative to the file we're analyzing
            base_dir = self.file_path.parent
            p = (
                (base_dir / path_str).expanduser().resolve()
                if not os.path.isabs(path_str)
                else Path(path_str).expanduser().resolve()
            )
        except Exception as e:
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(
                    "Failed to resolve path %s given base_dir %s: %s",
                    path_str,
                    os.fspath(base_dir),
                    e,
                )
            return
        # Only accept .py files or a directory with __init__.py
        if p.suffix == ".py" and ek.safe_exists(p):
            self.scan.custom_modules[module_name] = p
        elif ek.safe_is_dir(p) and ek.safe_exists(p / "__init__.py"):
            self.scan.custom_modules[module_name] = p

    def extract_module_name_from_importlib_import_module(
        self, node: ast.Call
    ) -> str | None:
        """Handle importlib.import_module(name, package=None) and aliased import_module().

        Only constant strings are supported.
        """
        if not node.args:
            return None
        name = self._const_str(node.args[0])
        if name is None:
            logging.error(
                f"Cannot resolve import_module with non-constant name: {ast.unparse(node)}"
            )
            return None
        pkg = None
        if len(node.args) >= 2:
            pkg = self._const_str(node.args[1])
        else:
            for kw in node.keywords or []:
                if kw.arg == "package":
                    pkg = self._const_str(kw.value)
        if name.startswith("."):
            abs_name = self._resolve_relative_module(name, pkg)
            if abs_name is None:
                logging.error(
                    f"Cannot resolve relative import_module without constant package: {ast.unparse(node)}"
                )
                return None
            return abs_name
        return name

    def extract_from_importlib_spec_from_file_location(
        self, node: ast.Call
    ) -> tuple[str, str] | None:
        """Handle importlib.util.spec_from_file_location(name, location, ...).

        Returns (module_name, location_path) if both are constant strings.
        """
        if len(node.args) < 2:
            return None
        mod = self._const_str(node.args[0])
        loc = self._const_str(node.args[1])
        if mod is None:
            logging.error(
                f"Cannot resolve spec_from_file_location with non-constant module name: {ast.unparse(node)}"
            )
            return None
        if loc is None:
            # We can still record the import name, just no path to register
            return (mod, None)
        return (mod, loc)

    def extract_from_importlib_sourcefileloader(
        self, node: ast.Call
    ) -> tuple[str, str] | None:
        """Handle importlib.machinery.SourceFileLoader(name, path).

        Returns (module_name, path) if both are constant strings.
        """
        if len(node.args) < 2:
            return None
        mod = self._const_str(node.args[0])
        loc = self._const_str(node.args[1])
        if mod is None:
            logging.error(
                f"Cannot resolve SourceFileLoader with non-constant module name: {ast.unparse(node)}"
            )
            return None
        if loc is None:
            return (mod, None)
        return (mod, loc)
