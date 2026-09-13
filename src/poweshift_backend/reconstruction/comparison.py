"""Numerical readiness selection for a bounded, reproducible comparison."""

from dataclasses import dataclass, replace
from math import isfinite

import numpy as np

from poweshift_backend.contracts.representation import NumericalPolicy
from poweshift_backend.driver.controller import KnownInputController
from poweshift_backend.physics.reference_solver import solve_reference
from poweshift_backend.physics.state import MechanicsState, RoadInput
from poweshift_backend.reconstruction.baseline import FittedBaseline, runtime_from_profile
from poweshift_backend.reconstruction.inputs import Phase3Inputs, TelemetryChunk
from poweshift_backend.reconstruction.replay import replay_with_step


@dataclass(frozen=True)
class NumericalCheck:
    """Independent reference and refined-step errors for one controlled regime."""

    policy: NumericalPolicy
    regime: str
    reference_difference_ms: float
    refined_step_difference_ms: float
    stricter_axle_difference_ms: float = 0.0


_REQUIRED_REGIMES = tuple(
    f"{split}:{regime}"
    for split in ("training", "selection")
    for regime in ("propulsion", "braking", "coast")
)


def select_numerical_policy(
    candidates: tuple[NumericalPolicy, ...], checks: tuple[NumericalCheck, ...], *, maximum_difference_ms: float
) -> NumericalPolicy:
    """Choose the first predeclared policy that passes every required controlled regime."""
    if maximum_difference_ms <= 0.0:
        raise ValueError("numerical maximum difference must be positive")
    keys = [(check.policy, check.regime) for check in checks]
    if len(set(keys)) != len(keys):
        raise ValueError("conflicting duplicate numerical regime checks")
    if any(
        not all(isfinite(value) and value >= 0.0 for value in (
            check.reference_difference_ms,
            check.refined_step_difference_ms,
            check.stricter_axle_difference_ms,
        ))
        for check in checks
    ):
        raise ValueError("numerical check differences must be finite and nonnegative")
    for policy in candidates:
        policy_checks = {check.regime: check for check in checks if check.policy == policy}
        missing = set(_REQUIRED_REGIMES).difference(policy_checks)
        if missing:
            continue
        if all(
            check.reference_difference_ms <= maximum_difference_ms
            and check.refined_step_difference_ms <= maximum_difference_ms
            and check.stricter_axle_difference_ms <= maximum_difference_ms
            for check in policy_checks.values()
        ):
            return policy
    available = {check.regime for check in checks}
    missing = set(_REQUIRED_REGIMES).difference(available)
    if missing:
        raise ValueError(f"numerical readiness missing controlled regimes: {sorted(missing)}")
    raise ValueError("no predeclared numerical policy passed readiness")


def measure_numerical_checks(
    inputs: Phase3Inputs, baseline: FittedBaseline, policies: tuple[NumericalPolicy, ...]
) -> tuple[NumericalCheck, ...]:
    """Measure controlled real telemetry checks before a policy is frozen for scoring."""
    chunks: dict[str, list[TelemetryChunk]] = {}
    for chunk in inputs.chunks:
        for controlled in _controlled_intervals(chunk):
            chunks.setdefault(_controlled_regime(controlled), []).append(controlled)
    needed = set(_REQUIRED_REGIMES)
    missing = needed.difference(chunks)
    if missing:
        raise ValueError(f"numerical readiness missing controlled regimes: {sorted(missing)}")
    checks = []
    for policy in policies:
        runtime = runtime_from_profile(baseline.profile, policy)
        candidate = replace(baseline, runtime=runtime)
        for regime in _REQUIRED_REGIMES:
            measured = None
            last_error = None
            for chunk in chunks[regime]:
                controller = KnownInputController(chunk.time_s, np.clip(chunk.controls["throttle_pct"] / 100.0, 0.0, 1.0), np.clip(chunk.controls["brake"], 0.0, 1.0), np.full(len(chunk.time_s), 0.5))
                initial = MechanicsState(chunk.time_s[0], chunk.speed_ms[0], 0.0, 0.0, 30.0)
                try:
                    reference = solve_reference(initial, float(chunk.time_s[-1]), controller.demand, runtime, RoadInput(0.0, 1.0))
                    coarse = replay_with_step(chunk, candidate, policy.step_s)
                    refined = replay_with_step(chunk, candidate, policy.step_s * 0.5)
                    stricter = replace(runtime, solve_config=replace(runtime.solve_config, tolerance_n=policy.axle_tolerance_n * 0.1))
                    strict_replay = replay_with_step(chunk, replace(candidate, runtime=stricter), policy.step_s)
                    if any(replay.exclusion is not None or not len(replay.predicted_speed_ms) for replay in (coarse, refined, strict_replay)):
                        raise ValueError("replay is infeasible")
                    measured = (reference, coarse, refined, strict_replay)
                    break
                except ValueError as error:
                    last_error = error
            if measured is None:
                raise ValueError(f"numerical readiness cannot evaluate {regime}: {last_error}")
            reference, coarse, refined, strict_replay = measured
            checks.append(
                NumericalCheck(
                    policy,
                    regime,
                    float(abs(coarse.predicted_speed_ms[-1] - reference.speed_ms)),
                    float(abs(coarse.predicted_speed_ms[-1] - refined.predicted_speed_ms[-1])),
                    float(abs(coarse.predicted_speed_ms[-1] - strict_replay.predicted_speed_ms[-1])),
                )
            )
    return tuple(checks)


def _controlled_regime(chunk: TelemetryChunk) -> str | None:
    if chunk.split not in ("training", "selection") or len(chunk.time_s) < 2:
        return None
    valid = chunk.valid["speed_ms"] & chunk.valid["throttle_pct"] & chunk.valid["brake"]
    if not valid.all():
        return None
    throttle = float(chunk.controls["throttle_pct"][0])
    brake = float(chunk.controls["brake"][0])
    regime = "braking" if brake > 0.0 else "propulsion" if throttle > 0.0 else "coast"
    return f"{chunk.split}:{regime}"


def _controlled_intervals(chunk: TelemetryChunk) -> tuple[TelemetryChunk, ...]:
    """Take one adjacent measured interval whose demand regime does not change."""
    if chunk.split not in ("training", "selection") or len(chunk.time_s) < 2:
        return ()
    intervals = []
    for index in range(len(chunk.time_s) - 1):
        left = _sample_regime(chunk, index)
        right = _sample_regime(chunk, index + 1)
        if left is None or left != right:
            continue
        intervals.append(TelemetryChunk(
            chunk.session_key,
            chunk.entry,
            chunk.run_id,
            chunk.chunk_index,
            chunk.split,
            chunk.time_s[index : index + 2],
            chunk.speed_ms[index : index + 2],
            {name: values[index : index + 2] for name, values in chunk.controls.items()},
            {name: values[index : index + 2] for name, values in chunk.valid.items()},
            chunk.tyre,
            chunk.source_rows[index : index + 2],
        ))
    return tuple(intervals)


def _sample_regime(chunk: TelemetryChunk, index: int) -> str | None:
    if not all(chunk.valid[name][index] for name in ("speed_ms", "throttle_pct", "brake")):
        return None
    if chunk.controls["brake"][index] > 0.0:
        return "braking"
    if chunk.controls["throttle_pct"][index] > 0.0:
        return "propulsion"
    return "coast"
