"""Load identity-checked FastF1 race records into an isolated cache."""

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import logging
from pathlib import Path

import fastf1
import pandas as pd

from poweshift_backend.sources.fastf1_loader import StreamResult, _driver_frames, _records


@dataclass(frozen=True)
class RaceIdentity:
    """Identity returned after FastF1 confirms the requested race."""

    year: int
    event_name: str
    date: date
    session_kind: str = "race"


def load_race(
    year: int,
    event_name: str,
    expected_date: date,
    cache_dir: Path,
    log_path: Path,
) -> tuple[RaceIdentity, list[str], dict[str, StreamResult]]:
    """Load one date-checked race without reusing another cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))
    session = fastf1.get_session(year, event_name, "R")
    actual_date = pd.Timestamp(session.event["EventDate"]).date()
    session_date = pd.Timestamp(session.date).date()
    if (
        expected_date.year != year
        or session.event["EventName"] != event_name
        or session.name != "Race"
        or actual_date != expected_date
        or session_date != expected_date
    ):
        raise ValueError("FastF1 returned an unexpected race session")
    identity = RaceIdentity(year=year, event_name=event_name, date=actual_date)
    _load_with_log(session, log_path)
    laps = _records(lambda: pd.DataFrame(session.laps).assign(NativeSourceRow=session.laps.index))
    return identity, [str(driver) for driver in session.drivers], {
        "car": _records(lambda: _driver_frames(session.car_data)),
        "position": _records(lambda: _driver_frames(session.pos_data)),
        "laps": laps,
        "tyres": _tyre_stream(laps),
        "weather": _records(lambda: session.weather_data),
        "session_status": _records(lambda: session.session_status),
        "track_status": _records(lambda: session.track_status),
        "race_control_messages": _records(lambda: session.race_control_messages),
    }


def _load_with_log(session: fastf1.core.Session, log_path: Path) -> None:
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


def _tyre_stream(laps: StreamResult) -> StreamResult:
    if laps.records is None:
        return StreamResult(None, laps.status, laps.reason)
    return StreamResult(
        laps.records.reindex(
            columns=["NativeSourceRow", "Time", "DriverNumber", "LapNumber", "Stint", "Compound", "TyreLife", "FreshTyre"]
        ),
        laps.status,
        laps.reason,
    )
