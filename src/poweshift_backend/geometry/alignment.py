"""Rebuild source-linked planar paths and reject unsupported observation mapping."""

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd

LAP_BOUNDARY_TOLERANCE_S = 1e-6


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


@dataclass(frozen=True)
class FullLapGeometry:
    """One source-linked lap with native controls and a 4 Hz observation grid."""

    position_source_rows: tuple[str, ...]
    control_source_rows: tuple[str, ...]
    position_source_brackets: tuple[tuple[str, str], ...]
    observed_speed_source_brackets: tuple[tuple[str, str], ...]
    control_source_brackets: tuple[tuple[str, str], ...]
    time_s: np.ndarray
    control_time_s: np.ndarray
    observed_speed_ms: np.ndarray
    throttle_pct: np.ndarray
    brake: np.ndarray
    distance_m: np.ndarray
    progress: np.ndarray
    curvature_m_inv: np.ndarray
    motion_derived_mask: np.ndarray
    lap_complete: bool
    lap_is_accurate: bool
    lap_deleted: bool
    source_position_unit: str = "decimetres"
    source_speed_unit: str = "km/h"


@dataclass(frozen=True)
class RaceLapCoverage:
    """One completed-lap coverage decision in a full-race geometry audit."""

    lap_number: float
    start_time_s: float
    end_time_s: float
    state: str


@dataclass(frozen=True)
class FullRaceGeometryAudit:
    """Ordered full-race geometry support without reanchoring unsupported intervals."""

    entry: str
    lap_coverage: tuple[RaceLapCoverage, ...]
    lap_boundaries_supported: bool
    full_race_supported: bool


@dataclass(frozen=True)
class FullRaceGeometry:
    """Common-clock race labels with unsupported intervals retained as masks."""

    entry: str
    time_s: np.ndarray
    unwrapped_progress_laps: np.ndarray
    observed_speed_ms: np.ndarray
    lap_number: np.ndarray
    supported_mask: np.ndarray
    derived_mask: np.ndarray
    lap_coverage: tuple[RaceLapCoverage, ...]
    lap_position_brackets: dict[float, tuple[tuple[str, str], ...]]
    lap_speed_brackets: dict[float, tuple[tuple[str, str], ...]]
    participation_start_s: float
    participation_end_s: float
    lap_boundary_tolerance_s: float
    lap_boundaries_supported: bool
    same_checkpoint_supported: bool
    full_race_supported: bool
    common_position_brackets: tuple[tuple[tuple[str, str], tuple[str, str]] | None, ...]
    common_speed_brackets: tuple[tuple[tuple[str, str], tuple[str, str]] | None, ...]


@dataclass(frozen=True)
class SourceCrossingTimes:
    """Source-derived checkpoint crossings with explicit support masks."""

    time_s: np.ndarray
    supported_mask: np.ndarray


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


def build_full_lap_geometry(
    laps_path: Path,
    position_path: Path,
    car_path: Path,
    entry: str,
    lap_number: float,
    *,
    max_time_offset_s: float,
    observation_interval_s: float = 0.25,
) -> FullLapGeometry:
    """Build a continuous source-linked lap with bounded interpolation."""
    return _build_full_lap_geometry(
        pd.read_parquet(laps_path),
        pd.read_parquet(position_path),
        pd.read_parquet(car_path),
        entry,
        lap_number,
        max_time_offset_s=max_time_offset_s,
        observation_interval_s=observation_interval_s,
    )


