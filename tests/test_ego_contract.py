import pytest

from poweshift_backend.contracts.action import ActionMask, ActionRequest, Manoeuvre
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.energy.state import EnergyState
from poweshift_backend.physics.state import MechanicsState
from poweshift_backend.simulation.ego import EgoState, advance_ego


def _advance(mechanics: MechanicsState, energy: EnergyState, _: ActionRequest):
    return (
        MechanicsState(mechanics.time_s + 1.0, mechanics.speed_ms, mechanics.distance_m + mechanics.speed_ms, mechanics.progress_m + mechanics.speed_ms, mechanics.fuel_mass_kg),
        EnergyState(energy.stored_energy_j - 10.0, energy.recharge_throughput_j, energy.discharge_throughput_j + 10.0),
    )


def test_ego_uses_one_admitted_bundle_and_shared_advance_boundary() -> None:
    ego = EgoState("ego", MechanicsState(0.0, 20.0, 0.0, 0.0, 10.0), EnergyState(500.0, 0.0, 0.0), "bundle-a")
    bundle = EnergyBundleCompatibility("bundle-a", True, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a")
    mask = ActionMask(frozenset({Manoeuvre.HOLD}), True)

    updated = advance_ego(ego, ActionRequest(Manoeuvre.HOLD, 0.5), mask, bundle, _advance)

    assert updated.mechanics.time_s == 1.0
    assert updated.energy.stored_energy_j == 490.0
    with pytest.raises(ValueError, match="masked"):
        advance_ego(ego, ActionRequest(Manoeuvre.ATTACK, 0.5), mask, bundle, _advance)
    with pytest.raises(ValueError, match="admitted"):
        advance_ego(ego, ActionRequest(Manoeuvre.HOLD, 0.5), mask, EnergyBundleCompatibility("bundle-a", False, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a"), _advance)
