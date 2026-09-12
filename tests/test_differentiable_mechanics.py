import pytest
import torch

from poweshift_backend.contracts.representation import NumericalPolicy
from poweshift_backend.driver.controller import DriverDemand, DriverMode
from poweshift_backend.physics.differentiable import (
    PARAMETER_NAMES,
    DifferentiableMechanics,
    MechanicsUnsupported,
    StaticRoadLookup,
    normalized_jvp_error,
    normalized_state_error,
)
from poweshift_backend.physics.integrate import IntegrationConfig, integrate
from poweshift_backend.physics.reference_solver import solve_reference
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
from poweshift_backend.reconstruction.baseline import BaselineRuntime
from poweshift_backend.tyres.condition import DryTyreCondition


def _runtime(max_drive_force_n: float = 4000.0, step_s: float = 0.02) -> BaselineRuntime:
    return BaselineRuntime(
        mass=MassAssumptions(800.0, True, True, True, FuelPolicy(FuelPolicyKind.LINEAR_BURN, 0.02)),
        geometry=CgGeometry(1.6, 1.4, 0.3),
        tyre=DryTyreCondition(2.0, 2.0),
        solve_config=AxleSolveConfig(9.81, 1e-10, 32),
        integration=IntegrationConfig(step_s, ()),
        forces=EffectiveForceAssumptions(max_drive_force_n, 8000.0, 0.6, 100.0, 0.04, 0.05),
        numerical_policy=NumericalPolicy(
            step_s=step_s,
            axle_tolerance_n=1e-10,
            event_time_tolerance_s=1e-12,
            axle_max_iterations=32,
        ),
    )


def _profile() -> torch.Tensor:
    return torch.tensor([4000.0, 8000.0, 0.6, 100.0, 0.04, 0.05, 2.0, 2.0], dtype=torch.float64)


def _controls(_: torch.Tensor) -> torch.Tensor:
    return torch.tensor([0.35, 0.0], dtype=torch.float64)


def _road(_: torch.Tensor) -> torch.Tensor:
    return torch.tensor([0.001, 1.0], dtype=torch.float64)


@pytest.mark.parametrize(
    ("name", "value"),
    (("gravity_ms2", float("nan")), ("front_brake_share", float("inf")), ("axle_max_iterations", 32.5), ("axle_max_iterations", True)),
)
def test_constructor_rejects_nonfinite_constants_and_noninteger_iterations(name: str, value: float | bool) -> None:
    constants: dict[str, float | int | bool] = {
        "reference_no_fuel_mass_kg": 800.0,
        "fuel_burn_rate_kg_s": 0.02,
        "front_axle_distance_m": 1.6,
        "rear_axle_distance_m": 1.4,
        "cg_height_m": 0.3,
        "gravity_ms2": 9.81,
        "axle_tolerance_n": 0.1,
        "axle_max_iterations": 32,
        "step_s": 0.04,
        "front_brake_share": 0.5,
    }
    constants[name] = value

    with pytest.raises(ValueError, match="finite|integer"):
        DifferentiableMechanics(**constants)


def test_parameter_order_is_fixed_and_tensor_derivative_matches_canonical() -> None:
    runtime = _runtime()
    engine = DifferentiableMechanics.from_runtime(runtime, front_brake_share=0.5)
    state = torch.tensor([24.0, 5.0, 0.001, 25.0], dtype=torch.float64)

    rate = engine.derivative(state, _controls(torch.tensor(0.0)), _road(state[2]), _profile())
    canonical = engine.canonical_derivative(
        MechanicsState(0.0, 24.0, 5.0, 0.001, 25.0),
        DriverDemand(0.35, 0.0, 0.5, DriverMode.KNOWN_INPUT),
        RoadInput(0.001, 1.0),
    )

    assert PARAMETER_NAMES == (
        "max_drive_force_n",
        "max_brake_force_n",
        "drag_n_per_ms2",
        "rolling_resistance_n",
        "front_downforce_n_per_ms2",
        "rear_downforce_n_per_ms2",
        "longitudinal_mu",
        "lateral_mu",
    )
    assert rate.detach().numpy() == pytest.approx(
        [canonical.speed_ms2, canonical.distance_ms, canonical.progress_ms, canonical.fuel_kg_s], rel=1e-10
    )


