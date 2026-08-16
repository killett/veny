# veny

veny runs a Python script without asking you to manage its environment by
hand. It analyzes the script's imports, resolves each one to the pip package
that actually provides it, and builds (or reuses a cached) virtual
environment holding exactly those packages before running the script inside
it.

## Installation

veny is an application, so install it as a tool rather than into a project
environment — that gives it a private virtual environment with a satisfying
interpreter and its `emmykit` and `uv` dependencies resolved for it:

```
uv tool install veny
```

`pipx install veny` works the same way. To install from a clone instead, so
that `git pull` takes effect with no reinstall:

```
uv tool install --editable ~/path/to/veny
```

Either way the `veny` command lands on your PATH — visible to scripts, cron and
`subprocess`, not just to interactive shells. `uv tool upgrade veny` and
`uv tool uninstall veny` manage it from there.

### Upgrading from the alias install

Earlier versions of veny installed themselves by appending a line to a shell
configuration file. A shell alias takes precedence over PATH, so that line will
keep running the old copy after you install the command. Delete it from your
`~/.bashrc`, `~/.zshrc` or equivalent:

```
alias veny="python3 ~/veny.py"
```

then refresh the current shell's command lookup with `hash -r` (bash) or
`rehash` (zsh), or just open a new terminal.

### Working on veny itself

```
pixi install
pixi run veny my_script.py
```

This installs the development tools (ruff, mypy, pytest, pre-commit) plus the
scaffold baseline — none of it is a runtime dependency of veny. `pixi run veny`
runs the working tree directly through `python -m veny`; no editable install is
involved. veny's runtime dependencies are
[emmykit](https://pypi.org/project/emmykit/) (`pip install 'emmykit>=0.4.0'`),
which provides its utility layer and the base `Options` class, and
[uv](https://pypi.org/project/uv/), installed alongside it as a PyPI
dependency and located through `uv.find_uv_bin()`; beyond that it must run on
a bare interpreter, since its job is to bootstrap environments for other
scripts.

## Quick usage

```
veny my_script.py [script args...]
```

or, inside a clone of this repo without installing:

```
pixi run veny my_script.py [script args...]
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
(`<venv_name>-py<major.minor>-<YYYYMMDD>-<HHMMSS>-<packages>`, packages
normalized and joined with `_`, truncated to the first 5 with an
`_and_N_more` tail beyond that) is only a quick filter. Environments built by
earlier versions of veny have no manifest, so they are never matched again —
but they are also never deleted, so they accumulate in the cache directory
until removed by hand.

### Cached environments have no pip

veny builds its environments with `uv venv`, which does not install `pip` into
them. A script that shells out to `pip` from inside its veny-built environment
will not find one. This is deliberate: veny manages the environment's packages,
and a script installing into it is working against that.

## Project structure

```
src/veny/
    __init__.py    # Version literal.
    __main__.py    # python -m veny.
    cli.py         # Argument parsing, import analysis driving, venv
                   # build/run orchestration.
    alias_index.py # Import-name -> pip-name resolution (overrides, cache,
                   # target-interpreter probe, PyPI confirmation chain).
    json_types.py  # Registers veny's own types with emmykit's JSON registry.
    pypi_client.py # Confirms a project provides an import name by reading a
                   # wheel's central directory over an HTTP range request.
    stdlib_index.py # Standard-library membership for the target interpreter.
    venv_cache.py  # Folder naming, manifests, and matching for cached
                   # virtual environments.
scripts/           # smoke-install.sh: wheel + console-script verification.
tests/             # pytest test suite.
docs/              # Design docs and implementation plans.
```

Note that `alias_index.py` is about *import-name aliases* — it is unrelated to
the shell alias this work removed, and it stays.
