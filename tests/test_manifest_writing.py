"""Tests for building a venv's manifest from its final state."""

import json
import subprocess
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import TypedDict

from veny import cache_search, stdlib_index, venv_cache
from veny import cli as veny
from veny.alias_index import ResolvedImport


def an_options() -> veny.Options:
    """Build an Options carrying the fields manifest_for reads."""
    options = veny.Options()
    options.python_command = "/usr/bin/python3.12"
    options.stdlib = stdlib_index.StdlibIndex(
        names=frozenset({"os"}), python_version=(3, 12), source="test"
    )
    options.timestamp = "20260814-091500"
    options.uninstalled_imports = {
        ResolvedImport("yaml", "PyYAML"),
        ResolvedImport("numpy", "numpy"),
    }
    options.extra_requirements = {"numpy": ">=1.2"}
    return options


class ManifestKwargs(TypedDict):
    """Keyword arguments cache_search.manifest_for takes, mirrored for the splat.

    A plain ``dict[str, object]`` return type would type-check the literal
    fine but make every ``**manifest_kwargs(...)`` call site an error --
    mypy cannot see through ``object`` to the specific parameter types
    ``manifest_for`` declares. A TypedDict is what mypy understands as a
    valid ``**kwargs`` source, so this is the annotation manifest_kwargs
    needs to stay both typed and splattable.
    """

    uninstalled: AbstractSet[ResolvedImport]
    extra_requirements: Mapping[str, str | None]
    timestamp: str
    python_command: str
    run_tag: str
    versions: dict[str, str]
    venv_tag: str


def manifest_kwargs(
    options: veny.Options, versions: dict[str, str], venv_tag: str = ""
) -> ManifestKwargs:
    """The arguments cli.py hands cache_search.manifest_for, read off an Options.

    manifest_for takes no Options any more -- every field it used to reach for
    is an explicit argument now. This mirrors setup_virtualenv's call so the
    fixture above stays the single description of the run under test; it is
    not a second implementation of anything manifest_for does.

    Args:
        options:  The run's Options, read for the fields manifest_for wants.
        versions: Installed versions, keyed by normalized pip name.
        venv_tag: The venv's own "major.minor", or "" if it could not be probed.

    Returns:
        Keyword arguments ready to splat into cache_search.manifest_for.
    """
    return {
        "uninstalled": options.uninstalled_imports,
        "extra_requirements": options.extra_requirements,
        "timestamp": options.timestamp,
        "python_command": options.python_command,
        "run_tag": cache_search.interpreter_tag(options.stdlib),
        "versions": versions,
        "venv_tag": venv_tag,
    }


def test_manifest_for_records_versions_and_specs() -> None:
    """A manifest without versions cannot answer whether a pin is satisfied."""
    manifest = cache_search.manifest_for(
        **manifest_kwargs(an_options(), {"pyyaml": "6.0.2", "numpy": "2.1.3"})
    )
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version == "6.0.2"
    assert by_pip["PyYAML"].requested_spec is None
    assert by_pip["numpy"].installed_version == "2.1.3"
    assert by_pip["numpy"].requested_spec == ">=1.2"
    assert manifest.interpreter_tag == "3.12"
    assert manifest.interpreter_path == "/usr/bin/python3.12"
    assert manifest.schema_version == venv_cache.SCHEMA_VERSION
    assert manifest.veny_version == veny.__version__


def test_manifest_for_records_an_unknown_version_as_none() -> None:
    """Inventing a version here would let an unsatisfiable pin look satisfied."""
    manifest = cache_search.manifest_for(**manifest_kwargs(an_options(), {}))
    assert all(record.installed_version is None for record in manifest.packages)


def test_manifest_for_keys_versions_by_normalized_name() -> None:
    """pip reports 'PyYAML'; the record spells it differently; both name one project."""
    manifest = cache_search.manifest_for(
        **manifest_kwargs(an_options(), {"py-yaml": "6.0.2"})
    )
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version is None
    manifest = cache_search.manifest_for(
        **manifest_kwargs(an_options(), {"pyyaml": "6.0.2"})
    )
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version == "6.0.2"


