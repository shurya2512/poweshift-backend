"""Project source positions onto one static metric race route."""

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd

ROUTE_PROJECTION_BATCH_SIZE = 1024

@dataclass(frozen=True)
class RouteProjectionConfig:
    """Frozen support limits for route and control reconstruction."""

    max_route_distance_m: float
    branch_ambiguity_separation_m: float
    branch_neighborhood_m: float
    max_closure_m: float
    max_seam_heading_delta_deg: float
    control_max_offset_s: float


@dataclass(frozen=True)
class StaticRaceRoute:
    """A metric route built from named recorded position rows."""

    source_rows: tuple[str, ...]
    x_m: np.ndarray
    y_m: np.ndarray
    distance_m: np.ndarray
    curvature_m_inv: np.ndarray
    closed: bool = False
    loop_closure_m: float = np.nan
    seam_heading_delta_deg: float = np.nan
    boundary_source_brackets: tuple[tuple[str, str], tuple[str, str]] | None = None


@dataclass(frozen=True)
class RouteProjection:
    """Source positions mapped to a route or retained as unsupported."""

    source_rows: tuple[str, ...]
    distance_m: np.ndarray
    supported_mask: np.ndarray


@dataclass(frozen=True)
class ControlInterpolation:
    """Recorded controls with unsupported brackets left empty."""

    throttle_pct: np.ndarray
    brake: np.ndarray
    supported_mask: np.ndarray
    inferred_mask: np.ndarray
    source_brackets: tuple[tuple[str, str] | None, ...]


@dataclass(frozen=True)
class LapSourceStreams:
    """One lap's source-linked route and control observations."""

    time_s: np.ndarray
    route_progress_m: np.ndarray
    position_supported_mask: np.ndarray
    position_source_brackets: tuple[tuple[str, str] | None, ...]
    throttle_pct: np.ndarray
    brake: np.ndarray
    control_supported_mask: np.ndarray
    control_inferred_mask: np.ndarray
    control_source_brackets: tuple[tuple[str, str] | None, ...]


@dataclass(frozen=True)
class CheckpointCrossings:
    """Checkpoint times that never bridge unsupported progress rows."""

    time_s: np.ndarray
    supported_mask: np.ndarray


@dataclass(frozen=True)
class LapFinishCrossing:
    """A source-timed finish event with a bracketed route crossing."""

    official_time_s: float
    spatial_crossing_time_s: float
    supported: bool
    position_source_bracket: tuple[str, str] | None
    source_cutoff_extension_s: float


def build_static_route(position_rows: pd.DataFrame) -> StaticRaceRoute:
    """Build a metric route from one ordered source-linked position sequence."""
    required = {"source_row", "X", "Y"}
    if not required.issubset(position_rows.columns):
        raise ValueError("route needs source-linked X/Y rows")
    rows = position_rows.copy()
    source_rows = tuple(rows["source_row"].astype(str))
    x_m = rows["X"].to_numpy(dtype=np.float64) * 0.1
    y_m = rows["Y"].to_numpy(dtype=np.float64) * 0.1
    step_m = np.hypot(np.diff(x_m), np.diff(y_m))
    if len(rows) < 3 or len(set(source_rows)) != len(source_rows) or not np.isfinite(step_m).all() or np.any(step_m <= 0.0):
        raise ValueError("route needs unique finite advancing coordinates")
    distance_m = np.concatenate(([0.0], np.cumsum(step_m)))
    dx = np.gradient(x_m, distance_m, edge_order=1)
    dy = np.gradient(y_m, distance_m, edge_order=1)
    ddx = np.gradient(dx, distance_m, edge_order=1)
    ddy = np.gradient(dy, distance_m, edge_order=1)
    curvature = (dx * ddy - dy * ddx) / np.hypot(dx, dy) ** 3
    if not np.isfinite(curvature).all():
        raise ValueError("route needs finite curvature")
    for values in (x_m, y_m, distance_m, curvature):
        values.setflags(write=False)
    return StaticRaceRoute(
        source_rows=source_rows,
        x_m=x_m,
        y_m=y_m,
        distance_m=distance_m,
        curvature_m_inv=curvature,
    )


