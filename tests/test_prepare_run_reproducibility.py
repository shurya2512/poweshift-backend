"""Reproducibility: repeating an approved preparation matches, and Phase 1 exports stay untouched."""

import json
from datetime import date
from hashlib import sha256
from pathlib import Path

import pandas as pd

from poweshift_backend.data.prepare_run import run_preparation


def _write_bundle_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """A tiny, hand-built stand-in for a Phase 1 acquisition bundle: one training day, two entries."""
    day_dir = tmp_path / "phase1" / "test_1_day_1"
    day_dir.mkdir(parents=True)

    car = pd.DataFrame(
        {
            "source_row": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
            "Date": pd.Timestamp("2026-02-11 06:00:00") + pd.to_timedelta([0.0, 0.2, 0.4, 0.6, 0.8, 0.0, 0.2, 0.4, 0.6, 0.8], unit="s"),
            "Time": pd.to_timedelta([0.0, 0.2, 0.4, 0.6, 0.8, 0.0, 0.2, 0.4, 0.6, 0.8], unit="s"),
            "DriverNumber": ["1", "1", "1", "1", "1", "2", "2", "2", "2", "2"],
            "Speed": [100.0, 110.0, 120.0, 115.0, 105.0, 90.0, 95.0, 100.0, 98.0, 92.0],
            "RPM": [10000.0] * 10,
            "Throttle": [80.0] * 10,
            "Brake": [0.0] * 10,
            "nGear": [5.0] * 10,
            "DRS": [0.0] * 10,
        }
    )
    car_path = day_dir / "car.parquet"
    car.to_parquet(car_path, index=False)

    laps = pd.DataFrame(
        {
            "source_row": [100, 101],
            "DriverNumber": ["1", "2"],
            "LapNumber": [1.0, 1.0],
            "Stint": [1.0, 1.0],
            "LapStartTime": pd.to_timedelta([0.0, 0.0], unit="s"),
            "Time": pd.to_timedelta([0.8, 1.0], unit="s"),
            "LapTime": pd.to_timedelta([0.8, 1.0], unit="s"),
            "PitInTime": pd.to_timedelta([None, 0.5], unit="s"),
            "PitOutTime": pd.to_timedelta([None, None], unit="s"),
            "Compound": ["MEDIUM", "SOFT"],
            "TyreLife": [1.0, 1.0],
            "FreshTyre": [True, True],
            "IsAccurate": [True, True],
            "Deleted": [False, False],
            "DeletedReason": ["", ""],
        }
    )
    laps_path = day_dir / "laps.parquet"
    laps.to_parquet(laps_path, index=False)

    track_status = pd.DataFrame({"source_row": [0], "Time": pd.to_timedelta([0.0], unit="s"), "Status": ["1"], "Message": ["AllClear"]})
    track_status_path = day_dir / "track_status.parquet"
    track_status.to_parquet(track_status_path, index=False)

    session_status = pd.DataFrame({"source_row": [0], "Time": pd.to_timedelta([0.0], unit="s"), "Status": ["Started"]})
    session_status_path = day_dir / "session_status.parquet"
    session_status.to_parquet(session_status_path, index=False)

    race_control_messages = pd.DataFrame(
        {
            "source_row": [0],
            "Time": [pd.Timestamp("2026-02-11 06:00:05")],
            "Category": ["Other"],
            "Message": ["installation lap complete"],
            "Flag": [None],
        }
    )
    race_control_messages_path = day_dir / "race_control_messages.parquet"
    race_control_messages.to_parquet(race_control_messages_path, index=False)

    position = pd.DataFrame(
        {
            "source_row": [200, 201, 202, 203, 204],
            "DriverNumber": ["1", "1", "1", "1", "1"],
            "Time": pd.to_timedelta([0.0, 0.2, 0.4, 0.6, 0.8], unit="s"),
            "X": [0.0, 10.0, 20.0, 25.0, 20.0],
            "Y": [0.0, 0.0, 5.0, 15.0, 25.0],
        }
    )
    position_path = day_dir / "position.parquet"
    position.to_parquet(position_path, index=False)

    bundle = {
        "sessions": [
            {
                "identity": {
                    "year": 2026,
                    "test_number": 1,
                    "day_number": 1,
                    "date": "2026-02-11",
                    "venue": "Bahrain",
                    "session_kind": "preseason_test",
                },
                "roster": ["1", "2"],
                "exclusions": {},
                "exports": {
                    "car": {"path": str(car_path)},
                    "laps": {"path": str(laps_path)},
                    "track_status": {"path": str(track_status_path)},
                    "session_status": {"path": str(session_status_path)},
                    "race_control_messages": {"path": str(race_control_messages_path)},
                    "position": {"path": str(position_path)},
                },
            }
        ]
    }
    bundle_path = tmp_path / "phase1" / "acquisition_bundle.json"
    bundle_path.write_text(json.dumps(bundle, sort_keys=True, indent=2))
    return bundle_path, day_dir


def _hash_tree(directory: Path) -> dict[str, str]:
    return {str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest() for path in sorted(directory.rglob("*")) if path.is_file()}


def test_repeating_an_approved_preparation_produces_the_same_manifests(tmp_path: Path) -> None:
    bundle_path, _ = _write_bundle_fixture(tmp_path)
    evidence_dir = tmp_path / "evidence"

    first = run_preparation(bundle_path, evidence_dir, reviewer="coverage-reviewer", recorded_on=date(2026, 9, 12))
    first_hashes = _hash_tree(evidence_dir)
    second = run_preparation(bundle_path, evidence_dir, reviewer="coverage-reviewer", recorded_on=date(2026, 9, 12))
    second_hashes = _hash_tree(evidence_dir)

    assert first == second
    assert first_hashes == second_hashes
    manifest = json.loads(first.read_text())
    assert manifest["counts"]["stint_packages"] > 0
    assert manifest["counts"]["target_records"] == 2
    assert manifest["counts"]["pit_records"] == 1


def test_repeating_a_preparation_leaves_the_phase_1_exports_unchanged(tmp_path: Path) -> None:
    bundle_path, day_dir = _write_bundle_fixture(tmp_path)
    evidence_dir = tmp_path / "evidence"
    phase1_hashes_before = _hash_tree(day_dir)

    run_preparation(bundle_path, evidence_dir, reviewer="coverage-reviewer", recorded_on=date(2026, 9, 12))
    run_preparation(bundle_path, evidence_dir, reviewer="coverage-reviewer", recorded_on=date(2026, 9, 12))

    assert _hash_tree(day_dir) == phase1_hashes_before


def test_evidence_manifest_states_its_own_limits_in_plain_language(tmp_path: Path) -> None:
    bundle_path, _ = _write_bundle_fixture(tmp_path)
    evidence_dir = tmp_path / "evidence"

    manifest_path = run_preparation(bundle_path, evidence_dir, reviewer="coverage-reviewer", recorded_on=date(2026, 9, 12))
    manifest = json.loads(manifest_path.read_text())

    statement = manifest["evidence_limits"].lower()
    for phrase in ("predict", "energy", "ranking", "race readiness", "live timing", "qualifying"):
        assert phrase in statement
