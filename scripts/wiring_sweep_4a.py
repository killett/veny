"""Run phase 4a's STANDING CHECK: substitute each argument, see what goes red.

For every argument at every call site phase 4a wired, replace the expression
with a type-correct but wrong value, import-check the module, run the suite,
and record the first test that fails. An argument nothing catches is an OPEN
HOLE; an argument the callee never reads is DEAD.

Results land in the scratch directory as sweep.json; the reviewed version is
docs/superpowers/plans/2026-08-21-state-model-values-wiring-index.md.

TRAP, recorded because it cost a full run: `pixi run` sets PYTHONPATH=src, and
tests/test_import_guard.py spawns its own subprocess that needs it. Without it
that one test fails under EVERY mutation and reports a spurious kill for each,
hiding every real hole behind it. ENV below is what stops that.

Usage:
    pixi run python scripts/wiring_sweep_4a.py
"""

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

# The call names this phase wired. Same list the enumeration used.
OWN = {
    "find_imports_in_script",
    "split_imports",
    "list_packages",
    "report",
    "warn_about_system_packages",
    "setup_virtualenv",
    "blank_slate",
    "build_alias_index",
    "run_script",
    "resolve_target",
    "feeling_lucky",
    "_load_last_used",
    "_probe_venv",
    "run",
}
PREFIXES = {
    "state",
    "settings",
    "classify",
    "verify",
    "environment",
    "cache_search",
    "venv_cache",
    "analysis_scan",
    "custom_modules",
    "last_used",
    "stdlib_index",
    "alias_index",
    "dataclasses",
}

# Substitutions by the shape of the expression, keyed on a suffix match.
BY_NAME = {
    "rawlog": "True",
    "announce": "True",
    "use_reqs": "True",
    "offline": "True",
    "use_cache": "True",
    "search_above_this_dir": "False",
    "my_name": '"wiring-probe"',
    "venv_name": '"wiringprobe"',
    "timestamp": '"20000101-000000"',
    "python_command": '"wiring-probe-python"',
    "run_tag": '"0.0"',
    "tag": '"0.0"',
    "interpreter_tag": '"0.0"',
    "extra_requirements_file": '"wiring_probe.txt"',
    "pathlibcutoff": '"00000000-000000"',
    "my_dir": '__import__("pathlib").Path("/tmp/veny-wiring-probe")',
    "cwd": '__import__("pathlib").Path("/tmp/veny-wiring-probe")',
    "script_dir": '__import__("pathlib").Path("/tmp/veny-wiring-probe")',
    "venv_dir": '__import__("pathlib").Path("/tmp/veny-wiring-probe")',
    "venv_python": '__import__("pathlib").Path("/tmp/veny-wiring-probe/bin/python")',
    "requirements_file": '__import__("pathlib").Path("/tmp/veny-wiring-probe/requirements.txt")',
    "python_script": '__import__("pathlib").Path("/tmp/veny-wiring-probe/script.py")',
    "script_args": "[]",
    "stay_out_list": "()",
    "known_bad_imports": "frozenset()",
    "also_needs": "{}",
    "extra_requirements": "{}",
    "uninstalled": "set()",
    "source_names": "frozenset()",
    "wanted": "[]",
    "pip_names": "[]",
    "all_imports": "frozenset()",
    "seen_stdlib_imports": "set()",
    "custom_modules": "{}",
    "new_name": '"wiring-probe-name"',
    "index": "alias_index.empty(__import__('pathlib').Path('/tmp/veny-wiring-probe'))",
    "aliases": "alias_index.empty(__import__('pathlib').Path('/tmp/veny-wiring-probe'))",
}


