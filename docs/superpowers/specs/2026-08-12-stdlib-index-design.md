# Design: replace the hardcoded standard-library list with a StdlibIndex resolver

Date: 2026-08-12
Status: approved, not yet implemented

## Problem

`veny.py` line 130 defines `Options.standard_modules` as a literal
`frozenset` of 1,785 standard-library module names, spanning lines 130–1064.
That is 935 lines, about 15% of a 6,320-line file. The list was copied from
the `pipreqs` repository's `stdlib` file on 2024-08-15 and has not been
updated since.

The list is used at three call sites (`veny.py:4323`, `5047`, `5181`), always
in the same form — `if import_name in options.standard_modules` — to decide
that an import needs no `pip install`.

Four problems:

1. **It is stale.** It still lists modules removed in Python 3.12
   (`asynchat`, `asyncore`, `binhex`, `imp`, `distutils`, `smtpd`) and 3.13
   (`lib2to3`, `telnetlib`, `cgi`, `cgitb`, `nntplib`, `pipes`, `crypt`,
   `aifc`, `audioop`, `chunk`, `imghdr`, `mailcap`, `msilib`, `nis`,
   `ossaudiodev`, `sndhdr`, `spwd`, `sunau`, `uu`, `xdrlib`). It is missing
   modules added since, including `tomllib`, `_pyrepl`, `_interpreters`, and
   `_zoneinfo`.
2. **It is contaminated.** It contains build-environment artifacts that are
   not standard library at all: `_sysconfigdata_x86_64_conda_linux_gnu`,
   `_sysconfigdata_x86_64_conda_cos6_linux_gnu`, and `lib`.
3. **It is redundant.** 1,785 entries collapse to 319 distinct top-level
   names. The other ~1,466 are submodules (`asyncio.base_events`,
   `lib2to3.tests.data.fixers.myfixes.fix_parrot`) that a first-component
   lookup handles for free.
4. **It is unmaintainable by construction.** Every future Python release
   invalidates it, and nothing in the codebase signals when that happens.

## Decision

Replace the literal with a small resolver module that derives the answer from
an actual interpreter. Since `pyproject.toml` sets
`requires-python = ">=3.12,<3.14"`, `sys.stdlib_module_names` (added in 3.10)
is unconditionally available — no version guard, no fallback list, no
third-party dependency.

### Truth source: the target interpreter, with the runner as the fast path

The question veny actually asks is not "is this name in the standard
library?" but "will pip need to install this for the interpreter that will
run the user's script?" That is a property of the **target** interpreter, not
of the interpreter running veny. A design that hardcodes runner semantics
bakes in a latent wrong assumption that stays invisible until the two
versions diverge.

`options.python_command` is resolved at `veny.py:2410`, well before any import
analysis, so the target is known early and no virtual environment is needed to
probe it.

Policy:

- If the target resolves (via `os.path.realpath`) to the same interpreter file
  as `sys.executable`, use the running interpreter's names directly. No
  subprocess.
- Otherwise probe the target once with a subprocess.
- If the probe fails for any reason, log a warning and degrade to the running
  interpreter's names, tagged as degraded. veny keeps working; the worst case
  is a handful of names misclassified across a minor-version gap.

Note that "compare versions first, probe only on mismatch" was considered and
rejected: learning the target's version requires a subprocess anyway, and the
probe already returns the version. The realpath check achieves the same
saving with one subprocess instead of two and no dead branch.

### Rejected alternatives

**`stdlib_list` package, or any union-across-versions approach.** Rejected on
two independent grounds. First, it is wrong in a direction that cannot be
detected at runtime: a name removed from the standard library but available on
PyPI as a backport (`legacy-cgi`, `standard-telnetlib`, `setuptools` for
`distutils`) would be silently skipped, and the user's script would fail with
`ImportError` *after* veny reported success. Being wrong toward "skip" is
strictly worse than being wrong toward "install", because a bogus install
fails loudly at install time. Second, it puts a third-party dependency inside
a bootstrapping tool whose entire purpose is to install third-party
dependencies — veny must run on a bare interpreter, and vendoring the package
back into the repository would reintroduce exactly the hardcoded blob being
removed.

