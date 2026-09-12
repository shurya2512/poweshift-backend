"""Minimal tyre policy for admitted dry mechanics only."""

from dataclasses import dataclass


class UnsupportedTyreCondition(ValueError):
    """Raised when a requested tyre state has no declared support."""


@dataclass(frozen=True)
class DryTyreCondition:
    """Declared constant dry grip without tyre-state identification."""

    longitudinal_mu: float
    lateral_mu: float
    surface: str = "dry"

    def __post_init__(self) -> None:
        if self.surface != "dry":
            raise UnsupportedTyreCondition("only dry tyre support is available")
        if self.longitudinal_mu <= 0.0 or self.lateral_mu <= 0.0:
            raise ValueError("dry grip coefficients must be positive")
