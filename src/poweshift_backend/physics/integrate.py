"""Fixed-step float64 RK4 integration with explicit event ordering."""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from poweshift_backend.physics.state import MechanicsState, StateRate


@dataclass(frozen=True)
class IntegrationConfig:
    """Configured fixed step and precedence for simultaneous events."""

    step_s: float
    event_tie_order: tuple[str, ...]
    event_time_tolerance_s: float = 1e-12

    def __post_init__(self) -> None:
        if self.step_s <= 0.0:
            raise ValueError("integration step must be positive")
        if len(set(self.event_tie_order)) != len(self.event_tie_order):
            raise ValueError("event tie order must not repeat a kind")
        if self.event_time_tolerance_s < 0.0:
            raise ValueError("event time tolerance cannot be negative")


@dataclass(frozen=True)
class IntegrationEvent:
    """A state transition applied exactly at one configured time."""

    time_s: float
    kind: str
    apply: Callable[[MechanicsState], MechanicsState]


class IntegrationInfeasible(ValueError):
    """Raised when integration reaches an infeasible state or event sequence."""


def rk4_step(
    state: MechanicsState,
    step_s: float,
    derivative: Callable[[MechanicsState], StateRate],
) -> MechanicsState:
    """Advance one state using a fixed float64 RK4 step."""
    if step_s <= 0.0:
        raise ValueError("RK4 step must be positive")
    try:
        k1 = derivative(state)
        k2 = derivative(_advance(state, k1, step_s * 0.5))
        k3 = derivative(_advance(state, k2, step_s * 0.5))
        k4 = derivative(_advance(state, k3, step_s))
        rate = StateRate(
            speed_ms2=(k1.speed_ms2 + 2.0 * k2.speed_ms2 + 2.0 * k3.speed_ms2 + k4.speed_ms2) / 6.0,
            distance_ms=(k1.distance_ms + 2.0 * k2.distance_ms + 2.0 * k3.distance_ms + k4.distance_ms) / 6.0,
            progress_ms=(k1.progress_ms + 2.0 * k2.progress_ms + 2.0 * k3.progress_ms + k4.progress_ms) / 6.0,
            fuel_kg_s=(k1.fuel_kg_s + 2.0 * k2.fuel_kg_s + 2.0 * k3.fuel_kg_s + k4.fuel_kg_s) / 6.0,
        )
        return _advance(state, rate, step_s)
    except ValueError as error:
        raise IntegrationInfeasible(str(error)) from error


def integrate(
    initial_state: MechanicsState,
    end_time_s: float,
    derivative: Callable[[MechanicsState], StateRate],
    config: IntegrationConfig,
    events: tuple[IntegrationEvent, ...] = (),
) -> tuple[MechanicsState, ...]:
    """Advance through fixed steps while splitting each configured event time."""
    if end_time_s < initial_state.time_s:
        raise ValueError("end time precedes initial state")
    event_queue = _ordered_events(events, config)
    if any(event.time_s < initial_state.time_s or event.time_s > end_time_s for event in event_queue):
        raise ValueError("events must lie inside the integration interval")
    states = [initial_state]
    state = initial_state
    index = 0
    while index < len(event_queue) and np.isclose(
        event_queue[index].time_s, state.time_s, rtol=0.0, atol=config.event_time_tolerance_s
    ):
        state = _apply_event(event_queue[index], state)
        states.append(state)
        index += 1
    while state.time_s < end_time_s:
        next_event = event_queue[index].time_s if index < len(event_queue) else end_time_s
        target = min(state.time_s + config.step_s, next_event, end_time_s)
        if target <= state.time_s:
            raise IntegrationInfeasible("integration could not advance to its next event")
        state = rk4_step(state, target - state.time_s, derivative)
        states.append(state)
        while index < len(event_queue) and np.isclose(
            event_queue[index].time_s, state.time_s, rtol=0.0, atol=config.event_time_tolerance_s
        ):
            state = _apply_event(event_queue[index], state)
            states.append(state)
            index += 1
    return tuple(states)


def _advance(state: MechanicsState, rate: StateRate, step_s: float) -> MechanicsState:
    return MechanicsState(
        time_s=float(np.float64(state.time_s) + np.float64(step_s)),
        speed_ms=float(np.float64(state.speed_ms) + np.float64(rate.speed_ms2) * np.float64(step_s)),
        distance_m=float(np.float64(state.distance_m) + np.float64(rate.distance_ms) * np.float64(step_s)),
        progress_m=float(np.float64(state.progress_m) + np.float64(rate.progress_ms) * np.float64(step_s)),
        fuel_mass_kg=float(np.float64(state.fuel_mass_kg) + np.float64(rate.fuel_kg_s) * np.float64(step_s)),
    )


def _ordered_events(events: tuple[IntegrationEvent, ...], config: IntegrationConfig) -> tuple[IntegrationEvent, ...]:
    precedence = {kind: index for index, kind in enumerate(config.event_tie_order)}
    unknown = {event.kind for event in events}.difference(precedence)
    if unknown:
        raise ValueError("every event kind needs configured tie precedence")
    return tuple(sorted(events, key=lambda event: (event.time_s, precedence[event.kind])))


def _apply_event(event: IntegrationEvent, state: MechanicsState) -> MechanicsState:
    updated = event.apply(state)
    if updated.time_s != state.time_s:
        raise IntegrationInfeasible("an event cannot change integration time")
    return updated
