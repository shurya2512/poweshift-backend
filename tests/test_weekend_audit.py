from pathlib import Path
from datetime import datetime
from hashlib import sha256
import json
import pickle

import pytest

from poweshift_backend.sources.cache_audit import audit_weekend_cache


_STREAMS = (
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
)


def _session(root: Path, weekend: str, session: str) -> None:
    directory = root / weekend / session
    directory.mkdir(parents=True)
    for stream in _STREAMS:
        if stream == "session_info.ff1pkl":
            continue
        (directory / stream).write_bytes(stream.encode())
    with (directory / "session_info.ff1pkl").open("wb") as handle:
        pickle.dump(
            {
                "version": 15,
                "data": {
                    "Meeting": {"Name": weekend[11:].replace("_", " ")},
                    "Name": session[11:].replace("_", " "),
                    "Path": f"2026/{weekend}/{session}/",
                    "StartDate": datetime.fromisoformat(session[:10]),
                },
            },
            handle,
        )


_WEEKENDS = (
    ("2026-03-08_Australian_Grand_Prix", "2026-03-07_Qualifying"),
    ("2026-03-15_Chinese_Grand_Prix", "2026-03-14_Qualifying"),
    ("2026-03-29_Japanese_Grand_Prix", "2026-03-28_Qualifying"),
    ("2026-05-03_Miami_Grand_Prix", "2026-05-02_Qualifying"),
    ("2026-05-24_Canadian_Grand_Prix", "2026-05-23_Qualifying"),
    ("2026-06-07_Monaco_Grand_Prix", "2026-06-06_Qualifying"),
    ("2026-06-14_Barcelona_Grand_Prix", "2026-06-13_Qualifying"),
    ("2026-06-28_Austrian_Grand_Prix", "2026-06-27_Qualifying"),
    ("2026-07-05_British_Grand_Prix", "2026-07-04_Qualifying"),
    ("2026-07-19_Belgian_Grand_Prix", "2026-07-18_Qualifying"),
    ("2026-07-26_Hungarian_Grand_Prix", "2026-07-25_Qualifying"),
    ("2026-08-23_Dutch_Grand_Prix", "2026-08-22_Qualifying"),
    ("2026-09-06_Italian_Grand_Prix", "2026-09-05_Qualifying"),
)


def test_audit_hashes_training_and_selection_but_never_final_or_reserved_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "cache"
    for weekend, session in _WEEKENDS:
        _session(root, weekend, session)
    protected = {root / weekend for weekend, _ in _WEEKENDS[-3:]}
    original_read_bytes = Path.read_bytes
    original_open = Path.open

    def read_bytes(path: Path) -> bytes:
        if any(parent in path.parents for parent in protected):
            raise AssertionError("final or reserved content was opened")
        return original_read_bytes(path)

    def open_path(path: Path, *args: object, **kwargs: object):
        if any(parent in path.parents for parent in protected):
            raise AssertionError("final or reserved content was opened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "open", open_path)

    audit = audit_weekend_cache(root, tmp_path / "audit.json")

    assert audit.status == "blocked"
    assert all(item.content_access == "hashed" for item in audit.sessions[:10])
    assert all(item.content_access == "inventory_only" for item in audit.sessions[10:])
    assert audit.sessions[11].partition == "final_evaluation"
    assert audit.blockers == ("race_source_missing", "target_masks_missing")
    assert all(item.source_state == "verified" for item in audit.sessions[:10])
    assert all(item.target_state == "refused" for item in audit.sessions[:10])
    assert (tmp_path / "audit.json").exists()


def test_audit_refuses_to_overwrite_a_changed_immutable_artifact(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    for weekend, session in _WEEKENDS:
        _session(root, weekend, session)
    artifact = tmp_path / "audit.json"
    audit_weekend_cache(root, artifact)
    (root / "2026-03-08_Australian_Grand_Prix" / "2026-03-07_Qualifying" / "car_data.ff1pkl").write_bytes(b"changed")

    with pytest.raises(FileExistsError, match="immutable weekend audit differs"):
        audit_weekend_cache(root, artifact)


def test_audit_refuses_a_session_date_after_its_weekend(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    for weekend, session in _WEEKENDS:
        _session(root, weekend, session)
    valid = root / "2026-03-08_Australian_Grand_Prix" / "2026-03-07_Qualifying"
    valid.rename(root / "2026-03-08_Australian_Grand_Prix" / "2026-03-09_Qualifying")

    audit = audit_weekend_cache(root, tmp_path / "audit.json")

    assert "session_date_after_weekend" in audit.sessions[0].source_issues
    assert "session_path_mismatch" in audit.sessions[0].source_issues


def test_audit_binds_a_verified_race_manifest_without_admitting_targets(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    for weekend, session in _WEEKENDS:
        _session(root, weekend, session)
    export_dir = tmp_path / "export_v2"
    export_dir.mkdir()
    snapshot_dir = export_dir / "source_snapshot"
    snapshot_dir.mkdir()
    exports = {}
    for name in ("car", "laps", "position", "tyres", "weather", "session_status", "track_status", "race_control_messages"):
        path = export_dir / f"{name}.parquet"
        path.write_bytes(name.encode())
        exports[name] = {"path": str(path), "sha256": sha256(name.encode()).hexdigest()}
    snapshot = {name: "a" * 64 for name in _STREAMS}
    for name in snapshot:
        value = name.encode()
        (snapshot_dir / name).write_bytes(value)
        snapshot[name] = sha256(value).hexdigest()
    manifest = export_dir / "acquisition_bundle.json"
    manifest.write_text(json.dumps({
        "identity": {"date": "2026-03-08", "event_name": "Australian Grand Prix", "session_kind": "race", "year": 2026},
        "source_snapshot": snapshot,
        "source_snapshot_sha256": sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
        "roster": ["1", "2"],
        "cache_hashes": {f"2026/event/race/{name}": value for name, value in snapshot.items()},
        "coverage": {name: {"status": "present"} for name in exports},
        "exports": exports,
    }))

    audit = audit_weekend_cache(root, tmp_path / "audit.json", (manifest,))

    assert audit.race_sources[0].source_state == "verified"
    assert audit.race_sources[0].target_state == "refused"
    assert audit.source_status == "verified"
    assert audit.blockers == ("race_source_missing", "target_masks_missing")

    (export_dir / "laps.parquet").write_bytes(b"changed")
    tampered = audit_weekend_cache(root, tmp_path / "tampered.json", (manifest,))

    assert tampered.race_sources[0].source_state == "incomplete"


def test_audit_rejects_protected_identity_before_opening_referenced_files(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    for weekend, session in _WEEKENDS:
        _session(root, weekend, session)
    protected = tmp_path / "Hungarian_Grand_Prix.parquet"
    protected.write_bytes(b"protected")
    manifest = tmp_path / "export_v2" / "acquisition_bundle.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({
        "identity": {"date": "2026-07-26", "event_name": "Hungarian Grand Prix", "session_kind": "race", "year": 2026},
        "source_snapshot": {},
        "source_snapshot_sha256": "a" * 64,
        "roster": [],
        "exports": {"laps": {"path": str(protected), "sha256": "a" * 64}},
        "coverage": {},
    }))

    audit = audit_weekend_cache(root, tmp_path / "audit.json", (manifest,))

    assert audit.race_sources[0].source_state == "incomplete"
