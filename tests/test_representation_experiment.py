import json
from hashlib import sha256
from pathlib import Path

import pytest

from poweshift_backend.contracts.representation import ComparisonPolicy, NumericalPolicy
from poweshift_backend.representation.experiment import _load_manifest
from poweshift_backend.representation.training import policy_identifier


def _write_manifest(directory: Path, declared_model_path: Path) -> None:
    model_path = directory / "gru.pt"
    inputs_path = directory / "training_inputs.npz"
    model_path.write_bytes(b"model")
    inputs_path.write_bytes(b"inputs")
    policy = ComparisonPolicy(
        numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12),
        metric="speed_mae_ms",
        minimum_relative_improvement=0.05,
        evaluation_reuse="reused_evaluation",
        per_update_refit_budget=1,
    )
    record = {
        "candidate": "gru",
        "feature_names": ["speed_ms", "throttle_pct", "brake"],
        "transform_id": "0" * 64,
        "policy_id": policy_identifier(policy),
        "training_input_sha256": "1" * 64,
        "teacher_fit_sha256": "2" * 64,
        "profile_component_names": ["propulsion", "resistance", "braking", "grip"],
        "profile_upper_bounds": [1.0, 1.0, 1.0, 1.0],
        "latent_width": 4,
        "hidden_width": 8,
        "layers": 2,
        "heads": 2,
        "feedforward_width": 16,
        "variance_floor": 1e-4,
        "objective": "gaussian_nll_full",
    }
    manifest = {
        "entry": "1",
        "policy": policy.model_dump(mode="json"),
        "policy_id": policy_identifier(policy),
        "models": {"gru": {"path": str(declared_model_path), "sha256": sha256(model_path.read_bytes()).hexdigest()}},
        "training_inputs": {"path": str(inputs_path), "sha256": sha256(inputs_path.read_bytes()).hexdigest()},
        "model_records": {"gru": record},
        "transforms": {"gru": {"features": record["feature_names"], "mean": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}},
        "teachers": [],
    }
    (directory / "training_manifest.json").write_text(json.dumps(manifest))


def test_loader_rejects_a_manifest_path_that_differs_from_the_loaded_checkpoint(tmp_path: Path) -> None:
    declared = tmp_path / "declared.pt"
    declared.write_bytes(b"model")
    _write_manifest(tmp_path, declared)

    with pytest.raises(ValueError, match="path"):
        _load_manifest(tmp_path)
