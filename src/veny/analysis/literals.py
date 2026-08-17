"""Evaluate the restricted subset of expressions veny reads out of source.

A script's sys.path manipulation is only useful to veny if it can be read
without running the script, so this evaluates literals, a short allow-list of
os.path calls, and pathlib construction -- and refuses everything else.
"""

import ast
import logging
import os
from pathlib import Path
from typing import Any

import emmykit as ek

PATHLIB_CONCRETE = {"Path", "PosixPath", "WindowsPath"}
PATHLIB_PURE = {"PurePath", "PurePosixPath", "PureWindowsPath"}
PATHLIB_ALL = PATHLIB_CONCRETE | PATHLIB_PURE


def collect_pathlib_aliases(module: ast.Module) -> set[str]:
    """Return the local names that refer to pathlib classes.

    Covers Path/PosixPath/WindowsPath and the Pure* variants, handles aliasing
    via 'as', and works even if imports are nested: the whole tree is scanned.
    """
    aliases: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
            for alias in node.names:
                if alias.name in PATHLIB_ALL:
                    aliases.add(alias.asname or alias.name)
    return aliases


def is_pathlib_ctor(fn: ast.AST, pathlib_aliases: set[str], allow_pure: bool) -> bool:
    """True if 'fn' is a constructor for a pathlib *Path* type.

    - When allow_pure=False, only concrete (filesystem) paths are allowed.
    - When allow_pure=True, accept both concrete and pure paths.
    """
    allowed = PATHLIB_CONCRETE | (PATHLIB_PURE if allow_pure else set())

    # Case: Name (possibly aliased import) e.g., Path(...), P(...), PurePath(...)
    if isinstance(fn, ast.Name):
        if fn.id in allowed or fn.id in pathlib_aliases:
            return True

    # Case: attribute like pathlib.Path(...), pathlib.PurePath(...)
    if (
        isinstance(fn, ast.Attribute)
        and isinstance(fn.value, ast.Name)
        and fn.value.id == "pathlib"
        and fn.attr in allowed
    ):
        return True

    return False


def _safe_eval_node(node: ast.AST, pathlib_aliases: set[str] | None = None) -> Any:  # noqa: ANN401  # Evaluates arbitrary literals: str, int, list, dict, Path. Any is the honest type.
    """Recursively evaluate a restricted subset of AST nodes.

    Supported:
    - Constants (strings, numbers, booleans, None)
    - Lists, tuples, dicts
    - os.getcwd()
    - os.path.(abspath|join|dirname|realpath)(<literal strings>)
    - pathlib.Path(<literal strings>).(resolve|absolute)() and .joinpath(<literal strings>...)
    - The "/" operator for joining pathlib Paths.

    Args:
        node:            The AST node to evaluate.
        pathlib_aliases: Optional set of local names that refer to pathlib classes.

    Returns:
        The evaluated Python object.

    Raises:
        ValueError: If the node contains unsupported syntax.
    """
    aliases = pathlib_aliases or set()
    # --- support "/" operator for path-like objects ---
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _safe_eval_node(node.left, pathlib_aliases=aliases)
        right = _safe_eval_node(node.right, pathlib_aliases=aliases)
        # accept strings or any PathLike (Path, etc.)
        if isinstance(left, (str, os.PathLike)) and isinstance(
            right, (str, os.PathLike)
        ):
            # Path(left) / right → Path; str(...) to get the string path
            return os.fspath(Path(left) / right)
        raise ValueError(f"Unsupported path division: {ast.unparse(node)}")

    # --- literals ---
    if isinstance(node, ast.Constant):
        # Python 3.8+: Constant covers str, int, float, bool, None
        return node.value

    # --- composite literals ---
    if isinstance(node, ast.List):
        return [_safe_eval_node(elt, pathlib_aliases=aliases) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_safe_eval_node(elt, pathlib_aliases=aliases) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _safe_eval_node(k, pathlib_aliases=aliases): _safe_eval_node(
                v, pathlib_aliases=aliases
            )
            for k, v in zip(node.keys, node.values, strict=False)
        }

    # --- calls ---
    if isinstance(node, ast.Call):
        func = node.func

        # os.getcwd()
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and func.attr == "getcwd"
            and len(node.args) == 0
        ):
            return os.getcwd()

        # os.path.* calls
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "path"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "os"
        ):
            method = func.attr
            allowed = {"abspath", "join", "dirname", "realpath"}
            if method in allowed:
                arg_vals = [
                    _safe_eval_node(arg, pathlib_aliases=aliases) for arg in node.args
                ]
                if all(isinstance(v, str) for v in arg_vals):
                    path_fn = getattr(os.path, method)
                    return path_fn(*arg_vals)

        # pathlib.Path(...).resolve()/absolute()
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "resolve",
            "absolute",
        }:
            func = node.func
            if isinstance(func.value, ast.Call):
                inner = func.value
                if (
                    is_pathlib_ctor(inner.func, aliases, allow_pure=False)
                    and len(inner.args) == 1
                ):
                    arg = _safe_eval_node(inner.args[0], pathlib_aliases=aliases)
                    if isinstance(arg, str):
                        # Recompute using canonical 'Path' and same method name
                        return os.fspath(getattr(Path(arg), func.attr)())

        # pathlib.Path(...).joinpath(...)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
            func = node.func
            if isinstance(func.value, ast.Call):
                inner = func.value
                if (
                    is_pathlib_ctor(inner.func, aliases, allow_pure=True)
                    and len(inner.args) == 1
                ):
                    base = _safe_eval_node(inner.args[0], pathlib_aliases=aliases)
                    parts = [
                        _safe_eval_node(a, pathlib_aliases=aliases) for a in node.args
                    ]
                    if isinstance(base, str) and all(isinstance(p, str) for p in parts):
                        return os.fspath(Path(base).joinpath(*parts))

        # unsupported call
        raise ValueError(f"Unsupported call: {ast.unparse(node)}")

    # anything else is disallowed
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def safe_eval(expr: str, pathlib_aliases: set[str] | None = None) -> Any | None:  # noqa: ANN401  # Same as _safe_eval_node: the value is whatever literal the expression held.
    """Safely evaluate a restricted Python expression string.

    Only these are allowed:
        - literals (str, int, float, bool, None)
        - lists, tuples, dicts of the above
        - os.getcwd()
        - os.path.(abspath|join|dirname|realpath)(<literal strings>)
        - pathlib.Path(<literal strings>).(resolve|absolute)() and
          .joinpath(<literal strings>...) and the "/" operator for joining paths.
        - The "/" operator for joining pathlib Paths.

    Args:
        expr:            The expression string to evaluate.
        pathlib_aliases: Optional set of local names that refer to pathlib classes.

    Returns:
        The evaluated Python object, or None on unsupported syntax.

    Raises:
        None: All errors are caught and None is returned.
    """
    try:
        # Parse in "eval" mode so we get an Expression node
        tree = ast.parse(expr, mode="eval")
        return _safe_eval_node(
            tree.body, pathlib_aliases=pathlib_aliases
        )  # tree.body is the root expr
    except (SyntaxError, ValueError) as e:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(
                "%s: Unsupported expression: %r: %s", ek.return_method_name(), expr, e
            )
        return None
