import pytest

from poweshift_backend.contracts.action import ActionRequest, Manoeuvre
from poweshift_backend.contracts.encounter import EncounterEvidence, EncounterState
from poweshift_backend.simulation.encounter import advance_encounter


def test_encounter_preserves_reference_identity_and_persistent_abort() -> None:
    evidence = EncounterEvidence("interaction-a", True, 0.9, 0.8)
    initial = EncounterState("ego", "reference-7", 10.0, 12.0, False, False)

    defended = advance_encounter(initial, ActionRequest(Manoeuvre.DEFEND, 0.0), evidence, 2.0, 1.0)
    aborted = advance_encounter(defended, ActionRequest(Manoeuvre.ABORT, 0.0), evidence, 2.0, 1.0)
    continued = advance_encounter(aborted, ActionRequest(Manoeuvre.ATTACK, 0.0), evidence, 2.0, 1.0)

    assert continued.reference_identity == "reference-7"
    assert continued.defence_active is True
    assert continued.abort_active is True
    with pytest.raises(ValueError, match="evidence"):
        advance_encounter(initial, ActionRequest(Manoeuvre.HOLD, 0.0), EncounterEvidence("interaction-a", False, 0.9, 0.8), 1.0, 1.0)
