"""Derive PreprocessingSpec limits from Test 1 training records only; nothing is invented."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from poweshift_backend.contracts.preparation import PreprocessingSpec
from poweshift_backend.prepare.runs import garage_stop_intervals_s, red_flag_intervals_s, split_into_runs, tyre_replacement_times_s

_GAP_LIMIT_QUANTILE = 0.999
_STALENESS_QUANTILE = 0.5
_SMOOTHING_QUANTILE = 0.95
_WINDOW_QUANTILE = 0.5


@dataclass(frozen=True)
class TrainingDayPaths:
    """The three Test 1 exports this derivation is allowed to read."""

    date: str
    car_path: Path
    laps_path: Path
    track_status_path: Path


def derive_preprocessing_spec(training_days: list[TrainingDayPaths]) -> tuple[PreprocessingSpec, dict]:
    """Derive every limit from Test 1 sample-interval and run-duration statistics; record the derivation."""
    intervals, rows_per_day = _training_sample_intervals(training_days)
    gap_limit_s = float(np.quantile(intervals, _GAP_LIMIT_QUANTILE))
    staleness_limit_s = float(np.quantile(intervals, _STALENESS_QUANTILE))
    smoothing_limit_s = float(np.quantile(intervals, _SMOOTHING_QUANTILE))

    durations, runs_per_day = _training_run_durations(training_days, gap_limit_s)
    window_limit_s = float(np.quantile(durations, _WINDOW_QUANTILE))

    spec = PreprocessingSpec(
        gap_limit_s=gap_limit_s,
        staleness_limit_s=staleness_limit_s,
        smoothing_limit_s=smoothing_limit_s,
        window_limit_s=window_limit_s,
        availability_convention="current_past_prefix",
    )
    derivation = {
        "training_days": [day.date for day in training_days],
        "sample_interval_statistic": {
            "description": (
                "consecutive within-entry sample-time differences, in seconds, across all car "
                "telemetry rows on the Test 1 training days"
            ),
            "n_intervals": len(intervals),
            "car_rows_per_day": rows_per_day,
            "gap_limit_s": {"value": gap_limit_s, "quantile": _GAP_LIMIT_QUANTILE},
            "staleness_limit_s": {
                "value": staleness_limit_s,
                "quantile": _STALENESS_QUANTILE,
                "note": "not consumed by any prepare/ function in this codebase as of this commit",
            },
            "smoothing_limit_s": {"value": smoothing_limit_s, "quantile": _SMOOTHING_QUANTILE},
        },
        "run_duration_statistic": {
            "description": (
                "durations, in seconds, of continuous runs assembled from Test 1 car telemetry using "
                "the sample-interval-derived gap_limit_s together with garage-stop, red-flag and "
                "tyre-replacement boundaries"
            ),
            "n_runs": len(durations),
            "runs_per_day": runs_per_day,
            "window_limit_s": {"value": window_limit_s, "quantile": _WINDOW_QUANTILE},
        },
    }
    return spec, derivation


def _training_sample_intervals(training_days: list[TrainingDayPaths]) -> tuple[np.ndarray, dict[str, int]]:
    all_intervals = []
    rows_per_day: dict[str, int] = {}
    for day in training_days:
        car = pd.read_parquet(day.car_path, columns=["Time", "DriverNumber"])
        rows_per_day[day.date] = len(car)
        for _, group in car.groupby("DriverNumber"):
            times_s = group["Time"].sort_values().dt.total_seconds().to_numpy()
            dt = np.diff(times_s)
            all_intervals.append(dt[dt > 0])
    return np.concatenate(all_intervals), rows_per_day


def _training_run_durations(training_days: list[TrainingDayPaths], gap_limit_s: float) -> tuple[np.ndarray, dict[str, int]]:
    durations = []
    runs_per_day: dict[str, int] = {}
    for day in training_days:
        car = pd.read_parquet(day.car_path, columns=["Time", "DriverNumber"])
        laps = pd.read_parquet(day.laps_path)
        track_status = pd.read_parquet(day.track_status_path)
        red_flags = red_flag_intervals_s(track_status)
        day_run_count = 0
        for entry in sorted(car["DriverNumber"].dropna().unique()):
            group = car[car["DriverNumber"] == entry].sort_values("Time")
            times_s = group["Time"].dt.total_seconds().reset_index(drop=True)
            excluded = garage_stop_intervals_s(laps, entry) + red_flags
            tyre_times = tyre_replacement_times_s(laps, entry)
            runs = split_into_runs(entry, times_s, excluded, tyre_times, gap_limit_s=gap_limit_s)
            day_run_count += len(runs)
            durations.extend(run.end_time_s - run.start_time_s for run in runs)
        runs_per_day[day.date] = day_run_count
    return np.array(durations), runs_per_day
