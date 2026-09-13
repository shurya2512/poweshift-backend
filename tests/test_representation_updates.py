import numpy as np
import pytest
import torch

from poweshift_backend.contracts.representation import ComparisonPolicy, NumericalPolicy
from poweshift_backend.representation.inputs import UpdateUnit
from poweshift_backend.representation.models import CandidateConfig
from poweshift_backend.representation import training
from poweshift_backend.representation.training import TeacherProfile, policy_identifier, train_distilled_candidate


def _unit(split: str) -> UpdateUnit:
    return UpdateUnit(
        entry="1", session_key="test", run_id=split, split=split, completed_cutoff_s=1.0,
        features=np.array([[1.0, 2.0], [2.0, 3.0]], dtype=np.float32),
        valid=np.ones((2, 2), dtype=np.bool_), padding=np.array([False, False], dtype=np.bool_),
    )


def _policy() -> ComparisonPolicy:
    return ComparisonPolicy(
        numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12),
        metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation",
        per_update_refit_budget=1, candidate_epochs=2,
    )


def test_training_uses_only_training_teacher_profiles_and_persists_the_transform() -> None:
    torch.manual_seed(3)
    result = train_distilled_candidate(
        "gru", CandidateConfig(feature_width=2, latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16),
        (TeacherProfile(_unit("training"), np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32), "a" * 64, "b" * 64, policy_identifier(_policy()), 1.0, np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32), np.ones(4, dtype=np.float32)),),
        _policy(),
        feature_names=("speed_ms", "throttle_pct"), policy_id=policy_identifier(_policy()),
    )

    assert result.model_record.transform_id == result.transform.identifier
    assert result.model_record.policy_id == policy_identifier(_policy())
    assert len(result.losses) == 2


def test_training_refuses_a_teacher_from_selection_or_final_evaluation() -> None:
    with pytest.raises(ValueError, match="training"):
        train_distilled_candidate(
            "gru", CandidateConfig(feature_width=2, latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16),
            (TeacherProfile(_unit("selection"), np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32), "a" * 64, "b" * 64, policy_identifier(_policy()), 1.0, np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32), np.ones(4, dtype=np.float32)),),
            _policy(), feature_names=("speed_ms", "throttle_pct"), policy_id=policy_identifier(_policy()),
        )


def test_training_refuses_to_report_a_candidate_outside_its_runtime_budget() -> None:
    policy = _policy().model_copy(update={"candidate_runtime_budget_s": 1e-12})
    with pytest.raises(ValueError, match="runtime"):
        train_distilled_candidate(
            "gru", CandidateConfig(feature_width=2, latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16),
            (TeacherProfile(_unit("training"), np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32), "a" * 64, "b" * 64, policy_identifier(policy), 1.0, np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32), np.ones(4, dtype=np.float32)),),
            policy, feature_names=("speed_ms", "throttle_pct"), policy_id=policy_identifier(policy), optimizer_steps=1,
        )


def test_training_refuses_a_nonfinite_nll_before_an_optimizer_step(monkeypatch) -> None:
    class NonfiniteCandidate(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.value = torch.nn.Parameter(torch.tensor(1.0))

        def distribution(self, features, valid, previous):
            nan = self.value * torch.tensor(float("nan"))
            return nan.expand(1, 4), torch.ones((1, 4)), torch.zeros_like(previous)

    monkeypatch.setattr(training, "build_candidate", lambda kind, config: NonfiniteCandidate())
    policy = _policy()
    teacher = TeacherProfile(
        _unit("training"), np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32), "a" * 64, "b" * 64,
        policy_identifier(policy), 1.0, np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32), np.ones(4, dtype=np.float32),
    )

    with pytest.raises(ValueError, match="nonfinite"):
        train_distilled_candidate(
            "gru", CandidateConfig(feature_width=2, latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16),
            (teacher,), policy, feature_names=("speed_ms", "throttle_pct"), policy_id=policy_identifier(policy), optimizer_steps=1,
        )
