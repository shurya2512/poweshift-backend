import pytest
import torch

from poweshift_backend.contracts.action import ActionMask, ActionRequest, DeliveredAction, Manoeuvre
from poweshift_backend.contracts.pits import FixedPitManifest, FixedPitSchedule, PitMappingMode, PitVisit
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.contracts.scenario import ScenarioSpec
from poweshift_backend.energy.state import EnergyState
from poweshift_backend.physics.state import MechanicsState
from poweshift_backend.policy.observation import AvailableContext, build_policy_observation
from poweshift_backend.policy.schema import PolicySchema
from poweshift_backend.simulation.ego import EgoState
from poweshift_backend.simulation.policy_env import PhysicalPolicyEnvironment
from poweshift_backend.simulation.replay_env import ReplayEnvironment


def _advance(mechanics, energy, request):
    return MechanicsState(mechanics.time_s + 1.0, mechanics.speed_ms, mechanics.distance_m + 1.0, mechanics.progress_m + 1.0, mechanics.fuel_mass_kg - 0.1), EnergyState(energy.stored_energy_j - 10.0 * request.deployment_fraction, energy.recharge_throughput_j, energy.discharge_throughput_j + 10.0 * request.deployment_fraction)


def _fixture():
    schema = PolicySchema("schema-a", ("speed_ms", "weather", "stored_energy_j"), tuple(Manoeuvre), 4, "beta-v1")
    ego = EgoState("ego-a", MechanicsState(0.0, 20.0, 0.0, 0.0, 10.0), EnergyState(500.0, 0.0, 0.0), "bundle-a")
    bundle = EnergyBundleCompatibility("bundle-a", True, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a")
    mask = ActionMask(frozenset({Manoeuvre.HOLD, Manoeuvre.ATTACK}), True)
    replay = ReplayEnvironment(ScenarioSpec("scenario-a", "route-a", 0.0, 2.0, 5, ()), ego, mask, bundle, FixedPitManifest("pit-a", "source-a", "a" * 64, ()), _advance)
    return schema, ego, mask, replay


def test_observation_masks_missing_or_future_context() -> None:
    schema, ego, _, _ = _fixture()
    values, mask, action_mask = build_policy_observation(ego, AvailableContext({"weather": 1.0, "allow_attack": 0.0}, frozenset({"weather", "allow_attack"}), 1.0), schema)
    assert torch.equal(values, torch.tensor([20.0, 0.0, 500.0]))
    assert torch.equal(mask, torch.tensor([True, False, True]))
    assert set(action_mask.manoeuvres) == set(schema.manoeuvres)


def test_environment_preserves_sampled_issued_and_delivered_actions() -> None:
    schema, _, _, replay = _fixture()
    context = AvailableContext({}, frozenset(), 0.0)
    def transform(_state, sampled, _mask):
        issued = ActionRequest(sampled.manoeuvre, min(sampled.deployment_fraction, 0.5))
        delivered = ActionRequest(sampled.manoeuvre, min(issued.deployment_fraction, 0.25))
        return DeliveredAction(issued, delivered, ("STORAGE_LIMIT",))
    env = PhysicalPolicyEnvironment(replay, schema, context, transform, lambda _sampled: -1.25, lambda before, after, _action: before.energy.stored_energy_j - after.energy.stored_energy_j)
    step = env.step(ActionRequest(Manoeuvre.ATTACK, 0.8))
    assert step.action.sampled.deployment_fraction == 0.8
    assert step.action.issued.deployment_fraction == 0.5
    assert step.action.delivered.deployment_fraction == 0.25
    assert step.action.sampled_joint_log_probability == -1.25
    assert replay.state.energy.stored_energy_j == 497.5
    assert step.reward == 2.5


def test_replay_loads_the_fixed_schedule_and_refuses_an_in_window_visit() -> None:
    _, ego, mask, _ = _fixture()
    bundle = EnergyBundleCompatibility("bundle-a", True, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a")
    schedule = FixedPitSchedule("schedule-a", PitMappingMode.LAP_RELATIVE_FIXED, (PitVisit(1, 1.0, 2.0, ("tyres",)),))
    with pytest.raises(ValueError, match="fixed pit visit"):
        ReplayEnvironment(ScenarioSpec("scenario-a", "route-a", 0.0, 3.0, 5, ()), ego, mask, bundle, FixedPitManifest("pit-a", "source-a", "a" * 64, ()), _advance, schedule)
