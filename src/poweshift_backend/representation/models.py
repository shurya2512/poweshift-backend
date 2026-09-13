"""Compact masked encoders with one bounded effective-profile decoder."""

from dataclasses import dataclass
from math import isfinite

import torch
from torch import nn
from torch.nn import functional as F


@dataclass(frozen=True)
class CandidateConfig:
    """Frozen dimensions shared by the two bounded candidates."""

    feature_width: int
    latent_width: int = 16
    hidden_width: int = 64
    layers: int = 2
    heads: int = 4
    feedforward_width: int = 128
    profile_width: int = 4
    variance_floor: float = 1e-4

    def __post_init__(self) -> None:
        if min(self.feature_width, self.latent_width, self.hidden_width, self.layers, self.heads, self.feedforward_width, self.profile_width) < 1:
            raise ValueError("candidate dimensions must be positive")
        if self.hidden_width % self.heads:
            raise ValueError("hidden width must divide evenly across heads")
        if not isfinite(self.variance_floor) or self.variance_floor <= 0.0:
            raise ValueError("variance floor must be positive")


class _Candidate(nn.Module):
    def _masked(self, features: torch.Tensor, valid: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if features.ndim != 3 or valid.shape != features.shape:
            raise ValueError("features and valid must be matching [batch, time, feature] tensors")
        time_valid = valid.any(dim=-1)
        if not time_valid.any(dim=-1).all():
            raise ValueError("every candidate sequence needs one valid timestep")
        return torch.where(valid, features, torch.zeros_like(features)), time_valid

    def _last(self, output: torch.Tensor, time_valid: torch.Tensor) -> torch.Tensor:
        positions = torch.arange(output.shape[1], device=output.device).expand_as(time_valid)
        index = torch.where(time_valid, positions, -torch.ones_like(positions)).max(dim=1).values
        return output[torch.arange(output.shape[0], device=output.device), index]

    def decode(self, latent: torch.Tensor) -> torch.Tensor:
        """Decode one bounded profile from a saved latent state."""
        return self.decoder(latent)

    def distribution(
        self, features: torch.Tensor, valid: torch.Tensor, previous_latent: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Return normalized mean, positive variance and next latent state."""
        latent = self.encode(features, valid, previous_latent)
        mean, variance = self.decoder.distribution(latent)
        return mean, variance, latent

    def update(
        self, features: torch.Tensor, valid: torch.Tensor, previous_latent: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Return the bounded profile and latent state for the next prefix."""
        latent = self.encode(features, valid, previous_latent)
        return self.decode(latent), latent


class BoundedProfileDecoder(nn.Module):
    def __init__(self, input_width: int, output_width: int, variance_floor: float) -> None:
        super().__init__()
        self.output = nn.Linear(input_width, output_width)
        self.variance = nn.Linear(input_width, output_width)
        self.variance_floor = variance_floor

    def forward(self, latent: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.output(latent))

    def distribution(self, latent: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Decode bounded means and variances above the configured floor."""
        return self(latent), F.softplus(self.variance(latent)) + self.variance_floor


class GruCandidate(_Candidate):
    def __init__(self, config: CandidateConfig) -> None:
        super().__init__()
        self.config = config
        self.input = nn.Linear(config.feature_width, config.hidden_width)
        self.initial = nn.Linear(config.latent_width, config.layers * config.hidden_width)
        self.encoder = nn.GRU(config.hidden_width, config.hidden_width, config.layers, batch_first=True)
        self.latent_projection = nn.Linear(config.hidden_width, config.latent_width)
        self.decoder = BoundedProfileDecoder(config.latent_width, config.profile_width, config.variance_floor)

    def encode(self, features: torch.Tensor, valid: torch.Tensor, previous_latent: torch.Tensor) -> torch.Tensor:
        values, time_valid = self._masked(features, valid)
        if previous_latent.shape != (features.shape[0], self.config.latent_width):
            raise ValueError("previous latent does not match the model record")
        encoded = self.input(values)
        initial = self.initial(previous_latent).view(features.shape[0], self.config.layers, self.config.hidden_width)
        hidden = initial.transpose(0, 1).contiguous()
        outputs = []
        for index in range(encoded.shape[1]):
            current, proposed = self.encoder(encoded[:, index : index + 1], hidden)
            active = time_valid[:, index].view(1, -1, 1)
            hidden = torch.where(active, proposed, hidden)
            outputs.append(current[:, 0])
        output = torch.stack(outputs, dim=1)
        return self.latent_projection(self._last(output, time_valid))

    def forward(self, features: torch.Tensor, valid: torch.Tensor, previous_latent: torch.Tensor) -> torch.Tensor:
        """Decode the next profile while retaining the training call shape."""
        return self.decode(self.encode(features, valid, previous_latent))


class TransformerCandidate(_Candidate):
    def __init__(self, config: CandidateConfig) -> None:
        super().__init__()
        self.config = config
        self.input = nn.Linear(config.feature_width, config.hidden_width)
        self.previous = nn.Linear(config.latent_width, config.hidden_width)
        layer = nn.TransformerEncoderLayer(
            d_model=config.hidden_width,
            nhead=config.heads,
            dim_feedforward=config.feedforward_width,
            dropout=0.0,
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, config.layers, enable_nested_tensor=False)
        self.latent_projection = nn.Linear(config.hidden_width, config.latent_width)
        self.decoder = BoundedProfileDecoder(config.latent_width, config.profile_width, config.variance_floor)

    def _positions(self, length: int, width: int, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
        position = torch.arange(length, device=device, dtype=dtype).unsqueeze(1)
        scale = torch.exp(torch.arange(0, width, 2, device=device, dtype=dtype) * (-torch.log(torch.tensor(10000.0, device=device)) / width))
        values = torch.zeros((length, width), device=device, dtype=dtype)
        values[:, 0::2] = torch.sin(position * scale)
        values[:, 1::2] = torch.cos(position * scale)
        return values

    def encode(self, features: torch.Tensor, valid: torch.Tensor, previous_latent: torch.Tensor) -> torch.Tensor:
        values, time_valid = self._masked(features, valid)
        if previous_latent.shape != (features.shape[0], self.config.latent_width):
            raise ValueError("previous latent does not match the model record")
        encoded = self.input(values) + self.previous(previous_latent).unsqueeze(1)
        encoded = encoded + self._positions(encoded.shape[1], encoded.shape[2], encoded.device, encoded.dtype).unsqueeze(0)
        output = self.encoder(encoded, src_key_padding_mask=~time_valid)
        return self.latent_projection(self._last(output, time_valid))

    def forward(self, features: torch.Tensor, valid: torch.Tensor, previous_latent: torch.Tensor) -> torch.Tensor:
        """Decode the next profile while retaining the training call shape."""
        return self.decode(self.encode(features, valid, previous_latent))


def build_candidate(kind: str, config: CandidateConfig) -> _Candidate:
    """Build one declared candidate architecture without changing its dimensions."""
    if kind == "gru":
        return GruCandidate(config)
    if kind == "transformer":
        return TransformerCandidate(config)
    raise ValueError(f"unknown candidate: {kind}")