def build_closed_static_route(
    position_rows: pd.DataFrame,
    *,
    start_xy_decimetres: tuple[float, float],
    end_xy_decimetres: tuple[float, float],
    boundary_source_brackets: tuple[tuple[str, str], tuple[str, str]],
    max_closure_m: float,
    max_seam_heading_delta_deg: float,
) -> StaticRaceRoute:
    """Close a route only when its source-bounded endpoints agree."""
    if max_closure_m <= 0.0 or max_seam_heading_delta_deg < 0.0:
        raise ValueError("route closure limits must be valid")
    start = np.asarray(start_xy_decimetres, dtype=np.float64) * 0.1
    end = np.asarray(end_xy_decimetres, dtype=np.float64) * 0.1
    closure_m = float(np.hypot(*(end - start)))
    if not np.isfinite(start).all() or not np.isfinite(end).all() or closure_m > max_closure_m:
        raise ValueError("source-bounded route endpoints do not close")
    datum = (start + end) / 2.0
    rows = position_rows.copy()
    rows = pd.concat(
        [
            pd.DataFrame({"source_row": ["__start_finish__"], "X": [datum[0] / 0.1], "Y": [datum[1] / 0.1]}),
            rows,
            pd.DataFrame({"source_row": ["__closure__"], "X": [datum[0] / 0.1], "Y": [datum[1] / 0.1]}),
        ],
        ignore_index=True,
    )
    route = build_static_route(rows)
    first = np.array((route.x_m[1] - route.x_m[0], route.y_m[1] - route.y_m[0]))
    last = np.array((route.x_m[-1] - route.x_m[-2], route.y_m[-1] - route.y_m[-2]))
    heading_delta_deg = float(np.degrees(np.arccos(np.clip(np.dot(first, last) / (np.linalg.norm(first) * np.linalg.norm(last)), -1.0, 1.0))))
    if heading_delta_deg > max_seam_heading_delta_deg:
        raise ValueError("source-bounded route seam has a heading discontinuity")
    return StaticRaceRoute(
        source_rows=route.source_rows,
        x_m=route.x_m,
        y_m=route.y_m,
        distance_m=route.distance_m,
        curvature_m_inv=route.curvature_m_inv,
        closed=True,
        loop_closure_m=closure_m,
        seam_heading_delta_deg=heading_delta_deg,
        boundary_source_brackets=boundary_source_brackets,
    )


def build_closed_route_for_lap(
    position: pd.DataFrame,
    lap_start: pd.Timedelta,
    lap_end: pd.Timedelta,
    config: RouteProjectionConfig,
    *,
    position_max_offset_s: float,
) -> StaticRaceRoute:
    """Build a closed source route from one full recorded lap."""
    _validate_config(config)
    endpoints, supported, brackets = _interpolate_position_with_mask(
        position, pd.TimedeltaIndex([lap_start, lap_end]), position_max_offset_s
    )
    if not supported.all() or brackets[0] is None or brackets[1] is None:
        raise ValueError("route lap lacks bounded start-finish position brackets")
    interior = position.loc[position["SessionTime"].between(lap_start, lap_end)].sort_values("SessionTime")
    advancing = interior[["X", "Y"]].ne(interior[["X", "Y"]].shift()).any(axis=1)
    interior = interior.loc[advancing]
    return build_closed_static_route(
        interior,
        start_xy_decimetres=tuple(endpoints[0] / 0.1),
        end_xy_decimetres=tuple(endpoints[1] / 0.1),
        boundary_source_brackets=(brackets[0], brackets[1]),
        max_closure_m=config.max_closure_m,
        max_seam_heading_delta_deg=config.max_seam_heading_delta_deg,
    )


