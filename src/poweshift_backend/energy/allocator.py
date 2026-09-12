"""Additive ICE, boost, and per-lap harvest accounting."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class DeploymentPrior:
    """Explicit diagnostic power and storage assumptions."""

    electric_boost_fraction: float
    usable_store_j: float
    harvest_cap_j_per_lap: float
    motor_efficiency: float
    harvest_efficiency: float

    def __post_init__(self) -> None:
        values = self.__dict__.values()
        if not all(isfinite(value) and value > 0.0 for value in values):
            raise ValueError("deployment prior values must be positive and finite")
        if max(self.electric_boost_fraction, self.motor_efficiency, self.harvest_efficiency) > 1.0:
            raise ValueError("deployment fractions and efficiencies cannot exceed one")


@dataclass(frozen=True)
class LapEnergyState:
    """Storage and gross energy ledgers for one simulated run."""

    stored_energy_j: float
    harvested_this_lap_j: float
    gross_deployment_j: float
    gross_harvest_j: float
    curtailed_energy_j: float

    @classmethod
    def full(cls, prior: DeploymentPrior) -> "LapEnergyState":
        """Start from the declared usable-store assumption."""
        return cls(prior.usable_store_j, 0.0, 0.0, 0.0, 0.0)

    def next_lap(self) -> "LapEnergyState":
        """Reset only the per-lap harvest counter."""
        return LapEnergyState(self.stored_energy_j, 0.0, self.gross_deployment_j, self.gross_harvest_j, self.curtailed_energy_j)


@dataclass(frozen=True)
class AdditivePowerResult:
    """Delivered power, axle force, and updated energy ledgers."""

    ice_wheel_power_w: float
    motor_wheel_power_w: float
    total_wheel_power_w: float
    axle_force_n: float
    harvest_curtailed_j: float
    state: LapEnergyState


def allocate_additive_power(
    prior: DeploymentPrior,
    state: LapEnergyState,
    speed_ms: float,
    throttle: float,
    brake: float,
    deployment_fraction: float,
    maximum_drive_force_n: float,
    step_s: float,
) -> AdditivePowerResult:
    """Add motor boost to ICE power or harvest during braking."""
    values = (speed_ms, throttle, brake, deployment_fraction, maximum_drive_force_n, step_s)
    if not all(isfinite(value) for value in values) or speed_ms <= 0.0 or maximum_drive_force_n <= 0.0 or step_s <= 0.0:
        raise ValueError("power allocation inputs are invalid")
    if not all(0.0 <= value <= 1.0 for value in (throttle, brake, deployment_fraction)):
        raise ValueError("driver and deployment fractions must be bounded")
    ice_force_n = maximum_drive_force_n * throttle
    ice_power_w = ice_force_n * speed_ms
    maximum_motor_wheel_w = maximum_drive_force_n * speed_ms * prior.electric_boost_fraction
    if brake > 0.0:
        requested_harvest_j = maximum_motor_wheel_w * brake * step_s
        lap_room_j = max(0.0, prior.harvest_cap_j_per_lap - state.harvested_this_lap_j)
        terminal_harvest_j = min(requested_harvest_j, lap_room_j)
        stored_j = terminal_harvest_j * prior.harvest_efficiency
        capacity_room_j = max(0.0, prior.usable_store_j - state.stored_energy_j)
        accepted_stored_j = min(stored_j, capacity_room_j)
        accepted_terminal_j = accepted_stored_j / prior.harvest_efficiency
        curtailed_j = max(0.0, requested_harvest_j - accepted_terminal_j)
        updated = LapEnergyState(
            state.stored_energy_j + accepted_stored_j,
            state.harvested_this_lap_j + terminal_harvest_j,
            state.gross_deployment_j,
            state.gross_harvest_j + accepted_terminal_j,
            state.curtailed_energy_j + curtailed_j,
        )
        return AdditivePowerResult(0.0, 0.0, 0.0, 0.0, curtailed_j, updated)
    requested_motor_wheel_w = maximum_motor_wheel_w * deployment_fraction
    storage_motor_wheel_w = state.stored_energy_j / step_s * prior.motor_efficiency
    motor_wheel_w = min(requested_motor_wheel_w, storage_motor_wheel_w)
    delivered_dc_j = motor_wheel_w / prior.motor_efficiency * step_s
    total_wheel_w = ice_power_w + motor_wheel_w
    updated = LapEnergyState(
        state.stored_energy_j - delivered_dc_j,
        state.harvested_this_lap_j,
        state.gross_deployment_j + delivered_dc_j,
        state.gross_harvest_j,
        state.curtailed_energy_j,
    )
    return AdditivePowerResult(ice_power_w, motor_wheel_w, total_wheel_w, total_wheel_w / speed_ms, 0.0, updated)
