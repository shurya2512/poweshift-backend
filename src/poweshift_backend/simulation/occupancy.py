"""Simple source-coordinate occupancy checks."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Occupancy:
    """Longitudinal gap and lateral overlap in source coordinates."""

    gap_m: float
    lateral_overlap: float

    def __post_init__(self) -> None:
        if not isfinite(self.gap_m) or not isfinite(self.lateral_overlap) or not 0.0 <= self.lateral_overlap <= 1.0:
            raise ValueError("occupancy values are invalid")
