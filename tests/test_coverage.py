import pandas as pd

from poweshift_backend.data.quality import audit_stream


def test_audit_reports_gaps_ordering_roster_and_available_fields() -> None:
    records = pd.DataFrame(
        {
            "SessionTime": pd.to_timedelta([0, 20, 10], unit="s"),
            "DriverNumber": ["1", "2", "1"],
            "Speed": [100.0, 110.0, 105.0],
        }
    )

    report = audit_stream(records, expected_roster={"1", "3"})

    assert report.status.value == "present"
    assert report.first_time_s == 0.0
    assert report.last_time_s == 20.0
    assert report.gap_count == 1
    assert report.out_of_order_count == 1
    assert report.missing_roster == ["3"]
    assert report.unexpected_roster == ["2"]
    assert report.fields == ["SessionTime", "DriverNumber", "Speed"]


def test_audit_distinguishes_missing_and_failed_streams() -> None:
    missing = audit_stream(None, expected_roster=set())
    failed = audit_stream(None, expected_roster=set(), error="public source timed out")

    assert missing.status.value == "missing"
    assert failed.status.value == "failed"
    assert failed.error == "public source timed out"


def test_audit_reports_datetime_stream_ranges_without_coercing_them_to_durations() -> None:
    records = pd.DataFrame(
        {"Time": pd.to_datetime(["2026-02-11T07:00:00Z", "2026-02-11T07:00:20Z"])}
    )

    report = audit_stream(records, expected_roster=set())

    assert report.first_time_s == 0.0
    assert report.last_time_s == 20.0
    assert report.time_origin == "2026-02-11T07:00:00+00:00"