def test_rk4_matches_independent_reference_on_smooth_supported_interval() -> None:
    runtime = _runtime()
    engine = DifferentiableMechanics.from_runtime(runtime, front_brake_share=0.5)
    times = torch.linspace(0.0, 1.0, 51, dtype=torch.float64)
    initial = torch.tensor([24.0, 5.0, 0.001, 25.0], dtype=torch.float64)

    trajectory = engine.integrate(initial, times, _controls, _road, _profile())
    canonical = integrate(
        MechanicsState(0.0, 24.0, 5.0, 0.001, 25.0),
        1.0,
        lambda state: engine.canonical_derivative(
            state,
            DriverDemand(0.35, 0.0, 0.5, DriverMode.KNOWN_INPUT),
            RoadInput(0.001, 1.0),
        ),
        runtime.integration,
    )[-1]
    reference = solve_reference(
        MechanicsState(0.0, 24.0, 5.0, 0.001, 25.0),
        1.0,
        lambda _: DriverDemand(0.35, 0.0, 0.5, DriverMode.KNOWN_INPUT),
        runtime,
        RoadInput(0.001, 1.0),
    )

    assert trajectory[-1].detach().numpy() == pytest.approx(
        [canonical.speed_ms, canonical.distance_m, canonical.progress_m, canonical.fuel_mass_kg], rel=1e-8
    )
    assert trajectory[-1].detach().numpy() == pytest.approx(
        [reference.speed_ms, reference.distance_m, reference.progress_m, reference.fuel_mass_kg], rel=2e-5
    )


def test_jvp_matches_central_difference_per_terminal_state() -> None:
    engine = DifferentiableMechanics.from_runtime(_runtime(), front_brake_share=0.5)
    initial = torch.tensor([24.0, 5.0, 0.001, 25.0], dtype=torch.float64)
    times = torch.linspace(0.0, 0.2, 11, dtype=torch.float64)
    normalized = engine.normalize_profile(_profile())

    def terminal(values: torch.Tensor) -> torch.Tensor:
        return engine.integrate(initial, times, _controls, _road, engine.denormalize_profile(values))[-1]

    for index in range(len(PARAMETER_NAMES)):
        tangent = torch.zeros_like(normalized)
        tangent[index] = 1.0
        _, jvp = torch.func.jvp(terminal, (normalized,), (tangent,))
        finite_difference = (
            terminal(normalized + 1e-4 * tangent) - terminal(normalized - 1e-4 * tangent)
        ) / 2e-4
        errors = normalized_jvp_error(jvp, finite_difference)

        for relative, absolute in zip(errors.relative, errors.absolute, strict=True):
            assert relative <= 0.05
            if absolute is not None:
                assert absolute <= 5e-8


def test_axle_solver_stops_after_the_first_all_car_convergence(monkeypatch) -> None:
    engine = DifferentiableMechanics.from_runtime(_runtime(), front_brake_share=0.5)
    states = torch.tensor([[24.0, 5.0, 0.001, 25.0], [22.0, 4.0, 0.001, 24.0]], dtype=torch.float64)
    profiles = torch.stack((_profile(), _profile()))
    controls = torch.tensor([[0.35, 0.0], [0.30, 0.0]], dtype=torch.float64)
    road = torch.tensor([[0.001, 1.0], [0.001, 1.0]], dtype=torch.float64)

    calls = 0
    original = engine._all

    def count(value: torch.Tensor) -> bool:
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(engine, "_all", count)
    evaluation = engine._evaluate(states, controls, road, profiles)

    assert torch.all(evaluation.converged)
    assert int(evaluation.iterations.max()) < engine.axle_max_iterations
    assert calls == int(evaluation.iterations.max())


def test_batched_field_returns_one_time_car_state_tensor() -> None:
    engine = DifferentiableMechanics.from_runtime(_runtime(), front_brake_share=0.5)
    initial = torch.tensor([[24.0, 5.0, 0.001, 25.0], [22.0, 4.0, 0.001, 24.0]], dtype=torch.float64)
    times = torch.tensor([0.0, 0.25, 0.5], dtype=torch.float64)
    profiles = torch.stack((_profile(), _profile() * torch.tensor([1.0, 1.0, 1.1, 1.0, 1.0, 1.0, 1.0, 1.0])))

    trajectory = engine.integrate(
        initial,
        times,
        lambda _: torch.tensor([[0.35, 0.0], [0.30, 0.0]], dtype=torch.float64),
        lambda _: torch.tensor([[0.001, 1.0], [0.001, 1.0]], dtype=torch.float64),
        profiles,
    )

    assert trajectory.shape == (3, 2, 4)
    assert torch.isfinite(trajectory).all()
    assert not torch.equal(trajectory[-1, 0], trajectory[-1, 1])


