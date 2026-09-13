"""Build the one target kind a Bahrain testing session genuinely supports: lap time."""

import pandas as pd

from poweshift_backend.contracts.preparation import ArtifactProvenance, EvaluationSpec, TargetKind
from poweshift_backend.targets.bundle import LapTimeTarget, TargetBundle, TargetStatus, build_target_bundle

LAP_TIME_EVALUATION = EvaluationSpec(
    target_kind=TargetKind.LAP_TIME,
    target_eligibility="every completed lap recorded for an admitted entry; incomplete (never-timed) laps are retained with status no_time rather than dropped",
    comparable_entry_rule="lap times are only comparable within the same entry and session; this testing source supports no cross-entry ranking or gap claim",
    status_treatment="a deleted lap keeps its deletion reason and no value; a lap without a recorded time keeps no_time and no value; a lap the source parser did not flag accurate keeps unavailable and no value",
    valid_lap_rule="a lap is valid only when it carries a source LapTime, is not marked Deleted, and IsAccurate is true",
)


def build_lap_time_target_bundle(
    laps: pd.DataFrame, admitted_entries: list[str], provenance: ArtifactProvenance
) -> TargetBundle:
    """One LapTimeTarget per completed lap of an admitted entry; status never hides a deleted or timeless lap."""
    admitted = set(admitted_entries)
    day_laps = laps[laps["DriverNumber"].astype(str).isin(admitted)].sort_values(["DriverNumber", "LapNumber"])
    records = tuple(_lap_time_target(lap) for _, lap in day_laps.iterrows())
    return build_target_bundle(TargetKind.LAP_TIME, provenance, LAP_TIME_EVALUATION, records)


def _lap_time_target(lap: pd.Series) -> LapTimeTarget:
    deleted = bool(lap["Deleted"])
    is_accurate = bool(lap["IsAccurate"])
    lap_time = lap.get("LapTime")
    has_time = pd.notna(lap_time)

    if deleted:
        status, detail, value = TargetStatus.DELETED, (str(lap["DeletedReason"]) or None), None
    elif not has_time:
        status, detail, value = TargetStatus.NO_TIME, None, None
    elif not is_accurate:
        status, detail, value = TargetStatus.UNAVAILABLE, "lap not flagged accurate by the source parser", None
    else:
        status, detail, value = TargetStatus.VALID, None, float(lap_time.total_seconds())

    return LapTimeTarget(
        entry=str(lap["DriverNumber"]),
        observed_availability_time_s=float(lap["Time"].total_seconds()),
        units="s",
        value=value,
        status=status,
        status_detail=detail,
        comparison_mask=status is TargetStatus.VALID,
        source_rows=(str(lap["source_row"]),),
    )
