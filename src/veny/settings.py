"""The invariants of one veny run, fixed once and never mutated."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Run invariants that no stage may change.

    Attributes:
        my_name:                 The installed command's name, "veny".
        cwd:                     The directory veny was invoked from.
        stay_out_list:           Path fragments never searched for local modules.
        search_above_this_dir:   Whether to search above cwd for local modules.
        rawlog:                  Suppress veny's own commentary.
    """

    my_name: str
    cwd: Path
    stay_out_list: tuple[str, ...]
    search_above_this_dir: bool
    rawlog: bool
