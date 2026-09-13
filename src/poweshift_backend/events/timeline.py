"""Timestamped session, track-status and race-control events with source-row references."""

from enum import Enum

import pandas as pd

from poweshift_backend.contracts.acquisition import StrictModel
from poweshift_backend.prepare.normalise import elapsed_seconds, native_elapsed_seconds


class EventKind(str, Enum):
    SESSION_STATUS = "session_status"
    TRACK_STATUS = "track_status"
    RACE_CONTROL_MESSAGE = "race_control_message"


class TrackStatusMeaning(str, Enum):
    ALL_CLEAR = "all_clear"
    YELLOW = "yellow"
    SAFETY_CAR_DEPLOYED = "safety_car_deployed"
    RED = "red"
    VSC_DEPLOYED = "vsc_deployed"
    VSC_ENDING = "vsc_ending"
    UNKNOWN = "unknown"


_TRACK_STATUS_MEANINGS = {
    "1": TrackStatusMeaning.ALL_CLEAR,
    "2": TrackStatusMeaning.YELLOW,
    "4": TrackStatusMeaning.SAFETY_CAR_DEPLOYED,
    "5": TrackStatusMeaning.RED,
    "6": TrackStatusMeaning.VSC_DEPLOYED,
    "7": TrackStatusMeaning.VSC_ENDING,
}


class TimelineEvent(StrictModel):
    """One timestamped event with its source row and explicit time origin."""

    session_key: str
    kind: EventKind
    time_s: float
    time_origin: str
    label: str
    detail: str | None
    source_row: int


def track_status_meaning(status_code: str) -> TrackStatusMeaning:
    """Map a coarse track-status code; code 7 is VSC ending, distinct from all-clear."""
    return _TRACK_STATUS_MEANINGS.get(status_code, TrackStatusMeaning.UNKNOWN)


def build_track_status_events(track_status: pd.DataFrame, session_key: str) -> list[TimelineEvent]:
    """Build one event per track-status row, preserving each coarse code's distinct meaning."""
    times = native_elapsed_seconds(track_status["Time"])
    events = []
    for time_s, (_, row) in zip(times, track_status.iterrows()):
        message = row.get("Message")
        events.append(
            TimelineEvent(
                session_key=session_key,
                kind=EventKind.TRACK_STATUS,
                time_s=float(time_s),
                time_origin="session_start",
                label=track_status_meaning(str(row["Status"])).value,
                detail=str(message) if pd.notna(message) and message != "" else None,
                source_row=int(row["source_row"]),
            )
        )
    return events


def build_session_status_events(session_status: pd.DataFrame, session_key: str) -> list[TimelineEvent]:
    """Build one event per session-status row."""
    times = native_elapsed_seconds(session_status["Time"])
    events = []
    for time_s, (_, row) in zip(times, session_status.iterrows()):
        events.append(
            TimelineEvent(
                session_key=session_key,
                kind=EventKind.SESSION_STATUS,
                time_s=float(time_s),
                time_origin="session_start",
                label=str(row["Status"]),
                detail=None,
                source_row=int(row["source_row"]),
            )
        )
    return events


def build_race_control_events(
    race_control_messages: pd.DataFrame, session_key: str, session_start: pd.Timestamp
) -> list[TimelineEvent]:
    """Build one event per race-control message, elapsed from the explicit session start."""
    times = elapsed_seconds(race_control_messages["Time"], session_start)
    events = []
    for time_s, (_, row) in zip(times, race_control_messages.iterrows()):
        flag = row.get("Flag")
        category = row.get("Category")
        message = row.get("Message")
        label = flag if pd.notna(flag) else (category if pd.notna(category) else "message")
        events.append(
            TimelineEvent(
                session_key=session_key,
                kind=EventKind.RACE_CONTROL_MESSAGE,
                time_s=float(time_s),
                time_origin="session_start",
                label=str(label),
                detail=str(message) if pd.notna(message) and message != "" else None,
                source_row=int(row["source_row"]),
            )
        )
    return events
