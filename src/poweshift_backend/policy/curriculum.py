"""Load bounded diagnostic curriculum inputs."""

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from math import ceil, floor, isfinite
from pathlib import Path

import pandas as pd
import torch

from poweshift_backend.policy.diagnostic import DiagnosticTrace, FittedProfile


SINGLETON_STEP_S = 0.24


@dataclass(frozen=True)
class PromotedProfileRegistry:
    """Active fitted profiles and their admission boundary."""

    profiles: dict[str, FittedProfile]
    admission_id: str
    status: str
    physics_admitted: bool


@dataclass(frozen=True)
class RaceFieldTick:
    """One source-bound reference-field observation."""

    time_s: float
    progress_by_entry: tuple[tuple[str, float], ...]
    speed_by_entry: tuple[tuple[str, float], ...]
    throttle_by_entry: tuple[tuple[str, float], ...] = ()
    brake_by_entry: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class NativeRaceData:
    """Native race laps and the matching reference field."""

    traces_by_entry: dict[str, tuple[DiagnosticTrace, ...]]
    field_ticks: tuple[RaceFieldTick, ...]
    route_length_m: float
    observation_hz: float


@dataclass(frozen=True)
class PracticeData:
    """Source-bound practice traces for energy-only learning."""

    traces_by_entry: dict[str, tuple[DiagnosticTrace, ...]]
    observation_hz: float
    session_id: str


def load_promoted_profiles(path: Path) -> PromotedProfileRegistry:
    """Load active profiles that declare downstream compatibility."""
    payload = json.loads(path.read_text())
    status = str(payload.get("status", ""))
    if not status.startswith("promoted"):
        raise ValueError("profile registry is not promoted")
    if payload.get("compatible_with_downstream_contract") is not True:
        raise ValueError("profile registry is not downstream-compatible")
    profiles: dict[str, FittedProfile] = {}
    for entry, record in payload.get("active_profiles", {}).items():
        if record.get("active") is not True:
            continue
        parameters = record["profile"]["parameters"]
        profiles[str(entry)] = FittedProfile(
            str(entry),
            float(parameters["max_drive_force_n"]),
            float(parameters["drag_n_per_ms2"]),
            float(parameters["rolling_resistance_n"]),
        )
    if not profiles:
        raise ValueError("profile registry has no active profiles")
    return PromotedProfileRegistry(
        profiles,
        str(payload["profile_admission_id"]),
        status,
        bool(payload.get("physics_admission", False)),
    )


