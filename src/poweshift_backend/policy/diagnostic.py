"""Diagnostic PPO updates over fitted profiles and observed controls."""

from dataclasses import dataclass
from math import isfinite
from statistics import mean

import torch
from torch.distributions import Beta, Categorical

from poweshift_backend.contracts.action import ActionRequest, Manoeuvre
from poweshift_backend.contracts.policy_training import PpoRunConfig
from poweshift_backend.energy.allocator import DeploymentPrior, LapEnergyState, allocate_additive_power
from poweshift_backend.policy.buffer import ActionRecord, RolloutStep
from poweshift_backend.policy.model import RecurrentActorCritic
from poweshift_backend.policy.ppo import RecurrentFragment, ppo_update
from poweshift_backend.policy.schema import PolicySchema


@dataclass(frozen=True)
class DiagnosticTrace:
    """One training-only sequence of observed driver controls."""

    source_partition: str
    trace_id: str
    speed_ms: tuple[float, ...]
    throttle: tuple[float, ...]
    brake: tuple[float, ...]
    step_s: float
    entry: str = "1"
    race_context: bool = False
    ahead_gap_s: tuple[float, ...] = ()
    ahead_closing_ms: tuple[float, ...] = ()
    behind_gap_s: tuple[float, ...] = ()
    behind_closing_ms: tuple[float, ...] = ()
    lap_index: int = 1
    total_laps: int = 1

    def __post_init__(self) -> None:
        rows = len(self.speed_ms)
        if self.source_partition != "training" or not self.trace_id or rows < 2:
            raise ValueError("diagnostic traces require training data and at least two rows")
        if len(self.throttle) != rows or len(self.brake) != rows or not isfinite(self.step_s) or self.step_s <= 0.0:
            raise ValueError("diagnostic trace columns must be aligned")
        if not all(isfinite(value) for values in (self.speed_ms, self.throttle, self.brake) for value in values):
            raise ValueError("diagnostic trace values must be finite")
        traffic = (self.ahead_gap_s, self.ahead_closing_ms, self.behind_gap_s, self.behind_closing_ms)
        if self.race_context and any(len(values) != rows for values in traffic):
            raise ValueError("race traffic columns must align with the trace")
        if self.race_context and not 1 <= self.lap_index <= self.total_laps:
            raise ValueError("race lap position is invalid")


@dataclass(frozen=True)
class FittedProfile:
    """Effective fitted force and resistance parameters for one entry."""

    entry: str
    maximum_drive_force_n: float
    drag_n_per_ms2: float
    rolling_resistance_n: float

    def __post_init__(self) -> None:
        if not self.entry or not all(isfinite(value) and value > 0.0 for value in (
            self.maximum_drive_force_n, self.drag_n_per_ms2, self.rolling_resistance_n,
        )):
            raise ValueError("fitted profile values must be positive and finite")


@dataclass(frozen=True)
class RaceInteractionPrior:
    """Transparent traffic thresholds and race-only reward weights."""

    attack_gap_s: float = 1.0
    defend_gap_s: float = 0.8
    minimum_closing_ms: float = 0.5
    free_air_gain_weight: float = 0.1
    attack_gain_weight: float = 1.0
    defend_gain_weight: float = 0.5
    deployment_cost_per_mj: float = 1.0
    late_race_cost_floor: float = 0.25
    reserve_shortfall_weight: float = 2.0


def classify_race_interaction(
    prior: RaceInteractionPrior,
    ahead_gap_s: float,
    ahead_closing_ms: float,
    behind_gap_s: float,
    behind_closing_ms: float,
    braking: bool,
) -> tuple[bool, bool]:
    """Classify bounded pass and defence opportunities from causal gaps."""
    if braking:
        return False, False
    opportunity = 0.0 < ahead_gap_s <= prior.attack_gap_s and ahead_closing_ms >= prior.minimum_closing_ms
    threat = 0.0 < behind_gap_s <= prior.defend_gap_s and behind_closing_ms >= prior.minimum_closing_ms
    return opportunity, threat


