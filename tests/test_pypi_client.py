import io
import json
import zipfile

import pypi_client
from pypi_client import (
    MAX_WHEEL_BYTES,
    PyPIClient,
)


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

    def get(self, url, headers=None, *, max_bytes=None):
        self.requests.append((url, dict(headers or {})))
        if url.endswith("/json"):
            if self.json_payload is None:
                raise pypi_client.FetchError("404")
            body = json.dumps(self.json_payload).encode()
            return 200, {}, body if max_bytes is None else body[:max_bytes]
        range_header = (headers or {}).get("Range")
        if range_header and self.honour_range:
            # veny only ever sends an absolute tail range now (files.pythonhosted.org
            # answers a suffix range, bytes=-N, with 501 Unsupported client range).
            start_str, end_str = range_header.removeprefix("bytes=").split("-")
            body = self.wheel[int(start_str) : int(end_str) + 1]
            return 206, {}, body if max_bytes is None else body[:max_bytes]
        body = self.wheel
        return 200, {}, body if max_bytes is None else body[:max_bytes]


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
    monkeypatch.setattr(pypi_client, "MAX_WHEEL_BYTES", 64)
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
    garbage = pypi_client._CENTRAL_SIGNATURE * 1000
    eocd = (
        pypi_client._EOCD_SIGNATURE
        + b"\x00" * 6
        + (5).to_bytes(2, "little")  # total_entries claims 5; nowhere near true
        + len(garbage).to_bytes(4, "little")
        + b"\x00" * 4
        + b"\x00" * 2
    )
    assert pypi_client._names_from_tail(garbage + eocd) is None


def test_range_header_is_an_absolute_tail_range():
    # files.pythonhosted.org answers a suffix range (bytes=-N) with
    # 501 Unsupported client range; veny must compute an absolute range from
    # the wheel's declared size instead (bytes=start-end, end == size - 1).
    wheel = _wheel_bytes([f"pkg/mod{i}.py" for i in range(200)])
    fetcher = _FakeFetcher(_json_for(wheel), wheel)
    PyPIClient(fetcher).top_levels("pkg")
    wheel_requests = [
        headers for url, headers in fetcher.requests if url.endswith(".whl")
    ]
    assert wheel_requests
    for headers in wheel_requests:
        range_header = headers["Range"]
        assert not range_header.startswith("bytes=-")
        start_str, end_str = range_header.removeprefix("bytes=").split("-")
        assert int(start_str) >= 0
        assert int(end_str) == len(wheel) - 1


def test_non_positive_declared_size_returns_none():
    # A declared size of 0 (or negative) cannot produce a usable Range;
    # treat it as "cannot inspect" rather than sending a malformed header.
    wheel = _wheel_bytes(["pkg/__init__.py"])
    payload = _json_for(wheel)
    payload["urls"][0]["size"] = 0
    fetcher = _FakeFetcher(payload, wheel)
    assert PyPIClient(fetcher).top_levels("pkg") is None
    assert not any(url.endswith(".whl") for url, _ in fetcher.requests)


def test_metadata_larger_than_max_wheel_bytes_is_not_truncated():
    # UrllibFetcher.get is shared by the metadata and wheel requests but must
    # not share a byte cap: real projects' /pypi/<name>/json bodies routinely
    # exceed MAX_WHEEL_BYTES on their own (grpcio is 8.8 MB; botocore, awscli,
    # numpy, and boto3 all clear 3 MB), so capping the metadata read at
    # MAX_WHEEL_BYTES would silently blind those projects.
    wheel = _wheel_bytes(["pkg/__init__.py"])
    payload = _json_for(wheel)
    payload["padding"] = "x" * (MAX_WHEEL_BYTES + 1024)
    fetcher = _FakeFetcher(payload, wheel)
    assert PyPIClient(fetcher).top_levels("pkg") == frozenset({"pkg"})
