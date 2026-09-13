import pytest

from poweshift_backend.energy.allocator import DeploymentPrior, LapEnergyState, allocate_additive_power


def _prior() -> DeploymentPrior:
    return DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)


def test_full_deployment_adds_the_rated_motor_power_to_fitted_ice_power() -> None:
    result = allocate_additive_power(_prior(), LapEnergyState.full(_prior()), 40.0, 1.0, 0.0, 1.0, 6_000.0, 16_000.0, 1.0)
    assert result.ice_wheel_power_w == pytest.approx(240_000.0)
    assert result.motor_wheel_power_w == pytest.approx(350_000.0)
    assert result.total_wheel_power_w == pytest.approx(590_000.0)
    assert result.axle_force_n == pytest.approx(14_750.0)


def test_deployment_fraction_scales_the_rated_motor_power() -> None:
    result = allocate_additive_power(_prior(), LapEnergyState.full(_prior()), 40.0, 1.0, 0.0, 0.4, 6_000.0, 16_000.0, 1.0)
    assert result.motor_wheel_power_w == pytest.approx(140_000.0)


def test_harvest_preserves_storage_and_obeys_the_per_lap_cap() -> None:
    prior = _prior()
    state = LapEnergyState(0.0, 4_950_000.0, 0.0, 0.0, 0.0)
    result = allocate_additive_power(prior, state, 40.0, 0.0, 1.0, 0.0, 10_000.0, 16_000.0, 1.0)
    assert result.state.harvested_this_lap_j == pytest.approx(5_000_000.0)
    assert result.state.stored_energy_j == pytest.approx(40_000.0)
    assert result.harvest_curtailed_j > 0.0


def test_braking_regen_scales_with_brake_force_and_is_capped_by_the_mgu_k_limit() -> None:
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 100_000.0)
    empty = LapEnergyState(0.0, 0.0, 0.0, 0.0, 0.0)

    weak_brake = allocate_additive_power(prior, empty, 40.0, 0.0, 1.0, 0.0, 10_000.0, 2_000.0, 1.0)
    strong_brake = allocate_additive_power(prior, empty, 40.0, 0.0, 1.0, 0.0, 10_000.0, 5_000.0, 1.0)
    assert strong_brake.state.stored_energy_j > weak_brake.state.stored_energy_j

    at_the_limit = allocate_additive_power(prior, empty, 40.0, 0.0, 1.0, 0.0, 10_000.0, 5_000.0, 1.0)
    past_the_limit = allocate_additive_power(prior, empty, 40.0, 0.0, 1.0, 0.0, 10_000.0, 10_000.0, 1.0)
    assert at_the_limit.state.stored_energy_j == pytest.approx(past_the_limit.state.stored_energy_j)
    assert at_the_limit.state.stored_energy_j == pytest.approx(prior.maximum_electric_power_w * prior.harvest_efficiency)
