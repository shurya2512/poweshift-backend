from pathlib import Path

import pytest
import torch

from poweshift_backend.contracts.action import Manoeuvre
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.policy.checkpoint import (
    PolicyCheckpointMetadata,
    load_policy_checkpoint,
    save_policy_checkpoint,
)
from poweshift_backend.policy.model import RecurrentActorCritic
from poweshift_backend.policy.schema import PolicySchema


def _schema(version: str = "schema-a") -> PolicySchema:
    return PolicySchema(version, ("speed", "energy"), tuple(Manoeuvre), 4, "beta-v1")


def _metadata(schema: PolicySchema) -> PolicyCheckpointMetadata:
    bundle = EnergyBundleCompatibility(
        "bundle-a", True, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a"
    )
    return PolicyCheckpointMetadata.from_energy_bundle(schema, bundle, "pit-a", "scenario-a")


def test_checkpoint_round_trip_requires_schema_and_world_compatibility(tmp_path: Path) -> None:
    schema = _schema()
    model = RecurrentActorCritic(schema)
    path = tmp_path / "policy.pt"
    save_policy_checkpoint(path, model, _metadata(schema))

    restored = RecurrentActorCritic(schema)
    metadata = load_policy_checkpoint(path, restored, _metadata(schema))

    assert metadata == _metadata(schema)
    assert all(torch.equal(restored.state_dict()[name], value) for name, value in model.state_dict().items())
    with pytest.raises(ValueError, match="compatible"):
        load_policy_checkpoint(path, RecurrentActorCritic(schema), _metadata(_schema("schema-b")))


def test_checkpoint_binds_the_continuous_profile() -> None:
    schema = _schema()

    metadata = _metadata(schema)

    assert metadata.energy_bundle_id == "bundle-a"
    assert metadata.physics_id == "physics-a"
    assert metadata.continuous_profile_id == "profile-a"
