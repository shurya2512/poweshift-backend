"""Seal one isolated FastF1 race capture as tables and provenance."""

from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import shutil

import fastf1

from poweshift_backend.data.coverage import entry_exclusions, parser_quality
from poweshift_backend.data.export import write_manifest, write_table
from poweshift_backend.data.quality import audit_stream
from poweshift_backend.sources.fastf1_loader import StreamResult
from poweshift_backend.sources.weekend_loader import load_race


def acquire_race(
    year: int,
    event_name: str,
    expected_date: date,
    cache_dir: Path,
    output_dir: Path,
) -> Path:
    """Export one checked race and its immutable parser-cache snapshot."""
    identity, roster, streams = load_race(
        year=year,
        event_name=event_name,
        expected_date=expected_date,
        cache_dir=cache_dir,
        log_path=output_dir / "fastf1_cached_export.log",
    )
    source_snapshot = _snapshot_race(cache_dir, identity.date, output_dir / "source_snapshot")
    source_snapshot_hash = sha256(json.dumps(source_snapshot, sort_keys=True).encode()).hexdigest()
    exports, coverage = _export_streams(streams, roster, output_dir, source_snapshot_hash)
    laps = streams["laps"].records
    bundle = {
        "identity": {
            "year": identity.year,
            "event_name": identity.event_name,
            "date": identity.date.isoformat(),
            "session_kind": identity.session_kind,
        },
        "parser_version": fastf1.__version__,
        "source_snapshot": source_snapshot,
        "source_snapshot_sha256": source_snapshot_hash,
        "loader_log": _file_record(output_dir / "fastf1_cached_export.log"),
        "roster": roster,
        "exports": exports,
        "coverage": coverage,
        "exclusions": entry_exclusions(
            laps,
            roster,
            streams["car"].records,
            streams["position"].records,
            streams["tyres"].records,
        ),
        "source_quality": parser_quality(laps) if laps is not None else {},
    }
    bundle_path = output_dir / "acquisition_bundle.json"
    write_manifest(bundle, bundle_path)
    return bundle_path


def _export_streams(
    streams: dict[str, StreamResult], roster: list[str], output_dir: Path, source_snapshot_hash: str
) -> tuple[dict[str, dict], dict[str, dict]]:
    exports: dict[str, dict] = {}
    coverage: dict[str, dict] = {}
    for name, result in streams.items():
        records = result.records
        expected_roster = set(roster) if name in {"car", "position", "laps", "tyres"} else set()
        if result.status.value not in {"present", "verified_empty"}:
            coverage[name] = audit_stream(
                None,
                expected_roster=expected_roster,
                error=result.reason if result.status.value == "failed" else None,
                reason=result.reason if result.status.value == "missing" else None,
            ).__dict__
            continue
        records = records.copy()
        records.insert(0, "source_row", records["NativeSourceRow"])
        table_path = output_dir / f"{name}.parquet"
        exports[name] = {
            "path": str(table_path),
            "sha256": write_table(records, table_path),
            "provenance": {
                "kind": "parser_derived",
                "stream": name,
                "source_snapshot_sha256": source_snapshot_hash,
                "row_key": ["DriverNumber", "source_row"] if name in {"car", "position"} else ["source_row"],
            },
        }
        coverage[name] = audit_stream(records, expected_roster).__dict__
    return exports, coverage


def _snapshot_race(cache_dir: Path, race_date: date, destination: Path) -> dict[str, str]:
    directories = list(cache_dir.glob(f"**/{race_date}_Race"))
    if len(directories) != 1:
        raise ValueError("expected exactly one parser-cache race directory")
    sources = sorted(directories[0].glob("*.ff1pkl"))
    if not sources:
        raise ValueError("parser-cache race directory is empty")
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


def _file_record(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
