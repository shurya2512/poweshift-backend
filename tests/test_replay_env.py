import pytest

from poweshift_backend.contracts.action import ActionMask, ActionRequest, Manoeuvre
from poweshift_backend.contracts.pits import FixedPitManifest, PitEvent
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.contracts.scenario import ScenarioEvent, ScenarioSpec
from poweshift_backend.energy.state import EnergyState
from poweshift_backend.physics.state import MechanicsState
from poweshift_backend.simulation.ego import EgoState
from poweshift_backend.simulation.replay_env import ReplayEnvironment


def _advance(mechanics, energy, _):
    return (
        MechanicsState(mechanics.time_s + 1.0, mechanics.speed_ms, mechanics.distance_m + 1.0, mechanics.progress_m + 1.0, mechanics.fuel_mass_kg),
        energy,
    )


def _bundle() -> EnergyBundleCompatibility:
    return EnergyBundleCompatibility("bundle-a", True, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a")


def test_replay_distinguishes_termination_from_truncation_and_preserves_events() -> None:
    scenario = ScenarioSpec("scenario-a", "route-a", 0.0, 2.0, 5, ())
    ego = EgoState("ego", MechanicsState(0.0, 1.0, 0.0, 0.0, 10.0), EnergyState(500.0, 0.0, 0.0), "bundle-a")
    env = ReplayEnvironment(scenario, ego, ActionMask(frozenset({Manoeuvre.HOLD}), True), _bundle(), FixedPitManifest("pit-a", "source-a", "a" * 64, ()), _advance)

    first = env.step(ActionRequest(Manoeuvre.HOLD, 0.0))
    second = env.step(ActionRequest(Manoeuvre.HOLD, 0.0))

    assert first.terminated is False and first.truncated is False
    assert second.terminated is True and second.truncated is False
    assert tuple(record.kind for record in second.events) == ("scenario_end",)


def test_replay_refuses_a_pit_event_inside_a_no_pit_window() -> None:
    scenario = ScenarioSpec("scenario-a", "route-a", 0.0, 2.0, 5, ())
    ego = EgoState("ego", MechanicsState(0.0, 1.0, 0.0, 0.0, 10.0), EnergyState(500.0, 0.0, 0.0), "bundle-a")
    manifest = FixedPitManifest("pit-a", "source-a", "a" * 64, (PitEvent(1.0, "entry", "pit_entry"),))

    with pytest.raises(ValueError, match="pit event"):
        ReplayEnvironment(scenario, ego, ActionMask(frozenset({Manoeuvre.HOLD}), True), _bundle(), manifest, _advance)


def test_scenario_refuses_events_outside_its_chronological_window() -> None:
    with pytest.raises(ValueError, match="event"):
        ScenarioSpec("scenario-a", "route-a", 0.0, 2.0, 5, (ScenarioEvent(3.0, "late"),))
