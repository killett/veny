import alias_index
from alias_index import Candidate, Source


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
