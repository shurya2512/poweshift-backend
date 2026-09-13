"""Project pit in/out rows into an isolated lane; never a feature, never a target."""

from enum import Enum
from typing import Literal

import pandas as pd

from poweshift_backend.contracts.acquisition import StrictModel
from poweshift_backend.contracts.preparation import ArtifactProvenance


class PitEventKind(str, Enum):
    PIT_IN = "pit_in"
    PIT_OUT = "pit_out"


class PitSourceRecord(StrictModel):
    """One retrospective pit in/out observation; no compound, undercut or schedule content."""

    entry: str
    event_kind: PitEventKind
    event_time_s: float
    retrospective_disclosure: Literal[True] = True
    source_rows: tuple[str, ...]


class PitProjection(StrictModel):
    """The isolated pit-source lane for one session; kept apart from reconstruction inputs and targets."""

    provenance: ArtifactProvenance
    records: tuple[PitSourceRecord, ...]


def project_pit_records(laps: pd.DataFrame, provenance: ArtifactProvenance) -> PitProjection:
    """Project only PitInTime/PitOutTime rows; no other lap field is read."""
    records: list[PitSourceRecord] = []
    for _, row in laps.iterrows():
        entry = str(row["DriverNumber"])
        source_row = (str(row["source_row"]),)
        if pd.notna(row["PitInTime"]):
            records.append(
                PitSourceRecord(
                    entry=entry,
                    event_kind=PitEventKind.PIT_IN,
                    event_time_s=row["PitInTime"].total_seconds(),
                    source_rows=source_row,
                )
            )
        if pd.notna(row["PitOutTime"]):
            records.append(
                PitSourceRecord(
                    entry=entry,
                    event_kind=PitEventKind.PIT_OUT,
                    event_time_s=row["PitOutTime"].total_seconds(),
                    source_rows=source_row,
                )
            )
    return PitProjection(provenance=provenance, records=tuple(records))


def pit_context_available_by(projection: PitProjection, cutoff_s: float) -> tuple[PitSourceRecord, ...]:
    """Return only pit-source records observed at or before the cutoff; later ones never affect this result."""
    return tuple(record for record in projection.records if record.event_time_s <= cutoff_s)