def test_manifest_for_finds_a_pin_keyed_by_a_different_spelling() -> None:
    """extra_requirements is user-typed; a lookup on the record's own pip_name spelling can miss it entirely."""
    options = an_options()
    options.uninstalled_imports = {ResolvedImport("yaml", "pyyaml")}
    options.extra_requirements = {"PyYAML": ">=6.0"}
    manifest = cache_search.manifest_for(**manifest_kwargs(options, {}))
    assert manifest.packages[0].requested_spec == ">=6.0"


def test_record_venv_state_renames_before_writing_the_manifest(monkeypatch, tmp_path):
    """A stale folder name would reject a venv the manifest would accept.

    The folder name is written before installing, from the pre-repair pip
    names. If verify_and_repair_imports later swaps one -- exactly what this
    test's records simulate, "yaml" repaired to "PyYAML" plus "numpy" newly
    added -- the folder must be brought back into agreement before the
    manifest is written, and the "failed-" prefix must survive that rename.

    Swapping the two calls in record_venv_state (write the manifest, then
    rename) would still pass every assertion about the *final* directory
    layout: renaming a directory carries a file already written inside it
    along for the ride, so old_dir simply stops existing either way and
    new_dir ends up holding a valid manifest either way. Only watching which
    directory write_manifest is actually called with -- via the spy below --
    can tell the two orderings apart.
    """
    options = an_options()
    run_tag = cache_search.interpreter_tag(options.stdlib)
    old_name = "failed-" + venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=run_tag,
        timestamp=options.timestamp,
        pip_names=["yaml"],  # The pre-repair pip name the folder was built with.
    )
    old_dir = tmp_path / old_name
    options.set_venv_dir(old_dir)  # Creates old_dir on disk.

    # Real record_venv_state, real rename_venv, real venv_cache.write_manifest
    # -- only the interpreter probe is stubbed, since it would otherwise spawn
    # a real Python.
    monkeypatch.setattr(
        cache_search,
        "installed_state_in_venv",
        lambda venv_python: ({"pyyaml": "6.0.2", "numpy": "2.1.3"}, "3.12"),
    )

    real_write_manifest = venv_cache.write_manifest
    write_manifest_calls: list[Path] = []

    def spy_write_manifest(venv_dir, manifest):
        write_manifest_calls.append(Path(venv_dir))
        return real_write_manifest(venv_dir, manifest)

    monkeypatch.setattr(venv_cache, "write_manifest", spy_write_manifest)

    recorded = cache_search.record_venv_state(
        old_dir,
        # What set_venv_dir(old_dir) above put on options.venv_python, spelled
        # out because record_venv_state takes it as a real argument now. The
        # probe that would read it is stubbed, so only its type matters here.
        venv_python=old_dir / "bin" / "python",
        venv_name=options.venv_name,
        timestamp=options.timestamp,
        run_tag=run_tag,
        python_command=options.python_command,
        uninstalled=options.uninstalled_imports,
        extra_requirements=options.extra_requirements,
        rawlog=options.rawlog,
    )

    wanted_name = venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=run_tag,
        timestamp=options.timestamp,
        pip_names=[record.pip_name for record in options.uninstalled_imports],
    )
    new_dir = tmp_path / f"failed-{wanted_name}"

    assert old_dir != new_dir, "the test setup must simulate an actual repair"
    assert recorded == new_dir
    assert new_dir.is_dir()
    assert not old_dir.exists()
    assert write_manifest_calls == [new_dir], (
        "write_manifest must be called after the rename, with the new directory"
    )

    manifest = venv_cache.read_manifest(new_dir)
    assert manifest is not None
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["PyYAML"].installed_version == "6.0.2"
    assert by_pip["numpy"].installed_version == "2.1.3"