def _sample_rows(rows: pd.DataFrame, sample_count: int) -> pd.DataFrame:
    rows = rows.sort_values("row_index")
    valid = (
        ~rows["padding"].astype(bool)
        & rows["valid__speed_ms"].astype(bool)
        & rows["valid__throttle_pct"].astype(bool)
        & rows["valid__brake"].astype(bool)
    )
    rows = rows.loc[valid]
    finite = rows[["X__speed_ms", "X__throttle_pct", "X__brake"]].map(
        lambda value: isfinite(float(value))
    ).all(axis=1)
    rows = rows.loc[finite]
    if len(rows) <= sample_count:
        return rows
    positions = [(index * (len(rows) - 1)) // (sample_count - 1) for index in range(sample_count)]
    return rows.iloc[positions]


def load_preseason_traces(
    manifest_path: Path,
    table_path: Path,
    profiles: dict[str, FittedProfile],
    sample_count: int = 64,
) -> tuple[DiagnosticTrace, ...]:
    """Load every training preseason package as one sampled trace."""
    if sample_count < 2:
        raise ValueError("sample count must be at least two")
    manifest = json.loads(manifest_path.read_text())
    packages = manifest.get("packages", [])
    if not packages or any(
        package.get("split") != "training"
        or package.get("programme_context") != "preseason_test"
        or package.get("quality_context") != "measured"
        or package.get("provenance", {}).get("coverage_state") != "admitted"
        for package in packages
    ):
        raise ValueError("curriculum requires measured training preseason packages")
    columns = [
        "package_id", "row_index", "padding", "X__speed_ms", "valid__speed_ms",
        "X__throttle_pct", "valid__throttle_pct", "X__brake", "valid__brake",
    ]
    table = pd.read_parquet(table_path, columns=columns)
    grouped = {str(package_id): rows for package_id, rows in table.groupby("package_id", sort=False)}
    expected = {str(package["package_id"]) for package in packages}
    if set(grouped) != expected:
        raise ValueError("package manifest and table identities do not match")
    traces: list[DiagnosticTrace] = []
    for package in packages:
        package_id = str(package["package_id"])
        entry = str(package["entry"])
        if entry not in profiles:
            raise ValueError(f"no promoted profile for entry {entry}")
        sampled = _sample_rows(grouped[package_id], sample_count)
        if sampled.empty:
            raise ValueError(f"package {package_id} has no valid rows")
        duration_s = float(package["end_time_s"]) - float(package["start_time_s"])
        if len(sampled) == 1:
            sampled = pd.concat((sampled, sampled), ignore_index=True)
            step_s = SINGLETON_STEP_S
        else:
            if not isfinite(duration_s) or duration_s <= 0.0:
                raise ValueError(f"package {package_id} has an invalid duration")
            step_s = duration_s / (len(sampled) - 1)
        traces.append(DiagnosticTrace(
            "training",
            package_id,
            tuple(float(value) for value in sampled["X__speed_ms"]),
            tuple(float(value) / 100.0 for value in sampled["X__throttle_pct"]),
            tuple(float(value) for value in sampled["X__brake"]),
            step_s,
            entry,
        ))
    return tuple(traces)


def save_curriculum_checkpoint(
    path: Path,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    stage: str,
    completed_updates: int,
    sources: dict[str, str],
) -> None:
    """Save one immutable stage boundary as state dictionaries."""
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save({
        "schema_id": model.schema.schema_id,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "stage": stage,
        "completed_updates": completed_updates,
        "sources": sources,
    }, temporary)
    temporary.replace(path)


def load_curriculum_checkpoint(
    path: Path,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
) -> dict[str, object]:
    """Restore a stage boundary using restricted checkpoint loading."""
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if payload.get("schema_id") != model.schema.schema_id:
        raise ValueError("checkpoint policy schema does not match")
    model.load_state_dict(payload["model_state_dict"])
    optimizer.load_state_dict(payload["optimizer_state_dict"])
    return {
        "stage": str(payload["stage"]),
        "completed_updates": int(payload["completed_updates"]),
        "sources": dict(payload["sources"]),
    }


def _normalization(path: Path) -> tuple[torch.Tensor, torch.Tensor]:
    payload = json.loads(path.read_text())
    values = payload.get("feature_normalization") or payload["source_binding"]["feature_normalization"]
    return torch.tensor(values["mean"], dtype=torch.float64), torch.tensor(values["scale"], dtype=torch.float64)


def load_qualifying_traces(batch_path: Path, binding_path: Path) -> tuple[DiagnosticTrace, ...]:
    """Load every car trace from source-bound qualifying batches."""
    payload = torch.load(batch_path, map_location="cpu", weights_only=True)
    mean, scale = _normalization(binding_path)
    traces: list[DiagnosticTrace] = []
    for batch, diagnostic in zip(payload["batches"], payload["diagnostics"]):
        features = batch["features"].to(torch.float64) * scale + mean
        step_s = float(diagnostic["horizon_s"]) / (features.shape[1] - 1)
        for car, entry in enumerate(diagnostic["entries"]):
            rows = features[car]
            traces.append(DiagnosticTrace(
                "training",
                f"{batch['logical_batch_id']}:{entry}",
                tuple(float(value) for value in rows[:, 0]),
                tuple(float(value) for value in rows[:, 1]),
                tuple(float(value) for value in rows[:, 2]),
                step_s,
                str(entry),
            ))
    return tuple(traces)


def _seconds(value: object) -> float:
    return float(pd.Timedelta(value).total_seconds())


def load_practice_traces(
    manifest_path: Path,
    profiles: dict[str, FittedProfile],
) -> PracticeData:
    """Load complete practice laps as causal 4 Hz energy traces."""
    return _load_energy_session_traces(
        manifest_path, profiles, "source_bound_practice_export_v1", "training", "practice",
    )


def load_qualifying_test_traces(
    manifest_path: Path,
    profiles: dict[str, FittedProfile],
) -> PracticeData:
    """Load protected qualifying controls without optimizer eligibility."""
    return _load_energy_session_traces(
        manifest_path,
        profiles,
        "source_bound_qualifying_test_export_v1",
        "final_evaluation",
        "qualifying",
    )


def load_qualifying_replay_traces(
    manifest_path: Path,
    profiles: dict[str, FittedProfile],
) -> PracticeData:
    """Load training-weekend qualifying controls for retrospective reports."""
    return _load_energy_session_traces(
        manifest_path,
        profiles,
        "source_bound_qualifying_export_v1",
        "training",
        "qualifying",
    )


def _load_energy_session_traces(
    manifest_path: Path,
    profiles: dict[str, FittedProfile],
    expected_kind: str,
    expected_partition: str,
    trace_kind: str,
) -> PracticeData:
    manifest = json.loads(manifest_path.read_text())
    identity = manifest.get("identity", {})
    partition = identity.get(
        "partition",
        "training" if expected_kind == "source_bound_qualifying_export_v1" else None,
    )
    if manifest.get("kind") != expected_kind or partition != expected_partition:
        raise ValueError("energy traces require the expected source-bound partition")
    tables: dict[str, pd.DataFrame] = {}
    for name in ("laps", "car"):
        record = manifest.get("exports", {}).get(name, {})
        path = Path(record.get("path", ""))
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
            raise ValueError(f"practice {name} export hash does not match")
        tables[name] = pd.read_parquet(path)
    laps = tables["laps"].copy()
    car = tables["car"].copy()
    laps["DriverNumber"] = laps["DriverNumber"].astype(str)
    car["DriverNumber"] = car["DriverNumber"].astype(str)
    car = car.assign(_time_s=car["SessionTime"].map(_seconds)).sort_values(
        ["DriverNumber", "_time_s", "source_row"],
    )
    traces_by_entry: dict[str, tuple[DiagnosticTrace, ...]] = {}
    session_id = str(identity.get("session_id", ""))
    for entry in profiles:
        entry_laps = laps.loc[laps["DriverNumber"] == entry].sort_values(["LapNumber", "source_row"])
        entry_car = car.loc[car["DriverNumber"] == entry]
        traces: list[DiagnosticTrace] = []
        for lap in entry_laps.itertuples(index=False):
            if not bool(lap.IsAccurate) or bool(lap.Deleted) or pd.isna(lap.LapStartTime) or pd.isna(lap.Time):
                continue
            start_s, end_s = _seconds(lap.LapStartTime), _seconds(lap.Time)
            if not isfinite(start_s) or not isfinite(end_s) or end_s <= start_s:
                continue
            first_tick = ceil(start_s * 4.0)
            last_tick = floor(end_s * 4.0)
            sample_times = [tick / 4.0 for tick in range(first_tick, last_tick + 1)]
            source = entry_car.loc[(entry_car["_time_s"] >= start_s) & (entry_car["_time_s"] <= end_s)]
            if len(source) < 2 or len(sample_times) < 2:
                continue
            source_times = source["_time_s"].to_numpy()
            indices = source_times.searchsorted(sample_times, side="right") - 1
            valid = indices >= 0
            if not valid.any():
                continue
            sample_times = [value for value, keep in zip(sample_times, valid) if keep]
            sampled = source.iloc[indices[valid]]
            finite = sampled[["Speed", "Throttle", "Brake"]].map(
                lambda value: isfinite(float(value)),
            ).all(axis=1)
            sampled = sampled.loc[finite]
            sample_times = [value for value, keep in zip(sample_times, finite) if keep]
            if len(sampled) < 2:
                continue
            traces.append(DiagnosticTrace(
                expected_partition,
                f"{trace_kind}:{session_id}:{entry}:lap-{float(lap.LapNumber):g}",
                tuple(float(value) / 3.6 for value in sampled["Speed"]),
                tuple(min(1.0, max(0.0, float(value) / 100.0)) for value in sampled["Throttle"]),
                tuple(min(1.0, max(0.0, float(value))) for value in sampled["Brake"]),
                0.25,
                entry,
                False,
                sample_time_s=tuple(sample_times),
            ))
        traces_by_entry[entry] = tuple(
            replace(trace, lap_index=index, total_laps=len(traces))
            for index, trace in enumerate(traces, start=1)
        )
    return PracticeData(traces_by_entry, 4.0, session_id)


def _traffic_gaps(progress: torch.Tensor, ego: int, route_length_m: float) -> tuple[list[float], list[float]]:
    ahead: list[float] = []
    behind: list[float] = []
    for row in progress:
        relative = torch.remainder(row - row[ego] + route_length_m / 2.0, route_length_m) - route_length_m / 2.0
        valid = torch.isfinite(relative)
        valid[ego] = False
        positive = relative[(relative > 0.0) & valid]
        negative = relative[(relative < 0.0) & valid]
        ahead.append(float(positive.min()) if positive.numel() else route_length_m / 2.0)
        behind.append(float(-negative.max()) if negative.numel() else route_length_m / 2.0)
    return ahead, behind


def _closing_rate(gaps: list[float], step_s: float) -> list[float]:
    rates = [0.0]
    rates.extend(max(0.0, min(20.0, (before - after) / step_s)) for before, after in zip(gaps, gaps[1:]))
    return rates


def _traffic_gap_row(progress: torch.Tensor, ego: int, route_length_m: float) -> tuple[float, float]:
    relative = torch.remainder(progress - progress[ego] + route_length_m / 2.0, route_length_m) - route_length_m / 2.0
    valid = torch.isfinite(relative)
    valid[ego] = False
    positive = relative[(relative > 0.0) & valid]
    negative = relative[(relative < 0.0) & valid]
    ahead = float(positive.min()) if positive.numel() else route_length_m / 2.0
    behind = float(-negative.max()) if negative.numel() else route_length_m / 2.0
    return ahead, behind


def load_race_traces(
    batch_path: Path,
    report_path: Path,
    entry: str = "1",
) -> tuple[tuple[DiagnosticTrace, ...], float, list[float]]:
    """Load all complete race laps with causal full-field gaps."""
    payload = torch.load(batch_path, map_location="cpu", weights_only=True)
    mean, scale = _normalization(report_path)
    report = json.loads(report_path.read_text())
    route_length_m = float(report["source_binding"]["route_length_m"])
    samples: list[tuple[float, float, float, float, float, float]] = []
    all_speeds: list[float] = []
    step_s = 30.0 / 63.0
    for batch, diagnostic in zip(payload["batches"], payload["diagnostics"]):
        if entry not in diagnostic["entries"]:
            continue
        ego = diagnostic["entries"].index(entry)
        features = batch["features"].to(torch.float64) * scale + mean
        indices = torch.linspace(0, batch["observed_progress"].shape[0] - 1, features.shape[1]).round().to(torch.long)
        progress = batch["observed_progress"][indices]
        ahead, behind = _traffic_gaps(progress, ego, route_length_m)
        rows = features[ego]
        for index, row in enumerate(rows):
            speed = max(1.0, float(row[0]))
            samples.append((
                float(progress[index, ego]), speed, float(row[1]), float(row[2]),
                ahead[index], behind[index],
            ))
            all_speeds.append(speed)
    lap_groups: dict[int, list[tuple[float, float, float, float, float, float]]] = {}
    for sample in samples:
        lap_groups.setdefault(int(sample[0] // route_length_m), []).append(sample)
    complete = [
        rows for _, rows in sorted(lap_groups.items())
        if len(rows) >= 100 and rows[-1][0] - rows[0][0] >= route_length_m * 0.8
    ]
    if not complete:
        raise ValueError("race source does not contain a complete diagnostic lap")
    traces: list[DiagnosticTrace] = []
    total_laps = len(complete)
    for lap, rows in enumerate(complete, start=1):
        speed = [row[1] for row in rows]
        ahead_distance = [row[4] for row in rows]
        behind_distance = [row[5] for row in rows]
        traces.append(DiagnosticTrace(
            "training",
            f"race:{entry}:lap-{lap}",
            tuple(speed),
            tuple(row[2] for row in rows),
            tuple(row[3] for row in rows),
            step_s,
            entry,
            True,
            tuple(distance / current_speed for distance, current_speed in zip(ahead_distance, speed)),
            tuple(_closing_rate(ahead_distance, step_s)),
            tuple(distance / current_speed for distance, current_speed in zip(behind_distance, speed)),
            tuple(_closing_rate(behind_distance, step_s)),
            lap,
            total_laps,
        ))
    return tuple(traces), route_length_m, all_speeds


def _past_controls(batch: dict[str, object]) -> torch.Tensor:
    observation_times = batch["observation_times_s"].contiguous()
    control_times = batch["control_times_s"].contiguous()
    indices = torch.searchsorted(control_times, observation_times, side="right").sub(1).clamp(0, len(control_times) - 1)
    return batch["controls"][indices]


def load_native_race_data(
    batch_path: Path,
    report_path: Path,
    entries: tuple[str, ...],
    allow_missing_entries: bool = False,
) -> NativeRaceData:
    """Load complete per-entry laps on the native 4 Hz clock."""
    payload = torch.load(batch_path, map_location="cpu", weights_only=True)
    report = json.loads(report_path.read_text())
    binding = report.get("source_binding", report)
    observation_hz = float(binding["observation_clock_hz"])
    route_length_m = float(binding["route_length_m"])
    if observation_hz != 4.0:
        raise ValueError("native race validation requires a 4 Hz observation clock")
    requested = set(entries)
    samples: dict[str, dict[float, tuple[float, ...]]] = {entry: {} for entry in entries}
    frames: dict[float, tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float]]] = {}
    for batch, diagnostic in zip(payload["batches"], payload["diagnostics"]):
        present = [str(entry) for entry in diagnostic["entries"]]
        observation_times = batch["observation_times_s"].to(torch.float64)
        absolute_times = observation_times + float(diagnostic["start_s"])
        progress = batch["observed_progress"].to(torch.float64)
        speed = batch["observed_speed"].to(torch.float64)
        controls = _past_controls(batch).to(torch.float64)
        for row_index, time_value in enumerate(absolute_times):
            time_s = float(time_value)
            progress_map, speed_map, throttle_map, brake_map = frames.setdefault(time_s, ({}, {}, {}, {}))
            for car, entry in enumerate(present):
                progress_map[entry] = float(progress[row_index, car])
                speed_map[entry] = max(1.0, float(speed[row_index, car]))
                throttle_map[entry] = min(1.0, max(0.0, float(controls[row_index, car, 0])))
                brake_map[entry] = min(1.0, max(0.0, float(controls[row_index, car, 1])))
            for car, entry in enumerate(present):
                if entry not in requested:
                    continue
                ego_progress = float(progress[row_index, car])
                ego_speed = max(1.0, float(speed[row_index, car]))
                ahead_distance, behind_distance = _traffic_gap_row(progress[row_index], car, route_length_m)
                position = 1 + sum(float(value) > ego_progress for value in progress[row_index])
                samples[entry][time_s] = (
                    ego_speed,
                    float(controls[row_index, car, 0]),
                    float(controls[row_index, car, 1]),
                    ego_progress,
                    float(position),
                    ahead_distance,
                    behind_distance,
                )
    missing = requested.difference(entry for entry, values in samples.items() if values)
    if missing and not allow_missing_entries:
        raise ValueError(f"race source is missing requested entries: {sorted(missing)}")
    traces_by_entry: dict[str, tuple[DiagnosticTrace, ...]] = {}
    step_s = 1.0 / observation_hz
    for entry in entries:
        ordered = [(time_s, values) for time_s, values in sorted(samples[entry].items())]
        if not ordered:
            traces_by_entry[entry] = ()
            continue
        lap_groups: dict[int, list[tuple[float, tuple[float, ...]]]] = {}
        for sample in ordered:
            lap_groups.setdefault(int(sample[1][3] // route_length_m), []).append(sample)
        complete = [
            (source_lap, rows) for source_lap, rows in sorted(lap_groups.items())
            if len(rows) >= 2 and rows[-1][1][3] - rows[0][1][3] >= route_length_m * 0.8
        ]
        if not complete and not allow_missing_entries:
            raise ValueError(f"race source has no complete 4 Hz lap for entry {entry}")
        if not complete:
            traces_by_entry[entry] = ()
            continue
        traces: list[DiagnosticTrace] = []
        for lap_index, (source_lap, rows) in enumerate(complete, start=1):
            speeds = [row[1][0] for row in rows]
            ahead_distance = [row[1][5] for row in rows]
            behind_distance = [row[1][6] for row in rows]
            traces.append(DiagnosticTrace(
                "training",
                f"race:{entry}:source-lap-{source_lap}",
                tuple(speeds),
                tuple(row[1][1] for row in rows),
                tuple(row[1][2] for row in rows),
                step_s,
                entry,
                True,
                tuple(distance / current_speed for distance, current_speed in zip(ahead_distance, speeds)),
                tuple(_closing_rate(ahead_distance, step_s)),
                tuple(distance / current_speed for distance, current_speed in zip(behind_distance, speeds)),
                tuple(_closing_rate(behind_distance, step_s)),
                lap_index,
                len(complete),
                tuple(row[0] for row in rows),
                tuple(row[1][3] for row in rows),
                tuple(int(row[1][4]) for row in rows),
            ))
        traces_by_entry[entry] = tuple(traces)
    field_ticks = tuple(
        RaceFieldTick(
            time_s,
            tuple(sorted(progress.items())),
            tuple(sorted(speed.items())),
            tuple(sorted(throttle.items())),
            tuple(sorted(brake.items())),
        )
        for time_s, (progress, speed, throttle, brake) in sorted(frames.items())
    )
    return NativeRaceData(traces_by_entry, field_ticks, route_length_m, observation_hz)


def split_race_traces(
    traces: tuple[DiagnosticTrace, ...],
    training_fraction: float = 0.8,
) -> tuple[tuple[DiagnosticTrace, ...], tuple[DiagnosticTrace, ...]]:
    """Split complete race laps chronologically without overlap."""
    if len(traces) < 2 or not 0.0 < training_fraction < 1.0:
        raise ValueError("race split requires two laps and a bounded fraction")
    boundary = min(len(traces) - 1, max(1, int(len(traces) * training_fraction)))
    return traces[:boundary], traces[boundary:]
