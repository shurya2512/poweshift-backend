"""Build the one shared TrackProfile from the fastest clean admitted lap in the training split."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from poweshift_backend.contracts.acquisition import SessionIdentity
from poweshift_backend.contracts.preparation import ArtifactProvenance, CoverageState
from poweshift_backend.geometry.reference import TrackProfile, build_track_profile


@dataclass(frozen=True)
class GeometryTrainingDay:
    """One training day's inputs for selecting a reference lap; position stays training-only."""

    identity: SessionIdentity
    laps_path: Path
    position_path: Path
    admitted_entries: list[str]


def build_training_track_profile(training_days: list[GeometryTrainingDay], config_version: str) -> tuple[TrackProfile, dict]:
    """Pick the fastest accurate admitted lap across training days and build geometry from its position path."""
    best = None
    for day in training_days:
        laps = pd.read_parquet(day.laps_path)
        candidates = laps[
            laps["DriverNumber"].astype(str).isin(day.admitted_entries)
            & laps["IsAccurate"].astype(bool)
            & ~laps["Deleted"].astype(bool)
            & laps["LapTime"].notna()
        ]
        if candidates.empty:
            continue
        fastest = candidates.loc[candidates["LapTime"].idxmin()]
        if best is None or fastest["LapTime"] < best[1]["LapTime"]:
            best = (day, fastest)

    if best is None:
        raise ValueError("no accurate admitted lap is available in the training split to build a reference geometry")

    day, lap = best
    entry = str(lap["DriverNumber"])
    position = pd.read_parquet(day.position_path)
    segment = position[
        (position["DriverNumber"] == entry) & (position["Time"] >= lap["LapStartTime"]) & (position["Time"] <= lap["Time"])
    ].sort_values("Time")

    deduped, dropped = _drop_consecutive_duplicates(segment)

    provenance = ArtifactProvenance(
        source_identity=day.identity,
        source_rows=tuple(str(row) for row in deduped["source_row"]),
        coverage_state=CoverageState.ADMITTED,
        config_version=config_version,
    )
    profile = build_track_profile(deduped[["X", "Y"]], provenance)
    derivation = {
        "selected_date": day.identity.date.isoformat(),
        "selected_entry": entry,
        "selected_lap_number": float(lap["LapNumber"]),
        "lap_time_s": float(lap["LapTime"].total_seconds()),
        "n_position_samples": len(deduped),
        "n_duplicate_samples_dropped": dropped,
    }
    return profile, derivation


def _drop_consecutive_duplicates(segment: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop samples that repeat the previous coordinate so the ordered path strictly advances."""
    xy = segment[["X", "Y"]].to_numpy(dtype=np.float64)
    keep = np.ones(len(xy), dtype=bool)
    for i in range(1, len(xy)):
        if xy[i, 0] == xy[i - 1, 0] and xy[i, 1] == xy[i - 1, 1]:
            keep[i] = False
    return segment.iloc[keep], int((~keep).sum())
