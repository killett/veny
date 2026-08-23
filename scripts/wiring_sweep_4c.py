"""Run phase 4c's STANDING CHECK: substitute each argument, see what goes red.

Phase 4c made four behaviour changes across the same four modules phase 4b
wired: (1) ``last_used.active_virtualenv_dir`` now answers from
``VIRTUAL_ENV`` instead of veny's own interpreter prefix, and
``pipeline.run``'s middle ``elif`` branch reads it; (2) ``cli._shell_status``
is a new single point for the ``128 - code`` signal arithmetic, called on
both of ``main``'s exit paths, including the ``--feeling-lucky`` one that used
to skip it; (3) ``pipeline.blank_slate`` reads ``args.yes`` so ``-y`` reaches
it; (4) all four ``pipeline.run_script`` call sites now pass
``announce=True``. This sweep re-scopes phase 4b's harness onto exactly the
code those four changes touch, so the index it produces reflects file:line
positions as phase 4c left them, not as 4b did.

For every argument at every call site in that scope -- ``last_used.py``
whole, ``pipeline.feeling_lucky``/``blank_slate``/``run_script`` whole plus
every ``run_script(...)`` call inside ``run`` and the whole of ``run``'s
rewritten ``elif`` branch, ``cache_search.find_match_dir_in_cache`` down to
the statement that spends ``try_last_used`` (unchanged from 4b -- only the
line numbers moved), and the whole of ``cli.main`` plus ``cli._shell_status``
-- replace the expression with a type-correct but wrong value, import-check
the modules, run the suite, and record the first test that fails. An
argument nothing catches is an OPEN HOLE; an argument the callee never reads
is DEAD.

Results land in the scratch directory as sweep4c.json; the reviewed version is
docs/superpowers/plans/2026-08-23-behaviour-changes-4c-wiring-index.md.

TRAP, recorded because it cost phase 4a a full run: `pixi run` sets
PYTHONPATH=src, and tests/test_import_guard.py spawns its own subprocess that
needs it. Without it that one test fails under EVERY mutation and reports a
spurious kill for each, hiding every real hole behind it. ENV below is what
stops that, and every mutation is import-checked before a failure is believed.
Kept exactly as 4b had it.

A second trap found while re-scoping for 4c and fixed here: the substitution
table mapped the argument name ``announce`` to the literal ``"True"``
unconditionally. Before phase 4c that was fine -- only one of the four
``run_script`` call sites passed ``announce=True`` at all, and the other
three did not pass it. Phase 4c's Task 4 made all four call sites pass the
literal ``announce=True``, so substituting the literal ``"True"`` over the
literal ``True`` already there is a no-op -- exactly the case ``apply()``
already guards against with a ``RuntimeError``, which would have aborted the
sweep partway through a twelve-minute run. Fixed by deleting the ``"announce"``
entry from ``BY_NAME`` below: the generic True/False literal flip further down
``substitute_for`` already produces the correct, non-no-op substitution
(``announce=True`` -> ``announce=False``), which is exactly the value that
should make ``test_every_launch_announces_the_command_it_is_about_to_run``
fail.

Usage:
    pixi run python scripts/wiring_sweep_4c.py
    pixi run python scripts/wiring_sweep_4c.py --list   # sites only, no run
"""

import argparse
import ast
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

REPO = pathlib.Path("/workspace")
OUT = pathlib.Path(os.environ.get("WIRING_SWEEP_OUT", tempfile.gettempdir()))
# `pixi run` sets PYTHONPATH=src, and tests/test_import_guard.py spawns its own
# subprocess that needs it. Without it that test fails on EVERY mutation, which
# reads as a kill and hides every real hole behind it.
ENV = {**os.environ, "PYTHONPATH": "src"}

FILES = (
    "src/veny/last_used.py",
    "src/veny/pipeline.py",
    "src/veny/cache_search.py",
    "src/veny/cli.py",
)