def project_positions_to_route(
    observations: pd.DataFrame, route: StaticRaceRoute, config: RouteProjectionConfig
) -> RouteProjection:
    """Map finite source positions to unambiguous route distances."""
    _validate_config(config)
    required = {"source_row", "X", "Y"}
    if not required.issubset(observations.columns):
        raise ValueError("projection needs source-linked X/Y rows")
    source_rows = tuple(observations["source_row"].astype(str))
    points = observations[["X", "Y"]].to_numpy(dtype=np.float64) * 0.1
    if len(set(source_rows)) != len(source_rows) or not np.isfinite(points).all():
        raise ValueError("projection needs unique finite coordinates")
    start = np.column_stack((route.x_m[:-1], route.y_m[:-1]))
    segment = np.diff(np.column_stack((route.x_m, route.y_m)), axis=0)
    length_sq = np.einsum("ij,ij->i", segment, segment)
    projected = np.full(len(points), np.nan, dtype=np.float64)
    supported = np.zeros(len(points), dtype=np.bool_)
    for start_index in range(0, len(points), ROUTE_PROJECTION_BATCH_SIZE):
        end_index = min(len(points), start_index + ROUTE_PROJECTION_BATCH_SIZE)
        point_batch = points[start_index:end_index]
        offset = point_batch[:, None, :] - start[None, :, :]
        fraction = np.clip(np.einsum("bij,ij->bi", offset, segment) / length_sq, 0.0, 1.0)
        closest = start[None, :, :] + fraction[:, :, None] * segment[None, :, :]
        distance = np.sqrt(((point_batch[:, None, :] - closest) ** 2).sum(axis=2))
        nearest = np.argmin(distance, axis=1)
        nearest_distance = distance[np.arange(len(point_batch)), nearest]
        branch_distance = _nearest_nonadjacent_distance(
            distance, nearest, route.distance_m, config.branch_neighborhood_m, closed=route.closed
        )
        batch_supported = (nearest_distance <= config.max_route_distance_m) & (
            branch_distance - nearest_distance > config.branch_ambiguity_separation_m
        )
        projected[start_index:end_index] = route.distance_m[nearest] + fraction[np.arange(len(point_batch)), nearest] * np.sqrt(length_sq[nearest])
        supported[start_index:end_index] = batch_supported
    projected[~supported] = np.nan
    projected.setflags(write=False)
    supported.setflags(write=False)
    return RouteProjection(source_rows=source_rows, distance_m=projected, supported_mask=supported)


def interpolate_controls_with_mask(
    controls: pd.DataFrame, query: pd.TimedeltaIndex, *, max_time_offset_s: float
) -> ControlInterpolation:
    """Interpolate only recorded control brackets within the frozen limit."""
    if max_time_offset_s <= 0.0:
        raise ValueError("control limit must be positive")
    required = {"source_row", "SessionTime", "Throttle", "Brake"}
    if not required.issubset(controls.columns):
        raise ValueError("controls need source rows, time, throttle and brake")
    ordered = controls.sort_values("SessionTime").reset_index(drop=True)
    source_time = ordered["SessionTime"].to_numpy(dtype="timedelta64[ns]").astype(np.int64)
    values = ordered[["Throttle", "Brake"]].to_numpy(dtype=np.float64)
    if len(source_time) == 0 or np.any(np.diff(source_time) <= 0) or not np.isfinite(values).all():
        raise ValueError("controls need unique finite timestamps and values")
    query_time = query.to_numpy(dtype="timedelta64[ns]").astype(np.int64)
    right = np.searchsorted(source_time, query_time, side="left")
    exact = (right < len(source_time)) & (source_time[np.minimum(right, len(source_time) - 1)] == query_time)
    left = np.where(exact, right, right - 1)
    supported = (left >= 0) & (right < len(source_time))
    widths = np.full(len(query), np.inf)
    valid = supported.copy()
    widths[valid] = (source_time[right[valid]] - source_time[left[valid]]) / 1_000_000_000
    supported &= widths <= max_time_offset_s
    throttle = np.full(len(query), np.nan, dtype=np.float64)
    brake = np.full(len(query), np.nan, dtype=np.float64)
    brackets: list[tuple[str, str] | None] = [None] * len(query)
    for index in np.flatnonzero(supported):
        fraction = 0.0 if left[index] == right[index] else (query_time[index] - source_time[left[index]]) / (source_time[right[index]] - source_time[left[index]])
        throttle[index] = values[left[index], 0] + fraction * (values[right[index], 0] - values[left[index], 0])
        brake[index] = values[left[index], 1] + fraction * (values[right[index], 1] - values[left[index], 1])
        brackets[index] = (str(ordered.iloc[left[index]]["source_row"]), str(ordered.iloc[right[index]]["source_row"]))
    inferred = supported & ~exact
    for value in (throttle, brake, supported, inferred):
        value.setflags(write=False)
    return ControlInterpolation(
        throttle_pct=throttle,
        brake=brake,
        supported_mask=supported,
        inferred_mask=inferred,
        source_brackets=tuple(brackets),
    )


