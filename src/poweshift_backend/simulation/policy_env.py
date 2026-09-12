"""Policy adapter over the shared single-car replay environment."""

from collections.abc import Callable
from dataclasses import dataclass

import torch

from poweshift_backend.contracts.action import ActionMask, ActionRequest, DeliveredAction
from poweshift_backend.policy.buffer import ActionRecord
from poweshift_backend.policy.observation import AvailableContext, build_policy_observation
from poweshift_backend.policy.schema import PolicySchema
from poweshift_backend.simulation.ego import EgoState
from poweshift_backend.simulation.replay_env import ReplayEnvironment


ActionTransform = Callable[[EgoState, ActionRequest, ActionMask], DeliveredAction]
SampledLikelihood = Callable[[ActionRequest], float]
RewardFunction = Callable[[EgoState, EgoState, ActionRecord], float]


@dataclass(frozen=True)
class PolicyStep:
    """One complete observation, action and episode result."""

    observation: torch.Tensor
    feature_mask: torch.Tensor
    action_mask: ActionMask
    action: ActionRecord | None
    reward: float
    terminated: bool
    truncated: bool


class PhysicalPolicyEnvironment:
    """Expose shared admitted replay as policy rollout steps."""

    def __init__(
        self,
        replay: ReplayEnvironment,
        schema: PolicySchema,
        context: AvailableContext,
        transform: ActionTransform,
        sampled_likelihood: SampledLikelihood,
        reward: RewardFunction,
    ) -> None:
        self.replay = replay
        self.schema = schema
        self.context = context
        self.transform = transform
        self.sampled_likelihood = sampled_likelihood
        self.reward = reward

    def _observation(self) -> tuple[torch.Tensor, torch.Tensor, ActionMask]:
        return build_policy_observation(self.replay.state, self.context, self.schema)

    def reset(self) -> PolicyStep:
        """Reset replay and emit the initial masked observation."""
        self.replay.reset()
        observation, feature_mask, action_mask = self._observation()
        return PolicyStep(observation, feature_mask, action_mask, None, 0.0, False, False)

    def step(self, sampled: ActionRequest) -> PolicyStep:
        """Transform one sampled action and advance shared physics."""
        _, _, action_mask = self._observation()
        before = self.replay.state
        delivered = self.transform(before, sampled, action_mask)
        action_mask.require(delivered.issued)
        result = self.replay.step(delivered.delivered)
        observation, feature_mask, next_action_mask = self._observation()
        action = ActionRecord(sampled, delivered.issued, delivered.delivered, self.sampled_likelihood(sampled), delivered.binding_reasons)
        reward = float(self.reward(before, result.state, action))
        return PolicyStep(observation, feature_mask, next_action_mask, action, reward, result.terminated, result.truncated)
