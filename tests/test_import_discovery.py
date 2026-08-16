"""Pin which imports veny's scan discovers, independent of I/O recording."""

from pathlib import Path

from veny import cli


def _scan(script: Path, custom_modules: dict[str, Path]) -> cli.Options:
    """Run the import scan over one script and return the populated options.

    Args:
        script:         The Python file to analyze.
        custom_modules: Local module name to file path, as main() would supply.

    Returns:
        The Options object the scan wrote its findings into.
    """
    options = cli.Options()
    options.rawlog = True
    options.python_script = script
    options.script_dir = script.parent
    options.custom_modules = custom_modules
    cli.find_imports_in_script(options, script)
    return options


def test_function_body_import_in_a_custom_module_is_discovered(
    tmp_path: Path,
) -> None:
    """An import inside a called function of a local module still counts."""
    helper = tmp_path / "helper.py"
    helper.write_text(
        "import numpy\n\n\ndef h():\n    import pandas\n\n    return pandas\n"
    )
    script = tmp_path / "s.py"
    script.write_text(
        "import requests\n"
        "import helper\n\n\n"
        "def main():\n"
        "    requests.get('https://example.com')\n"
        "    return helper.h()\n\n\n"
        "main()\n"
    )

    options = _scan(script, {"helper": helper})

    assert options.all_imports == {"numpy", "pandas", "requests"}
    assert options.loaded_custom_modules == {"helper"}


def test_standard_library_imports_are_not_reported_as_needing_install(
    tmp_path: Path,
) -> None:
    """Stdlib names are recorded as seen, never as imports to install."""
    script = tmp_path / "s.py"
    script.write_text("import os\nimport json\nimport requests\n\nprint(os, json)\n")

    options = _scan(script, {})

    assert options.all_imports == {"requests"}
    assert {"os", "json"} <= options.seen_stdlib_imports


def test_a_script_with_no_third_party_imports_yields_an_empty_import_set(
    tmp_path: Path,
) -> None:
    """The empty case is empty -- nothing is seeded into the import set."""
    script = tmp_path / "s.py"
    script.write_text("import sys\n\nprint(sys.version)\n")

    options = _scan(script, {})

    assert options.all_imports == set()