# A Target built from nothing this run owns, spelled so it needs no import in
# the module it is spliced into. Phase 4a injected a probe block above a
# marker line; this is the same idea without the splice.
PROBE_DIR = '__import__("pathlib").Path("/tmp/veny-wiring-probe")'
PROBE_PY = '__import__("pathlib").Path("/tmp/veny-wiring-probe/bin/python")'
PROBE_SCRIPT = '__import__("pathlib").Path("/tmp/veny-wiring-probe/script.py")'
PROBE_TARGET = (
    '__import__("veny.state", fromlist=["Target"]).Target('
    f"python_script={PROBE_SCRIPT}, script_dir={PROBE_DIR}, script_args=(), "
    'python_command="wiring-probe-python", timestamp="20000101-000000")'
)
PROBE_RECORD = (
    '__import__("veny.state", fromlist=["LastUsed"]).LastUsed('
    f"venv_dir={PROBE_DIR}, venv_python={PROBE_PY}, "
    'timestamp="20000101-000000")'
)
PROBE_SETTINGS = (
    '__import__("veny.settings", fromlist=["Settings"]).Settings('
    f'my_name="wiring-probe", my_dir={PROBE_DIR}, cwd={PROBE_DIR}, '
    'venv_name="wiringprobe", stay_out_list=(), search_above_this_dir=False, '
    "rawlog=True, known_bad_imports=frozenset(), also_needs={}, "
    'extra_requirements_file="wiring_probe.txt")'
)

# Substitutions by argument name, or by the tail of a dotted expression.
BY_NAME = {
    "rawlog": "True",
    "strict": "False",
    "my_name": '"wiring-probe"',
    "venv_name": '"wiringprobe"',
    "timestamp": '"20000101-000000"',
    "tag": '"0.0"',
    "encoding": '"latin-1"',
    "indent": "0",
    "extra_requirements_file": '"wiring_probe.txt"',
    "search_above_this_dir": "False",
    "my_dir": PROBE_DIR,
    "cwd": PROBE_DIR,
    "script_dir": PROBE_DIR,
    "venv_dir": PROBE_DIR,
    "venv_python": PROBE_PY,
    "python_script": PROBE_SCRIPT,
    "stay_out_list": "()",
    "known_bad_imports": "frozenset()",
    "also_needs": "{}",
    "extra_requirements": "{}",
    "uninstalled": "set()",
    "source_names": "frozenset()",
    "wanted": "[]",
    "record": PROBE_RECORD,
    "target": PROBE_TARGET,
}

# Substitutions by the whole expression: a different object of the same type.
BY_EXPR = {
    "args": "argparse.Namespace()",
    "target": PROBE_TARGET,
    "record": PROBE_RECORD,
    "settings": PROBE_SETTINGS,
    "payload": "{}",
    "path": PROBE_SCRIPT,
    "venv_dir": PROBE_DIR,
    "venv_python": PROBE_PY,
    "declared": '"/tmp/veny-wiring-probe"',
    "sys.prefix": '"/tmp/veny-wiring-probe"',
    "MY_NAME": '"wiring-probe"',
    "rawlog": "True",
    "start_time": '__import__("datetime").datetime(2000, 1, 1)',
    "log_mode": "logging.CRITICAL",
    "memory_handler": "None",
    "exc": '"wiring-probe"',
    "str(exc)": '"wiring-probe"',
    "sys.stderr": "sys.stdout",
    "run_settings": PROBE_SETTINGS,
    "stdlib": "stdlib_index.for_running_interpreter()",
    "requirements.all_imports": "frozenset()",
    "requirements.uninstalled": "set()",
    "set(requirements.all_imports)": "frozenset()",
    "path.read_text(encoding='utf-8')": '"{}"',
    "lambda: _load_last_used(target, my_name=settings.my_name, rawlog=settings.rawlog)": "(lambda: None)",
    "'myenv'": '"wiringprobe"',
    "'extra_requirements.txt'": '"wiring_probe.txt"',
    "'VIRTUAL_ENV'": '"WIRING_PROBE_ENV"',
    "'venv_dir'": '"wiring_probe_venv_dir"',
    "'venv_python'": '"wiring_probe_venv_python"',
    "'timestamp'": '"wiring_probe_timestamp"',
    "dict": "object",
    "str": "object",
    "Path.home() / MY_NAME": PROBE_DIR,
    "Path.cwd().expanduser().resolve(strict=True)": PROBE_DIR,
    "settings.DEFAULT_STAY_OUT_LIST": "()",
    "settings.DEFAULT_KNOWN_BAD_IMPORTS": "frozenset()",
    "settings.DEFAULT_ALSO_NEEDS": "{}",
    "record.venv_dir": PROBE_DIR,
    "record.venv_python": PROBE_PY,
    "handle.venv_dir": PROBE_DIR,
    "handle.venv_python": PROBE_PY,
    "target.script_dir": PROBE_DIR,
    "target.python_script": PROBE_SCRIPT,
    "target.timestamp": '"20000101-000000"',
    "target.script_args": "()",
    "list(target.script_args)": "[]",
    "settings.my_name": '"wiring-probe"',
    "settings.my_dir": PROBE_DIR,
    "settings.venv_name": '"wiringprobe"',
    "settings.rawlog": "True",
    "set(requirements.uninstalled)": "set()",
    "requirements.extra_requirements": "{}",
    "cache_search.interpreter_tag(stdlib)": '"0.0"',
    "last_used_venv_python": PROBE_PY,
    "json.dumps(payload, indent=4) + '\\n'": '"{}\\n"',
    "state.LastUsed(venv_dir=handle.venv_dir, venv_python=handle.venv_python, timestamp=target.timestamp)": PROBE_RECORD,
}


