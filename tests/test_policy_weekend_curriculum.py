import json

import pytest

from poweshift_backend.policy.weekend_curriculum import (
    freeze_curriculum_manifest,
    ordered_training_sessions,
)


def test_training_sessions_are_ordered_with_practice_before_race() -> None:
    sessions = (
        {"event_date": "2026-05-24", "event_name": "Canada", "session_kind": "race", "session_id": "canada-race"},
        {"event_date": "2026-05-03", "event_name": "Miami", "session_kind": "race", "session_id": "miami-race"},
        {"event_date": "2026-05-03", "event_name": "Miami", "session_kind": "practice", "session_id": "miami-fp1"},
    )

    ordered = ordered_training_sessions(sessions)

    assert [item["session_id"] for item in ordered] == ["miami-fp1", "miami-race", "canada-race"]


def test_curriculum_manifest_refuses_overlapping_race_splits(tmp_path) -> None:
    path = tmp_path / "curriculum.json"
    payload = {
        "source_partition": "training",
        "sessions": [{
            "event_date": "2026-05-03",
            "event_name": "Miami",
            "session_kind": "race",
            "session_id": "miami-race",
            "profiles": {
                "1": {"training_trace_ids": ["lap-1"], "validation_trace_ids": ["lap-1"]},
            },
        }],
    }

    with pytest.raises(ValueError, match="disjoint"):
        freeze_curriculum_manifest(path, payload)


def test_curriculum_manifest_is_immutable(tmp_path) -> None:
    path = tmp_path / "curriculum.json"
    payload = {
        "source_partition": "training",
        "sessions": [{
            "event_date": "2026-05-03",
            "event_name": "Miami",
            "session_kind": "practice",
            "session_id": "miami-fp1",
            "profiles": {"1": {"training_trace_ids": ["lap-1"], "validation_trace_ids": []}},
        }],
    }

    freeze_curriculum_manifest(path, payload)
    assert json.loads(path.read_text()) == payload
    freeze_curriculum_manifest(path, payload)
    changed = json.loads(json.dumps(payload))
    changed["sessions"][0]["session_id"] = "changed"
    with pytest.raises(RuntimeError, match="differs"):
        freeze_curriculum_manifest(path, changed)
