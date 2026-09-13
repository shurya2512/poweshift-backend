"""Serialize source-bound qualifying fields for direct mechanics smoke runs."""

from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from poweshift_backend.geometry.race_route import (
    RouteProjectionConfig,
    StaticRaceRoute,
    build_lap_source_streams,
    interpolate_controls_with_mask,
    source_finish_crossing,
    unwrap_route_progress,
)
from poweshift_backend.physics.differentiable import PARAMETER_NAMES
from poweshift_backend.representation.weekend_training import WeekendTrajectoryBatch


_FEATURE_SAMPLES = 64
_PARAMETER_LOWER = (2000.0, 4000.0, 0.1, 10.0, 0.01, 0.01, 1.0, 1.0)
_PARAMETER_UPPER = (16000.0, 20000.0, 5.0, 2500.0, 3.0, 3.0, 3.5, 3.5)
_PARAMETER_SEED = (8000.0, 16000.0, 0.8, 100.0, 2.0, 2.0, 2.2, 2.2)
_DIAGNOSTIC_BRAKE_FRACTION = 0.2


def build_qualifying_smoke_artifact(
    export_manifest: Path,
    route_manifest: Path,
    artifact_path: Path,
    source_binding_path: Path,
    *,
    diagnostic_hotfix: bool = False,
) -> dict[str, object]:
    """Build immutable real qualifying batches from one bound export and route."""
    export_bytes = export_manifest.read_bytes()
    export = json.loads(export_bytes)
    route_bytes = route_manifest.read_bytes()
    route_record = json.loads(route_bytes)
    export_hash = sha256(export_bytes).hexdigest()
    if export.get("kind") != "source_bound_qualifying_export_v1":
        raise ValueError("qualifying export kind is required")
    if route_record.get("source_binding", {}).get("manifest_sha256") != export_hash:
        raise ValueError("route must bind this qualifying export")
    route = _load_route(route_manifest, route_record)
    _require_training_source(export_manifest, export)
    root = export_manifest.parent
    frames = _load_frames(root, export)
    groups = _qualifying_groups(frames["laps"])
    source_hash = str(export["source_session"]["weekend_source_sha256"])
    excluded: list[dict[str, object]] = []
    records = []
    for group in groups:
        record = _source_record(group, frames, route, route_record["config"], source_hash, excluded)
        if record is not None:
            records.append(record)
    if len(records) < 10:
        raise ValueError("qualifying smoke needs ten eligible logical fields")
    normalization = _feature_normalization(records)
    timing_scale = _timing_scale(records)
    batches = tuple(_batch_from_record(record, route, normalization, timing_scale, source_hash) for record in records)
    if diagnostic_hotfix:
        batches = tuple(_apply_diagnostic_hotfix(batch) for batch in batches)
    binding = {
        "artifact_kind": "qualifying_smoke_source_binding_v1",
        "export_manifest": str(export_manifest),
        "export_manifest_sha256": export_hash,
        "route_manifest": str(route_manifest),
        "route_manifest_sha256": sha256(route_bytes).hexdigest(),
        "source_partition": "training",
        "target": "same-segment official finish gap with a source-bounded shared-route crossing proof",
        "progress_pair_mask": "false_for_qualifying",
        "control_clock": "native_relative_source_union",
        "control_interpolation": "linear_source_bracket_at_most_2s",
        "position_label_bound_s": 1.1,
        "feature_schema": {"samples": _FEATURE_SAMPLES, "names": ["speed_ms", "throttle_fraction", "brake_fraction"]},
        "feature_normalization": normalization,
        "timing_scale_s": timing_scale,
        "parameter_names": PARAMETER_NAMES,
        "parameter_lower": _PARAMETER_LOWER,
        "parameter_upper": _PARAMETER_UPPER,
        "parameter_seed": _PARAMETER_SEED,
        "parameter_assumptions": "Broad effective force, resistance, downforce and tyre bounds; the seed uses 8 kN drive, 16 kN brake, 0.8 N per (m/s)^2 drag, 100 N rolling resistance, 2 N per (m/s)^2 aero per axle and 2.2 tyre coefficients.",
        "diagnostic_hotfix": {
            "enabled": diagnostic_hotfix,
            "brake_true_fraction": _DIAGNOSTIC_BRAKE_FRACTION if diagnostic_hotfix else None,
            "throttle_fraction": "clamped_to_0_1" if diagnostic_hotfix else "source_divided_by_100",
            "road_curvature": "zeroed" if diagnostic_hotfix else "source_route",
            "admission_eligible": False if diagnostic_hotfix else True,
        },
        "logical_batch_count": len(batches),
        "batches": [_record_summary(record) for record in records],
        "excluded_laps": excluded,
    }
    _write_immutable_json(source_binding_path, binding)
    payload = {
        "source_binding_sha256": sha256(source_binding_path.read_bytes()).hexdigest(),
        "batches": tuple(asdict(batch) for batch in batches),
        "model_config": {
            "feature_width": 3,
            "parameter_lower": _PARAMETER_LOWER,
            "parameter_upper": _PARAMETER_UPPER,
            "initial_parameter_seed": _PARAMETER_SEED,
            "latent_width": 16,
            "hidden_width": 32,
            "layers": 1,
        },
        "learning_rate": 1e-4,
        "diagnostics": binding["batches"],
    }
    _write_immutable_torch(artifact_path, payload)
    return binding


