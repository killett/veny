# Design: replace veny's shell alias with a packaged console-script entry point

**Status:** approved 2026-08-15
**Topic:** how `veny` gets onto the user's PATH

## Problem

veny installs itself by appending a line to a shell configuration file. Running
`veny.py --alias veny` calls `add_alias`, which detects the shell
(`ek.detect_shell`), finds the rc file (`ek.find_shell_rc_file`), builds a
shell-specific command string (`define_alias_command`, carrying four dialects:
bash/zsh, fish, csh and tcsh), checks for a pre-existing entry with a regex
(`alias_exists`), and appends it (`add_alias_to_rc_file`).

That mechanism has four defects, in increasing order of importance:

1. **It only works in interactive shells.** An alias is invisible to scripts,
   Makefiles, cron, `xargs`, and `subprocess`. `which veny` finds nothing.
2. **It costs four shell dialects plus rc-file discovery**, all of which must
   keep working forever, for a problem the operating system already solves with
   PATH.
3. **It mutates a file veny does not own**, with no supported uninstall or
   upgrade path beyond hand-editing.
4. **It cannot guarantee the interpreter it names is usable.** The alias bakes
   in `f"{options.python_command} {options.my_filepath}"`. Nothing checks that
   the interpreter satisfies `requires-python = ">=3.12,<3.14"` or that
   `emmykit>=0.4.0` is importable from it. Both are hard requirements of veny.

## Considered alternatives

### A. PATH symlink, as in `killett/utilities`' `clean-caches.sh`

`clean-caches.sh --install` symlinks itself into the best writable directory on
PATH, offering to fix PATH when the chosen directory is not on it. It is
strictly better than an rc-file alias: one mechanism instead of four dialects,
visible to every process, uninstalled with `rm`, and shell-specific only in the
optional PATH fix and the `rehash` hint.

It is the right answer *for `clean-caches.sh`*, which is one self-contained bash
file with no dependencies. It is not sufficient for veny, which is six Python
modules plus a pinned PyPI dependency plus a Python version floor. A symlink
delegates interpreter selection to the script's shebang, `#!/usr/bin/env
python3` — whatever `python3` resolves to first on the user's PATH. That
interpreter may be older than 3.12 and need not have emmykit installed. During
this investigation `python3` resolved to 3.13.14 in one shell and 3.11.2 in
another on the same machine; under a symlink that difference is a silent
failure at run time.

A symlink does survive a symlinked invocation correctly in one respect worth
recording: CPython resolves the symlink when computing `sys.path[0]`, so a
symlinked `veny.py` would still import its sibling modules from the real
directory. Verified experimentally. `__file__` and `sys.argv[0]`, however,
remain the *link* path.

### B. Packaged console-script entry point (chosen)

Declare a `[build-system]` and `[project.scripts] veny = "veny.cli:main"`, and
install with `uv tool install` (or `pipx`). The installer creates the launcher
on PATH, in a private virtual environment, with an interpreter that satisfies
`requires-python`, and installs `emmykit>=0.4.0,<1.0` alongside. This provides
everything the symlink provides and additionally resolves the dependency and
interpreter problems that the symlink cannot. `uv tool install --editable` keeps
the symlink's live-edit property for development from a clone.

veny is intended for PyPI, and `veny` is unclaimed there (`pypi.org` returned
404 for `/pypi/veny/json` on 2026-08-15). Publishing requires this packaging
work regardless, so doing it now avoids designing the install story twice.

A useful consequence: veny has two interpreters in play — the one running veny,
and `options.python_command`, the one it builds virtual environments for.
Packaging separates them by construction. veny's own interpreter becomes the
installer's concern; `python_command` stays purely about the user's script.

### C. Keep the alias

Rejected. Every defect above is inherent to the mechanism.

## Design

### Layout

```
src/veny/
    __init__.py      # __version__ literal; no imports
    __main__.py      # python -m veny -> cli.main()
    cli.py           # veny.py moved verbatim, minus the alias code
    alias_index.py
    pypi_client.py
    stdlib_index.py
    venv_cache.py
    json_types.py    # was veny_json_types.py
