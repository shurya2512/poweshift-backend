"""Fit a bounded effective motion profile from admitted training telemetry."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from poweshift_backend.contracts.reconstruction import (
    DeclaredAssumption,
    EffectiveComponent,
    EffectiveProfile,
    FitReport,
    MechanicsAssumptions,
    SupportState,
)
from poweshift_backend.driver.controller import DriverDemand, DriverMode
from poweshift_backend.physics.forces import mechanics_derivative
from poweshift_backend.physics.integrate import IntegrationConfig
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
from poweshift_backend.reconstruction.inputs import Phase3Inputs, TelemetryChunk
from poweshift_backend.reconstruction.losses import mean_absolute_error
from poweshift_backend.tyres.condition import DryTyreCondition


@dataclass(frozen=True)
class BaselineRuntime:
    """The frozen shared mechanics inputs used by fitting and replay."""

    mass: MassAssumptions
    geometry: CgGeometry
    tyre: DryTyreCondition
    solve_config: AxleSolveConfig
    integration: IntegrationConfig
    forces: EffectiveForceAssumptions


@dataclass(frozen=True)
class FittedBaseline:
    """One frozen effective profile and the settings that produced it."""

    profile: EffectiveProfile
    runtime: BaselineRuntime
    settings: dict[str, object]
    diagnostics: dict[str, object]
    missing_components: tuple[str, ...]


@dataclass(frozen=True)
class _Observation:
    state: MechanicsState
    demand: DriverDemand
    acceleration_ms2: float


def fit_effective_profile(inputs: Phase3Inputs, sample_budget: int = 320, entry: str | None = None) -> FittedBaseline:
    """Fit four bounded effective terms for one entry using training chunks only."""
    entries = {chunk.entry for chunk in inputs.chunks}
    if entry is None:
        if len(entries) != 1:
            raise ValueError("an effective baseline requires one explicit entry")
        entry = next(iter(entries))
    training = _sample_observations(inputs.chunks, "training", sample_budget, entry)
    if len(training) < 4:
        raise ValueError("admitted training telemetry has too few motion observations")
    selection = _sample_observations(inputs.chunks, "selection", sample_budget, entry)
    runtime = _runtime_from_vector(_initial_vector(training))
    lower, upper, recipe = _data_bounds(training)
    observed = np.array([item.acceleration_ms2 for item in training], dtype=np.float64)

    def residuals(vector: np.ndarray) -> np.ndarray:
        candidate = _runtime_from_vector(vector)
        predicted = _accelerations(training, candidate)
        invalid = ~np.isfinite(predicted)
        if invalid.any():
            predicted[invalid] = observed[invalid] + recipe["acceleration_scale_ms2"]
        return predicted - observed

    result = least_squares(
        residuals,
        x0=np.clip(_initial_vector(training), lower, upper),
        bounds=(lower, upper),
        method="trf",
        loss="linear",
        x_scale="jac",
        max_nfev=80,
    )
    runtime = _runtime_from_vector(result.x)
    profile = _profile_from_runtime(runtime)
    selection_predicted = _accelerations(selection, runtime) if selection else np.array([], dtype=np.float64)
    selection_observed = np.array([item.acceleration_ms2 for item in selection], dtype=np.float64)
    settings = {
        "optimizer": "scipy.optimize.least_squares(method=trf, loss=linear, x_scale=jac, max_nfev=80)",
        "sample_budget": sample_budget,
        "entry": entry,
        "bound_recipe": recipe,
        "selection_policy": "selection residual is recorded after training-only fit; final evaluation is excluded",
        "illustrative_assumptions": {
            "reference_no_fuel_mass_kg": 800.0,
            "fuel_mass_kg": 30.0,
            "fuel_policy": "fixed",
            "front_axle_distance_m": 1.60,
            "rear_axle_distance_m": 1.60,
            "cg_height_m": 0.30,
            "gravity_ms2": 9.80665,
            "longitudinal_and_lateral_grip_share": "one fitted dry coefficient",
            "front_brake_share": 0.5,
            "rolling_resistance_n": 0.0,
            "front_downforce_n_per_ms2": 0.0,
            "rear_downforce_n_per_ms2": 0.0,
        },
        "integration": {
            "step_s": runtime.integration.step_s,
            "event_tie_order": list(runtime.integration.event_tie_order),
            "axle_tolerance_n": runtime.solve_config.tolerance_n,
            "axle_max_iterations": runtime.solve_config.max_iterations,
            "status": "initial numerical setting; refined-step difference is reported",
        },
    }
    diagnostics = {
        "training_observations": len(training),
        "selection_observations": len(selection),
        "training_acceleration_mae_ms2": mean_absolute_error(_accelerations(training, runtime), observed, np.ones(len(training), dtype=np.bool_)),
        "selection_acceleration_mae_ms2": mean_absolute_error(
            selection_predicted, selection_observed, np.ones(len(selection), dtype=np.bool_)
        ) if len(selection) else None,
        "optimizer_status": int(result.status),
        "optimizer_nfev": int(result.nfev),
        "active_bounds": result.active_mask.tolist(),
    }
    return FittedBaseline(
        profile=profile,
        runtime=runtime,
        settings=settings,
        diagnostics=diagnostics,
        missing_components=(
            "rolling resistance identification",
            "aerodynamic downforce identification",
            "cornering curvature for package observations",
            "grade",
            "tyre-state identification",
            "energy actuation",
        ),
    )


def build_fit_report(inputs: Phase3Inputs, baseline: FittedBaseline, settings_pin) -> FitReport:
    """Build the immutable report that binds a profile to its admitted evidence."""
    return FitReport(
        created_on=date.today(),
        input_manifest=inputs.manifest,
        profile=baseline.profile,
        settings_evidence=(settings_pin,),
        missing_components=baseline.missing_components,
        settings=baseline.settings,
        diagnostics=baseline.diagnostics,
    )


def runtime_from_profile(profile: EffectiveProfile) -> BaselineRuntime:
    """Recreate the shared runtime only from frozen profile values."""
    values = {component.name: component.value for component in profile.components}
    mass = profile.assumptions.reference_mass_kg.value
    fuel = profile.assumptions.fuel_load_kg.value
    return BaselineRuntime(
        mass=MassAssumptions(mass, True, True, True, FuelPolicy(FuelPolicyKind.FIXED)),
        geometry=CgGeometry(
            profile.assumptions.front_axle_distance_m.value,
            profile.assumptions.rear_axle_distance_m.value,
            0.30,
        ),
        tyre=DryTyreCondition(values["grip"], values["grip"]),
        solve_config=AxleSolveConfig(9.80665, 0.1, 32),
        integration=IntegrationConfig(0.04, ("chunk_boundary",)),
        forces=EffectiveForceAssumptions(values["propulsion"], values["braking"], values["resistance"], 0.0, 0.0, 0.0),
    )


def _sample_observations(chunks: tuple[TelemetryChunk, ...], split: str, budget: int, entry: str) -> list[_Observation]:
    selected = [chunk for chunk in chunks if chunk.split == split and chunk.entry == entry and len(chunk.time_s) > 1]
    if not selected:
        return []
    selected = [selected[index] for index in np.linspace(0, len(selected) - 1, min(len(selected), budget), dtype=int)]
    observations = []
    for chunk in selected:
        index = 1 + (len(chunk.time_s) - 2) // 2
        dt = chunk.time_s[index] - chunk.time_s[index - 1]
        valid = all(chunk.valid[name][index - 1] for name in ("speed_ms", "throttle_pct", "brake"))
        if not valid or dt <= 0.0:
            continue
        observations.append(
            _Observation(
                state=MechanicsState(chunk.time_s[index - 1], chunk.speed_ms[index - 1], 0.0, 0.0, 30.0),
                demand=DriverDemand(
                    throttle=float(np.clip(chunk.controls["throttle_pct"][index - 1] / 100.0, 0.0, 1.0)),
                    brake=float(np.clip(chunk.controls["brake"][index - 1], 0.0, 1.0)),
                    front_brake_share=0.5,
                    mode=DriverMode.KNOWN_INPUT,
                ),
                acceleration_ms2=float((chunk.speed_ms[index] - chunk.speed_ms[index - 1]) / dt),
            )
        )
    return observations


def _data_bounds(observations: list[_Observation]) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    acceleration = np.abs(np.array([item.acceleration_ms2 for item in observations], dtype=np.float64))
    speeds = np.array([item.state.speed_ms for item in observations], dtype=np.float64)
    acceleration_scale = float(acceleration.max())
    force_scale = 830.0 * acceleration_scale
    speed_square = float(np.square(speeds).max())
    lower = np.array([0.0, 0.0, 0.0, np.finfo(np.float64).eps], dtype=np.float64)
    upper = np.array(
        [force_scale, force_scale, force_scale / speed_square, acceleration_scale / 9.80665], dtype=np.float64
    )
    upper = np.maximum(upper, lower * 2.0)
    return lower, upper, {
        "mass_kg": 830.0,
        "acceleration_scale_ms2": acceleration_scale,
        "maximum_speed_square_m2s2": speed_square,
        "bounds": {"lower": lower.tolist(), "upper": upper.tolist()},
    }


def _initial_vector(observations: list[_Observation]) -> np.ndarray:
    _, upper, _ = _data_bounds(observations)
    return upper * 0.5


def _runtime_from_vector(vector: np.ndarray) -> BaselineRuntime:
    return BaselineRuntime(
        mass=MassAssumptions(800.0, True, True, True, FuelPolicy(FuelPolicyKind.FIXED)),
        geometry=CgGeometry(1.60, 1.60, 0.30),
        tyre=DryTyreCondition(float(vector[3]), float(vector[3])),
        solve_config=AxleSolveConfig(9.80665, 0.1, 32),
        integration=IntegrationConfig(0.04, ("chunk_boundary",)),
        forces=EffectiveForceAssumptions(float(vector[0]), float(vector[1]), float(vector[2]), 0.0, 0.0, 0.0),
    )


def _accelerations(observations: list[_Observation], runtime: BaselineRuntime) -> np.ndarray:
    values = []
    for item in observations:
        try:
            values.append(
                mechanics_derivative(
                    item.state,
                    item.demand,
                    RoadInput(0.0, 1.0),
                    runtime.mass,
                    runtime.geometry,
                    runtime.forces,
                    runtime.tyre,
                    runtime.solve_config,
                ).speed_ms2
            )
        except ValueError:
            values.append(float("nan"))
    return np.array(values, dtype=np.float64)


def _profile_from_runtime(runtime: BaselineRuntime) -> EffectiveProfile:
    assumed = SupportState.ASSUMED
    assumptions = MechanicsAssumptions(
        reference_mass_kg=DeclaredAssumption(value=800.0, unit="kg", support=assumed, source="illustrative frozen baseline assumption"),
        fuel_load_kg=DeclaredAssumption(value=30.0, unit="kg", support=assumed, source="illustrative frozen baseline assumption"),
        front_axle_distance_m=DeclaredAssumption(value=1.60, unit="m", support=assumed, source="illustrative frozen baseline assumption"),
        rear_axle_distance_m=DeclaredAssumption(value=1.60, unit="m", support=assumed, source="illustrative frozen baseline assumption"),
    )
    return EffectiveProfile(
        assumptions=assumptions,
        components=(
            EffectiveComponent(name="propulsion", value=runtime.forces.max_drive_force_n, unit="N", support=assumed),
            EffectiveComponent(name="resistance", value=runtime.forces.drag_n_per_ms2, unit="N/(m/s)^2", support=assumed),
            EffectiveComponent(name="braking", value=runtime.forces.max_brake_force_n, unit="N", support=assumed),
            EffectiveComponent(name="grip", value=runtime.tyre.longitudinal_mu, unit="1", support=assumed),
        ),
    )