def test_checkpointed_blocks_match_values_and_parameter_gradients() -> None:
    engine = DifferentiableMechanics.from_runtime(_runtime(), front_brake_share=0.5)
    initial = torch.tensor([24.0, 5.0, 0.001, 25.0], dtype=torch.float64)
    times = torch.tensor([0.0, 0.25, 0.5, 0.75], dtype=torch.float64)
    direct_profile = _profile().requires_grad_()
    direct = engine.integrate(initial, times, _controls, _road, direct_profile)
    direct[-1].sum().backward()
    direct_gradient = direct_profile.grad.detach().clone()
    checkpointed_profile = _profile().requires_grad_()

    checkpointed = engine.integrate(
        initial,
        times,
        _controls,
        _road,
        checkpointed_profile,
        checkpoint_observations=1,
    )
    checkpointed[-1].sum().backward()

    assert checkpointed.detach().numpy() == pytest.approx(direct.detach().numpy(), rel=1e-12, abs=1e-12)
    assert checkpointed_profile.grad.detach().numpy() == pytest.approx(direct_gradient.numpy(), rel=1e-12, abs=1e-12)


def test_clipped_force_matches_canonical_and_gradient_events_refuse() -> None:
    runtime = _runtime(max_drive_force_n=30000.0)
    engine = DifferentiableMechanics.from_runtime(runtime, front_brake_share=0.5)
    state = torch.tensor([30.0, 5.0, 0.001, 25.0], dtype=torch.float64)
    profile = _profile().clone()
    profile[0] = 30000.0

    rate = engine.derivative(state, _controls(torch.tensor(0.0)), _road(state[2]), profile)
    canonical = engine.canonical_derivative(
        MechanicsState(0.0, 30.0, 5.0, 0.001, 25.0),
        DriverDemand(0.35, 0.0, 0.5, DriverMode.KNOWN_INPUT),
        RoadInput(0.001, 1.0),
    )

    assert rate.detach().numpy() == pytest.approx(
        [canonical.speed_ms2, canonical.distance_ms, canonical.progress_ms, canonical.fuel_kg_s], rel=1e-10
    )
    with pytest.raises(MechanicsUnsupported, match="event"):
        engine.assert_gradient_supported(state, _controls(torch.tensor(0.0)), _road(state[2]), profile, event_times=(0.1,))


def test_unsaturated_parameter_interventions_keep_the_expected_direction() -> None:
    engine = DifferentiableMechanics.from_runtime(_runtime(), front_brake_share=0.5)
    initial = torch.tensor([24.0, 5.0, 0.001, 25.0], dtype=torch.float64)
    times = torch.tensor([0.0, 0.25], dtype=torch.float64)
    baseline = engine.integrate(initial, times, _controls, _road, _profile())[-1]
    increased_drive = _profile().clone()
    increased_drive[0] *= 1.01
    increased_drag = _profile().clone()
    increased_drag[2] *= 1.01

    driven = engine.integrate(initial, times, _controls, _road, increased_drive)[-1]
    dragged = engine.integrate(initial, times, _controls, _road, increased_drag)[-1]

    assert driven[0] >= baseline[0]
    assert driven[2] >= baseline[2]
    assert dragged[0] <= baseline[0]
    assert dragged[2] <= baseline[2]


