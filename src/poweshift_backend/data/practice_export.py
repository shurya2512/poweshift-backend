"""Seal audited free-practice controls for energy-policy training."""

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil

import fastf1
import pandas as pd

from poweshift_backend.data.export import write_manifest, write_table
from poweshift_backend.sources.fastf1_loader import _driver_frames
from poweshift_backend.targets.weekend import _session_snapshot_hash, _weekend_hash


@dataclass(frozen=True)
class ApprovedPracticeSource:
    """Resolved identity for one audited free-practice cache."""

    cache_root: Path
    record: dict
    event_name: str
    session_selector: str
    session_name: str
    session_date: date


def approved_practice_source(audit: dict, source_session_dir: Path) -> ApprovedPracticeSource:
    """Resolve a verified training FP1, FP2 or FP3 source."""
    weekend = source_session_dir.parent.name
    cache_root = Path(audit["cache_root"])
    record = next((item for item in audit["sessions"] if item["weekend"] == weekend), None)
    if record is None or record.get("partition") != "training":
        raise ValueError("practice source is not in the training partition")
    if record.get("source_state") != "verified" or not isinstance(record.get("source_hash"), str):
        raise ValueError("practice source is not verified by the audit")
    if source_session_dir.resolve() != (cache_root / weekend / source_session_dir.name).resolve():
        raise ValueError("practice source is outside the audited cache root")
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})_Practice_([123])", source_session_dir.name)
    if match is None:
        raise ValueError("source session is not an audited free-practice session")
    if source_session_dir.name not in record.get("session_names", ()):
        raise ValueError("practice source is absent from the audit record")
    event_name = weekend[11:].replace("_", " ")
    ordinal = match.group(2)
    return ApprovedPracticeSource(
        cache_root,
        record,
        event_name,
        f"FP{ordinal}",
        f"Practice {ordinal}",
        date.fromisoformat(match.group(1)),
    )


def export_practice(
    source_session_dir: Path,
    *,
    audit_path: Path,
    isolated_cache_root: Path,
    output_dir: Path,
) -> Path:
    """Export one audited free-practice session from a copied cache."""
    audit = json.loads(audit_path.read_text())
    approved = approved_practice_source(audit, source_session_dir)
    weekend = source_session_dir.parent.name
    source_hash = approved.record["source_hash"]
    if _weekend_hash(approved.cache_root, weekend) != source_hash:
        raise ValueError("source hash does not match the audited weekend cache")
    source_snapshot = _session_snapshot_hash(source_session_dir)
    copied_dir = _copy_snapshot(
        source_session_dir,
        isolated_cache_root / "2026" / weekend / source_session_dir.name,
    )
    session = _load_session(copied_dir, approved)
    if _weekend_hash(approved.cache_root, weekend) != source_hash:
        raise ValueError("source cache changed during practice export")
    if _session_snapshot_hash(source_session_dir) != source_snapshot:
        raise ValueError("source cache changed during practice export")
    if _session_snapshot_hash(copied_dir) != source_snapshot:
        raise ValueError("practice load changed the copied cache")
    tables = _tables(session)
    exports = _write_tables(tables, output_dir, source_snapshot)
    payload = {
        "kind": "source_bound_practice_export_v1",
        "identity": {
            "year": 2026,
            "event_name": approved.event_name,
            "event_date": approved.record["event_date"],
            "session_date": approved.session_date.isoformat(),
            "session_kind": approved.session_name,
            "session_id": f"{weekend}:{source_session_dir.name}",
            "partition": "training",
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
    manifest_path = output_dir / "practice_export.json"
    write_manifest(payload, manifest_path)
    return manifest_path


def _copy_snapshot(source_dir: Path, destination: Path) -> Path:
    source_snapshot = _session_snapshot_hash(source_dir)
    if destination.exists():
        if _session_snapshot_hash(destination) != source_snapshot:
            raise FileExistsError(f"immutable copied cache differs: {destination}")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, destination)
    if _session_snapshot_hash(destination) != source_snapshot:
        raise ValueError("copied practice cache differs from the audited source")
    return destination


def _load_session(copied_dir: Path, approved: ApprovedPracticeSource) -> object:
    fastf1.Cache.enable_cache(str(copied_dir.parents[2]))
    session = fastf1.get_session(2026, approved.event_name, approved.session_selector)
    if (
        session.event["EventName"] != approved.event_name
        or session.name != approved.session_name
        or pd.Timestamp(session.date).date() != approved.session_date
        or pd.Timestamp(session.event["EventDate"]).date() != date.fromisoformat(approved.record["event_date"])
    ):
        raise ValueError("FastF1 returned an unexpected practice session")
    session.load(laps=True, telemetry=True, weather=True, messages=True)
    return session


def _tables(session: object) -> dict[str, pd.DataFrame]:
    laps = pd.DataFrame(session.laps).assign(
        NativeSourceRow=session.laps.index,
        source_row=session.laps.index,
    )
    car = _driver_frames(session.car_data)
    car = car.assign(source_row=car["NativeSourceRow"]) if not car.empty else car
    required = {
        "laps": {"DriverNumber", "LapNumber", "LapStartTime", "Time", "IsAccurate", "Deleted", "source_row"},
        "car": {"DriverNumber", "SessionTime", "Throttle", "Brake", "Speed", "source_row"},
    }
    for name, records in (("laps", laps), ("car", car)):
        if records.empty or not required[name] <= set(records):
            raise ValueError(f"practice {name} records lack required fields")
    return {"laps": laps, "car": car}


def _write_tables(
    tables: dict[str, pd.DataFrame], output_dir: Path, source_snapshot: str,
) -> dict[str, dict]:
    exports: dict[str, dict] = {}
    for name, records in tables.items():
        path = output_dir / f"{name}.parquet"
        exports[name] = {
            "path": str(path),
            "sha256": write_table(records, path),
            "provenance": {
                "kind": "parser_derived_energy_controls",
                "source_session_snapshot_sha256": source_snapshot,
                "row_key": ["DriverNumber", "source_row"] if name == "car" else ["source_row"],
            },
        }
    return exports


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