def test_record_venv_state_renames_into_agreement_when_the_venvs_tag_differs_from_the_runs(
    monkeypatch, tmp_path
):
    """The folder name must track the manifest's tag, not just the run's.

    build_folder_name is called with the run's classified tag
    (cache_search.interpreter_tag(options.stdlib)) in setup_virtualenv, before
    the venv exists -- nothing better is available there. But the manifest
    record_venv_state writes uses the venv's own probed tag. If the venv's
    real interpreter ends up differing from the run's -- a degraded probe, or
    uv resolving to a different Python than veny classified imports against --
    those two tags disagree, and venv_cache.satisfies rejects this venv on
    every later run because its folder tag mismatches its own manifest,
    forcing a silent rebuild forever with the mismatched venv left as an
    orphan. This test pins that record_venv_state renames the folder to the
    manifest's tag even when no package changed -- only the tag did -- not
    just when verify_and_repair_imports changed which packages are listed.
    """
    options = an_options()  # classifies against "3.12"
    run_tag = cache_search.interpreter_tag(options.stdlib)  # "3.12", the run's tag
    old_name = "failed-" + venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=run_tag,
        timestamp=options.timestamp,
        pip_names=[record.pip_name for record in options.uninstalled_imports],
    )
    old_dir = tmp_path / old_name
    options.set_venv_dir(old_dir)  # Creates old_dir on disk.

    # The venv actually reports 3.13 -- disagreeing with the run's 3.12 -- and
    # no package changed.
    monkeypatch.setattr(
        cache_search,
        "installed_state_in_venv",
        lambda venv_python: ({"pyyaml": "6.0.2", "numpy": "2.1.3"}, "3.13"),
    )

    recorded = cache_search.record_venv_state(
        old_dir,
        # What set_venv_dir(old_dir) above put on options.venv_python, spelled
        # out because record_venv_state takes it as a real argument now. The
        # probe that would read it is stubbed, so only its type matters here.
        venv_python=old_dir / "bin" / "python",
        venv_name=options.venv_name,
        timestamp=options.timestamp,
        run_tag=run_tag,
        python_command=options.python_command,
        uninstalled=options.uninstalled_imports,
        extra_requirements=options.extra_requirements,
        rawlog=options.rawlog,
    )

    wanted_name = venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag="3.13",
        timestamp=options.timestamp,
        pip_names=[record.pip_name for record in options.uninstalled_imports],
    )
    new_dir = tmp_path / f"failed-{wanted_name}"

    assert old_dir != new_dir, "the test setup must simulate an actual tag mismatch"
    assert "py3.13" in new_dir.name
    assert recorded == new_dir
    assert new_dir.is_dir()
    assert not old_dir.exists()

    manifest = venv_cache.read_manifest(new_dir)
    assert manifest is not None
    assert manifest.interpreter_tag == "3.13"


def test_installed_state_in_venv_returns_empty_on_oserror(monkeypatch):
    """A probe that cannot even launch must cost a rebuild, not raise out of record_venv_state."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no such file")),
    )
    assert cache_search.installed_state_in_venv(Path("/usr/bin/python3.12")) == ({}, "")


def test_installed_state_in_venv_returns_empty_on_subprocess_error(monkeypatch):
    """A timed-out probe is a SubprocessError, not an OSError; both must degrade the same way."""

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="probe", timeout=60)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    assert cache_search.installed_state_in_venv(Path("/usr/bin/python3.12")) == ({}, "")


def test_installed_state_in_venv_returns_empty_on_nonzero_returncode(monkeypatch):
    """A probe that ran but failed inside the venv must not be read as an empty-but-successful venv."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="boom"
        ),
    )
    assert cache_search.installed_state_in_venv(Path("/usr/bin/python3.12")) == ({}, "")


def test_installed_state_in_venv_returns_empty_on_malformed_json(monkeypatch):
    """A truncated or corrupted probe response must not raise out of a never-raise cache path."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json", stderr=""
        ),
    )
    assert cache_search.installed_state_in_venv(Path("/usr/bin/python3.12")) == ({}, "")


def test_installed_state_in_venv_keys_by_normalized_pip_name(monkeypatch):
    """manifest_for looks this mapping up by normalize_pip_name(record.pip_name); a raw-keyed dict would never match."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "python": [3, 12],
                    "versions": {
                        "PyYAML": "6.0.2",
                        "types_requests": "2.31.0.6",
                    },
                }
            ),
            stderr="",
        ),
    )
    assert cache_search.installed_state_in_venv(Path("/usr/bin/python3.12")) == (
        {
            "pyyaml": "6.0.2",
            "types-requests": "2.31.0.6",
        },
        "3.12",
    )


