"""Frozen inputs for physical policy training."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Literal


@dataclass(frozen=True)
class PpoRunConfig:
    """All numerical settings used by one PPO run."""

    learning_rate: float
    discount: float
    gae_lambda: float
    clip_ratio: float
    value_weight: float
    entropy_weight: float
    maximum_gradient_norm: float

    def __post_init__(self) -> None:
        values = tuple(asdict(self).values())
        if not all(isfinite(value) for value in values):
            raise ValueError("PPO settings must be finite")
        if self.learning_rate <= 0.0 or self.maximum_gradient_norm <= 0.0:
            raise ValueError("PPO learning rate and gradient norm must be positive")
        if not 0.0 <= self.discount <= 1.0 or not 0.0 <= self.gae_lambda <= 1.0:
            raise ValueError("PPO discounts must be between zero and one")
        if self.clip_ratio <= 0.0 or min(self.value_weight, self.entropy_weight) < 0.0:
            raise ValueError("PPO loss settings are invalid")


def config_sha256(config: PpoRunConfig) -> str:
    """Hash one PPO configuration canonically."""
    payload = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class PolicyTrainingManifest:
    """Frozen physical, source and evaluation boundary for one run."""

    run_id: str
    mode: Literal["preflight", "smoke"]
    seed: int
    updates: int
    source_partition: Literal["training"]
    training_source_sha256: str
    code_revision: str
    config_sha256: str
    schema_id: str
    energy_bundle_id: str
    continuous_profile_id: str
    physics_id: str
    rules_id: str
    pit_manifest_id: str
    route_id: str
    scenario_id: str
    held_out_measure_id: str
    acceptance_criteria_id: str
    config: PpoRunConfig

    def __post_init__(self) -> None:
        identities = (
            self.run_id, self.code_revision, self.schema_id, self.energy_bundle_id,
            self.continuous_profile_id, self.physics_id, self.rules_id,
            self.pit_manifest_id, self.route_id, self.scenario_id,
            self.held_out_measure_id, self.acceptance_criteria_id,
        )
        if not all(identities):
            raise ValueError("policy training identities are incomplete")
        if self.seed < 0 or len(self.training_source_sha256) != 64:
            raise ValueError("policy training source binding is invalid")
        try:
            int(self.training_source_sha256, 16)
        except ValueError as error:
            raise ValueError("policy training source binding is invalid") from error
        if self.config_sha256 != config_sha256(self.config):
            raise ValueError("policy training configuration hash is invalid")
