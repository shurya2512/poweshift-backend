"""Race-wide motion, rank, gap, coverage, and profile diagnostics."""

from collections import defaultdict
from math import log, pi, sqrt

import numpy as np
import torch
import torch.nn.functional as F

from poweshift_backend.physics.differentiable import DifferentiableMechanics, PARAMETER_NAMES, StaticRoadLookup
from poweshift_backend.representation.weekend_model import WeekendTelemetryModel
from poweshift_backend.representation.weekend_training import WeekendTrajectoryBatch, _checkpoint_crossings, _controls_at


def race_batch_errors(
    predicted_trajectory: torch.Tensor,
    predicted_crossings: torch.Tensor,
    batch: WeekendTrajectoryBatch,
    *,
    car_uncertainty: torch.Tensor | None = None,
) -> dict[str, float | int]:
    """Return additive error terms for one complete whole-field window."""
    if batch.observed_speed is None:
        raise ValueError("race evaluation needs observed 4 Hz speed")
    predicted_speed = predicted_trajectory[..., 0]
    predicted_progress = predicted_trajectory[..., 2]
    speed_error = predicted_speed - batch.observed_speed
    observed_delta = batch.observed_progress - batch.observed_progress[:1]
    predicted_delta = predicted_progress - predicted_progress[:1]
    progress_error = (predicted_delta - observed_delta)[1:]
    progress_mask = batch.progress_pair_mask
    wall, first, second = progress_mask.nonzero(as_tuple=True)
    observed_order = batch.observed_progress[wall, first] > batch.observed_progress[wall, second]
    predicted_order = predicted_progress[wall, first] > predicted_progress[wall, second]
    checkpoint, first, second = batch.timing_pair_mask.nonzero(as_tuple=True)
    observed_gap = batch.observed_crossings[first, checkpoint] - batch.observed_crossings[second, checkpoint]
    predicted_gap = predicted_crossings[first, checkpoint] - predicted_crossings[second, checkpoint]
    gap_supported = torch.isfinite(predicted_gap) & torch.isfinite(observed_gap)
    gap_error = predicted_gap[gap_supported] - observed_gap[gap_supported]
    observed_gap = observed_gap[gap_supported]
    predicted_gap = predicted_gap[gap_supported]
    needed = (batch.timing_pair_mask.any(dim=-1) | batch.timing_pair_mask.any(dim=-2)).transpose(0, 1)
    requested_crossing = predicted_crossings[needed]
    observed_crossing = batch.observed_crossings[needed]
    crossing_supported = torch.isfinite(requested_crossing) & torch.isfinite(observed_crossing)
    crossing_error = requested_crossing[crossing_supported] - observed_crossing[crossing_supported]
    calibration = {}
    if car_uncertainty is not None and gap_error.numel():
        uncertainty = (car_uncertainty[first][gap_supported] + car_uncertainty[second][gap_supported]) * 0.5
        variance = F.softplus(uncertainty) + 1e-4
        scaled_error = gap_error / batch.timing_scale
        sigma_s = torch.sqrt(variance) * batch.timing_scale
        calibration = {
            "calibration_count": gap_error.numel(),
            "calibration_nll_sum": float((0.5 * (scaled_error.square() / variance + variance.log() + log(2.0 * pi))).sum()),
            "calibration_sigma_sum": float(sigma_s.sum()),
            "calibration_within_1sigma": int((gap_error.abs() <= sigma_s).sum()),
            "calibration_within_2sigma": int((gap_error.abs() <= 2.0 * sigma_s).sum()),
        }
    horizon_s = max(float(batch.observation_times_s[-1] - batch.observation_times_s[0]), 1.0)
    speed_basis = max(float(torch.sqrt(batch.observed_speed.square().mean())), 1.0)
    progress_basis = max(float(observed_delta.abs().max()), 1.0)
    return {
        "speed_count": speed_error.numel(),
        "speed_abs": float(speed_error.abs().sum()),
        "speed_sq": float(speed_error.square().sum()),
        "speed_norm_sq": float((speed_error / speed_basis).square().sum()),
        "progress_count": progress_error.numel(),
        "progress_abs": float(progress_error.abs().sum()),
        "progress_sq": float(progress_error.square().sum()),
        "progress_norm_sq": float((progress_error / progress_basis).square().sum()),
        "progress_rank_count": observed_order.numel(),
        "progress_rank_correct": int((observed_order == predicted_order).sum()),
        "gap_requested": gap_supported.numel(),
        "gap_count": gap_error.numel(),
        "gap_abs": float(gap_error.abs().sum()),
        "gap_sq": float(gap_error.square().sum()),
        "gap_sum": float(gap_error.sum()),
        "gap_sign_correct": int((torch.sign(observed_gap) == torch.sign(predicted_gap)).sum()),
        "crossing_requested": crossing_supported.numel(),
        "crossing_count": crossing_error.numel(),
        "crossing_abs": float(crossing_error.abs().sum()),
        "crossing_sq": float(crossing_error.square().sum()),
        "crossing_norm_sq": float((crossing_error / horizon_s).square().sum()),
        **calibration,
    }


