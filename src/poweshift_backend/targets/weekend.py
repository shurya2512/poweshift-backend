"""Build masked weekend timing targets from recorded FastF1 exports."""

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import itertools
import json
from math import isfinite
from pathlib import Path
import shutil

import fastf1
import pandas as pd

from poweshift_backend.targets.bundle import ComparableTimingPair, LapTimeTarget, TargetStatus


_SEGMENTS = ("Q1", "Q2", "Q3")
_CONTROL_REASONS = {
    "2": "yellow",
    "4": "safety_car",
    "5": "red_flag",
    "6": "virtual_safety_car",
}


@dataclass(frozen=True)
class LapObservation:
    """One lap target with the observed context needed to mask it."""

    target: LapTimeTarget
    session_key: str
    qualifying_segment: str | None
    compound: str | None
    fuel_known: bool
    tyre_known: bool
    weather_known: bool
    track_phase_known: bool
    traffic_clear: bool
    pit_free: bool
    coverage_complete: bool


@dataclass(frozen=True)
class RaceWallTimeStatus:
    """Completed-lap status for an entry at one common wall time."""

    entry: str
    wall_time_s: float
    completed_laps: int
    status: TargetStatus
    status_mask: bool
    context_reasons: tuple[str, ...]
    source_rows: tuple[str, ...]


@dataclass(frozen=True)
class RaceCheckpointGap:
    """An observed same-lap checkpoint gap, or a lap-deficit status."""

    first: str
    second: str
    checkpoint_lap: int
    value_s: float | None
    status: TargetStatus
    comparison_mask: bool
    context_reasons: tuple[str, ...]
    source_rows: tuple[str, ...]


@dataclass(frozen=True)
class WeekendTargets:
    """Target records and source identity for one extracted session."""

    source_hash: str
    laps: tuple[LapObservation, ...]
    timing_pairs: tuple[ComparableTimingPair, ...]
    race_wall_time_statuses: tuple[RaceWallTimeStatus, ...] = ()
    race_checkpoint_gaps: tuple[RaceCheckpointGap, ...] = ()


def extract_qualifying_targets(
    laps: pd.DataFrame,
    qualifying_sessions: tuple[pd.DataFrame | None, ...],
    *,
    source_hash: str,
    session_key: str,
    cutoff_s: float,
    weather_known: bool,
    session_kind: str = "qualifying",
) -> WeekendTargets:
    """Extract valid lap observations and within-session timing pairs."""
    _require_hash(source_hash)
    if session_kind not in {"practice", "qualifying"}:
        raise ValueError("session_kind must be practice or qualifying")
    segments = _segment_by_index(qualifying_sessions) if session_kind == "qualifying" else {}
    observations = tuple(
        _lap_observation(row, index, session_key, segments.get(index), weather_known, session_kind)
        for index, row in laps.iterrows()
    )
    pairs = _timing_pairs(observations, session_kind, cutoff_s)
    return WeekendTargets(source_hash=source_hash, laps=observations, timing_pairs=pairs)


def load_qualifying_targets(
    source_session_dir: Path,
    isolated_cache_root: Path,
    *,
    source_hash: str,
) -> WeekendTargets:
    """Load one copied qualifying cache without modifying the approved source."""
    if source_session_dir.name.endswith("_Qualifying") is False:
        raise ValueError("source session must be a qualifying cache")
    weekend = source_session_dir.parent.name
    cache_root = source_session_dir.parent.parent
    if _weekend_hash(cache_root, weekend) != source_hash:
        raise ValueError("source hash does not match the audited weekend cache")
    source_snapshot = _session_snapshot_hash(source_session_dir)
    cache_target = isolated_cache_root / "2026" / weekend / source_session_dir.name
    if cache_target.exists():
        raise FileExistsError(f"isolated cache already contains {source_session_dir.name}")
    cache_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_session_dir, cache_target)
    if _session_snapshot_hash(cache_target) != source_snapshot:
        raise ValueError("copied qualifying cache differs from the audited source")
    fastf1.Cache.enable_cache(str(isolated_cache_root))
    event_name = weekend[11:].replace("_", " ")
    session = fastf1.get_session(2026, event_name, "Q")
    _verify_qualifying_identity(session, event_name, source_session_dir.name, weekend)
    session.load(laps=True, telemetry=False, weather=True, messages=True)
    if _session_snapshot_hash(cache_target) != source_snapshot:
        raise ValueError("qualifying load changed the isolated cache")
    laps = pd.DataFrame(session.laps)
    cutoff_s = _max_seconds(laps["Time"])
    return extract_qualifying_targets(
        laps,
        tuple(session.laps.split_qualifying_sessions()),
        source_hash=source_hash,
        session_key=source_session_dir.name,
        cutoff_s=cutoff_s,
        weather_known=not session.weather_data.empty,
    )


