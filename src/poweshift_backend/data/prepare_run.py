"""Compose commits 1-3 over the admitted Bahrain entries and emit reproducible Phase 2 evidence."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from poweshift_backend.contracts.acquisition import SessionIdentity
from poweshift_backend.contracts.preparation import ArtifactProvenance, CoverageState, SplitManifest
from poweshift_backend.data.coverage_disposition import build_admission_disposition
from poweshift_backend.data.export import write_manifest
from poweshift_backend.data.prepare_geometry import GeometryTrainingDay, build_training_track_profile
from poweshift_backend.data.prepare_serialize import (
    write_event_timeline,
    write_pit_projection,
    write_stint_packages,
    write_target_bundle,
    write_track_profile,
)
from poweshift_backend.data.prepare_targets import build_lap_time_target_bundle
from poweshift_backend.data.preparation_limits import TrainingDayPaths, derive_preprocessing_spec
from poweshift_backend.data.protected_dirs import check_protected_directories
from poweshift_backend.events.timeline import build_race_control_events, build_session_status_events, build_track_status_events
from poweshift_backend.information.projector import project_pit_records
from poweshift_backend.prepare.admission import bundle_sha256, resolve_admitted_entries, validate_disposition
from poweshift_backend.prepare.normalise import speed_series_kmh_to_si
from poweshift_backend.prepare.runs import (
    RunSegment,
    garage_stop_intervals_s,
    red_flag_intervals_s,
    split_into_runs,
    tyre_history,
    tyre_replacement_times_s,
)
from poweshift_backend.prepare.windows import TyreContext, build_stint_packages, resolve_split

CONFIG_VERSION = "phase2-v1"

_EVIDENCE_LIMITS_STATEMENT = (
    "This is a preparation result only. Passing these checks does not show that any model built on this "
    "data can predict a driving profile, tell cars apart, measure energy use accurately, produce a "
    "ranking, judge race strategy, prove race readiness, or replace live timing. Every record here comes "
    "from Bahrain preseason testing, not a qualifying session or a race, and must not be read as either."
)

_CAR_FEATURE_COLUMNS = ["source_row", "Date", "Time", "DriverNumber", "Speed", "RPM", "Throttle", "Brake", "nGear", "DRS"]


def _session_identity(session: dict) -> SessionIdentity:
    """Parse a bundle session's identity; the bundle stores its date as an ISO string."""
    fields = dict(session["identity"])
    fields["date"] = date.fromisoformat(fields["date"])
    return SessionIdentity(**fields)