def _build_full_lap_geometry(
    laps: pd.DataFrame,
    position_table: pd.DataFrame,
    car_table: pd.DataFrame,
    entry: str,
    lap_number: float,
    *,
    max_time_offset_s: float,
    observation_interval_s: float,
    require_clean_lap: bool = True,
) -> FullLapGeometry:
    """Build a full lap from already-loaded immutable source tables."""
    if max_time_offset_s <= 0.0 or observation_interval_s <= 0.0:
        raise ValueError("geometry needs positive source and observation intervals")
    lap = _select_clean_lap(laps, entry, lap_number, require_clean_lap=require_clean_lap)
    position = _select_lap_positions(position_table, entry, lap)
    car = _select_car_rows(car_table, entry)
    control_times = _lap_control_times(car, lap)
    observation_times = _fixed_observation_times(lap, observation_interval_s)
    _, position_brackets = _interpolate_position(
        position, observation_times, max_time_offset_s
    )
    observed_values, observed_brackets = _interpolate_controls(
        car, observation_times, max_time_offset_s
    )
    native_controls, control_brackets = _interpolate_controls(car, control_times, max_time_offset_s)
    raw_distance, raw_curvature = _path_geometry(position)
    raw_time_s = (position["SessionTime"] - lap["LapStartTime"]).dt.total_seconds().to_numpy(dtype=np.float64)
    query_time_s = (observation_times - lap["LapStartTime"]).total_seconds().to_numpy(dtype=np.float64)
    distance_absolute = np.interp(query_time_s, raw_time_s, raw_distance)
    distance_m = distance_absolute - distance_absolute[0]
    if distance_m[-1] <= 0.0:
        raise ValueError("full lap has no source-linked distance advance")
    values = {
        "time_s": query_time_s,
        "observed_speed_ms": observed_values["Speed"] / 3.6,
        "distance_m": distance_m,
        "progress": distance_m / distance_m[-1],
        "curvature_m_inv": np.interp(query_time_s, raw_time_s, raw_curvature),
    }
    position_index = {str(row): index for index, row in enumerate(position["source_row"])}
    if any(
        position_index[left] in {0, len(position) - 1} or position_index[right] in {0, len(position) - 1}
        for left, right in position_brackets
    ):
        raise ValueError("full lap lacks supported boundary curvature")
    lap_duration_s = (lap["Time"] - lap["LapStartTime"]).total_seconds()
    if not np.isclose(values["time_s"][0], 0.0) or not np.isclose(values["time_s"][-1], lap_duration_s):
        raise ValueError("full-lap geometry must include both lap boundaries")
    if np.any(np.diff(values["time_s"]) <= 0.0):
        raise ValueError("observation times must be strictly increasing")
    if np.any(np.diff(values["progress"]) <= 0.0):
        raise ValueError("source progress must be strictly increasing")
    if not all(np.isfinite(value).all() for value in values.values()):
        raise ValueError("matched controls and geometry must be finite")
    control_time_s = (control_times - lap["LapStartTime"]).total_seconds().to_numpy(dtype=np.float64)
    motion_derived_mask = np.asarray(
        [position_pair[0] != position_pair[1] or speed_pair[0] != speed_pair[1]
         for position_pair, speed_pair in zip(position_brackets, observed_brackets, strict=True)],
        dtype=np.bool_,
    )
    for value in values.values():
        value.setflags(write=False)
    for value in (control_time_s, native_controls["Throttle"], native_controls["Brake"], motion_derived_mask):
        value.setflags(write=False)
    return FullLapGeometry(
        position_source_rows=tuple(position["source_row"].astype(str)),
        control_source_rows=_unique_source_rows(observed_brackets + control_brackets),
        position_source_brackets=position_brackets,
        observed_speed_source_brackets=observed_brackets,
        control_source_brackets=control_brackets,
        **values,
        control_time_s=control_time_s,
        throttle_pct=native_controls["Throttle"],
        brake=native_controls["Brake"],
        motion_derived_mask=motion_derived_mask,
        lap_complete=True,
        lap_is_accurate=_known_bool(lap["IsAccurate"], expected=True),
        lap_deleted=_known_bool(lap["Deleted"], expected=True),
    )


def audit_full_race_geometry(
    laps_path: Path,
    position_path: Path,
    car_path: Path,
    entry: str,
    *,
    max_time_offset_s: float,
    observation_interval_s: float = 0.25,
    lap_boundary_tolerance_s: float = LAP_BOUNDARY_TOLERANCE_S,
) -> FullRaceGeometryAudit:
    """Audit every completed lap without joining unsupported spans into a race rollout."""
    laps = pd.read_parquet(laps_path)
    position = pd.read_parquet(position_path)
    car = pd.read_parquet(car_path)
    selected = _completed_entry_laps(laps, entry)
    race_start = _race_clock_start(laps)
    coverage: list[RaceLapCoverage] = []
    for _, lap in selected.iterrows():
        try:
            _build_full_lap_geometry(
                laps,
                position,
                car,
                entry,
                float(lap["LapNumber"]),
                max_time_offset_s=max_time_offset_s,
                observation_interval_s=observation_interval_s,
                require_clean_lap=False,
            )
        except ValueError as error:
            state = _geometry_failure_state(error, lap)
        else:
            state = _coverage_state(lap)
        coverage.append(
            RaceLapCoverage(
                lap_number=float(lap["LapNumber"]),
                start_time_s=float((lap["LapStartTime"] - race_start).total_seconds()),
                end_time_s=float((lap["Time"] - race_start).total_seconds()),
                state=state,
            )
        )
    expected_laps = np.arange(1.0, float(selected["LapNumber"].max()) + 1.0)
    complete_lap_numbers = np.array_equal(selected["LapNumber"].to_numpy(dtype=np.float64), expected_laps)
    lap_boundaries_supported = _lap_boundaries_supported(selected, lap_boundary_tolerance_s)
    return FullRaceGeometryAudit(
        entry=entry,
        lap_coverage=tuple(coverage),
        lap_boundaries_supported=lap_boundaries_supported,
        full_race_supported=(
            complete_lap_numbers
            and lap_boundaries_supported
            and all(_state_supports_rollout(item.state) for item in coverage)
        ),
    )


