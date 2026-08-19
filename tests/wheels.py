"""Build a minimal, real, installable wheel for tests that cross the uv boundary."""

import zipfile
from pathlib import Path


def build_wheel(
    directory: Path, *, name: str = "venytest", version: str = "0.1", value: int = 42
) -> Path:
    """Build a minimal, real, installable wheel entirely from scratch.

    A plain zip carrying ``<name>/__init__.py`` plus a
    ``<name>-<version>.dist-info/`` with METADATA, WHEEL and RECORD -- the
    format verified (2026-08-18, while planning phase 3c's Task 1) to install
    through real ``uv pip install`` with no --no-index/--offline flag and no
    network.

    Args:
        directory: Where to write the wheel and its staging tree.
        name:      The distribution and package name.
        version:   The distribution version.
        value:     The integer the built package's ``value`` attribute holds.

    Returns:
        The path to the built wheel.
    """
    staging = directory / "wheel-staging"
    pkg_dir = staging / name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text(f"value = {value}\n")

    dist_info = staging / f"{name}-{version}.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    )
    (dist_info / "WHEEL").write_text(
        "Wheel-Version: 1.0\nGenerator: test_environment\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    (dist_info / "RECORD").write_text("")

    wheel_path = directory / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging))
    return wheel_path