**A generated per-version data file.** Same regeneration burden as the current
list, just relocated. `sys.stdlib_module_names` is correct on the first day of
every new Python release; a data file is not.

**Dynamic `importlib.util.find_spec` plus a `sysconfig` stdlib-path check.**
Answers only for modules present in the *current* environment, requires
distinguishing stdlib paths from site-packages paths across platforms and
virtual environments, and is far more machinery than a frozenset lookup for no
gain.

## Component: `stdlib_index.py`

A new module at the repository root, alongside `veny.py` and `univ_defs.py`.
It imports neither of them, so it stays independently testable and the
dependency direction does not invert (`univ_defs.py` is itself 9,711 lines and
overdue for splitting).

```python
@dataclass(frozen=True)
class StdlibIndex:
    names:          frozenset[str]        # top-level names only
    python_version: tuple[int, int]       # version the names came from
    source:         str                   # "running" | "probe" | "degraded"

    def __contains__(self, import_name: str) -> bool:
        """True if import_name resolves to the standard library."""
        return import_name.partition(".")[0] in self.names

def for_running_interpreter() -> StdlibIndex: ...
def for_interpreter(python: str | Path, *, timeout: float = 10.0) -> StdlibIndex: ...
def resolve(python: str | Path | None) -> StdlibIndex: ...
```

`resolve()` holds the policy described above and is the only function
`veny.py` calls. `for_interpreter` is wrapped in `functools.lru_cache`, keyed
by the resolved interpreter path. The cache is in-memory only: veny is a
short-lived process, and an on-disk cache would require invalidation on
interpreter upgrade to save a single ~50 ms subprocess.

Dotted-name normalization lives in `__contains__`, so call sites do not change
shape and cannot forget it.

### Probe payload

```python
_PROBE = (
    "import sys, json; "
    "print(json.dumps({'version': list(sys.version_info[:2]), "
    "'names': sorted(sys.stdlib_module_names)}))"
)
```

Run with `check=False`, `capture_output=True`, `text=True`, `timeout=10`. Any
of: non-zero exit, `TimeoutExpired`, `FileNotFoundError`, `JSONDecodeError`,
or a missing key triggers the degraded path. That also covers a target older
than 3.10, where `sys.stdlib_module_names` does not exist and the probe simply
fails — so no version guard is needed in our own code.

The resolver is pure with respect to individual imports: it classifies, and it
never logs about a specific import name. All user-facing reporting stays in
`veny.py`. This is what keeps the module testable without capturing logs.

## Classification and the `known_bad_imports` migration

`Options.known_bad_imports` (`veny.py:2287`) currently holds 29 names that are
three unrelated concerns in one set. It is split by owner.

**Moves into `stdlib_index.PYTHON2_ONLY`** — 20 names that are facts about
Python, not about this user, and are not installable under any Python 3:
`__builtin__`, `BaseHTTPServer`, `urlparse`, `tkFileDialog`, `tkMessageBox`,
`tkFont`, `ConfigParser`, `Cookie`, `HTMLParser`, `Queue`, `SocketServer`,
`StringIO`, `cStringIO`, `cPickle`, `Tkinter`, `UserDict`, `cookielib`,
`htmlentitydefs`, `httplib`, `urllib2`.

**Drops out entirely** — `msvcrt`. It appears in `sys.stdlib_module_names` on
every platform, so the resolver classifies it as standard library and skips
it. That is the correct outcome: a script importing `msvcrt` guards it behind
a platform check.

**Becomes a hint rather than a block** — `tkinter`. Also standard library per
the resolver, so it stops being `pip install` bait, but on Linux it fails at
runtime without the `python3-tk` system package. The resolver therefore
carries `NEEDS_SYSTEM_PACKAGE: dict[str, str] = {"tkinter": "python3-tk"}` —
standard library, skip the install, but log an actionable warning. One entry,
extensible, no speculation.