def test_installed_state_in_venv_probes_the_interpreter_it_was_given(monkeypatch):
    """The probe must run the venv's own Python, not whatever interpreter veny happens to be.

    installed_state_in_venv no longer reads options.venv_python; the caller
    passes it. Ignoring the argument and probing sys.executable would report
    the versions installed outside the venv, and every manifest would record
    them as the venv's own.
    """
    seen: list[list[str]] = []

    def spy_run(command, *args, **kwargs):
        seen.append(list(command))
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps({"python": [3, 12], "versions": {}}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", spy_run)
    cache_search.installed_state_in_venv(Path("/somewhere/myenv/bin/python"))
    assert seen[0][0] == "/somewhere/myenv/bin/python"


def test_the_manifest_tag_comes_from_the_venv_not_the_run() -> None:
    """A degraded stdlib probe must not mislabel the venv's interpreter.

    an_options() classifies against 3.12. A venv reporting 3.13 must be recorded
    as 3.13, or a later degraded run matches the wrong tag and reuses it.
    """
    manifest = cache_search.manifest_for(**manifest_kwargs(an_options(), {}, "3.13"))
    assert manifest.interpreter_tag == "3.13"
    assert manifest.interpreter_path == "/usr/bin/python3.12"


def test_an_unreadable_venv_falls_back_to_the_runs_own_tag() -> None:
    """An empty tag means the probe failed, not that the venv has no version."""
    manifest = cache_search.manifest_for(**manifest_kwargs(an_options(), {}, ""))
    assert manifest.interpreter_tag == "3.12"


def test_record_venv_state_probes_the_given_venv_and_records_the_runs_own_fields(
    monkeypatch, tmp_path
):
    """record_venv_state's own five call sites must all be wired to its arguments.

    record_venv_state takes nine explicit arguments now and passes seven of
    them on to manifest_for, one to installed_state_in_venv and four to
    build_folder_name. Measured by substitution, six of those onward wirings
    left the whole suite green: `installed_state_in_venv("<other path>")`,
    `interpreter_tag=venv_tag` (dropping the `or run_tag` fallback), and
    manifest_for's `extra_requirements={}`, `timestamp=...`,
    `python_command=""` and `run_tag=...`.

    Concrete bugs this catches: probing the wrong interpreter records
    another environment's package versions as this venv's, so the next run
    matches on versions the venv does not have; dropping the `or run_tag`
    fallback writes a folder named `myenv-py-...` whenever the probe
    degrades, which parse_folder_name then rejects, retiring the venv from
    the cache permanently; and `python_command=""` records the interpreter
    running veny as the one the venv was built with.

    The probe is made to report an empty tag on purpose -- that is the
    degraded case where the fallback is the only thing supplying a tag.
    """
    options = an_options()
    run_tag = cache_search.interpreter_tag(options.stdlib)
    stale_name = "failed-" + venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag=run_tag,
        timestamp=options.timestamp,
        pip_names=["yaml"],
    )
    old_dir = tmp_path / stale_name
    options.set_venv_dir(old_dir)
    probed: list[Path] = []

    def spy_probe(venv_python):
        probed.append(Path(venv_python))
        return ({"pyyaml": "6.0.2", "numpy": "2.1.3"}, "")

    monkeypatch.setattr(cache_search, "installed_state_in_venv", spy_probe)

    recorded = cache_search.record_venv_state(
        old_dir,
        venv_python=old_dir / "bin" / "python",
        venv_name=options.venv_name,
        timestamp=options.timestamp,
        run_tag=run_tag,
        python_command=options.python_command,
        uninstalled=options.uninstalled_imports,
        extra_requirements=options.extra_requirements,
        rawlog=options.rawlog,
    )

    assert probed == [old_dir / "bin" / "python"]
    assert recorded.name == "failed-" + venv_cache.build_folder_name(
        venv_name=options.venv_name,
        interpreter_tag="3.12",
        timestamp=options.timestamp,
        pip_names=["PyYAML", "numpy"],
    )
    manifest = venv_cache.read_manifest(recorded)
    assert manifest is not None
    assert manifest.interpreter_tag == "3.12"
    assert manifest.interpreter_path == "/usr/bin/python3.12"
    assert manifest.created == "20260814-091500"
    by_pip = {record.pip_name: record for record in manifest.packages}
    assert by_pip["numpy"].requested_spec == ">=1.2"