def run_preparation(bundle_path: Path, evidence_root: Path, reviewer: str, recorded_on: date) -> Path:
    """Run the whole approved Phase 2 preparation and return the phase-end evidence manifest path."""
    bundle = json.loads(bundle_path.read_text())
    reconstruction_dir = evidence_root / "reconstruction_inputs"
    targets_dir = evidence_root / "targets"
    pit_dir = evidence_root / "pit_source"
    spec_dir = evidence_root / "spec"
    coverage_dir = evidence_root / "coverage"

    disposition = build_admission_disposition(bundle, bundle_path, reviewer, recorded_on)
    disposition_path = coverage_dir / "coverage_disposition.json"
    disposition_sha256 = write_manifest(disposition.model_dump(mode="json"), disposition_path)
    disposition = validate_disposition(disposition, bundle_path)

    split_manifest = SplitManifest(training="Test 1", selection=date(2026, 2, 18), final_evaluation=(date(2026, 2, 19), date(2026, 2, 20)))

    training_sessions = [s for s in bundle["sessions"] if s["identity"]["test_number"] == 1]
    spec, spec_derivation = derive_preprocessing_spec(
        [
            TrainingDayPaths(
                date=s["identity"]["date"],
                car_path=Path(s["exports"]["car"]["path"]),
                laps_path=Path(s["exports"]["laps"]["path"]),
                track_status_path=Path(s["exports"]["track_status"]["path"]),
            )
            for s in training_sessions
        ]
    )
    spec_path = spec_dir / "preprocessing_spec.json"
    spec_sha256 = write_manifest(spec.model_dump(mode="json"), spec_path)
    derivation_path = spec_dir / "preprocessing_spec_derivation.json"
    derivation_sha256 = write_manifest(spec_derivation, derivation_path)

    geometry_training_days = [
        GeometryTrainingDay(
            identity=_session_identity(s),
            laps_path=Path(s["exports"]["laps"]["path"]),
            position_path=Path(s["exports"]["position"]["path"]),
            admitted_entries=resolve_admitted_entries(disposition, s, s["identity"]["date"]),
        )
        for s in training_sessions
    ]
    profile, geometry_derivation = build_training_track_profile(geometry_training_days, config_version=f"{CONFIG_VERSION}-geometry")
    geometry_result = write_track_profile(profile, source_label="bahrain_test1_reference", out_dir=reconstruction_dir)
    geometry_derivation_path = spec_dir / "track_profile_derivation.json"
    geometry_derivation_sha256 = write_manifest(geometry_derivation, geometry_derivation_path)

    session_results = []
    totals = {"stint_packages": 0, "events": 0, "target_records": 0, "pit_records": 0}
    for session in bundle["sessions"]:
        result, session_totals = _prepare_session(session, disposition, spec, split_manifest, reconstruction_dir, targets_dir, pit_dir)
        session_results.append(result)
        for key in totals:
            totals[key] += session_totals[key]

    check_protected_directories(reconstruction_dir, targets_dir, pit_dir)

    evidence = {
        "bundle_path": str(bundle_path),
        "bundle_sha256": bundle_sha256(bundle_path),
        "coverage_disposition": {"path": str(disposition_path), "sha256": disposition_sha256, "choice": disposition.choice.value},
        "split_manifest": split_manifest.model_dump(mode="json"),
        "preprocessing_spec": {
            "path": str(spec_path),
            "sha256": spec_sha256,
            "derivation_path": str(derivation_path),
            "derivation_sha256": derivation_sha256,
        },
        "track_profile": {
            **geometry_result,
            "derivation_path": str(geometry_derivation_path),
            "derivation_sha256": geometry_derivation_sha256,
        },
        "sessions": session_results,
        "counts": totals,
        "evidence_limits": _EVIDENCE_LIMITS_STATEMENT,
    }
    evidence_path = evidence_root / "phase2_evidence_manifest.json"
    write_manifest(evidence, evidence_path)
    return evidence_path


def _prepare_session(
    session: dict,
    disposition,
    spec,
    split_manifest: SplitManifest,
    reconstruction_dir: Path,
    targets_dir: Path,
    pit_dir: Path,
) -> tuple[dict, dict]:
    identity = _session_identity(session)
    session_key = session["identity"]["date"]
    admitted_entries = resolve_admitted_entries(disposition, session, session_key)
    split = resolve_split(identity.date, identity.test_number, split_manifest)

    car = pd.read_parquet(session["exports"]["car"]["path"], columns=_CAR_FEATURE_COLUMNS)
    laps = pd.read_parquet(session["exports"]["laps"]["path"])
    track_status = pd.read_parquet(session["exports"]["track_status"]["path"])
    session_status = pd.read_parquet(session["exports"]["session_status"]["path"])
    race_control_messages = pd.read_parquet(session["exports"]["race_control_messages"]["path"])

    packages = _build_session_stint_packages(car, laps, track_status, identity, session_key, admitted_entries, split, spec)
    stint_result = write_stint_packages(packages, session_key, reconstruction_dir)

    session_start = pd.Timestamp((car["Date"] - car["Time"]).iloc[0])
    events = (
        build_track_status_events(track_status, session_key)
        + build_session_status_events(session_status, session_key)
        + build_race_control_events(race_control_messages, session_key, session_start)
    )
    event_result = write_event_timeline(events, session_key, reconstruction_dir)

    admitted_laps = laps[laps["DriverNumber"].astype(str).isin(admitted_entries)]
    target_provenance = ArtifactProvenance(
        source_identity=identity,
        source_rows=tuple(str(row) for row in admitted_laps["source_row"]),
        coverage_state=CoverageState.ADMITTED,
        config_version=f"{CONFIG_VERSION}-targets",
    )
    target_bundle = build_lap_time_target_bundle(laps, admitted_entries, target_provenance)
    target_result = write_target_bundle(target_bundle, session_key, targets_dir)

    pit_provenance = ArtifactProvenance(
        source_identity=identity,
        source_rows=tuple(str(row) for row in admitted_laps["source_row"]),
        coverage_state=CoverageState.ADMITTED,
        config_version=f"{CONFIG_VERSION}-pit",
    )
    pit_projection = project_pit_records(admitted_laps, pit_provenance)
    pit_result = write_pit_projection(pit_projection, session_key, pit_dir)

    result = {
        "session_key": session_key,
        "identity": identity.model_dump(mode="json"),
        "split": split,
        "admitted_entries": admitted_entries,
        "excluded_entries": session["exclusions"],
        "stint_packages": stint_result,
        "events": event_result,
        "targets": target_result,
        "pit_source": pit_result,
    }
    totals = {
        "stint_packages": stint_result["n_packages"],
        "events": event_result["n_events"],
        "target_records": target_result["n_records"],
        "pit_records": pit_result["n_records"],
    }
    return result, totals


