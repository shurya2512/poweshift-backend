import json

import pandas as pd
import pytest

from poweshift_backend.representation.training_event_prep import (
    candidate_route_laps,
    validate_training_event,
)


def test_route_candidates_are_accurate_complete_and_deterministic() -> None:
    laps = pd.DataFrame({
        "DriverNumber": ["2", "1", "1", "2"],
        "LapNumber": [2.0, 3.0, 2.0, 1.0],
        "LapStartTime": pd.to_timedelta([10.0, 20.0, 10.0, 0.0], unit="s"),
        "Time": pd.to_timedelta([20.0, 30.0, 20.0, 10.0], unit="s"),
        "IsAccurate": [True, True, False, True],
        "Deleted": [False, False, False, True],
    })

    candidates = candidate_route_laps(laps)

    assert [(item.entry, item.lap_number) for item in candidates] == [("1", 3.0), ("2", 2.0)]


def test_training_event_refuses_a_protected_partition(tmp_path) -> None:
    acquisition_path = tmp_path / "acquisition.json"
    audit_path = tmp_path / "audit.json"
    acquisition_path.write_text(json.dumps({
        "identity": {
            "date": "2026-07-19",
            "event_name": "Belgian Grand Prix",
            "session_kind": "race",
        }
    }))
    audit_path.write_text(json.dumps({
        "sessions": [{
            "weekend": "2026-07-19_Belgian_Grand_Prix",
            "partition": "selection",
            "source_state": "verified",
        }]
    }))

    with pytest.raises(ValueError, match="verified training"):
        validate_training_event(acquisition_path, audit_path)
