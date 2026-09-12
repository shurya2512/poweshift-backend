import numpy as np
import pytest

from poweshift_backend.contracts.representation import ComparisonPolicy, NumericalPolicy
from poweshift_backend.reconstruction.inputs import Phase3Inputs, TelemetryChunk
from poweshift_backend.representation.inputs import UpdateUnit
from poweshift_backend.representation.run import _precompute_window, build_training_teacher, policy_identifier


def _policy() -> ComparisonPolicy:
    return ComparisonPolicy(
        numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12),
        metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation",
        per_update_refit_budget=1,
    )


def _chunk(run_id: str, start: float, end: float) -> TelemetryChunk:
    time_s = np.linspace(start, end, 6, dtype=np.float64)
    speed_ms = np.linspace(20.0 + start, 22.0 + start, 6, dtype=np.float64)
    controls = {"throttle_pct": np.full(6, 30.0), "brake": np.zeros(6), "n_gear": np.full(6, 4.0)}
    valid = {name: np.ones(6, dtype=np.bool_) for name in ("speed_ms", *controls)}
    return TelemetryChunk("2026-02-11", "1", run_id, 0, "training", time_s, speed_ms, controls, valid, {}, ())


def _unit(run_id: str, cutoff: float) -> UpdateUnit:
    return UpdateUnit(
        "1", "2026-02-11", run_id, "training", cutoff,
        np.ones((5, 3), dtype=np.float32), np.ones((5, 3), dtype=np.bool_), np.zeros(5, dtype=np.bool_),
    )


def _inputs(*chunks: TelemetryChunk) -> Phase3Inputs:
    return Phase3Inputs(None, chunks, (), None)


def test_teacher_for_an_earlier_unit_excludes_later_training_evidence() -> None:
    policy = _policy()
    unit = _unit("early", 1.0)
    prefix = tuple(_chunk(run_id, 0.0, 1.0) for run_id in ("a", "b", "c", "early"))

    bounds = np.array([100000.0, 100000.0, 100000.0, 10.0], dtype=np.float32)
    earlier = build_training_teacher(_inputs(*prefix), unit, policy, policy_identifier(policy), bounds)
    with_later = build_training_teacher(
        _inputs(*prefix, _chunk("later", 2.0, 3.0)), unit, policy, policy_identifier(policy), bounds
    )

    assert earlier.numerical_fit_sha256 == with_later.numerical_fit_sha256
    assert np.array_equal(earlier.physical_target, with_later.physical_target)


def test_teacher_rejects_a_policy_identifier_that_does_not_describe_its_policy() -> None:
    with pytest.raises(ValueError, match="policy"):
        build_training_teacher(_inputs(*tuple(_chunk(run_id, 0.0, 1.0) for run_id in ("a", "b", "c", "early"))), _unit("early", 1.0), _policy(), "other", np.ones(4, dtype=np.float32))


def test_precomputed_inputs_left_pad_a_short_completed_run_to_the_frozen_window() -> None:
    prepared = _precompute_window(_unit("early", 1.0))

    assert prepared.features.shape == (64, 3)
    assert prepared.padding[:59].all()
    assert not prepared.padding[59:].any()