**Removed as stale** — `seaborn`. It is a normal, installable PyPI package;
the entry was a debugging leftover.

**Stays in `known_bad_imports`** — six project-specific local names that are
correctly hand-maintained and, at last, mean one single thing: `snakeClass`,
`GPUampcor`, `pathfinding_salvo_rework`, `DQN`, `bayesOpt`,
`non_existent_module`. They stay hardcoded; a config file or CLI flag would be
machinery for a six-item list. Revisit if it grows.

**Deliberately not added: a "removed from stdlib" category.** Because truth
comes from the target interpreter, `asynchat` under 3.12 or `telnetlib` under
3.13 simply is not standard library, flows to pip, and pip finds the backport
if one exists. A hardcoded removals list would break that.

## Changes in `veny.py`

1. Delete lines 125–1064 (the comment block and the frozenset), about 940
   lines.
2. `Options.__init__` gains
   `self.stdlib: StdlibIndex = stdlib_index.for_running_interpreter()`. This
   is cheap — a frozenset read from `sys`, no subprocess — and means the
   attribute is never `None`, so no `Optional` handling leaks into call sites.
3. `main()`, immediately after `options.python_command` is set at line 2410,
   overwrites it with `stdlib_index.resolve(options.python_command)`.
   `resolve` accepts `str | Path | None` because `python_command` is a command
   name such as `python3.12`, not a path. The early last-used-venv fast path
   returns before line 2410 and performs no import analysis, so it needs
   nothing.
4. The three call sites (4323, 5047, 5181) change `options.standard_modules`
   to `options.stdlib`. Two docstrings (4985, 5418) are updated to match.
5. `split_imports` (5357) gains a pure extracted helper
   `_compute_bad_imports(all_imports, known_bad, py2_only) -> set[str]`, which
   unions `known_bad_imports` with `stdlib_index.PYTHON2_ONLY` before
   intersecting with `all_imports`. The leading-underscore rule on line 5358
   moves into the helper unchanged.
6. `NEEDS_SYSTEM_PACKAGE` hits are collected into
   `options.system_package_hints` during analysis and warned about **once**,
   next to the existing bad-imports warning at line 2506 — not at the skip
   site, which runs per import and would spam the log.

## Behavior differences, measured

Diffing the deleted list (reduced to its 319 top-level names) against
`sys.stdlib_module_names` on Python 3.13 gives 53 names present in the old
list but not in the new, and 23 names present in the new but not in the old.

Every one of the 53 falls into an expected bucket: modules genuinely removed
from the standard library in 3.12/3.13; CPython private test and build
artifacts (`_testcapi`, `_testbuffer`, `_xxtestfuzz`, `xxsubtype`,
`__phello__`); or conda build contamination (`_sysconfigdata_*`, `lib`).
The 23 additions are modules added since 2024, including `tomllib`,
`_pyrepl`, `_interpreters`, `_zoneinfo`, `_colorize`, and the Android/iOS
support modules.

Two of the 53 deserve explicit notice:

- `__main__` is no longer classified as standard library. It is still caught,
  because the existing leading-underscore rule routes it to `bad_imports`.
- `test` is no longer classified as standard library. CPython deliberately
  excludes `Lib/test` from `sys.stdlib_module_names`, so a script containing
  `import test` would now be handed to pip, and a package named `test` does
  exist on PyPI. This is accepted: `import test` in user code is vanishingly
  rare and is arguably a bug in that script. If it ever bites, the fix is one
  entry in `known_bad_imports`, not a new mechanism.

The equivalence check is a one-off performed during implementation, with its
output recorded in the commit message. It is deliberately **not** kept as a
test — pinning behavior to a stale 2024 list is the debt being removed.

## Test plan

`tests/test_stdlib_index.py`, pytest. The happy path uses a real subprocess
against `sys.executable`: it is fast, hermetic, and mocking it would reduce
the test to asserting call arguments. `subprocess.run` is monkeypatched only
for failure modes that cannot be produced honestly.

