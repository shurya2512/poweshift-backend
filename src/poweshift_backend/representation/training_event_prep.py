"""Prepare source-bound 4 Hz race artifacts for training weekends."""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from poweshift_backend.geometry.race_route import (
    RouteProjectionConfig,
    build_closed_route_for_lap,
    write_static_route_artifact,
)
from poweshift_backend.representation.race_batches import build_race_training_artifact


ROUTE_CONFIG = RouteProjectionConfig(5.0, 2.0, 20.0, 5.0, 10.0, 2.0)


@dataclass(frozen=True)
class RouteLapCandidate:
    """One complete lap that can define a static route."""

    entry: str
    lap_number: float
    start: pd.Timedelta
    end: pd.Timedelta


def candidate_route_laps(laps: pd.DataFrame) -> tuple[RouteLapCandidate, ...]:
    """Return accurate complete laps in stable entry and lap order."""
    required = {"DriverNumber", "LapNumber", "LapStartTime", "Time", "IsAccurate", "Deleted"}
    if not required <= set(laps):
        raise ValueError("route selection needs complete lap identity columns")
    valid = laps.loc[
        laps["IsAccurate"].fillna(False).astype(bool)
        & ~laps["Deleted"].fillna(False).astype(bool)
        & laps["LapStartTime"].notna()
        & laps["Time"].notna()
        & laps["LapNumber"].notna()
    ].copy()
    valid = valid.assign(_entry=valid["DriverNumber"].astype(str))
    valid = valid.sort_values(["_entry", "LapNumber"], key=lambda column: pd.to_numeric(column, errors="coerce"))
    return tuple(
        RouteLapCandidate(str(row.DriverNumber), float(row.LapNumber), row.LapStartTime, row.Time)
        for row in valid.itertuples(index=False)
        if row.Time > row.LapStartTime
    )


def validate_training_event(acquisition_path: Path, audit_path: Path) -> tuple[dict, dict]:
    """Require a verified training race before preparing artifacts."""
    acquisition = json.loads(acquisition_path.read_text())
    audit = json.loads(audit_path.read_text())
    identity = acquisition.get("identity", {})
    weekend = f"{identity.get('date')}_{str(identity.get('event_name', '')).replace(' ', '_')}"
    record = next((item for item in audit.get("sessions", ()) if item.get("weekend") == weekend), None)
    if (
        identity.get("session_kind") != "race"
        or record is None
        or record.get("partition") != "training"
        or record.get("source_state") != "verified"
    ):
        raise ValueError("race preparation requires a verified training event")
    return acquisition, record


def prepare_training_event(
    acquisition_path: Path,
    audit_path: Path,
    output_root: Path,
) -> dict[str, object]:
    """Build one deterministic route and native race batch artifact."""
    acquisition, record = validate_training_event(acquisition_path, audit_path)
    frames = {
        name: _load_export(acquisition_path, acquisition, name)
        for name in ("laps", "position")
    }
    position = frames["position"].assign(_entry=frames["position"]["DriverNumber"].astype(str))
    route = None
    selected = None
    errors: list[str] = []
    for candidate in candidate_route_laps(frames["laps"]):
        try:
            route = build_closed_route_for_lap(
                position.loc[position["_entry"] == candidate.entry],
                candidate.start,
                candidate.end,
                ROUTE_CONFIG,
                position_max_offset_s=2.0,
            )
        except ValueError as error:
            errors.append(f"{candidate.entry}:{candidate.lap_number:g}:{error}")
            continue
        selected = candidate
        break
    if route is None or selected is None:
        raise ValueError(f"no race lap produced a closed route: {errors[:3]}")
    identity = acquisition["identity"]
    slug = "_".join(
        word.lower() for word in str(identity["event_name"]).split()
        if word.lower() not in {"grand", "prix"}
    )
    route_dir = output_root / f"static_route_{slug}_race_v1"
    route_manifest = write_static_route_artifact(
        route,
        route_dir,
        source_manifest_path=str(acquisition_path),
        source_manifest_sha256=sha256(acquisition_path.read_bytes()).hexdigest(),
        config=ROUTE_CONFIG,
    )
    race_dir = output_root / f"race_full_weekend_{slug}_v1_diagnostic"
    binding_path = race_dir / "source_binding.json"
    artifact_path = race_dir / "race_batches.pt"
    binding = build_race_training_artifact(
        acquisition_path,
        route_manifest,
        audit_path,
        artifact_path,
        binding_path,
    )
    return {
        "event_name": identity["event_name"],
        "event_date": identity["date"],
        "partition": record["partition"],
        "route_entry": selected.entry,
        "route_lap": selected.lap_number,
        "route_manifest": str(route_manifest),
        "race_artifact": str(artifact_path),
        "source_binding": str(binding_path),
        "observation_clock_hz": binding["observation_clock_hz"],
        "logical_batch_count": binding["logical_batch_count"],
    }


def _load_export(acquisition_path: Path, acquisition: dict, name: str) -> pd.DataFrame:
    record = acquisition.get("exports", {}).get(name, {})
    path = Path(record.get("path", ""))
    if not path.is_absolute() and not path.exists():
        path = acquisition_path.parent / path.name
    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
        raise ValueError(f"{name} race export hash differs")
    return pd.read_parquet(path)
