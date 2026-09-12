"""Load permitted FastF1 testing-session records."""

from collections.abc import Mapping
import logging
from pathlib import Path

import fastf1
import pandas as pd

from poweshift_backend.contracts.acquisition import SessionIdentity, SessionRequest, resolve_bahrain_test_request


def load_bahrain_test_day(
    request: SessionRequest, cache_dir: Path, log_path: Path
) -> tuple[SessionIdentity, dict[str, pd.DataFrame]]:
    """Load one identity-checked Bahrain test day into a separate cache."""
    identity = resolve_bahrain_test_request(request)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)
    session = fastf1.get_testing_session(2026, identity.test_number, identity.day_number)
    if session.event["Location"] != identity.venue or session.date.date() != identity.date:
        raise ValueError("FastF1 returned an unexpected testing session")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, mode="w")
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    logger = logging.getLogger("fastf1")
    logger.addHandler(handler)
    try:
        session.load(laps=True, telemetry=True, weather=True, messages=True)
    finally:
        logger.removeHandler(handler)
        handler.close()
    return identity, {
        "car": _driver_frames(session.car_data),
        "position": _driver_frames(session.pos_data),
        "laps": pd.DataFrame(session.laps),
        "tyres": pd.DataFrame(session.laps).reindex(
            columns=["DriverNumber", "LapNumber", "Stint", "Compound", "TyreLife", "FreshTyre"]
        ),
        "weather": session.weather_data,
        "session_status": session.session_status,
        "track_status": session.track_status,
        "race_control_messages": session.race_control_messages,
    }


def _driver_frames(records: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    frames = [frame.assign(DriverNumber=driver) for driver, frame in records.items()]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
