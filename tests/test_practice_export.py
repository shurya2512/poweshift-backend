import json
from pathlib import Path

import pytest

from poweshift_backend.data.practice_export import approved_practice_source


def _audit(cache_root: Path, partition: str = "training") -> dict:
    return {
        "cache_root": str(cache_root),
        "sessions": [{
            "weekend": "2026-05-03_Miami_Grand_Prix",
            "event_date": "2026-05-03",
            "partition": partition,
            "source_state": "verified",
            "source_hash": "abc",
            "session_names": ["2026-05-01_Practice_1", "2026-05-01_Sprint_Qualifying"],
        }],
    }


def test_practice_source_resolves_audited_training_fp(tmp_path) -> None:
    cache_root = tmp_path / "cache"
    source = cache_root / "2026-05-03_Miami_Grand_Prix" / "2026-05-01_Practice_1"
    source.mkdir(parents=True)

    approved = approved_practice_source(_audit(cache_root), source)

    assert approved.event_name == "Miami Grand Prix"
    assert approved.session_selector == "FP1"
    assert approved.session_name == "Practice 1"


def test_practice_source_rejects_sprint_and_protected_partitions(tmp_path) -> None:
    cache_root = tmp_path / "cache"
    sprint = cache_root / "2026-05-03_Miami_Grand_Prix" / "2026-05-01_Sprint_Qualifying"
    sprint.mkdir(parents=True)
    with pytest.raises(ValueError, match="free-practice"):
        approved_practice_source(_audit(cache_root), sprint)

    practice = cache_root / "2026-05-03_Miami_Grand_Prix" / "2026-05-01_Practice_1"
    practice.mkdir()
    with pytest.raises(ValueError, match="training partition"):
        approved_practice_source(_audit(cache_root, "selection"), practice)
