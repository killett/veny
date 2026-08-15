"""Fetch PyPI wheel metadata and determine the top-level import names provided.

This module never installs anything; it only reads remote wheels over HTTP range
requests to extract their central directory listings. The caller (AliasIndex in
alias_index.py) uses the results to confirm whether a PyPI project declares a
given top-level import name.
"""

from __future__ import annotations

import io
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterable
from typing import Final, Protocol


class FetchError(Exception):
    """Raised by a fetcher when a URL cannot be retrieved."""


class Fetcher(Protocol):
    """Minimal HTTP surface the PyPI client needs, so tests can inject a fake."""

    def get(
        self, url: str, headers: dict[str, str] | None = None, *, max_bytes: int
    ) -> tuple[int, dict[str, str], bytes]:
        """Retrieve a URL.

        Args:
            url:       The absolute URL to retrieve.
            headers:   Request headers, such as Range.
            max_bytes: Upper bound on bytes read from the response body. The
                caller chooses this per request -- a wheel body and a JSON
                metadata body have very different legitimate sizes -- so
                nothing here should default to a one-size-fits-all cap.

        Returns:
            The status code, response headers, and body bytes.

        Raises:
            FetchError: If the URL cannot be retrieved.
        """
        ...


class UrllibFetcher:
    """A Fetcher backed by urllib, so veny needs no third-party HTTP library."""

    def get(
        self, url: str, headers: dict[str, str] | None = None, *, max_bytes: int
    ) -> tuple[int, dict[str, str], bytes]:
        """Retrieve a URL with a bounded timeout and a bounded read.

        Args:
            url:       The absolute URL to retrieve.
            headers:   Request headers, such as Range.
            max_bytes: Upper bound on bytes read from the response body, so a
                server that ignores a Range header (or serves an
                unexpectedly large body) cannot make this method transfer
                more than the caller is willing to receive.

        Returns:
            The status code, response headers, and body bytes.

        Raises:
            FetchError: On any network or protocol failure.
        """
        if not url.startswith("https://"):
            raise FetchError(f"Refusing to fetch a non-https URL: {url}")
        request = urllib.request.Request(url, headers=headers or {})  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=_READ_TIMEOUT) as response:  # noqa: S310
                body = response.read(max_bytes)
                return int(response.status), dict(response.headers), body
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise FetchError(str(exc)) from exc


PYPI_JSON_URL: Final[str] = "https://pypi.org/pypi/{name}/json"
MAX_WHEEL_BYTES: Final[int] = 5 * 1024 * 1024
# The metadata and wheel requests share UrllibFetcher.get but must not share a
# byte cap: a project's /pypi/<name>/json body routinely exceeds MAX_WHEEL_BYTES
# on its own (grpcio is 8.8 MB; botocore, awscli, numpy, and boto3 all clear
# 3 MB), so capping it at MAX_WHEEL_BYTES silently blinds those projects.
MAX_METADATA_BYTES: Final[int] = 32 * 1024 * 1024
_FIRST_WINDOW: Final[int] = 64 * 1024
_WIDE_WINDOW: Final[int] = 1024 * 1024
_CONNECT_TIMEOUT: Final[float] = 5.0
_READ_TIMEOUT: Final[float] = 10.0
_EXCLUDED_SUFFIXES: Final[tuple[str, ...]] = (".dist-info", ".data")

_EOCD_SIGNATURE: Final[bytes] = b"PK\x05\x06"
_CENTRAL_SIGNATURE: Final[bytes] = b"PK\x01\x02"


def _top_levels_from_names(member_names: Iterable[str]) -> frozenset[str]:
    """Reduce zip member paths to the top-level import names a wheel provides.

    Args:
        member_names: Archive member paths, as stored in the central directory.

    Returns:
        The top-level names, excluding packaging metadata directories.
    """
    found: set[str] = set()
    for member in member_names:
        head, _, tail = member.replace("\\", "/").partition("/")
        if (
            not head
            or head.startswith("__pycache__")
            or head.endswith(_EXCLUDED_SUFFIXES)
        ):
            continue
        if tail:
            found.add(head)
        elif head.endswith(".py"):
            found.add(head.removesuffix(".py"))
    return frozenset(found)


def _names_from_zip_bytes(blob: bytes) -> tuple[str, ...]:
    """List member names of a complete zip archive held in memory.

    Args:
        blob: The whole archive.

    Returns:
        Member names.
    """
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        return tuple(archive.namelist())


def _names_from_tail(tail: bytes) -> tuple[str, ...] | None:
    """Parse member names from a zip's trailing bytes.

    A zip's central directory lists every member path and ends immediately
    before the end-of-central-directory record, so the whole listing can be read
    from the tail alone and no member is ever decompressed.

    Args:
        tail: The trailing bytes of the archive.

    Returns:
        Member names, or None if the end-of-central-directory record is not in
        tail, the directory it points at is not fully inside tail, or the
        parsed walk does not satisfy the invariants a genuine central
        directory has (see below). Either way the caller should retry with a
        wider window.
    """
    marker = tail.rfind(_EOCD_SIGNATURE)
    if marker < 0:
        return None
    total_entries = int.from_bytes(tail[marker + 10 : marker + 12], "little")
    directory_size = int.from_bytes(tail[marker + 12 : marker + 16], "little")
    start = marker - directory_size
    if start < 0:
        return None
    names: list[str] = []
    cursor = start
    while tail[cursor : cursor + 4] == _CENTRAL_SIGNATURE:
        name_length = int.from_bytes(tail[cursor + 28 : cursor + 30], "little")
        extra_length = int.from_bytes(tail[cursor + 30 : cursor + 32], "little")
        comment_length = int.from_bytes(tail[cursor + 32 : cursor + 34], "little")
        name_start = cursor + 46
        names.append(
            tail[name_start : name_start + name_length].decode("utf-8", "replace")
        )
        cursor = name_start + name_length + extra_length + comment_length
    # A genuine central directory satisfies two invariants that garbage bytes
    # (e.g. a buffer that merely repeats the central-file signature) do not:
    # the walk ends exactly where the EOCD begins, and the number of entries
    # walked matches the EOCD's own total-entries field. Either mismatch
    # means this was not a real directory, so report "could not determine"
    # rather than a confidently wrong (and possibly empty) name list.
    if not names or cursor != marker or len(names) != total_entries:
        return None
    return tuple(names)


