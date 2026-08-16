"""Pin how veny locates the uv binary it drives its environment layer with."""

import shutil
import sys

import pytest

from veny import cli


def test_the_packaged_uv_is_preferred_over_the_one_on_path(monkeypatch):
    """The uv installed alongside veny wins; PATH is never consulted."""
    fake = type(sys)("uv")
    fake.find_uv_bin = lambda: "/packaged/uv"
    monkeypatch.setitem(sys.modules, "uv", fake)
    monkeypatch.setattr(shutil, "which", lambda _name: "/on/path/uv")
    cli.uv_binary.cache_clear()

    assert cli.uv_binary() == "/packaged/uv"


def test_a_path_uv_is_used_when_the_package_is_missing(monkeypatch, caplog):
    """Without the package, PATH serves -- and veny says the version is unpinned."""
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: "/on/path/uv")
    cli.uv_binary.cache_clear()

    assert cli.uv_binary() == "/on/path/uv"
    assert "not pinned" in caplog.text


def test_no_uv_anywhere_exits_with_an_install_message(monkeypatch):
    """The failure names the command that fixes it, not just a traceback."""
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    cli.uv_binary.cache_clear()

    with pytest.raises(SystemExit) as caught:
        cli.uv_binary()
    assert "uv tool install veny" in str(caught.value)