def _build_session_stint_packages(car, laps, track_status, identity, session_key, admitted_entries, split, spec) -> list:
    red_flags = red_flag_intervals_s(track_status)
    packages = []
    for entry in admitted_entries:
        group = car[car["DriverNumber"] == entry].sort_values("Time").reset_index(drop=True)
        if group.empty:
            continue
        times_s = group["Time"].dt.total_seconds()
        feature_columns = {
            "speed_ms": speed_series_kmh_to_si(group["Speed"]),
            "rpm": group["RPM"].astype(float),
            "throttle_pct": group["Throttle"].astype(float),
            "brake": group["Brake"].astype(float),
            "n_gear": group["nGear"].astype(float),
            "drs": group["DRS"].astype(float),
        }
        source_row_values = group["source_row"]

        garage = garage_stop_intervals_s(laps, entry)
        tyre_times = tyre_replacement_times_s(laps, entry)
        runs = split_into_runs(entry, times_s, garage + red_flags, tyre_times, gap_limit_s=spec.gap_limit_s)

        stint_intervals = _lap_stint_intervals(laps, entry)
        tyre_by_stint = {context.stint: context for context in tyre_history(laps, entry)}

        for run in runs:
            packages += _build_run_packages(
                entry, run, times_s, feature_columns, source_row_values, stint_intervals, tyre_by_stint, identity, session_key, split, spec
            )
    return packages


def _build_run_packages(
    entry: str,
    run: RunSegment,
    times_s: pd.Series,
    feature_columns: dict,
    source_row_values: pd.Series,
    stint_intervals: list[tuple[float, float, int]],
    tyre_by_stint: dict[int, TyreContext],
    identity: SessionIdentity,
    session_key: str,
    split: str,
    spec,
) -> list:
    stint_number = _nearest_stint(stint_intervals, run.start_time_s)
    tyre = tyre_by_stint.get(stint_number) if stint_number is not None else None
    if tyre is None:
        tyre = TyreContext(stint=stint_number or 0, compound=None, tyre_life=None, fresh_tyre=None, tyre_set_id=None)

    run_source_rows = tuple(str(value) for value in source_row_values.iloc[list(run.sample_indices)])
    provenance = ArtifactProvenance(
        source_identity=identity,
        source_rows=run_source_rows,
        coverage_state=CoverageState.ADMITTED,
        config_version=f"{CONFIG_VERSION}-stints",
    )
    return build_stint_packages(
        entry=entry,
        session_key=session_key,
        run=run,
        times_s=times_s,
        feature_columns=feature_columns,
        tyre=tyre,
        programme_context=identity.session_kind,
        quality_context="measured",
        split=split,
        spec=spec,
        provenance=provenance,
    )


def _lap_stint_intervals(laps: pd.DataFrame, entry: str) -> list[tuple[float, float, int]]:
    """This entry's [lap start, lap end] time windows, each tagged with its own recorded stint."""
    driver_laps = laps[laps["DriverNumber"].astype(str) == entry].sort_values("LapStartTime")
    intervals = []
    for _, lap in driver_laps.iterrows():
        if pd.isna(lap["LapStartTime"]) or pd.isna(lap["Stint"]):
            continue
        intervals.append((lap["LapStartTime"].total_seconds(), lap["Time"].total_seconds(), int(lap["Stint"])))
    return intervals


def _nearest_stint(intervals: list[tuple[float, float, int]], t: float) -> int | None:
    """The stint whose lap window contains t, else the stint of the nearest lap window by boundary distance."""
    if not intervals:
        return None
    for start, end, stint in intervals:
        if start <= t <= end:
            return stint
    return min(intervals, key=lambda interval: interval[0] - t if t < interval[0] else t - interval[1])[2]
