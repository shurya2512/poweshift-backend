"""Signed fuel, terminal, store-loss and throughput accounting."""

from dataclasses import dataclass
from math import isfinite

from poweshift_backend.contracts.powertrain import EnergyStoreSpec
from poweshift_backend.energy.state import EnergyState


@dataclass(frozen=True)
class AccountingConfig:
    """Frozen physical values for one accounting experiment."""

    store: EnergyStoreSpec
    fuel_lower_heating_value_j_kg: float
    ice_efficiency: float
    charge_efficiency: float
    named_store_loss_w: float
    evidence_id: str

    def __post_init__(self) -> None:
        values = (self.fuel_lower_heating_value_j_kg, self.ice_efficiency, self.charge_efficiency, self.named_store_loss_w)
        if not all(isfinite(value) for value in values):
            raise ValueError("accounting values must be finite")
        if self.fuel_lower_heating_value_j_kg <= 0.0 or not 0.0 < self.ice_efficiency <= 1.0:
            raise ValueError("fuel accounting values are invalid")
        if not 0.0 < self.charge_efficiency <= 1.0 or self.named_store_loss_w < 0.0 or not self.evidence_id:
            raise ValueError("store accounting values are invalid")


@dataclass(frozen=True)
class AccountingResult:
    """Updated state with explicit losses, recovery and curtailment."""

    state: EnergyState
    fuel_mass_kg: float
    fuel_used_kg: float
    store_loss_j: float
    stored_recovery_j: float
    curtailed_energy_j: float


def account_energy_step(
    state: EnergyState,
    fuel_mass_kg: float,
    ice_shaft_power_w: float,
    motor_dc_power_w: float,
    step_s: float,
    config: AccountingConfig,
) -> AccountingResult:
    """Advance one signed terminal-power stage and clip only at store limits."""
    values = (fuel_mass_kg, ice_shaft_power_w, motor_dc_power_w, step_s)
    if not all(isfinite(value) for value in values) or fuel_mass_kg < 0.0 or ice_shaft_power_w < 0.0 or step_s <= 0.0:
        raise ValueError("energy step inputs are unsupported")
    fuel_used = ice_shaft_power_w * step_s / (config.ice_efficiency * config.fuel_lower_heating_value_j_kg)
    if fuel_used > fuel_mass_kg:
        raise ValueError("fuel state would become negative")
    terminal_energy = motor_dc_power_w * step_s
    store_loss = config.named_store_loss_w * step_s
    stored_recovery = max(0.0, -terminal_energy) * config.charge_efficiency
    requested_energy = state.stored_energy_j - max(0.0, terminal_energy) + stored_recovery - store_loss
    clipped_energy = min(config.store.maximum_energy_j, max(config.store.minimum_energy_j, requested_energy))
    curtailed = abs(requested_energy - clipped_energy)
    return AccountingResult(
        EnergyState(
            clipped_energy,
            state.recharge_throughput_j + max(0.0, -terminal_energy),
            state.discharge_throughput_j + max(0.0, terminal_energy),
        ),
        fuel_mass_kg - fuel_used,
        fuel_used,
        store_loss,
        stored_recovery,
        curtailed,
    )
