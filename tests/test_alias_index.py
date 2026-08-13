import io
import json
import subprocess
import sys
import zipfile

import pytest

import alias_index
from alias_index import (
    MAX_WHEEL_BYTES,
    AliasCache,
    AliasOverrideError,
    Candidate,
    PyPIClient,
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


def _wheel_bytes(names, comment=b""):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, b"x")
        archive.comment = comment
    return buffer.getvalue()


class _FakeFetcher:
    """Serves one JSON document and one wheel, recording every request."""

    def __init__(self, json_payload, wheel, honour_range=True):
        self.json_payload = json_payload
        self.wheel = wheel
        self.honour_range = honour_range
        self.requests = []

    def get(self, url, headers=None):
        self.requests.append((url, dict(headers or {})))
        if url.endswith("/json"):
            if self.json_payload is None:
                raise alias_index.FetchError("404")
            return 200, {}, json.dumps(self.json_payload).encode()
        range_header = (headers or {}).get("Range")
        if range_header and self.honour_range:
            start = int(range_header.removeprefix("bytes=").split("-")[0] or 0)
            if range_header.startswith("bytes=-"):
                length = int(range_header.removeprefix("bytes=-"))
                return 206, {}, self.wheel[-length:]
            end = range_header.split("-")[1]
            stop = int(end) + 1 if end else len(self.wheel)
            return 206, {}, self.wheel[start:stop]
        return 200, {}, self.wheel


def _json_for(wheel, extra_files=()):
    files = [
        {
            "filename": "pkg-1.0-py3-none-any.whl",
            "url": "https://files/pkg.whl",
            "packagetype": "bdist_wheel",
            "size": len(wheel),
        }
    ]
    files.extend(extra_files)
    return {"urls": files}


def test_top_levels_are_read_from_the_wheel_listing():
    wheel = _wheel_bytes(
        ["cv2/__init__.py", "cv2/data.py", "pkg-1.0.dist-info/METADATA"]
    )
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    assert PyPIClient(fetcher).top_levels("opencv-python") == frozenset({"cv2"})


def test_dist_info_and_data_members_are_excluded():
    # Without exclusion, every wheel would "provide" a top level named
    # "<project>-<version>.dist-info", matching nothing and confirming nonsense.
    wheel = _wheel_bytes(
        [
            "thing/__init__.py",
            "pkg-1.0.dist-info/RECORD",
            "pkg-1.0.data/scripts/run",
            "__pycache__/stale.pyc",
        ]
    )
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    assert PyPIClient(fetcher).top_levels("thing") == frozenset({"thing"})


def test_single_file_module_contributes_its_stem():
    # six.py and its kin ship as one top-level file, not a package directory.
    wheel = _wheel_bytes(["six.py", "pkg-1.0.dist-info/METADATA"])
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    assert PyPIClient(fetcher).top_levels("six") == frozenset({"six"})


def test_smallest_wheel_is_chosen():
    wheel = _wheel_bytes(["small/__init__.py"])
    payload = _json_for(
        wheel,
        extra_files=[
            {
                "filename": "pkg-1.0-cp312-manylinux.whl",
                "url": "https://files/big.whl",
                "packagetype": "bdist_wheel",
                "size": len(wheel) * 100,
            },
        ],
    )
    fetcher = _FakeFetcher(payload, wheel)
    PyPIClient(fetcher).top_levels("pkg")
    assert any(url == "https://files/pkg.whl" for url, _ in fetcher.requests)
    assert not any(url == "https://files/big.whl" for url, _ in fetcher.requests)


def test_range_request_avoids_transferring_the_whole_wheel():
    wheel = _wheel_bytes([f"pkg/mod{i}.py" for i in range(200)])
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    PyPIClient(fetcher).top_levels("pkg")
    wheel_requests = [
        headers for url, headers in fetcher.requests if url.endswith(".whl")
    ]
    assert wheel_requests
    assert all("Range" in headers for headers in wheel_requests)


def test_oversized_wheel_is_abandoned_when_range_is_ignored():
    # Fail closed: an unprovable candidate must not be attempted, and veny must
    # not silently download 200 MB to find out.
    wheel = _wheel_bytes(["pkg/__init__.py"])
    payload = _json_for(wheel)
    payload["urls"][0]["size"] = MAX_WHEEL_BYTES + 1
    fetcher = _FakeFetcher(payload, wheel, honour_range=False)
    assert PyPIClient(fetcher).top_levels("pkg") is None


def test_small_wheel_is_accepted_when_range_is_ignored():
    wheel = _wheel_bytes(["pkg/__init__.py"])
    fetcher = _FakeFetcher(_json_for(wheel), wheel, honour_range=False)
    assert PyPIClient(fetcher).top_levels("pkg") == frozenset({"pkg"})


def test_central_directory_outside_the_first_window_is_still_found():
    # A long archive comment pushes the end-of-central-directory record out of
    # the initial suffix read; a single-window parser would silently return None.
    wheel = _wheel_bytes(["pkg/__init__.py"], comment=b"c" * 70_000)
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    assert PyPIClient(fetcher).top_levels("pkg") == frozenset({"pkg"})


def test_missing_project_returns_none():
    fetcher = _FakeFetcher(None, b"")
    assert PyPIClient(fetcher).top_levels("does-not-exist") is None