def build_lap_source_streams(
    position: pd.DataFrame,
    controls: pd.DataFrame,
    lap_start: pd.Timedelta,
    lap_end: pd.Timedelta,
    route: StaticRaceRoute,
    config: RouteProjectionConfig,
    *,
    position_max_offset_s: float,
    observation_interval_s: float = 0.25,
) -> LapSourceStreams:
    """Build masked source streams for one continuous observed lap."""
    _validate_config(config)
    if position_max_offset_s <= 0.0 or observation_interval_s <= 0.0 or lap_end <= lap_start:
        raise ValueError("lap stream needs positive source bounds and duration")
    duration_s = (lap_end - lap_start).total_seconds()
    offsets_s = np.arange(0.0, duration_s, observation_interval_s, dtype=np.float64)
    if not np.isclose(offsets_s[-1], duration_s):
        offsets_s = np.append(offsets_s, duration_s)
    query = pd.TimedeltaIndex(lap_start + pd.to_timedelta(offsets_s, unit="s"))
    points, position_supported, position_brackets = _interpolate_position_with_mask(
        position, query, position_max_offset_s
    )
    route_progress = np.full(len(query), np.nan, dtype=np.float64)
    if position_supported.any():
        projection = project_positions_to_route(
            pd.DataFrame(
                {
                    "source_row": [str(index) for index in np.flatnonzero(position_supported)],
                    "X": points[position_supported, 0] / 0.1,
                    "Y": points[position_supported, 1] / 0.1,
                }
            ),
            route,
            config,
        )
        supported_indices = np.flatnonzero(position_supported)
        route_progress[supported_indices] = projection.distance_m
        position_supported[supported_indices] &= projection.supported_mask
    control = interpolate_controls_with_mask(controls, query, max_time_offset_s=config.control_max_offset_s)
    for values in (
        offsets_s,
        route_progress,
        position_supported,
    ):
        values.setflags(write=False)
    return LapSourceStreams(
        time_s=offsets_s,
        route_progress_m=route_progress,
        position_supported_mask=position_supported,
        position_source_brackets=position_brackets,
        throttle_pct=control.throttle_pct,
        brake=control.brake,
        control_supported_mask=control.supported_mask,
        control_inferred_mask=control.inferred_mask,
        control_source_brackets=control.source_brackets,
    )


def bounded_checkpoint_times(
    progress_m: np.ndarray, time_s: np.ndarray, supported_mask: np.ndarray, checkpoints_m: np.ndarray
) -> CheckpointCrossings:
    """Interpolate crossings only inside supported increasing progress segments."""
    progress = np.asarray(progress_m, dtype=np.float64)
    time = np.asarray(time_s, dtype=np.float64)
    supported = np.asarray(supported_mask, dtype=np.bool_)
    checkpoints = np.asarray(checkpoints_m, dtype=np.float64)
    if progress.ndim != 1 or time.shape != progress.shape or supported.shape != progress.shape or not np.isfinite(time).all() or np.any(np.diff(time) <= 0.0):
        raise ValueError("checkpoint inputs need increasing one-dimensional time")
    if not np.isfinite(checkpoints).all():
        raise ValueError("checkpoints must be finite")
    crossing_time = np.full(checkpoints.shape, np.nan, dtype=np.float64)
    crossing_supported = np.zeros(checkpoints.shape, dtype=np.bool_)
    segment_supported = supported[:-1] & supported[1:] & np.isfinite(progress[:-1]) & np.isfinite(progress[1:]) & (np.diff(progress) > 0.0)
    for index, checkpoint in np.ndenumerate(checkpoints):
        exact = np.flatnonzero(supported & (progress == checkpoint))
        if len(exact):
            crossing_time[index] = time[exact[0]]
            crossing_supported[index] = True
            continue
        segment = np.flatnonzero(segment_supported & (progress[:-1] < checkpoint) & (checkpoint < progress[1:]))
        if len(segment):
            left = int(segment[0])
            fraction = (checkpoint - progress[left]) / (progress[left + 1] - progress[left])
            crossing_time[index] = time[left] + fraction * (time[left + 1] - time[left])
            crossing_supported[index] = True
    crossing_time.setflags(write=False)
    crossing_supported.setflags(write=False)
    return CheckpointCrossings(time_s=crossing_time, supported_mask=crossing_supported)


def unwrap_route_progress(
    progress_m: np.ndarray,
    supported_mask: np.ndarray,
    *,
    route_length_m: float,
    start_near_datum: bool = False,
) -> np.ndarray:
    """Unwrap forward route seams while preserving each source coordinate."""
    progress = np.asarray(progress_m, dtype=np.float64)
    supported = np.asarray(supported_mask, dtype=np.bool_)
    if progress.ndim != 1 or supported.shape != progress.shape or route_length_m <= 0.0:
        raise ValueError("progress needs a matching mask and positive route length")
    unwrapped = np.full(progress.shape, np.nan, dtype=np.float64)
    offset = 0.0
    previous: float | None = None
    for index, value in enumerate(progress):
        if not supported[index] or not np.isfinite(value):
            previous = None
            continue
        if previous is None and start_near_datum and value > route_length_m / 2.0:
            offset = -route_length_m
        if previous is not None and value < previous - route_length_m / 2.0:
            offset += route_length_m
        unwrapped[index] = value + offset
        previous = value
    unwrapped.setflags(write=False)
    return unwrapped


