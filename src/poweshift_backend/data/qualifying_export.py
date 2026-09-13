"""Seal approved qualifying telemetry with source hashes."""

from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import shutil

import fastf1
import pandas as pd

from poweshift_backend.data.export import write_manifest, write_table
from poweshift_backend.sources.fastf1_loader import _driver_frames
from poweshift_backend.targets.weekend import _session_snapshot_hash, _weekend_hash


_SMOKE_SESSIONS = {
    "2026-03-08_Australian_Grand_Prix": ("Australian Grand Prix", "2026-03-07_Qualifying"),
    "2026-03-15_Chinese_Grand_Prix": ("Chinese Grand Prix", "2026-03-14_Qualifying"),
    "2026-03-29_Japanese_Grand_Prix": ("Japanese Grand Prix", "2026-03-28_Qualifying"),
    "2026-05-03_Miami_Grand_Prix": ("Miami Grand Prix", "2026-05-02_Qualifying"),
    "2026-05-24_Canadian_Grand_Prix": ("Canadian Grand Prix", "2026-05-23_Qualifying"),
    "2026-06-07_Monaco_Grand_Prix": ("Monaco Grand Prix", "2026-06-06_Qualifying"),
    "2026-06-14_Barcelona_Grand_Prix": ("Barcelona Grand Prix", "2026-06-13_Qualifying"),
    "2026-06-28_Austrian_Grand_Prix": ("Austrian Grand Prix", "2026-06-27_Qualifying"),
    "2026-07-05_British_Grand_Prix": ("British Grand Prix", "2026-07-04_Qualifying"),
}


def qualifying_session_name(session_names: tuple[str, ...] | list[str]) -> str | None:
    """Return standard qualifying without matching sprint qualifying."""
    return next((name for name in session_names if name[11:] == "Qualifying"), None)


def export_qualifying(
    source_session_dir: Path,
    *,
    audit_path: Path,
    isolated_cache_root: Path,
    output_dir: Path,
) -> Path:
    """Export one approved qualifying session from a copied cache."""
    audit = json.loads(audit_path.read_text())
    cache_root, record, event_name, session_date = _approved_source(audit, source_session_dir)
    weekend = source_session_dir.parent.name
    source_hash = record["source_hash"]
    if _weekend_hash(cache_root, weekend) != source_hash:
        raise ValueError("source hash does not match the audited weekend cache")
    source_snapshot = _session_snapshot_hash(source_session_dir)
    copied_dir = _copy_snapshot(source_session_dir, isolated_cache_root / "2026" / weekend / source_session_dir.name)
    session = _load_session(copied_dir, event_name, session_date, date.fromisoformat(record["event_date"]))
    if _weekend_hash(cache_root, weekend) != source_hash:
        raise ValueError("source cache changed during qualifying export")
    if _session_snapshot_hash(source_session_dir) != source_snapshot:
        raise ValueError("source cache changed during qualifying export")
    if _session_snapshot_hash(copied_dir) != source_snapshot:
        raise ValueError("qualifying load changed the copied cache")
    tables = _tables(session)
    exports = _write_tables(tables, output_dir, source_snapshot)
    payload = {
        "kind": "source_bound_qualifying_export_v1",
        "identity": {
            "year": 2026,
            "event_name": event_name,
            "event_date": record["event_date"],
            "session_date": session_date.isoformat(),
            "session_kind": "Qualifying",
        },
        "parser_version": fastf1.__version__,
        "source_audit": {"path": str(audit_path), "sha256": _file_hash(audit_path)},
        "source_session": {
            "weekend": weekend,
            "session": source_session_dir.name,
            "weekend_source_sha256": source_hash,
            "session_snapshot_sha256": source_snapshot,
            "copied_session_snapshot_sha256": _session_snapshot_hash(copied_dir),
        },
        "exports": exports,
    }
    manifest_path = output_dir / "qualifying_export.json"
    write_manifest(payload, manifest_path)
    return manifest_path


