import pytest
import torch

from poweshift_backend.contracts.representation import NumericalPolicy
from poweshift_backend.physics.differentiable import DifferentiableMechanics
from poweshift_backend.physics.integrate import IntegrationConfig
from poweshift_backend.physics.state import AxleSolveConfig, CgGeometry, EffectiveForceAssumptions, FuelPolicy, FuelPolicyKind, MassAssumptions
from poweshift_backend.reconstruction.baseline import BaselineRuntime
from poweshift_backend.representation.weekend_model import WeekendModelConfig, WeekendTelemetryModel
from poweshift_backend.representation.weekend_training import WeekendTrajectoryBatch, run_smoke, save_smoke_checkpoint, train_trajectory
from poweshift_backend.tyres.condition import DryTyreCondition


def _engine() -> DifferentiableMechanics:
    runtime = BaselineRuntime(
        MassAssumptions(800.0, True, True, True, FuelPolicy(FuelPolicyKind.LINEAR_BURN, 0.02)), CgGeometry(1.6, 1.4, 0.3), DryTyreCondition(2.0, 2.0),
        AxleSolveConfig(9.81, 1e-10, 32), IntegrationConfig(0.02, ()), EffectiveForceAssumptions(4000.0, 8000.0, 0.6, 100.0, 0.04, 0.05),
        NumericalPolicy(step_s=0.02, axle_tolerance_n=1e-10, event_time_tolerance_s=1e-12, axle_max_iterations=32),
    )
    return DifferentiableMechanics.from_runtime(runtime)


def _batch(checkpoint: float = 5.0) -> WeekendTrajectoryBatch:
    pair = torch.tensor([[[False, True], [False, False]]])
    return WeekendTrajectoryBatch(
        features=torch.tensor([[[0.2, 0.0, 24.0, 25.0]] * 3, [[0.3, 0.0, 22.0, 24.0]] * 3], dtype=torch.float64),
        initial_state=torch.tensor([[24.0, 0.0, 0.0, 25.0], [22.0, 0.0, 0.0, 24.0]], dtype=torch.float64),
        observation_times_s=torch.tensor([0.0, 0.25, 0.5], dtype=torch.float64),
        control_times_s=torch.tensor([0.0, 0.25, 0.5], dtype=torch.float64),
        controls=torch.tensor([[[0.2, 0.0], [0.3, 0.0]]] * 3, dtype=torch.float64),
        control_inferred_mask=torch.zeros((3, 2), dtype=torch.bool),
        control_bracket_span_s=torch.zeros((3, 2), dtype=torch.float64),
        road_progress_m=torch.tensor([0.0, 10.0, 20.0], dtype=torch.float64),
        road_curvature_m_inv=torch.tensor([0.001, 0.001, 0.001], dtype=torch.float64),
        observed_progress=torch.tensor([[0.0, 0.0], [6.0, 5.5], [12.0, 11.0]], dtype=torch.float64),
        observed_crossings=torch.tensor([[0.21], [0.23]], dtype=torch.float64),
        checkpoint_progress_m=torch.tensor([checkpoint], dtype=torch.float64),
        timing_pair_mask=pair,
        progress_pair_mask=torch.zeros((3, 2, 2), dtype=torch.bool),
        timing_scale=1.0,
        progress_scale=1.0,
        source_partition="training",
        source_hash="unit-only",
        cutoff_s=0.5,
        control_clock_kind="source_union",
        control_interpolation="linear_source_bracket",
        logical_batch_id="unit-q1-lap1",
        source_context="Q1 lap 1",
    )


def _model() -> WeekendTelemetryModel:
    return WeekendTelemetryModel(WeekendModelConfig(4, (3800.0, 7600.0, 0.5, 80.0, 0.03, 0.04, 1.8, 1.8), (4200.0, 8400.0, 0.7, 120.0, 0.05, 0.06, 2.2, 2.2)))


def test_train_step_updates_one_joint_trajectory_within_the_cap(tmp_path) -> None:
    model = _model()
    before = model.input.weight.detach().clone()
    record = train_trajectory(model, _engine(), torch.optim.SGD(model.parameters(), lr=1e-4), _batch(), updates=1)

    assert record.updates == 1
    assert torch.isfinite(torch.tensor(record.losses)).all()
    assert not torch.equal(before, model.input.weight)
    assert model.uncertainty_decoder.weight.grad is not None
    assert model.uncertainty_decoder.weight.grad.abs().sum() > 0.0
    save_smoke_checkpoint(tmp_path / "checkpoint.pt", model, (record,))


def test_train_step_refuses_more_than_one_update_or_missing_required_crossings() -> None:
    model = _model()
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-4)

    with pytest.raises(ValueError, match="one update"):
        train_trajectory(model, _engine(), optimizer, _batch(), updates=2)
    with pytest.raises(ValueError, match="checkpoint"):
        train_trajectory(model, _engine(), optimizer, _batch(checkpoint=-1.0), updates=1)
    with pytest.raises(ValueError, match="one update per batch"):
        run_smoke(model, _engine(), optimizer, (_batch(),), total_updates=2)


def test_smoke_uses_each_shuffled_batch_once() -> None:
    model = _model()
    batches = tuple(
        WeekendTrajectoryBatch(**{**_batch().__dict__, "logical_batch_id": f"batch-{index}"})
        for index in range(3)
    )

    records = run_smoke(
        model,
        _engine(),
        torch.optim.SGD(model.parameters(), lr=1e-4),
        batches,
        total_updates=3,
        seed=7,
    )

    assert len(records) == 3
    assert all(record.updates == 1 for record in records)
    assert {record.logical_batch_id for record in records} == {"batch-0", "batch-1", "batch-2"}