def source_finish_crossing(
    position: pd.DataFrame,
    lap_start: pd.Timedelta,
    lap_end: pd.Timedelta,
    route: StaticRaceRoute,
    config: RouteProjectionConfig,
    *,
    position_max_offset_s: float,
    post_lap_margin_s: float,
) -> LapFinishCrossing:
    """Locate the route datum using bounded source positions around lap end."""
    if position_max_offset_s <= 0.0 or post_lap_margin_s < 0.0 or lap_end <= lap_start:
        raise ValueError("finish crossing needs valid lap and position bounds")
    rows = position.loc[position["SessionTime"].between(lap_start, lap_end + pd.Timedelta(seconds=post_lap_margin_s))].sort_values("SessionTime")
    if len(rows) < 2:
        return _unsupported_finish_crossing(lap_start, lap_end)
    projection = project_positions_to_route(rows, route, config)
    times = rows["SessionTime"].to_numpy(dtype="timedelta64[ns]").astype(np.int64)
    progress = unwrap_route_progress(
        projection.distance_m,
        projection.supported_mask,
        route_length_m=route.distance_m[-1],
        start_near_datum=True,
    )
    lap_end_ns = lap_end.to_timedelta64().astype("timedelta64[ns]").astype(np.int64)
    for index in range(len(rows) - 1):
        left_time, right_time = times[index], times[index + 1]
        left, right = progress[index], progress[index + 1]
        if (
            not projection.supported_mask[index]
            or not projection.supported_mask[index + 1]
            or right_time - left_time > position_max_offset_s * 1_000_000_000
            or not left <= route.distance_m[-1] <= right
            or right <= left
        ):
            continue
        fraction = (route.distance_m[-1] - left) / (right - left)
        crossing_ns = left_time + fraction * (right_time - left_time)
        if abs(crossing_ns - lap_end_ns) > post_lap_margin_s * 1_000_000_000:
            continue
        return LapFinishCrossing(
            official_time_s=(lap_end - lap_start).total_seconds(),
            spatial_crossing_time_s=(crossing_ns - lap_start.to_timedelta64().astype("timedelta64[ns]").astype(np.int64)) / 1_000_000_000,
            supported=True,
            position_source_bracket=(str(rows.iloc[index]["source_row"]), str(rows.iloc[index + 1]["source_row"])),
            source_cutoff_extension_s=max(0.0, (right_time - lap_end_ns) / 1_000_000_000),
        )
    return _unsupported_finish_crossing(lap_start, lap_end)


def _unsupported_finish_crossing(lap_start: pd.Timedelta, lap_end: pd.Timedelta) -> LapFinishCrossing:
    return LapFinishCrossing(
        official_time_s=(lap_end - lap_start).total_seconds(),
        spatial_crossing_time_s=np.nan,
        supported=False,
        position_source_bracket=None,
        source_cutoff_extension_s=np.nan,
    )


def _nearest_nonadjacent_distance(
    distance: np.ndarray,
    nearest: np.ndarray,
    route_distance_m: np.ndarray,
    neighborhood_m: float,
    *,
    closed: bool,
) -> np.ndarray:
    candidate = distance.copy()
    for row, segment in enumerate(nearest):
        anchor = route_distance_m[segment]
        separation = np.abs(route_distance_m[:-1] - anchor)
        if closed:
            length = route_distance_m[-1]
            segment_end = route_distance_m[segment + 1]
            starts = route_distance_m[:-1]
            ends = route_distance_m[1:]
            separation = np.minimum.reduce(
                [
                    np.minimum(np.abs(starts - anchor), length - np.abs(starts - anchor)),
                    np.minimum(np.abs(starts - segment_end), length - np.abs(starts - segment_end)),
                    np.minimum(np.abs(ends - anchor), length - np.abs(ends - anchor)),
                    np.minimum(np.abs(ends - segment_end), length - np.abs(ends - segment_end)),
                ]
            )
        nearby = separation <= neighborhood_m
        candidate[row, nearby] = np.inf
    return candidate.min(axis=1)


