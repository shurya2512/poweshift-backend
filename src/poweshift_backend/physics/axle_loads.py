"""Bounded flat-road axle load consistency solve."""

from collections.abc import Callable
from dataclasses import dataclass

from poweshift_backend.physics.state import AxleSolveConfig, CgGeometry


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
) -> AxleLoads:
    """Solve loads against the force selected from those same loads."""
    if mass_kg <= 0.0 or front_downforce_n < 0.0 or rear_downforce_n < 0.0:
        raise ValueError("mass and downforce must be valid")
    front = mass_kg * config.gravity_ms2 * geometry.rear_axle_distance_m / geometry.wheelbase_m + front_downforce_n
    rear = mass_kg * config.gravity_ms2 * geometry.front_axle_distance_m / geometry.wheelbase_m + rear_downforce_n
    if front <= 0.0 or rear <= 0.0:
        raise AxleLoadInfeasible("an axle has no positive normal load")
    for iteration in range(1, config.max_iterations + 1):
        acceleration = longitudinal_force_n(front, rear) / mass_kg
        next_front = mass_kg * config.gravity_ms2 * geometry.rear_axle_distance_m / geometry.wheelbase_m + front_downforce_n
        next_front -= mass_kg * acceleration * geometry.height_m / geometry.wheelbase_m
        next_rear = mass_kg * config.gravity_ms2 * geometry.front_axle_distance_m / geometry.wheelbase_m + rear_downforce_n
        next_rear += mass_kg * acceleration * geometry.height_m / geometry.wheelbase_m
        if next_front <= 0.0 or next_rear <= 0.0:
            raise AxleLoadInfeasible("an axle unloaded during the force solve")
        if max(abs(next_front - front), abs(next_rear - rear)) <= config.tolerance_n:
            return AxleLoads(next_front, next_rear, acceleration, iteration)
        front, rear = next_front, next_rear
    raise AxleLoadInfeasible("axle load consistency did not converge")
