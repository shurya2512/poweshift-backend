"""Immutable powertrain inputs with explicit units and evidence origins."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class EvidenceOrigin(str, Enum):
    """How a powertrain value entered the model."""

    OBSERVED = "observed"
    SOURCE_DERIVED = "source_derived"
    ASSUMED = "assumed"
    MODEL_DERIVED = "model_derived"


@dataclass(frozen=True)
class PowerInput:
    """Requested and delivered shaft power in watts."""

    requested_power_w: float
    delivered_power_w: float
    origin: EvidenceOrigin
    source_id: str
    available: bool = True

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.requested_power_w, self.delivered_power_w)):
            raise ValueError("power inputs must be finite")
        if not self.source_id:
            raise ValueError("power inputs need a source id")
        if not self.available and self.delivered_power_w != 0.0:
            raise ValueError("unavailable power cannot be delivered")


@dataclass(frozen=True)
class ElectricalPowerInput:
    """Signed machine shaft and DC-bus power in watts."""

    requested_shaft_power_w: float
    delivered_shaft_power_w: float
    motor_dc_power_w: float
    origin: EvidenceOrigin
    source_id: str
    available: bool = True

    def __post_init__(self) -> None:
        values = (self.requested_shaft_power_w, self.delivered_shaft_power_w, self.motor_dc_power_w)
        if not all(isfinite(value) for value in values):
            raise ValueError("electrical power inputs must be finite")
        if not self.source_id:
            raise ValueError("electrical power inputs need a source id")
        if not self.available and (self.delivered_shaft_power_w != 0.0 or self.motor_dc_power_w != 0.0):
            raise ValueError("unavailable electrical power cannot be delivered")
        if self.delivered_shaft_power_w * self.motor_dc_power_w < 0.0:
            raise ValueError("machine shaft and DC-bus power must have the same direction")


@dataclass(frozen=True)
class EnergyStoreSpec:
    """Usable storage limits, separate from cumulative throughput."""

    usable_capacity_j: float
    minimum_energy_j: float
    maximum_energy_j: float
    origin: EvidenceOrigin
    source_id: str

    def __post_init__(self) -> None:
        values = (self.usable_capacity_j, self.minimum_energy_j, self.maximum_energy_j)
        if not all(isfinite(value) for value in values):
            raise ValueError("store limits must be finite")
        if self.usable_capacity_j <= 0.0:
            raise ValueError("store capacity must be positive")
        if self.minimum_energy_j < 0.0 or self.maximum_energy_j <= self.minimum_energy_j:
            raise ValueError("store energy limits are invalid")
        if self.maximum_energy_j - self.minimum_energy_j > self.usable_capacity_j:
            raise ValueError("store range exceeds usable capacity")
        if not self.source_id:
            raise ValueError("store limits need a source id")

    def state_of_charge(self, stored_energy_j: float) -> float:
        """Return usable state of charge inside the declared limits."""
        if not isfinite(stored_energy_j) or not self.minimum_energy_j <= stored_energy_j <= self.maximum_energy_j:
            raise ValueError("stored energy is outside declared limits")
        return (stored_energy_j - self.minimum_energy_j) / (self.maximum_energy_j - self.minimum_energy_j)


@dataclass(frozen=True)
class PowertrainAllocation:
    """One exclusive source allocation at the axle boundary."""

    requested_axle_force_n: float
    delivered_axle_force_n: float
    unmet_axle_force_n: float
    ice: PowerInput
    electrical: ElectricalPowerInput
    wheel_power_w: float
    bundle_id: str

    def __post_init__(self) -> None:
        values = (
            self.requested_axle_force_n,
            self.delivered_axle_force_n,
            self.unmet_axle_force_n,
            self.wheel_power_w,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("allocation values must be finite")
        if not self.bundle_id:
            raise ValueError("allocation needs an admitted bundle id")
        scale = max(1.0, abs(self.requested_axle_force_n))
        if abs(self.delivered_axle_force_n + self.unmet_axle_force_n - self.requested_axle_force_n) > 1e-9 * scale:
            raise ValueError("allocation force balance is inconsistent")


@dataclass(frozen=True)
class EnergyBundleCompatibility:
    """Compatibility record required by energy-aware consumers."""

    bundle_id: str
    admitted: bool
    physics_id: str
    rules_id: str
    response_id: str
    accounting_id: str
    continuous_profile_id: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.bundle_id,
                self.physics_id,
                self.rules_id,
                self.response_id,
                self.accounting_id,
                self.continuous_profile_id,
            )
        ):
            raise ValueError("energy bundle compatibility is incomplete")
