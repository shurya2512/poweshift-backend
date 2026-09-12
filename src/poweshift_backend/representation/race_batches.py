"""Build complete whole-field race windows for direct mechanics training."""

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import numpy as np
import pandas as pd
import torch

from poweshift_backend.geometry.alignment import FullRaceGeometry, build_full_race_geometry
from poweshift_backend.geometry.race_route import interpolate_controls_with_mask
from poweshift_backend.physics.differentiable import PARAMETER_NAMES
from poweshift_backend.representation.weekend_training import WeekendTrajectoryBatch


_FEATURE_SAMPLES = 64
_CHECKPOINTS_PER_LAP = 4
_DIAGNOSTIC_BRAKE_FRACTION = 0.2
_PARAMETER_LOWER = (2000.0, 4000.0, 0.1, 10.0, 0.01, 0.01, 1.0, 1.0)
_PARAMETER_UPPER = (16000.0, 20000.0, 5.0, 2500.0, 3.0, 3.0, 3.5, 3.5)
_PARAMETER_SEED = (8000.0, 16000.0, 0.8, 100.0, 2.0, 2.0, 2.2, 2.2)


def build_race_training_artifact(
    acquisition_manifest: Path,
    route_manifest: Path,
    source_audit: Path,
    artifact_path: Path,
    source_binding_path: Path,
    *,
    window_s: float = 30.0,
) -> dict[str, object]:
    """Build immutable Australia race windows from source-bound tables."""
    acquisition_bytes = acquisition_manifest.read_bytes()
    acquisition = json.loads(acquisition_bytes)
    audit_bytes = source_audit.read_bytes()
    audit = json.loads(audit_bytes)
    identity = acquisition.get("identity", {})
    weekend = f"{identity.get('date')}_{str(identity.get('event_name', '')).replace(' ', '_')}"
    audited = next((item for item in audit.get("sessions", ()) if item.get("weekend") == weekend), None)
    if identity.get("session_kind") != "race" or audited is None or audited.get("partition") != "training":
        raise ValueError("race batches require an audited training weekend")
    frames = _load_acquisition_frames(acquisition_manifest, acquisition)
    route_length_m = _route_length(route_manifest)
    entries = tuple(sorted(frames["laps"]["DriverNumber"].astype(str).unique(), key=int))
    geometries: dict[str, FullRaceGeometry] = {}
    geometry_failures: dict[str, str] = {}
    for entry in entries:
        try:
            geometries[entry] = build_full_race_geometry(
                _export_path(acquisition_manifest, acquisition, "laps"),
                _export_path(acquisition_manifest, acquisition, "position"),
                _export_path(acquisition_manifest, acquisition, "car"),
                entry,
                max_time_offset_s=2.0,
            )
        except ValueError as error:
            geometry_failures[entry] = str(error)
    race_start = frames["laps"].loc[frames["laps"]["LapStartTime"].notna(), "LapStartTime"].min()
    source_hash = sha256(acquisition_bytes).hexdigest()
    batches, diagnostics, normalization = build_complete_race_batches(
        geometries,
        frames["car"],
        route_length_m=route_length_m,
        source_hash=source_hash,
        window_s=window_s,
        race_start_time=race_start,
        batch_prefix=_batch_prefix(str(identity["event_name"])),
    )
    if not batches:
        raise ValueError("race source has no complete whole-field windows")
    binding = {
        "artifact_kind": "complete_race_window_binding_v1",
        "weekend": weekend,
        "sessions_used": ["prior_training_checkpoint", "race"],
        "practice_context": "audited but excluded because practice targets remain refused",
        "acquisition_manifest": str(acquisition_manifest),
        "acquisition_manifest_sha256": source_hash,
        "route_manifest": str(route_manifest),
        "route_manifest_sha256": sha256(route_manifest.read_bytes()).hexdigest(),
        "source_audit": str(source_audit),
        "source_audit_sha256": sha256(audit_bytes).hexdigest(),
        "source_partition": "training",
        "observation_clock_hz": 4.0,
        "window_s": window_s,
        "optimizer_updates_per_batch": 1,
        "control_interpolation": "linear source bracket at most 2 s",
        "skip_policy": "discard a car from any window containing an unsupported 4 Hz or control row",
        "diagnostic_hotfix": {
            "brake_true_fraction": _DIAGNOSTIC_BRAKE_FRACTION,
            "throttle_fraction": "clamped_to_0_1",
            "road_curvature": "zeroed",
            "state_at_window_start": "source anchored",
            "admission_eligible": False,
        },
        "route_length_m": route_length_m,
        "feature_normalization": normalization,
        "parameter_names": PARAMETER_NAMES,
        "parameter_lower": _PARAMETER_LOWER,
        "parameter_upper": _PARAMETER_UPPER,
        "parameter_seed": _PARAMETER_SEED,
        "logical_batch_count": len(batches),
        "geometry_failures": geometry_failures,
        "batches": diagnostics,
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
        "diagnostics": diagnostics,
    }
    _write_immutable_torch(artifact_path, payload)
    return binding


