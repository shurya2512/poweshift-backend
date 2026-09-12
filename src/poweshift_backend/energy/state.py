"""Energy state owned separately from mechanics state."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class EnergyState:
    """Stored energy and cumulative terminal throughput."""

    stored_energy_j: float
    recharge_throughput_j: float
    discharge_throughput_j: float

    def __post_init__(self) -> None:
        if not all(isfinite(value) and value >= 0.0 for value in self.__dict__.values()):
            raise ValueError("energy state values must be finite and non-negative")