Each test is listed with the concrete bug it would catch.

**Lookup semantics** (expected values from domain knowledge, not from the
implementation):

1. `"xml.etree.ElementTree"` against `frozenset({"xml"})` is `True` —
   catches forgetting to split on `.`, which would send every dotted standard
   library import to `pip install xml.etree.ElementTree`.
2. `"osquery"` against `frozenset({"os"})` is `False` — catches using
   `startswith` instead of an exact first-component match, which would
   silently refuse to install the real PyPI package `osquery`.
3. `"mypackage.os"` against `frozenset({"os"})` is `False` — catches
   splitting but taking `[-1]` instead of `[0]`.
4. `""` is `False` — catches an empty import name partitioning to `""` and
   matching an empty entry.

**Source construction:**

5. `for_running_interpreter()` contains `os`, `sys`, `asyncio`; does not
   contain `numpy`; `python_version == sys.version_info[:2]`;
   `source == "running"` — catches using `sys.builtin_module_names` (about 30
   names, no `os`) instead of `sys.stdlib_module_names`, which would quietly
   send half the standard library to pip.
6. `for_interpreter(sys.executable)` returns names equal to
   `for_running_interpreter()` with `source == "probe"` — catches a malformed
   probe payload, reading the wrong JSON key, or returning a `list` where a
   `frozenset` is typed.

**Degradation** (each asserts `source == "degraded"`, that names still contain
`os`, and that no exception escapes):

7. `resolve(Path("/nonexistent/python"))` — catches `FileNotFoundError`
   propagating and killing veny over a stale `which` result.
8. `subprocess.run` raises `TimeoutExpired` — catches an unbounded or
   uncaught-timeout probe hanging veny on a wedged interpreter.
9. Probe exits 0 with stdout `"not json"` — catches an uncaught
   `JSONDecodeError`, the realistic case of an interpreter printing a banner
   or warning before the payload.
10. Probe exits non-zero, simulating a target older than 3.10 — catches
    trusting the exit code and parsing empty stdout into an empty index, which
    would make every import look installable.

**Short circuit:**

11. `resolve(sys.executable)` returns `source == "running"` with
    `subprocess.run` monkeypatched to fail the test if called — catches
    comparing raw strings so a symlinked path misses and spawns a needless
    subprocess on every run, and equally catches a short circuit so eager that
    it never probes a genuinely different interpreter.

**Hand-maintained set invariants** (these guard the two lists that stay
manual):

12. `PYTHON2_ONLY` is disjoint from `for_running_interpreter().names` —
    catches adding `queue` instead of `Queue`, which would make veny report a
    valid Python 3 standard library import as a Python 2 module.
13. Every key of `NEEDS_SYSTEM_PACKAGE` is in
    `for_running_interpreter().names` — catches a typo such as `tkiner`, where
    the hint silently never fires and the user gets an unexplained runtime
    `ImportError`.

**`veny.py` side.** `split_imports` builds a real temporary virtual
environment, so it cannot be unit tested as-is; that is why the classification
line is extracted into `_compute_bad_imports`. Tests, in
`tests/test_split_imports.py`:

14. `httplib` in the input lands in the result — catches forgetting to union
    `PYTHON2_ONLY` after the migration, so `pip install httplib` is attempted.
15. `_private_thing` lands in the result — catches dropping the existing
    leading-underscore rule during the refactor.
16. `numpy` does not land in the result — catches an over-broad filter that
    strips every import and installs nothing.

## Success criteria

- `veny.py` shrinks by roughly 940 lines and contains no literal list of
  standard library module names.
- The three call sites read `options.stdlib` and behave identically for every
  name that is standard library in both the old list and the target
  interpreter.
- `pixi run test`, `pixi run lint`, and `pixi run typecheck` pass.
- Running veny on a script that imports `os`, `xml.etree.ElementTree`,
  `numpy`, and `httplib` skips the first two, installs `numpy`, and reports
  `httplib` as a Python 2 module without attempting to install it.
