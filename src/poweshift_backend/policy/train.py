"""Physical policy training gate."""

from dataclasses import dataclass

from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.contracts.policy_training import PolicyTrainingManifest


@dataclass(frozen=True)
class PhysicalTrainingGate:
    """Frozen inputs required before physical PPO may run."""

    energy_bundle: EnergyBundleCompatibility
    continuous_profile_id: str
    held_out_measure_id: str
    acceptance_criteria_id: str


def require_physical_training_ready(gate: PhysicalTrainingGate) -> PhysicalTrainingGate:
    """Refuse PPO until every physical and evaluation input is admitted."""
    if not gate.energy_bundle.admitted:
        raise ValueError("physical PPO requires an admitted energy bundle")
    if gate.energy_bundle.continuous_profile_id != gate.continuous_profile_id:
        raise ValueError("physical PPO profile does not match its energy bundle")
    if not all((gate.continuous_profile_id, gate.held_out_measure_id, gate.acceptance_criteria_id)):
        raise ValueError("physical PPO requires a supported profile and frozen evaluation")
    return gate


def require_policy_training_ready(
    manifest: PolicyTrainingManifest,
    gate: PhysicalTrainingGate,
) -> PolicyTrainingManifest:
    """Validate the complete boundary before creating runtime objects."""
    require_physical_training_ready(gate)
    required_updates = 1 if manifest.mode == "preflight" else 100 if manifest.mode == "smoke" else None
    if required_updates is None or manifest.updates != required_updates:
        detail = "one update" if manifest.mode == "preflight" else "100 updates"
        raise ValueError(f"{manifest.mode} requires exactly {detail}")
    if manifest.source_partition != "training":
        raise ValueError("physical PPO requires the training partition")
    bundle = gate.energy_bundle
    actual = (manifest.energy_bundle_id, manifest.continuous_profile_id, manifest.physics_id, manifest.rules_id)
    expected = (bundle.bundle_id, bundle.continuous_profile_id, bundle.physics_id, bundle.rules_id)
    if actual != expected:
        raise ValueError("policy training identities do not match the admitted energy bundle")
    if manifest.held_out_measure_id != gate.held_out_measure_id or manifest.acceptance_criteria_id != gate.acceptance_criteria_id:
        raise ValueError("policy training evaluation identities do not match the physical gate")
    return manifest