def substitute_for(argname: str, expr: str) -> str | None:
    """Pick a type-correct but wrong replacement for one argument.

    Args:
        argname: The parameter's name, or "positional N" when it has none.
        expr: The argument's source text, as unparsed from the AST.

    Returns:
        Replacement source, or None when nothing sensible is available.
    """
    if expr in BY_EXPR:
        return BY_EXPR[expr]
    key = "" if argname.startswith("positional") else argname
    if key and key in BY_NAME:
        return BY_NAME[key]
    for name, sub in BY_NAME.items():
        if expr.endswith("." + name) or expr == name:
            return sub
    if expr in {"True", "False"}:
        return "False" if expr == "True" else "True"
    if expr.startswith("os.fspath("):
        return '"/tmp/veny-wiring-probe"'
    if expr.startswith("getattr("):
        return f"not {expr}"
    if expr.startswith(('"', "'", 'f"', "f'")):
        return '"wiring-probe"'
    return None


def _func_name(node: ast.Call) -> str | None:
    """The dotted name of a call's callee, or None for a call of a call."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return f"{ast.unparse(func.value)}.{func.attr}"
    if isinstance(func, ast.Name):
        return func.id
    return None


def _defs(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    """Index a module's top-level and nested function definitions by name."""
    found: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            found[node.name] = node
    return found


def _calls_under(node: ast.AST) -> list[ast.Call]:
    """Every Call in a subtree, in source order.

    Deliberately unfiltered. Phase 4a's harness kept an allowlist of callee
    names, and its own index records that 3e's hand-written list missed a
    whole spelling; the only list here is the scope of *which code* is in
    the phase, decided in scoped_calls() from the structure of the modules.
    Logging and print arguments are swept like any other -- veny's
    commentary is behaviour the suite asserts on.

    Args:
        node: The subtree to search.

    Returns:
        The calls, in source order.
    """
    found = [child for child in ast.walk(node) if isinstance(child, ast.Call)]
    return sorted(found, key=lambda c: (c.lineno, c.col_offset))


