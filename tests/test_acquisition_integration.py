from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from poweshift_backend.contracts.acquisition import SessionRequest, StreamStatus, resolve_bahrain_test_request
from poweshift_backend.data import acquisition
from poweshift_backend.sources import fastf1_loader
from poweshift_backend.sources.fastf1_loader import StreamResult


def test_acquisition_keeps_present_empty_missing_and_failed_streams_distinct(
    tmp_path: Path, monkeypatch
) -> None:
    request = SessionRequest(year=2026, test_number=1, day_number=1)
    cache_dir = _sealed_cache(tmp_path, (request,))
    _install_session(monkeypatch, _Session(resolve_bahrain_test_request(request), missing=True, failed=True))
    monkeypatch.setattr(acquisition, "load_bahrain_test_day", _verified_empty_loader)

    result = acquisition._acquire_day(request, cache_dir, tmp_path / "output")

    assert set(result["exports"]) == {"car", "position", "laps", "tyres", "weather", "race_control_messages"}
    assert {name: report["status"] for name, report in result["coverage"].items()} == {
        "car": "present", "position": "present", "laps": "present", "tyres": "present",
        "weather": "present", "session_status": "missing", "track_status": "failed",
        "race_control_messages": "verified_empty",
    }
    assert result["coverage"]["session_status"]["reason"] == "FastF1 returned no records"
    assert result["coverage"]["track_status"]["error"] == "captured source request failed"
    assert result["exclusions"] == {"44": "missing_car_data"}


def test_loader_classifies_explicit_empty_evidence_without_guessing_from_empty_records() -> None:
    rows = _frame({"DriverNumber": ["1"]})

    assert fastf1_loader._records(lambda: rows).status is StreamStatus.PRESENT
    missing = fastf1_loader._records(lambda: rows.iloc[0:0])
    assert (missing.status, missing.reason) == (StreamStatus.MISSING, "FastF1 returned no records")
    assert fastf1_loader._records(lambda: rows.iloc[0:0], verified_empty=True).status is StreamStatus.VERIFIED_EMPTY
    failed = fastf1_loader._records(lambda: (_ for _ in ()).throw(RuntimeError("source failed")))
    assert (failed.status, failed.reason) == (StreamStatus.FAILED, "source failed")


def test_actual_loader_preserves_valid_peers_when_a_stream_property_fails(
    tmp_path: Path, monkeypatch
) -> None:
    request = SessionRequest(year=2026, test_number=1, day_number=1)
    _install_session(monkeypatch, _Session(resolve_bahrain_test_request(request), failed=True))

    _, _, streams = fastf1_loader.load_bahrain_test_day(request, tmp_path / "cache", tmp_path / "fastf1.log")

    assert streams["car"].status is StreamStatus.PRESENT
    assert streams["position"].status is StreamStatus.PRESENT
    assert streams["track_status"].status is StreamStatus.FAILED
    assert streams["track_status"].reason == "captured source request failed"


def test_sealed_capture_reproduces_export_and_bundle_hashes_without_changing_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    requests = tuple(SessionRequest(year=2026, test_number=test, day_number=day) for test in (1, 2) for day in (1, 2, 3))
    cache_dir = _sealed_cache(tmp_path, requests)
    original_cache = _hashes(cache_dir)
    monkeypatch.setattr(acquisition, "load_bahrain_test_day", _present_loader)
    output_dir = tmp_path / "output"

    first_bundle = acquisition.acquire_all(cache_dir, output_dir)
    first_hashes = _hashes(output_dir)
    second_bundle = acquisition.acquire_all(cache_dir, output_dir)

    assert second_bundle == first_bundle
    assert _hashes(output_dir) == first_hashes
    assert _hashes(cache_dir) == original_cache
    bundle = json.loads(first_bundle.read_text())
    assert bundle["sessions"][0]["exports"]["car"]["sha256"] == first_hashes["test_1_day_1/car.parquet"]