def _diagnostic_controls_and_curvature(
    controls: torch.Tensor, curvature: torch.Tensor
) -> tuple[torch.Tensor, torch.Tensor]:
    """Create explicitly non-admissible controls and road inputs for diagnostic training."""
    fixed_controls = controls.clone()
    fixed_controls[..., 0].clamp_(0.0, 1.0)
    fixed_controls[..., 1] *= _DIAGNOSTIC_BRAKE_FRACTION
    return fixed_controls, torch.zeros_like(curvature)


def _apply_diagnostic_hotfix(batch: WeekendTrajectoryBatch) -> WeekendTrajectoryBatch:
    controls, curvature = _diagnostic_controls_and_curvature(batch.controls, batch.road_curvature_m_inv)
    return replace(
        batch,
        controls=controls,
        road_curvature_m_inv=curvature,
        source_context=f"{batch.source_context}; diagnostic hotfix: zero curvature and {_DIAGNOSTIC_BRAKE_FRACTION:.1f} brake fraction; not admission eligible",
    )


def _load_route(route_manifest: Path, record: dict[str, object]) -> StaticRaceRoute:
    arrays_path = route_manifest.parent / str(record["arrays_path"])
    if sha256(arrays_path.read_bytes()).hexdigest() != record["arrays_sha256"]:
        raise ValueError("route array hash differs")
    arrays = np.load(arrays_path)
    progress = arrays["progress_m"]
    curvature = arrays["curvature_m_inv"]
    return StaticRaceRoute((), arrays["x_m"], arrays["y_m"], progress, curvature, closed=bool(record["closed"]))


def _require_training_source(export_manifest: Path, export: dict[str, object]) -> None:
    audit_path = Path(export["source_audit"]["path"])
    if not audit_path.is_absolute():
        audit_path = export_manifest.parents[3] / audit_path
    audit_bytes = audit_path.read_bytes()
    if sha256(audit_bytes).hexdigest() != export["source_audit"]["sha256"]:
        raise ValueError("qualifying export source audit differs")
    audit = json.loads(audit_bytes)
    weekend = export["source_session"]["weekend"]
    session = next((value for value in audit["sessions"] if value["weekend"] == weekend), None)
    if session is None or session["partition"] != "training" or session["source_hash"] != export["source_session"]["weekend_source_sha256"]:
        raise ValueError("qualifying export is not an audited training source")


def _load_frames(root: Path, export: dict[str, object]) -> dict[str, pd.DataFrame]:
    frames = {}
    for name in ("car", "laps", "position"):
        item = export["exports"][name]
        path = Path(item["path"])
        if not path.is_absolute() and not path.exists():
            path = root / path.name
        if sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"{name} export hash differs")
        frames[name] = pd.read_parquet(path)
    return frames


