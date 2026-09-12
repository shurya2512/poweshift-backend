"""Explicit dynamic state and effective mechanics assumptions."""

from dataclasses import dataclass
from enum import Enum


class FuelPolicyKind(str, Enum):
    """The declared fuel evolution available to the reduced model."""

    FIXED = "fixed"
    LINEAR_BURN = "linear_burn"


@dataclass(frozen=True)
class FuelPolicy:
    """Fuel policy with an explicit constant burn rate when enabled."""

    kind: FuelPolicyKind
    burn_rate_kg_s: float = 0.0

    def __post_init__(self) -> None:
        if self.burn_rate_kg_s < 0.0:
            raise ValueError("fuel burn rate cannot be negative")
        if self.kind is FuelPolicyKind.FIXED and self.burn_rate_kg_s != 0.0:
            raise ValueError("fixed fuel policy cannot burn fuel")
        if self.kind is FuelPolicyKind.LINEAR_BURN and self.burn_rate_kg_s <= 0.0:
            raise ValueError("linear fuel policy needs a positive burn rate")


@dataclass(frozen=True)
class CgGeometry:
    """Flat-road axle geometry with an explicit CG height."""

    front_axle_distance_m: float
    rear_axle_distance_m: float
    height_m: float

    def __post_init__(self) -> None:
        if min(self.front_axle_distance_m, self.rear_axle_distance_m, self.height_m) <= 0.0:
            raise ValueError("CG geometry dimensions must be positive")

    @property
    def wheelbase_m(self) -> float:
        """Return the distance between the two axles."""
        return self.front_axle_distance_m + self.rear_axle_distance_m


@dataclass(frozen=True)
class MassAssumptions:
    """Reference no-fuel mass and its declared inclusion convention."""

    reference_no_fuel_mass_kg: float
    reference_includes_driver: bool
    reference_includes_ballast: bool
    reference_includes_tyres: bool
    fuel_policy: FuelPolicy

    def __post_init__(self) -> None:
        if self.reference_no_fuel_mass_kg <= 0.0:
            raise ValueError("reference no-fuel mass must be positive")


@dataclass(frozen=True)
class MechanicsState:
    """The float-valued state advanced by the common mechanics path."""

    time_s: float
    speed_ms: float
    distance_m: float
    progress_m: float
    fuel_mass_kg: float

    def __post_init__(self) -> None:
        if self.speed_ms < 0.0:
            raise ValueError("negative speed is an infeasible state")
        if self.fuel_mass_kg < 0.0:
            raise ValueError("negative fuel mass is an infeasible state")


@dataclass(frozen=True)
class StateRate:
    """Time derivative for the mechanics state."""

    speed_ms2: float
    distance_ms: float
    progress_ms: float
    fuel_kg_s: float


@dataclass(frozen=True)
class RoadInput:
    """Supported planar path values for one mechanics evaluation."""

    curvature_m_inv: float
    progress_ratio: float

    def __post_init__(self) -> None:
        if self.progress_ratio <= 0.0:
            raise ValueError("progress ratio must be positive")


@dataclass(frozen=True)
class EffectiveForceAssumptions:
    """Frozen effective force and aero terms used by fitting and replay."""

    max_drive_force_n: float
    max_brake_force_n: float
    drag_n_per_ms2: float
    rolling_resistance_n: float
    front_downforce_n_per_ms2: float
    rear_downforce_n_per_ms2: float

    def __post_init__(self) -> None:
        if min(
            self.max_drive_force_n,
            self.max_brake_force_n,
            self.drag_n_per_ms2,
            self.rolling_resistance_n,
            self.front_downforce_n_per_ms2,
            self.rear_downforce_n_per_ms2,
        ) < 0.0:
            raise ValueError("effective force assumptions cannot be negative")


@dataclass(frozen=True)
class AxleSolveConfig:
    """Configured iteration limit and tolerance for coupled axle loads."""

    gravity_ms2: float
    tolerance_n: float
    max_iterations: int

    def __post_init__(self) -> None:
        if self.gravity_ms2 <= 0.0 or self.tolerance_n <= 0.0 or self.max_iterations < 1:
            raise ValueError("axle solve configuration must be positive")