def scoped_calls() -> list[tuple[str, ast.Call]]:
    """Every call site phase 4c created or changed, straight from the AST.

    The scope is written as four rules rather than a list of names: phase 3e's
    symbol sweep worked from a hand-written list and missed a whole spelling,
    and this function exists so that cannot recur.

    Returns:
        (file, call node) pairs, one per call site in scope.
    """
    out: list[tuple[str, ast.Call]] = []

    # 1. last_used.py whole -- Task 1 rewrote its virtualenv answer.
    tree = ast.parse((REPO / "src/veny/last_used.py").read_text())
    out += [("src/veny/last_used.py", c) for c in _calls_under(tree)]

    # 2. pipeline.py: feeling_lucky, blank_slate and run_script whole -- Task 4
    #    gave run_script its announce parameter and Task 3 made blank_slate
    #    read args.yes -- plus every run_script(...) call inside run() (all
    #    four call sites Task 4 touched: one here, three in run()) and the
    #    whole of run()'s middle branch: the elif Task 1 rewrote to read
    #    last_used.active_virtualenv_dir() instead of veny's own interpreter
    #    prefix. That elif's own orelse (the final "else:" venv-build branch)
    #    is NOT part of this rule -- Task 1 did not touch it, and its
    #    run_script call is already covered by the "every run_script(...)
    #    call inside run" half of this rule.
    tree = ast.parse((REPO / "src/veny/pipeline.py").read_text())
    defs = _defs(tree)
    for name in ("feeling_lucky", "blank_slate", "run_script"):
        out += [("src/veny/pipeline.py", c) for c in _calls_under(defs[name])]
    for call in _calls_under(defs["run"]):
        if _func_name(call) == "run_script":
            out += [("src/veny/pipeline.py", c) for c in _calls_under(call)]
    elif_node = next(
        node
        for node in ast.walk(defs["run"])
        if isinstance(node, ast.If)
        and "active_virtualenv_dir" in ast.unparse(node.test)
    )
    for node in [elif_node.test, *elif_node.body]:
        out += [("src/veny/pipeline.py", c) for c in _calls_under(node)]

    # 3. cache_search.py: the last-used pass inside find_match_dir_in_cache,
    #    down to the statement that spends it. Everything below that line is
    #    the --latest/--oldest/--smallest ranking, swept by phase 3d --
    #    docs/superpowers/plans/2026-08-18-verify-cache-search-last-used-wiring-index.md.
    #    (NOT phase 4a: 4a's index has no cache_search.py rows at all.)
    #    Unchanged from 4b's rule -- phase 4c did not touch this function
    #    above the cutoff, only the line numbers moved.
    tree = ast.parse((REPO / "src/veny/cache_search.py").read_text())
    search = _defs(tree)["find_match_dir_in_cache"]
    cutoff = max(
        stmt.end_lineno or stmt.lineno
        for stmt in search.body
        if isinstance(stmt, ast.If) and "try_last_used" in ast.unparse(stmt.test)
    )
    out += [
        ("src/veny/cache_search.py", c)
        for c in _calls_under(search)
        if c.lineno <= cutoff
    ]

    # 4. cli.py: the whole of main, plus _shell_status -- Task 2 added
    #    _shell_status and routed both of main's exit paths through it.
    tree = ast.parse((REPO / "src/veny/cli.py").read_text())
    defs = _defs(tree)
    for name in ("main", "_shell_status"):
        out += [("src/veny/cli.py", c) for c in _calls_under(defs[name])]

    seen: set[tuple[str, int, int]] = set()
    unique: list[tuple[str, ast.Call]] = []
    for fname, call in out:
        key = (fname, call.lineno, call.col_offset)
        if key in seen:
            continue
        seen.add(key)
        unique.append((fname, call))
    return unique


def collect() -> list[dict[str, Any]]:
    """Enumerate every argument at every call site in scope.

    Returns:
        One record per argument, with its source position and a substitute.
    """
    sites = []
    for fname, node in scoped_calls():
        name = _func_name(node)
        if name is None:
            continue
        entries = [(f"positional {i}", a) for i, a in enumerate(node.args)]
        entries += [(kw.arg, kw.value) for kw in node.keywords if kw.arg]
        for argname, valnode in entries:
            expr = ast.unparse(valnode)
            sites.append(
                {
                    "file": fname,
                    "call": name,
                    "line": valnode.lineno,
                    "col": valnode.col_offset,
                    "end_line": valnode.end_lineno,
                    "end_col": valnode.end_col_offset,
                    "arg": argname,
                    "expr": expr,
                    "sub": substitute_for(argname, expr),
                }
            )
    return sites


