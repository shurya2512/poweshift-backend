"""Cutoff-safe ego observation contracts."""

from dataclasses import dataclass

from poweshift_backend.contracts.action import DeliveredAction
from poweshift_backend.contracts.powertrain import EvidenceOrigin


@dataclass(frozen=True)
class EgoObservation:
    """Observed ego values without privileged opponent state."""

    speed_ms: float
    progress_m: float
    stored_energy_j: float
    origin: EvidenceOrigin
    previous_action: DeliveredAction | None
