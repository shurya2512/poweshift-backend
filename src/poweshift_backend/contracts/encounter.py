"""Persistent two-car encounter state and evidence contracts."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class EncounterEvidence:
    """Frozen bounds required by the interaction world."""

    evidence_id: str
    admitted: bool
    minimum_wake_multiplier: float
    minimum_grip_multiplier: float

    def __post_init__(self) -> None:
        if not self.evidence_id or not all(
            isfinite(value) and 0.0 < value <= 1.0
            for value in (self.minimum_wake_multiplier, self.minimum_grip_multiplier)
        ):
            raise ValueError("interaction evidence bounds are invalid")


@dataclass(frozen=True)
class EncounterState:
    """Ego and persistent reference identity through one encounter."""

    ego_identity: str
    reference_identity: str
    ego_progress_m: float
    reference_progress_m: float
    defence_active: bool
    abort_active: bool

    def __post_init__(self) -> None:
        if not self.ego_identity or not self.reference_identity:
            raise ValueError("encounter identities are required")
        if not all(isfinite(value) for value in (self.ego_progress_m, self.reference_progress_m)):
            raise ValueError("encounter progress must be finite")
