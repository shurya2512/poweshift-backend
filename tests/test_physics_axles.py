import pytest

from poweshift_backend.driver.controller import DriverDemand
from poweshift_backend.physics.forces import evaluate_forces
from poweshift_backend.physics.grip import LateralInfeasible
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


def _inputs() -> tuple:
    return (
        MassAssumptions(800.0, True, True, True, FuelPolicy(FuelPolicyKind.FIXED)),
        CgGeometry(1.6, 1.4, 0.3),
        EffectiveForceAssumptions(4000.0, 8000.0, 0.0, 0.0, 0.0, 0.0),
        DryTyreCondition(2.0, 2.0),
        AxleSolveConfig(9.81, 1e-9, 100),
    )


def test_rear_drive_moves_load_to_rear_axle() -> None:
    mass, geometry, forces, tyre, config = _inputs()
    result = evaluate_forces(
        MechanicsState(0.0, 10.0, 0.0, 0.0, 20.0),
        DriverDemand(throttle=1.0, brake=0.0, front_brake_share=0.5, mode="forecast"),
        RoadInput(0.0, 1.0),
        mass,
        geometry,
        forces,
        tyre,
        config,
    )

    assert result.front_force_n == 0.0
    assert result.rear_force_n == 4000.0
    assert result.axle_loads.rear_n > result.axle_loads.front_n


def test_excess_lateral_demand_remains_explicit() -> None:
    mass, geometry, forces, tyre, config = _inputs()
    with pytest.raises(LateralInfeasible):
        evaluate_forces(
            MechanicsState(0.0, 60.0, 0.0, 0.0, 20.0),
            DriverDemand(throttle=0.0, brake=0.0, front_brake_share=0.5, mode="forecast"),
            RoadInput(0.2, 1.0),
            mass,
            geometry,
            forces,
            tyre,
            config,
        )