def build_full_race_geometry(
    laps_path: Path,
    position_path: Path,
    car_path: Path,
    entry: str,
    *,
    max_time_offset_s: float,
    observation_interval_s: float = 0.25,
    lap_boundary_tolerance_s: float = LAP_BOUNDARY_TOLERANCE_S,
) -> FullRaceGeometry:
    """Build common-clock race labels without filling unsupported source intervals."""
    laps = pd.read_parquet(laps_path)
    position = pd.read_parquet(position_path)
    car = pd.read_parquet(car_path)
    selected = _completed_entry_laps(laps, entry)
    race_start = _race_clock_start(laps)
    race_end = _race_clock_end(laps)
    duration_s = (race_end - race_start).total_seconds()
    participation_end_s = float((selected["Time"].iloc[-1] - race_start).total_seconds())
    time_s = np.arange(0.0, duration_s + 1e-12, observation_interval_s, dtype=np.float64)
    progress = np.full(len(time_s), np.nan, dtype=np.float64)
    speed_ms = np.full(len(time_s), np.nan, dtype=np.float64)
    lap_number = np.full(len(time_s), np.nan, dtype=np.float64)
    supported = np.zeros(len(time_s), dtype=np.bool_)
    derived = np.zeros(len(time_s), dtype=np.bool_)
    coverage: list[RaceLapCoverage] = []
    position_brackets: dict[float, tuple[tuple[str, str], ...]] = {}
    speed_brackets: dict[float, tuple[tuple[str, str], ...]] = {}
    common_position_brackets: list[tuple[tuple[str, str], tuple[str, str]] | None] = [None] * len(time_s)
    common_speed_brackets: list[tuple[tuple[str, str], tuple[str, str]] | None] = [None] * len(time_s)
    for _, lap in selected.iterrows():
        number = float(lap["LapNumber"])
        start_s = float((lap["LapStartTime"] - race_start).total_seconds())
        end_s = float((lap["Time"] - race_start).total_seconds())
        geometry: FullLapGeometry | None = None
        try:
            geometry = _build_full_lap_geometry(
                laps,
                position,
                car,
                entry,
                number,
                max_time_offset_s=max_time_offset_s,
                observation_interval_s=observation_interval_s,
                require_clean_lap=False,
            )
        except ValueError as error:
            state = _geometry_failure_state(error, lap)
        else:
            state = _coverage_state(lap)
        coverage.append(RaceLapCoverage(number, start_s, end_s, state))
        if geometry is None:
            continue
        include_end = np.isclose(end_s, participation_end_s)
        indices = np.flatnonzero((time_s >= start_s) & ((time_s <= end_s) if include_end else (time_s < end_s)))
        if not len(indices):
            continue
        local_time_s = time_s[indices] - start_s
        left = np.searchsorted(geometry.time_s, local_time_s, side="left")
        left = np.minimum(left, len(geometry.time_s) - 1)
        exact = geometry.time_s[left] == local_time_s
        right = left.copy()
        right[~exact] = left[~exact]
        left[~exact] -= 1
        if np.any(left < 0):
            raise ValueError("common race clock lacks a bounded lap interpolation bracket")
        progress[indices] = number - 1.0 + np.interp(local_time_s, geometry.time_s, geometry.progress)
        speed_ms[indices] = np.interp(local_time_s, geometry.time_s, geometry.observed_speed_ms)
        lap_number[indices] = number
        supported[indices] = True
        derived[indices] = (~exact) | geometry.motion_derived_mask[left] | geometry.motion_derived_mask[right]
        for output_index, left_index, right_index in zip(indices, left, right, strict=True):
            common_position_brackets[output_index] = (
                geometry.position_source_brackets[left_index], geometry.position_source_brackets[right_index]
            )
            common_speed_brackets[output_index] = (
                geometry.observed_speed_source_brackets[left_index], geometry.observed_speed_source_brackets[right_index]
            )
        position_brackets[number] = geometry.position_source_brackets
        speed_brackets[number] = geometry.observed_speed_source_brackets
    for values in (time_s, progress, speed_ms, lap_number, supported, derived):
        values.setflags(write=False)
    participation_start_s = float((selected["LapStartTime"].iloc[0] - race_start).total_seconds())
    expected_laps = np.arange(1.0, float(selected["LapNumber"].max()) + 1.0)
    complete_lap_numbers = np.array_equal(selected["LapNumber"].to_numpy(dtype=np.float64), expected_laps)
    lap_boundaries_supported = _lap_boundaries_supported(selected, lap_boundary_tolerance_s)
    participation = (time_s >= participation_start_s) & (time_s <= participation_end_s)
    return FullRaceGeometry(
        entry=entry,
        time_s=time_s,
        unwrapped_progress_laps=progress,
        observed_speed_ms=speed_ms,
        lap_number=lap_number,
        supported_mask=supported,
        derived_mask=derived,
        lap_coverage=tuple(coverage),
        lap_position_brackets=position_brackets,
        lap_speed_brackets=speed_brackets,
        participation_start_s=participation_start_s,
        participation_end_s=participation_end_s,
        lap_boundary_tolerance_s=lap_boundary_tolerance_s,
        lap_boundaries_supported=lap_boundaries_supported,
        same_checkpoint_supported=False,
        full_race_supported=(
            bool(participation.any())
            and bool(supported[participation].all())
            and complete_lap_numbers
            and lap_boundaries_supported
            and all(_state_supports_rollout(item.state) for item in coverage)
        ),
        common_position_brackets=tuple(common_position_brackets),
        common_speed_brackets=tuple(common_speed_brackets),
    )


