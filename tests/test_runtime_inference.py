from pathlib import Path

import torch

from poweshift_backend.contracts.action import Manoeuvre
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.contracts.runtime import ObservationFrame
from poweshift_backend.policy.checkpoint import PolicyCheckpointMetadata, save_policy_checkpoint
from poweshift_backend.policy.model import RecurrentActorCritic
from poweshift_backend.policy.schema import PolicySchema
from poweshift_backend.recommendations.frame import build_recommendation
from poweshift_backend.runtime.inference import ResidentPolicy


def _resident(tmp_path: Path, clock) -> ResidentPolicy:
    schema = PolicySchema("schema-a", ("speed_ms", "stored_energy_j"), tuple(Manoeuvre), 3, "beta-v1")
    bundle = EnergyBundleCompatibility(
        "bundle-a", True, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a"
    )
    model = RecurrentActorCritic(schema)
    for parameter in model.parameters():
        torch.nn.init.zeros_(parameter)
    with torch.no_grad():
        model.manoeuvre_head.bias[1] = 1.0
    checkpoint = tmp_path / "checkpoint.pt"
    metadata = PolicyCheckpointMetadata.from_energy_bundle(schema, bundle, "pit-a", "scenario-a")
    save_policy_checkpoint(checkpoint, model, metadata)
    return ResidentPolicy(checkpoint, schema, bundle, "pit-a", "route-a", "scenario-a", clock_ns=clock)


def _frame(sequence: int = 0) -> ObservationFrame:
    return ObservationFrame(
        sequence=sequence,
        observed_at_s=float(sequence),
        values=(20.0, 4_000_000.0),
        feature_mask=(True, True),
        action_mask=(True, True, False, True),
        deployment_available=True,
        news_prior_ids=(),
    )


def test_resident_policy_selects_a_deterministic_compatible_action(tmp_path: Path) -> None:
    clock = iter((100, 110)).__next__
    resident = _resident(tmp_path, clock)

    result = resident.infer("run-a", "request-0", _frame(), deadline_ns=120)

    assert result.status == "accepted"
    assert result.action.manoeuvre is Manoeuvre.ATTACK
    assert result.action.deployment_fraction == 0.5
    assert result.memory_version == 1
    assert resident.memory_version == 1
    assert result.policy_id == "schema-a"
    assert result.energy_bundle_id == "bundle-a"
    assert result.route_id == "route-a"


def test_late_inference_falls_back_without_advancing_memory(tmp_path: Path) -> None:
    clock = iter((100, 130)).__next__
    resident = _resident(tmp_path, clock)

    result = resident.infer("run-a", "request-0", _frame(), deadline_ns=120)

    assert result.status == "fallback"
    assert result.action.manoeuvre is Manoeuvre.HOLD
    assert result.action.deployment_fraction == 0.0
    assert result.binding_reasons == ("INFERENCE_DEADLINE",)
    assert result.memory_version == 0
    assert resident.memory_version == 0


def test_recommendation_exposes_forecast_not_realised_delivery(tmp_path: Path) -> None:
    clock = iter((100, 110)).__next__
    resident = _resident(tmp_path, clock)
    result = resident.infer("run-a", "request-0", _frame(), deadline_ns=120)

    recommendation = build_recommendation(result, expires_after_ns=200)

    assert recommendation.sequence == 0
    assert recommendation.intent == "attack"
    assert recommendation.requested_power_w is None
    assert recommendation.reachable_power_w is None
    assert recommendation.retrospective is True
    assert recommendation.route_id == "route-a"
    assert recommendation.expires_monotonic_ns == 310
