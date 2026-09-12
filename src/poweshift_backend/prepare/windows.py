"""Emit masked StintPackages from continuous runs, and fit/freeze transforms on training records only."""

from dataclasses import dataclass
from datetime import date
from enum import IntEnum
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import ConfigDict, field_validator, model_validator

from poweshift_backend.contracts.acquisition import _TEST_DATES, StrictModel
from poweshift_backend.contracts.preparation import ArtifactProvenance, PreprocessingSpec, SplitManifest
from poweshift_backend.prepare.runs import RunSegment, TyreContext

Split = Literal["training", "selection", "final_evaluation"]


class OriginKind(IntEnum):
    MEASURED = 0
    DERIVED = 1


class StintPackage(StrictModel):
    """A masked, source-referenced telemetry window for one continuous run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    entry: str
    session_key: str
    run_id: str
    chunk_index: int
    start_time_s: float
    end_time_s: float
    completed_cutoff_s: float
    X: np.ndarray
    valid: np.ndarray
    origin: np.ndarray
    dt_s: np.ndarray
    padding: np.ndarray
    feature_names: tuple[str, ...]
    tyre: TyreContext
    programme_context: str
    quality_context: str
    availability_convention: str
    split: Split
    provenance: ArtifactProvenance

    @field_validator("X")
    @classmethod
    def _check_x(cls, value: np.ndarray) -> np.ndarray:
        if value.dtype != np.float32 or value.ndim != 2:
            raise ValueError("X must be a float32 [T, F] array")
        if not np.isfinite(value).all():
            raise ValueError("X must be finite everywhere; use valid to mark unavailable cells")
        value.setflags(write=False)
        return value

    @field_validator("valid")
    @classmethod
    def _check_valid(cls, value: np.ndarray) -> np.ndarray:
        if value.dtype != np.bool_:
            raise ValueError("valid must be a bool array")
        value.setflags(write=False)
        return value

    @field_validator("origin")
    @classmethod
    def _check_origin(cls, value: np.ndarray) -> np.ndarray:
        if value.dtype != np.uint8:
            raise ValueError("origin must be a uint8 array")
        value.setflags(write=False)
        return value

    @field_validator("dt_s")
    @classmethod
    def _check_dt_s(cls, value: np.ndarray) -> np.ndarray:
        if value.dtype != np.float64:
            raise ValueError("dt_s must be a float64 array")
        value.setflags(write=False)
        return value

    @field_validator("padding")
    @classmethod
    def _check_padding(cls, value: np.ndarray) -> np.ndarray:
        if value.dtype != np.bool_:
            raise ValueError("padding must be a bool array")
        value.setflags(write=False)
        return value

    @model_validator(mode="after")
    def _shapes_and_interval_rules(self) -> "StintPackage":
        t, f = self.X.shape
        if self.valid.shape != (t, f) or self.origin.shape != (t, f):
            raise ValueError("valid and origin must match X's [T, F] shape")
        if self.dt_s.shape != (t,) or self.padding.shape != (t,):
            raise ValueError("dt_s and padding must match X's T length")
        if len(self.feature_names) != f:
            raise ValueError("feature_names must match X's F width")
        if t > 0 and self.dt_s[0] != 0.0:
            raise ValueError("the initial interval must be zero")
        for i in range(1, t):
            if not self.padding[i] and self.dt_s[i] <= 0.0:
                raise ValueError("every later valid (non-padding) interval must be positive")
        return self


def resolve_split(day_date: date, test_number: int, manifest: SplitManifest) -> Split:
    """Map a session's own date to its assigned Phase 2 split; never the inactive Phase 1 proposal."""
    if test_number == 1:
        if day_date not in _TEST_DATES[1]:
            raise ValueError(f"{day_date} is not a Test 1 date")
        return "training"
    if day_date == manifest.selection:
        return "selection"
    if day_date in manifest.final_evaluation:
        return "final_evaluation"
    raise ValueError(f"{day_date} is not covered by the phase 2 split manifest")


def chunk_run_indices(times_s: list[float], window_limit_s: float) -> list[list[int]]:
    """Split a run's sample positions into chunks no longer than the window duration limit."""
    if not times_s:
        return []
    chunks: list[list[int]] = [[0]]
    for i in range(1, len(times_s)):
        if times_s[i] - times_s[chunks[-1][0]] > window_limit_s:
            chunks.append([i])
        else:
            chunks[-1].append(i)
    return chunks


def _median_dt_s(times_s: list[float]) -> float:
    diffs = sorted(b - a for a, b in zip(times_s, times_s[1:]))
    if not diffs:
        return 0.0
    mid = len(diffs) // 2
    return diffs[mid] if len(diffs) % 2 else (diffs[mid - 1] + diffs[mid]) / 2


def window_capacity_for_run(times_s: list[float], window_limit_s: float) -> int:
    """Sample capacity implied by the window duration limit and the run's own native rate."""
    median_dt = _median_dt_s(times_s)
    if median_dt <= 0.0:
        return len(times_s)
    return max(1, round(window_limit_s / median_dt) + 1)


