import pytest
import torch

from poweshift_backend.reconstruction.weekend_losses import WeekendPairInputs, weekend_pair_objective


def _inputs() -> WeekendPairInputs:
    progress = torch.tensor([[[0.2, 0.1], [0.5, 0.4]]], dtype=torch.float32, requires_grad=True)
    crossings = torch.tensor([[[10.0], [11.0]]], dtype=torch.float32, requires_grad=True)
    observed_progress = torch.tensor([[[0.2, 0.1], [0.5, 0.4]]], dtype=torch.float32)
    observed_crossings = torch.tensor([[[10.0], [11.0]]], dtype=torch.float32)
    pair_mask = torch.tensor([[[[False, True], [False, False]]]])
    return WeekendPairInputs(progress, crossings, observed_progress, observed_crossings, pair_mask, pair_mask.repeat(1, 2, 1, 1), torch.zeros((1, 2)))


def test_objective_uses_signed_checkpoint_gaps_and_backpropagates_to_both_cars() -> None:
    inputs = _inputs()
    result = weekend_pair_objective(inputs, timing_scale=1.0, progress_scale=1.0)

    result.loss.backward()

    assert result.timing_gap_count == 1
    assert result.loss.item() > 0.0
    assert inputs.predicted_crossings.grad[0, :, 0].abs().sum() > 0.0


def test_pair_direction_keeps_symmetric_variance_and_reverses_signed_gap() -> None:
    inputs = _inputs()
    reverse = torch.tensor([[[[False, False], [True, False]]]])
    reversed_inputs = WeekendPairInputs(
        inputs.predicted_progress,
        inputs.predicted_crossings,
        inputs.observed_progress,
        inputs.observed_crossings,
        reverse,
        reverse.repeat(1, 2, 1, 1),
        inputs.car_uncertainty,
    )

    forward = weekend_pair_objective(inputs, timing_scale=1.0, progress_scale=1.0)
    backward = weekend_pair_objective(reversed_inputs, timing_scale=1.0, progress_scale=1.0)

    assert torch.allclose(forward.gap_loss, backward.gap_loss)


def test_ties_are_excluded_from_rank_but_retained_for_gap_loss() -> None:
    inputs = _inputs()
    inputs = WeekendPairInputs(
        inputs.predicted_progress,
        inputs.predicted_crossings,
        inputs.observed_progress,
        torch.tensor([[[10.0], [10.0]]]),
        inputs.timing_pair_mask,
        inputs.progress_pair_mask,
        inputs.car_uncertainty,
    )

    result = weekend_pair_objective(inputs, timing_scale=1.0, progress_scale=1.0)

    assert result.timing_rank_count == 0
    assert result.timing_gap_count == 1


def test_objective_refuses_empty_or_nonfinite_targets() -> None:
    inputs = _inputs()
    empty = WeekendPairInputs(
        inputs.predicted_progress, inputs.predicted_crossings, inputs.observed_progress,
        inputs.observed_crossings, torch.zeros_like(inputs.timing_pair_mask),
        torch.zeros_like(inputs.progress_pair_mask), inputs.car_uncertainty,
    )

    with pytest.raises(ValueError, match="no valid"):
        weekend_pair_objective(empty, timing_scale=1.0, progress_scale=1.0)
    with pytest.raises(ValueError, match="finite"):
        weekend_pair_objective(inputs, timing_scale=float("nan"), progress_scale=1.0)


def test_trajectory_means_are_equal_when_one_has_more_valid_wall_times() -> None:
    first = _inputs()
    second = _inputs()
    combined = WeekendPairInputs(
        torch.cat((first.predicted_progress, second.predicted_progress)),
        torch.cat((first.predicted_crossings, second.predicted_crossings)),
        torch.cat((first.observed_progress, second.observed_progress)),
        torch.cat((first.observed_crossings, second.observed_crossings)),
        torch.cat((first.timing_pair_mask, second.timing_pair_mask)),
        torch.cat((first.progress_pair_mask, torch.cat((second.progress_pair_mask[:, :1], torch.zeros_like(second.progress_pair_mask[:, :1])), dim=1))),
        torch.cat((first.car_uncertainty, second.car_uncertainty)),
    )
    second_one = WeekendPairInputs(
        second.predicted_progress, second.predicted_crossings, second.observed_progress,
        second.observed_crossings, second.timing_pair_mask,
        torch.cat((second.progress_pair_mask[:, :1], torch.zeros_like(second.progress_pair_mask[:, :1])), dim=1),
        second.car_uncertainty,
    )

    result = weekend_pair_objective(combined, timing_scale=1.0, progress_scale=1.0)
    expected = (weekend_pair_objective(first, timing_scale=1.0, progress_scale=1.0).rank_loss + weekend_pair_objective(second_one, timing_scale=1.0, progress_scale=1.0).rank_loss) / 2.0

    assert torch.allclose(result.rank_loss, expected)


def test_masked_missing_observations_do_not_block_selected_finite_pairs() -> None:
    inputs = _inputs()
    observed_progress = inputs.observed_progress.clone()
    observed_progress[0, 1] = float("nan")
    progress_mask = torch.cat((inputs.progress_pair_mask[:, :1], torch.zeros_like(inputs.progress_pair_mask[:, :1])), dim=1)
    masked = WeekendPairInputs(
        inputs.predicted_progress, inputs.predicted_crossings, observed_progress,
        inputs.observed_crossings, inputs.timing_pair_mask, progress_mask, inputs.car_uncertainty,
    )

    result = weekend_pair_objective(masked, timing_scale=1.0, progress_scale=1.0)

    assert torch.isfinite(result.loss)


def test_progress_only_loss_ignores_masked_nan_checkpoint_predictions() -> None:
    inputs = _inputs()
    crossings = inputs.predicted_crossings.detach().clone()
    crossings[:] = float("nan")
    progress_only = WeekendPairInputs(
        inputs.predicted_progress, crossings, inputs.observed_progress, inputs.observed_crossings,
        torch.zeros_like(inputs.timing_pair_mask), inputs.progress_pair_mask, inputs.car_uncertainty,
    )

    result = weekend_pair_objective(progress_only, timing_scale=1.0, progress_scale=1.0)

    assert torch.isfinite(result.loss)
    assert result.timing_gap_count == 0
