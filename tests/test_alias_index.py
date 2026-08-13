import json
import subprocess
import sys

import pytest

import alias_index
from alias_index import (
    AliasCache,
    AliasIndex,
    AliasOverrideError,
    Candidate,
    Source,
)


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


def test_pep503_equivalent_spellings_collapse_to_one_candidate():
    # PyPI normalizes runs of "-", "_", "." and case, so "skill-metrics" and
    # "skill_metrics" name the same project. Task 6 attempts at most 3
    # candidates; two spellings of one project must not consume two of them.
    # Same-source ties survive as the first-encountered spelling (see rank()'s
    # docstring), so the exact surviving string is asserted, not just
    # membership -- a regression that stored the normalized form instead of
    # an original spelling would still satisfy a membership check but hand
    # pip a name the evidence never confirmed.
    ranked = alias_index.rank(
        [
            _candidate("skill-metrics", Source.PYPI_CONFIRMED),
            _candidate("skill_metrics", Source.PYPI_CONFIRMED),
        ]
    )
    assert len(ranked) == 1
    assert ranked[0].pip_name == "skill-metrics"


def test_pep503_equivalent_spellings_collapse_across_tiers():
    # The single-tier case above ties on source, so first-encountered order
    # decides the survivor -- that alone wouldn't catch a regression that
    # broke the strongest-evidence rule for equivalent spellings specifically.
    # This crosses tiers: INSTALLED must still win over PYPI_CONFIRMED even
    # though the two candidates are spelled differently, and the survivor
    # must carry INSTALLED's own original spelling, not PYPI_CONFIRMED's.
    ranked = alias_index.rank(
        [
            _candidate("skill-metrics", Source.PYPI_CONFIRMED),
            _candidate("skill_metrics", Source.INSTALLED),
        ]
    )
    assert len(ranked) == 1
    assert ranked[0].pip_name == "skill_metrics"
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

    monkeypatch.setattr("alias_index.subprocess.run", fake_run)
    tag, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert tag == "3.12"
    assert packages == {"cv2": ["opencv-python"]}
    assert len(calls) == 1


def test_probe_degrades_when_the_interpreter_cannot_run(monkeypatch, caplog):
    # veny's job is to keep going; a missing probe must not stop a run.
    def fake_run(command, **kwargs):
        raise OSError("no such executable")

    monkeypatch.setattr("alias_index.subprocess.run", fake_run)
    with caplog.at_level("WARNING"):
        tag, packages = alias_index.probe_interpreter("/nope/python3")
    assert packages == {}
    assert tag == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert "no such executable" in caplog.text


def test_probe_degrades_on_unparseable_output(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="not json", stderr="")

    monkeypatch.setattr("alias_index.subprocess.run", fake_run)
    _, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert packages == {}


def test_probe_degrades_on_nonzero_exit(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="boom")

    monkeypatch.setattr("alias_index.subprocess.run", fake_run)
    _, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert packages == {}


def test_probe_of_the_running_interpreter_reports_its_own_version():
    # Integration check that the probe code itself is valid Python.
    tag, _ = alias_index.probe_interpreter(sys.executable)
    assert tag == f"{sys.version_info.major}.{sys.version_info.minor}"


def test_probe_degrades_on_timeout(monkeypatch, caplog):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=kwargs.get("timeout", 10))

    monkeypatch.setattr("alias_index.subprocess.run", fake_run)
    with caplog.at_level("WARNING"):
        _, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert packages == {}
    assert "Could not run" in caplog.text


def test_probe_degrades_on_malformed_payload(monkeypatch):
    # If packages is a list instead of dict, validation should catch it.
    payload = '{"version": [3, 12], "packages": ["not", "a", "dict"]}'

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

    monkeypatch.setattr("alias_index.subprocess.run", fake_run)
    _, packages = alias_index.probe_interpreter("/usr/bin/python3")
    assert packages == {}


