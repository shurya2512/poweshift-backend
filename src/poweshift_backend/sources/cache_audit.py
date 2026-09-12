"""Read-only inventories and immutable cache audit artifacts."""

from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import pickle
import shutil

from poweshift_backend.contracts.representation import RaceSourceAudit, WeekendAudit, WeekendAuditSession


_REQUIRED_STREAMS = frozenset(
    {
        "_extended_timing_data.ff1pkl",
        "car_data.ff1pkl",
        "driver_info.ff1pkl",
        "position_data.ff1pkl",
        "race_control_messages.ff1pkl",
        "session_info.ff1pkl",
        "session_status_data.ff1pkl",
        "timing_app_data.ff1pkl",
        "track_status_data.ff1pkl",
        "weather_data.ff1pkl",
    }
)
_WEEKENDS = (
    ("2026-03-08_Australian_Grand_Prix", date(2026, 3, 8), "training"),
    ("2026-03-15_Chinese_Grand_Prix", date(2026, 3, 15), "training"),
    ("2026-03-29_Japanese_Grand_Prix", date(2026, 3, 29), "training"),
    ("2026-05-03_Miami_Grand_Prix", date(2026, 5, 3), "training"),
    ("2026-05-24_Canadian_Grand_Prix", date(2026, 5, 24), "training"),
    ("2026-06-07_Monaco_Grand_Prix", date(2026, 6, 7), "training"),
    ("2026-06-14_Barcelona_Grand_Prix", date(2026, 6, 14), "training"),
    ("2026-06-28_Austrian_Grand_Prix", date(2026, 6, 28), "training"),
    ("2026-07-05_British_Grand_Prix", date(2026, 7, 5), "training"),
    ("2026-07-19_Belgian_Grand_Prix", date(2026, 7, 19), "selection"),
    ("2026-07-26_Hungarian_Grand_Prix", date(2026, 7, 26), "final_evaluation"),
    ("2026-08-23_Dutch_Grand_Prix", date(2026, 8, 23), "final_evaluation"),
    ("2026-09-06_Italian_Grand_Prix", date(2026, 9, 6), "reserved"),
)


def cache_inventory(cache_dir: Path) -> dict[str, str]:
    """Return SHA-256 hashes without deserializing cache entries."""
    return {
        str(path.relative_to(cache_dir)): sha256(path.read_bytes()).hexdigest()
        for path in sorted(cache_dir.rglob("*.ff1pkl"))
    }


def snapshot_session(cache_dir: Path, session_date: str, day_number: int, destination: Path) -> dict[str, str]:
    """Seal the parser-cache records used for one testing day."""
    directories = list(cache_dir.glob(f"**/{session_date}_Day_{day_number}"))
    if len(directories) != 1:
        raise ValueError("expected exactly one parser-cache session directory")
    sources = sorted(directories[0].glob("*.ff1pkl"))
    if not sources:
        raise ValueError("parser-cache session directory is empty")
    result = {source.name: sha256(source.read_bytes()).hexdigest() for source in sources}
    if destination.exists():
        existing = {path.name: sha256(path.read_bytes()).hexdigest() for path in destination.glob("*.ff1pkl")}
        if existing != result:
            raise FileExistsError(f"immutable source snapshot differs: {destination}")
        return result
    destination.mkdir(parents=True)
    for source in sources:
        shutil.copyfile(source, destination / source.name)
    return result


def audit_weekend_cache(cache_root: Path, destination: Path, race_manifests: tuple[Path, ...] = ()) -> WeekendAudit:
    """Write an immutable audit without opening final or reserved content."""
    sessions = tuple(_audit_weekend(cache_root, *weekend) for weekend in _WEEKENDS)
    race_sources = tuple(_audit_race_manifest(path) for path in race_manifests)
    blockers = ["target_masks_missing"]
    used = tuple(session for session in sessions if session.content_access == "hashed")
    expected_races = {weekend for weekend, _, partition in _WEEKENDS if partition in {"training", "selection"}}
    missing_race_weekends = tuple(sorted(expected_races - {source.weekend for source in race_sources if source.source_state == "verified"}))
    if missing_race_weekends:
        blockers.insert(0, "race_source_missing")
    if any(session.source_state != "verified" for session in used):
        blockers.insert(0, "source_coverage_incomplete")
    source_status = "verified" if all(session.source_state == "verified" for session in used) and all(
        source.source_state == "verified" for source in race_sources
    ) else "incomplete"
    audit = WeekendAudit(
        cache_root=str(cache_root),
        sessions=sessions,
        race_sources=race_sources,
        source_status=source_status,
        missing_race_weekends=missing_race_weekends,
        blockers=tuple(blockers),
    )
    _write_immutable_json(destination, audit.model_dump(mode="json"))
    return audit