def apply(site: dict[str, Any], original: str) -> str | None:
    """Rewrite one argument's expression in the module source.

    Args:
        site: The record collect() produced.
        original: The unmutated module source.

    Returns:
        The mutated source, or None for a multi-line expression this cannot
        rewrite in place.

    Raises:
        RuntimeError: If the substitution reproduced the original text. Such
            a row would score as an OPEN HOLE with no signal in it at all --
            the suite passes because nothing changed. None of the rows
            measured here is a no-op; the guard is for the next retarget of
            the substitution table.
    """
    if site["line"] != site["end_line"]:
        return None
    lines = original.split("\n")
    line = lines[site["line"] - 1]
    lines[site["line"] - 1] = (
        line[: site["col"]] + site["sub"] + line[site["end_col"] :]
    )
    mutated = "\n".join(lines)
    # A substitution that reproduces the original text scores as an OPEN HOLE
    # with no signal in it at all -- the suite passes because nothing changed.
    # None of the rows measured here is a no-op; this guard is so the next
    # retarget of the substitution table finds out at once if one of its is.
    if mutated == original:
        raise RuntimeError(
            f"no-op substitution at {site['file']}:{site['line']} "
            f"{site['call']}({site['arg']}): {site['expr']} -> {site['sub']}"
        )
    return mutated


def main() -> None:
    """Measure every site and write the results to OUT/sweep4c.json."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Print the sites and stop.")
    options = parser.parse_args()
    sites = collect()
    if options.list:
        for site in sites:
            print(
                f"{site['file']}:{site['line']} {site['call']}"
                f"({site['arg']}) = {site['expr']}  ->  {site['sub']}"
            )
        print(len(sites), "arguments")
        return
    originals = {f: (REPO / f).read_text() for f in FILES}
    results = []
    for number, site in enumerate(sites, 1):
        if site["sub"] is None:
            site["verdict"] = "NO SUBSTITUTE"
            results.append(site)
            print(f"{number}/{len(sites)} NO SUBSTITUTE {site['call']}({site['arg']})")
            continue
        mutated = apply(site, originals[site["file"]])
        if mutated is None:
            site["verdict"] = "MULTILINE"
            results.append(site)
            print(f"{number}/{len(sites)} MULTILINE     {site['call']}({site['arg']})")
            continue
        target = REPO / site["file"]
        target.write_text(mutated)
        try:
            # A mutation that breaks import is not a kill: test_import_guard
            # re-imports veny in a subprocess and would report every NameError
            # as though the wiring had been caught. Check first.
            sanity = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.path.insert(0, 'src'); import veny.cli, "
                    "veny.pipeline, veny.state, veny.last_used, veny.cache_search",
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
                timeout=120,
                env=ENV,
            )
            if sanity.returncode != 0:
                site["verdict"] = "INVALID"
                site["killer"] = sanity.stderr.strip().split("\n")[-1][:140]
                results.append(site)
                print(
                    f"{number}/{len(sites)} INVALID       "
                    f"{site['call']}({site['arg']}) {site['killer']}",
                    flush=True,
                )
                continue
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-x",
                    "-q",
                    "--no-header",
                    "-p",
                    "no:cacheprovider",
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
                timeout=900,
                env=ENV,
            )
            if proc.returncode == 0:
                site["verdict"] = "OPEN HOLE"
                site["killer"] = ""
            else:
                killers = [
                    line.split(" ")[1]
                    for line in proc.stdout.split("\n")
                    if line.startswith("FAILED") and len(line.split(" ")) > 1
                ]
                if not killers:
                    site["verdict"] = "ERROR"
                    site["killer"] = proc.stdout.strip().split("\n")[-1][:120]
                else:
                    site["verdict"] = "KILLED"
                    site["killer"] = killers[0].replace("FAILED ", "")
        finally:
            target.write_text(originals[site["file"]])
        results.append(site)
        print(
            f"{number}/{len(sites)} {site['verdict']:13s} "
            f"{site['call']}({site['arg']}) {site.get('killer', '')}",
            flush=True,
        )
    (OUT / "sweep4c.json").write_text(json.dumps(results, indent=1))
    print("written", OUT / "sweep4c.json")


if __name__ == "__main__":
    main()
