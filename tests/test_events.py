import pandas as pd
import pytest

from poweshift_backend.events.timeline import (
    EventKind,
    TrackStatusMeaning,
    build_race_control_events,
    build_session_status_events,
    build_track_status_events,
    track_status_meaning,
)


def test_track_status_code_seven_is_vsc_ending_distinct_from_all_clear() -> None:
    assert track_status_meaning("7") == TrackStatusMeaning.VSC_ENDING
    assert track_status_meaning("1") == TrackStatusMeaning.ALL_CLEAR
    assert track_status_meaning("7") != track_status_meaning("1")


def test_unknown_track_status_code_is_marked_unknown_not_silently_misclassified() -> None:
    assert track_status_meaning("99") == TrackStatusMeaning.UNKNOWN


def test_build_track_status_events_preserve_time_meaning_and_source_row() -> None:
    track_status = pd.DataFrame(
        {
            "source_row": [0, 1, 2],
            "Time": pd.to_timedelta(["0:00:00", "0:01:00", "0:02:00"]),
            "Status": ["2", "7", "1"],
            "Message": ["Yellow", "VSCEnding", "AllClear"],
        }
    )

    events = build_track_status_events(track_status, session_key="test_1_day_1")

    assert [e.label for e in events] == ["yellow", "vsc_ending", "all_clear"]
    assert [e.time_s for e in events] == [0.0, 60.0, 120.0]
    assert [e.source_row for e in events] == [0, 1, 2]
    assert all(e.kind == EventKind.TRACK_STATUS for e in events)
    assert all(e.time_origin == "session_start" for e in events)


@pytest.mark.parametrize(
    ("codes", "expected_labels"),
    [
        (["7", "1"], ["vsc_ending", "all_clear"]),
        (["6", "7"], ["vsc_deployed", "vsc_ending"]),
    ],
)
def test_vsc_ending_is_never_collapsed_into_an_unrestricted_clear_meaning(
    codes: list[str], expected_labels: list[str]
) -> None:
    track_status = pd.DataFrame(
        {
            "source_row": list(range(len(codes))),
            "Time": pd.to_timedelta([f"0:0{i}:00" for i in range(len(codes))]),
            "Status": codes,
            "Message": [""] * len(codes),
        }
    )

    events = build_track_status_events(track_status, session_key="test_1_day_1")

    assert [e.label for e in events] == expected_labels


def test_build_session_status_events_preserve_status_text_and_time() -> None:
    session_status = pd.DataFrame(
        {
            "source_row": [0, 1],
            "Time": pd.to_timedelta(["0:00:10", "0:10:36"]),
            "Status": ["Inactive", "Started"],
        }
    )

    events = build_session_status_events(session_status, session_key="test_1_day_1")

    assert [e.label for e in events] == ["Inactive", "Started"]
    assert [e.time_s for e in events] == [10.0, 636.0]
    assert all(e.kind == EventKind.SESSION_STATUS for e in events)
    assert all(e.detail is None for e in events)


def test_build_race_control_events_carry_flag_message_and_source_row_from_the_explicit_origin() -> None:
    session_start = pd.Timestamp("2026-02-11 06:49:26")
    race_control_messages = pd.DataFrame(
        {
            "source_row": [0, 1],
            "Time": [pd.Timestamp("2026-02-11 06:58:39"), pd.Timestamp("2026-02-11 07:00:02")],
            "Category": ["Other", "Flag"],
            "Message": ["PINK HEAD PADDING MATERIAL MUST BE USED", "GREEN LIGHT - PIT EXIT OPEN"],
            "Flag": [None, "GREEN"],
        }
    )

    events = build_race_control_events(
        race_control_messages, session_key="test_1_day_1", session_start=session_start
    )

    assert events[0].label == "Other"
    assert events[0].detail == "PINK HEAD PADDING MATERIAL MUST BE USED"
    assert events[1].label == "GREEN"
    assert events[0].time_s == pytest.approx(553.0)
    assert all(e.kind == EventKind.RACE_CONTROL_MESSAGE for e in events)
    assert [e.source_row for e in events] == [0, 1]
