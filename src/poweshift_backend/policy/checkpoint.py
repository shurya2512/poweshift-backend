"""Policy checkpoint compatibility and safe state-dict persistence."""

from dataclasses import asdict, dataclass
from pathlib import Path

import torch

from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.policy.model import RecurrentActorCritic
from poweshift_backend.policy.schema import PolicySchema


@dataclass(frozen=True)
class PolicyCheckpointMetadata:
    """Schema and world identities required to replay a policy."""

    schema_id: str
    feature_names: tuple[str, ...]
    manoeuvres: tuple[str, ...]
    recurrent_width: int
    action_transform_id: str
    energy_bundle_id: str
    physics_id: str
    continuous_profile_id: str
    rules_id: str
    pit_manifest_id: str
    scenario_id: str

    @classmethod
    def from_energy_bundle(
        cls,
        schema: PolicySchema,
        energy_bundle: EnergyBundleCompatibility,
        pit_manifest_id: str,
        scenario_id: str,
    ) -> "PolicyCheckpointMetadata":
        """Bind one schema to its required replay world."""
        if not energy_bundle.admitted:
            raise ValueError("policy checkpoint requires an admitted energy bundle")
        return cls(
            schema.schema_id,
            schema.feature_names,
            tuple(value.value for value in schema.manoeuvres),
            schema.recurrent_width,
            schema.action_transform_id,
            energy_bundle.bundle_id,
            energy_bundle.physics_id,
            energy_bundle.continuous_profile_id,
            energy_bundle.rules_id,
            pit_manifest_id,
            scenario_id,
        )


def save_policy_checkpoint(path: Path, model: RecurrentActorCritic, metadata: PolicyCheckpointMetadata) -> None:
    """Save a state dict and primitive compatibility metadata."""
    torch.save({"state_dict": model.state_dict(), "metadata": asdict(metadata)}, path)


def load_policy_checkpoint(
    path: Path,
    model: RecurrentActorCritic,
    expected: PolicyCheckpointMetadata,
) -> PolicyCheckpointMetadata:
    """Load only a compatible state dict using restricted deserialization."""
    payload = torch.load(path, map_location="cpu", weights_only=True)
    metadata = PolicyCheckpointMetadata(**payload["metadata"])
    if metadata != expected:
        raise ValueError("policy checkpoint is not compatible with this schema and world")
    model.load_state_dict(payload["state_dict"])
    return metadata
