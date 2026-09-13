"""Masked recurrent actor and critic for structural diagnostics."""

from dataclasses import dataclass

import torch
from torch import nn
from torch.distributions import Beta, Categorical
from torch.nn import functional as F

from poweshift_backend.policy.schema import PolicySchema


@dataclass(frozen=True)
class StructuralDiagnostic:
    """Finite forward/backward evidence for the policy scaffold."""

    finite: bool
    masked_probability: float
    gradient_norm: float


class RecurrentActorCritic(nn.Module):
    """GRU policy with masked manoeuvres and beta deployment."""

    def __init__(self, schema: PolicySchema) -> None:
        super().__init__()
        self.schema = schema
        feature_width = len(schema.feature_names)
        self.recurrent = nn.GRU(feature_width * 2, schema.recurrent_width, batch_first=True)
        self.manoeuvre_head = nn.Linear(schema.recurrent_width, len(schema.manoeuvres))
        self.deployment_head = nn.Linear(schema.recurrent_width, 2)
        self.value_head = nn.Linear(schema.recurrent_width, 1)

    def forward(
        self,
        features: torch.Tensor,
        feature_mask: torch.Tensor,
        action_mask: torch.Tensor,
        recurrent_state: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Return masked logits, beta parameters, values and final state."""
        if features.ndim != 3 or feature_mask.shape != features.shape or feature_mask.dtype is not torch.bool:
            raise ValueError("features and feature mask must share batch, time and feature shape")
        if features.shape[-1] != len(self.schema.feature_names):
            raise ValueError("features do not match the policy schema")
        if action_mask.shape != (features.shape[0], len(self.schema.manoeuvres)) or action_mask.dtype is not torch.bool:
            raise ValueError("action mask does not match the policy schema")
        if not torch.all(action_mask.any(dim=-1)):
            raise ValueError("every policy row needs an available manoeuvre")
        masked_features = torch.where(feature_mask, features, torch.zeros_like(features))
        recurrent_inputs = torch.cat((masked_features, feature_mask.to(features.dtype)), dim=-1)
        outputs, next_state = self.recurrent(recurrent_inputs, recurrent_state)
        last = outputs[:, -1]
        logits = self.manoeuvre_head(last).masked_fill(~action_mask, -torch.inf)
        concentrations = F.softplus(self.deployment_head(last)) + 1.0
        values = self.value_head(last).squeeze(-1)
        return logits, concentrations[:, 0], concentrations[:, 1], values, next_state


def structural_forward_backward_diagnostic(
    model: RecurrentActorCritic,
    features: torch.Tensor,
    feature_mask: torch.Tensor,
    action_mask: torch.Tensor,
) -> StructuralDiagnostic:
    """Run one synthetic actor-critic backward pass."""
    model.zero_grad(set_to_none=True)
    logits, alpha, beta, values, _ = model(features, feature_mask, action_mask)
    manoeuvre = Categorical(logits=logits)
    deployment = Beta(alpha, beta)
    sampled_manoeuvre = manoeuvre.sample()
    sampled_deployment = deployment.sample()
    joint_log_probability = manoeuvre.log_prob(sampled_manoeuvre) + deployment.log_prob(sampled_deployment)
    loss = -joint_log_probability.mean() + values.square().mean()
    loss.backward()
    gradients = tuple(parameter.grad for parameter in model.parameters() if parameter.grad is not None)
    finite = bool(torch.isfinite(loss).item()) and bool(gradients) and all(bool(torch.isfinite(value).all()) for value in gradients)
    gradient_norm = float(torch.sqrt(sum(value.square().sum() for value in gradients)).detach()) if gradients else 0.0
    masked = manoeuvre.probs.masked_select(~action_mask)
    masked_probability = float(masked.max().detach()) if masked.numel() else 0.0
    return StructuralDiagnostic(finite, masked_probability, gradient_norm)