def _select_clean_lap(
    laps: pd.DataFrame, entry: str, lap_number: float, *, require_clean_lap: bool = True
) -> pd.Series:
    selected = laps.loc[
        (laps["DriverNumber"].astype(str) == entry) & (laps["LapNumber"] == lap_number)
    ]
    if len(selected) != 1:
        raise ValueError("expected exactly one source lap")
    lap = selected.iloc[0]
    if (
        pd.isna(lap["LapStartTime"])
        or pd.isna(lap["Time"])
        or lap["Time"] <= lap["LapStartTime"]
    ):
        raise ValueError("full-lap geometry needs valid lap boundaries")
    if require_clean_lap and not _timing_clean(lap):
        raise ValueError("full-lap geometry needs a clean timed lap")
    return lap


def _timing_clean(lap: pd.Series) -> bool:
    return _known_bool(lap["IsAccurate"], expected=True) and _known_bool(lap["Deleted"], expected=False)


def _pit_lap(lap: pd.Series) -> bool:
    return pd.notna(lap["PitInTime"]) or pd.notna(lap["PitOutTime"])


def _coverage_state(lap: pd.Series) -> str:
    if _pit_lap(lap):
        return "pit_geometry_present"
    timing_masked = not _timing_clean(lap)
    event_masked = _event_masked(lap)
    if timing_masked and event_masked:
        return "timing_and_event_masked_geometry_present"
    if timing_masked:
        return "timing_masked_geometry_present"
    if event_masked:
        return "event_masked_geometry_present"
    return "supported"


def _state_supports_rollout(state: str) -> bool:
    return state in {
        "supported",
        "timing_masked_geometry_present",
        "event_masked_geometry_present",
        "timing_and_event_masked_geometry_present",
    }


def _event_masked(lap: pd.Series) -> bool:
    return "TrackStatus" in lap and str(lap["TrackStatus"]) != "1"


def _completed_entry_laps(laps: pd.DataFrame, entry: str) -> pd.DataFrame:
    selected = laps.loc[
        (laps["DriverNumber"].astype(str) == entry)
        & laps["LapNumber"].notna()
        & laps["LapStartTime"].notna()
        & laps["Time"].notna()
    ].sort_values("LapStartTime")
    if selected.empty or selected["LapStartTime"].duplicated().any():
        raise ValueError("race geometry needs ordered completed source laps")
    return selected