def extract_race_export(export_dir: Path, *, manifest_sha256: str) -> WeekendTargets:
    """Read one manifest-bound race export after validating its exact manifest."""
    manifest_path = export_dir / "acquisition_bundle.json"
    if _file_hash(manifest_path) != manifest_sha256:
        raise ValueError("manifest hash does not match the required race export")
    manifest = json.loads(manifest_path.read_text())
    laps_record = manifest["exports"]["laps"]
    laps_path = Path(laps_record["path"])
    if not laps_path.is_absolute() and not laps_path.exists():
        laps_path = export_dir / laps_path
    if _file_hash(laps_path) != laps_record["sha256"]:
        raise ValueError("laps table hash does not match the race manifest")
    return extract_race_targets(
        pd.read_parquet(laps_path),
        roster=tuple(str(entry) for entry in manifest["roster"]),
        source_hash=manifest["source_snapshot_sha256"],
        weather_known="weather" in manifest["exports"],
    )


def extract_race_targets(
    laps: pd.DataFrame,
    *,
    roster: tuple[str, ...],
    source_hash: str,
    weather_known: bool = True,
) -> WeekendTargets:
    """Extract completed-lap progress and same-checkpoint race gaps."""
    _require_hash(source_hash)
    completed = {entry: _completed_laps(laps, entry, weather_known) for entry in roster}
    wall_times = sorted({lap.time_s for entry_laps in completed.values() for lap in entry_laps.completed.values()})
    statuses = tuple(
        _wall_time_status(entry, wall_time_s, completed[entry])
        for wall_time_s in wall_times
        for entry in roster
    )
    gaps = tuple(
        gap
        for first, second in itertools.combinations(roster, 2)
        for gap in _checkpoint_gaps(first, second, completed[first], completed[second])
    )
    return WeekendTargets(
        source_hash=source_hash,
        laps=(),
        timing_pairs=(),
        race_wall_time_statuses=statuses,
        race_checkpoint_gaps=gaps,
    )


