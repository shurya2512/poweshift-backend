"""Replay-only single-car environment with explicit episode endings."""

from dataclasses import dataclass

from poweshift_backend.contracts.action import ActionMask, ActionRequest
from poweshift_backend.contracts.pits import FixedPitManifest, FixedPitSchedule
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.contracts.scenario import ScenarioEvent, ScenarioSpec
from poweshift_backend.pits.manifest import require_no_pit_schedule, require_no_pit_window
from poweshift_backend.simulation.ego import EgoState, SharedAdvance, advance_ego


@dataclass(frozen=True)
class ReplayStep:
    """One replay transition and its ending markers."""

    state: EgoState
    events: tuple[ScenarioEvent, ...]
    terminated: bool
    truncated: bool


class ReplayEnvironment:
    """Run a supported no-pit scenario through shared admitted physics."""

    def __init__(
        self,
        scenario: ScenarioSpec,
        initial_state: EgoState,
        action_mask: ActionMask,
        bundle: EnergyBundleCompatibility,
        pit_manifest: FixedPitManifest,
        advance: SharedAdvance,
        pit_schedule: FixedPitSchedule | None = None,
    ) -> None:
        require_no_pit_window(pit_manifest, scenario.start_time_s, scenario.end_time_s)
        if pit_schedule is not None:
            require_no_pit_schedule(pit_schedule, scenario.start_time_s, scenario.end_time_s)
        if initial_state.mechanics.time_s != scenario.start_time_s:
            raise ValueError("initial ego time must match the scenario")
        self.scenario = scenario
        self.initial_state = initial_state
        self.action_mask = action_mask
        self.bundle = bundle
        self.pit_manifest = pit_manifest
        self.pit_schedule = pit_schedule
        self.advance = advance
        self.reset()

    def reset(self) -> EgoState:
        """Restore the declared initial state."""
        self.state = self.initial_state
        self.steps = 0
        self.finished = False
        return self.state

    def step(self, request: ActionRequest) -> ReplayStep:
        """Advance one step and preserve crossed scenario events."""
        if self.finished:
            raise ValueError("replay episode has already ended")
        before = self.state.mechanics.time_s
        self.state = advance_ego(self.state, request, self.action_mask, self.bundle, self.advance)
        self.steps += 1
        after = self.state.mechanics.time_s
        events = tuple(event for event in self.scenario.events if before < event.time_s <= after)
        terminated = after >= self.scenario.end_time_s
        truncated = self.steps >= self.scenario.maximum_steps and not terminated
        if terminated:
            events = (*events, ScenarioEvent(self.scenario.end_time_s, "scenario_end"))
        elif truncated:
            events = (*events, ScenarioEvent(after, "step_limit"))
        self.finished = terminated or truncated
        return ReplayStep(self.state, events, terminated, truncated)