def _lap_boundaries_supported(laps: pd.DataFrame, tolerance_s: float) -> bool:
    if tolerance_s < 0.0:
        raise ValueError("lap boundary tolerance must be non-negative")
    if len(laps) < 2:
        return True
    gap_s = (laps["LapStartTime"].iloc[1:].reset_index(drop=True) - laps["Time"].iloc[:-1].reset_index(drop=True)).dt.total_seconds()
    return bool((gap_s.abs() <= tolerance_s).all())


def _race_clock_start(laps: pd.DataFrame) -> pd.Timedelta:
    starts = laps.loc[laps["LapStartTime"].notna(), "LapStartTime"]
    if starts.empty:
        raise ValueError("race geometry needs a field clock origin")
    return starts.min()


def _race_clock_end(laps: pd.DataFrame) -> pd.Timedelta:
    ends = laps.loc[laps["Time"].notna(), "Time"]
    if ends.empty:
        raise ValueError("race geometry needs a field clock end")
    return ends.max()


def _geometry_failure_state(error: ValueError, lap: pd.Series) -> str:
    message = str(error)
    if "bounded interpolation bracket" in message:
        state = "source_gap_unsupported"
    elif "on-track" in message:
        state = "path_unsupported"
    elif "curvature" in message:
        state = "curvature_unsupported"
    else:
        state = "geometry_unsupported"
    if _pit_lap(lap):
        return f"pit_{state}"
    return state


def _select_lap_positions(position: pd.DataFrame, entry: str, lap: pd.Series) -> pd.DataFrame:
    required = {"source_row", "DriverNumber", "SessionTime", "X", "Y", "Status"}
    if not required.issubset(position.columns):
        raise ValueError("position table lacks source-linked geometry fields")
    selected = position.loc[position["DriverNumber"].astype(str) == entry].sort_values("SessionTime").copy()
    if len(selected) < 3 or not selected["SessionTime"].is_monotonic_increasing:
        raise ValueError("full lap lacks ordered position samples")
    if selected["SessionTime"].duplicated().any():
        raise ValueError("position samples have duplicate timestamps")
    inside = selected["SessionTime"].between(lap["LapStartTime"], lap["Time"])
    if not inside.any():
        raise ValueError("full lap lacks position samples")
    first = max(0, int(np.flatnonzero(inside.to_numpy())[0]) - 2)
    last = min(len(selected) - 1, int(np.flatnonzero(inside.to_numpy())[-1]) + 2)
    selected = selected.iloc[first : last + 1].reset_index(drop=True)
    if selected["SessionTime"].iloc[1] >= lap["LapStartTime"] or selected["SessionTime"].iloc[-2] <= lap["Time"]:
        raise ValueError("full lap lacks source brackets at both boundaries")
    if not selected["Status"].eq("OnTrack").all():
        raise ValueError("full-lap geometry requires on-track position samples")
    if not np.isfinite(selected[["X", "Y"]].to_numpy(dtype=np.float64)).all():
        raise ValueError("full-lap geometry requires finite coordinates")
    changed = selected[["X", "Y"]].ne(selected[["X", "Y"]].shift()).any(axis=1)
    selected = selected.loc[changed].reset_index(drop=True)
    if len(selected) < 3:
        raise ValueError("full lap has insufficient advancing coordinates")
    return selected