def _interpolate_position_with_mask(
    position: pd.DataFrame, query: pd.TimedeltaIndex, max_time_offset_s: float
) -> tuple[np.ndarray, np.ndarray, tuple[tuple[str, str] | None, ...]]:
    required = {"source_row", "SessionTime", "X", "Y"}
    if not required.issubset(position.columns):
        raise ValueError("positions need source rows, time and X/Y")
    ordered = position.sort_values("SessionTime").reset_index(drop=True)
    source_time = ordered["SessionTime"].to_numpy(dtype="timedelta64[ns]").astype(np.int64)
    coordinates = ordered[["X", "Y"]].to_numpy(dtype=np.float64) * 0.1
    if len(source_time) == 0 or np.any(np.diff(source_time) <= 0) or not np.isfinite(coordinates).all():
        raise ValueError("positions need unique finite timestamps and coordinates")
    query_time = query.to_numpy(dtype="timedelta64[ns]").astype(np.int64)
    right = np.searchsorted(source_time, query_time, side="left")
    exact = (right < len(source_time)) & (source_time[np.minimum(right, len(source_time) - 1)] == query_time)
    left = np.where(exact, right, right - 1)
    supported = (left >= 0) & (right < len(source_time))
    widths = np.full(len(query), np.inf)
    valid = supported.copy()
    widths[valid] = (source_time[right[valid]] - source_time[left[valid]]) / 1_000_000_000
    supported &= widths <= max_time_offset_s
    values = np.full((len(query), 2), np.nan, dtype=np.float64)
    brackets: list[tuple[str, str] | None] = [None] * len(query)
    for index in np.flatnonzero(supported):
        fraction = 0.0 if left[index] == right[index] else (query_time[index] - source_time[left[index]]) / (source_time[right[index]] - source_time[left[index]])
        values[index] = coordinates[left[index]] + fraction * (coordinates[right[index]] - coordinates[left[index]])
        brackets[index] = (str(ordered.iloc[left[index]]["source_row"]), str(ordered.iloc[right[index]]["source_row"]))
    return values, supported, tuple(brackets)


def _validate_config(config: RouteProjectionConfig) -> None:
    if (
        config.max_route_distance_m <= 0.0
        or config.branch_ambiguity_separation_m < 0.0
        or config.branch_neighborhood_m <= 0.0
        or config.max_closure_m <= 0.0
        or config.max_seam_heading_delta_deg < 0.0
        or config.control_max_offset_s <= 0.0
    ):
        raise ValueError("route configuration needs positive support limits")


def write_static_route_artifact(
    route: StaticRaceRoute,
    output_dir: Path,
    *,
    source_manifest_path: str,
    source_manifest_sha256: str,
    config: RouteProjectionConfig,
) -> Path:
    """Write an immutable route with its source binding and support limits."""
    _validate_config(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    arrays_path = output_dir / "static_route.npz"
    candidate = output_dir / "static_route.candidate.npz"
    arrays = {
        "x_m": route.x_m,
        "y_m": route.y_m,
        "progress_m": route.distance_m,
        "curvature_m_inv": route.curvature_m_inv,
    }
    np.savez_compressed(candidate, **arrays)
    arrays_hash = sha256(candidate.read_bytes()).hexdigest()
    if arrays_path.exists() and sha256(arrays_path.read_bytes()).hexdigest() != arrays_hash:
        candidate.unlink()
        raise FileExistsError(f"immutable route differs: {arrays_path}")
    candidate.replace(arrays_path)
    payload = {
        "artifact_kind": "source_bound_static_race_route_v1",
        "arrays": {name: {"dtype": str(value.dtype), "shape": list(value.shape)} for name, value in arrays.items()},
        "arrays_path": arrays_path.name,
        "arrays_sha256": arrays_hash,
        "config": asdict(config),
        "source_binding": {"manifest_path": source_manifest_path, "manifest_sha256": source_manifest_sha256},
        "source_rows": route.source_rows,
        "closed": route.closed,
        "loop_closure_m": route.loop_closure_m,
        "seam_heading_delta_deg": route.seam_heading_delta_deg,
        "boundary_source_brackets": route.boundary_source_brackets,
        "units": {"curvature_m_inv": "1/m", "progress_m": "m", "x_m": "m", "y_m": "m"},
    }
    manifest_path = output_dir / "static_route_manifest.json"
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    digest = sha256(content.encode()).hexdigest()
    if manifest_path.exists() and sha256(manifest_path.read_bytes()).hexdigest() != digest:
        raise FileExistsError(f"immutable route manifest differs: {manifest_path}")
    manifest_path.write_text(content)
    return manifest_path
