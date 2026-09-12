from datetime import datetime, timezone

from poweshift_backend.contracts.pits import PitCrossing, PitExecutionState, PitVisit
from poweshift_backend.contracts.rules import RuleApplicability, RegulatoryRuleSnapshot
from poweshift_backend.pits.execution import advance_fixed_pit


def _rules(*, closed: bool = False) -> RegulatoryRuleSnapshot:
    return RegulatoryRuleSnapshot.create(
        snapshot_id="rules-a", source_sha256="a" * 64,
        applicability=RuleApplicability(2026, "event-a", "R", datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc)),
        limits=(), line_maps=("pit_entry", "pit_exit"),
        unsupported_modes=frozenset({"pit_lane_closed"}) if closed else frozenset(),
    )


def test_pit_execution_advances_finite_stages_without_owning_vehicle_state() -> None:
    state = PitExecutionState(0, "track", PitVisit(3, 30.0, 40.0, ("tyres",)))
    stages = []
    for time_s in (30.0, 31.0, 32.0, 33.0, 40.0, 41.0, 42.0):
        result = advance_fixed_pit(state, PitCrossing(3, time_s), _rules())
        state = result.state
        stages.append(state.stage)
    assert stages == ["entry", "transit", "service", "wait", "exit", "merge", "track"]
    assert state.visit_index == 1


def test_pit_execution_reports_rule_conflicts() -> None:
    state = PitExecutionState(0, "track", PitVisit(3, 30.0, 40.0, ()))
    assert advance_fixed_pit(state, PitCrossing(3, 30.0), _rules(closed=True)).conflict == "pit_lane_closed"
