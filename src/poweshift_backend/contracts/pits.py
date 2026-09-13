"""Immutable fixed-pit context contracts."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Literal


class PitMappingMode(str, Enum):
    """Supported source-to-ego pit mapping."""

    LAP_RELATIVE_FIXED = "lap_relative_fixed"


@dataclass(frozen=True)
class PitVisit:
    """One paired entry and exit from the source schedule."""

    lap: int
    entry_time_s: float
    exit_time_s: float
    serviced_items: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.lap < 1 or not all(isfinite(value) for value in (self.entry_time_s, self.exit_time_s)):
            raise ValueError("pit visit timing is invalid")
        if self.exit_time_s <= self.entry_time_s:
            raise ValueError("pit visit exit must follow entry")
        if len(self.serviced_items) != len(set(self.serviced_items)) or any(not item for item in self.serviced_items):
            raise ValueError("pit serviced items must be unique and named")


@dataclass(frozen=True)
class PitCrossing:
    """One ego crossing used to advance fixed pit execution."""

    lap: int
    time_s: float

    def __post_init__(self) -> None:
        if self.lap < 1 or not isfinite(self.time_s) or self.time_s < 0.0:
            raise ValueError("pit crossing is invalid")


@dataclass(frozen=True)
class PitSourceBinding:
    """Source provenance and approved future pit fields."""

    source_id: str
    source_sha256: str
    visits: tuple[PitVisit, ...]
    allowed_future_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source_id or len(self.source_sha256) != 64:
            raise ValueError("pit source provenance is invalid")


@dataclass(frozen=True)
class FixedPitSchedule:
    """Immutable paired visits mapped to ego laps."""

    schedule_id: str
    mapping_mode: PitMappingMode
    visits: tuple[PitVisit, ...]


@dataclass(frozen=True)
class PitExecutionState:
    """Current stage for one fixed pit visit."""

    visit_index: int
    stage: Literal["track", "entry", "transit", "service", "wait", "exit", "merge"]
    visit: PitVisit | None = None

    def __post_init__(self) -> None:
        if self.visit_index < 0:
            raise ValueError("pit visit index cannot be negative")


@dataclass(frozen=True)
class PitExecutionResult:
    """Next pit stage and any rule conflict."""

    state: PitExecutionState
    conflict: str | None


@dataclass(frozen=True)
class PitEvent:
    """One source-recorded pit event."""

    time_s: float
    kind: str
    line_map_id: str

    def __post_init__(self) -> None:
        if not isfinite(self.time_s) or self.time_s < 0.0 or not self.kind or not self.line_map_id:
            raise ValueError("pit event is incomplete")


@dataclass(frozen=True)
class FixedPitManifest:
    """Source-bound pit events that policy code cannot alter."""

    manifest_id: str
    source_id: str
    source_sha256: str
    events: tuple[PitEvent, ...]

    def __post_init__(self) -> None:
        if not self.manifest_id or not self.source_id or len(self.source_sha256) != 64:
            raise ValueError("fixed pit manifest provenance is invalid")
        if any(right.time_s < left.time_s for left, right in zip(self.events, self.events[1:])):
            raise ValueError("fixed pit events must be chronological")
