"""Acquire, export and describe all permitted Bahrain test days."""

from hashlib import sha256
from pathlib import Path

from poweshift_backend.contracts.acquisition import SessionRequest
from poweshift_backend.data.coverage import entry_exclusions, parser_quality
from poweshift_backend.data.export import write_manifest, write_table
from poweshift_backend.data.quality import audit_stream
from poweshift_backend.sources.cache_audit import cache_inventory
from poweshift_backend.sources.fastf1_loader import load_bahrain_test_day


STREAMS = (
    "car",
    "position",
    "laps",
    "tyres",
    "weather",
    "session_status",
    "track_status",
    "race_control_messages",
)


def acquire_all(cache_dir: Path, output_dir: Path) -> Path:
    """Acquire all six days and write one immutable acquisition bundle."""
    sessions = []
    for test_number in (1, 2):
        for day_number in (1, 2, 3):
            request = SessionRequest(year=2026, test_number=test_number, day_number=day_number)
            sessions.append(_acquire_day(request, cache_dir, output_dir))
    bundle = {
        "cache_hashes": cache_inventory(cache_dir),
        "coverage_review": "pending_human_approval",
        "downstream_ready": False,
        "reason": "critical gaps block later work until coverage review",
        "sessions": sessions,
        "split": {"training": "Test 1", "selection": "2026-02-18", "final_evaluation": ["2026-02-19", "2026-02-20"], "active": False},
    }
    bundle_path = output_dir / "acquisition_bundle.json"
    write_manifest(bundle, bundle_path)
    return bundle_path


def _acquire_day(request: SessionRequest, cache_dir: Path, output_dir: Path) -> dict:
    day_dir = output_dir / f"test_{request.test_number}_day_{request.day_number}"
    log_path = day_dir / "fastf1.log"
    identity, streams = load_bahrain_test_day(request, cache_dir, log_path)
    roster = sorted({str(driver) for driver in streams["car"]["DriverNumber"].dropna()})
    exports = {}
    coverage = {}
    for name in STREAMS:
        records = streams[name].copy()
        records.insert(0, "source_row", range(len(records)))
        exports[name] = {"path": str(day_dir / f"{name}.parquet"), "sha256": write_table(records, day_dir / f"{name}.parquet")}
        report = audit_stream(records, set(roster)) if "SessionTime" in records else None
        coverage[name] = report.__dict__ if report else {"status": "present" if len(records) else "verified_empty"}
    laps = streams["laps"]
    return {
        "identity": identity.model_dump(mode="json"),
        "exports": exports,
        "coverage": coverage,
        "roster": roster,
        "exclusions": entry_exclusions(laps, roster),
        "source_quality": parser_quality(laps),
        "loader_log": {"path": str(log_path), "sha256": sha256(log_path.read_bytes()).hexdigest()},
    }
