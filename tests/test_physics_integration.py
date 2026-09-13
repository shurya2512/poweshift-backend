import pytest

from poweshift_backend.physics.integrate import IntegrationConfig, IntegrationEvent, integrate
from poweshift_backend.physics.state import MechanicsState, StateRate


def test_rk4_straight_line_matches_constant_acceleration() -> None:
    start = MechanicsState(0.0, 10.0, 0.0, 0.0, 0.0)
    states = integrate(
        start,
        2.0,
        lambda _: StateRate(3.0, 10.0, 10.0, 0.0),
        IntegrationConfig(step_s=0.3, event_tie_order=()),
    )

    assert states[-1].speed_ms == pytest.approx(16.0)
    assert states[-1].distance_m == pytest.approx(20.0)


def test_events_split_steps_in_declared_tie_order() -> None:
    start = MechanicsState(0.0, 1.0, 0.0, 0.0, 0.0)
    first = IntegrationEvent(
        0.25,
        "first",
        lambda state: MechanicsState(state.time_s, 2.0, state.distance_m, state.progress_m, state.fuel_mass_kg),
    )
    second = IntegrationEvent(
        0.25,
        "second",
        lambda state: MechanicsState(state.time_s, state.speed_ms + 3.0, state.distance_m, state.progress_m, state.fuel_mass_kg),
    )
    states = integrate(
        start,
        0.5,
        lambda state: StateRate(0.0, state.speed_ms, state.speed_ms, 0.0),
        IntegrationConfig(step_s=1.0, event_tie_order=("first", "second")),
        (second, first),
    )

    assert states[-1].speed_ms == 5.0
    assert states[-1].distance_m == 1.5