def _qualifying_groups(laps: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    valid = laps.loc[
        laps["qualifying_segment"].isin(("Q1", "Q2", "Q3"))
        & laps["LapTime"].notna()
        & laps["IsAccurate"].eq(True)
        & laps["Deleted"].eq(False)
        & laps["PitInTime"].isna()
        & laps["PitOutTime"].isna()
        & (laps["TrackStatus"].astype(str) == "1")
    ].copy()
    valid.sort_values(["qualifying_segment", "DriverNumber", "LapStartTime"], inplace=True)
    valid["field_ordinal"] = valid.groupby(["qualifying_segment", "DriverNumber"]).cumcount()
    groups = tuple(
        group.sort_values("DriverNumber")
        for _, group in valid.groupby(["qualifying_segment", "field_ordinal"], sort=True)
        if len(group) >= 2
    )
    if not groups:
        raise ValueError("qualifying export has no eligible same-segment fields")
    return groups


def _source_record(
    group: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    route: StaticRaceRoute,
    config_record: dict[str, object],
    source_hash: str,
    excluded: list[dict[str, object]],
) -> dict[str, object] | None:
    config = RouteProjectionConfig(**config_record)
    selected = []
    horizon = max(row.LapTime.total_seconds() for row in group.itertuples())
    for row in group.itertuples():
        car = _driver_rows(frames["car"], row.DriverNumber)
        position = _driver_rows(frames["position"], row.DriverNumber)
        lap_end = row.LapStartTime + row.LapTime
        stream = build_lap_source_streams(position, car, row.LapStartTime, lap_end, route, config, position_max_offset_s=1.1)
        crossing = source_finish_crossing(
            position,
            row.LapStartTime,
            lap_end,
            route,
            config,
            position_max_offset_s=1.1,
            post_lap_margin_s=1.0,
        )
        if not crossing.supported:
            excluded.append({"segment": row.qualifying_segment, "driver": str(row.DriverNumber), "reason": "no_bounded_spatial_finish_crossing"})
            continue
        unwrapped = unwrap_route_progress(
            stream.route_progress_m,
            stream.position_supported_mask,
            route_length_m=route.distance_m[-1],
            start_near_datum=True,
        )
        projected = unwrapped[np.isfinite(unwrapped)]
        if len(projected) == 0:
            excluded.append({"segment": row.qualifying_segment, "driver": str(row.DriverNumber), "reason": "no_supported_initial_route_coordinate"})
            continue
        selected.append(
            {
                "row": row,
                "car": car,
                "stream": stream,
                "crossing_s": float(crossing.official_time_s),
                "spatial_crossing_s": float(crossing.spatial_crossing_time_s),
                "initial_progress_m": float(projected[0]),
                "finish_bracket": crossing.position_source_bracket,
            }
        )
    if len(selected) < 2:
        return None
    return {
        "segment": str(group.iloc[0]["qualifying_segment"]),
        "ordinal": int(group.iloc[0]["field_ordinal"]),
        "cars": selected,
        "horizon_s": horizon,
        "session_cutoff_s": max((item["row"].LapStartTime + pd.Timedelta(seconds=horizon)).total_seconds() for item in selected),
        "source_hash": source_hash,
    }


def _driver_rows(frame: pd.DataFrame, driver: object) -> pd.DataFrame:
    rows = frame.loc[frame["DriverNumber"].astype(str) == str(driver)].copy()
    rows.sort_values("SessionTime", inplace=True)
    if rows.empty:
        raise ValueError(f"driver {driver} source stream is missing")
    return rows


def _feature_normalization(records: list[dict[str, object]]) -> dict[str, list[float]]:
    values = np.concatenate([_feature_values(car["car"], car["row"].LapStartTime, car["row"].LapTime.total_seconds()) for record in records for car in record["cars"]])
    mean = values.mean(axis=0)
    scale = values.std(axis=0)
    if not np.isfinite(values).all() or np.any(scale <= 0.0):
        raise ValueError("training feature normalization is invalid")
    return {"mean": mean.tolist(), "scale": scale.tolist()}


def _feature_values(car: pd.DataFrame, lap_start: pd.Timedelta, duration_s: float) -> np.ndarray:
    offsets = np.linspace(0.0, duration_s, _FEATURE_SAMPLES, dtype=np.float64)
    query = pd.TimedeltaIndex(lap_start + pd.to_timedelta(offsets, unit="s"))
    controls = interpolate_controls_with_mask(car, query, max_time_offset_s=2.0)
    speed = _interpolate_speed(car, query)
    if not controls.supported_mask.all() or not np.isfinite(speed).all():
        raise ValueError("feature history needs bounded speed and control source brackets")
    return np.column_stack((speed, controls.throttle_pct / 100.0, controls.brake.astype(np.float64)))


def _interpolate_speed(car: pd.DataFrame, query: pd.TimedeltaIndex) -> np.ndarray:
    times = car["SessionTime"].to_numpy(dtype="timedelta64[ns]").astype(np.int64)
    values = car["Speed"].to_numpy(dtype=np.float64) / 3.6
    requested = query.to_numpy(dtype="timedelta64[ns]").astype(np.int64)
    upper = np.searchsorted(times, requested, side="left")
    exact = (upper < len(times)) & (times[np.minimum(upper, len(times) - 1)] == requested)
    lower = np.where(exact, upper, upper - 1)
    valid = (lower >= 0) & (upper < len(times))
    spans = np.full(len(query), np.inf)
    spans[valid] = (times[upper[valid]] - times[lower[valid]]) / 1_000_000_000
    if not valid.all() or np.any(spans > 2.0):
        raise ValueError("speed history needs a source bracket of at most two seconds")
    fraction = np.zeros(len(query), dtype=np.float64)
    different = lower != upper
    fraction[different] = (requested[different] - times[lower[different]]) / (times[upper[different]] - times[lower[different]])
    return values[lower] + fraction * (values[upper] - values[lower])


def _timing_scale(records: list[dict[str, object]]) -> float:
    gaps = [first["crossing_s"] - second["crossing_s"] for record in records for index, first in enumerate(record["cars"]) for second in record["cars"][index + 1 :]]
    scale = float(np.std(gaps))
    if not np.isfinite(scale) or scale <= 0.0:
        raise ValueError("training timing scale is invalid")
    return scale


def _batch_from_record(
    record: dict[str, object],
    route: StaticRaceRoute,
    normalization: dict[str, list[float]],
    timing_scale: float,
    source_hash: str,
) -> WeekendTrajectoryBatch:
    cars = record["cars"]
    horizon_s = float(record["horizon_s"])
    control_times_s = _control_union(cars, horizon_s)
    observation_times_s = _loss_clock(horizon_s)
    controls, inferred, spans = _controls(cars, control_times_s)
    features = np.stack([_feature_values(car["car"], car["row"].LapStartTime, car["row"].LapTime.total_seconds()) for car in cars])
    normalized = (features - np.asarray(normalization["mean"])) / np.asarray(normalization["scale"])
    initial_speed = np.array([features[index, 0, 0] for index in range(len(cars))])
    initial_progress = np.array([_signed_initial_progress(car["initial_progress_m"], route.distance_m[-1]) for car in cars])
    crossings = np.array([[car["crossing_s"]] for car in cars], dtype=np.float64)
    checkpoint = np.array([route.distance_m[-1]], dtype=np.float64)
    timing_mask = np.zeros((1, len(cars), len(cars)), dtype=np.bool_)
    for first in range(len(cars)):
        timing_mask[0, first, first + 1 :] = True
    road_progress, curvature = _tile_route(route, tiles=3)
    batch_id = f"australia-{record['segment'].lower()}-field-{record['ordinal'] + 1}"
    return WeekendTrajectoryBatch(
        features=torch.tensor(normalized, dtype=torch.float64),
        initial_state=torch.tensor(np.column_stack((initial_speed, np.zeros(len(cars)), initial_progress, np.full(len(cars), 25.0))), dtype=torch.float64),
        observation_times_s=torch.tensor(observation_times_s, dtype=torch.float64),
        control_times_s=torch.tensor(control_times_s, dtype=torch.float64),
        controls=torch.tensor(controls, dtype=torch.float64),
        control_inferred_mask=torch.tensor(inferred, dtype=torch.bool),
        control_bracket_span_s=torch.tensor(spans, dtype=torch.float64),
        road_progress_m=torch.tensor(road_progress, dtype=torch.float64),
        road_curvature_m_inv=torch.tensor(curvature, dtype=torch.float64),
        observed_progress=torch.zeros((len(observation_times_s), len(cars)), dtype=torch.float64),
        observed_crossings=torch.tensor(crossings, dtype=torch.float64),
        checkpoint_progress_m=torch.tensor(checkpoint, dtype=torch.float64),
        timing_pair_mask=torch.tensor(timing_mask, dtype=torch.bool),
        progress_pair_mask=torch.zeros((len(observation_times_s), len(cars), len(cars)), dtype=torch.bool),
        timing_scale=timing_scale,
        progress_scale=1.0,
        source_partition="training",
        source_hash=source_hash,
        cutoff_s=horizon_s,
        control_clock_kind="source_union",
        control_interpolation="linear_source_bracket",
        logical_batch_id=batch_id,
        source_context=f"{record['segment']} ordinal valid field; session cutoff {record['session_cutoff_s']:.3f}s; post-finish recorded controls through {horizon_s:.3f}s",
    )


def _control_union(cars: list[dict[str, object]], horizon_s: float) -> np.ndarray:
    values = [np.array([0.0, horizon_s], dtype=np.float64)]
    for car in cars:
        offsets = (car["car"]["SessionTime"] - car["row"].LapStartTime).dt.total_seconds().to_numpy(dtype=np.float64)
        values.append(offsets[(offsets > 0.0) & (offsets < horizon_s)])
    union = np.unique(np.concatenate(values))
    if len(union) < 2 or union[0] != 0.0 or union[-1] != horizon_s:
        raise ValueError("native control union must span the full logical field")
    return union


def _loss_clock(horizon_s: float) -> np.ndarray:
    clock = np.arange(0.0, horizon_s, 0.25, dtype=np.float64)
    if not np.isclose(clock[-1], horizon_s):
        clock = np.append(clock, horizon_s)
    return clock


def _controls(cars: list[dict[str, object]], control_times_s: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    controls = np.empty((len(control_times_s), len(cars), 2), dtype=np.float64)
    inferred = np.empty((len(control_times_s), len(cars)), dtype=np.bool_)
    spans = np.empty((len(control_times_s), len(cars)), dtype=np.float64)
    for index, car in enumerate(cars):
        query = pd.TimedeltaIndex(car["row"].LapStartTime + pd.to_timedelta(control_times_s, unit="s"))
        result = interpolate_controls_with_mask(car["car"], query, max_time_offset_s=2.0)
        if not result.supported_mask.all():
            raise ValueError(f"{car['row'].qualifying_segment} driver {car['row'].DriverNumber} has an unsupported control union row")
        lookup = car["car"].set_index("source_row")["SessionTime"]
        spans[:, index] = [
            0.0 if bracket[0] == bracket[1] else (lookup.loc[int(bracket[1])] - lookup.loc[int(bracket[0])]).total_seconds()
            for bracket in result.source_brackets
        ]
        controls[:, index, 0] = result.throttle_pct / 100.0
        controls[:, index, 1] = result.brake.astype(np.float64)
        inferred[:, index] = result.inferred_mask
    return controls, inferred, spans


def _tile_route(route: StaticRaceRoute, *, tiles: int) -> tuple[np.ndarray, np.ndarray]:
    length = route.distance_m[-1]
    offsets = range(-1, tiles - 1)
    progress = np.concatenate([route.distance_m + index * length if index == -1 else route.distance_m[1:] + index * length for index in offsets])
    curvature = np.concatenate([route.curvature_m_inv if index == -1 else route.curvature_m_inv[1:] for index in offsets])
    return progress, curvature


def _signed_initial_progress(progress_m: float, route_length_m: float) -> float:
    return progress_m - route_length_m if progress_m > route_length_m / 2.0 else progress_m


def _record_summary(record: dict[str, object]) -> dict[str, object]:
    cars = record["cars"]
    return {
        "logical_batch_id": f"australia-{record['segment'].lower()}-field-{record['ordinal'] + 1}",
        "segment": record["segment"],
        "cars": len(cars),
        "horizon_s": record["horizon_s"],
        "session_cutoff_s": record["session_cutoff_s"],
        "entries": [str(car["row"].DriverNumber) for car in cars],
        "source_finish_crossings": len(cars),
        "position_masked_4hz_rows": int(sum((~car["stream"].position_supported_mask).sum() for car in cars)),
    }


def _write_immutable_json(path: Path, value: dict[str, object]) -> None:
    content = json.dumps(value, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text() != content:
        raise FileExistsError(f"immutable artifact differs: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_immutable_torch(path: Path, value: dict[str, object]) -> None:
    candidate = path.with_suffix(path.suffix + ".candidate")
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(value, candidate)
    if path.exists() and sha256(path.read_bytes()).hexdigest() != sha256(candidate.read_bytes()).hexdigest():
        candidate.unlink()
        raise FileExistsError(f"immutable artifact differs: {path}")
    candidate.replace(path)
