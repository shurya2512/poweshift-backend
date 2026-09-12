"""Admission gate for the integrated two-corner tactical world."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TacticalAdmission:
    """Prerequisites for constructing a tactical environment."""

    energy_bundle_admitted: bool
    interaction_world_admitted: bool
    route_supported: bool
    fixed_pits_available: bool
    continuation_supported: bool


def require_tactical_ready(admission: TacticalAdmission) -> TacticalAdmission:
    """Refuse tactical execution until every world input is admitted."""
    checks = (
        (admission.energy_bundle_admitted, "admitted energy bundle"),
        (admission.interaction_world_admitted, "admitted interaction world"),
        (admission.route_supported, "supported route"),
        (admission.fixed_pits_available, "fixed pit manifest"),
        (admission.continuation_supported, "supported continuation"),
    )
    for available, name in checks:
        if not available:
            raise ValueError(f"tactical environment requires an {name}")
    return admission
