from hashlib import sha256
import json
from pathlib import Path

from poweshift_backend.contracts.policy_training import PolicyTrainingManifest, PpoRunConfig, config_sha256
from poweshift_backend.policy.artifact import TrainingScenarioCandidate, build_policy_training_artifact
from poweshift_backend.policy.run import run_policy_training


def _source(path: Path) -> str:
    payload = {
        "energy_bundle": {"bundle_id": "bundle-a", "admitted": True, "physics_id": "physics-a", "rules_id": "rules-a", "response_id": "response-a", "accounting_id": "accounting-a", "continuous_profile_id": "profile-a"},
        "schema": {"schema_id": "schema-a", "feature_names": ["a", "b"], "manoeuvres": ["hold", "attack", "defend", "abort"], "recurrent_width": 2, "action_transform_id": "beta-v1"},
        "pit_manifest_id": "pit-a", "route_id": "route-a", "scenario_id": "scenario-a",
        "steps": [{"observation": [1.0, 2.0], "feature_mask": [True, True], "action_mask": [True, True, True, True], "sampled": ["attack", 0.8], "issued": ["attack", 0.8], "delivered": ["attack", 0.5], "sampled_joint_log_probability": -1.25, "recurrent_state_before": [0.0, 0.0], "recurrent_state_after": [0.1, 0.2], "value": 0.4, "reward": 1.0, "terminated": True, "truncated": False}],
    }
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return sha256(path.read_bytes()).hexdigest()


def _artifact(tmp_path: Path, source_sha: str, mode: str = "preflight") -> Path:
    config = PpoRunConfig(1e-2, 0.9, 0.95, 0.2, 0.5, 0.01, 1.0)
    manifest = PolicyTrainingManifest(f"run-{mode}", mode, 4, 1 if mode == "preflight" else 100, "training", source_sha, "rev-a", config_sha256(config), "schema-a", "bundle-a", "profile-a", "physics-a", "rules-a", "pit-a", "route-a", "scenario-a", "measure-a", "criteria-a", config)
    path = tmp_path / f"{mode}-artifact.json"
    build_policy_training_artifact((TrainingScenarioCandidate("scenario-a", "2026-01-01T00:00:00+00:00", "training", source_sha, True),), manifest, path)
    return path


def test_preflight_runs_one_update_and_round_trips_checkpoint(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    artifact = _artifact(tmp_path, _source(source))
    report = run_policy_training(artifact, source, tmp_path / "preflight", mode="preflight")
    assert report.status == "passed"
    assert report.updates == 1
    assert report.records[0].parameter_delta_norm > 0.0
    assert (tmp_path / "preflight" / "checkpoint.pt").is_file()
    assert (tmp_path / "preflight" / "report.json").is_file()


def test_source_mismatch_persists_a_failure_report(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    artifact = _artifact(tmp_path, _source(source))
    source.write_text("{}")
    report = run_policy_training(artifact, source, tmp_path / "failed", mode="preflight")
    assert report.status == "failed"
    assert "source hash" in report.failure
    assert (tmp_path / "failed" / "report.json").is_file()


def test_smoke_requires_matching_preflight_bindings(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source_sha = _source(source)
    preflight = run_policy_training(_artifact(tmp_path, source_sha), source, tmp_path / "preflight", mode="preflight")
    smoke = run_policy_training(_artifact(tmp_path, source_sha, "smoke"), source, tmp_path / "smoke", mode="smoke")
    assert preflight.status == "passed"
    assert smoke.status == "passed"
    assert smoke.updates == 100
