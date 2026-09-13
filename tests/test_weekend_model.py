import pytest
import torch

from poweshift_backend.contracts.representation import NumericalPolicy
from poweshift_backend.physics.differentiable import DifferentiableMechanics
from poweshift_backend.physics.integrate import IntegrationConfig
from poweshift_backend.physics.state import AxleSolveConfig, CgGeometry, EffectiveForceAssumptions, FuelPolicy, FuelPolicyKind, MassAssumptions
from poweshift_backend.reconstruction.baseline import BaselineRuntime
from poweshift_backend.reconstruction.weekend_losses import WeekendPairInputs, weekend_pair_objective
from poweshift_backend.representation.weekend_model import WeekendModelConfig, WeekendTelemetryModel
from poweshift_backend.tyres.condition import DryTyreCondition


LOWER = (3800.0, 7600.0, 0.5, 80.0, 0.03, 0.04, 1.8, 1.8)
UPPER = (4200.0, 8400.0, 0.7, 120.0, 0.05, 0.06, 2.2, 2.2)


def _model() -> WeekendTelemetryModel:
    return WeekendTelemetryModel(WeekendModelConfig(feature_width=4, parameter_lower=LOWER, parameter_upper=UPPER)).double()


def _runtime() -> BaselineRuntime:
    return BaselineRuntime(
        mass=MassAssumptions(800.0, True, True, True, FuelPolicy(FuelPolicyKind.LINEAR_BURN, 0.02)),
        geometry=CgGeometry(1.6, 1.4, 0.3),
        tyre=DryTyreCondition(2.0, 2.0),
        solve_config=AxleSolveConfig(9.81, 1e-10, 32),
        integration=IntegrationConfig(0.02, ()),
        forces=EffectiveForceAssumptions(4000.0, 8000.0, 0.6, 100.0, 0.04, 0.05),
        numerical_policy=NumericalPolicy(step_s=0.02, axle_tolerance_n=1e-10, event_time_tolerance_s=1e-12, axle_max_iterations=32),
    )


def test_model_decodes_one_frozen_bounded_profile_and_uncertainty_per_car() -> None:
    model = _model()
    output = model(torch.linspace(-1.0, 1.0, 60, dtype=torch.float64).reshape(3, 5, 4))

    assert output.latent.shape == (3, 16)
    assert output.parameters.shape == (3, 8)
    assert output.uncertainty.shape == (3,)
    assert torch.all(output.parameters >= torch.tensor(LOWER, dtype=torch.float64))
    assert torch.all(output.parameters <= torch.tensor(UPPER, dtype=torch.float64))


def test_model_refuses_invalid_frozen_bounds_and_feature_shape() -> None:
    with pytest.raises(ValueError, match="bounds"):
        WeekendModelConfig(feature_width=4, parameter_lower=LOWER, parameter_upper=LOWER)

    with pytest.raises(ValueError, match=r"\[car, sample, feature\]"):
        _model()(torch.ones((3, 4), dtype=torch.float64))


def test_model_uses_float64_mechanics_bounds_and_rejects_nonphysical_configurations() -> None:
    model = WeekendTelemetryModel(WeekendModelConfig(feature_width=4, parameter_lower=LOWER, parameter_upper=UPPER))

    assert model.parameter_lower.dtype is torch.float64
    assert model(torch.ones((2, 3, 4), dtype=torch.float64)).parameters.dtype is torch.float64
    with pytest.raises(ValueError, match="integer"):
        WeekendModelConfig(feature_width=True, parameter_lower=LOWER, parameter_upper=UPPER)
    with pytest.raises(ValueError, match="physics support"):
        WeekendModelConfig(feature_width=4, parameter_lower=(0.0,) * 8, parameter_upper=UPPER)


def test_model_can_start_from_a_frozen_physical_profile_inside_broad_bounds() -> None:
    seed = (4000.0, 8000.0, 0.6, 100.0, 0.04, 0.05, 2.0, 2.0)
    model = WeekendTelemetryModel(WeekendModelConfig(feature_width=4, parameter_lower=LOWER, parameter_upper=UPPER, initial_parameter_seed=seed))

    output = model(torch.zeros((2, 3, 4), dtype=torch.float64))

    assert torch.allclose(output.parameters, torch.tensor([seed, seed], dtype=torch.float64), rtol=0.03)


def test_unit_only_analytical_fixture_backpropagates_through_the_shared_physics_path() -> None:
    model = _model()
    output = model(torch.tensor([[[0.2, 0.0, 24.0, 25.0]] * 3, [[0.3, 0.0, 22.0, 24.0]] * 3], dtype=torch.float64))
    engine = DifferentiableMechanics.from_runtime(_runtime())
    times = torch.tensor([0.0, 0.25, 0.5], dtype=torch.float64)
    trajectory = engine.integrate(
        torch.tensor([[24.0, 0.0, 0.0, 25.0], [22.0, 0.0, 0.0, 24.0]], dtype=torch.float64),
        times,
        lambda _: torch.tensor([[0.2, 0.0], [0.3, 0.0]], dtype=torch.float64),
        lambda _: torch.tensor([[0.001, 1.0], [0.001, 1.0]], dtype=torch.float64),
        output.parameters,
    )
    progress = trajectory[..., 2].unsqueeze(0)
    crossings = ((5.0 - trajectory[0, :, 2]) / (trajectory[-1, :, 2] - trajectory[0, :, 2]) * times[-1]).view(1, 2, 1)
    pair = torch.tensor([[[[False, True], [False, False]]]])
    inputs = WeekendPairInputs(progress, crossings, progress.detach(), crossings.detach() + torch.tensor([[[0.01], [-0.01]]]), pair, pair.repeat(1, 3, 1, 1), output.uncertainty.unsqueeze(0))

    weekend_pair_objective(inputs, timing_scale=1.0, progress_scale=1.0).loss.backward()

    assert model.input.weight.grad is not None
    assert model.input.weight.grad.abs().sum() > 0.0
