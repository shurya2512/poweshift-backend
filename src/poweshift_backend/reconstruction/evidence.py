"""Summarise held-out replay errors, exclusions and numerical checks."""

import numpy as np

from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.physics.reference_solver import solve_reference
from poweshift_backend.physics.state import MechanicsState, RoadInput
from poweshift_backend.reconstruction.baseline import FittedBaseline
from poweshift_backend.reconstruction.replay import ReplayChunk, replay_with_step


def build_energy_readiness(
    *,
    interface_stable: bool,
    phase4_training_artifact_id: str | None,
    continuous_profile_id: str | None,
    continuous_profile_admission_id: str | None,
    physics_id: str | None,
    response_evidence_id: str | None,
    accounting_evidence_id: str | None,
    rules_snapshot_id: str | None,
    numerical_compatible: bool,
    differentiable_compatible: bool,
) -> dict[str, object]:
    """Report exact missing gates without enabling runtime early."""
    gates = {
        "interface": interface_stable,
        "phase4_training_artifact": bool(phase4_training_artifact_id),
        "continuous_profile": bool(continuous_profile_id),
        "continuous_profile_admission": bool(continuous_profile_admission_id),
        "physics": bool(physics_id),
        "response_evidence": bool(response_evidence_id),
        "accounting_evidence": bool(accounting_evidence_id),
        "rules_snapshot": bool(rules_snapshot_id),
        "numerical_compatibility": numerical_compatible,
        "differentiable_compatibility": differentiable_compatible,
    }
    missing = tuple(name for name, ready in gates.items() if not ready)
    offline_gates = (
        interface_stable,
        bool(phase4_training_artifact_id),
        bool(physics_id),
        numerical_compatible,
        differentiable_compatible,
    )
    return {
        "offline_experiments_enabled": all(offline_gates),
        "runtime_enabled": not missing,
        "missing": missing,
        "phase4_training_artifact_id": phase4_training_artifact_id,
        "continuous_profile_id": continuous_profile_id,
        "continuous_profile_admission_id": continuous_profile_admission_id,
        "physics_id": physics_id,
        "response_evidence_id": response_evidence_id,
        "accounting_evidence_id": accounting_evidence_id,
        "rules_snapshot_id": rules_snapshot_id,
    }


def admit_energy_bundle(readiness: dict[str, object], *, bundle_id: str) -> EnergyBundleCompatibility:
    """Create a compatibility bundle only from complete readiness evidence."""
    if not readiness.get("runtime_enabled") or readiness.get("missing"):
        raise ValueError("energy bundle readiness has not passed")
    identifiers = (
        bundle_id,
        readiness.get("physics_id"),
        readiness.get("rules_snapshot_id"),
        readiness.get("response_evidence_id"),
        readiness.get("accounting_evidence_id"),
        readiness.get("continuous_profile_id"),
    )
    if not all(isinstance(value, str) and value for value in identifiers):
        raise ValueError("energy bundle readiness identifiers are incomplete")
    return EnergyBundleCompatibility(bundle_id, True, *identifiers[1:])


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
