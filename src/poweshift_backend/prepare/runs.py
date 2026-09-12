"""Identify continuous telemetry runs and tyre history without inventing tyre-set identity."""

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class RunBoundaryReason(str, Enum):
    GARAGE_STOP = "garage_stop"
    RED_FLAG = "red_flag"
    TYRE_REPLACEMENT = "tyre_replacement"
    EXCESSIVE_GAP = "excessive_gap"
    RUN_END = "run_end"


@dataclass(frozen=True)
class TyreContext:
    """Tyre state for one stint; tyre_set_id stays unknown without a supporting event."""

    stint: int
    compound: str | None
    tyre_life: float | None
    fresh_tyre: bool | None
    tyre_set_id: str | None


@dataclass(frozen=True)
class RunSegment:
    """One continuous run of kept sample positions, and why it ended."""

    entry: str
    sample_indices: tuple[int, ...]
    start_time_s: float
    end_time_s: float
    end_boundary_reason: RunBoundaryReason


def tyre_history(laps: pd.DataFrame, entry: str) -> list[TyreContext]:
    """One tyre context per stint; tyre_set_id stays unknown since no source field identifies a physical set."""
    driver_laps = laps[laps["DriverNumber"].astype(str) == entry].sort_values("LapNumber")
    contexts: list[TyreContext] = []
    for stint, stint_laps in driver_laps.groupby("Stint", sort=True):
        first = stint_laps.iloc[0]
        stint_number = int(stint)
        compound = first.get("Compound")
        fresh_tyre = bool(first["FreshTyre"]) if pd.notna(first.get("FreshTyre")) else None
        tyre_life = first.get("TyreLife")
        contexts.append(
            TyreContext(
                stint=stint_number,
                compound=compound if pd.notna(compound) else None,
                tyre_life=float(tyre_life) if pd.notna(tyre_life) else None,
                fresh_tyre=fresh_tyre,
                tyre_set_id=None,
            )
        )
    return contexts


def garage_stop_intervals_s(laps: pd.DataFrame, entry: str) -> list[tuple[float, float, RunBoundaryReason]]:
    """Native elapsed [pit-in, pit-out] intervals for one entry.

    PitOutTime on a row is the start of that lap; PitInTime on a row is the end of that
    lap, so a row can carry both for two different stops. Resolve the pending pit-in
    against this row's PitOutTime before recording this row's own PitInTime.
    """
    driver_laps = laps[laps["DriverNumber"].astype(str) == entry].sort_values("LapNumber")
    intervals: list[tuple[float, float, RunBoundaryReason]] = []
    pending_pit_in_s: float | None = None
    for _, lap in driver_laps.iterrows():
        pit_in = lap.get("PitInTime")
        pit_out = lap.get("PitOutTime")
        if pd.notna(pit_out) and pending_pit_in_s is not None:
            pit_out_s = pit_out.total_seconds()
            if pit_out_s > pending_pit_in_s:
                intervals.append((pending_pit_in_s, pit_out_s, RunBoundaryReason.GARAGE_STOP))
            pending_pit_in_s = None
        if pd.notna(pit_in):
            pending_pit_in_s = pit_in.total_seconds()
    return intervals


def red_flag_intervals_s(track_status: pd.DataFrame) -> list[tuple[float, float, RunBoundaryReason]]:
    """Native elapsed [red, next status] intervals from the session's track-status stream."""
    if track_status is None or track_status.empty:
        return []
    statuses = track_status.sort_values("Time").reset_index(drop=True)
    intervals: list[tuple[float, float, RunBoundaryReason]] = []
    red_start: float | None = None
    last_time_s = 0.0
    for _, row in statuses.iterrows():
        time_s = row["Time"].total_seconds()
        last_time_s = time_s
        if str(row["Status"]) == "5":
            if red_start is None:
                red_start = time_s
        elif red_start is not None:
            intervals.append((red_start, time_s, RunBoundaryReason.RED_FLAG))
            red_start = None
    if red_start is not None:
        intervals.append((red_start, last_time_s, RunBoundaryReason.RED_FLAG))
    return intervals


def tyre_replacement_times_s(laps: pd.DataFrame, entry: str) -> list[float]:
    """Native elapsed seconds where a lap's own record evidences a fresh tyre replacement."""
    driver_laps = laps[laps["DriverNumber"].astype(str) == entry].sort_values("LapNumber")
    times: list[float] = []
    previous_stint = None
    for _, lap in driver_laps.iterrows():
        stint = lap.get("Stint")
        fresh_tyre = lap.get("FreshTyre")
        if previous_stint is not None and stint != previous_stint and pd.notna(fresh_tyre) and bool(fresh_tyre):
            times.append(lap["Time"].total_seconds())
        previous_stint = stint
    return times


def split_into_runs(
    entry: str,
    times_s: pd.Series,
    excluded_intervals: list[tuple[float, float, RunBoundaryReason]],
    tyre_replacement_s: list[float],
    gap_limit_s: float,
) -> list[RunSegment]:
    """Segment sorted native elapsed times into continuous runs; never span a boundary."""
    times = list(times_s)
    tyre_points = {round(t, 6) for t in tyre_replacement_s}

    def excluded_reason(t: float) -> RunBoundaryReason | None:
        for start, end, reason in excluded_intervals:
            if start <= t <= end:
                return reason
        return None

    runs: list[RunSegment] = []
    current: list[int] = []
    for i, t in enumerate(times):
        reason = excluded_reason(t)
        if reason is not None:
            if current:
                runs.append(_finish_run(entry, current, times, reason))
                current = []
            continue
        if current and round(t, 6) in tyre_points:
            runs.append(_finish_run(entry, current, times, RunBoundaryReason.TYRE_REPLACEMENT))
            current = []
        elif current and (t - times[current[-1]]) > gap_limit_s:
            runs.append(_finish_run(entry, current, times, RunBoundaryReason.EXCESSIVE_GAP))
            current = []
        current.append(i)
    if current:
        runs.append(_finish_run(entry, current, times, RunBoundaryReason.RUN_END))
    return runs


def _finish_run(entry: str, indices: list[int], times: list[float], end_reason: RunBoundaryReason) -> RunSegment:
    return RunSegment(
        entry=entry,
        sample_indices=tuple(indices),
        start_time_s=times[indices[0]],
        end_time_s=times[indices[-1]],
        end_boundary_reason=end_reason,
    )