def summarize_race_errors(rows: tuple[dict[str, float | int], ...]) -> dict[str, float | int | bool | None]:
    """Combine additive window metrics and apply the five-percent motion gate."""
    totals = defaultdict(float)
    for row in rows:
        for name, value in row.items():
            totals[name] += float(value)

    def mean(name: str, count: str) -> float | None:
        return totals[name] / totals[count] if totals[count] else None

    def rmse(name: str, count: str) -> float | None:
        return sqrt(totals[name] / totals[count]) if totals[count] else None

    speed_normalized = rmse("speed_norm_sq", "speed_count")
    progress_normalized = rmse("progress_norm_sq", "progress_count")
    crossing_normalized = rmse("crossing_norm_sq", "crossing_count")
    motion_values = (speed_normalized, progress_normalized, crossing_normalized)
    crossing_coverage = mean("crossing_count", "crossing_requested")
    motion_available = all(value is not None for value in motion_values) and crossing_coverage == 1.0
    return {
        "speed_samples": int(totals["speed_count"]),
        "speed_mae_ms": mean("speed_abs", "speed_count"),
        "speed_rmse_ms": rmse("speed_sq", "speed_count"),
        "speed_normalized_rmse": speed_normalized,
        "progress_samples": int(totals["progress_count"]),
        "progress_delta_mae_m": mean("progress_abs", "progress_count"),
        "progress_delta_rmse_m": rmse("progress_sq", "progress_count"),
        "progress_normalized_rmse": progress_normalized,
        "progress_rank_pairs": int(totals["progress_rank_count"]),
        "progress_rank_accuracy": mean("progress_rank_correct", "progress_rank_count"),
        "timing_gap_pairs_requested": int(totals["gap_requested"]),
        "timing_gap_pairs": int(totals["gap_count"]),
        "timing_gap_prediction_coverage": mean("gap_count", "gap_requested"),
        "signed_gap_mae_s": mean("gap_abs", "gap_count"),
        "signed_gap_rmse_s": rmse("gap_sq", "gap_count"),
        "signed_gap_bias_s": mean("gap_sum", "gap_count"),
        "signed_gap_sign_accuracy": mean("gap_sign_correct", "gap_count"),
        "timing_calibration_pairs": int(totals["calibration_count"]),
        "timing_gaussian_nll": mean("calibration_nll_sum", "calibration_count"),
        "timing_predicted_sigma_mean_s": mean("calibration_sigma_sum", "calibration_count"),
        "timing_empirical_1sigma_coverage": mean("calibration_within_1sigma", "calibration_count"),
        "timing_empirical_2sigma_coverage": mean("calibration_within_2sigma", "calibration_count"),
        "crossing_samples_requested": int(totals["crossing_requested"]),
        "crossing_samples": int(totals["crossing_count"]),
        "crossing_prediction_coverage": crossing_coverage,
        "crossing_time_mae_s": mean("crossing_abs", "crossing_count"),
        "crossing_time_rmse_s": rmse("crossing_sq", "crossing_count"),
        "crossing_normalized_rmse": crossing_normalized,
        "motion_gate_target": 0.05,
        "motion_gate_available": motion_available,
        "motion_gate_passed": motion_available and max(value for value in motion_values if value is not None) <= 0.05,
    }


def evaluate_race_model(
    model: WeekendTelemetryModel,
    engine: DifferentiableMechanics,
    batches: tuple[WeekendTrajectoryBatch, ...],
    diagnostics: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    """Evaluate one frozen model over all supported race windows."""
    rows = []
    exclusions = []
    profiles: dict[str, list[tuple[np.ndarray, np.ndarray]]] = defaultdict(list)
    evaluated = []
    with torch.no_grad():
        for batch, diagnostic in zip(batches, diagnostics, strict=True):
            try:
                output = model(batch.features)
                route = StaticRoadLookup(batch.road_progress_m, batch.road_curvature_m_inv)
                trajectory = engine.integrate(
                    batch.initial_state,
                    batch.observation_times_s,
                    _controls_at(batch),
                    route,
                    output.parameters,
                )
                crossings = _checkpoint_crossings(trajectory[..., 2], batch.observation_times_s, batch.checkpoint_progress_m)
                rows.append(race_batch_errors(trajectory, crossings, batch, car_uncertainty=output.uncertainty))
            except ValueError as error:
                exclusions.append({"logical_batch_id": batch.logical_batch_id, "failure": str(error)})
                continue
            evaluated.append(diagnostic)
            for index, entry in enumerate(diagnostic["entries"]):
                profiles[str(entry)].append((output.latent[index].cpu().numpy(), output.parameters[index].cpu().numpy()))
    report = summarize_race_errors(tuple(rows))
    report.update(
        requested_batches=len(batches),
        evaluated_batches=len(rows),
        excluded_batches=len(exclusions),
        exclusions=exclusions,
        evaluated_observation_rows=sum(int(item["observation_rows"]) for item in evaluated),
        evaluated_car_observation_rows=sum(int(item["observation_rows"]) * int(item["cars"]) for item in evaluated),
        race_clock_coverage_s=sum(float(item["end_s"]) - float(item["start_s"]) for item in evaluated),
    )
    frozen_profiles = {
        entry: {
            "windows": len(values),
            "latent_16d": np.mean([value[0] for value in values], axis=0).tolist(),
            "latent_std": np.std([value[0] for value in values], axis=0).tolist(),
            "parameters": dict(zip(PARAMETER_NAMES, np.mean([value[1] for value in values], axis=0).tolist(), strict=True)),
            "parameter_std": dict(zip(PARAMETER_NAMES, np.std([value[1] for value in values], axis=0).tolist(), strict=True)),
        }
        for entry, values in sorted(profiles.items(), key=lambda item: int(item[0]))
    }
    return report, frozen_profiles