# A different object of the same type -- 3e's "fresh Options" substitution,
# generalised to every value phase 4a introduced.
BY_EXPR = {
    "settings": "_WIRING_SETTINGS",
    "scan": "ImportScan()",
    "target": "_WIRING_TARGET",
    "requirements": "_WIRING_REQUIREMENTS",
    "args": "argparse.Namespace()",
    "options": "run_options.Options()",
    "handle": "state.VenvHandle.for_dir('/tmp/veny-wiring-probe')",
    "stdlib": "stdlib_index.for_running_interpreter()",
    "is_stdlib": "(lambda name: True)",
    "first_path": '__import__("pathlib").Path("/tmp/veny-wiring-probe/script.py")',
    "python_file": '__import__("pathlib").Path("/tmp/veny-wiring-probe/script.py")',
    "match_dir": '__import__("pathlib").Path("/tmp/veny-wiring-probe")',
    "active_venv": '__import__("pathlib").Path("/tmp/veny-wiring-probe")',
    "venv_dir": '__import__("pathlib").Path("/tmp/veny-wiring-probe")',
    "last_used_venv_python": '__import__("pathlib").Path("/tmp/veny-wiring-probe/bin/python")',
    "sys.executable": '"/tmp/veny-wiring-probe/bin/python"',
    "import_name": '"wiringprobe"',
    "folder_name": '"wiring-probe-folder"',
    "python_command": '"wiring-probe-python"',
    "list(target.script_args)": "[]",
    "set(requirements.all_imports)": "frozenset()",
    "python_command or ''": '"wiring-probe-python"',
    "os.fspath(handle.requirements_file)": '"/tmp/veny-wiring-probe/requirements.txt"',
    "environment.venv_python_for(handle.venv_dir)": '__import__("pathlib").Path("/tmp/veny-wiring-probe/bin/python")',
    "environment.venv_python_for(venv_dir)": '__import__("pathlib").Path("/tmp/veny-wiring-probe/bin/python")',
    "environment.venv_python_for(active_venv)": '__import__("pathlib").Path("/tmp/veny-wiring-probe/bin/python")',
    "environment.venv_build_interpreter(target.python_command)": '"/tmp/veny-wiring-probe/bin/python"',
    "(record.pip_name for record in requirements.uninstalled)": "iter(())",
    "stdlib.__contains__": "(lambda name: True)",
    "_probe_venv(target)": "contextlib.nullcontext(lambda name: True)",
    "handle.venv_dir.name.removeprefix('failed-')": '"wiring-probe-name"',
    "cache_search.rename_venv(handle.venv_dir, handle.venv_dir.name.removeprefix('failed-'))": '"/tmp/veny-wiring-probe"',
    "settings.my_dir / f'failed-{folder_name}'": '"/tmp/veny-wiring-probe"',
    "alias_index.ResolvedImport(import_name=import_name, pip_name=import_name)": 'alias_index.ResolvedImport(import_name="wiringprobe", pip_name="wiringprobe")',
    "lambda: _load_last_used(options, target, pathlibcutoff=options.pathlibcutoff, rawlog=settings.rawlog)": "(lambda: None)",
    "'install'": '"uninstall"',
    "'-r'": '"-e"',
    "getattr(args, 'reqs', False)": "True",
}


def substitute_for(argname: str, expr: str) -> str | None:
    """Pick a type-correct but wrong replacement for one argument."""
    if expr in BY_EXPR:
        return BY_EXPR[expr]
    key = argname if not argname.startswith("positional") else ""
    if key and key in BY_NAME:
        return BY_NAME[key]
    for name, sub in BY_NAME.items():
        if expr.endswith("." + name) or expr == name:
            return sub
    if expr in {"True", "False"}:
        return "False" if expr == "True" else "True"
    if expr.startswith('"') or expr.startswith('f"'):
        return '"wiring-probe"'
    return None


