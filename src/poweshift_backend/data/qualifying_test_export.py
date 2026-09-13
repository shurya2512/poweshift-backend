"""Acquire and seal one protected qualifying-only test source."""

from datetime import date
from hashlib import sha256
from pathlib import Path

import fastf1
import pandas as pd

from poweshift_backend.data.export import write_manifest
from poweshift_backend.data.qualifying_export import _tables, _write_tables
from poweshift_backend.targets.weekend import _session_snapshot_hash


def acquire_qualifying_test(
    *,
    year: int,
    event_name: str,
    event_date: date,
    session_date: date,
    cache_root: Path,
    output_dir: Path,
) -> Path:
    """Acquire qualifying telemetry and mark it final-evaluation only."""
    cache_root.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_root))
    session = fastf1.get_session(year, event_name, "Q")
    if (
        session.event["EventName"] != event_name
        or session.name != "Qualifying"
        or pd.Timestamp(session.date).date() != session_date
        or pd.Timestamp(session.event["EventDate"]).date() != event_date
    ):
        raise ValueError("FastF1 returned an unexpected qualifying test session")
    session.load(laps=True, telemetry=True, weather=True, messages=True)
    weekend = f"{event_date.isoformat()}_{event_name.replace(' ', '_')}"
    source_dir = cache_root / str(year) / weekend / f"{session_date.isoformat()}_Qualifying"
    if not source_dir.is_dir():
        raise FileNotFoundError("FastF1 did not create the expected qualifying cache")
    source_snapshot = _session_snapshot_hash(source_dir)
    exports = _write_tables(_tables(session), output_dir, source_snapshot)
    payload = {
        "kind": "source_bound_qualifying_test_export_v1",
        "identity": {
            "year": year,
            "event_name": event_name,
            "event_date": event_date.isoformat(),
            "session_date": session_date.isoformat(),
            "session_kind": "Qualifying",
            "session_id": f"{weekend}:{session_date.isoformat()}_Qualifying",
            "partition": "final_evaluation",
            "circuit": "Madring",
        },
        "parser_version": fastf1.__version__,
        "source_session": {
            "path": str(source_dir),
            "session_snapshot_sha256": source_snapshot,
        },
        "exports": exports,
        "race_source_state": "not_available_at_acquisition",
        "optimizer_eligible": False,
    }
    manifest_path = output_dir / "qualifying_test_export.json"
    write_manifest(payload, manifest_path)
    return manifest_path


def file_sha256(path: Path) -> str:
    """Return one artifact hash for registry generation."""
    return sha256(path.read_bytes()).hexdigest()
