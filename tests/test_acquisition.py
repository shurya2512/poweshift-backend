from datetime import date

import pytest
from pydantic import ValidationError

from poweshift_backend.contracts.acquisition import (
    SessionRequest,
    StreamStatus,
    resolve_bahrain_test_request,
)


@pytest.mark.parametrize(
    ("test_number", "day_number", "expected_date"),
    [
        (1, 1, date(2026, 2, 11)),
        (1, 2, date(2026, 2, 12)),
        (1, 3, date(2026, 2, 13)),
        (2, 1, date(2026, 2, 18)),
        (2, 2, date(2026, 2, 19)),
        (2, 3, date(2026, 2, 20)),
    ],
)
def test_resolves_each_requested_bahrain_test_day(
    test_number: int, day_number: int, expected_date: date
) -> None:
    identity = resolve_bahrain_test_request(
        SessionRequest(year=2026, test_number=test_number, day_number=day_number)
    )

    assert identity.date == expected_date
    assert identity.venue == "Bahrain"
    assert identity.session_kind == "preseason_test"


@pytest.mark.parametrize(
    "request_args",
    [
        {"year": 2025, "test_number": 1, "day_number": 1},
        {"year": 2026, "test_number": 3, "day_number": 1},
        {"year": 2026, "test_number": 1, "day_number": 4},
        {
            "year": 2026,
            "test_number": 1,
            "day_number": 1,
            "venue": "Melbourne",
        },
    ],
)
def test_rejects_requests_outside_the_bahrain_preseason_corpus(
    request_args: dict[str, int | str]
) -> None:
    with pytest.raises(ValidationError):
        SessionRequest(**request_args)


def test_stream_statuses_keep_empty_missing_and_failed_distinct() -> None:
    assert {status.value for status in StreamStatus} == {
        "present",
        "verified_empty",
        "missing",
        "failed",
    }