def collect() -> list[dict[str, Any]]:
    """Enumerate every argument at every call site this phase wired.

    Returns:
        One record per argument, with its source position and a substitute.
    """
    sites = []
    for fname in ("src/veny/cli.py", "src/veny/pipeline.py", "src/veny/state.py"):
        src = (REPO / fname).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute):
                name = f"{ast.unparse(f.value)}.{f.attr}"
            elif isinstance(f, ast.Name):
                name = f.id
            else:
                continue
            if not (name in OWN or name.split(".")[0] in PREFIXES):
                continue
            entries = [(f"positional {i}", a) for i, a in enumerate(node.args)]
            entries += [(kw.arg, kw.value) for kw in node.keywords if kw.arg]
            for argname, valnode in entries:
                expr = ast.unparse(valnode)
                sub = substitute_for(argname, expr)
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
                        "sub": sub,
                    }
                )
    return sites


PROBES = """
from pathlib import Path as _WiringPath  # noqa: E402

_WIRING_SETTINGS = __import__("veny.settings", fromlist=["Settings"]).Settings(
    my_name="wiring-probe", my_dir=_WiringPath("/tmp/veny-wiring-probe"),
    cwd=_WiringPath("/tmp/veny-wiring-probe"), venv_name="wiringprobe",
    stay_out_list=(), search_above_this_dir=False, rawlog=True,
    known_bad_imports=frozenset(), also_needs={}, extra_requirements_file="wiring_probe.txt",
)
_WIRING_TARGET = state.Target(
    python_script=_WiringPath("/tmp/veny-wiring-probe/script.py"),
    script_dir=_WiringPath("/tmp/veny-wiring-probe"), script_args=(),
    python_command="wiring-probe-python", timestamp="20000101-000000",
)
_WIRING_REQUIREMENTS = state.Requirements(
    all_imports=frozenset(), bad=frozenset(), installed=frozenset(),
    uninstalled=frozenset(), seen_stdlib=frozenset(), extra_requirements={},
)
"""


def apply(site: dict[str, Any], original: str) -> str | None:
    """Rewrite one argument's expression in the module source.

    Args:
        site: The record collect() produced.
        original: The unmutated module source.

    Returns:
        The mutated source, or None for a multi-line expression this cannot
        rewrite in place.
    """
    lines = original.split("\n")
    if site["line"] != site["end_line"]:
        return None  # multi-line expression: skip, handled by hand
    line = lines[site["line"] - 1]
    lines[site["line"] - 1] = (
        line[: site["col"]] + site["sub"] + line[site["end_col"] :]
    )
    out = "\n".join(lines)
    if "_WIRING_" in site["sub"]:
        marker = "class UsageError(Exception):"
        if marker in out:
            out = out.replace(marker, PROBES + "\n\n" + marker, 1)
    return out


def main() -> None:
    """Measure every site and write the results to OUT/sweep.json."""
    sites = collect()
    results = []
    originals = {
        f: (REPO / f).read_text()
        for f in ("src/veny/cli.py", "src/veny/pipeline.py", "src/veny/state.py")
    }
    for n, site in enumerate(sites, 1):
        if site["sub"] is None:
            site["verdict"] = "NO SUBSTITUTE"
            results.append(site)
            continue
        mutated = apply(site, originals[site["file"]])
        if mutated is None:
            site["verdict"] = "MULTILINE"
            results.append(site)
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
                    "import sys; sys.path.insert(0, 'src'); "
                    "import veny.cli, veny.pipeline, veny.state",
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
                    f"{n}/{len(sites)} INVALID      {site['call']}({site['arg']}) "
                    f"{site['killer']}",
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
                timeout=600,
                env=ENV,
            )
            if proc.returncode == 0:
                site["verdict"] = "OPEN HOLE"
                site["killer"] = ""
            else:
                killers = [
                    ln.split(" ")[1]
                    for ln in proc.stdout.split("\n")
                    if ln.startswith("FAILED") and len(ln.split(" ")) > 1
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
            f"{n}/{len(sites)} {site['verdict']:12s} "
            f"{site['call']}({site['arg']}) {site['killer'] if 'killer' in site else ''}",
            flush=True,
        )
    (OUT / "sweep.json").write_text(json.dumps(results, indent=1))
    print("written", OUT / "sweep.json")


if __name__ == "__main__":
    main()
