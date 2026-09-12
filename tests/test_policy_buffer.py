import pytest
import torch

from poweshift_backend.contracts.action import ActionRequest, Manoeuvre
from poweshift_backend.policy.buffer import ActionRecord, RecurrentRolloutBuffer, RolloutStep
from poweshift_backend.policy.ppo import RecurrentFragment, compute_recurrent_advantages, ppo_update
from poweshift_backend.contracts.policy_training import PpoRunConfig
from poweshift_backend.policy.model import RecurrentActorCritic
from poweshift_backend.policy.schema import PolicySchema


def _step(*, terminated: bool = False, truncated: bool = False) -> RolloutStep:
    return RolloutStep(
        observation=(1.0, 2.0),
        feature_mask=(True, True),
        action=ActionRecord(
            sampled=ActionRequest(Manoeuvre.ATTACK, 0.8),
            issued=ActionRequest(Manoeuvre.ATTACK, 0.8),
            delivered=ActionRequest(Manoeuvre.ATTACK, 0.5),
            sampled_joint_log_probability=-1.25,
        ),
        recurrent_state_before=(0.0, 0.0),
        recurrent_state_after=(0.1, 0.2),
        value=0.4,
        reward=1.0,
        terminated=terminated,
        truncated=truncated,
        action_mask=(True, True, True, True),
    )


def test_buffer_retains_sampled_probability_when_delivery_is_clipped() -> None:
    buffer = RecurrentRolloutBuffer(feature_width=2, recurrent_width=2)
    buffer.append(_step())

    stored = buffer.steps[0]
    assert stored.action.sampled.deployment_fraction == 0.8
    assert stored.action.delivered.deployment_fraction == 0.5
    assert stored.action.sampled_joint_log_probability == -1.25


def test_buffer_refuses_missing_action_record_and_handles_episode_endings() -> None:
    buffer = RecurrentRolloutBuffer(feature_width=2, recurrent_width=2)
    broken = _step()
    object.__setattr__(broken, "action", None)
    with pytest.raises(ValueError, match="sampled action"):
        buffer.append(broken)

    assert RecurrentRolloutBuffer.bootstrap_value(_step(terminated=True), 3.0) == 0.0
    assert RecurrentRolloutBuffer.bootstrap_value(_step(truncated=True), 3.0) == 3.0
    with pytest.raises(ValueError, match="both"):
        _step(terminated=True, truncated=True)


def test_advantages_bootstrap_truncation_but_not_termination() -> None:
    config = PpoRunConfig(1e-3, 0.9, 1.0, 0.2, 0.5, 0.0, 1.0)
    terminal = compute_recurrent_advantages(RecurrentFragment((_step(terminated=True),), 0), torch.tensor(3.0), config)
    truncated = compute_recurrent_advantages(RecurrentFragment((_step(truncated=True),), 0), torch.tensor(3.0), config)
    assert terminal.advantages.item() == pytest.approx(0.6)
    assert truncated.advantages.item() == pytest.approx(3.3)


def test_one_ppo_update_changes_parameters_and_uses_original_sample() -> None:
    torch.manual_seed(4)
    schema = PolicySchema("schema-a", ("a", "b"), tuple(Manoeuvre), 2, "beta-v1")
    model = RecurrentActorCritic(schema)
    config = PpoRunConfig(1e-2, 0.9, 0.95, 0.2, 0.5, 0.01, 1.0)
    before = tuple(parameter.detach().clone() for parameter in model.parameters())
    record = ppo_update(model, torch.optim.Adam(model.parameters(), lr=config.learning_rate), RecurrentFragment((_step(terminated=True),), 0), config)
    assert record.sample_count == 1
    assert record.gradient_norm > 0.0
    assert record.parameter_delta_norm > 0.0
    assert any(not torch.equal(left, right) for left, right in zip(before, model.parameters()))