def test_refinement_and_static_predicted_progress_lookup_are_declared() -> None:
    coarse = DifferentiableMechanics.from_runtime(_runtime(step_s=0.02), front_brake_share=0.5)
    refined = DifferentiableMechanics.from_runtime(_runtime(step_s=0.01), front_brake_share=0.5)
    initial = torch.tensor([24.0, 5.0, 0.001, 25.0], dtype=torch.float64)
    times = torch.tensor([0.0, 0.25, 0.5], dtype=torch.float64)
    lookup = StaticRoadLookup(
        torch.tensor([0.0, 10.0, 20.0], dtype=torch.float64),
        torch.tensor([0.0, 0.001, 0.002], dtype=torch.float64),
    )

    lookup_values = lookup(torch.tensor([5.0, 15.0], dtype=torch.float64))
    coarse_end = coarse.integrate(initial, times, _controls, _road, _profile())[-1]
    refined_end = refined.integrate(initial, times, _controls, _road, _profile())[-1]

    assert lookup_values.numpy().reshape(-1) == pytest.approx([0.0005, 1.0, 0.0015, 1.0])
    assert all(error <= 0.05 for error in normalized_state_error(coarse_end, refined_end))
    with pytest.raises(MechanicsUnsupported, match="outside"):
        lookup(torch.tensor([21.0], dtype=torch.float64))


def test_refuses_non_float64_and_gradient_boundaries() -> None:
    engine = DifferentiableMechanics.from_runtime(_runtime(), front_brake_share=0.5)
    state = torch.tensor([24.0, 5.0, 0.001, 25.0], dtype=torch.float64)

    with pytest.raises(MechanicsUnsupported, match="float64"):
        engine.derivative(state.float(), _controls(torch.tensor(0.0)), _road(state[2]), _profile())
    with pytest.raises(MechanicsUnsupported, match="lateral"):
        engine.assert_gradient_supported(
            state,
            _controls(torch.tensor(0.0)),
            torch.tensor([0.5, 1.0], dtype=torch.float64),
            _profile(),
        )
    with pytest.raises(MechanicsUnsupported, match="lateral"):
        engine.derivative(
            state,
            _controls(torch.tensor(0.0)),
            torch.tensor([0.5, 1.0], dtype=torch.float64),
            _profile(),
        )


def test_single_timestamp_trajectory_validates_its_initial_state() -> None:
    engine = DifferentiableMechanics.from_runtime(_runtime(), front_brake_share=0.5)
    initial = torch.tensor([float("nan"), 5.0, 0.001, 25.0], dtype=torch.float64)

    with pytest.raises(MechanicsUnsupported, match="finite"):
        engine.integrate(initial, torch.tensor([0.0], dtype=torch.float64), _controls, _road, _profile())


@pytest.mark.parametrize("axle_tolerance_n", (1e-10, 0.1))
def test_bounded_axle_root_resolves_real_braking_oscillation_and_gradients(axle_tolerance_n: float) -> None:
    from dataclasses import replace

    profile = torch.tensor([
        7938.689040545336, 16264.588241629379, 0.7964728696077152,
        89.4437240867762, 2.0614553700689866, 2.142419369523459,
        2.196685932730405, 2.1710405780556115,
    ], dtype=torch.float64)
    runtime = replace(
        _runtime(),
        forces=EffectiveForceAssumptions(*profile[:6].tolist()),
        tyre=DryTyreCondition(*profile[6:].tolist()),
        solve_config=AxleSolveConfig(9.81, axle_tolerance_n, 32),
    )
    engine = DifferentiableMechanics.from_runtime(runtime)
    state = torch.tensor([74.04912099566046, 336.72657461621367, 334.3181790225797, 24.919599999999846], dtype=torch.float64)
    controls = torch.tensor([0.35915789473684234, 1.0], dtype=torch.float64)
    road = torch.tensor([-0.013096567858059927, 1.0], dtype=torch.float64)
    rate = engine.derivative(state, controls, road, profile)
    canonical = engine.canonical_derivative(
        MechanicsState(4.02, *state.tolist()),
        DriverDemand(*controls.tolist(), 0.5, DriverMode.KNOWN_INPUT),
        RoadInput(*road.tolist()),
    )
    acceleration_tolerance = axle_tolerance_n / ((800.0 + state[3].item()) * 0.1)
    assert rate[0].item() == pytest.approx(-17.905218203138126, abs=max(1e-9, acceleration_tolerance))
    assert rate[0].item() == pytest.approx(canonical.speed_ms2, abs=1e-10)
    with pytest.raises(MechanicsUnsupported, match="too near"):
        engine.assert_gradient_supported(state, controls, road, profile)
    normalized = engine.normalize_profile(profile).requires_grad_()

    def acceleration(values):
        return engine.derivative(state, controls, road, engine.denormalize_profile(values))[0]

    gradient = torch.autograd.grad(acceleration(normalized), normalized)[0]
    for index in range(8):
        tangent = torch.zeros_like(normalized)
        tangent[index] = 1.0
        _, jvp = torch.func.jvp(acceleration, (normalized,), (tangent,))
        fd = (acceleration(normalized + 1e-4 * tangent) - acceleration(normalized - 1e-4 * tangent)) / 2e-4
        assert jvp.item() == pytest.approx(fd.item(), rel=0.05, abs=5e-8)
        assert gradient[index].item() == pytest.approx(jvp.item(), rel=1e-8, abs=5e-8)

    with pytest.raises(MechanicsUnsupported):
        engine.derivative(state, controls, road * 2, profile)

    state[0] = 73.76513271661628
    state[3] = 24.919199999999844
    controls[0] = 0.34652631578947385
    road[0] = -0.0138434765566316
    with pytest.raises(MechanicsUnsupported, match="not bracketed"):
        engine.derivative(state, controls, road, profile)
    with pytest.raises(ValueError, match="not bracketed"):
        engine.canonical_derivative(
            MechanicsState(4.04, *state.tolist()),
            DriverDemand(*controls.tolist(), 0.5, DriverMode.KNOWN_INPUT),
            RoadInput(*road.tolist()),
        )


