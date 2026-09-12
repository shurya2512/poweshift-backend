"""Supported scenario duration and event contracts."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ScenarioEvent:
    """One scenario event preserved by replay."""

    time_s: float
    kind: str

    def __post_init__(self) -> None:
        if not isfinite(self.time_s) or not self.kind:
            raise ValueError("scenario event is incomplete")


@dataclass(frozen=True)
class ScenarioSpec:
    """Route, duration and truncation boundary for one scenario."""

    scenario_id: str
    route_id: str
    start_time_s: float
    end_time_s: float
    maximum_steps: int
    events: tuple[ScenarioEvent, ...]

    def __post_init__(self) -> None:
        if not self.scenario_id or not self.route_id or not all(isfinite(value) for value in (self.start_time_s, self.end_time_s)):
            raise ValueError("scenario identity or times are invalid")
        if self.end_time_s <= self.start_time_s or self.maximum_steps < 1:
            raise ValueError("scenario bounds must advance")
        if any(not self.start_time_s <= event.time_s <= self.end_time_s for event in self.events):
            raise ValueError("scenario event is outside the scenario window")
        if any(right.time_s < left.time_s for left, right in zip(self.events, self.events[1:])):
            raise ValueError("scenario events must be chronological")