def race_step_reward(
    prior: RaceInteractionPrior,
    delivered_fraction: float,
    deployment_j: float,
    remaining_laps_fraction: float,
    step_weight: float,
    opportunity: bool,
    threat: bool,
) -> float:
    """Value normalized traffic gain against time-varying energy cost."""
    gain_weight = prior.free_air_gain_weight
    if opportunity:
        gain_weight += prior.attack_gain_weight
    if threat:
        gain_weight += prior.defend_gain_weight
    cost_scale = prior.late_race_cost_floor + (1.0 - prior.late_race_cost_floor) * remaining_laps_fraction
    return gain_weight * delivered_fraction * step_weight - prior.deployment_cost_per_mj * cost_scale * deployment_j / 1_000_000.0


def race_reserve_penalty(
    prior: RaceInteractionPrior,
    state_of_charge: float,
    target_fraction: float,
) -> float:
    """Penalize only an end-of-lap reserve shortfall."""
    return -prior.reserve_shortfall_weight * max(0.0, target_fraction - state_of_charge)


_SCHEMA = PolicySchema(
    "diagnostic-additive-v2",
    (
        "speed_ratio", "throttle", "brake", "state_of_charge",
        "ahead_gap_s", "ahead_closing_ratio", "behind_gap_s", "behind_closing_ratio",
        "remaining_laps_fraction",
    ),
    (Manoeuvre.HOLD, Manoeuvre.ATTACK, Manoeuvre.DEFEND),
    8,
    "additive-electric-percentage-v1",
)

_CONFIG = PpoRunConfig(3e-4, 0.99, 0.95, 0.2, 0.5, 0.01, 0.5)


def create_diagnostic_model(seed: int) -> RecurrentActorCritic:
    """Create the small recurrent policy used by the bounded diagnostic."""
    torch.manual_seed(seed)
    return RecurrentActorCritic(_SCHEMA)


