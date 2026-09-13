from pathlib import Path

import pytest

from poweshift_backend.contracts.policy_training import PolicyTrainingManifest, PpoRunConfig, config_sha256
from poweshift_backend.policy.artifact import TrainingScenarioCandidate, build_policy_training_artifact


def _manifest(scenario_id: str = "scenario-a") -> PolicyTrainingManifest:
    config = PpoRunConfig(1e-3, 0.99, 0.95, 0.2, 0.5, 0.01, 1.0)
    return PolicyTrainingManifest("run-a", "preflight", 2, 1, "training", "a" * 64, "rev-a", config_sha256(config), "schema-a", "bundle-a", "profile-a", "physics-a", "rules-a", "pit-a", "route-a", scenario_id, "measure-a", "criteria-a", config)


def test_artifact_selects_the_earliest_compatible_training_candidate(tmp_path: Path) -> None:
    candidates = (
        TrainingScenarioCandidate("late", "2026-01-02T00:00:00+00:00", "training", "a" * 64, True),
        TrainingScenarioCandidate("early", "2026-01-01T00:00:00+00:00", "training", "a" * 64, True),
    )
    artifact = build_policy_training_artifact(candidates, _manifest("early"), tmp_path / "artifact.json")
    assert artifact.scenario_id == "early"
    with pytest.raises(FileExistsError):
        build_policy_training_artifact(candidates, _manifest("early"), tmp_path / "artifact.json")


def test_artifact_refuses_ambiguous_or_nontraining_candidates(tmp_path: Path) -> None:
    tied = (
        TrainingScenarioCandidate("a", "2026-01-01T00:00:00+00:00", "training", "a" * 64, True),
        TrainingScenarioCandidate("b", "2026-01-01T00:00:00+00:00", "training", "a" * 64, True),
    )
    with pytest.raises(ValueError, match="ambiguous"):
        build_policy_training_artifact(tied, _manifest(), tmp_path / "artifact.json")