def test_bounded_axle_root_keeps_state_control_and_road_gradients() -> None:
    engine = DifferentiableMechanics.from_runtime(_runtime(max_drive_force_n=30000.0))
    profile = _profile().clone()
    profile[0] = 30000.0
    inputs = torch.tensor([30.0, 5.0, 0.001, 25.0, 0.7, 0.1, 0.001, 1.0], dtype=torch.float64, requires_grad=True)

    def rate(values):
        return engine.derivative(values[:4], values[4:6], values[6:], profile)

    jacobian = torch.autograd.functional.jacobian(rate, inputs)
    for index in range(len(inputs)):
        tangent = torch.zeros_like(inputs)
        tangent[index] = 1.0
        _, jvp = torch.func.jvp(rate, (inputs,), (tangent,))
        fd = (rate(inputs + 1e-7 * tangent) - rate(inputs - 1e-7 * tangent)) / 2e-7
        torch.testing.assert_close(jvp, fd, rtol=0.05, atol=5e-8)
        torch.testing.assert_close(jacobian[:, index], jvp, rtol=1e-8, atol=5e-8)


@pytest.mark.parametrize("allocated_force_n", (2000.0, 30000.0))
def test_bounded_axle_root_preserves_allocated_force_gradient(allocated_force_n: float) -> None:
    engine = DifferentiableMechanics.from_runtime(_runtime())
    state = torch.tensor([30.0, 5.0, 0.001, 25.0], dtype=torch.float64)
    controls = torch.tensor([0.0, 0.1], dtype=torch.float64)
    allocation = torch.tensor(allocated_force_n, dtype=torch.float64, requires_grad=True)

    def rate(force):
        return engine.derivative(state, controls, _road(state[2]), _profile(), allocated_axle_force_n=force)[0]

    gradient = torch.autograd.grad(rate(allocation), allocation)[0]
    _, jvp = torch.func.jvp(rate, (allocation,), (torch.ones_like(allocation),))
    fd = (rate(allocation + 1e-3) - rate(allocation - 1e-3)) / 2e-3
    torch.testing.assert_close(jvp, fd, rtol=0.05, atol=5e-8)
    torch.testing.assert_close(gradient, jvp, rtol=1e-8, atol=5e-8)


def test_bounded_axle_root_refuses_partial_field_convergence_at_cap() -> None:
    engine = DifferentiableMechanics.from_runtime(_runtime())
    engine.axle_max_iterations = 1
    states = torch.tensor([[30.0, 5.0, 0.001, 25.0]] * 2, dtype=torch.float64)
    controls = torch.tensor([[0.0, 0.0], [0.7, 0.1]], dtype=torch.float64)
    profiles = torch.stack((_profile(), _profile()))
    profiles[0, 2:4] = 0.0
    roads = torch.tensor([[0.001, 1.0]] * 2, dtype=torch.float64)
    evaluation = engine._evaluate(states, controls, roads, profiles)
    assert evaluation.converged.tolist() == [True, False]
    with pytest.raises(MechanicsUnsupported, match="did not converge"):
        engine.derivative(states, controls, roads, profiles)
