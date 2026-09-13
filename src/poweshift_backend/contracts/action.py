"""Masked manoeuvre and electrical deployment contracts."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class Manoeuvre(str, Enum):
    """Supported high-level manoeuvre choices."""

    HOLD = "hold"
    ATTACK = "attack"
    DEFEND = "defend"
    ABORT = "abort"


@dataclass(frozen=True)
class ActionRequest:
    """Requested manoeuvre and usable electrical fraction."""

    manoeuvre: Manoeuvre
    deployment_fraction: float

    def __post_init__(self) -> None:
        if not isfinite(self.deployment_fraction) or not 0.0 <= self.deployment_fraction <= 1.0:
            raise ValueError("deployment fraction must be between zero and one")


@dataclass(frozen=True)
class ActionMask:
    """Available manoeuvres and electrical deployment state."""

    manoeuvres: frozenset[Manoeuvre]
    deployment_available: bool

    def __post_init__(self) -> None:
        if not self.manoeuvres:
            raise ValueError("action mask must permit at least one manoeuvre")

    def require(self, request: ActionRequest) -> None:
        """Refuse a masked manoeuvre or electrical request."""
        if request.manoeuvre not in self.manoeuvres:
            raise ValueError("requested manoeuvre is masked")
        if request.deployment_fraction > 0.0 and not self.deployment_available:
            raise ValueError("electrical deployment is masked")


@dataclass(frozen=True)
class DeliveredAction:
    """Issued and physically delivered action kept separate."""

    issued: ActionRequest
    delivered: ActionRequest
    binding_reasons: tuple[str, ...] = ()
