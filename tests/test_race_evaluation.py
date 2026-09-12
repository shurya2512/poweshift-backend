import pytest
import torch

from poweshift_backend.representation.race_evaluation import race_batch_errors, summarize_race_errors
from poweshift_backend.representation.weekend_training import WeekendTrajectoryBatch


def _batch() -> WeekendTrajectoryBatch:
    return WeekendTrajectoryBatch(
        features=torch.zeros((2, 3, 3), dtype=torch.float64),
        initial_state=torch.tensor([[10.0, 0.0, 0.0, 25.0], [8.0, 0.0, 0.0, 25.0]], dtype=torch.float64),
        observation_times_s=torch.tensor([0.0, 1.0, 2.0], dtype=torch.float64),
        control_times_s=torch.tensor([0.0, 1.0, 2.0], dtype=torch.float64),
        controls=torch.zeros((3, 2, 2), dtype=torch.float64),
        control_inferred_mask=torch.zeros((3, 2), dtype=torch.bool),
        control_bracket_span_s=torch.zeros((3, 2), dtype=torch.float64),
        road_progress_m=torch.tensor([-10.0, 20.0], dtype=torch.float64),
        road_curvature_m_inv=torch.zeros(2, dtype=torch.float64),
        observed_progress=torch.zeros((3, 2), dtype=torch.float64),
        observed_crossings=torch.zeros((2, 1), dtype=torch.float64),
        checkpoint_progress_m=torch.tensor([5.0], dtype=torch.float64),
        timing_pair_mask=torch.tensor([[[False, True], [False, False]]]),
        progress_pair_mask=torch.zeros((3, 2, 2), dtype=torch.bool),
        timing_scale=1.0,
        progress_scale=10.0,
        source_partition="training",
        source_hash="unit",
        cutoff_s=2.0,
        control_clock_kind="source_union",
        control_interpolation="linear_source_bracket",
        logical_batch_id="unit",
        source_context="unit",
    )


def test_race_errors_include_motion_rank_gap_and_crossing_time() -> None:
    batch = _batch()
    batch = type(batch)(
        **{
            **batch.__dict__,
            "observed_speed": torch.tensor([[10.0, 8.0], [11.0, 9.0], [12.0, 10.0]], dtype=torch.float64),
            "observed_progress": torch.tensor([[0.0, 0.0], [5.0, 4.0], [10.0, 8.0]], dtype=torch.float64),
            "progress_pair_mask": torch.tensor(
                [[[False, False], [False, False]], [[False, True], [False, False]], [[False, True], [False, False]]]
            ),
            "observed_crossings": torch.tensor([[1.5], [2.0]], dtype=torch.float64),
        }
    )
    predicted = torch.tensor(
        [[10.0, 8.0, 0.0, 25.0], [12.0, 10.0, 6.0, 25.0], [13.0, 11.0, 11.0, 25.0]],
        dtype=torch.float64,
    ).unsqueeze(1).expand(-1, 2, -1).clone()
    predicted[:, 1, 0] = torch.tensor([8.0, 10.0, 11.0])
    predicted[:, 1, 2] = torch.tensor([0.0, 5.0, 9.0])
    predicted_crossings = torch.tensor([[1.0], [2.0]], dtype=torch.float64)

    report = summarize_race_errors(
        (race_batch_errors(predicted, predicted_crossings, batch, car_uncertainty=torch.zeros(2)),)
    )

    assert report["speed_rmse_ms"] == pytest.approx((4.0 / 6.0) ** 0.5)
    assert report["progress_delta_rmse_m"] == pytest.approx(1.0)
    assert report["progress_rank_accuracy"] == pytest.approx(1.0)
    assert report["signed_gap_mae_s"] == pytest.approx(0.5)
    assert report["signed_gap_sign_accuracy"] == pytest.approx(1.0)
    assert report["crossing_time_rmse_s"] == pytest.approx((0.25 / 2.0) ** 0.5)
    assert report["crossing_prediction_coverage"] == pytest.approx(1.0)
    assert report["timing_calibration_pairs"] == 1
    assert report["timing_predicted_sigma_mean_s"] > 0.0


def test_missing_predicted_crossing_is_reported_as_coverage() -> None:
    batch = _batch()
    batch = type(batch)(**{**batch.__dict__, "observed_speed": torch.ones((3, 2), dtype=torch.float64)})
    trajectory = torch.tensor(
        [[[1.0, 0.0, 0.0, 25.0], [1.0, 0.0, 0.0, 25.0]]] * 3,
        dtype=torch.float64,
    )

    report = summarize_race_errors(
        (race_batch_errors(trajectory, torch.tensor([[float("nan")], [2.0]]), batch),)
    )

    assert report["timing_gap_pairs_requested"] == 1
    assert report["timing_gap_pairs"] == 0
    assert report["crossing_prediction_coverage"] == pytest.approx(0.5)
    assert report["motion_gate_available"] is False