class PyPIClient:
    """Answers whether a PyPI project declares a given top-level import name.

    The answer comes from the wheel's zip central directory, which lists every
    member path and sits at the end of the file. An absolute tail Range request
    (computed from the wheel's declared size) reads it without transferring the
    wheel body, so confirming a candidate costs one JSON request plus tens of
    kilobytes. A suffix Range request (``bytes=-N``) would be simpler, but
    files.pythonhosted.org answers that form with ``501 Unsupported client
    range``; only the absolute form (``bytes=start-end``) works against it.
    """

    def __init__(self, fetcher: Fetcher | None = None) -> None:
        """Store the fetcher and start an empty per-project cache.

        Args:
            fetcher: HTTP surface to use. Defaults to UrllibFetcher.
        """
        self._fetcher: Fetcher = fetcher if fetcher is not None else UrllibFetcher()
        self._cache: dict[str, frozenset[str] | None] = {}

    def top_levels(self, name: str) -> frozenset[str] | None:
        """Return the top-level names the project's smallest wheel declares.

        Args:
            name: The PyPI project name.

        Returns:
            The declared top-level names, or None when the project does not
            exist, ships no wheel, or cannot be inspected within the size cap.
        """
        if name not in self._cache:
            self._cache[name] = self._inspect(name)
        return self._cache[name]

    def _inspect(self, name: str) -> frozenset[str] | None:
        """Fetch project metadata and read its smallest wheel's member listing.

        Args:
            name: The PyPI project name.

        Returns:
            The declared top-level names, or None if anything prevents inspection.
        """
        url = PYPI_JSON_URL.format(name=urllib.parse.quote(name, safe=""))
        try:
            _, _, body = self._fetcher.get(url, max_bytes=MAX_METADATA_BYTES)
            payload = json.loads(body)
        except (FetchError, ValueError) as exc:
            logging.debug("No PyPI metadata for %s (%s).", name, exc)
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("urls"), list):
            logging.debug("Malformed PyPI metadata for %s.", name)
            return None
        wheels = []
        for entry in payload["urls"]:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("filename"), str)
                or not isinstance(entry.get("url"), str)
                or not entry["url"].startswith("https://")
                or not isinstance(entry.get("size"), int)
            ):
                logging.debug("Malformed PyPI file entry for %s.", name)
                return None
            if entry["filename"].endswith(".whl"):
                wheels.append(entry)
        if not wheels:
            logging.debug(
                "Project %s ships no wheel, so its top-level names cannot be read.",
                name,
            )
            return None
        smallest = min(wheels, key=lambda entry: entry["size"])
        try:
            return self._read_member_names(smallest["url"], smallest["size"])
        except (FetchError, ValueError, zipfile.BadZipFile) as exc:
            logging.debug("Could not read the wheel listing for %s (%s).", name, exc)
            return None

    def _read_member_names(self, url: str, size: int) -> frozenset[str] | None:
        """Read a remote wheel's member listing without downloading its body.

        files.pythonhosted.org answers a suffix Range (``bytes=-N``) with
        ``501 Unsupported client range``, so the tail is instead requested as
        an absolute range computed from the wheel's declared size: for a
        window W, ``bytes={max(0, size - W)}-{size - 1}``.

        Args:
            url:  Absolute URL of the wheel.
            size: Wheel size in bytes, as reported by PyPI.

        Returns:
            The top-level names, or None when size is not usable, or the
            server refuses Range on a wheel larger than MAX_WHEEL_BYTES.

        Raises:
            FetchError: If the wheel cannot be retrieved.
        """
        if size <= 0:
            logging.debug(
                "Wheel size for %s is not usable (%d); skipping it.", url, size
            )
            return None
        for window in (_FIRST_WINDOW, _WIDE_WINDOW):
            start = max(0, size - window)
            status, _, chunk = self._fetcher.get(
                url,
                headers={"Range": f"bytes={start}-{size - 1}"},
                max_bytes=MAX_WHEEL_BYTES + 1,
            )
            if status != 206:
                # size is PyPI's claim; len(chunk) is what was actually
                # received. Both are checked -- a false or missing declared
                # size must not let an oversized body slip past the cap that
                # exists to bound it.
                if size > MAX_WHEEL_BYTES or len(chunk) > MAX_WHEEL_BYTES:
                    logging.debug(
                        "Server ignored Range for %s and the wheel is %d bytes; abandoning it.",
                        url,
                        max(size, len(chunk)),
                    )
                    return None
                return _top_levels_from_names(_names_from_zip_bytes(chunk))
            names = _names_from_tail(chunk)
            if names is not None:
                return _top_levels_from_names(names)
        logging.debug("Could not locate the central directory of %s.", url)
        return None
