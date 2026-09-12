"""Independent adaptive integration used to check the shared derivative."""

import numpy as np
from scipy.integrate import solve_ivp

from poweshift_backend.driver.controller import DriverDemand
from poweshift_backend.physics.forces import mechanics_derivative
from poweshift_backend.physics.state import MechanicsState, RoadInput
from poweshift_backend.reconstruction.baseline import BaselineRuntime


def solve_reference(
    initial: MechanicsState, end_time_s: float, demand_at, runtime: BaselineRuntime, road: RoadInput
) -> MechanicsState:
    """Integrate the shared derivative with SciPy's independent adaptive solver."""
    def derivative(time_s: float, values: np.ndarray) -> np.ndarray:
        state = MechanicsState(time_s, values[0], values[1], values[2], values[3])
        rate = mechanics_derivative(
            state, demand_at(time_s), road, runtime.mass, runtime.geometry, runtime.forces, runtime.tyre, runtime.solve_config
        )
        return np.array([rate.speed_ms2, rate.distance_ms, rate.progress_ms, rate.fuel_kg_s], dtype=np.float64)

    solution = solve_ivp(
        derivative,
        (initial.time_s, end_time_s),
        np.array([initial.speed_ms, initial.distance_m, initial.progress_m, initial.fuel_mass_kg], dtype=np.float64),
        method="DOP853",
        rtol=1e-9,
        atol=1e-11,
        max_step=runtime.integration.step_s,
    )
    if not solution.success:
        raise ValueError(f"reference solver failed: {solution.message}")
    values = solution.y[:, -1]
    return MechanicsState(float(solution.t[-1]), float(values[0]), float(values[1]), float(values[2]), float(values[3]))
