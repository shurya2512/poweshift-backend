from datetime import date
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from poweshift_backend.sources import fastf1_loader
from poweshift_backend.sources import weekend_loader
from poweshift_backend.data import weekend_acquisition
from poweshift_backend.sources.fastf1_loader import StreamResult


def test_race_loader_rejects_a_session_with_an_unexpected_event_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _Session(event_date=date(2026, 3, 15))
    _install_session(monkeypatch, session)

    with pytest.raises(ValueError, match="unexpected race session"):
        weekend_loader.load_race(
            year=2026,
            event_name="Australian Grand Prix",
            expected_date=date(2026, 3, 8),
            cache_dir=tmp_path / "cache",
            log_path=tmp_path / "fastf1.log",
        )

    assert session.load_calls == []


def test_race_loader_rejects_a_session_with_an_unexpected_race_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _Session(session_date=date(2026, 3, 9))
    _install_session(monkeypatch, session)

    with pytest.raises(ValueError, match="unexpected race session"):
        weekend_loader.load_race(
            year=2026,
            event_name="Australian Grand Prix",
            expected_date=date(2026, 3, 8),
            cache_dir=tmp_path / "cache",
            log_path=tmp_path / "fastf1.log",
        )

    assert session.load_calls == []


def test_race_loader_returns_identity_and_isolates_stream_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _Session(failed=True)
    _install_session(monkeypatch, session)

    identity, roster, streams = weekend_loader.load_race(
        year=2026,
        event_name="Australian Grand Prix",
        expected_date=date(2026, 3, 8),
        cache_dir=tmp_path / "cache",
        log_path=tmp_path / "fastf1.log",
    )

    assert identity.event_name == "Australian Grand Prix"
    assert identity.date == date(2026, 3, 8)
    assert identity.session_kind == "race"
    assert roster == ["1"]
    assert session.load_calls == [{"laps": True, "telemetry": True, "weather": True, "messages": True}]
    assert streams["car"].status is fastf1_loader.StreamStatus.PRESENT
    assert streams["track_status"].status is fastf1_loader.StreamStatus.FAILED
    assert streams["track_status"].reason == "captured source request failed"


def test_race_acquisition_seals_exports_and_source_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = weekend_loader.RaceIdentity(2026, "Australian Grand Prix", date(2026, 3, 8))
    cache_dir = tmp_path / "cache"
    source_dir = cache_dir / "2026" / "2026-03-08_Australian_Grand_Prix" / "2026-03-08_Race"
    source_dir.mkdir(parents=True)
    (source_dir / "timing.ff1pkl").write_bytes(b"official race capture")

    def load_race(*args, **kwargs):
        log_path = kwargs["log_path"]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("captured FastF1 loader log\n")
        return identity, ["1"], _present_streams()

    monkeypatch.setattr(weekend_acquisition, "load_race", load_race)
    output_dir = tmp_path / "output"

    manifest_path = weekend_acquisition.acquire_race(
        year=2026,
        event_name="Australian Grand Prix",
        expected_date=date(2026, 3, 8),
        cache_dir=cache_dir,
        output_dir=output_dir,
    )

    manifest = json.loads(manifest_path.read_text())
    assert manifest["identity"] == {
        "date": "2026-03-08",
        "event_name": "Australian Grand Prix",
        "session_kind": "race",
        "year": 2026,
    }
    assert manifest["exports"]["laps"]["provenance"]["source_snapshot_sha256"] == manifest["source_snapshot_sha256"]
    assert manifest["source_snapshot"] == {"timing.ff1pkl": sha256(b"official race capture").hexdigest()}
    assert (output_dir / "source_snapshot" / "timing.ff1pkl").read_bytes() == b"official race capture"
    assert (output_dir / "laps.parquet").exists()
    assert "cache_hashes" not in manifest

    first_hash = sha256(manifest_path.read_bytes()).hexdigest()
    assert weekend_acquisition.acquire_race(
        year=2026,
        event_name="Australian Grand Prix",
        expected_date=date(2026, 3, 8),
        cache_dir=cache_dir,
        output_dir=output_dir,
    ) == manifest_path
    assert sha256(manifest_path.read_bytes()).hexdigest() == first_hash


def _install_session(monkeypatch: pytest.MonkeyPatch, session: "_Session") -> None:
    monkeypatch.setattr(weekend_loader.fastf1.Cache, "enable_cache", lambda path: None)
    monkeypatch.setattr(weekend_loader.fastf1, "get_session", lambda *args: session)


def _frame(values: dict[str, list[object]]) -> pd.DataFrame:
    return pd.DataFrame(values).assign(NativeSourceRow=lambda frame: range(10, 10 + len(frame)))


def _present_streams() -> dict[str, StreamResult]:
    records = _frame({
        "Time": [pd.Timedelta(seconds=20)],
        "DriverNumber": ["1"],
        "LapNumber": [1],
        "IsAccurate": [True],
        "FastF1Generated": [False],
    })
    return {
        "car": StreamResult(_frame({"SessionTime": [pd.Timedelta(seconds=10)], "DriverNumber": ["1"]}), fastf1_loader.StreamStatus.PRESENT),
        "position": StreamResult(_frame({"SessionTime": [pd.Timedelta(seconds=11)], "DriverNumber": ["1"]}), fastf1_loader.StreamStatus.PRESENT),
        "laps": StreamResult(records, fastf1_loader.StreamStatus.PRESENT),
        "tyres": StreamResult(records, fastf1_loader.StreamStatus.PRESENT),
        "weather": StreamResult(_frame({"Time": [pd.Timedelta(seconds=5)]}), fastf1_loader.StreamStatus.PRESENT),
        "session_status": StreamResult(_frame({"Time": [pd.Timedelta(seconds=5)]}), fastf1_loader.StreamStatus.PRESENT),
        "track_status": StreamResult(_frame({"Time": [pd.Timedelta(seconds=5)]}), fastf1_loader.StreamStatus.PRESENT),
        "race_control_messages": StreamResult(_frame({"Time": [pd.Timedelta(seconds=5)]}), fastf1_loader.StreamStatus.PRESENT),
    }


class _Session:
    def __init__(
        self, event_date: date = date(2026, 3, 8), session_date: date | None = None, failed: bool = False
    ) -> None:
        self.event = {"EventName": "Australian Grand Prix", "EventDate": pd.Timestamp(event_date)}
        self.name = "Race"
        self.date = pd.Timestamp(session_date or event_date)
        self.drivers = ["1"]
        self.load_calls: list[dict[str, bool]] = []
        self.laps = _frame({"Time": [pd.Timedelta(seconds=20)], "DriverNumber": ["1"]})
        self.car_data = {"1": _frame({"SessionTime": [pd.Timedelta(seconds=10)]})}
        self.pos_data = {"1": _frame({"SessionTime": [pd.Timedelta(seconds=11)]})}
        self.weather_data = _frame({"Time": [pd.Timedelta(seconds=5)]})
        self.session_status = self.weather_data
        self.race_control_messages = self.weather_data
        self._failed = failed

    @property
    def track_status(self) -> pd.DataFrame:
        if self._failed:
            raise RuntimeError("captured source request failed")
        return self.weather_data

    def load(self, **kwargs: bool) -> None:
        self.load_calls.append(kwargs)