def build_stint_packages(
    *,
    entry: str,
    session_key: str,
    run: RunSegment,
    times_s: pd.Series,
    feature_columns: dict[str, pd.Series],
    tyre: TyreContext,
    programme_context: str,
    quality_context: str,
    split: Split,
    spec: PreprocessingSpec,
    provenance: ArtifactProvenance,
) -> list[StintPackage]:
    """Build one or more StintPackages for a run, chunked to the window duration limit."""
    indices = list(run.sample_indices)
    run_times = [float(times_s.iloc[i]) for i in indices]
    feature_names = tuple(feature_columns.keys())
    capacity = window_capacity_for_run(run_times, spec.window_limit_s)
    chunks = chunk_run_indices(run_times, spec.window_limit_s)

    packages = []
    for chunk_number, chunk in enumerate(chunks):
        chunk_source_positions = [indices[i] for i in chunk]
        is_last_chunk = chunk_number == len(chunks) - 1
        pad_to = capacity if is_last_chunk else len(chunk)
        packages.append(
            _build_one_package(
                entry=entry,
                session_key=session_key,
                run_id=f"{entry}-{run.start_time_s:.3f}",
                chunk_id=chunk_number,
                source_positions=chunk_source_positions,
                times_s=times_s,
                feature_names=feature_names,
                feature_columns=feature_columns,
                pad_to=pad_to,
                tyre=tyre,
                programme_context=programme_context,
                quality_context=quality_context,
                split=split,
                spec=spec,
                provenance=provenance,
            )
        )
    return packages


def _build_one_package(
    *,
    entry: str,
    session_key: str,
    run_id: str,
    chunk_id: int,
    source_positions: list[int],
    times_s: pd.Series,
    feature_names: tuple[str, ...],
    feature_columns: dict[str, pd.Series],
    pad_to: int,
    tyre: TyreContext,
    programme_context: str,
    quality_context: str,
    split: Split,
    spec: PreprocessingSpec,
    provenance: ArtifactProvenance,
) -> StintPackage:
    real_count = len(source_positions)
    total = max(real_count, pad_to)
    n_features = len(feature_names)

    X = np.zeros((total, n_features), dtype=np.float32)
    valid = np.zeros((total, n_features), dtype=np.bool_)
    origin = np.full((total, n_features), OriginKind.DERIVED, dtype=np.uint8)
    dt_s = np.zeros(total, dtype=np.float64)
    padding = np.ones(total, dtype=np.bool_)

    chunk_times = [float(times_s.iloc[p]) for p in source_positions]
    for row, position in enumerate(source_positions):
        padding[row] = False
        dt_s[row] = 0.0 if row == 0 else chunk_times[row] - chunk_times[row - 1]
        for col, name in enumerate(feature_names):
            raw_value = feature_columns[name].iloc[position]
            if pd.notna(raw_value) and np.isfinite(raw_value):
                X[row, col] = np.float32(raw_value)
                valid[row, col] = True
                origin[row, col] = OriginKind.MEASURED

    completed_cutoff_s = chunk_times[-1] if chunk_times else 0.0
    return StintPackage(
        entry=entry,
        session_key=session_key,
        run_id=run_id,
        chunk_index=chunk_id,
        start_time_s=chunk_times[0] if chunk_times else 0.0,
        end_time_s=chunk_times[-1] if chunk_times else 0.0,
        completed_cutoff_s=completed_cutoff_s,
        X=X,
        valid=valid,
        origin=origin,
        dt_s=dt_s,
        padding=padding,
        feature_names=feature_names,
        tyre=tyre,
        programme_context=programme_context,
        quality_context=quality_context,
        availability_convention=spec.availability_convention,
        split=split,
        provenance=provenance,
    )


@dataclass(frozen=True)
class FrozenScaler:
    """Standardisation parameters fit once from training records, then frozen and reused."""

    feature_names: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray

    def apply(self, X: np.ndarray, valid: np.ndarray) -> np.ndarray:
        """Standardise valid cells with the frozen parameters; invalid cells stay zero."""
        out = np.zeros_like(X, dtype=np.float32)
        broadcast_mean = np.broadcast_to(self.mean, X.shape)
        broadcast_scale = np.broadcast_to(self.scale, X.shape)
        out[valid] = ((X[valid] - broadcast_mean[valid]) / broadcast_scale[valid]).astype(np.float32)
        return out


def fit_scaler(
    feature_names: tuple[str, ...], training_X: list[np.ndarray], training_valid: list[np.ndarray]
) -> FrozenScaler:
    """Fit mean/scale from valid cells of training arrays only; held-out data is never seen."""
    stacked_X = np.concatenate(training_X, axis=0) if training_X else np.zeros((0, len(feature_names)))
    stacked_valid = np.concatenate(training_valid, axis=0) if training_valid else np.zeros((0, len(feature_names)), dtype=bool)
    mean = np.zeros(len(feature_names), dtype=np.float64)
    scale = np.ones(len(feature_names), dtype=np.float64)
    for f in range(len(feature_names)):
        column = stacked_X[stacked_valid[:, f], f]
        if column.size:
            mean[f] = column.mean()
            std = column.std()
            scale[f] = std if std > 0 else 1.0
    mean.setflags(write=False)
    scale.setflags(write=False)
    return FrozenScaler(feature_names=feature_names, mean=mean, scale=scale)


def causal_smooth(times_s: np.ndarray, values: np.ndarray, valid: np.ndarray, smoothing_limit_s: float) -> np.ndarray:
    """Average each valid value over its own past within the smoothing window; never look ahead."""
    index = pd.to_timedelta(times_s, unit="s")
    series = pd.Series(np.where(valid, values, np.nan), index=index)
    smoothed = series.rolling(pd.Timedelta(seconds=smoothing_limit_s), min_periods=1).mean()
    return np.where(valid, smoothed.to_numpy(), 0.0).astype(np.float64)