def _rollout(
    model: RecurrentActorCritic,
    trace: DiagnosticTrace,
    profile: FittedProfile,
    prior: DeploymentPrior,
    initial_state: LapEnergyState,
    interaction_prior: RaceInteractionPrior,
) -> tuple[RecurrentFragment, LapEnergyState, dict[str, float]]:
    hidden = torch.zeros(1, 1, _SCHEMA.recurrent_width)
    state = initial_state
    steps: list[RolloutStep] = []
    reward_total = 0.0
    deployed_steps = 0
    eligible_steps = 0
    incremental_progress_proxy_m = 0.0
    incremental_speed_ms = 0.0
    attack_opportunities = 0
    defence_threats = 0
    requested_fraction_sum = 0.0
    for index, (speed, throttle, brake) in enumerate(zip(trace.speed_ms, trace.throttle, trace.brake)):
        speed = max(float(speed), 1.0)
        throttle = min(max(float(throttle), 0.0), 1.0)
        brake = min(max(float(brake), 0.0), 1.0)
        before_hidden = tuple(float(value) for value in hidden.flatten())
        if trace.race_context:
            ahead_gap_s = trace.ahead_gap_s[index]
            ahead_closing_ms = trace.ahead_closing_ms[index]
            behind_gap_s = trace.behind_gap_s[index]
            behind_closing_ms = trace.behind_closing_ms[index]
        else:
            ahead_gap_s = ahead_closing_ms = behind_gap_s = behind_closing_ms = 0.0
        opportunity, threat = classify_race_interaction(
            interaction_prior, ahead_gap_s, ahead_closing_ms,
            behind_gap_s, behind_closing_ms, braking=brake > 0.0,
        ) if trace.race_context else (False, False)
        attack_opportunities += int(opportunity)
        defence_threats += int(threat)
        remaining_laps_fraction = (
            (trace.total_laps - trace.lap_index + 1) / trace.total_laps if trace.race_context else 0.0
        )
        observation = (
            speed / 100.0, throttle, brake, state.stored_energy_j / prior.usable_store_j,
            ahead_gap_s, ahead_closing_ms / 20.0, behind_gap_s, behind_closing_ms / 20.0,
            remaining_laps_fraction,
        )
        features = torch.tensor(observation, dtype=torch.float32).reshape(1, 1, -1)
        feature_mask = torch.tensor((True, True, True, True) + (trace.race_context,) * 5, dtype=torch.bool).reshape(1, 1, -1)
        deployment_available = brake == 0.0 and throttle > 0.0 and state.stored_energy_j > 0.0
        action_mask_values = (True, deployment_available, deployment_available and trace.race_context and threat)
        action_mask = torch.tensor(action_mask_values, dtype=torch.bool).reshape(1, -1)
        with torch.no_grad():
            logits, alpha, beta, value, next_hidden = model(features, feature_mask, action_mask, hidden)
            manoeuvre_distribution = Categorical(logits=logits)
            manoeuvre_index = manoeuvre_distribution.sample()
            joint_log_probability = manoeuvre_distribution.log_prob(manoeuvre_index)
            if deployment_available:
                deployment_distribution = Beta(alpha, beta)
                deployment = deployment_distribution.sample().clamp(1e-6, 1.0 - 1e-6)
                joint_log_probability = joint_log_probability + deployment_distribution.log_prob(deployment)
                deployment_fraction = float(deployment)
                eligible_steps += 1
                requested_fraction_sum += deployment_fraction
            else:
                deployment_fraction = 0.0
        before_deployment_j = state.gross_deployment_j
        allocation = allocate_additive_power(
            prior, state, speed, throttle, brake, deployment_fraction,
            profile.maximum_drive_force_n, trace.step_s,
        )
        state = allocation.state
        deployment_j = state.gross_deployment_j - before_deployment_j
        if deployment_j > 0.0:
            deployed_steps += 1
        incremental_force_n = allocation.motor_wheel_power_w / speed
        incremental_speed_ms += incremental_force_n / 800.0 * trace.step_s
        incremental_progress_proxy_m += incremental_speed_ms * trace.step_s
        local_gain = incremental_force_n / 800.0 * trace.step_s
        maximum_motor_wheel_w = profile.maximum_drive_force_n * speed * prior.electric_boost_fraction
        delivered_fraction = allocation.motor_wheel_power_w / maximum_motor_wheel_w if maximum_motor_wheel_w > 0.0 else 0.0
        if trace.race_context:
            reward = race_step_reward(
                interaction_prior, delivered_fraction, deployment_j,
                remaining_laps_fraction, 1.0 / len(trace.speed_ms), opportunity, threat,
            )
            if index == len(trace.speed_ms) - 1:
                reserve_target = (trace.total_laps - trace.lap_index) / trace.total_laps
                reward += race_reserve_penalty(
                    interaction_prior, state.stored_energy_j / prior.usable_store_j, reserve_target,
                )
        else:
            reward = local_gain - 0.02 * deployment_j / 1_000_000.0
        reward_total += reward
        manoeuvre = _SCHEMA.manoeuvres[int(manoeuvre_index)]
        sampled = ActionRequest(manoeuvre, deployment_fraction)
        delivered = ActionRequest(manoeuvre, min(max(delivered_fraction, 0.0), 1.0))
        reasons = ("storage_limited",) if delivered.deployment_fraction + 1e-9 < deployment_fraction else ()
        steps.append(RolloutStep(
            observation,
            tuple(bool(value) for value in feature_mask.flatten()),
            ActionRecord(sampled, sampled, delivered, float(joint_log_probability), reasons),
            before_hidden,
            tuple(float(item) for item in next_hidden.flatten()),
            float(value),
            reward,
            index == len(trace.speed_ms) - 1,
            False,
            action_mask_values,
            deployment_available,
        ))
        hidden = next_hidden
    metrics = {
        "reward": reward_total,
        "deployed_steps": float(deployed_steps),
        "eligible_steps": float(eligible_steps),
        "incremental_progress_proxy_m": incremental_progress_proxy_m,
        "attack_opportunities": float(attack_opportunities),
        "defence_threats": float(defence_threats),
        "requested_fraction_sum": requested_fraction_sum,
    }
    return RecurrentFragment(tuple(steps), 0), state, metrics


