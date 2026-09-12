"""Gated two-car continuation with persistent defence and abort."""

from poweshift_backend.contracts.action import ActionRequest, Manoeuvre
from poweshift_backend.contracts.encounter import EncounterEvidence, EncounterState


def advance_encounter(
    state: EncounterState,
    request: ActionRequest,
    evidence: EncounterEvidence,
    ego_progress_delta_m: float,
    reference_progress_delta_m: float,
) -> EncounterState:
    """Advance both identities after the interaction evidence gate."""
    if not evidence.admitted:
        raise ValueError("interaction evidence is not admitted")
    if ego_progress_delta_m < 0.0 or reference_progress_delta_m < 0.0:
        raise ValueError("encounter progress cannot reverse")
    return EncounterState(
        state.ego_identity,
        state.reference_identity,
        state.ego_progress_m + ego_progress_delta_m,
        state.reference_progress_m + reference_progress_delta_m,
        state.defence_active or request.manoeuvre is Manoeuvre.DEFEND,
        state.abort_active or request.manoeuvre is Manoeuvre.ABORT,
    )
