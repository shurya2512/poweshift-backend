"""Pure effective force derivative shared by fitting and replay."""

from dataclasses import dataclass
from math import copysign

from poweshift_backend.driver.controller import DriverDemand
from poweshift_backend.physics.axle_loads import AxleLoads, solve_axle_loads
from poweshift_backend.physics.grip import AxleGrip, longitudinal_headroom
from poweshift_backend.physics.state import (
    AxleSolveConfig,
    CgGeometry,
    EffectiveForceAssumptions,
    MassAssumptions,
    MechanicsState,
    RoadInput,
    StateRate,
)
from poweshift_backend.tyres.condition import DryTyreCondition


@dataclass(frozen=True)
class ForceEvaluation:
    """Resolved axle forces and external resistance for one state."""

    front_force_n: float
    rear_force_n: float
    drag_force_n: float
    rolling_force_n: float
    lateral_force_n: float
    axle_loads: AxleLoads
    front_grip: AxleGrip
    rear_grip: AxleGrip

    @property
    def net_force_n(self) -> float:
        """Return the signed force that accelerates the vehicle mass."""
        return self.front_force_n + self.rear_force_n - self.drag_force_n - self.rolling_force_n


def effective_mass_kg(state: MechanicsState, mass: MassAssumptions) -> float:
    """Return reference no-fuel mass plus the current fuel mass once."""
    return mass.reference_no_fuel_mass_kg + state.fuel_mass_kg


def evaluate_forces(
    state: MechanicsState,
    demand: DriverDemand,
    road: RoadInput,
    mass: MassAssumptions,
    geometry: CgGeometry,
    forces: EffectiveForceAssumptions,
    tyre: DryTyreCondition,
    solve_config: AxleSolveConfig,
) -> ForceEvaluation:
    """Resolve axle-aware effective tyre forces without repairing infeasibility."""
    vehicle_mass = effective_mass_kg(state, mass)
    drag = forces.drag_n_per_ms2 * state.speed_ms * abs(state.speed_ms)
    rolling = 0.0 if state.speed_ms == 0.0 else copysign(forces.rolling_resistance_n, state.speed_ms)
    front_downforce = forces.front_downforce_n_per_ms2 * state.speed_ms**2
    rear_downforce = forces.rear_downforce_n_per_ms2 * state.speed_ms**2
    lateral = vehicle_mass * state.speed_ms**2 * road.curvature_m_inv

    def resolved(load_front: float, load_rear: float) -> tuple[float, float, AxleGrip, AxleGrip]:
        front_grip = longitudinal_headroom(load_front, lateral * geometry.rear_axle_distance_m / geometry.wheelbase_m, tyre)
        rear_grip = longitudinal_headroom(load_rear, lateral * geometry.front_axle_distance_m / geometry.wheelbase_m, tyre)
        requested_drive = forces.max_drive_force_n * demand.throttle
        requested_brake = forces.max_brake_force_n * demand.brake
        requested_front = -requested_brake * demand.front_brake_share
        requested_rear = requested_drive - requested_brake * (1.0 - demand.front_brake_share)
        front_force = max(-front_grip.longitudinal_headroom_n, min(front_grip.longitudinal_headroom_n, requested_front))
        rear_force = max(-rear_grip.longitudinal_headroom_n, min(rear_grip.longitudinal_headroom_n, requested_rear))
        return front_force, rear_force, front_grip, rear_grip

    axle_loads = solve_axle_loads(
        mass_kg=vehicle_mass,
        geometry=geometry,
        front_downforce_n=front_downforce,
        rear_downforce_n=rear_downforce,
        longitudinal_force_n=lambda front, rear: sum(resolved(front, rear)[:2]) - drag - rolling,
        config=solve_config,
    )
    front_force, rear_force, front_grip, rear_grip = resolved(axle_loads.front_n, axle_loads.rear_n)
    return ForceEvaluation(front_force, rear_force, drag, rolling, lateral, axle_loads, front_grip, rear_grip)


def mechanics_derivative(
    state: MechanicsState,
    demand: DriverDemand,
    road: RoadInput,
    mass: MassAssumptions,
    geometry: CgGeometry,
    forces: EffectiveForceAssumptions,
    tyre: DryTyreCondition,
    solve_config: AxleSolveConfig,
) -> StateRate:
    """Return the pure float64-compatible motion derivative for one state."""
    evaluation = evaluate_forces(state, demand, road, mass, geometry, forces, tyre, solve_config)
    fuel_rate = -mass.fuel_policy.burn_rate_kg_s
    return StateRate(
        speed_ms2=evaluation.net_force_n / effective_mass_kg(state, mass),
        distance_ms=state.speed_ms,
        progress_ms=state.speed_ms / road.progress_ratio,
        fuel_kg_s=fuel_rate,
    )