def run_diagnostic_updates(
    traces: tuple[DiagnosticTrace, ...],
    profiles: dict[str, FittedProfile],
    prior: DeploymentPrior,
    updates: int,
    seed: int,
    model: RecurrentActorCritic | None = None,
    carry_energy_across_updates: bool = False,
    interaction_prior: RaceInteractionPrior | None = None,
    optimizer: torch.optim.Optimizer | None = None,
) -> dict[str, object]:
    """Run bounded PPO updates and return physical and optimizer evidence."""
    if not traces or updates < 1:
        raise ValueError("diagnostic updates require traces and a positive update count")
    torch.manual_seed(seed)
    model = model or create_diagnostic_model(seed)
    optimizer = optimizer or torch.optim.Adam(model.parameters(), lr=_CONFIG.learning_rate)
    episode_rewards: list[float] = []
    losses: list[float] = []
    aggregate_deployment_j = 0.0
    aggregate_harvest_j = 0.0
    aggregate_curtailment_j = 0.0
    deployed_steps = 0.0
    eligible_steps = 0.0
    progress_proxy_m = 0.0
    attack_opportunities = 0.0
    defence_threats = 0.0
    requested_fraction_sum = 0.0
    persistent_state = LapEnergyState.full(prior)
    interaction_prior = interaction_prior or RaceInteractionPrior()
    for update in range(updates):
        trace = traces[update % len(traces)]
        profile = profiles.get(trace.entry) or profiles.get("1")
        if profile is None:
            raise ValueError(f"no fitted profile for entry {trace.entry}")
        initial_state = persistent_state.next_lap() if carry_energy_across_updates else LapEnergyState.full(prior)
        before = initial_state
        fragment, final_state, metrics = _rollout(model, trace, profile, prior, initial_state, interaction_prior)
        record = ppo_update(model, optimizer, fragment, _CONFIG)
        losses.append(record.total_loss)
        episode_rewards.append(metrics["reward"])
        deployed_steps += metrics["deployed_steps"]
        eligible_steps += metrics["eligible_steps"]
        progress_proxy_m += metrics["incremental_progress_proxy_m"]
        attack_opportunities += metrics["attack_opportunities"]
        defence_threats += metrics["defence_threats"]
        requested_fraction_sum += metrics["requested_fraction_sum"]
        aggregate_deployment_j += final_state.gross_deployment_j - before.gross_deployment_j
        aggregate_harvest_j += final_state.gross_harvest_j - before.gross_harvest_j
        aggregate_curtailment_j += final_state.curtailed_energy_j - before.curtailed_energy_j
        if carry_energy_across_updates:
            persistent_state = final_state
    window = min(10, max(1, updates // 3))
    first_reward = mean(episode_rewards[:window])
    last_reward = mean(episode_rewards[-window:])
    deployment_rate = deployed_steps / eligible_steps if eligible_steps else 0.0
    mean_requested_fraction = requested_fraction_sum / eligible_steps if eligible_steps else 0.0
    remaining_store_j = persistent_state.stored_energy_j if carry_energy_across_updates else 0.0
    reward_findings: list[str] = []
    if mean_requested_fraction > 0.8:
        reward_findings.append("deployment saturated; add opportunity-cost or terminal-energy shaping for race use")
    if mean_requested_fraction < 0.1 and (not carry_energy_across_updates or remaining_store_j > prior.usable_store_j * 0.5):
        reward_findings.append("deployment was hoarded; increase local time-gain reward or reduce energy penalty")
    if carry_energy_across_updates and remaining_store_j == 0.0:
        reward_findings.append("store was exhausted; ten race updates did not yet adapt deployment to the shaped objective")
    return {
        "status": "diagnostic_only",
        "updates": updates,
        "source_partition": "training",
        "electric_boost_fraction": prior.electric_boost_fraction,
        "usable_store_j": prior.usable_store_j,
        "harvest_cap_j_per_lap": prior.harvest_cap_j_per_lap,
        "gross_deployment_j": aggregate_deployment_j,
        "gross_harvest_j": aggregate_harvest_j,
        "net_battery_change_j": aggregate_harvest_j * prior.harvest_efficiency - aggregate_deployment_j,
        "harvest_curtailed_j": aggregate_curtailment_j,
        "remaining_store_j": remaining_store_j if carry_energy_across_updates else None,
        "deployment_step_rate": deployment_rate,
        "mean_requested_deployment_fraction": mean_requested_fraction,
        "incremental_progress_proxy_m": progress_proxy_m,
        "attack_opportunity_steps": attack_opportunities,
        "defence_threat_steps": defence_threats,
        "mean_first_reward": first_reward,
        "mean_last_reward": last_reward,
        "reward_change": last_reward - first_reward,
        "mean_total_loss": mean(losses),
        "reward_findings": reward_findings,
        "race_interaction_prior": {
            "enabled": any(trace.race_context for trace in traces),
            "attack_gap_s": interaction_prior.attack_gap_s,
            "defend_gap_s": interaction_prior.defend_gap_s,
            "minimum_closing_ms": interaction_prior.minimum_closing_ms,
            "free_air_gain_weight": interaction_prior.free_air_gain_weight,
            "attack_gain_weight": interaction_prior.attack_gain_weight,
            "defend_gain_weight": interaction_prior.defend_gain_weight,
            "deployment_cost_per_mj": interaction_prior.deployment_cost_per_mj,
            "late_race_cost_floor": interaction_prior.late_race_cost_floor,
            "reserve_shortfall_weight": interaction_prior.reserve_shortfall_weight,
            "gain_normalization": "equal_share_per_lap_step",
        },
    }


def evaluate_diagnostic_policy(
    model: RecurrentActorCritic,
    traces: tuple[DiagnosticTrace, ...],
    profiles: dict[str, FittedProfile],
    prior: DeploymentPrior,
    seed: int,
    carry_energy_across_traces: bool = False,
    interaction_prior: RaceInteractionPrior | None = None,
) -> dict[str, float]:
    """Evaluate a policy without applying optimizer updates."""
    torch.manual_seed(seed)
    interaction_prior = interaction_prior or RaceInteractionPrior()
    rewards: list[float] = []
    deployment_j = 0.0
    harvest_j = 0.0
    progress_m = 0.0
    attack_steps = 0.0
    defence_steps = 0.0
    requested_fraction_sum = 0.0
    eligible_steps = 0.0
    persistent_state = LapEnergyState.full(prior)
    for trace in traces:
        profile = profiles.get(trace.entry) or profiles.get("1")
        if profile is None:
            raise ValueError(f"no fitted profile for entry {trace.entry}")
        initial_state = persistent_state.next_lap() if carry_energy_across_traces else LapEnergyState.full(prior)
        _, final_state, metrics = _rollout(model, trace, profile, prior, initial_state, interaction_prior)
        rewards.append(metrics["reward"])
        deployment_j += final_state.gross_deployment_j - initial_state.gross_deployment_j
        harvest_j += final_state.gross_harvest_j - initial_state.gross_harvest_j
        progress_m += metrics["incremental_progress_proxy_m"]
        attack_steps += metrics["attack_opportunities"]
        defence_steps += metrics["defence_threats"]
        requested_fraction_sum += metrics["requested_fraction_sum"]
        eligible_steps += metrics["eligible_steps"]
        if carry_energy_across_traces:
            persistent_state = final_state
    return {
        "mean_reward": mean(rewards),
        "gross_deployment_j": deployment_j,
        "gross_harvest_j": harvest_j,
        "incremental_progress_proxy_m": progress_m,
        "remaining_store_j": persistent_state.stored_energy_j if carry_energy_across_traces else 0.0,
        "attack_opportunity_steps": attack_steps,
        "defence_threat_steps": defence_steps,
        "mean_requested_deployment_fraction": requested_fraction_sum / eligible_steps if eligible_steps else 0.0,
    }
