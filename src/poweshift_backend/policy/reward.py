"""Non-overlapping local and continuation-tail reward records."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class TacticalReward:
    """Separate local and supported continuation components."""

    local: float
    tail: float

    @property
    def total(self) -> float:
        """Return the sum after both components are independently defined."""
        return self.local + self.tail


def tactical_reward(local: float, tail: float, *, has_supported_continuation: bool) -> TacticalReward:
    """Refuse a tail target when continuation evidence is absent."""
    if not all(isfinite(value) for value in (local, tail)):
        raise ValueError("tactical reward values must be finite")
    if tail != 0.0 and not has_supported_continuation:
        raise ValueError("continuation tail requires supported continuation")
    return TacticalReward(local, tail)