def write_weekend_target_report(audit_path: Path, isolated_cache_root: Path, destination: Path) -> Path:
    """Write immutable target counts for audited training and selection sources."""
    audit_bytes = audit_path.read_bytes()
    audit = json.loads(audit_bytes)
    if audit["source_status"] != "verified":
        raise ValueError("target report requires a verified source audit")
    qualifying_reports = []
    for weekend in audit["sessions"]:
        if weekend["partition"] not in {"training", "selection"}:
            continue
        for session_name in weekend["session_names"]:
            if not session_name.endswith("_Qualifying") or "Sprint_" in session_name:
                continue
            targets = load_qualifying_targets(
                Path(audit["cache_root"]) / weekend["weekend"] / session_name,
                isolated_cache_root / weekend["weekend"],
                source_hash=weekend["source_hash"],
            )
            qualifying_reports.append({
                "weekend": weekend["weekend"],
                "partition": weekend["partition"],
                "session": session_name,
                "source_hash": targets.source_hash,
                "lap_statuses": _status_counts(item.target.status for item in targets.laps),
                "pairs": len(targets.timing_pairs),
                "usable_pairs": sum(pair.comparison_mask for pair in targets.timing_pairs),
                "pairs_by_segment": _segment_counts(targets.timing_pairs),
            })
    race_reports = []
    for race in audit["race_sources"]:
        targets = extract_race_export(Path(race["manifest_path"]).parent, manifest_sha256=race["manifest_sha256"])
        race_reports.append({
            "weekend": race["weekend"],
            "manifest_sha256": race["manifest_sha256"],
            "source_snapshot_sha256": targets.source_hash,
            "wall_time_statuses": len(targets.race_wall_time_statuses),
            "checkpoint_statuses": _status_counts(item.status for item in targets.race_checkpoint_gaps),
            "usable_checkpoint_gaps": sum(item.comparison_mask for item in targets.race_checkpoint_gaps),
        })
    report = {
        "report_kind": "weekend_targets_v1",
        "source_audit_sha256": sha256(audit_bytes).hexdigest(),
        "availability_semantics": "Lap Time completion session time is used only as a completed-session reconstruction cutoff, not evidence of real-time publication of later flags.",
        "qualifying": qualifying_reports,
        "race": race_reports,
        "gate": {
            "qualifying_pairs_available": sum(item["usable_pairs"] for item in qualifying_reports),
            "race_checkpoint_gaps_available": sum(item["usable_checkpoint_gaps"] for item in race_reports),
            "continuous_along_track_progress": "unavailable_without_geometry",
            "state": "blocked",
        },
    }
    content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if destination.exists() and destination.read_text() != content:
        raise FileExistsError(f"immutable target report differs: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content)
    return destination


@dataclass(frozen=True)
class _CompletedLap:
    lap_number: int
    time_s: float
    source_row: str
    comparison_mask: bool
    context_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _EntryLaps:
    completed: dict[int, _CompletedLap]
    unavailable_reasons: tuple[str, ...]
    unavailable_laps: frozenset[int]


def _segment_by_index(qualifying_sessions: tuple[pd.DataFrame | None, ...]) -> dict[object, str]:
    if len(qualifying_sessions) > len(_SEGMENTS):
        raise ValueError("qualifying sessions may contain only Q1, Q2 and Q3")
    return {
        index: _SEGMENTS[position]
        for position, part in enumerate(qualifying_sessions)
        if part is not None
        for index in part.index
    }


def _lap_observation(
    row: pd.Series,
    index: object,
    session_key: str,
    qualifying_segment: str | None,
    weather_known: bool,
    session_kind: str,
) -> LapObservation:
    lap_time = _seconds(row.get("LapTime"))
    availability_s = _seconds(row.get("Time"))
    if availability_s is None:
        raise ValueError("lap observation has no finite availability time")
    status, detail = _lap_status(row, lap_time)
    pit_free = _missing(row.get("PitInTime")) and _missing(row.get("PitOutTime"))
    track_phase_known = not _missing(row.get("TrackStatus"))
    track_clear = _track_clear(row.get("TrackStatus"))
    coverage_complete = all(column in row.index for column in ("DriverNumber", "LapTime", "Time", "IsAccurate"))
    entry = str(row["DriverNumber"])
    value = lap_time if status is TargetStatus.VALID else None
    comparison_mask = status is TargetStatus.VALID and pit_free and track_clear and coverage_complete
    return LapObservation(
        target=LapTimeTarget(
            entry=entry,
            observed_availability_time_s=availability_s,
            units="s",
            value=value,
            status=status,
            status_detail=detail,
            comparison_mask=comparison_mask,
            source_rows=(_source_row(row, index),),
        ),
        session_key=session_key,
        qualifying_segment=qualifying_segment if session_kind == "qualifying" else None,
        compound=_string_or_none(row.get("Compound")),
        fuel_known=False,
        tyre_known=not _missing(row.get("Compound")),
        weather_known=weather_known,
        track_phase_known=track_phase_known,
        traffic_clear=False,
        pit_free=pit_free,
        coverage_complete=coverage_complete,
    )


def _timing_pairs(
    observations: tuple[LapObservation, ...], session_kind: str, cutoff_s: float
) -> tuple[ComparableTimingPair, ...]:
    groups: dict[str | None, dict[str, LapObservation]] = {}
    for observation in observations:
        if (
            observation.target.status is not TargetStatus.VALID
            or not observation.target.comparison_mask
            or observation.target.observed_availability_time_s > cutoff_s
        ):
            continue
        key = observation.qualifying_segment if session_kind == "qualifying" else None
        existing = groups.setdefault(key, {}).get(observation.target.entry)
        if existing is None or observation.target.value < existing.target.value:
            groups[key][observation.target.entry] = observation
    pairs: list[ComparableTimingPair] = []
    for segment, by_entry in groups.items():
        for first, second in itertools.combinations(by_entry.values(), 2):
            pairs.append(_timing_pair(first, second, session_kind, segment, cutoff_s))
    return tuple(pairs)


def _timing_pair(
    first: LapObservation,
    second: LapObservation,
    session_kind: str,
    segment: str | None,
    cutoff_s: float,
) -> ComparableTimingPair:
    tyre_matched = first.tyre_known and second.tyre_known and first.compound == second.compound
    comparison_mask = (
        first.weather_known
        and second.weather_known
        and first.track_phase_known
        and second.track_phase_known
        and first.pit_free
        and second.pit_free
        and first.coverage_complete
        and second.coverage_complete
    )
    if session_kind == "practice":
        comparison_mask = (
            comparison_mask
            and first.traffic_clear
            and second.traffic_clear
            and tyre_matched
            and first.fuel_known
            and second.fuel_known
        )
    return ComparableTimingPair(
        first=first.target,
        second=second.target,
        session_kind=session_kind,
        qualifying_segment=segment,
        tyre_matched=tyre_matched,
        fuel_known=first.fuel_known and second.fuel_known,
        weather_known=first.weather_known and second.weather_known,
        track_phase_known=first.track_phase_known and second.track_phase_known,
        traffic_clear=first.traffic_clear and second.traffic_clear,
        pit_free=first.pit_free and second.pit_free,
        coverage_complete=first.coverage_complete and second.coverage_complete,
        comparison_mask=comparison_mask,
        first_session_key=first.session_key,
        second_session_key=second.session_key,
        first_segment=first.qualifying_segment or "practice",
        second_segment=second.qualifying_segment or "practice",
        cutoff_s=cutoff_s,
    )


def _completed_laps(laps: pd.DataFrame, entry: str, weather_known: bool) -> _EntryLaps:
    values: dict[int, _CompletedLap] = {}
    unavailable_reasons: list[str] = []
    unavailable_laps: set[int] = set()
    for index, row in laps.loc[laps["DriverNumber"].astype(str) == entry].iterrows():
        lap_number = row.get("LapNumber")
        time_s = _seconds(row.get("Time"))
        if _missing(lap_number) or time_s is None or _missing(row.get("LapTime")):
            unavailable_reasons.append("no_equivalent_completed_checkpoint")
            if not _missing(lap_number):
                unavailable_laps.add(int(lap_number))
            continue
        number = int(lap_number)
        reasons = _race_context_reasons(row, weather_known)
        candidate = _CompletedLap(
            lap_number=number,
            time_s=time_s,
            source_row=_source_row(row, index),
            comparison_mask=not reasons,
            context_reasons=reasons,
        )
        existing = values.get(number)
        if existing is None or candidate.time_s < existing.time_s:
            values[number] = candidate
    return _EntryLaps(values, tuple(sorted(set(unavailable_reasons))), frozenset(unavailable_laps))


def _wall_time_status(entry: str, wall_time_s: float, laps: _EntryLaps) -> RaceWallTimeStatus:
    reached = [lap for lap in laps.completed.values() if lap.time_s <= wall_time_s]
    if not reached:
        return RaceWallTimeStatus(entry, wall_time_s, 0, TargetStatus.NO_TIME, False, ("no_completed_lap",), ())
    latest = max(reached, key=lambda lap: lap.lap_number)
    return RaceWallTimeStatus(
        entry,
        wall_time_s,
        latest.lap_number,
        TargetStatus.VALID,
        False,
        latest.context_reasons,
        (latest.source_row,),
    )


def _checkpoint_gaps(
    first: str,
    second: str,
    first_laps: _EntryLaps,
    second_laps: _EntryLaps,
) -> tuple[RaceCheckpointGap, ...]:
    common = sorted(first_laps.completed.keys() & second_laps.completed.keys())
    gaps = [
        RaceCheckpointGap(
            first,
            second,
            checkpoint,
            first_laps.completed[checkpoint].time_s - second_laps.completed[checkpoint].time_s,
            TargetStatus.VALID,
            first_laps.completed[checkpoint].comparison_mask and second_laps.completed[checkpoint].comparison_mask,
            tuple(sorted(set(first_laps.completed[checkpoint].context_reasons + second_laps.completed[checkpoint].context_reasons))),
            (first_laps.completed[checkpoint].source_row, second_laps.completed[checkpoint].source_row),
        )
        for checkpoint in common
    ]
    first_max = max(first_laps.completed, default=0)
    second_max = max(second_laps.completed, default=0)
    if first_max != second_max:
        checkpoint = max(first_max, second_max)
        missing_completion = checkpoint in first_laps.unavailable_laps or checkpoint in second_laps.unavailable_laps
        status = TargetStatus.LAP_DEFICIT if first_max and second_max and not missing_completion else TargetStatus.UNAVAILABLE
        reasons = ("lap_deficit",) if status is TargetStatus.LAP_DEFICIT else (
            first_laps.unavailable_reasons + second_laps.unavailable_reasons or ("no_equivalent_completed_checkpoint",)
        )
        gaps.append(
            RaceCheckpointGap(
                first,
                second,
                checkpoint,
                None,
                status,
                False,
                tuple(sorted(set(reasons))),
                (),
            )
        )
    return tuple(gaps)


def _lap_status(row: pd.Series, lap_time: float | None) -> tuple[TargetStatus, str | None]:
    if _is_true(row.get("Deleted")):
        return TargetStatus.DELETED, _string_or_none(row.get("DeletedReason")) or "deleted"
    if lap_time is None:
        return TargetStatus.NO_TIME, "lap_time_missing"
    if _is_true(row.get("FastF1Generated")):
        return TargetStatus.UNAVAILABLE, "parser_generated"
    if not _is_true(row.get("IsAccurate")):
        return TargetStatus.UNAVAILABLE, "parser_inaccurate"
    return TargetStatus.VALID, None


def _race_context_reasons(row: pd.Series, weather_known: bool) -> tuple[str, ...]:
    reasons: list[str] = []
    if _is_true(row.get("Deleted")):
        reasons.append("deleted")
    if _is_true(row.get("FastF1Generated")):
        reasons.append("parser_generated")
    if not _is_true(row.get("IsAccurate")):
        reasons.append("parser_inaccurate")
    if not _missing(row.get("PitInTime")) or not _missing(row.get("PitOutTime")):
        reasons.append("pit")
    status = _string_or_none(row.get("TrackStatus"))
    if status is None:
        reasons.append("track_status_missing")
    elif status != "1":
        reasons.extend(_CONTROL_REASONS.get(code, "track_status_unknown") for code in status if code != "1")
    if not weather_known:
        reasons.append("weather_missing")
    return tuple(sorted(set(reasons)))


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _status_counts(statuses: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status.value] = counts.get(status.value, 0) + 1
    return dict(sorted(counts.items()))


def _segment_counts(pairs: tuple[ComparableTimingPair, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pair in pairs:
        counts[pair.qualifying_segment] = counts.get(pair.qualifying_segment, 0) + 1
    return dict(sorted(counts.items()))


def _weekend_hash(cache_root: Path, weekend: str) -> str:
    digest = sha256()
    for path in sorted((cache_root / weekend).rglob("*.ff1pkl")):
        digest.update(str(path.relative_to(cache_root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _session_snapshot_hash(session_dir: Path) -> str:
    digest = sha256()
    for path in sorted(session_dir.glob("*.ff1pkl")):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _verify_qualifying_identity(session: object, event_name: str, session_name: str, weekend: str) -> None:
    session_date = date.fromisoformat(session_name[:10])
    event_date = date.fromisoformat(weekend[:10])
    if (
        session.event["EventName"] != event_name
        or session.name != "Qualifying"
        or pd.Timestamp(session.date).date() != session_date
        or pd.Timestamp(session.event["EventDate"]).date() != event_date
    ):
        raise ValueError("FastF1 returned an unexpected qualifying session")


def _require_hash(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("source hash must be a lowercase SHA-256 digest")


def _source_row(row: pd.Series, index: object) -> str:
    return str(row.get("NativeSourceRow", row.get("source_row", index)))


def _seconds(value: object) -> float | None:
    if _missing(value):
        return None
    seconds = pd.Timedelta(value).total_seconds()
    return seconds if isfinite(seconds) else None


def _max_seconds(values: pd.Series) -> float:
    result = max((seconds for value in values if (seconds := _seconds(value)) is not None), default=None)
    if result is None:
        raise ValueError("lap records contain no availability times")
    return result


def _track_clear(value: object) -> bool:
    return _string_or_none(value) == "1"


def _string_or_none(value: object) -> str | None:
    return None if _missing(value) else str(value)


def _missing(value: object) -> bool:
    return bool(pd.isna(value))


def _is_true(value: object) -> bool:
    return not _missing(value) and bool(value)
