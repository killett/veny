"""The products one veny run's stages hand to the next."""

from collections.abc import Mapping
from dataclasses import dataclass

from .alias_index import ResolvedImport


@dataclass(frozen=True)
class Requirements:
    """What classification decided about one run's imports.

    Frozen because it is a product, not a workspace: classification computes
    it once and every later stage only reads it.

    `seen_stdlib` and `extra_requirements` are pass-throughs, not products.
    Classification neither computes nor changes them -- the first is copied
    off the scan and the second is the caller's own input -- and they travel
    here only because later stages (the manifest writer, the reporting block)
    need them alongside the classification itself.

    Attributes:
        all_imports:        Import names left to account for, after the bad
                            ones are subtracted and any --reqs names folded in.
        bad:                Names that must never be handed to pip.
        installed:          Records for imports the probe environment already
                            satisfies.
        uninstalled:        Records for imports that must be installed,
                            dependencies included.
        seen_stdlib:        Standard-library names the scan skipped
                            (pass-through, for reporting).
        extra_requirements: The --reqs file's entries, name to version
                            specifier (pass-through, for the manifest).
    """

    all_imports: frozenset[str]
    bad: frozenset[str]
    installed: frozenset[ResolvedImport]
    uninstalled: frozenset[ResolvedImport]
    seen_stdlib: frozenset[str]
    extra_requirements: Mapping[str, str | None]

    @property
    def total_imports(self) -> int:
        """The number of imports classification had to account for.

        Returns:
            The size of all_imports, which is what the progress display
            counts towards.
        """
        return len(self.all_imports)