tests/               # stays at the repository root
```

The `src/` layout matches the global convention the repository has so far
departed from (recorded as a gotcha in `PROGRESS.md`). It also makes the modules'
one-way dependency discipline structural rather than conventional:
`alias_index` and `pypi_client` import nothing from `cli`; `json_types` imports
`alias_index` and `stdlib_index`, never `cli`.

`veny.py` moves whole, with `git mv`, and is not split. Splitting a 5,101-line
module is its own design with its own tests; mixing it into a layout change
would make the diff unreviewable. The `veny_` prefix drops from
`veny_json_types` because it existed only to disambiguate a top-level module
name.

### Packaging metadata

`pyproject.toml` gains:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
veny = "veny.cli:main"

[tool.hatch.version]
path = "src/veny/__init__.py"
```

and `[project]` gains `dynamic = ["version"]`, losing its static `version`.

This resolves an existing contradiction: `veny.py:43` declares
`__version__ = "0.2.2"` while `pyproject.toml` declares `version = "0.1.0"`.
Publishing today would ship a wheel labelled with a version that disagrees with
what `--version` prints and with what `venv_cache` records in every manifest's
`veny_version` field. After this change one literal, in `src/veny/__init__.py`,
is the single source: available with no `dist-info` when running from a clone,
and read by the build backend when building.

### Installation

Three paths, one mechanism.

1. **End users, once published:** `uv tool install veny` or `pipx install veny`.
   Not `pip install veny`: veny is an application, and a tool install gives it a
   private environment, so its emmykit pin cannot collide with whatever
   environment the user is standing in. The isolation is safe because veny
   probes `options.python_command` independently of the interpreter running it.
2. **Development machines, from a clone:** `uv tool install --editable <path>`.
   The launcher points into the working tree, so `git pull` takes effect with no
   reinstall, while uv still enforces the Python floor and installs emmykit.
   `uv tool upgrade veny` and `uv tool uninstall veny` replace hand-editing an rc
   file.
3. **Inside the repository:** unchanged in policy. `pixi.toml` already sets
   `[activation.env] PYTHONPATH = "src"` precisely so that `python -m <package>`
   works without an editable install, with a comment explaining that pulling uv
   and a build backend into the pixi environment is fragile. That decision
   stands; the `src/` move is what finally makes the setting meaningful. One new
   task is added:

   ```toml
   veny = "python -m veny"     # pixi run veny my_script.py
   ```

This design makes veny publishable; it does not publish it. Uploading stays a
separate decision.

### Changes inside `cli.py`

Beyond the move, six changes. Everything else is untouched.

1. **Import rewrites.** `import alias_index` becomes `from . import
   alias_index`, and likewise for `stdlib_index`, `venv_cache` and `json_types`.
   Inside `alias_index.py`, `from pypi_client import PyPIClient` becomes
   `from .pypi_client import PyPIClient`.
2. **The emmykit import guard stays at the top of `cli.py`**, before anything
   touches `ek`. The installer guarantees emmykit for installation paths 1 and 2,
   but not for `pixi run veny` or `python -m veny` from a clone.
3. **`__version__` moves to `src/veny/__init__.py`**, as described above.
4. **Self-identity becomes a constant.** `my_filepath = ek.ensure_path(sys.argv[0])`
   is deleted along with the alias code, `define_alias_command` having been its
   only reader. `my_name` becomes the literal `"veny"`. This is required, not
   cosmetic: `my_name` determines the state directory `~/veny`, the `.veny-*.out`
   and `.veny-*.err` prefixes, and the `.veny_custom_modules_*.pkl` names, and
   under `python -m veny` the argv-derived form would yield `"__main__"` and a
   state directory of `~/__main__`.
5. **`prog="veny"` is set explicitly on the `ArgumentParser`.** On Python 3.12
   and 3.13, argparse derives `prog` from `basename(sys.argv[0])`, so
   `python -m veny --help` would print `usage: __main__.py ...` and `--version`
   would print `__main__.py 0.2.2` through the `%(prog)s` template.
