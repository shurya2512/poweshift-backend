"""Reduced combined-grip limits for each loaded axle."""

from dataclasses import dataclass
from math import sqrt

from poweshift_backend.tyres.condition import DryTyreCondition


@dataclass(frozen=True)
class AxleGrip:
    """Longitudinal headroom after an axle's lateral demand."""

    longitudinal_headroom_n: float
    lateral_ratio: float


class LateralInfeasible(ValueError):
    """Raised when lateral force exceeds the declared combined-grip envelope."""


def longitudinal_headroom(load_n: float, lateral_force_n: float, tyre: DryTyreCondition) -> AxleGrip:
    """Calculate combined-grip longitudinal headroom for one axle."""
    if load_n <= 0.0:
        raise LateralInfeasible("combined grip needs positive normal load")
    lateral_ratio = lateral_force_n / (tyre.lateral_mu * load_n)
    if abs(lateral_ratio) > 1.0:
        raise LateralInfeasible("lateral demand exceeds declared tyre support")
    return AxleGrip(
        longitudinal_headroom_n=tyre.longitudinal_mu * load_n * sqrt(max(0.0, 1.0 - lateral_ratio**2)),
        lateral_ratio=lateral_ratio,
    )
