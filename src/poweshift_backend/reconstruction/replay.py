"""Replay frozen effective profiles without bridging unavailable gaps."""

from dataclasses import dataclass, replace

import numpy as np

from poweshift_backend.driver.controller import DriverDemand, DriverMode, ForecastController, KnownInputController
from poweshift_backend.energy.accounting import AccountingConfig
from poweshift_backend.energy.integration import CoupledEnergyState, EnergyStage, integrate_energy_stages
from poweshift_backend.physics.forces import mechanics_derivative
from poweshift_backend.physics.integrate import integrate
from poweshift_backend.physics.state import MechanicsState, RoadInput
from poweshift_backend.reconstruction.baseline import FittedBaseline
from poweshift_backend.reconstruction.inputs import Phase3Inputs, TelemetryChunk


@dataclass(frozen=True)
class ReplayChunk:
    """One replayed observed chunk with its input boundary label."""

    session_key: str
    entry: str
    run_id: str
    chunk_index: int
    mode: DriverMode
    time_s: np.ndarray
    observed_speed_ms: np.ndarray
    predicted_speed_ms: np.ndarray
    regime: np.ndarray
    anchor: str
    exclusion: str | None = None


@dataclass(frozen=True)
class OfflineEnergyReplay:
    """Separately selected energy replay that cannot enable runtime."""

    mode: str
    states: tuple[CoupledEnergyState, ...]
    accounting_evidence_id: str
    runtime_enabled: bool = False


def replay_offline_energy(
    initial: CoupledEnergyState,
    stages: tuple[EnergyStage, ...],
    config: AccountingConfig,
) -> OfflineEnergyReplay:
    """Run source-stage accounting outside the active reconstruction path."""
    return OfflineEnergyReplay("offline_energy", integrate_energy_stages(initial, stages, config), config.evidence_id)


def replay_final_evaluation(
    inputs: Phase3Inputs, baseline: FittedBaseline, mode: DriverMode = DriverMode.KNOWN_INPUT, chunk_budget: int = 4
) -> tuple[ReplayChunk, ...]:
    """Replay held-out chunks while refusing to invent an unobserved bridge."""
    chunks = _moving_run_chunks(inputs.chunks, chunk_budget)
    if chunk_budget < 1:
        raise ValueError("held-out chunk budget must be positive")
    results = []
    previous: tuple[TelemetryChunk, MechanicsState] | None = None
    continuations = set(inputs.continuations)
    forecast_prefix = None
    if mode is DriverMode.FORECAST and chunks:
        forecast_prefix = DriverDemand(
            float(np.clip(chunks[0].controls["throttle_pct"][0] / 100.0, 0.0, 1.0)),
            float(np.clip(chunks[0].controls["brake"][0], 0.0, 1.0)),
            0.5,
            DriverMode.FORECAST,
        )
    for chunk in chunks:
        state = None
        anchor = "observed_chunk_anchor"
        if previous is not None and is_verified_continuation(
            previous[0].session_key,
            previous[0].entry,
            previous[0].run_id,
            previous[0].chunk_index,
            chunk.chunk_index,
            continuations,
        ):
            state = _bridge_verified_gap(previous[0], previous[1], chunk, baseline, mode, forecast_prefix)
            anchor = "carried_verified_state_with_last_demand"
        result, final_state = replay_chunk(
            chunk, baseline, mode, initial_state=state, anchor=anchor, forecast_prefix=forecast_prefix
        )
        results.append(result)
        previous = (chunk, final_state) if final_state is not None else None
    return tuple(results)


def replay_chunk(
    chunk: TelemetryChunk,
    baseline: FittedBaseline,
    mode: DriverMode,
    *,
    initial_state: MechanicsState | None = None,
    anchor: str = "observed_chunk_anchor",
    forecast_prefix: DriverDemand | None = None,
) -> tuple[ReplayChunk, MechanicsState | None]:
    """Replay one recorded interval with known controls or a frozen prefix demand."""
    if len(chunk.time_s) < 2:
        return _excluded(chunk, mode, anchor, "chunk has fewer than two observations"), None
    required = ("speed_ms", "throttle_pct", "brake") if mode is DriverMode.KNOWN_INPUT else ("speed_ms",)
    if not all(np.all(chunk.valid[name]) for name in required):
        return _excluded(chunk, mode, anchor, "chunk has invalid motion controls"), None
    if mode is DriverMode.FORECAST and (not chunk.valid["throttle_pct"][0] or not chunk.valid["brake"][0]):
        return _excluded(chunk, mode, anchor, "chunk lacks a declared forecast prefix"), None
    if initial_state is None:
        state = MechanicsState(chunk.time_s[0], chunk.speed_ms[0], 0.0, 0.0, 30.0)
    elif not np.isclose(initial_state.time_s, chunk.time_s[0], rtol=0.0, atol=1e-12):
        return _excluded(chunk, mode, anchor, "unobserved gap cannot be bridged"), None
    else:
        state = initial_state
    controller = _controller(chunk, mode, forecast_prefix)
    road = RoadInput(0.0, 1.0)

    def derivative(current: MechanicsState):
        return mechanics_derivative(
            current,
            controller.demand(current.time_s),
            road,
            baseline.runtime.mass,
            baseline.runtime.geometry,
            baseline.runtime.forces,
            baseline.runtime.tyre,
            baseline.runtime.solve_config,
        )

    predicted = [state.speed_ms]
    try:
        for end_time_s in chunk.time_s[1:]:
            state = integrate(state, float(end_time_s), derivative, baseline.runtime.integration)[-1]
            predicted.append(state.speed_ms)
    except ValueError as error:
        length = len(predicted)
        return (
            ReplayChunk(
                chunk.session_key,
                chunk.entry,
                chunk.run_id,
                chunk.chunk_index,
                mode,
                chunk.time_s[:length],
                chunk.speed_ms[:length],
                np.array(predicted, dtype=np.float64),
                _regimes(chunk)[:length],
                anchor,
                str(error),
            ),
            None,
        )
    return (
        ReplayChunk(
            chunk.session_key,
            chunk.entry,
            chunk.run_id,
            chunk.chunk_index,
            mode,
            chunk.time_s,
            chunk.speed_ms,
            np.array(predicted, dtype=np.float64),
            _regimes(chunk),
            anchor,
        ),
        state,
    )


