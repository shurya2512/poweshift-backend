"""Source-bound ICE power maps."""

from dataclasses import dataclass
from math import isfinite

import numpy as np

from poweshift_backend.contracts.powertrain import EvidenceOrigin


@dataclass(frozen=True)
class SourcePowerMap:
    """One monotonic shaft-speed map with explicit provenance."""

    shaft_speed_rpm: tuple[float, ...]
    power_values_w: tuple[float, ...]
    origin: EvidenceOrigin
    source_id: str

    def __post_init__(self) -> None:
        if len(self.shaft_speed_rpm) < 2 or len(self.power_values_w) != len(self.shaft_speed_rpm):
            raise ValueError("power map axes must align and contain at least two points")
        if not all(isfinite(value) for value in (*self.shaft_speed_rpm, *self.power_values_w)):
            raise ValueError("power map values must be finite")
        if any(right <= left for left, right in zip(self.shaft_speed_rpm, self.shaft_speed_rpm[1:])):
            raise ValueError("power map shaft speeds must strictly increase")
        if any(value < 0.0 for value in self.power_values_w) or not self.source_id:
            raise ValueError("power map provenance or values are invalid")

    def maximum_power_w_at(self, shaft_speed_rpm: float) -> float:
        """Interpolate maximum power inside source support."""
        if not self.shaft_speed_rpm[0] <= shaft_speed_rpm <= self.shaft_speed_rpm[-1]:
            raise ValueError("shaft speed is outside source map support")
        return float(np.interp(shaft_speed_rpm, self.shaft_speed_rpm, self.power_values_w))

    def maximum_power_w(self, shaft_speed_rpm: float) -> float:
        """Interpolate maximum power inside source support."""
        return self.maximum_power_w_at(shaft_speed_rpm)
