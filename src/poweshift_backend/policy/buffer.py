"""Recurrent rollout records that preserve sampled action likelihoods."""

from dataclasses import dataclass
from math import isfinite

from poweshift_backend.contracts.action import ActionRequest


@dataclass(frozen=True)
class ActionRecord:
    """Sampled, issued and delivered actions at one rollout step."""

    sampled: ActionRequest
    issued: ActionRequest
    delivered: ActionRequest
    sampled_joint_log_probability: float
    binding_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isfinite(self.sampled_joint_log_probability):
            raise ValueError("sampled joint log probability must be finite")


@dataclass(frozen=True)
class RolloutStep:
    """One recurrent transition with explicit episode markers."""

    observation: tuple[float, ...]
    feature_mask: tuple[bool, ...]
    action: ActionRecord
    recurrent_state_before: tuple[float, ...]
    recurrent_state_after: tuple[float, ...]
    value: float
    reward: float
    terminated: bool
    truncated: bool
    action_mask: tuple[bool, ...] = ()
    deployment_available: bool = True

    def __post_init__(self) -> None:
        if self.terminated and self.truncated:
            raise ValueError("a rollout step cannot be both terminated and truncated")
        if self.action_mask and not any(self.action_mask):
            raise ValueError("rollout action mask must permit a manoeuvre")
        values = (*self.observation, *self.recurrent_state_before, *self.recurrent_state_after, self.value, self.reward)
        if not all(isfinite(value) for value in values):
            raise ValueError("rollout values must be finite")


class RecurrentRolloutBuffer:
    """Validate and retain complete recurrent fragments."""

    def __init__(self, feature_width: int, recurrent_width: int) -> None:
        if min(feature_width, recurrent_width) < 1:
            raise ValueError("buffer widths must be positive")
        self.feature_width = feature_width
        self.recurrent_width = recurrent_width
        self.steps: list[RolloutStep] = []

    def append(self, step: RolloutStep) -> None:
        """Append only a complete transition with original likelihood."""
        if not isinstance(step.action, ActionRecord):
            raise ValueError("sampled action record is required")
        if len(step.observation) != self.feature_width or len(step.feature_mask) != self.feature_width:
            raise ValueError("rollout observation does not match the feature schema")
        if len(step.recurrent_state_before) != self.recurrent_width or len(step.recurrent_state_after) != self.recurrent_width:
            raise ValueError("rollout state does not match the recurrent schema")
        self.steps.append(step)

    @staticmethod
    def bootstrap_value(step: RolloutStep, next_value: float) -> float:
        """Bootstrap truncation but not true termination."""
        if step.terminated:
            return 0.0
        if not isfinite(next_value):
            raise ValueError("bootstrap value must be finite")
        return next_value
