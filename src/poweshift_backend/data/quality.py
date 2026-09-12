"""Independent quality checks for acquired streams."""

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from poweshift_backend.contracts.acquisition import StreamStatus


@dataclass(frozen=True)
class StreamAudit:
    status: StreamStatus
    first_time_s: float | None
    last_time_s: float | None
    gap_count: int
    out_of_order_count: int
    missing_roster: list[str]
    unexpected_roster: list[str]
    fields: list[str]
    error: str | None = None


def audit_stream(
    records: pd.DataFrame | None,
    expected_roster: set[str],
    max_gap: timedelta = timedelta(seconds=15),
    error: str | None = None,
) -> StreamAudit:
    """Describe time and roster coverage without changing records."""
    if records is None:
        return StreamAudit(
            status=StreamStatus.FAILED if error else StreamStatus.MISSING,
            first_time_s=None,
            last_time_s=None,
            gap_count=0,
            out_of_order_count=0,
            missing_roster=sorted(expected_roster),
            unexpected_roster=[],
            fields=[],
            error=error,
        )
    if records.empty:
        return StreamAudit(
            status=StreamStatus.VERIFIED_EMPTY,
            first_time_s=None,
            last_time_s=None,
            gap_count=0,
            out_of_order_count=0,
            missing_roster=sorted(expected_roster),
            unexpected_roster=[],
            fields=list(records.columns),
        )

    time_column = "SessionTime" if "SessionTime" in records else "Time"
    times = pd.to_timedelta(records[time_column])
    deltas = times.diff()
    observed_roster = set(records.get("DriverNumber", pd.Series(dtype=str)).dropna().astype(str))
    return StreamAudit(
        status=StreamStatus.PRESENT,
        first_time_s=times.min().total_seconds(),
        last_time_s=times.max().total_seconds(),
        gap_count=int((deltas > pd.Timedelta(max_gap)).sum()),
        out_of_order_count=int((deltas < pd.Timedelta(0)).sum()),
        missing_roster=sorted(expected_roster - observed_roster),
        unexpected_roster=sorted(observed_roster - expected_roster),
        fields=list(records.columns),
    )
