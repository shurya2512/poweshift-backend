import json
from hashlib import sha256

import pytest

from poweshift_backend.representation.race_promotion import promote_provisional_race_profiles


def _write_inputs(tmp_path, *, progress=0.0562, crossing=0.0558):
    checkpoint = tmp_path / "full_race.pt"
    checkpoint.write_bytes(b"checkpoint")
    checkpoint_hash = sha256(checkpoint.read_bytes()).hexdigest()
    report = {
        "status": "passed",
        "admission_eligible": False,
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": checkpoint_hash,
        "training_hotfixes": [{"logical_batch_id": "window-1"}],
        "training_exclusions": [],
        "error_metrics": {
            "progress_normalized_rmse": progress,
            "crossing_normalized_rmse": crossing,
            "speed_normalized_rmse": 0.186,
            "progress_rank_accuracy": 0.974,
            "signed_gap_mae_s": 1.586,
        },
    }
    profiles = {
        "artifact_kind": "diagnostic_full_weekend_car_profiles_v1",
        "admission_eligible": False,
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": checkpoint_hash,
        "profiles": {
            "1": {"latent_16d": [0.1] * 16, "parameters": {"mass_kg": 800.0}},
            "2": {"latent_16d": [0.2] * 16, "parameters": {"mass_kg": 805.0}},
        },
    }
    report_path = tmp_path / "full_race.json"
    profiles_path = tmp_path / "diagnostic_profiles.json"
    retention_path = tmp_path / "retention.json"
    report_path.write_text(json.dumps(report))
    profiles_path.write_text(json.dumps(profiles))
    retention_path.write_text(json.dumps({"progress_rank_accuracy": 0.99}))
    return report_path, profiles_path, retention_path


def test_promotes_one_active_provisional_profile_per_entry(tmp_path) -> None:
    report, profiles, retention = _write_inputs(tmp_path)
    output = tmp_path / "promoted_profiles.json"

    registry = promote_provisional_race_profiles(report, profiles, (retention,), output)

    assert registry["status"] == "promoted_provisional"
    assert registry["compatible_with_downstream_contract"] is True
    assert registry["physics_admission"] is False
    assert registry["policy"]["progress_normalized_rmse_limit"] == 0.06
    assert registry["policy"]["speed_gate_waived"] is True
    assert set(registry["active_profiles"]) == {"1", "2"}
    assert all(item["active"] is True for item in registry["active_profiles"].values())
    assert all(len(item["profile_id"]) == 64 for item in registry["active_profiles"].values())
    assert len(registry["profile_admission_id"]) == 64
    assert registry == json.loads(output.read_text())


def test_refuses_provisional_promotion_above_six_percent_motion_limit(tmp_path) -> None:
    report, profiles, retention = _write_inputs(tmp_path, progress=0.061)

    with pytest.raises(ValueError, match="progress motion limit"):
        promote_provisional_race_profiles(report, profiles, (retention,), tmp_path / "promoted.json")


def test_refuses_checkpoint_mismatch_and_preserves_immutable_output(tmp_path) -> None:
    report, profiles, retention = _write_inputs(tmp_path)
    payload = json.loads(profiles.read_text())
    payload["checkpoint_sha256"] = "0" * 64
    profiles.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="checkpoint binding"):
        promote_provisional_race_profiles(report, profiles, (retention,), tmp_path / "promoted.json")

    report, profiles, retention = _write_inputs(tmp_path)
    output = tmp_path / "promoted.json"
    output.write_text("{}\n")
    with pytest.raises(FileExistsError, match="immutable promotion"):
        promote_provisional_race_profiles(report, profiles, (retention,), output)
