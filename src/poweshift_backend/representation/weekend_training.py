"""Direct full-trajectory training through shared mechanics."""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from random import Random

import torch

from poweshift_backend.physics.differentiable import DifferentiableMechanics, StaticRoadLookup
from poweshift_backend.reconstruction.weekend_losses import WeekendPairInputs, weekend_pair_objective
from poweshift_backend.representation.weekend_model import WeekendTelemetryModel


@dataclass(frozen=True)
class WeekendTrajectoryBatch:
    """One continuous whole-field trajectory with source-bound labels."""

    features: torch.Tensor
    initial_state: torch.Tensor
    observation_times_s: torch.Tensor
    control_times_s: torch.Tensor
    controls: torch.Tensor
    control_inferred_mask: torch.Tensor
    control_bracket_span_s: torch.Tensor
    road_progress_m: torch.Tensor
    road_curvature_m_inv: torch.Tensor
    observed_progress: torch.Tensor
    observed_crossings: torch.Tensor
    checkpoint_progress_m: torch.Tensor
    timing_pair_mask: torch.Tensor
    progress_pair_mask: torch.Tensor
    timing_scale: float
    progress_scale: float
    source_partition: str
    source_hash: str
    cutoff_s: float
    control_clock_kind: str
    control_interpolation: str
    logical_batch_id: str
    source_context: str
    observed_speed: torch.Tensor | None = None


@dataclass(frozen=True)
class WeekendTrainingRecord:
    """Finite losses from bounded joint updates of one logical batch."""

    losses: tuple[float, ...]
    updates: int
    logical_batch_id: str
    source_hash: str
    cutoff_s: float
    timing_scale: float
    progress_scale: float


def run_smoke(
    model: WeekendTelemetryModel,
    engine: DifferentiableMechanics,
    optimizer: torch.optim.Optimizer,
    batches: tuple[WeekendTrajectoryBatch, ...],
    *,
    total_updates: int = 100,
    seed: int = 0,
) -> tuple[WeekendTrainingRecord, ...]:
    """Run a bounded smoke across whole-field logical batches."""
    if isinstance(total_updates, bool) or not isinstance(total_updates, int) or total_updates < 1:
        raise ValueError("smoke updates must be a positive integer")
    if len(batches) < total_updates:
        raise ValueError("smoke needs one update per batch")
    if len({batch.logical_batch_id for batch in batches}) != len(batches):
        raise ValueError("smoke batches need distinct logical batch ids")
    ordered = list(batches)
    Random(seed).shuffle(ordered)
    records = []
    remaining = total_updates
    for batch in ordered:
        if not remaining:
            break
        records.append(train_trajectory(model, engine, optimizer, batch, updates=1))
        remaining -= 1
    return tuple(records)


def save_smoke_checkpoint(path: Path, model: WeekendTelemetryModel, records: tuple[WeekendTrainingRecord, ...]) -> None:
    """Save and verify a smoke checkpoint before longer training."""
    state = model.state_dict()
    torch.save({"model_state": state, "model_config": model.config.__dict__, "records": tuple(record.__dict__ for record in records)}, path)
    loaded = torch.load(path, weights_only=True)
    if loaded["model_state"].keys() != state.keys() or any(
        not torch.equal(loaded["model_state"][name], value) for name, value in state.items()
    ):
        raise ValueError("smoke checkpoint round-trip differs")


def train_trajectory(
    model: WeekendTelemetryModel,
    engine: DifferentiableMechanics,
    optimizer: torch.optim.Optimizer,
    batch: WeekendTrajectoryBatch,
    *,
    updates: int = 1,
) -> WeekendTrainingRecord:
    """Train one joint full trajectory without state resets or detaches."""
    if updates != 1:
        raise ValueError("one logical batch allows exactly one update")
    _validate_batch(batch, model)
    losses = []
    for _ in range(updates):
        optimizer.zero_grad(set_to_none=True)
        loss = _trajectory_loss(model, engine, batch)
        if not torch.isfinite(loss):
            raise ValueError("trajectory loss must be finite")
        loss.backward()
        gradients = [parameter.grad for parameter in model.parameters() if parameter.grad is not None]
        if not gradients or any(not torch.isfinite(gradient).all() for gradient in gradients):
            raise ValueError("trajectory gradients must be finite")
        encoder_gradients = [parameter.grad for parameter in model.encoder.parameters() if parameter.grad is not None]
        if not encoder_gradients or not any(gradient.abs().sum() > 0.0 for gradient in encoder_gradients):
            raise ValueError("informative trajectory loss must reach the encoder")
        if batch.timing_pair_mask.any() and (
            model.uncertainty_decoder.weight.grad is None or model.uncertainty_decoder.weight.grad.abs().sum() == 0.0
        ):
            raise ValueError("timing loss must reach per-car uncertainty")
        optimizer.step()
        losses.append(float(loss.detach()))
    return WeekendTrainingRecord(tuple(losses), updates, batch.logical_batch_id, batch.source_hash, batch.cutoff_s, batch.timing_scale, batch.progress_scale)


def _trajectory_loss(model: WeekendTelemetryModel, engine: DifferentiableMechanics, batch: WeekendTrajectoryBatch) -> torch.Tensor:
    output = model(batch.features)
    route = StaticRoadLookup(batch.road_progress_m, batch.road_curvature_m_inv)
    engine.assert_gradient_supported(
        batch.initial_state,
        batch.controls[0],
        route(batch.initial_state[..., 2]),
        output.parameters,
    )
    trajectory = engine.integrate(
        batch.initial_state,
        batch.observation_times_s,
        _controls_at(batch),
        route,
        output.parameters,
    )
    progress = trajectory[..., 2].unsqueeze(0)
    crossings = _checkpoint_crossings(trajectory[..., 2], batch.observation_times_s, batch.checkpoint_progress_m)
    _require_needed_crossings(crossings, batch.timing_pair_mask)
    inputs = WeekendPairInputs(
        progress,
        crossings.unsqueeze(0),
        batch.observed_progress.unsqueeze(0),
        batch.observed_crossings.unsqueeze(0),
        batch.timing_pair_mask.unsqueeze(0),
        batch.progress_pair_mask.unsqueeze(0),
        output.uncertainty.unsqueeze(0),
    )
    return weekend_pair_objective(inputs, timing_scale=batch.timing_scale, progress_scale=batch.progress_scale).loss