6. **`__main__.py` delegates to `cli.main()`, and exit-code propagation is
   fixed.** This section originally claimed exit codes needed no work, on the
   strength of the `sys.exit(result.returncode)` at `cli.py:266`. That line is
   inside the `--feeling-lucky` branch, whose own help text reads
   `NOT FINISHED!!!`. The three paths that actually run the user's script
   (`cli.py:385`, `392`, `423`) discard the return code, so `veny` exits 0 no
   matter how the wrapped script exits. Corrected 2026-08-15, after Task 4's
   smoke check caught it; the defect predates this work (`git show
   986bf40^:veny.py` has the same shape).

   That matters more under a console script than it did under an alias:
   `veny script.py && deploy` runs `deploy` after a failure, and CI reads every
   failure as a pass — scripts and cron being exactly the callers a PATH
   install reaches and an alias never did. So this design now also propagates
   the wrapped script's status: the three run paths capture their return code,
   `main()` exits with it after its normal cleanup, and `__main__.py` uses
   `sys.exit(main())`.

   Out of scope, recorded as an open question: what veny should exit with when
   *veny itself* cannot run the script — the "current virtual environment does
   not have all the required packages" path (`cli.py:396`) also exits 0 today.
   That is a question about veny's own status codes rather than about
   propagating the script's, and it is left for a follow-up.

### Deleted surface

From `cli.py`: `--alias`, `--manual`, `manual_instructions`,
`define_alias_command`, `alias_exists`, `add_alias_to_rc_file`, `add_alias`, and
the `options.alias` / `options.alias_command` handling in `main()`.

`shell`, `rc_file` and `additional_alias_files` are emmykit's `Options` fields,
populated by `ek.detect_shell` and `ek.find_shell_rc_file`. veny simply stops
calling them; nothing is removed from emmykit by this work. See "Cross-repo
follow-up" below.

### Existing installations

Users of the old mechanism have `alias veny="python3 ~/veny.py"` in an rc file,
and a shell alias takes precedence over PATH — so the alias would silently keep
running the old path after the console script is installed. This is handled by
documentation only: an "Upgrading from the alias install" section in `README.md`
giving the line to delete and the `hash -r` / `rehash` follow-up.

Detecting and removing it automatically was rejected: it would keep
`find_shell_rc_file`, `alias_exists` and the additional-alias-file logic alive,
which is precisely the code this design retires.

### Tests and tooling

**Test imports.** The five test files that do `import veny`
(`test_cache_search`, `test_manifest_writing`, `test_options_surface`,
`test_rename_venv`, `test_split_imports`) become `from veny import cli as veny`,
leaving their existing `veny.<name>` references intact. Two more files —
`test_import_guard` and `test_json_types` — carry `import veny` inside
subprocess source strings and need the same treatment there. Rewriting roughly 200 call sites during a move that must be
behaviour-preserving adds risk without adding coverage. Sibling imports become
`from veny import alias_index` and so on.
`tests/test_manifest_writing.py`'s version assertion imports the package itself.

**Configuration.** `[tool.pytest.ini_options] pythonpath` drops `"."`, which
existed only because the modules sat at the repository root.
`[tool.coverage.run] source = ["src"]` begins measuring something for the first
time. `mypy_path = "src"` is already correct. `.gitignore` gains `dist/`,
`build/` and `*.egg-info/`.

**The formatter trap becomes enforced.** `PROGRESS.md` records that a trial run
of pre-commit's `ruff-format` once rewrote roughly 2,000 lines of `veny.py`'s
hand-aligned formatting. After the move that warning names a path that no longer
exists. This design adds an explicit `exclude` for `src/veny/cli.py` to the
`ruff` and `ruff-format` hooks in `.pre-commit-config.yaml`, so the trap cannot
be stepped in rather than merely being written down. The move itself is `git mv`
plus hand-edited import lines, with no formatter in the path.

**Baselines.** The move is behaviour-preserving, so three numbers are recorded
before and compared after:

| Gate | Before | Expected after |
| --- | --- | --- |
| `pixi run test` | 252 passed | 252 passed, plus the new entry-point tests |
| `ruff check <cli> --statistics` | 299 findings | 299 or fewer |
| `mypy <cli> <json_types>` | 28 errors | 28 or fewer |