class _StubPyPI:
    """Stands in for PyPIClient with a fixed project-to-top-levels table."""

    def __init__(self, table):
        self.table = table
        self.asked = []

    def top_levels(self, name):
        self.asked.append(name)
        return self.table.get(name)


def _index(tmp_path, *, overrides=None, installed=None, pypi=None, tag="3.12"):
    return AliasIndex(
        overrides=overrides or {},
        cache=AliasCache.load(tmp_path / "cache.json", interpreter_tag=tag),
        installed=installed or {},
        pypi=pypi,
    )


def test_override_wins_and_costs_no_network(tmp_path):
    pypi = _StubPyPI({})
    index = _index(tmp_path, overrides={"cv2": "my-opencv"}, pypi=pypi)
    resolution = index.resolve("cv2")
    assert [c.pip_name for c in resolution.candidates] == ["my-opencv"]
    assert resolution.candidates[0].source is Source.OVERRIDE
    assert pypi.asked == []


def test_cache_hit_costs_no_network(tmp_path):
    pypi = _StubPyPI({})
    index = _index(tmp_path, pypi=pypi)
    index.confirm("cv2", "opencv-python")
    resolution = index.resolve("cv2")
    assert [c.pip_name for c in resolution.candidates] == ["opencv-python"]
    assert pypi.asked == []


def test_installed_metadata_and_seed_both_contribute(tmp_path):
    # The seed must not stop the walk, or a stale seed entry could hide better
    # evidence permanently.
    index = _index(
        tmp_path, installed={"cv2": ["opencv-python-headless"]}, pypi=_StubPyPI({})
    )
    names = [c.pip_name for c in index.resolve("cv2").candidates]
    assert names == ["opencv-python-headless", "opencv-python"]


def test_unconfirmed_mutation_never_becomes_a_candidate(tmp_path):
    # The highest-consequence bug in the design: installing a plausible-looking
    # name that does not actually provide the import.
    pypi = _StubPyPI({"typosquat": frozenset({"something_else"})})
    index = _index(tmp_path, pypi=pypi)
    assert index.resolve("typosquat").candidates == ()


def test_confirmed_mutation_becomes_a_pypi_candidate(tmp_path):
    pypi = _StubPyPI({"python-dateutil": frozenset({"dateutil"})})
    index = _index(tmp_path, pypi=pypi)
    candidates = index.resolve("dateutil").candidates
    assert [c.pip_name for c in candidates] == ["python-dateutil"]
    assert candidates[0].source is Source.PYPI_CONFIRMED
    assert candidates[0].top_levels == frozenset({"dateutil"})


def test_identity_candidate_is_confirmed_when_the_project_provides_itself(tmp_path):
    pypi = _StubPyPI({"numpy": frozenset({"numpy"})})
    index = _index(tmp_path, pypi=pypi)
    assert [c.pip_name for c in index.resolve("numpy").candidates] == ["numpy"]


def test_rejected_candidate_is_filtered_out(tmp_path):
    # Re-offering a package already proven not to provide the import wastes an
    # install attempt on every subsequent run.
    pypi = _StubPyPI({"numpy": frozenset({"numpy"})})
    index = _index(tmp_path, pypi=pypi)
    index.reject("numpy", "numpy", "import_failed")
    assert index.resolve("numpy").candidates == ()


def test_rejection_normalizes_across_pep503_equivalent_spellings(tmp_path):
    # rank() dedupes PYPI_CONFIRMED candidates on the PEP 503 normalized
    # name, so the rejection filter must compare on the same normalized
    # form -- otherwise a project rejected as one spelling (e.g.
    # "foo_bar") could be re-offered under an equivalent one (e.g.
    # "foo-bar"), burning an install attempt on the exact project that was
    # just proven not to work. "foo_bar" is not in SEED, so the only
    # possible candidate here comes from the PyPI tier.
    pypi = _StubPyPI({"foo-bar": frozenset({"foo_bar"})})
    index = _index(tmp_path, pypi=pypi)
    index.reject("foo_bar", "foo_bar", "import_failed")
    assert index.resolve("foo_bar").candidates == ()


