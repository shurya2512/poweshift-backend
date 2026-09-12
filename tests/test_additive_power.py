import pytest

from poweshift_backend.energy.allocator import DeploymentPrior, LapEnergyState, allocate_additive_power


def _prior() -> DeploymentPrior:
    return DeploymentPrior(0.2, 5_000_000.0, 5_000_000.0, 0.95, 0.8)


def test_boost_adds_a_percentage_to_fitted_ice_power() -> None:
    result = allocate_additive_power(_prior(), LapEnergyState.full(_prior()), 40.0, 1.0, 0.0, 1.0, 6_000.0, 1.0)
    assert result.ice_wheel_power_w == pytest.approx(240_000.0)
    assert result.motor_wheel_power_w == pytest.approx(48_000.0)
    assert result.total_wheel_power_w == pytest.approx(288_000.0)
    assert result.axle_force_n == pytest.approx(7_200.0)


def test_harvest_preserves_storage_and_obeys_the_per_lap_cap() -> None:
    prior = _prior()
    state = LapEnergyState(0.0, 4_950_000.0, 0.0, 0.0, 0.0)
    result = allocate_additive_power(prior, state, 40.0, 0.0, 1.0, 0.0, 10_000.0, 1.0)
    assert result.state.harvested_this_lap_j == pytest.approx(5_000_000.0)
    assert result.state.stored_energy_j == pytest.approx(40_000.0)
    assert result.harvest_curtailed_j > 0.0
