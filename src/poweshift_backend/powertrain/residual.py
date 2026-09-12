"""One bounded neural residual for a named response mechanism."""

import torch
from torch import nn


class BoundedResponseResidual(nn.Module):
    """Bound a learned correction to one declared mechanism."""

    def __init__(self, input_width: int, hidden_width: int, maximum_correction_w: float, mechanism: str) -> None:
        super().__init__()
        if min(input_width, hidden_width) < 1 or maximum_correction_w <= 0.0 or not mechanism:
            raise ValueError("residual dimensions, bound and mechanism are required")
        self.network = nn.Sequential(nn.Linear(input_width, hidden_width), nn.Tanh(), nn.Linear(hidden_width, 1))
        self.maximum_correction_w = float(maximum_correction_w)
        self.mechanism = mechanism

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        """Return one bounded power correction per input row."""
        return torch.tanh(self.network(inputs).squeeze(-1)) * self.maximum_correction_w