def test_cache_hit_rejected_under_an_equivalent_spelling_falls_through(tmp_path):
    # Same requirement as the PYPI_CONFIRMED case above, but for the CACHE
    # short-circuit itself: the cache branch's own rejection check must also
    # compare on the normalized name, not the raw string.
    pypi = _StubPyPI({})
    index = _index(tmp_path, installed={"cv2": ["opencv-python-headless"]}, pypi=pypi)
    index.confirm("cv2", "opencv_python")
    index.reject("cv2", "opencv-python", "import_failed")
    names = [c.pip_name for c in index.resolve("cv2").candidates]
    assert "opencv_python" not in names
    assert names == ["opencv-python-headless"]


def test_rejected_cache_hit_falls_through_to_the_rest_of_the_walk(tmp_path):
    # AliasCache.confirm() clears rejections for a name, but AliasCache.reject()
    # does not clear a confirmed entry -- so run 1 can confirm a name and a
    # later run's import can fail for a real reason (a broken native
    # dependency, a yanked release) and persist that rejection, while the
    # cache would still answer with the very name that just failed unless
    # the cache branch itself is checked against rejections. Installed
    # evidence is present here to prove the walk actually falls through to
    # it, not merely that the rejected cache hit disappears.
    pypi = _StubPyPI({})
    index = _index(tmp_path, installed={"cv2": ["opencv-python-headless"]}, pypi=pypi)
    index.confirm("cv2", "opencv-python")
    index.reject("cv2", "opencv-python", "import_failed")
    names = [c.pip_name for c in index.resolve("cv2").candidates]
    assert names == ["opencv-python-headless"]
    assert "opencv-python" not in names


def test_offline_index_still_resolves_from_local_evidence(tmp_path):
    index = _index(tmp_path, installed={"cv2": ["opencv-python"]}, pypi=None)
    assert [c.pip_name for c in index.resolve("cv2").candidates] == ["opencv-python"]


def test_unknown_name_offline_resolves_to_nothing(tmp_path):
    assert _index(tmp_path, pypi=None).resolve("mystery").candidates == ()


def test_build_wires_the_pieces_together(tmp_path, monkeypatch):
    monkeypatch.setattr(
        alias_index,
        "probe_interpreter",
        lambda python: ("3.12", {"cv2": ["opencv-python"]}),
    )
    (tmp_path / "module_aliases.toml").write_text('[aliases]\nfoo = "bar"\n')
    index = alias_index.build(python=sys.executable, my_dir=tmp_path, offline=True)
    assert index.overrides == {"foo": "bar"}
    assert index.pypi is None
    assert [c.pip_name for c in index.resolve("cv2").candidates] == ["opencv-python"]
    # Pin that build() wires the *probed* tag through, not the running
    # interpreter's own tag -- a regression that swapped in _running_tag()
    # would still pass every other assertion here (the stub returns "3.12",
    # which only coincidentally differs from the test runner's own version
    # in the general case) while silently making cache entries valid across
    # interpreter versions, defeating the point of tagging them at all.
    assert index.cache.interpreter_tag == "3.12"
    assert index.cache.path == tmp_path / alias_index.CACHE_FILENAME


def test_empty_spawns_no_probe_and_touches_no_network(tmp_path, monkeypatch):
    # Options() is constructed before the target interpreter is known, and in
    # every test, so empty() must not pay for a probe subprocess or a
    # network call. Both potential culprits are made to raise, so any code
    # path that reaches either fails the test instead of silently degrading.
    def _boom(*args, **kwargs):
        raise AssertionError("empty() must not run a probe or touch the network")

    monkeypatch.setattr(alias_index, "probe_interpreter", _boom)
    monkeypatch.setattr(subprocess, "run", _boom)
    index = alias_index.empty(tmp_path)
    assert index.installed == {}
    assert index.pypi is None