def build_complete_race_batches(
    geometries: Mapping[str, FullRaceGeometry | SimpleNamespace],
    car: pd.DataFrame,
    *,
    route_length_m: float,
    source_hash: str,
    window_s: float,
    race_start_time: pd.Timedelta = pd.Timedelta(0),
    batch_prefix: str = "race",
) -> tuple[tuple[WeekendTrajectoryBatch, ...], list[dict[str, object]], dict[str, object]]:
    """Keep complete cars in each chronological race window and discard skips."""
    if route_length_m <= 0.0 or window_s <= 0.0 or not source_hash or len(geometries) < 2:
        raise ValueError("race windows need a route, source hash, and at least two cars")
    entries = tuple(sorted(geometries, key=int))
    car_by_entry = {
        str(entry): rows.sort_values("SessionTime").reset_index(drop=True)
        for entry, rows in car.assign(_entry=car["DriverNumber"].astype(str)).groupby("_entry", sort=False)
    }
    reference_time = np.asarray(geometries[entries[0]].time_s, dtype=np.float64)
    if any(not np.array_equal(reference_time, geometry.time_s) for geometry in geometries.values()):
        raise ValueError("race geometry must share one 4 Hz wall clock")
    raw_records = []
    for ordinal, start_s in enumerate(np.arange(reference_time[0], reference_time[-1], window_s)):
        end_s = min(float(start_s + window_s), float(reference_time[-1]))
        indices = np.flatnonzero((reference_time >= start_s - 1e-9) & (reference_time <= end_s + 1e-9))
        if len(indices) < 2:
            continue
        candidates = [entry for entry in entries if _geometry_complete(geometries[entry], indices)]
        record = _window_record(
            candidates,
            geometries,
            car_by_entry,
            indices,
            race_start_time,
            route_length_m,
            ordinal,
            batch_prefix,
        )
        if record is not None:
            raw_records.append(record)
    if not raw_records:
        return (), [], {"samples": _FEATURE_SAMPLES, "mean": [], "scale": []}
    feature_values = np.concatenate([record["features"] for record in raw_records], axis=0)
    mean = feature_values.reshape(-1, feature_values.shape[-1]).mean(axis=0)
    scale = feature_values.reshape(-1, feature_values.shape[-1]).std(axis=0)
    scale[scale <= 1e-12] = 1.0
    timing_gaps = [gap for record in raw_records for gap in record["timing_gaps"]]
    timing_scale = float(np.std(timing_gaps)) if timing_gaps else 1.0
    if timing_scale <= 1e-12:
        timing_scale = 1.0
    batches = tuple(_batch_from_window(record, mean, scale, timing_scale, route_length_m, source_hash) for record in raw_records)
    diagnostics = [_window_diagnostic(record) for record in raw_records]
    normalization = {"samples": _FEATURE_SAMPLES, "mean": mean.tolist(), "scale": scale.tolist()}
    return batches, diagnostics, normalization


def _geometry_complete(geometry: FullRaceGeometry | SimpleNamespace, indices: np.ndarray) -> bool:
    participation = geometry.time_s[indices[0]] >= geometry.participation_start_s - 1e-9
    participation &= geometry.time_s[indices[-1]] <= geometry.participation_end_s + 1e-9
    progress = np.asarray(geometry.unwrapped_progress_laps)[indices]
    speed = np.asarray(geometry.observed_speed_ms)[indices]
    return bool(
        participation
        and np.asarray(geometry.supported_mask)[indices].all()
        and np.isfinite(progress).all()
        and np.isfinite(speed).all()
        and np.all(np.diff(progress) > 0.0)
        and np.all(speed > 0.1)
    )


