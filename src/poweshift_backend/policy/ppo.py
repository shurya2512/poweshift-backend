"""Minimal recurrent PPO evaluation and optimizer update."""

from dataclasses import dataclass
from math import isfinite

import torch
from torch.distributions import Beta, Categorical

from poweshift_backend.contracts.policy_training import PpoRunConfig
from poweshift_backend.policy.buffer import RolloutStep
from poweshift_backend.policy.model import RecurrentActorCritic


@dataclass(frozen=True)
class RecurrentFragment:
    """Contiguous rollout steps with an excluded burn-in prefix."""

    steps: tuple[RolloutStep, ...]
    burn_in: int
    bootstrap_value: float = 0.0

    def __post_init__(self) -> None:
        if not self.steps or not 0 <= self.burn_in < len(self.steps):
            raise ValueError("recurrent fragment needs informative steps")
        if not isfinite(self.bootstrap_value):
            raise ValueError("fragment bootstrap value must be finite")


@dataclass(frozen=True)
class AdvantageBatch:
    """Advantages and value targets after burn-in."""

    advantages: torch.Tensor
    returns: torch.Tensor


@dataclass(frozen=True)
class PpoUpdateRecord:
    """Finite evidence returned by one optimizer update."""

    total_loss: float
    actor_loss: float
    value_loss: float
    entropy: float
    gradient_norm: float
    parameter_delta_norm: float
    sample_count: int


@dataclass(frozen=True)
class EvaluatedActions:
    """Current likelihood, entropy and values for sampled actions."""

    joint_log_probability: torch.Tensor
    entropy: torch.Tensor
    values: torch.Tensor


def evaluate_sampled_actions(model: RecurrentActorCritic, fragment: RecurrentFragment) -> EvaluatedActions:
    """Evaluate original samples while replaying recurrent state."""
    device = next(model.parameters()).device
    first_state = torch.tensor(fragment.steps[0].recurrent_state_before, dtype=torch.float32, device=device).reshape(1, 1, -1)
    recurrent_state: torch.Tensor | None = first_state
    log_probabilities: list[torch.Tensor] = []
    entropies: list[torch.Tensor] = []
    values: list[torch.Tensor] = []
    for index, step in enumerate(fragment.steps):
        features = torch.tensor(step.observation, dtype=torch.float32, device=device).reshape(1, 1, -1)
        feature_mask = torch.tensor(step.feature_mask, dtype=torch.bool, device=device).reshape(1, 1, -1)
        mask_values = step.action_mask or tuple(True for _ in model.schema.manoeuvres)
        action_mask = torch.tensor(mask_values, dtype=torch.bool, device=device).reshape(1, -1)
        logits, alpha, beta, value, recurrent_state = model(features, feature_mask, action_mask, recurrent_state)
        if index < fragment.burn_in:
            continue
        manoeuvre = Categorical(logits=logits)
        sampled_index = model.schema.manoeuvres.index(step.action.sampled.manoeuvre)
        sampled_manoeuvre = torch.tensor([sampled_index], device=device)
        joint = manoeuvre.log_prob(sampled_manoeuvre)
        entropy = manoeuvre.entropy()
        if step.deployment_available:
            deployment = Beta(alpha, beta)
            fraction = torch.tensor([step.action.sampled.deployment_fraction], dtype=torch.float32, device=device)
            joint = joint + deployment.log_prob(fraction)
            entropy = entropy + deployment.entropy()
        log_probabilities.append(joint.squeeze(0))
        entropies.append(entropy.squeeze(0))
        values.append(value.squeeze(0))
    return EvaluatedActions(torch.stack(log_probabilities), torch.stack(entropies), torch.stack(values))


def compute_recurrent_advantages(
    fragment: RecurrentFragment,
    next_value: torch.Tensor,
    config: PpoRunConfig,
) -> AdvantageBatch:
    """Compute GAE with distinct termination and truncation handling."""
    steps = fragment.steps
    advantages = [0.0] * len(steps)
    gae = 0.0
    following = float(next_value.detach())
    for index in range(len(steps) - 1, -1, -1):
        step = steps[index]
        bootstrap = 0.0 if step.terminated else following
        delta = step.reward + config.discount * bootstrap - step.value
        continues = 0.0 if step.terminated or step.truncated else 1.0
        gae = delta + config.discount * config.gae_lambda * continues * gae
        advantages[index] = gae
        following = step.value
    selected = torch.tensor(advantages[fragment.burn_in :], dtype=torch.float32)
    values = torch.tensor([step.value for step in steps[fragment.burn_in :]], dtype=torch.float32)
    return AdvantageBatch(selected, selected + values)


def ppo_update(
    model: RecurrentActorCritic,
    optimizer: torch.optim.Optimizer,
    fragment: RecurrentFragment,
    config: PpoRunConfig,
) -> PpoUpdateRecord:
    """Apply one guarded PPO optimizer step."""
    evaluated = evaluate_sampled_actions(model, fragment)
    device = evaluated.values.device
    next_value = torch.tensor(fragment.bootstrap_value, dtype=torch.float32)
    batch = compute_recurrent_advantages(fragment, next_value, config)
    advantages = batch.advantages.to(device)
    returns = batch.returns.to(device)
    old_log_probability = torch.tensor(
        [step.action.sampled_joint_log_probability for step in fragment.steps[fragment.burn_in :]],
        dtype=torch.float32,
        device=device,
    )
    ratio = torch.exp(evaluated.joint_log_probability - old_log_probability)
    unclipped = ratio * advantages
    clipped = torch.clamp(ratio, 1.0 - config.clip_ratio, 1.0 + config.clip_ratio) * advantages
    actor_loss = -torch.minimum(unclipped, clipped).mean()
    value_loss = torch.square(evaluated.values - returns).mean()
    entropy = evaluated.entropy.mean()
    total_loss = actor_loss + config.value_weight * value_loss - config.entropy_weight * entropy
    if not bool(torch.isfinite(total_loss)):
        raise ValueError("PPO loss must be finite")
    before = tuple(parameter.detach().clone() for parameter in model.parameters())
    optimizer.zero_grad(set_to_none=True)
    total_loss.backward()
    gradients = tuple(parameter.grad for parameter in model.parameters() if parameter.grad is not None)
    if not gradients or any(not bool(torch.isfinite(gradient).all()) for gradient in gradients):
        optimizer.zero_grad(set_to_none=True)
        raise ValueError("PPO gradients must be finite and informative")
    raw_norm = torch.sqrt(sum(gradient.square().sum() for gradient in gradients))
    if not bool(torch.isfinite(raw_norm)) or float(raw_norm) == 0.0:
        optimizer.zero_grad(set_to_none=True)
        raise ValueError("PPO gradients must be finite and informative")
    torch.nn.utils.clip_grad_norm_(model.parameters(), config.maximum_gradient_norm, error_if_nonfinite=True)
    optimizer.step()
    delta_norm = torch.sqrt(sum((parameter.detach() - old).square().sum() for parameter, old in zip(model.parameters(), before)))
    if not bool(torch.isfinite(delta_norm)) or float(delta_norm) == 0.0:
        with torch.no_grad():
            for parameter, old in zip(model.parameters(), before):
                parameter.copy_(old)
        raise ValueError("PPO update left parameters unchanged")
    return PpoUpdateRecord(
        float(total_loss.detach()), float(actor_loss.detach()), float(value_loss.detach()),
        float(entropy.detach()), float(raw_norm.detach()), float(delta_norm.detach()),
        len(fragment.steps) - fragment.burn_in,
    )
