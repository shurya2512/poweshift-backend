"""Bounded flat-road axle load consistency solve."""

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite, ulp

from poweshift_backend.physics.state import AxleSolveConfig, CgGeometry
from poweshift_backend.physics.grip import LateralInfeasible


@dataclass(frozen=True)
class AxleLoads:
    """The front and rear normal loads from one coupled iteration."""

    front_n: float
    rear_n: float
    acceleration_ms2: float
    iterations: int


class AxleLoadInfeasible(ValueError):
    """Raised when an axle unloads or the consistency solve does not close."""


def solve_axle_loads(
    mass_kg: float,
    geometry: CgGeometry,
    front_downforce_n: float,
    rear_downforce_n: float,
    longitudinal_force_n: Callable[[float, float], float],
    config: AxleSolveConfig,
    *,
    minimum_front_n: float,
    minimum_rear_n: float,
    force_transfer_slope: Callable[[float, float], float],
) -> AxleLoads:
    """Solve load transfer inside the positive-load, lateral-grip interval."""
    if mass_kg <= 0.0 or front_downforce_n < 0.0 or rear_downforce_n < 0.0:
        raise ValueError("mass and downforce must be valid")
    front = mass_kg * config.gravity_ms2 * geometry.rear_axle_distance_m / geometry.wheelbase_m + front_downforce_n
    rear = mass_kg * config.gravity_ms2 * geometry.front_axle_distance_m / geometry.wheelbase_m + rear_downforce_n
    ratio = geometry.height_m / geometry.wheelbase_m
    lower = minimum_rear_n + ulp(rear) - rear
    upper = front - minimum_front_n - ulp(front)
    if lower >= upper:
        raise LateralInfeasible("lateral demand leaves no supported axle-load interval")

    def residual(transfer: float) -> float:
        return transfer - ratio * longitudinal_force_n(front - transfer, rear + transfer)

    if residual(lower) > 0.0 or residual(upper) < 0.0:
        raise AxleLoadInfeasible("axle consistency root is not bracketed within tyre support")
    transfer = min(upper, max(lower, 0.0))
    for iteration in range(1, config.max_iterations + 1):
        error = residual(transfer)
        if abs(error) <= config.tolerance_n:
            acceleration = longitudinal_force_n(front - transfer, rear + transfer) / mass_kg
            return AxleLoads(front - transfer, rear + transfer, acceleration, iteration)
        if error < 0.0:
            lower = transfer
        else:
            upper = transfer
        slope = 1.0 - ratio * force_transfer_slope(front - transfer, rear + transfer)
        candidate = transfer - error / slope if isfinite(slope) and slope != 0.0 else float("nan")
        transfer = candidate if lower < candidate < upper else (lower + upper) / 2.0
    raise AxleLoadInfeasible("axle load consistency did not converge")