def _window_record(
    candidates: list[str],
    geometries: Mapping[str, FullRaceGeometry | SimpleNamespace],
    car_by_entry: Mapping[str, pd.DataFrame],
    indices: np.ndarray,
    race_start: pd.Timedelta,
    route_length_m: float,
    ordinal: int,
    batch_prefix: str,
) -> dict[str, object] | None:
    if len(candidates) < 2:
        return None
    time_s = np.asarray(geometries[candidates[0]].time_s)[indices]
    start_s, end_s = float(time_s[0]), float(time_s[-1])
    selected = list(candidates)
    while len(selected) >= 2:
        control_times = _control_union(car_by_entry, selected, race_start, start_s, end_s)
        unsupported = [entry for entry in selected if not _controls_supported(car_by_entry, entry, race_start, control_times).supported_mask.all()]
        if not unsupported:
            break
        selected = [entry for entry in selected if entry not in unsupported]
    if len(selected) < 2:
        return None
    controls, inferred, spans = _window_controls(car_by_entry, selected, race_start, control_times)
    feature_time = np.linspace(start_s, end_s, _FEATURE_SAMPLES, dtype=np.float64)
    features = []
    for entry in selected:
        source = car_by_entry[entry]
        query = pd.TimedeltaIndex(race_start + pd.to_timedelta(feature_time, unit="s"))
        interpolated = interpolate_controls_with_mask(source, query, max_time_offset_s=2.0)
        geometry = geometries[entry]
        speed = np.interp(feature_time, geometry.time_s, geometry.observed_speed_ms)
        features.append(np.column_stack((speed, np.clip(interpolated.throttle_pct / 100.0, 0.0, 1.0), interpolated.brake * _DIAGNOSTIC_BRAKE_FRACTION)))
    progress_laps = np.column_stack([np.asarray(geometries[entry].unwrapped_progress_laps)[indices] for entry in selected])
    speed = np.column_stack([np.asarray(geometries[entry].observed_speed_ms)[indices] for entry in selected])
    checkpoints = _window_checkpoints(progress_laps)
    crossings = np.full((len(selected), len(checkpoints)), np.nan, dtype=np.float64)
    for car_index in range(len(selected)):
        for checkpoint_index, checkpoint in enumerate(checkpoints):
            if progress_laps[0, car_index] <= checkpoint <= progress_laps[-1, car_index]:
                crossings[car_index, checkpoint_index] = np.interp(checkpoint, progress_laps[:, car_index], time_s - start_s)
    timing_mask = np.zeros((len(checkpoints), len(selected), len(selected)), dtype=np.bool_)
    timing_gaps = []
    for checkpoint_index in range(len(checkpoints)):
        for first in range(len(selected)):
            for second in range(first + 1, len(selected)):
                if np.isfinite(crossings[first, checkpoint_index]) and np.isfinite(crossings[second, checkpoint_index]):
                    timing_mask[checkpoint_index, first, second] = True
                    timing_gaps.append(float(crossings[first, checkpoint_index] - crossings[second, checkpoint_index]))
    progress_mask = np.zeros((len(indices), len(selected), len(selected)), dtype=np.bool_)
    first, second = np.triu_indices(len(selected), 1)
    progress_mask[:, first, second] = True
    return {
        "ordinal": ordinal,
        "batch_prefix": batch_prefix,
        "entries": selected,
        "available_entries": candidates,
        "start_s": start_s,
        "end_s": end_s,
        "time_s": time_s - start_s,
        "control_times_s": control_times - start_s,
        "controls": controls,
        "inferred": inferred,
        "spans": spans,
        "features": np.stack(features),
        "progress_m": progress_laps * route_length_m,
        "speed_ms": speed,
        "checkpoints_m": checkpoints * route_length_m,
        "crossings_s": crossings,
        "timing_mask": timing_mask,
        "progress_mask": progress_mask,
        "timing_gaps": timing_gaps,
    }


def _control_union(car_by_entry: Mapping[str, pd.DataFrame], entries: list[str], race_start: pd.Timedelta, start_s: float, end_s: float) -> np.ndarray:
    values = [np.array((start_s, end_s), dtype=np.float64)]
    for entry in entries:
        source = car_by_entry[entry]["SessionTime"]
        offsets = (source - race_start).dt.total_seconds().to_numpy(dtype=np.float64)
        values.append(offsets[(offsets > start_s) & (offsets < end_s)])
    return np.unique(np.concatenate(values))


def _controls_supported(car_by_entry: Mapping[str, pd.DataFrame], entry: str, race_start: pd.Timedelta, control_times: np.ndarray):
    source = car_by_entry[entry]
    query = pd.TimedeltaIndex(race_start + pd.to_timedelta(control_times, unit="s"))
    return interpolate_controls_with_mask(source, query, max_time_offset_s=2.0)


def _window_controls(car_by_entry: Mapping[str, pd.DataFrame], entries: list[str], race_start: pd.Timedelta, control_times: np.ndarray):
    controls = np.empty((len(control_times), len(entries), 2), dtype=np.float64)
    inferred = np.empty((len(control_times), len(entries)), dtype=np.bool_)
    spans = np.empty((len(control_times), len(entries)), dtype=np.float64)
    for index, entry in enumerate(entries):
        source = car_by_entry[entry]
        result = _controls_supported(car_by_entry, entry, race_start, control_times)
        lookup = source.set_index(source["source_row"].astype(str))["SessionTime"]
        spans[:, index] = [
            0.0 if pair[0] == pair[1] else (lookup.loc[pair[1]] - lookup.loc[pair[0]]).total_seconds()
            for pair in result.source_brackets
        ]
        controls[:, index, 0] = np.clip(result.throttle_pct / 100.0, 0.0, 1.0)
        controls[:, index, 1] = result.brake * _DIAGNOSTIC_BRAKE_FRACTION
        inferred[:, index] = result.inferred_mask
    return controls, inferred, spans


