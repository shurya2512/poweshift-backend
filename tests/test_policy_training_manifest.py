from dataclasses import replace

import pytest

from poweshift_backend.contracts.policy_training import PolicyTrainingManifest, PpoRunConfig, config_sha256
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.policy.train import PhysicalTrainingGate, require_policy_training_ready


def _config() -> PpoRunConfig:
    return PpoRunConfig(1e-3, 0.99, 0.95, 0.2, 0.5, 0.01, 1.0)


def _manifest(mode: str = "preflight") -> PolicyTrainingManifest:
    config = _config()
    return PolicyTrainingManifest(
        "run-a", mode, 7, 1 if mode == "preflight" else 100, "training", "a" * 64,
        "revision-a", config_sha256(config), "schema-a", "bundle-a", "profile-a",
        "physics-a", "rules-a", "pit-a", "route-a", "scenario-a", "measure-a",
        "criteria-a", config,
    )


def _gate() -> PhysicalTrainingGate:
    bundle = EnergyBundleCompatibility("bundle-a", True, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a")
    return PhysicalTrainingGate(bundle, "profile-a", "measure-a", "criteria-a")


def test_manifest_accepts_only_the_fixed_update_count_and_training_partition() -> None:
    assert require_policy_training_ready(_manifest(), _gate()).updates == 1
    assert require_policy_training_ready(_manifest("smoke"), _gate()).updates == 100
    with pytest.raises(ValueError, match="one update"):
        require_policy_training_ready(replace(_manifest(), updates=2), _gate())
    with pytest.raises(ValueError, match="training partition"):
        require_policy_training_ready(replace(_manifest(), source_partition="selection"), _gate())


@pytest.mark.parametrize("field", ["energy_bundle_id", "continuous_profile_id", "physics_id", "rules_id"])
def test_manifest_identities_match_the_admitted_bundle(field: str) -> None:
    with pytest.raises(ValueError, match="energy bundle"):
        require_policy_training_ready(replace(_manifest(), **{field: "other"}), _gate())
