"""Rebuild source-linked planar paths and reject unsupported observation mapping."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SourceLinkedPath:
    """A metric path rebuilt from the exact position rows named by provenance."""

    source_rows: tuple[str, ...]
    x_m: np.ndarray
    y_m: np.ndarray
    distance_m: np.ndarray
    progress: np.ndarray


@dataclass(frozen=True)
class RouteAlignment:
    """Nearest-route coordinates for observations with recorded planar positions."""

    distance_m: np.ndarray
    progress: np.ndarray


def rebuild_source_linked_path(source_rows: tuple[str, ...], position_path: Path, entry: str) -> SourceLinkedPath:
    """Recover the named X/Y records from an acquisition position table."""
    position = pd.read_parquet(position_path)
    required = {"source_row", "DriverNumber", "X", "Y"}
    if not required.issubset(position.columns):
        raise ValueError("position table lacks recorded X/Y source rows")
    indexed = position.loc[position["DriverNumber"].astype(str) == entry].assign(
        _source_row=lambda frame: frame["source_row"].astype(str)
    ).set_index("_source_row")
    if len(set(source_rows)) != len(source_rows) or any(row not in indexed.index for row in source_rows):
        raise ValueError("profile source rows are unavailable in position data")
    recovered = indexed.loc[list(source_rows)]
    x_m = recovered["X"].to_numpy(dtype=np.float64) * 0.1
    y_m = recovered["Y"].to_numpy(dtype=np.float64) * 0.1
    if not np.isfinite(x_m).all() or not np.isfinite(y_m).all():
        raise ValueError("recorded path coordinates must be finite")
    distance_m = np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(x_m), np.diff(y_m)))))
    if len(distance_m) < 2 or distance_m[-1] <= 0.0:
        raise ValueError("recorded path coordinates do not advance")
    progress = distance_m / distance_m[-1]
    for values in (x_m, y_m, distance_m, progress):
        values.setflags(write=False)
    return SourceLinkedPath(source_rows=source_rows, x_m=x_m, y_m=y_m, distance_m=distance_m, progress=progress)


def align_supported_observations(
    observations: pd.DataFrame,
    path: SourceLinkedPath,
    *,
    max_distance_m: float | None = None,
    ambiguity_margin_m: float | None = None,
) -> RouteAlignment:
    """Map only finite recorded X/Y observations to their nearest recovered path point."""
    if not {"X", "Y"}.issubset(observations.columns):
        raise ValueError("route mapping requires recorded X/Y observations")
    x_m = observations["X"].to_numpy(dtype=np.float64) * 0.1
    y_m = observations["Y"].to_numpy(dtype=np.float64) * 0.1
    if not np.isfinite(x_m).all() or not np.isfinite(y_m).all():
        raise ValueError("route mapping requires finite recorded X/Y observations")
    if max_distance_m is None or ambiguity_margin_m is None:
        raise ValueError("route mapping requires configured distance thresholds")
    if max_distance_m <= 0.0 or ambiguity_margin_m < 0.0:
        raise ValueError("alignment thresholds must be non-negative physical distances")
    squared_distance = (x_m[:, None] - path.x_m) ** 2 + (y_m[:, None] - path.y_m) ** 2
    nearest = np.argmin(squared_distance, axis=1)
    sorted_distance = np.sort(np.sqrt(squared_distance), axis=1)
    if np.any(sorted_distance[:, 0] > max_distance_m):
        raise ValueError("observation exceeds the configured route distance")
    if len(path.x_m) > 1 and np.any(sorted_distance[:, 1] - sorted_distance[:, 0] <= ambiguity_margin_m):
        raise ValueError("observation has an ambiguous nearest route point")
    distance_m = path.distance_m[nearest].copy()
    progress = path.progress[nearest].copy()
    distance_m.setflags(write=False)
    progress.setflags(write=False)
    return RouteAlignment(distance_m=distance_m, progress=progress)