def _window_checkpoints(progress_laps: np.ndarray) -> np.ndarray:
    lower = np.floor(np.min(progress_laps[0]) * _CHECKPOINTS_PER_LAP) + 1.0
    upper = np.ceil(np.max(progress_laps[-1]) * _CHECKPOINTS_PER_LAP)
    if upper <= lower:
        return np.empty(0, dtype=np.float64)
    return np.arange(lower, upper, dtype=np.float64) / _CHECKPOINTS_PER_LAP


def _batch_from_window(record, mean, scale, timing_scale, route_length_m, source_hash) -> WeekendTrajectoryBatch:
    normalized = (record["features"] - mean) / scale
    cars = len(record["entries"])
    progress = record["progress_m"]
    margin = route_length_m
    return WeekendTrajectoryBatch(
        features=torch.tensor(normalized, dtype=torch.float64),
        initial_state=torch.tensor(np.column_stack((record["speed_ms"][0], np.zeros(cars), progress[0], np.full(cars, 25.0))), dtype=torch.float64),
        observation_times_s=torch.tensor(record["time_s"], dtype=torch.float64),
        control_times_s=torch.tensor(record["control_times_s"], dtype=torch.float64),
        controls=torch.tensor(record["controls"], dtype=torch.float64),
        control_inferred_mask=torch.tensor(record["inferred"], dtype=torch.bool),
        control_bracket_span_s=torch.tensor(record["spans"], dtype=torch.float64),
        road_progress_m=torch.tensor([float(progress.min() - margin), float(progress.max() + margin)], dtype=torch.float64),
        road_curvature_m_inv=torch.zeros(2, dtype=torch.float64),
        observed_progress=torch.tensor(progress, dtype=torch.float64),
        observed_crossings=torch.tensor(record["crossings_s"], dtype=torch.float64),
        checkpoint_progress_m=torch.tensor(record["checkpoints_m"], dtype=torch.float64),
        timing_pair_mask=torch.tensor(record["timing_mask"], dtype=torch.bool),
        progress_pair_mask=torch.tensor(record["progress_mask"], dtype=torch.bool),
        timing_scale=timing_scale,
        progress_scale=route_length_m,
        source_partition="training",
        source_hash=source_hash,
        cutoff_s=float(record["end_s"] - record["start_s"]),
        control_clock_kind="source_union",
        control_interpolation="linear_source_bracket",
        logical_batch_id=f"{record['batch_prefix']}-race-window-{record['ordinal'] + 1:03d}",
        source_context=f"race {record['start_s']:.3f}-{record['end_s']:.3f}s; source-anchored diagnostic window",
        observed_speed=torch.tensor(record["speed_ms"], dtype=torch.float64),
    )


def _window_diagnostic(record) -> dict[str, object]:
    return {
        "logical_batch_id": f"{record['batch_prefix']}-race-window-{record['ordinal'] + 1:03d}",
        "start_s": record["start_s"],
        "end_s": record["end_s"],
        "entries": record["entries"],
        "available_entries": record["available_entries"],
        "cars": len(record["entries"]),
        "observation_rows": len(record["time_s"]),
        "timing_pairs": int(record["timing_mask"].sum()),
        "progress_pairs": int(record["progress_mask"].sum()),
    }


def _load_acquisition_frames(manifest_path: Path, manifest: dict[str, object]) -> dict[str, pd.DataFrame]:
    frames = {}
    for name in ("car", "laps", "position"):
        path = _export_path(manifest_path, manifest, name)
        if sha256(path.read_bytes()).hexdigest() != manifest["exports"][name]["sha256"]:
            raise ValueError(f"{name} race export hash differs")
        frames[name] = pd.read_parquet(path)
    return frames


def _export_path(manifest_path: Path, manifest: dict[str, object], name: str) -> Path:
    path = Path(manifest["exports"][name]["path"])
    if not path.is_absolute() and not path.exists():
        path = manifest_path.parent / path.name
    return path


def _route_length(route_manifest: Path) -> float:
    record = json.loads(route_manifest.read_text())
    arrays_path = route_manifest.parent / record["arrays_path"]
    if sha256(arrays_path.read_bytes()).hexdigest() != record["arrays_sha256"]:
        raise ValueError("route arrays differ from their manifest")
    with np.load(arrays_path, allow_pickle=False) as arrays:
        length = float(arrays["progress_m"][-1])
    if length <= 0.0:
        raise ValueError("route length must be positive")
    return length


def _batch_prefix(event_name: str) -> str:
    words = [word.lower() for word in event_name.split() if word.lower() not in {"grand", "prix"}]
    return "-".join(words)


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