def _controls_at(batch: WeekendTrajectoryBatch):
    def interpolate(time_s: torch.Tensor) -> torch.Tensor:
        upper = torch.searchsorted(batch.control_times_s, time_s, right=False).clamp(1, len(batch.control_times_s) - 1)
        lower = upper - 1
        start = batch.control_times_s[lower]
        fraction = (time_s - start) / (batch.control_times_s[upper] - start)
        return batch.controls[lower] + fraction * (batch.controls[upper] - batch.controls[lower])

    return interpolate


def _checkpoint_crossings(progress: torch.Tensor, times: torch.Tensor, checkpoints: torch.Tensor) -> torch.Tensor:
    if not torch.all(torch.diff(progress, dim=0) > 0.0):
        raise ValueError("predicted progress must be strictly increasing for checkpoint crossings")
    by_car = progress.transpose(0, 1).contiguous()
    values = checkpoints.expand(progress.shape[1], -1).contiguous()
    index = torch.searchsorted(by_car.detach(), values, right=False)
    valid = (values >= by_car[:, :1]) & (values <= by_car[:, -1:])
    safe_index = index.clamp(1, len(times) - 1)
    starts = by_car.gather(1, safe_index - 1)
    ends = by_car.gather(1, safe_index)
    start_times = times[safe_index - 1]
    end_times = times[safe_index]
    interpolated = start_times + (values - starts) * (end_times - start_times) / (ends - starts)
    start_crossing = torch.full_like(interpolated, times[0])
    crossing = torch.where(index == 0, start_crossing, interpolated)
    return torch.where(valid, crossing, torch.full_like(crossing, float("nan")))


def _require_needed_crossings(crossings: torch.Tensor, mask: torch.Tensor) -> None:
    needed = mask.any(dim=-1) | mask.any(dim=-2)
    if not torch.isfinite(crossings.transpose(0, 1)[needed]).all():
        raise ValueError("required predicted checkpoint crossing is unavailable")


def _validate_batch(batch: WeekendTrajectoryBatch, model: WeekendTelemetryModel) -> None:
    cars = batch.features.shape[0] if batch.features.ndim == 3 else 0
    times = len(batch.observation_times_s)
    controls = len(batch.control_times_s)
    checkpoints = len(batch.checkpoint_progress_m)
    expected = (
        (batch.initial_state, (cars, 4)),
        (batch.controls, (controls, cars, 2)),
        (batch.control_inferred_mask, (controls, cars)),
        (batch.control_bracket_span_s, (controls, cars)),
        (batch.observed_progress, (times, cars)),
        (batch.observed_crossings, (cars, checkpoints)),
        (batch.timing_pair_mask, (checkpoints, cars, cars)),
        (batch.progress_pair_mask, (times, cars, cars)),
    )
    if batch.observed_speed is not None:
        expected += ((batch.observed_speed, (times, cars)),)
    if cars < 2 or batch.features.shape[-1] != model.config.feature_width or any(value.shape != shape for value, shape in expected):
        raise ValueError("trajectory batch shapes do not match the whole field")
    if batch.timing_pair_mask.dtype is not torch.bool or batch.progress_pair_mask.dtype is not torch.bool or batch.control_inferred_mask.dtype is not torch.bool:
        raise ValueError("trajectory masks must be boolean")
    finite_tensors = (batch.features, batch.initial_state, batch.observation_times_s, batch.control_times_s, batch.controls, batch.control_bracket_span_s, batch.road_progress_m, batch.road_curvature_m_inv, batch.checkpoint_progress_m)
    if batch.observed_speed is not None:
        finite_tensors += (batch.observed_speed,)
    if not all(torch.isfinite(value).all() for value in finite_tensors) or not all(isfinite(value) and value > 0.0 for value in (batch.timing_scale, batch.progress_scale)):
        raise ValueError("trajectory data and scales must be finite")
    if controls < 2 or times < 2 or len(batch.road_progress_m) < 2 or torch.diff(batch.control_times_s).min() <= 0.0 or torch.diff(batch.observation_times_s).min() <= 0.0:
        raise ValueError("trajectory clocks and route must be increasing")
    if batch.control_times_s[0] > batch.observation_times_s[0] or batch.control_times_s[-1] < batch.observation_times_s[-1]:
        raise ValueError("control clock must cover the full trajectory")
    if torch.diff(batch.control_times_s).max() > 2.0 or batch.control_bracket_span_s.min() < 0.0 or batch.control_bracket_span_s.max() > 2.0:
        raise ValueError("inferred controls require a source bracket of at most two seconds")
    if batch.source_partition != "training" or not batch.source_hash or not isfinite(batch.cutoff_s) or batch.cutoff_s < float(batch.observation_times_s[-1]):
        raise ValueError("trajectory batch requires a training source binding and completed cutoff")
    if batch.control_clock_kind != "source_union" or batch.control_interpolation != "linear_source_bracket":
        raise ValueError("controls must use declared source-union bracket interpolation")
    if not batch.logical_batch_id or not batch.source_context:
        raise ValueError("trajectory batch requires logical source context")
