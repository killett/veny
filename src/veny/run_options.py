"""What is left of the per-run state object, and why each field survived.

Phase 4a drained every field the pipeline read or wrote into the frozen
`Settings`, `Target`, `Requirements` and `VenvHandle` values, and into the
mutable `ImportScan` the analysis layer accumulates. Fifteen fields remain,
in four groups:

- **Persistence.** `python_script`, `script_dir`, `timestamp` and `my_name`
  are what `ek.save_options_to_json` builds its filename from;
  `venv_dir` and `venv_python` are the payload the *reader* recovers;
  `options_json_filepath` is where the writer records the result, and
  `pathlibcutoff` is what `last_used.load_last_used_options` compares against.
  emmykit's reader and writer are typed against `ek.Options` rather than
  against a payload, which is the whole of why this class is still alive.
  `pipeline.run` copies the first three across at the save and nowhere else.
- **Construction inputs.** `home` and `cwd`, which `cli.main` derives the
  run's `Settings` from, and `log_mode`, which only `ek.configure_logging`
  reads.
- **Passed as themselves.** `stdlib` and `aliases`. The design keeps both out
  of every bundle ("they belong to no bundle"), and `pipeline.run` builds its
  own rather than reading these -- they survive because
  `save_options_to_json` serializes the instance's whole `__dict__`, so
  removing them would change the payload, and the payload is phase 4b's.
- **`rawlog`.** Read by `cli.main` for `ek.configure_logging` and for
  `ek.print_all_errors`; `Settings.rawlog` is what every stage below reads.

Phase 4b breaks the persistence coupling -- veny writes its own `LastUsed`
record -- and deletes this file, the `cli.Options` re-export, and the test
references in both spellings. Nothing new goes in here.
"""

from __future__ import annotations

import logging
from pathlib import Path

import emmykit as ek

from . import alias_index, stdlib_index


class Options(ek.Options):
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        super().__init__()  # Call the parent class's __init__ method from emmykit
        self.log_mode: int = logging.INFO  # Use --debug to change to logging.DEBUG.
        self.my_name: str = "veny"  # Fixed: the installed command's name, not whatever argv[0] happens to be.
        self.home: Path = Path.home()  # User's home directory
        # The "my_dir" is NOT the directory where this script is located.
        # Instead, it's the directory where this script will store its virtual environments and packages.
        self.my_dir: Path = self.home / self.my_name
        self.cwd: Path = Path.cwd().expanduser().resolve(strict=True)
        # The three fields ek.save_options_to_json builds its filename from,
        # alongside my_name. Target owns them for the run; pipeline.run copies
        # them across just before the save, because emmykit's writer is typed
        # against ek.Options rather than against a payload. Phase 4b drops the
        # coupling -- veny writes its own LastUsed record -- and these go with
        # it. Nothing else may read them.
        self.python_script: Path | None = None
        self.script_dir: Path | None = None
        self.timestamp: str = ""
        # And the two the *reader* recovers. last_used.load_last_used_options
        # rebuilds an Options from the saved __dict__, and
        # load_last_used_venv_python and the cache search's last-used pass
        # read these two back off it. They left Options in phase 4a Task 6
        # and had to come back: without them the JSON carries no venv at all,
        # so --feeling-lucky and the last-used pointer silently never match
        # again. Caught by scripts/differential_4a.py, not by the unit suite.
        self.venv_dir: Path | None = None
        self.venv_python: Path | None = None
        self.options_json_filepath: Path | None = None
        # Before 2025-08-10 at 22:49:00, paths were stored as strings. After that date, they were stored as pathlib.Path objects. Any .pkl files created before that date have their paths converted to pathlib.Path objects when loaded. Any .json files created before that date are ignored when loading last-used options.
        self.pathlibcutoff: str = "20250810-224900"
        self.rawlog: bool = False
        # Standard-library membership is derived from a real interpreter, never hardcoded.
        # Replaced in run() once the target's python_command is known, so that truth comes from
        # the interpreter that will actually run the user's script. See
        # docs/superpowers/specs/2026-08-12-stdlib-index-design.md
        self.stdlib: stdlib_index.StdlibIndex = stdlib_index.for_running_interpreter()
        # Import-name-to-pip-name resolution. Replaced in main() once
        # the target's python_command is known, so the resolver probes the
        # interpreter that will actually run the user's script. empty()
        # rather than build() here: Options() is constructed before
        # python_command is known and in every test, and build() spawns a
        # probe subprocess. See
        # docs/superpowers/specs/2026-08-12-module-alias-resolver-design.md
        self.aliases: alias_index.AliasIndex = alias_index.empty(self.my_dir)