def _audit_weekend(cache_root: Path, weekend: str, event_date: date, partition: str) -> WeekendAuditSession:
    directory = cache_root / weekend
    session_dirs = tuple(sorted(path for path in directory.iterdir() if path.is_dir())) if directory.is_dir() else ()
    if partition in {"final_evaluation", "reserved"}:
        return WeekendAuditSession(
            weekend=weekend,
            partition=partition,
            event_date=event_date.isoformat(),
            session_count=len(session_dirs),
            session_names=tuple(path.name for path in session_dirs),
            stream_names=(),
            content_access="inventory_only",
            source_state="unproved",
            source_issues=("content_not_opened",),
            target_issues=("content_not_opened",),
        )
    files = tuple(path for session in session_dirs for path in sorted(session.glob("*.ff1pkl")))
    stream_names = tuple(sorted({path.name for path in files}))
    issues = _source_issues(session_dirs, weekend, event_date)
    return WeekendAuditSession(
        weekend=weekend,
        partition=partition,
        event_date=event_date.isoformat(),
        session_count=len(session_dirs),
        session_names=tuple(path.name for path in session_dirs),
        stream_names=stream_names,
        source_hash=_hash_files(cache_root, files) if files else None,
        content_access="hashed",
        source_state="verified" if not issues else "missing" if not session_dirs else "incomplete",
        source_issues=issues,
        target_issues=_target_issues(session_dirs),
    )


def _source_issues(session_dirs: tuple[Path, ...], weekend: str, event_date: date) -> tuple[str, ...]:
    issues: list[str] = []
    if not session_dirs:
        issues.append("session_directory_missing")
    for directory in session_dirs:
        stream_names = {path.name for path in directory.glob("*.ff1pkl")}
        if _REQUIRED_STREAMS.difference(stream_names):
            issues.append("required_stream_missing")
        try:
            session_date = date.fromisoformat(directory.name[:10])
        except ValueError:
            issues.append("session_date_unparseable")
            continue
        if session_date > event_date:
            issues.append("session_date_after_weekend")
        issues.extend(_identity_issues(directory, weekend, session_date))
    return tuple(sorted(set(issues)))


def _identity_issues(directory: Path, weekend: str, session_date: date) -> tuple[str, ...]:
    try:
        cached = _read_cache(directory / "session_info.ff1pkl")
        metadata = cached["data"]
        meeting = metadata["Meeting"]["Name"]
        name = metadata["Name"]
        path = metadata["Path"]
        start_date = metadata["StartDate"].date()
    except (KeyError, OSError, TypeError, ValueError, pickle.UnpicklingError, AttributeError):
        return ("session_identity_unreadable",)
    expected_name = directory.name[11:].replace("_", " ")
    expected_meeting = weekend[11:].replace("_", " ")
    expected_path = f"2026/{weekend}/{directory.name}/"
    issues: list[str] = []
    if meeting != expected_meeting or name != expected_name:
        issues.append("session_identity_mismatch")
    if path != expected_path:
        issues.append("session_path_mismatch")
    if start_date != session_date:
        issues.append("session_start_date_mismatch")
    return tuple(issues)


def _target_issues(session_dirs: tuple[Path, ...]) -> tuple[str, ...]:
    issues: list[str] = []
    for directory in session_dirs:
        source = directory / "timing_app_data.ff1pkl"
        try:
            cached = _read_cache(source)
            records = cached["data"]
            columns = set(records.columns)
            has_lap = bool(records["LapTime"].notna().any()) if "LapTime" in columns else False
        except (KeyError, OSError, TypeError, ValueError, pickle.UnpicklingError, AttributeError):
            issues.append("timing_data_unreadable")
            continue
        if not {"Driver", "LapTime", "Time"}.issubset(columns) or not has_lap:
            issues.append("timing_lap_fields_missing")
        elif directory.name.endswith("_Qualifying"):
            issues.append("qualifying_segmentation_not_derived")
        elif "Practice" in directory.name:
            issues.append("practice_context_missing")
        elif directory.name.endswith("_Race"):
            issues.append("race_checkpoint_targets_missing")
        else:
            issues.append("session_kind_not_supported")
    return tuple(sorted(set(issues)))


