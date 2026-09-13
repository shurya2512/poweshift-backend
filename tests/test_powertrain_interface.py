import pytest
import torch

from poweshift_backend.contracts.powertrain import (
    ElectricalPowerInput,
    EvidenceOrigin,
    PowerInput,
    PowertrainAllocation,
)
from poweshift_backend.driver.controller import DriverDemand, DriverMode
from poweshift_backend.physics.differentiable import DifferentiableMechanics
from poweshift_backend.physics.forces import evaluate_forces
from poweshift_backend.physics.state import (
    AxleSolveConfig,
    CgGeometry,
    EffectiveForceAssumptions,
    FuelPolicy,
    FuelPolicyKind,
    MassAssumptions,
    MechanicsState,
    RoadInput,
)
from poweshift_backend.tyres.condition import DryTyreCondition


def _allocation(force_n: float) -> PowertrainAllocation:
    return PowertrainAllocation(
        force_n,
        force_n,
        0.0,
        PowerInput(80_000.0, 80_000.0, EvidenceOrigin.SOURCE_DERIVED, "ice-a"),
        ElectricalPowerInput(0.0, 0.0, 0.0, EvidenceOrigin.SOURCE_DERIVED, "motor-a"),
        80_000.0,
        "bundle-a",
    )


def _force_inputs():
    return (
        MechanicsState(0.0, 20.0, 0.0, 0.0, 20.0),
        RoadInput(0.0, 1.0),
        MassAssumptions(800.0, True, True, True, FuelPolicy(FuelPolicyKind.FIXED)),
        CgGeometry(1.6, 1.4, 0.3),
        EffectiveForceAssumptions(4_000.0, 8_000.0, 0.0, 0.0, 0.0, 0.0),
        DryTyreCondition(2.0, 2.0),
        AxleSolveConfig(9.81, 0.1, 32),
    )


def test_allocated_force_replaces_effective_propulsion() -> None:
    state, road, mass, geometry, forces, tyre, solve = _force_inputs()
    demand = DriverDemand(0.0, 0.0, 0.5, DriverMode.KNOWN_INPUT)

    result = evaluate_forces(state, demand, road, mass, geometry, forces, tyre, solve, _allocation(1_500.0))

    assert result.rear_force_n == pytest.approx(1_500.0)
    with pytest.raises(ValueError, match="exclusive"):
        evaluate_forces(
            state,
            DriverDemand(0.2, 0.0, 0.5, DriverMode.KNOWN_INPUT),
            road,
            mass,
            geometry,
            forces,
            tyre,
            solve,
            _allocation(1_500.0),
        )


def test_differentiable_allocation_replaces_profile_drive_force() -> None:
    engine = DifferentiableMechanics(
        reference_no_fuel_mass_kg=800.0,
        fuel_burn_rate_kg_s=0.0,
        front_axle_distance_m=1.6,
        rear_axle_distance_m=1.4,
        cg_height_m=0.3,
        gravity_ms2=9.81,
        axle_tolerance_n=0.1,
        axle_max_iterations=32,
        step_s=0.04,
    )
    state = torch.tensor([20.0, 0.0, 0.0, 20.0], dtype=torch.float64)
    controls = torch.tensor([0.0, 0.0], dtype=torch.float64)
    road = torch.tensor([0.0, 1.0], dtype=torch.float64)
    profile = torch.tensor([4_000.0, 8_000.0, 0.0, 0.0, 0.0, 0.0, 2.0, 2.0], dtype=torch.float64)

    allocated = engine.derivative(
        state,
        controls,
        road,
        profile,
        allocated_axle_force_n=torch.tensor(1_500.0, dtype=torch.float64),
    )
    effective = engine.derivative(state, torch.tensor([0.375, 0.0], dtype=torch.float64), road, profile)

    assert allocated == pytest.approx(effective)
    with pytest.raises(ValueError, match="exclusive"):
        engine.derivative(
            state,
            torch.tensor([0.2, 0.0], dtype=torch.float64),
            road,
            profile,
            allocated_axle_force_n=torch.tensor(1_500.0, dtype=torch.float64),
        )
