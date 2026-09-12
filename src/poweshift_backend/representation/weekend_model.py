"""Bounded per-car profiles for direct weekend reconstruction."""

from dataclasses import dataclass
from math import isfinite

import torch
from torch import nn

from poweshift_backend.physics.differentiable import PARAMETER_NAMES


@dataclass(frozen=True)
class WeekendModelConfig:
    """Frozen encoder dimensions and physical parameter bounds."""

    feature_width: int
    parameter_lower: tuple[float, ...]
    parameter_upper: tuple[float, ...]
    initial_parameter_seed: tuple[float, ...] | None = None
    latent_width: int = 16
    hidden_width: int = 32
    layers: int = 1

    def __post_init__(self) -> None:
        dimensions = (self.feature_width, self.latent_width, self.hidden_width, self.layers)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in dimensions):
            raise ValueError("model dimensions must be positive integers")
        if len(self.parameter_lower) != len(PARAMETER_NAMES) or len(self.parameter_upper) != len(PARAMETER_NAMES):
            raise ValueError("bounds must match the physics parameter order")
        if not all(isfinite(value) for value in (*self.parameter_lower, *self.parameter_upper)):
            raise ValueError("bounds must be finite")
        if any(lower >= upper for lower, upper in zip(self.parameter_lower, self.parameter_upper, strict=True)):
            raise ValueError("bounds must have a positive span")
        if any(value < 0.0 for value in self.parameter_lower[:6]) or any(value <= 0.0 for value in self.parameter_lower[6:]):
            raise ValueError("bounds must remain inside physics support")
        if self.initial_parameter_seed is not None and (
            len(self.initial_parameter_seed) != len(PARAMETER_NAMES)
            or not all(isfinite(value) for value in self.initial_parameter_seed)
            or any(value <= lower or value >= upper for value, lower, upper in zip(self.initial_parameter_seed, self.parameter_lower, self.parameter_upper, strict=True))
        ):
            raise ValueError("initial profile must lie strictly inside the frozen bounds")


@dataclass(frozen=True)
class WeekendModelOutput:
    """Latents, bounded physics parameters and raw per-car uncertainty."""

    latent: torch.Tensor
    parameters: torch.Tensor
    uncertainty: torch.Tensor


class WeekendTelemetryModel(nn.Module):
    """Encode supplied telemetry into one profile for each car."""

    def __init__(self, config: WeekendModelConfig) -> None:
        super().__init__()
        self.config = config
        self.input = nn.Linear(config.feature_width, config.hidden_width)
        self.encoder = nn.GRU(config.hidden_width, config.hidden_width, config.layers, batch_first=True)
        self.latent_projection = nn.Linear(config.hidden_width, config.latent_width)
        self.parameter_decoder = nn.Linear(config.latent_width, len(PARAMETER_NAMES))
        self.uncertainty_decoder = nn.Linear(config.latent_width, 1)
        self.register_buffer("parameter_lower", torch.tensor(config.parameter_lower, dtype=torch.float64))
        self.register_buffer("parameter_upper", torch.tensor(config.parameter_upper, dtype=torch.float64))
        self.double()
        if config.initial_parameter_seed is not None:
            seed = torch.tensor(config.initial_parameter_seed, dtype=torch.float64)
            unit = (seed - self.parameter_lower) / (self.parameter_upper - self.parameter_lower)
            with torch.no_grad():
                self.parameter_decoder.bias.copy_(torch.logit(unit))

    def forward(self, features: torch.Tensor) -> WeekendModelOutput:
        """Return one bounded profile and uncertainty for every supplied car."""
        if features.ndim != 3 or features.shape[-1] != self.config.feature_width:
            raise ValueError("features must be [car, sample, feature] with the configured width")
        if not torch.isfinite(features).all():
            raise ValueError("features must be finite")
        _, hidden = self.encoder(self.input(features))
        latent = self.latent_projection(hidden[-1])
        unit_parameters = torch.sigmoid(self.parameter_decoder(latent))
        parameters = self.parameter_lower + (self.parameter_upper - self.parameter_lower) * unit_parameters
        return WeekendModelOutput(latent, parameters, self.uncertainty_decoder(latent).squeeze(-1))