Deleting the alias code will likely reduce both counts slightly. A reduction is
expected; an increase means the move introduced something. Every finding's path
changes from `veny.py:NNN` to `src/veny/cli.py:NNN`, so `PROGRESS.md`'s
scoped-gate instructions are updated in the same commit — those instructions are
the only way to check anything in this repository, given that the whole-repo
`mypy .` pre-commit hook cannot pass while the existing debt exists.

### New tests

The 252 existing tests are the regression net for the move itself: they exercise
the same functions through a new import path. New tests cover only new surface.

In the pytest suite:

1. **`python -m veny --version` prints `veny <__version__>`**, asserted as an
   exact string from a subprocess. Fails if `__main__.py` is not wired to
   `cli.main`, if `prog="veny"` is dropped (the output becomes
   `__main__.py 0.2.2`), or if the `__init__.py` literal and what the CLI reports
   drift apart.
2. **The state directory is `~/veny` regardless of `argv[0]`.** Construct
   `Options` with `sys.argv` monkeypatched to `["/tmp/anything/__main__.py"]` and
   assert `options.my_dir == home / "veny"`. Restoring the argv-derived
   `my_name` would send the entire state directory to `~/__main__` under
   `python -m veny`, and no other test would notice: every other test constructs
   `Options` under pytest, where `argv[0]` is already arbitrary.
3. **`--alias` and `--manual` are rejected**, each raising `SystemExit(2)` from
   `parse_arguments`. Fails on a half-applied deletion that leaves the flags as
   dead argparse entries pointing at removed functions.
4. **`tests/test_import_guard.py` is updated** to subprocess `import veny.cli`,
   keeping its coverage of the missing-emmykit and too-old-emmykit exits.

Outside the suite, a `pixi run smoke` task, because nothing in-process can prove
that `[project.scripts]` resolves — that string is interpreted only by an
installer. It builds the wheel, creates a throwaway virtual environment,
installs the wheel into it, and then:

- runs `veny --version` and `veny --help` from that environment's `bin/`,
  proving the console script exists and imports, and that emmykit resolved from
  the pin rather than from the development environment;
- runs `veny fixture.py`, where the fixture is `import sys; sys.exit(7)`, and
  asserts an exit status of 7 — proving `SystemExit(result.returncode)` survives
  the console-script wrapper end to end.

It needs the network and builds a real virtual environment, so it stays out of
`pixi run test` and serves as an explicit verification step and a pre-publish
gate.

## Cross-repo follow-up

veny is emmykit's only known consumer, and this design removes veny's last use
of emmykit's shell/alias helpers. The implementation plan ends by producing a
prompt, in `docs/prompts/`, to be run in the emmykit repository. It asks for a
usage audit — not a deletion — of:

- `emmykit/python_env.py`: `detect_shell`, `find_shell_rc_file`,
  `find_additional_alias_files`, all three exported in `__init__.py`'s `__all__`
- `emmykit/options.py`: the `Options` fields `shell`, `rc_file`, `alias`,
  `alias_command`, `additional_alias_files`

Removing any of them is a breaking change to a published 0.4.0, so the prompt
asks whether each is used elsewhere inside emmykit and what the recommended
disposition is, leaving the decision to a follow-up.

The prompt must also carry a ready-to-paste `fd` command that counts
occurrences of those names under an arbitrary directory. The audit the prompt
requests covers the emmykit repository only; the command covers everywhere
else, so that a call site in some other project is not missed before anything
is removed. It uses `fd` to select the files and `rg` to count within them,
excludes vendored copies (`.pixi`, `site-packages`, `.git`), and is written as
several short lines rather than one long one, per the shell-command convention
in the global `CLAUDE.md`.

## Out of scope

- Publishing to PyPI (this design makes it possible; the upload is a separate
  decision).
- Splitting `cli.py` into smaller modules.
- The pre-existing ruff and mypy debt, which is carried across the move
  unchanged.
- Any change to how veny resolves `options.python_command` or builds virtual
  environments.
