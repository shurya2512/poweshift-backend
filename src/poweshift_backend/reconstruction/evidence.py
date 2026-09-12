"""Summarise held-out replay errors, exclusions and numerical checks."""

import numpy as np

from poweshift_backend.physics.reference_solver import solve_reference
from poweshift_backend.physics.state import MechanicsState, RoadInput
from poweshift_backend.reconstruction.baseline import FittedBaseline
from poweshift_backend.reconstruction.replay import ReplayChunk, replay_with_step


def build_evidence(replays: tuple[ReplayChunk, ...], baseline: FittedBaseline) -> dict[str, object]:
    """Return actual held-out metrics grouped by entry and recorded regime."""
    grouped: dict[str, list[float]] = {}
    exclusions = []
    for replay in replays:
        if replay.exclusion is not None:
            exclusions.append(f"{replay.entry}/{replay.run_id}/{replay.chunk_index}: {replay.exclusion}")
        if not len(replay.predicted_speed_ms):
            continue
        error = replay.predicted_speed_ms - replay.observed_speed_ms
        for regime in ("propulsion", "coast", "braking"):
            mask = replay.regime == regime
            if mask.any():
                grouped.setdefault(f"{replay.entry}:{regime}", []).extend(error[mask].tolist())
    counts = {key: len(values) for key, values in sorted(grouped.items())}
    metrics = {
        key: {"speed_mae_ms": float(np.mean(np.abs(values))), "speed_rmse_ms": float(np.sqrt(np.mean(np.square(values))))}
        for key, values in sorted(grouped.items())
    }
    return {
        "counts_by_entry_regime": counts,
        "metrics_by_entry_regime": metrics,
        "exclusions": tuple(exclusions),
        "unsupported_components": baseline.missing_components,
        "numerical_diagnostics": _numerical_diagnostics(replays, baseline),
        "support": {
            "braking": "recorded controls only; effective force is assumed",
            "cornering": "missing because package observations have no aligned curvature",
            "forecast": "not scored here; known-input replay uses recorded controls",
        },
        "evaluated_chunks": len(replays),
    }


def _numerical_diagnostics(replays: tuple[ReplayChunk, ...], baseline: FittedBaseline) -> dict[str, float]:
    replay = next((item for item in replays if len(item.predicted_speed_ms) > 1), None)
    if replay is None:
        return {}
    from poweshift_backend.driver.controller import KnownInputController

    index = 1
    controller = KnownInputController(
        replay.time_s[: index + 1],
        np.full(index + 1, 0.0),
        np.full(index + 1, 0.0),
        np.full(index + 1, 0.5),
    )
    initial = MechanicsState(replay.time_s[0], replay.observed_speed_ms[0], 0.0, 0.0, 30.0)
    try:
        reference = solve_reference(initial, float(replay.time_s[index]), controller.demand, baseline.runtime, RoadInput(0.0, 1.0))
        coarse = replay_with_step_from_replay(replay, baseline, baseline.runtime.integration.step_s).predicted_speed_ms[index]
        refined = replay_with_step_from_replay(replay, baseline, baseline.runtime.integration.step_s * 0.5).predicted_speed_ms[index]
        return {
            "reference_solver_speed_difference_ms": float(abs(coarse - reference.speed_ms)),
            "refined_step_speed_difference_ms": float(abs(coarse - refined)),
        }
    except ValueError:
        return {}


def replay_with_step_from_replay(replay: ReplayChunk, baseline: FittedBaseline, step_s: float) -> ReplayChunk:
    """Use the replayed records to compare one fixed-step refinement."""
    from poweshift_backend.reconstruction.inputs import TelemetryChunk

    controls = {"throttle_pct": np.zeros(len(replay.time_s)), "brake": np.zeros(len(replay.time_s)), "n_gear": np.ones(len(replay.time_s))}
    valid = {name: np.ones(len(replay.time_s), dtype=np.bool_) for name in ("speed_ms", "throttle_pct", "brake", "n_gear")}
    chunk = TelemetryChunk("numerical", "numerical", "numerical", 0, "final_evaluation", replay.time_s, replay.observed_speed_ms, controls, valid, {}, ())
    return replay_with_step(chunk, baseline, step_s)