def _audit_race_manifest(manifest_path: Path) -> RaceSourceAudit:
    raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(raw)
        identity = manifest["identity"]
        snapshot = manifest["source_snapshot"]
        expected_identities = (
            (weekend, {"date": event_date.isoformat(), "event_name": weekend[11:].replace("_", " "), "session_kind": "race", "year": 2026})
            for weekend, event_date, partition in _WEEKENDS
            if partition in {"training", "selection"}
        )
        weekend = next((weekend for weekend, expected in expected_identities if identity == expected), "unknown")
        identity_ok = weekend != "unknown"
        if not identity_ok:
            return _incomplete_race_manifest(manifest_path, raw)
        snapshot_ok = _snapshot_hash(snapshot) == manifest["source_snapshot_sha256"]
        snapshot_ok = snapshot_ok and _snapshot_files_match(manifest_path, snapshot)
        exports_ok = _exports_match(manifest_path, manifest["exports"])
        coverage_ok = all(
            manifest["coverage"].get(name, {}).get("status") == "present"
            for name in ("car", "laps", "position", "tyres", "weather", "session_status", "track_status", "race_control_messages")
        )
        verified = (
            _REQUIRED_STREAMS.issubset(snapshot)
            and snapshot_ok
            and exports_ok
            and coverage_ok
        )
        snapshot_hash = manifest["source_snapshot_sha256"]
        roster_size = len(manifest["roster"])
        coverage_notes = _coverage_notes(manifest, manifest_path)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        verified = False
        snapshot_hash = "0" * 64
        roster_size = 0
        weekend = "unknown"
        coverage_notes = ()
    return RaceSourceAudit(
        manifest_path=str(manifest_path),
        weekend=weekend,
        manifest_sha256=sha256(raw).hexdigest(),
        source_snapshot_sha256=snapshot_hash,
        roster_size=roster_size,
        source_state="verified" if verified else "incomplete",
        coverage_notes=coverage_notes,
        target_issues=("race_checkpoint_targets_not_derived",),
    )


def _incomplete_race_manifest(manifest_path: Path, raw: bytes) -> RaceSourceAudit:
    return RaceSourceAudit(
        manifest_path=str(manifest_path),
        weekend="unknown",
        manifest_sha256=sha256(raw).hexdigest(),
        source_snapshot_sha256="0" * 64,
        roster_size=0,
        source_state="incomplete",
        coverage_notes=(),
        target_issues=("race_checkpoint_targets_not_derived",),
    )


def _snapshot_hash(snapshot: dict[str, str]) -> str:
    return sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def _snapshot_files_match(manifest_path: Path, snapshot: dict[str, str]) -> bool:
    snapshot_dir = manifest_path.parent / "source_snapshot"
    try:
        return all(sha256((snapshot_dir / name).read_bytes()).hexdigest() == value for name, value in snapshot.items())
    except OSError:
        return False


def _exports_match(manifest_path: Path, exports: dict[str, dict[str, str]]) -> bool:
    expected = {"car", "laps", "position", "tyres", "weather", "session_status", "track_status", "race_control_messages"}
    if set(exports) != expected:
        return False
    export_dir = manifest_path.parent.resolve()
    try:
        paths = [Path(value["path"]).resolve() for value in exports.values()]
        if any(path.parent != export_dir for path in paths):
            return False
        return all(sha256(path.read_bytes()).hexdigest() == value["sha256"] for path, value in zip(paths, exports.values()))
    except (KeyError, OSError, TypeError):
        return False


def _coverage_notes(manifest: dict[str, object], manifest_path: Path) -> tuple[str, ...]:
    try:
        log = manifest["loader_log"]
        log_path = Path(log["path"]).resolve()
        if log_path.parent != manifest_path.parent.resolve() or sha256(log_path.read_bytes()).hexdigest() != log["sha256"]:
            return ("loader_log_unverified",)
        lines = log_path.read_text().splitlines()
    except (KeyError, OSError, TypeError):
        return ("loader_log_unverified",)
    if any("Car data is incomplete" in line for line in lines):
        return ("loader_reported_incomplete_car_data",)
    return ()


def _read_cache(source: Path) -> object:
    with source.open("rb") as handle:
        return pickle.load(handle)


def _hash_files(cache_root: Path, files: tuple[Path, ...]) -> str:
    digest = sha256()
    for path in files:
        digest.update(str(path.relative_to(cache_root)).encode())
        digest.update(b"\0")
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _write_immutable_json(destination: Path, value: dict[str, object]) -> None:
    serialized = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if destination.exists():
        if destination.read_text() != serialized:
            raise FileExistsError(f"immutable weekend audit differs: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(serialized)
