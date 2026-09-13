"""Event-stage coupling for the single mechanics and energy owners."""

from dataclasses import dataclass
from math import isfinite

from poweshift_backend.contracts.powertrain import PowertrainAllocation
from poweshift_backend.energy.accounting import AccountingConfig, account_energy_step
from poweshift_backend.energy.state import EnergyState
from poweshift_backend.physics.state import MechanicsState


@dataclass(frozen=True)
class CoupledEnergyState:
    """Mechanics fuel and storage state at one event boundary."""

    mechanics: MechanicsState
    energy: EnergyState
    bundle_id: str


@dataclass(frozen=True)
class EnergyStage:
    """One constant source allocation ending at a named time."""

    end_time_s: float
    allocation: PowertrainAllocation

    def __post_init__(self) -> None:
        if not isfinite(self.end_time_s):
            raise ValueError("energy stage time must be finite")


def integrate_energy_stages(
    initial: CoupledEnergyState,
    stages: tuple[EnergyStage, ...],
    config: AccountingConfig,
) -> tuple[CoupledEnergyState, ...]:
    """Split accounting at every declared source transition."""
    states = [initial]
    current = initial
    for stage in stages:
        if stage.allocation.bundle_id != current.bundle_id:
            raise ValueError("energy stage bundle is incompatible")
        step_s = stage.end_time_s - current.mechanics.time_s
        if step_s <= 0.0:
            raise ValueError("energy stages must strictly advance")
        result = account_energy_step(
            current.energy,
            current.mechanics.fuel_mass_kg,
            stage.allocation.ice.delivered_power_w,
            stage.allocation.electrical.motor_dc_power_w,
            step_s,
            config,
        )
        mechanics = MechanicsState(
            stage.end_time_s,
            current.mechanics.speed_ms,
            current.mechanics.distance_m,
            current.mechanics.progress_m,
            result.fuel_mass_kg,
        )
        current = CoupledEnergyState(mechanics, result.state, current.bundle_id)
        states.append(current)
    return tuple(states)