def test_project_without_wheels_returns_none():
    # sdist-only projects cannot be inspected without building them.
    fetcher = _FakeFetcher(
        {
            "urls": [
                {
                    "filename": "pkg-1.0.tar.gz",
                    "url": "https://files/pkg.tar.gz",
                    "packagetype": "sdist",
                    "size": 10,
                }
            ]
        },
        b"",
    )
    assert PyPIClient(fetcher).top_levels("pkg") is None


def test_results_are_cached_per_project():
    # resolve() asks about the same name from several generators; re-fetching
    # would multiply network cost by the number of mutations.
    wheel = _wheel_bytes(["pkg/__init__.py"])
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    client = PyPIClient(fetcher)
    client.top_levels("pkg")
    before = len(fetcher.requests)
    client.top_levels("pkg")
    assert len(fetcher.requests) == before


def test_missing_project_result_is_cached_too():
    # A cached None ("could not determine") must not be re-fetched either --
    # a falsy check like `if not self._cache.get(name)` would pass this test
    # suite while still re-fetching on every call for an unresolvable name.
    fetcher = _FakeFetcher(None, b"")
    client = PyPIClient(fetcher)
    client.top_levels("does-not-exist")
    before = len(fetcher.requests)
    client.top_levels("does-not-exist")
    assert len(fetcher.requests) == before


def test_dist_info_only_wheel_yields_empty_frozenset_not_none():
    # A wheel that genuinely provides nothing importable is a real (if odd)
    # answer, distinct from "could not determine" -- Task 5 treats None and
    # frozenset() differently and must not see one where the other belongs.
    wheel = _wheel_bytes(["pkg-1.0.dist-info/METADATA", "pkg-1.0.dist-info/RECORD"])
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    assert PyPIClient(fetcher).top_levels("pkg") == frozenset()


def test_malformed_pypi_payload_not_a_dict_returns_none():
    fetcher = _FakeFetcher(["not", "a", "dict"], b"")
    assert PyPIClient(fetcher).top_levels("pkg") is None


def test_malformed_pypi_file_entry_missing_size_returns_none():
    # Right top-level shape, malformed entry: must not raise KeyError/TypeError
    # reaching into a missing field -- the same defect class review already
    # caught once each in Task 2's cache loader and Task 3's probe loader.
    fetcher = _FakeFetcher(
        {
            "urls": [
                {
                    "filename": "pkg-1.0-py3-none-any.whl",
                    "url": "https://files/pkg.whl",
                }
            ]
        },
        b"",
    )
    assert PyPIClient(fetcher).top_levels("pkg") is None


def test_non_https_file_url_is_rejected():
    # A malicious or misconfigured index entry pointing at file:// or plain
    # http:// must never reach urlopen.
    wheel = _wheel_bytes(["pkg/__init__.py"])
    payload = _json_for(wheel)
    payload["urls"][0]["url"] = "http://files/pkg.whl"
    fetcher = _FakeFetcher(payload, wheel)
    assert PyPIClient(fetcher).top_levels("pkg") is None


def test_invalid_utf8_member_name_returns_none_instead_of_raising():
    # zipfile.ZipFile decodes a UTF-8-flagged central-directory name
    # strictly; a corrupt or adversarial wheel must degrade to "could not
    # determine" rather than propagate UnicodeDecodeError out of a function
    # contracted never to raise. Only the non-206 full-zip fallback path is
    # exposed to this -- _names_from_tail decodes with errors="replace".
    wheel = bytearray(_wheel_bytes(["\U0001f600/__init__.py"]))
    marker = "\U0001f600".encode()
    index = wheel.rfind(marker)
    assert index != -1
    wheel[index : index + len(marker)] = b"\xff" * len(marker)
    frozen_wheel = bytes(wheel)
    fetcher = _FakeFetcher(_json_for(frozen_wheel), frozen_wheel, honour_range=False)
    assert PyPIClient(fetcher).top_levels("pkg") is None


def test_oversized_body_is_rejected_even_when_declared_size_is_small(monkeypatch):
    # The cap bounds bytes actually received, not just PyPI's claim; a false
    # or stale declared size must not let an oversized body through when the
    # server ignores Range.
    monkeypatch.setattr(alias_index, "MAX_WHEEL_BYTES", 64)
    wheel = _wheel_bytes([f"pkg/mod{i}.py" for i in range(20)])
    payload = _json_for(wheel)
    payload["urls"][0]["size"] = 1
    fetcher = _FakeFetcher(payload, wheel, honour_range=False)
    assert PyPIClient(fetcher).top_levels("pkg") is None


def test_corrupt_central_directory_returns_none_not_empty_frozenset():
    # A buffer of nothing but repeated central-file signatures is what a
    # single "the list is non-empty" check accepts as a real directory,
    # yielding a false "this wheel declares no top-level names" instead of
    # "could not determine". The entry-count and cursor-alignment invariants
    # must catch it.
    garbage = alias_index._CENTRAL_SIGNATURE * 1000
    eocd = (
        alias_index._EOCD_SIGNATURE
        + b"\x00" * 6
        + (5).to_bytes(2, "little")  # total_entries claims 5; nowhere near true
        + len(garbage).to_bytes(4, "little")
        + b"\x00" * 4
        + b"\x00" * 2
    )
    assert alias_index._names_from_tail(garbage + eocd) is None
