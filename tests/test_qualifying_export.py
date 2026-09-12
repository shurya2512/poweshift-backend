from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from poweshift_backend.data import qualifying_export


class _Laps(pd.DataFrame):
    @property
    def _constructor(self):
        return _Laps

    def split_qualifying_sessions(self):
        return (self.iloc[:1], self.iloc[1:], self.iloc[:0])


class _Session:
    def __init__(self) -> None:
        self.event = {"EventName": "Australian Grand Prix", "EventDate": pd.Timestamp("2026-03-08")}
        self.name = "Qualifying"
        self.date = pd.Timestamp("2026-03-07")
        self.laps = _Laps(
            {
                "DriverNumber": ["1", "2"],
                "LapNumber": [1, 1],
                "LapStartTime": pd.to_timedelta([0, 1], unit="s"),
                "Time": pd.to_timedelta([90, 91], unit="s"),
                "IsAccurate": [True, True],
                "Deleted": [False, False],
            }
        )
        self.car_data = {"1": pd.DataFrame({"SessionTime": pd.to_timedelta([1], unit="s"), "Throttle": [75], "Brake": [False], "Speed": [220]})}
        self.pos_data = {"1": pd.DataFrame({"SessionTime": pd.to_timedelta([1], unit="s"), "X": [1.0], "Y": [2.0]})}
        self.loaded = None

    def load(self, **kwargs) -> None:
        self.loaded = kwargs


def _hash_weekend(root: Path, weekend: str) -> str:
    digest = sha256()
    for path in sorted((root / weekend).rglob("*.ff1pkl")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _audit(tmp_path: Path, partition: str = "training") -> tuple[Path, Path]:
    root = tmp_path / "cache" / "2026"
    weekend = "2026-03-08_Australian_Grand_Prix"
    session = root / weekend / "2026-03-07_Qualifying"
    session.mkdir(parents=True)
    (session / "session_info.ff1pkl").write_bytes(b"source")
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "cache_root": str(root),
                "sessions": [
                    {
                        "weekend": weekend,
                        "event_date": "2026-03-08",
                        "partition": partition,
                        "source_state": "verified",
                        "source_hash": _hash_weekend(root, weekend),
                        "session_names": [session.name],
                    }
                ],
            }
        )
    )
    return audit, session


def test_export_seals_source_bound_qualifying_tables(tmp_path: Path, monkeypatch) -> None:
    audit, session_dir = _audit(tmp_path)
    session = _Session()
    monkeypatch.setattr(qualifying_export.fastf1.Cache, "enable_cache", lambda path: None)
    monkeypatch.setattr(qualifying_export.fastf1, "get_session", lambda *args: session)

    manifest_path = qualifying_export.export_qualifying(
        session_dir,
        audit_path=audit,
        isolated_cache_root=tmp_path / "isolated",
        output_dir=tmp_path / "export",
    )

    manifest = json.loads(manifest_path.read_text())
    assert session.loaded == {"laps": True, "telemetry": True, "weather": True, "messages": True}
    assert manifest["identity"] == {
        "year": 2026,
        "event_name": "Australian Grand Prix",
        "event_date": "2026-03-08",
        "session_date": "2026-03-07",
        "session_kind": "Qualifying",
    }
    assert manifest["source_audit"]["sha256"] == sha256(audit.read_bytes()).hexdigest()
    assert set(manifest["exports"]) == {"laps", "car", "position"}
    for record in manifest["exports"].values():
        path = Path(record["path"])
        assert sha256(path.read_bytes()).hexdigest() == record["sha256"]
    laps = pd.read_parquet(Path(manifest["exports"]["laps"]["path"]))
    assert laps["qualifying_segment"].tolist() == ["Q1", "Q2"]
    assert {"source_row", "DriverNumber", "LapNumber", "LapStartTime", "Time", "IsAccurate", "Deleted"} <= set(laps)
    car = pd.read_parquet(Path(manifest["exports"]["car"]["path"]))
    position = pd.read_parquet(Path(manifest["exports"]["position"]["path"]))
    assert {"source_row", "DriverNumber", "SessionTime", "Throttle", "Brake", "Speed"} <= set(car)
    assert {"source_row", "DriverNumber", "SessionTime", "X", "Y"} <= set(position)


def test_export_refuses_source_hash_change_before_fastf1_load(tmp_path: Path, monkeypatch) -> None:
    audit, session_dir = _audit(tmp_path)
    (session_dir / "session_info.ff1pkl").write_bytes(b"changed")
    monkeypatch.setattr(qualifying_export.fastf1, "get_session", lambda *args: pytest.fail("FastF1 must not run"))

    with pytest.raises(ValueError, match="source hash"):
        qualifying_export.export_qualifying(
            session_dir,
            audit_path=audit,
            isolated_cache_root=tmp_path / "isolated",
            output_dir=tmp_path / "export",
        )


def test_export_refuses_non_training_session_before_copy(tmp_path: Path) -> None:
    audit, session_dir = _audit(tmp_path, partition="selection")

    with pytest.raises(ValueError, match="training"):
        qualifying_export.export_qualifying(
            session_dir,
            audit_path=audit,
            isolated_cache_root=tmp_path / "isolated",
            output_dir=tmp_path / "export",
        )
