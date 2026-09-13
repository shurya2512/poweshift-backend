import pytest

from poweshift_backend.physics.integrate import IntegrationConfig, IntegrationEvent, integrate
from poweshift_backend.physics.state import MechanicsState, StateRate


def test_event_tolerance_is_a_declared_integration_setting() -> None:
    event = IntegrationEvent(
        0.1,
        "boundary",
        lambda state: MechanicsState(state.time_s, state.speed_ms + 1.0, state.distance_m, state.progress_m, state.fuel_mass_kg),
    )

    states = integrate(
        MechanicsState(0.0, 1.0, 0.0, 0.0, 0.0),
        0.1,
        lambda _: StateRate(0.0, 0.0, 0.0, 0.0),
        IntegrationConfig(0.03, ("boundary",), event_time_tolerance_s=1e-6),
        (event,),
    )

    assert states[-1].speed_ms == pytest.approx(2.0)


def test_event_tolerance_changes_the_declared_boundary_grouping() -> None:
    event = IntegrationEvent(
        5e-7,
        "boundary",
        lambda state: MechanicsState(state.time_s, state.speed_ms + 1.0, state.distance_m, state.progress_m, state.fuel_mass_kg),
    )
    start = MechanicsState(0.0, 1.0, 0.0, 0.0, 0.0)
    derivative = lambda state: StateRate(0.0, state.speed_ms, state.speed_ms, 0.0)

    grouped = integrate(start, 0.1, derivative, IntegrationConfig(0.1, ("boundary",), 1e-6), (event,))
    separate = integrate(start, 0.1, derivative, IntegrationConfig(0.1, ("boundary",), 0.0), (event,))

    assert grouped[-1].distance_m > separate[-1].distance_m