def test_loader_refuses_a_conflicting_immutable_log_without_replacing_it(tmp_path: Path, monkeypatch) -> None:
    request = SessionRequest(year=2026, test_number=1, day_number=1)
    log_path = tmp_path / "fastf1.log"
    log_path.write_text("sealed loader log\n")
    original = log_path.read_bytes()
    _install_session(monkeypatch, _Session(resolve_bahrain_test_request(request)))

    with pytest.raises(FileExistsError):
        fastf1_loader.load_bahrain_test_day(request, tmp_path / "cache", log_path)

    assert log_path.read_bytes() == original
    assert not log_path.with_suffix(".log.candidate").exists()


def _verified_empty_loader(request: SessionRequest, cache_dir: Path, log_path: Path):
    identity, roster, streams = fastf1_loader.load_bahrain_test_day(request, cache_dir, log_path)
    streams["race_control_messages"] = StreamResult(_frame({"Time": []}), StreamStatus.VERIFIED_EMPTY)
    return identity, roster, streams


def _present_loader(request: SessionRequest, cache_dir: Path, log_path: Path):
    identity = resolve_bahrain_test_request(request)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("captured FastF1 loader log\n")
    streams = _present_streams()
    return identity, ["1"], streams


def _install_session(monkeypatch, session: "_Session") -> None:
    monkeypatch.setattr(fastf1_loader.fastf1.Cache, "enable_cache", lambda path: None)
    monkeypatch.setattr(fastf1_loader.fastf1, "get_testing_session", lambda *args: session)


def _present_streams() -> dict[str, StreamResult]:
    session = _Session(resolve_bahrain_test_request(SessionRequest(year=2026, test_number=1, day_number=1)))
    return {
        "car": StreamResult(_driver_records(session.car_data), StreamStatus.PRESENT),
        "position": StreamResult(_driver_records(session.pos_data), StreamStatus.PRESENT),
        "laps": StreamResult(session.laps, StreamStatus.PRESENT),
        "tyres": StreamResult(session.laps, StreamStatus.PRESENT),
        "weather": StreamResult(session.weather_data, StreamStatus.PRESENT),
        "session_status": StreamResult(session.weather_data, StreamStatus.PRESENT),
        "track_status": StreamResult(session.weather_data, StreamStatus.PRESENT),
        "race_control_messages": StreamResult(session.weather_data, StreamStatus.PRESENT),
    }


def _driver_records(records: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.concat([frame.assign(DriverNumber=driver) for driver, frame in records.items()])


def _sealed_cache(tmp_path: Path, requests: tuple[SessionRequest, ...]) -> Path:
    cache_dir = tmp_path / "cache"
    for request in requests:
        identity = resolve_bahrain_test_request(request)
        source_dir = cache_dir / f"{identity.date}_Day_{identity.day_number}"
        source_dir.mkdir(parents=True)
        (source_dir / "capture.ff1pkl").write_bytes(b"captured FastF1 source")
    return cache_dir


def _frame(values: dict[str, list[object]]) -> pd.DataFrame:
    return pd.DataFrame(values).assign(NativeSourceRow=lambda frame: range(101, 101 + len(frame)))


def _hashes(directory: Path) -> dict[str, str]:
    return {str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest() for path in sorted(path for path in directory.rglob("*") if path.is_file())}


class _Session:
    def __init__(self, identity, missing: bool = False, failed: bool = False) -> None:
        self.event = {"Location": identity.venue}
        self.date = pd.Timestamp(identity.date)
        self.drivers = ["1", "44"] if missing else ["1"]
        self.laps = _frame({"Time": [pd.Timedelta(seconds=20)], "DriverNumber": ["1"], "IsAccurate": [True], "FastF1Generated": [False]})
        self.car_data = {"1": _frame({"SessionTime": [pd.Timedelta(seconds=10)]})}
        self.pos_data = {"1": _frame({"SessionTime": [pd.Timedelta(seconds=11)]})}
        self.weather_data = _frame({"Time": [pd.Timedelta(seconds=5)]})
        self.session_status = self.weather_data.iloc[0:0] if missing else self.weather_data
        self.race_control_messages = self.weather_data.iloc[0:0]
        self._failed = failed

    @property
    def track_status(self) -> pd.DataFrame:
        if self._failed:
            raise RuntimeError("captured source request failed")
        return self.weather_data

    def load(self, **kwargs) -> None:
        pass
