"""Contracts for Bahrain preseason evidence."""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class StreamStatus(str, Enum):
    PRESENT = "present"
    VERIFIED_EMPTY = "verified_empty"
    MISSING = "missing"
    FAILED = "failed"


class SessionRequest(StrictModel):
    year: Literal[2026]
    test_number: Literal[1, 2]
    day_number: Literal[1, 2, 3]
    venue: Literal["Bahrain"] = "Bahrain"


class SessionIdentity(StrictModel):
    year: Literal[2026]
    test_number: Literal[1, 2]
    day_number: Literal[1, 2, 3]
    date: date
    venue: Literal["Bahrain"]
    session_kind: Literal["preseason_test"]


_TEST_DATES = {
    1: (date(2026, 2, 11), date(2026, 2, 12), date(2026, 2, 13)),
    2: (date(2026, 2, 18), date(2026, 2, 19), date(2026, 2, 20)),
}


def resolve_bahrain_test_request(request: SessionRequest) -> SessionIdentity:
    """Resolve one of the six permitted test days."""
    return SessionIdentity(
        year=request.year,
        test_number=request.test_number,
        day_number=request.day_number,
        date=_TEST_DATES[request.test_number][request.day_number - 1],
        venue=request.venue,
        session_kind="preseason_test",
    )
