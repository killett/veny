"""The mutable state one import scan accumulates."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImportScan:
    """What scanning a script and its local modules discovered.

    Mutable by design: a scan accumulates into it as it walks. Contrast
    Settings, which is frozen because it is fixed before the run starts.

    Attributes:
        all_imports:           Import names the reachable code actually uses.
        custom_modules:        Local module name to the file that provides it.
        loaded_custom_modules: Names resolved to a local module.
        samedir_files:         Local files found beside the script.
        subfolders:            Package subfolders found under the script.
        sys_path_hints:        Directories the script adds to sys.path.
        seen_stdlib_imports:   Standard-library names skipped during the scan.
    """

    all_imports: set[str] = field(default_factory=set)
    custom_modules: dict[str, Path] = field(default_factory=dict)
    loaded_custom_modules: set[str] = field(default_factory=set)
    samedir_files: list[Path] = field(default_factory=list)
    subfolders: list[str] = field(default_factory=list)
    sys_path_hints: set[Path] = field(default_factory=set)
    seen_stdlib_imports: set[str] = field(default_factory=set)
