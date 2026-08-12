import json
import subprocess
import sys

import pytest

import alias_index
from alias_index import AliasCache, AliasOverrideError, Candidate, Source


def _candidate(pip_name, source, evidence="test"):
    return Candidate(pip_name=pip_name, source=source, evidence=evidence)


def test_stronger_evidence_ranks_first():
    # A heuristic-derived PyPI name must never outrank a human override.
    ranked = alias_index.rank(
        [
            _candidate("guessed", Source.PYPI_CONFIRMED),
            _candidate("chosen", Source.OVERRIDE),
        ]
    )
    assert [c.pip_name for c in ranked] == ["chosen", "guessed"]


def test_same_source_ranks_alphabetically():
    # Without a tiebreak, set iteration order would make runs non-reproducible.
    ranked = alias_index.rank(
        [
            _candidate("zzz", Source.PYPI_CONFIRMED),
            _candidate("aaa", Source.PYPI_CONFIRMED),
        ]
    )
    assert [c.pip_name for c in ranked] == ["aaa", "zzz"]


def test_duplicate_pip_name_keeps_strongest_source():
    # The same name found by two tiers must appear once, at its best evidence,
    # or the attempt loop wastes an attempt installing it twice.
    ranked = alias_index.rank(
        [
            _candidate("pillow", Source.PYPI_CONFIRMED),
            _candidate("pillow", Source.INSTALLED),
        ]
    )
    assert len(ranked) == 1
    assert ranked[0].source is Source.INSTALLED


def test_rank_returns_a_tuple_not_a_generator():
    # Callers iterate candidates more than once; a generator would silently
    # yield nothing on the second pass.
    ranked = alias_index.rank([_candidate("numpy", Source.SEED)])
    assert isinstance(ranked, tuple)


def test_source_has_no_unverified_heuristic_tier():
    # The structural typosquat guard: if a HEURISTIC source ever exists, an
    # unverified name mutation can reach the installer.
    assert not any(member.name == "HEURISTIC" for member in Source)


def test_seed_carries_the_hand_added_aliases():
    # Weak sample assertions would miss dropped or altered entries; compare the full dict.
    expected = {
        "osgeo": "gdal",
        "ffmpeg": "ffmpeg-python",
        "cv2": "opencv-python",
        "netCDF4": "netcdf4",
        "skill_metrics": "SkillMetrics",
        "bugbear": "flake8-bugbear",
        "whisper": "openai-whisper",
        "speedtest": "speedtest-cli",
        "yaml": "PyYAML",
        "zmq": "pyzmq",
    }
    assert alias_index.SEED == expected


def test_missing_override_file_is_not_an_error(tmp_path):
    # Most users never write one; treating absence as failure would break them.
    assert alias_index.load_overrides(tmp_path / "nope.toml") == {}


def test_override_file_is_read(tmp_path):
    path = tmp_path / "module_aliases.toml"
    path.write_text('[aliases]\ncv2 = "my-fork-of-opencv"\n')
    assert alias_index.load_overrides(path) == {"cv2": "my-fork-of-opencv"}


def test_malformed_override_file_raises(tmp_path):
    # Continuing here would resolve names contrary to what the user wrote --
    # the exact silent-wrongness this design exists to remove.
    path = tmp_path / "module_aliases.toml"
    path.write_text("[aliases\ncv2 = broken")
    with pytest.raises(AliasOverrideError) as excinfo:
        alias_index.load_overrides(path)
    assert str(path) in str(excinfo.value)