def _path_geometry(position: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    x_m = position["X"].to_numpy(dtype=np.float64) * 0.1
    y_m = position["Y"].to_numpy(dtype=np.float64) * 0.1
    step_m = np.hypot(np.diff(x_m), np.diff(y_m))
    if np.any(step_m <= 0.0):
        raise ValueError("full-lap coordinates must advance")
    distance_m = np.concatenate(([0.0], np.cumsum(step_m)))
    dx = np.gradient(x_m, distance_m, edge_order=1)
    dy = np.gradient(y_m, distance_m, edge_order=1)
    ddx = np.gradient(dx, distance_m, edge_order=1)
    ddy = np.gradient(dy, distance_m, edge_order=1)
    curvature = (dx * ddy - dy * ddx) / np.hypot(dx, dy) ** 3
    if not np.isfinite(curvature).all():
        raise ValueError("full-lap curvature must be finite")
    return distance_m, curvature


def _select_car_rows(car: pd.DataFrame, entry: str) -> pd.DataFrame:
    required = {"source_row", "DriverNumber", "SessionTime", "Speed", "Throttle", "Brake"}
    if not required.issubset(car.columns):
        raise ValueError("car table lacks recorded control fields")
    controls = car.loc[car["DriverNumber"].astype(str) == entry].sort_values("SessionTime").copy()
    if controls.empty or controls["SessionTime"].duplicated().any():
        raise ValueError("recorded controls need unique timestamps")
    numeric = controls[["Speed", "Throttle", "Brake"]].to_numpy(dtype=np.float64)
    if (
        not np.isfinite(numeric).all()
        or (controls["Speed"] < 0.0).any()
        or (controls["Brake"] < 0.0).any()
        or (controls["Brake"] > 1.0).any()
        or (controls["Throttle"] < 0.0).any()
    ):
        raise ValueError("recorded controls must be finite and non-negative")
    return controls.reset_index(drop=True)


def _lap_control_times(car: pd.DataFrame, lap: pd.Series) -> pd.TimedeltaIndex:
    inside = car.loc[
        car["SessionTime"].between(lap["LapStartTime"], lap["Time"]), "SessionTime"
    ]
    query = pd.TimedeltaIndex([lap["LapStartTime"], *inside, lap["Time"]]).unique().sort_values()
    if len(query) < 3:
        raise ValueError("full lap lacks recorded control samples")
    return query


def _fixed_observation_times(lap: pd.Series, interval_s: float) -> pd.TimedeltaIndex:
    duration_s = (lap["Time"] - lap["LapStartTime"]).total_seconds()
    offsets_s = np.arange(0.0, duration_s, interval_s, dtype=np.float64)
    if not np.isclose(offsets_s[-1], duration_s):
        offsets_s = np.append(offsets_s, duration_s)
    return pd.TimedeltaIndex(lap["LapStartTime"] + pd.to_timedelta(offsets_s, unit="s"))


def _interpolate_position(
    position: pd.DataFrame, query: pd.TimedeltaIndex, max_time_offset_s: float
) -> tuple[dict[str, np.ndarray], tuple[tuple[str, str], ...]]:
    values, brackets = _interpolate_columns(position, query, ("X", "Y"), max_time_offset_s)
    return values, brackets


def _interpolate_controls(
    car: pd.DataFrame, query: pd.TimedeltaIndex, max_time_offset_s: float
) -> tuple[dict[str, np.ndarray], tuple[tuple[str, str], ...]]:
    return _interpolate_columns(car, query, ("Speed", "Throttle", "Brake"), max_time_offset_s)


def _interpolate_columns(
    source: pd.DataFrame,
    query: pd.TimedeltaIndex,
    columns: tuple[str, ...],
    max_time_offset_s: float,
) -> tuple[dict[str, np.ndarray], tuple[tuple[str, str], ...]]:
    source_time = source["SessionTime"].to_numpy(dtype="timedelta64[ns]").astype(np.int64)
    query_time = query.to_numpy(dtype="timedelta64[ns]").astype(np.int64)
    result = {name: np.empty(len(query), dtype=np.float64) for name in columns}
    source_values = {name: source[name].to_numpy(dtype=np.float64) for name in columns}
    brackets: list[tuple[str, str]] = []
    max_gap_ns = int(max_time_offset_s * 1_000_000_000)
    for index, moment in enumerate(query_time):
        right = int(np.searchsorted(source_time, moment, side="left"))
        if right < len(source_time) and source_time[right] == moment:
            left = right
        else:
            left = right - 1
        if left < 0 or right >= len(source_time) or source_time[right] - source_time[left] > max_gap_ns:
            raise ValueError("source samples lack a bounded interpolation bracket")
        fraction = 0.0 if left == right else (moment - source_time[left]) / (source_time[right] - source_time[left])
        for name in columns:
            values = source_values[name]
            result[name][index] = values[left] + fraction * (values[right] - values[left])
        brackets.append((str(source.iloc[left]["source_row"]), str(source.iloc[right]["source_row"])))
    return result, tuple(brackets)


def _unique_source_rows(brackets: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(row for pair in brackets for row in pair))


def _known_bool(value: object, *, expected: bool) -> bool:
    return not pd.isna(value) and bool(value) is expected


def road_at_predicted_progress(geometry: FullLapGeometry, predicted_progress: np.ndarray) -> np.ndarray:
    """Return source curvature for predicted canonical metre progress."""
    progress_m = np.asarray(predicted_progress, dtype=np.float64)
    lap_length_m = geometry.distance_m[-1]
    tolerance_m = max(1e-9, lap_length_m * 1e-12)
    if (
        not np.isfinite(progress_m).all()
        or np.any(progress_m < -tolerance_m)
        or np.any(progress_m > lap_length_m + tolerance_m)
    ):
        raise ValueError("predicted progress must stay within the supported lap")
    progress = np.clip(progress_m, 0.0, lap_length_m) / lap_length_m
    curvature = np.interp(progress, geometry.progress, geometry.curvature_m_inv)
    return np.stack((curvature, np.ones_like(curvature)), axis=-1)


def source_progress_at_wall_time(geometry: FullLapGeometry, wall_time_s: np.ndarray) -> np.ndarray:
    """Return source-derived progress at supported lap-clock times."""
    time_s = np.asarray(wall_time_s, dtype=np.float64)
    if not np.isfinite(time_s).all() or np.any(time_s < 0.0) or np.any(time_s > geometry.time_s[-1]):
        raise ValueError("wall time must stay within the supported lap")
    return np.interp(time_s, geometry.time_s, geometry.progress)


def source_crossing_time_at_progress(geometry: FullLapGeometry, progress: np.ndarray) -> np.ndarray:
    """Return source-derived first crossing times for supported checkpoints."""
    values = np.asarray(progress, dtype=np.float64)
    if not np.isfinite(values).all() or np.any(values < 0.0) or np.any(values > 1.0):
        raise ValueError("checkpoint progress must stay within the supported lap")
    return np.interp(values, geometry.progress, geometry.time_s)


def source_crossing_time_at_unwrapped_progress(
    geometry: FullRaceGeometry, progress_laps: np.ndarray
) -> SourceCrossingTimes:
    """Return supported common-clock crossings without bridging masked intervals."""
    checkpoints = np.asarray(progress_laps, dtype=np.float64)
    if not np.isfinite(checkpoints).all() or np.any(checkpoints < 0.0):
        raise ValueError("race checkpoints must be finite non-negative progress")
    crossing_time = np.full(checkpoints.shape, np.nan, dtype=np.float64)
    valid = np.zeros(checkpoints.shape, dtype=np.bool_)
    left = geometry.unwrapped_progress_laps[:-1]
    right = geometry.unwrapped_progress_laps[1:]
    segment_support = geometry.supported_mask[:-1] & geometry.supported_mask[1:]
    segment_support &= np.diff(geometry.time_s) <= 0.25 + 1e-12
    for index, checkpoint in np.ndenumerate(checkpoints):
        matching = np.flatnonzero(segment_support & (left <= checkpoint) & (checkpoint <= right))
        if len(matching):
            segment = int(matching[0])
            span = right[segment] - left[segment]
            fraction = 0.0 if span == 0.0 else (checkpoint - left[segment]) / span
            crossing_time[index] = geometry.time_s[segment] + fraction * (
                geometry.time_s[segment + 1] - geometry.time_s[segment]
            )
            valid[index] = True
    crossing_time.setflags(write=False)
    valid.setflags(write=False)
    return SourceCrossingTimes(time_s=crossing_time, supported_mask=valid)


def write_full_lap_geometry_artifact(
    geometry: FullLapGeometry,
    output_dir: Path,
    *,
    source_manifest_path: str,
    source_manifest_sha256: str,
    config: dict[str, float | str],
) -> Path:
    """Write an immutable source-bound geometry fixture for downstream integration."""
    output_dir.mkdir(parents=True, exist_ok=True)
    arrays_path = output_dir / "geometry.npz"
    candidate = output_dir / "geometry.candidate.npz"
    arrays = {
        "time_s": geometry.time_s,
        "control_time_s": geometry.control_time_s,
        "observed_speed_ms": geometry.observed_speed_ms,
        "throttle_pct": geometry.throttle_pct,
        "brake": geometry.brake,
        "distance_m": geometry.distance_m,
        "progress": geometry.progress,
        "curvature_m_inv": geometry.curvature_m_inv,
        "motion_derived_mask": geometry.motion_derived_mask,
    }
    np.savez_compressed(candidate, **arrays)
    arrays_hash = sha256(candidate.read_bytes()).hexdigest()
    if arrays_path.exists() and sha256(arrays_path.read_bytes()).hexdigest() != arrays_hash:
        candidate.unlink()
        raise FileExistsError(f"immutable geometry differs: {arrays_path}")
    candidate.replace(arrays_path)
    payload = {
        "artifact_kind": "source_bound_full_lap_geometry_v1",
        "arrays": {name: {"dtype": str(value.dtype), "shape": list(value.shape)} for name, value in arrays.items()},
        "arrays_path": arrays_path.name,
        "arrays_sha256": arrays_hash,
        "config": config,
        "control_source_brackets": geometry.control_source_brackets,
        "control_source_rows": geometry.control_source_rows,
        "geometry_scope": "single supported lap; not a full-race rollout",
        "lap_status": {
            "complete": geometry.lap_complete,
            "deleted": geometry.lap_deleted,
            "is_accurate": geometry.lap_is_accurate,
        },
        "observed_speed_source_brackets": geometry.observed_speed_source_brackets,
        "position_source_brackets": geometry.position_source_brackets,
        "position_source_rows": geometry.position_source_rows,
        "source_binding": {
            "manifest_path": source_manifest_path,
            "manifest_sha256": source_manifest_sha256,
        },
        "units": {
            "distance_m": "m",
            "observed_speed_ms": "m/s",
            "source_position": geometry.source_position_unit,
            "source_speed": geometry.source_speed_unit,
            "time_s": "s",
        },
    }
    manifest_path = output_dir / "geometry_manifest.json"
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    digest = sha256(content.encode()).hexdigest()
    if manifest_path.exists() and sha256(manifest_path.read_bytes()).hexdigest() != digest:
        raise FileExistsError(f"immutable geometry manifest differs: {manifest_path}")
    manifest_path.write_text(content)
    return manifest_path


def write_full_race_geometry_artifact(
    geometry: FullRaceGeometry,
    output_dir: Path,
    *,
    source_manifest_path: str,
    source_manifest_sha256: str,
    config: dict[str, float | str],
) -> Path:
    """Write immutable common-clock race labels and their unsupported coverage."""
    output_dir.mkdir(parents=True, exist_ok=True)
    arrays_path = output_dir / "race_geometry.npz"
    candidate = output_dir / "race_geometry.candidate.npz"
    arrays = {
        "time_s": geometry.time_s,
        "unwrapped_progress_laps": geometry.unwrapped_progress_laps,
        "observed_speed_ms": geometry.observed_speed_ms,
        "lap_number": geometry.lap_number,
        "supported_mask": geometry.supported_mask,
        "derived_mask": geometry.derived_mask,
    }
    np.savez_compressed(candidate, **arrays)
    arrays_hash = sha256(candidate.read_bytes()).hexdigest()
    if arrays_path.exists() and sha256(arrays_path.read_bytes()).hexdigest() != arrays_hash:
        candidate.unlink()
        raise FileExistsError(f"immutable race geometry differs: {arrays_path}")
    candidate.replace(arrays_path)
    payload = {
        "artifact_kind": "source_bound_full_race_geometry_v1",
        "arrays": {name: {"dtype": str(value.dtype), "shape": list(value.shape)} for name, value in arrays.items()},
        "arrays_path": arrays_path.name,
        "arrays_sha256": arrays_hash,
        "config": config,
        "entry": geometry.entry,
        "full_race_supported": geometry.full_race_supported,
        "geometry_scope": "diagnostic common-clock labels; not engine-ready shared checkpoints",
        "lap_coverage": [item.__dict__ for item in geometry.lap_coverage],
        "lap_boundary_tolerance_s": geometry.lap_boundary_tolerance_s,
        "lap_boundaries_supported": geometry.lap_boundaries_supported,
        "lap_position_brackets": geometry.lap_position_brackets,
        "lap_speed_brackets": geometry.lap_speed_brackets,
        "participation_window_s": [geometry.participation_start_s, geometry.participation_end_s],
        "same_checkpoint_supported": geometry.same_checkpoint_supported,
        "common_position_source_brackets": geometry.common_position_brackets,
        "common_speed_source_brackets": geometry.common_speed_brackets,
        "source_binding": {
            "manifest_path": source_manifest_path,
            "manifest_sha256": source_manifest_sha256,
        },
        "units": {
            "observed_speed_ms": "m/s",
            "time_s": "s",
            "unwrapped_progress_laps": "laps",
        },
    }
    manifest_path = output_dir / "race_geometry_manifest.json"
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    digest = sha256(content.encode()).hexdigest()
    if manifest_path.exists() and sha256(manifest_path.read_bytes()).hexdigest() != digest:
        raise FileExistsError(f"immutable race geometry manifest differs: {manifest_path}")
    manifest_path.write_text(content)
    return manifest_path
