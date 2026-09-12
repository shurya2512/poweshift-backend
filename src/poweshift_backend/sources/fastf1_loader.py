"""Load permitted FastF1 testing-session records."""

from collections.abc import Mapping
from hashlib import sha256
import logging
from pathlib import Path

import fastf1
import pandas as pd

from poweshift_backend.contracts.acquisition import SessionIdentity, SessionRequest, resolve_bahrain_test_request
from poweshift_backend.contracts.acquisition import StreamStatus


class StreamResult:
    """One stream outcome after a FastF1 session load."""

    def __init__(self, records: pd.DataFrame | None, status: StreamStatus, reason: str | None = None):
        self.records = records
        self.status = status
        self.reason = reason


def load_bahrain_test_day(
    request: SessionRequest, cache_dir: Path, log_path: Path
) -> tuple[SessionIdentity, list[str], dict[str, StreamResult]]:
    """Load one identity-checked Bahrain test day into a separate cache."""
    identity = resolve_bahrain_test_request(request)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)
    session = fastf1.get_testing_session(2026, identity.test_number, identity.day_number)
    if session.event["Location"] != identity.venue or session.date.date() != identity.date:
        raise ValueError("FastF1 returned an unexpected testing session")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_log = log_path.with_suffix(log_path.suffix + ".candidate")
    handler = logging.FileHandler(candidate_log, mode="w")
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    logger = logging.getLogger("fastf1")
    logger.addHandler(handler)
    try:
        session.load(laps=True, telemetry=True, weather=True, messages=True)
    finally:
        logger.removeHandler(handler)
        handler.close()
    candidate_hash = sha256(candidate_log.read_bytes()).hexdigest()
    if log_path.exists() and sha256(log_path.read_bytes()).hexdigest() != candidate_hash:
        candidate_log.unlink()
        raise FileExistsError(f"immutable loader log differs: {log_path}")
    candidate_log.replace(log_path)
    laps = _records(lambda: pd.DataFrame(session.laps).assign(NativeSourceRow=session.laps.index))
    return identity, [str(driver) for driver in session.drivers], {
        "car": _records(lambda: _driver_frames(session.car_data)),
        "position": _records(lambda: _driver_frames(session.pos_data)),
        "laps": laps,
        "tyres": StreamResult(laps.records.reindex(
            columns=["NativeSourceRow", "Time", "DriverNumber", "LapNumber", "Stint", "Compound", "TyreLife", "FreshTyre"]
        ), laps.status, laps.reason) if laps.records is not None else StreamResult(None, laps.status, laps.reason),
        "weather": _records(lambda: session.weather_data),
        "session_status": _records(lambda: session.session_status),
        "track_status": _records(lambda: session.track_status),
        "race_control_messages": _records(lambda: session.race_control_messages),
    }


def _driver_frames(records: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    frames = [frame.assign(DriverNumber=driver, NativeSourceRow=frame.index) for driver, frame in records.items()]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _records(load: callable) -> StreamResult:
    try:
        records = load()
    except Exception as error:
        return StreamResult(None, StreamStatus.FAILED, str(error))
    if records.empty:
        return StreamResult(records, StreamStatus.MISSING, "FastF1 returned no records")
    return StreamResult(records, StreamStatus.PRESENT)
