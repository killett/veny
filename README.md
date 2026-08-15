# veny

veny runs a Python script without asking you to manage its environment by
hand. It analyzes the script's imports, resolves each one to the pip package
that actually provides it, and builds (or reuses a cached) virtual
environment holding exactly those packages before running the script inside
it.

## Installation

```
pixi install
```

This installs veny's own development dependencies (ruff, mypy, pytest,
pre-commit). veny itself has no third-party dependencies — it must run on a
bare interpreter, since its job is to bootstrap environments for other
scripts.

## Quick usage

```
pixi run python veny.py my_script.py [script args...]
```

veny inspects `my_script.py`'s imports, finds or builds a virtual
environment with the packages it needs, and runs the script in it. Pass
`--justprint` to see the resolved package list without running anything, or
`--help` for the full flag set (`--full`, `--no-cache`, `--latest`,
`--reqs`, and others).

## Virtual environment cache

Each cached virtual environment carries a `veny_manifest.json` recording the
interpreter it was built for and, per package, the import name, the pip name,
the installed version, and any `--reqs` pin. veny matches a cached environment
against that file; the folder name
(`<venv_name>-py<major.minor>-<YYYYMMDD>-<HHMMSS>-<packages>`) is only a quick
filter. Environments built by earlier versions of veny have no manifest and are
rebuilt once.

## Project structure

```
veny.py           # Entry point: argument parsing, import analysis driving,
                   # venv build/run orchestration.
univ_defs.py       # Shared utilities and the base Options class.
alias_index.py     # Import-name -> pip-name resolution (overrides, cache,
                   # target-interpreter probe, PyPI confirmation chain).
stdlib_index.py    # Standard-library membership for the target interpreter.
pypi_client.py     # Confirms a project provides an import name by reading a
                   # wheel's central directory over an HTTP range request.
venv_cache.py      # Folder naming, manifests, and matching for cached
                   # virtual environments.
tests/             # pytest test suite.
docs/              # Design docs and implementation plans.
```