def test_corrupt_cache_is_quarantined_not_fatal(tmp_path):
    # A cache is regenerable; refusing to run because of one would be absurd.
    # The bad file is kept, because a corrupt cache is evidence of a bug.
    path = tmp_path / "module_aliases_cache.json"
    path.write_text("{not json at all")
    cache = AliasCache.load(path, interpreter_tag="3.12")
    assert cache.get("anything") is None
    quarantined = list(tmp_path.glob("module_aliases_cache.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text() == "{not json at all"


def test_confirm_round_trips_through_disk(tmp_path):
    path = tmp_path / "cache.json"
    AliasCache.load(path, interpreter_tag="3.12").confirm("cv2", "opencv-python")
    reloaded = AliasCache.load(path, interpreter_tag="3.12")
    assert reloaded.get("cv2") == "opencv-python"


def test_entry_from_another_interpreter_is_ignored(tmp_path):
    # A name verified under 3.12 must not silently govern a 3.13 run, where a
    # different distribution may provide it.
    path = tmp_path / "cache.json"
    AliasCache.load(path, interpreter_tag="3.12").confirm("cv2", "opencv-python")
    assert AliasCache.load(path, interpreter_tag="3.13").get("cv2") is None


def test_import_failure_is_persisted_as_a_rejection(tmp_path):
    # "Installed but did not provide the module" is a fact about the package,
    # so re-attempting it on the next run wastes an install every time.
    path = tmp_path / "cache.json"
    AliasCache.load(path, interpreter_tag="3.12").reject("cv2", "cv2", "import_failed")
    reloaded = AliasCache.load(path, interpreter_tag="3.12")
    assert reloaded.rejected_names("cv2") == frozenset({"cv2"})


def test_install_failure_is_not_persisted(tmp_path):
    # An install can fail for transient reasons (network, index outage);
    # persisting that would permanently blacklist a correct package.
    path = tmp_path / "cache.json"
    AliasCache.load(path, interpreter_tag="3.12").reject("cv2", "cv2", "install_failed")
    reloaded = AliasCache.load(path, interpreter_tag="3.12")
    assert reloaded.rejected_names("cv2") == frozenset()


def test_unknown_rejection_kind_raises(tmp_path):
    # Guards against a typo'd kind silently behaving like install_failed.
    cache = AliasCache.load(tmp_path / "cache.json", interpreter_tag="3.12")
    with pytest.raises(ValueError):
        cache.reject("cv2", "cv2", "exploded")


def test_cache_file_is_written_as_readable_json(tmp_path):
    # The file is user-inspectable by design; a pickle or a blob would not be.
    path = tmp_path / "cache.json"
    AliasCache.load(path, interpreter_tag="3.12").confirm("cv2", "opencv-python")
    payload = json.loads(path.read_text())
    assert payload["entries"]["cv2"]["pip_name"] == "opencv-python"


def test_corrupt_rejections_not_a_dict_is_quarantined(tmp_path):
    # Rejections as a list crashes .items() during load without shape validation.
    path = tmp_path / "cache.json"
    path.write_text('{"entries": {}, "rejections": ["not", "a", "dict"]}')
    cache = AliasCache.load(path, interpreter_tag="3.12")
    assert cache.get("anything") is None
    quarantined = list(tmp_path.glob("cache.json.corrupt-*"))
    assert len(quarantined) == 1


def test_corrupt_entry_value_not_a_dict_is_quarantined(tmp_path):
    # Entry value as a string crashes .get() on the affected key.
    path = tmp_path / "cache.json"
    path.write_text('{"entries": {"cv2": "not-a-dict"}, "rejections": {}}')
    cache = AliasCache.load(path, interpreter_tag="3.12")
    assert cache.get("cv2") is None
    quarantined = list(tmp_path.glob("cache.json.corrupt-*"))
    assert len(quarantined) == 1


def test_corrupt_entry_missing_pip_name_is_quarantined(tmp_path):
    # Entry dict without pip_name key crashes on access during load.
    path = tmp_path / "cache.json"
    path.write_text('{"entries": {"cv2": {"python": "3.12"}}, "rejections": {}}')
    cache = AliasCache.load(path, interpreter_tag="3.12")
    assert cache.get("cv2") is None
    quarantined = list(tmp_path.glob("cache.json.corrupt-*"))
    assert len(quarantined) == 1


def test_probe_reads_version_and_distributions(monkeypatch):
    payload = '{"version": [3, 12], "packages": {"cv2": ["opencv-python"]}}'
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

    monkeypatch.setattr(alias_index.subprocess, "run", fake_run)
    tag, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert tag == "3.12"
    assert packages == {"cv2": ["opencv-python"]}
    assert len(calls) == 1


def test_probe_degrades_when_the_interpreter_cannot_run(monkeypatch, caplog):
    # veny's job is to keep going; a missing probe must not stop a run.
    def fake_run(command, **kwargs):
        raise OSError("no such executable")

    monkeypatch.setattr(alias_index.subprocess, "run", fake_run)
    with caplog.at_level("WARNING"):
        tag, packages = alias_index.probe_interpreter("/nope/python3")
    assert packages == {}
    assert tag == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert "no such executable" in caplog.text


def test_probe_degrades_on_unparseable_output(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="not json", stderr="")

    monkeypatch.setattr(alias_index.subprocess, "run", fake_run)
    _, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert packages == {}


def test_probe_degrades_on_nonzero_exit(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="boom")

    monkeypatch.setattr(alias_index.subprocess, "run", fake_run)
    _, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert packages == {}


def test_probe_of_the_running_interpreter_reports_its_own_version():
    # Integration check that the probe code itself is valid Python.
    tag, _ = alias_index.probe_interpreter(sys.executable)
    assert tag == f"{sys.version_info.major}.{sys.version_info.minor}"


def test_probe_degrades_on_timeout(monkeypatch, caplog):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=kwargs.get("timeout", 10))

    monkeypatch.setattr(alias_index.subprocess, "run", fake_run)
    with caplog.at_level("WARNING"):
        _, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert packages == {}
    assert "Could not run" in caplog.text


def test_probe_degrades_on_malformed_payload(monkeypatch):
    # If packages is a list instead of dict, validation should catch it.
    payload = '{"version": [3, 12], "packages": ["not", "a", "dict"]}'

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

    monkeypatch.setattr(alias_index.subprocess, "run", fake_run)
    _, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert packages == {}
