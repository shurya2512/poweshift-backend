"""Direct pair losses for engine-produced weekend trajectories."""

from dataclasses import dataclass
from math import isfinite, log, pi

import torch
import torch.nn.functional as F


@dataclass(frozen=True)
class WeekendPairInputs:
    """Progress is [B,T,C]; crossings are [B,C,K] at matching checkpoints."""

    predicted_progress: torch.Tensor
    predicted_crossings: torch.Tensor
    observed_progress: torch.Tensor
    observed_crossings: torch.Tensor
    timing_pair_mask: torch.Tensor
    progress_pair_mask: torch.Tensor
    car_uncertainty: torch.Tensor


@dataclass(frozen=True)
class WeekendPairLoss:
    """Normalized loss scalars and the number of admitted comparisons."""

    loss: torch.Tensor
    rank_loss: torch.Tensor
    gap_loss: torch.Tensor
    timing_rank_count: int
    progress_rank_count: int
    timing_gap_count: int


def weekend_pair_objective(
    inputs: WeekendPairInputs,
    *,
    timing_scale: float,
    progress_scale: float,
    tau: float = 1.0,
    variance_floor: float = 1e-4,
    rank_weight: float = 1.0,
    gap_weight: float = 1.0,
) -> WeekendPairLoss:
    """Score checkpoint timing and common-wall-time progress without a rank head."""
    _validate(inputs, timing_scale, progress_scale, tau, variance_floor, rank_weight, gap_weight)
    rank_by_trajectory: list[torch.Tensor] = []
    gap_by_trajectory: list[torch.Tensor] = []
    timing_rank_count = progress_rank_count = timing_gap_count = 0
    for trajectory in range(inputs.predicted_progress.shape[0]):
        timing_rank, timing_gap, timing_count, gap_count = _timing_terms(inputs, trajectory, timing_scale, tau, variance_floor)
        progress_rank, progress_count = _progress_terms(inputs, trajectory, progress_scale, tau)
        rank_terms = timing_rank + progress_rank
        if rank_terms:
            rank_by_trajectory.append(torch.cat(rank_terms).mean())
        if timing_gap:
            gap_by_trajectory.append(torch.cat(timing_gap).mean())
        timing_rank_count += timing_count
        progress_rank_count += progress_count
        timing_gap_count += gap_count
    if not rank_by_trajectory and not gap_by_trajectory:
        raise ValueError("no valid timing or progress pairs")
    if rank_by_trajectory:
        rank_loss = torch.stack(rank_by_trajectory).mean()
    else:
        rank_loss = torch.stack(gap_by_trajectory).mean() * 0.0
    if gap_by_trajectory:
        gap_loss = torch.stack(gap_by_trajectory).mean()
    else:
        gap_loss = rank_loss * 0.0
    return WeekendPairLoss(
        loss=rank_weight * rank_loss + gap_weight * gap_loss,
        rank_loss=rank_loss,
        gap_loss=gap_loss,
        timing_rank_count=timing_rank_count,
        progress_rank_count=progress_rank_count,
        timing_gap_count=timing_gap_count,
    )


def _timing_terms(inputs: WeekendPairInputs, trajectory: int, scale: float, tau: float, floor: float):
    checkpoint, first, second = inputs.timing_pair_mask[trajectory].nonzero(as_tuple=True)
    if checkpoint.numel() == 0:
        return [], [], 0, 0
    observed = (inputs.observed_crossings[trajectory, first, checkpoint] - inputs.observed_crossings[trajectory, second, checkpoint]) / scale
    predicted = (inputs.predicted_crossings[trajectory, first, checkpoint] - inputs.predicted_crossings[trajectory, second, checkpoint]) / scale
    uncertainty = (inputs.car_uncertainty[trajectory, first] + inputs.car_uncertainty[trajectory, second]) * 0.5
    _require_finite(observed, predicted, uncertainty)
    variance = F.softplus(uncertainty) + floor
    gaps = [0.5 * ((observed - predicted).square() / variance + variance.log() + log(2.0 * pi))]
    tied = observed == 0.0
    if tied.all():
        return [], gaps, 0, int(observed.numel())
    logit = -predicted[~tied] / tau
    ranks = [torch.where(observed[~tied] < 0.0, F.softplus(-logit), F.softplus(logit))]
    return ranks, gaps, int((~tied).sum()), int(observed.numel())


def _progress_terms(inputs: WeekendPairInputs, trajectory: int, scale: float, tau: float):
    wall_time, first, second = inputs.progress_pair_mask[trajectory].nonzero(as_tuple=True)
    if wall_time.numel() == 0:
        return [], 0
    observed = inputs.observed_progress[trajectory, wall_time, first] - inputs.observed_progress[trajectory, wall_time, second]
    predicted = (inputs.predicted_progress[trajectory, wall_time, first] - inputs.predicted_progress[trajectory, wall_time, second]) / scale
    _require_finite(observed, predicted)
    tied = observed == 0.0
    if tied.all():
        return [], 0
    values = torch.where(observed[~tied] > 0.0, F.softplus(-predicted[~tied] / tau), F.softplus(predicted[~tied] / tau))
    return [values], int((~tied).sum())


def _validate(inputs: WeekendPairInputs, *scales: float) -> None:
    if any(not isfinite(value) or value <= 0.0 for value in scales):
        raise ValueError("scales, weights and floors must be finite positive values")
    progress_shape = inputs.predicted_progress.shape
    crossing_shape = inputs.predicted_crossings.shape
    if len(progress_shape) != 3 or len(crossing_shape) != 3 or inputs.observed_progress.shape != progress_shape or inputs.observed_crossings.shape != crossing_shape:
        raise ValueError("predicted and observed tensors must share [trajectory, time, car] shapes")
    trajectories, wall_times, cars = progress_shape
    if crossing_shape[0] != trajectories or crossing_shape[1] != cars:
        raise ValueError("crossings must share trajectory and car dimensions")
    if inputs.car_uncertainty.shape != (trajectories, cars):
        raise ValueError("car uncertainty must share trajectory and car dimensions")
    if inputs.timing_pair_mask.shape != (trajectories, crossing_shape[2], cars, cars) or inputs.progress_pair_mask.shape != (trajectories, wall_times, cars, cars):
        raise ValueError("pair masks must match checkpoint or wall-time dimensions")
    if inputs.timing_pair_mask.dtype is not torch.bool or inputs.progress_pair_mask.dtype is not torch.bool:
        raise ValueError("pair masks must be boolean")
    if inputs.timing_pair_mask.diagonal(dim1=-2, dim2=-1).any() or inputs.progress_pair_mask.diagonal(dim1=-2, dim2=-1).any():
        raise ValueError("self pairs are not allowed")
    if (inputs.timing_pair_mask & inputs.timing_pair_mask.transpose(-1, -2)).any() or (inputs.progress_pair_mask & inputs.progress_pair_mask.transpose(-1, -2)).any():
        raise ValueError("pair masks cannot duplicate both directions")


def _require_finite(*values: torch.Tensor) -> None:
    if not all(torch.isfinite(value).all() for value in values):
        raise ValueError("used predictions, observations and uncertainty must be finite")
