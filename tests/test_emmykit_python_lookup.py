"""pipeline's bridge over emmykit's interpreter lookup, before and after emmykit 0.7.0.

emmykit 0.7.0 renamed `find_preferred_python_version` to `find_python` (which
returns an absolute path) and replaced the float `PY_VERSION` with the tuple
`MIN_PYTHON_VERSION`. veny allows `emmykit>=0.4.0,<1.0`, so either API can be
installed; each test builds one of them on the real emmykit module.
"""

from __future__ import annotations

import emmykit as ek
import pytest

from veny import pipeline


@pytest.fixture
def old_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """emmykit as it was before 0.7.0: find_preferred_python_version and PY_VERSION only."""
    for name in ("find_python", "MIN_PYTHON_VERSION"):
        monkeypatch.delattr(ek, name, raising=False)
    monkeypatch.setattr(
        ek, "find_preferred_python_version", lambda: "python3", raising=False
    )
    monkeypatch.setattr(ek, "PY_VERSION", 3.12, raising=False)


@pytest.fixture
def new_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """emmykit from 0.7.0: find_python and MIN_PYTHON_VERSION only."""
    for name in ("find_preferred_python_version", "PY_VERSION"):
        monkeypatch.delattr(ek, name, raising=False)
    monkeypatch.setattr(ek, "find_python", lambda: "/usr/bin/python3", raising=False)
    monkeypatch.setattr(ek, "MIN_PYTHON_VERSION", (3, 12), raising=False)


@pytest.mark.usefixtures("new_api")
def test_new_emmykit_is_asked_through_find_python() -> None:
    """With emmykit 0.7.0, the lookup calls find_python, the only name it has."""
    assert pipeline._find_target_python() == "/usr/bin/python3"


@pytest.mark.usefixtures("old_api")
def test_old_emmykit_is_asked_through_find_preferred_python_version() -> None:
    """With an older emmykit, the lookup calls find_preferred_python_version."""
    assert pipeline._find_target_python() == "python3"


@pytest.mark.usefixtures("new_api")
def test_lookup_passes_on_none_when_no_python_qualifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """None means "no preferred Python"; pipeline.run turns it into "" itself."""
    monkeypatch.setattr(ek, "find_python", lambda: None)

    assert pipeline._find_target_python() is None


@pytest.mark.usefixtures("new_api")
def test_floor_is_formatted_from_the_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    """MIN_PYTHON_VERSION (3, 10) prints as 3.10, not the float's 3.1."""
    monkeypatch.setattr(ek, "MIN_PYTHON_VERSION", (3, 10))

    assert pipeline._python_floor() == "3.10"


@pytest.mark.usefixtures("old_api")
def test_floor_falls_back_to_the_old_float() -> None:
    """An older emmykit's PY_VERSION 3.12 prints as 3.12."""
    assert pipeline._python_floor() == "3.12"