def _approved_source(audit: dict, source_session_dir: Path) -> tuple[Path, dict, str, date]:
    weekend = source_session_dir.parent.name
    requested = _SMOKE_SESSIONS.get(weekend)
    if requested is None:
        raise ValueError("session is not approved for the qualifying smoke export")
    event_name, session_name = requested
    if source_session_dir.name != session_name:
        raise ValueError("source session date does not match the approved qualifying session")
    cache_root = Path(audit["cache_root"])
    if source_session_dir.resolve() != (cache_root / weekend / session_name).resolve():
        raise ValueError("source session is outside the audited cache root")
    record = next((item for item in audit["sessions"] if item["weekend"] == weekend), None)
    if record is None or record["partition"] != "training":
        raise ValueError("source session is not in the training partition")
    if record["source_state"] != "verified" or not isinstance(record["source_hash"], str):
        raise ValueError("source session is not verified by the audit")
    if session_name not in record["session_names"]:
        raise ValueError("source session is absent from the audit record")
    return cache_root, record, event_name, date.fromisoformat(session_name[:10])


def _copy_snapshot(source_dir: Path, destination: Path) -> Path:
    source_snapshot = _session_snapshot_hash(source_dir)
    if destination.exists():
        if _session_snapshot_hash(destination) != source_snapshot:
            raise FileExistsError(f"immutable copied cache differs: {destination}")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, destination)
    if _session_snapshot_hash(destination) != source_snapshot:
        raise ValueError("copied qualifying cache differs from the audited source")
    return destination


def _session(copied_dir: Path, event_name: str) -> object:
    fastf1.Cache.enable_cache(str(copied_dir.parents[2]))
    return fastf1.get_session(2026, event_name, "Q")


def _load_session(copied_dir: Path, event_name: str, session_date: date, event_date: date) -> object:
    session = _session(copied_dir, event_name)
    if (
        session.event["EventName"] != event_name
        or session.name != "Qualifying"
        or pd.Timestamp(session.date).date() != session_date
        or pd.Timestamp(session.event["EventDate"]).date() != event_date
    ):
        raise ValueError("FastF1 returned an unexpected qualifying session")
    session.load(laps=True, telemetry=True, weather=True, messages=True)
    return session


def _tables(session: object) -> dict[str, pd.DataFrame]:
    laps = pd.DataFrame(session.laps).assign(NativeSourceRow=session.laps.index)
    labels = {index: name for name, segment in zip(("Q1", "Q2", "Q3"), session.laps.split_qualifying_sessions()) if segment is not None for index in segment.index}
    laps = laps.assign(qualifying_segment=laps.index.map(labels), source_row=laps["NativeSourceRow"])
    car = _driver_frames(session.car_data)
    position = _driver_frames(session.pos_data)
    for name, records, fields in (
        ("laps", laps, {"DriverNumber", "LapNumber", "LapStartTime", "Time", "IsAccurate", "Deleted", "qualifying_segment", "source_row"}),
        ("car", car, {"DriverNumber", "SessionTime", "Throttle", "Brake", "Speed", "NativeSourceRow"}),
        ("position", position, {"DriverNumber", "SessionTime", "X", "Y", "NativeSourceRow"}),
    ):
        if records.empty or not fields <= set(records):
            raise ValueError(f"qualifying {name} records lack required fields")
    return {"laps": laps, "car": car.assign(source_row=car["NativeSourceRow"]), "position": position.assign(source_row=position["NativeSourceRow"])}


def _write_tables(tables: dict[str, pd.DataFrame], output_dir: Path, source_snapshot: str) -> dict[str, dict]:
    exports: dict[str, dict] = {}
    for name, records in tables.items():
        path = output_dir / f"{name}.parquet"
        exports[name] = {
            "path": str(path),
            "sha256": write_table(records, path),
            "provenance": {
                "kind": "parser_derived",
                "source_session_snapshot_sha256": source_snapshot,
                "row_key": ["DriverNumber", "source_row"] if name in {"car", "position"} else ["source_row"],
            },
        }
    return exports


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