def replay_with_step(chunk: TelemetryChunk, baseline: FittedBaseline, step_s: float) -> ReplayChunk:
    """Replay a chunk at a specified step for convergence reporting."""
    runtime = replace(baseline.runtime, integration=replace(baseline.runtime.integration, step_s=step_s))
    altered = replace(baseline, runtime=runtime)
    return replay_chunk(chunk, altered, DriverMode.KNOWN_INPUT)[0]


def _controller(chunk: TelemetryChunk, mode: DriverMode, forecast_prefix: DriverDemand | None = None):
    if mode is DriverMode.KNOWN_INPUT:
        throttle = np.clip(chunk.controls["throttle_pct"] / 100.0, 0.0, 1.0)
        brake = np.clip(chunk.controls["brake"], 0.0, 1.0)
        return KnownInputController(chunk.time_s, throttle, brake, np.full(len(chunk.time_s), 0.5))
    if forecast_prefix is not None:
        return ForecastController(forecast_prefix)
    return ForecastController(
        DriverDemand(
            float(np.clip(chunk.controls["throttle_pct"][0] / 100.0, 0.0, 1.0)),
            float(np.clip(chunk.controls["brake"][0], 0.0, 1.0)),
            0.5,
            DriverMode.FORECAST,
        )
    )


def is_verified_continuation(
    session_key: str, entry: str, run_id: str, previous_chunk_index: int, current_chunk_index: int, continuations: set[tuple[str, str, str, int, int]]
) -> bool:
    """Return whether admission explicitly verified this chronological chunk link."""
    return (session_key, entry, run_id, previous_chunk_index, current_chunk_index) in continuations


def _moving_run_chunks(chunks: tuple[TelemetryChunk, ...], budget: int) -> list[TelemetryChunk]:
    moving = [
        chunk
        for chunk in chunks
        if chunk.split == "final_evaluation" and len(chunk.speed_ms) > 1 and np.any(np.diff(chunk.speed_ms) != 0.0)
    ]
    by_run: dict[tuple[str, str, str], list[TelemetryChunk]] = {}
    for chunk in moving:
        by_run.setdefault((chunk.session_key, chunk.entry, chunk.run_id), []).append(chunk)
    if not by_run:
        return []
    selected = max(by_run.values(), key=lambda run: (len(run), run[0].session_key, run[0].run_id))
    return sorted(selected, key=lambda chunk: chunk.chunk_index)[:budget]


def _bridge_verified_gap(
    previous: TelemetryChunk,
    state: MechanicsState,
    current: TelemetryChunk,
    baseline: FittedBaseline,
    mode: DriverMode,
    forecast_prefix: DriverDemand | None,
) -> MechanicsState:
    demand = forecast_prefix
    if mode is DriverMode.KNOWN_INPUT:
        demand = DriverDemand(
            float(np.clip(previous.controls["throttle_pct"][-1] / 100.0, 0.0, 1.0)),
            float(np.clip(previous.controls["brake"][-1], 0.0, 1.0)),
            0.5,
            DriverMode.FORECAST,
        )
    if demand is None:
        raise ValueError("forecast replay needs a prefix demand")
    controller = ForecastController(demand)
    road = RoadInput(0.0, 1.0)

    def derivative(current_state: MechanicsState):
        return mechanics_derivative(
            current_state,
            controller.demand(current_state.time_s),
            road,
            baseline.runtime.mass,
            baseline.runtime.geometry,
            baseline.runtime.forces,
            baseline.runtime.tyre,
            baseline.runtime.solve_config,
        )

    return integrate(state, float(current.time_s[0]), derivative, baseline.runtime.integration)[-1]


def _regimes(chunk: TelemetryChunk) -> np.ndarray:
    throttle = chunk.controls["throttle_pct"]
    brake = chunk.controls["brake"]
    return np.where(brake > 0.0, "braking", np.where(throttle > 0.0, "propulsion", "coast"))


def _excluded(chunk: TelemetryChunk, mode: DriverMode, anchor: str, exclusion: str) -> ReplayChunk:
    return ReplayChunk(
        chunk.session_key,
        chunk.entry,
        chunk.run_id,
        chunk.chunk_index,
        mode,
        chunk.time_s,
        chunk.speed_ms,
        np.array([], dtype=np.float64),
        _regimes(chunk),
        anchor,
        exclusion,
    )
