"""Finite execution of an already selected pit visit."""

from poweshift_backend.contracts.pits import PitCrossing, PitExecutionResult, PitExecutionState
from poweshift_backend.contracts.rules import RegulatoryRuleSnapshot


_NEXT_STAGE = {
    "entry": "transit",
    "transit": "service",
    "service": "wait",
    "exit": "merge",
}


def advance_fixed_pit(
    state: PitExecutionState,
    crossing: PitCrossing,
    rules: RegulatoryRuleSnapshot,
) -> PitExecutionResult:
    """Advance one fixed visit without owning vehicle resources."""
    visit = state.visit
    if visit is None:
        return PitExecutionResult(state, None)
    if "pit_lane_closed" in rules.unsupported_modes and state.stage == "track" and crossing.lap == visit.lap:
        return PitExecutionResult(state, "pit_lane_closed")
    stage = state.stage
    if stage == "track":
        if crossing.lap < visit.lap or crossing.time_s < visit.entry_time_s:
            return PitExecutionResult(state, None)
        if crossing.lap != visit.lap:
            return PitExecutionResult(state, "fixed_pit_visit_missed")
        stage = "entry"
    elif stage == "wait":
        stage = "exit" if crossing.time_s >= visit.exit_time_s else "wait"
    elif stage == "merge":
        return PitExecutionResult(PitExecutionState(state.visit_index + 1, "track"), None)
    else:
        stage = _NEXT_STAGE[stage]
    return PitExecutionResult(PitExecutionState(state.visit_index, stage, visit), None)
