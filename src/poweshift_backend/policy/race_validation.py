"""Deterministic race reports and independent grid-P23 diagnostics."""

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from statistics import median

import numpy as np
import pandas as pd
import torch
from torch.distributions import Beta, Categorical

from poweshift_backend.contracts.action import Manoeuvre
from poweshift_backend.energy.allocator import DeploymentPrior, LapEnergyState, allocate_additive_power
from poweshift_backend.policy.curriculum import RaceFieldTick
from poweshift_backend.policy.diagnostic import (
    DiagnosticDecision,
    DiagnosticTrace,
    FittedProfile,
    RaceInteractionPrior,
    classify_race_interaction,
    evaluate_diagnostic_trace,
    race_step_reward,
)
from poweshift_backend.policy.model import RecurrentActorCritic


_MAJOR_TRACK_STATUSES = {
    "2": "yellow",
    "4": "safety_car_deployed",
    "5": "red",
    "6": "vsc_deployed",
    "7": "vsc_ending",
}


@dataclass(frozen=True)
class P23ScenarioPrior:
    """Declared causal longitudinal assumptions for the extra ego."""

    decision_hz: float
    vehicle_mass_kg: float
    maximum_brake_force_n: float
    maximum_additive_speed_ms: float = 5.0

    def __post_init__(self) -> None:
        values = (
            self.decision_hz, self.vehicle_mass_kg,
            self.maximum_brake_force_n, self.maximum_additive_speed_ms,
        )
        if not all(isfinite(value) and value > 0.0 for value in values):
            raise ValueError("P23 scenario values must be positive and finite")


def _decision_payload(decision: DiagnosticDecision) -> dict[str, object]:
    return {
        "time_s": decision.time_s,
        "lap": decision.lap_index,
        "path": decision.manoeuvre.value,
        "uncalibrated_action_probability": decision.action_probability,
        "requested_deployment_fraction": decision.requested_deployment_fraction,
        "delivered_deployment_fraction": decision.delivered_deployment_fraction,
        "motor_wheel_power_kw": decision.motor_wheel_power_w / 1_000.0,
        "deployment_j": decision.deployment_j,
        "harvest_j": decision.harvest_j,
        "stored_energy_before_j": decision.stored_energy_before_j,
        "stored_energy_after_j": decision.stored_energy_after_j,
        "ahead_gap_s": decision.ahead_gap_s,
        "ahead_closing_ms": decision.ahead_closing_ms,
        "behind_gap_s": decision.behind_gap_s,
        "behind_closing_ms": decision.behind_closing_ms,
        "attack_opportunity": decision.attack_opportunity,
        "defence_threat": decision.defence_threat,
    }


def bounded_additive_lap_time_proxy(
    observed_lap_time_s: float,
    additive_power_fraction: float,
    mean_delivered_fraction: float,
) -> tuple[float, float]:
    """Bound an ideal lap-time proxy by the delivered additive-power ratio."""
    values = (observed_lap_time_s, additive_power_fraction, mean_delivered_fraction)
    if not all(isfinite(value) for value in values) or observed_lap_time_s <= 0.0:
        raise ValueError("lap-time proxy values must be finite and observed time positive")
    if additive_power_fraction < 0.0 or not 0.0 <= mean_delivered_fraction <= 1.0:
        raise ValueError("lap-time proxy fractions are outside bounds")
    attainable = observed_lap_time_s / (1.0 + additive_power_fraction * mean_delivered_fraction)
    return attainable, observed_lap_time_s - attainable


def _sha256(path: Path) -> str:
    value = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load_major_race_events(
    binding_path: Path,
    end_time_s: float | None = None,
) -> tuple[dict[str, object], ...]:
    """Load hash-verified track-status events relative to the race start."""
    binding = json.loads(binding_path.read_text())
    manifest_path = Path(binding["acquisition_manifest"])
    if _sha256(manifest_path) != binding["acquisition_manifest_sha256"]:
        raise ValueError("race acquisition manifest hash changed")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("identity", {}).get("session_kind") != "race":
        raise ValueError("major event report requires a race source")
    exports = manifest["exports"]
    paths: dict[str, Path] = {}
    for name in ("laps", "track_status"):
        path = Path(exports[name]["path"])
        if _sha256(path) != exports[name]["sha256"]:
            raise ValueError(f"race {name} export hash changed")
        paths[name] = path
    laps = pd.read_parquet(paths["laps"], columns=["LapStartTime"])
    track = pd.read_parquet(paths["track_status"])
    race_start = laps["LapStartTime"].dropna().min()
    if pd.isna(race_start):
        raise ValueError("race source has no lap start")
    events: list[dict[str, object]] = []
    for row in track.itertuples(index=False):
        label = _MAJOR_TRACK_STATUSES.get(str(row.Status))
        if label is None or pd.isna(row.Time):
            continue
        time_s = float((row.Time - race_start).total_seconds())
        if time_s < 0.0 or (end_time_s is not None and time_s > end_time_s):
            continue
        detail = getattr(row, "Message", None)
        events.append({
            "time_s": time_s,
            "label": label,
            "detail": None if pd.isna(detail) else str(detail),
            "source_row": int(row.source_row),
        })
    return tuple(events)


def load_source_pit_strategy(binding_path: Path, entry: str) -> dict[str, object]:
    """Load one entry's recorded stints and pit laps from the hash-verified lap export."""
    binding = json.loads(binding_path.read_text())
    manifest_path = Path(binding["acquisition_manifest"])
    if _sha256(manifest_path) != binding["acquisition_manifest_sha256"]:
        raise ValueError("race acquisition manifest hash changed")
    manifest = json.loads(manifest_path.read_text())
    export = manifest["exports"]["laps"]
    path = Path(export["path"])
    if _sha256(path) != export["sha256"]:
        raise ValueError("race laps export hash changed")
    columns = ["DriverNumber", "LapNumber", "Stint", "Compound", "TyreLife", "PitInTime", "PitOutTime", "LapStartTime"]
    laps = pd.read_parquet(path, columns=columns)
    race_start = laps["LapStartTime"].dropna().min()
    rows = laps[laps["DriverNumber"].astype(str) == str(entry)].sort_values("LapNumber")
    if rows.empty:
        return {"entry": entry, "status": "unavailable", "stints": [], "pit_laps": []}
    stints: list[dict[str, object]] = []
    for stint, group in rows.groupby("Stint", sort=True):
        compound = group["Compound"].dropna()
        ages = group["TyreLife"].dropna()
        stints.append({
            "stint": int(stint),
            "compound": str(compound.iloc[0]) if not compound.empty else "UNKNOWN",
            "from_lap": int(group["LapNumber"].min()),
            "to_lap": int(group["LapNumber"].max()),
            "end_tyre_life_laps": int(ages.max()) if not ages.empty else None,
        })
    pit_laps = []
    for row in rows.itertuples(index=False):
        if pd.isna(row.PitInTime):
            continue
        pit_laps.append({
            "lap": int(row.LapNumber),
            "pit_in_time_s": float((row.PitInTime - race_start).total_seconds()) if not pd.isna(race_start) else None,
        })
    return {
        "entry": entry,
        "status": "source_bound",
        "stints": stints,
        "pit_laps": pit_laps,
        "total_source_laps": int(rows["LapNumber"].max()),
    }


def load_source_route_geometry(binding_path: Path, point_limit: int = 400) -> dict[str, object]:
    """Load the track's recorded metric centreline from its static route artifact."""
    binding = json.loads(binding_path.read_text())
    route_path = Path(binding["route_manifest"])
    if _sha256(route_path) != binding["route_manifest_sha256"]:
        raise ValueError("static route manifest hash changed")
    manifest = json.loads(route_path.read_text())
    arrays_path = route_path.parent / manifest["arrays_path"]
    if _sha256(arrays_path) != manifest["arrays_sha256"]:
        raise ValueError("static route arrays hash changed")
    with np.load(arrays_path) as arrays:
        x = np.asarray(arrays["x_m"], dtype=float)
        y = np.asarray(arrays["y_m"], dtype=float)
        progress = np.asarray(arrays["progress_m"], dtype=float)
    step = max(1, len(x) // point_limit)
    return {
        "status": "source_bound",
        "closed": bool(manifest.get("closed", False)),
        "loop_closure_m": float(manifest.get("loop_closure_m", float("nan"))),
        "lap_length_m": float(progress[-1]),
        "point_count": int(len(x[::step])),
        "x_m": [round(value, 2) for value in x[::step]],
        "y_m": [round(value, 2) for value in y[::step]],
        "progress_m": [round(value, 2) for value in progress[::step]],
    }


def _episode_rows(
    decisions: tuple[DiagnosticDecision, ...],
    kind: str,
) -> list[dict[str, object]]:
    active = (
        (lambda row: row.attack_opportunity) if kind == "attack"
        else (lambda row: row.defence_threat)
    )
    matching = Manoeuvre.ATTACK if kind == "attack" else Manoeuvre.DEFEND
    groups: list[list[DiagnosticDecision]] = []
    current: list[DiagnosticDecision] = []
    for decision in decisions:
        if active(decision):
            if current and decision.lap_index != current[-1].lap_index:
                groups.append(current)
                current = []
            current.append(decision)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    rows: list[dict[str, object]] = []
    for group in groups:
        taken = any(item.manoeuvre is matching for item in group)
        rows.append({
            "kind": kind,
            "lap": group[0].lap_index,
            "start_time_s": group[0].time_s,
            "end_time_s": group[-1].time_s,
            "ticks": len(group),
            "taken": taken,
            "selected_paths": sorted({item.manoeuvre.value for item in group}),
            "maximum_uncalibrated_action_probability": max(item.action_probability for item in group),
            "mean_requested_deployment_fraction": sum(item.requested_deployment_fraction for item in group) / len(group),
            "mean_delivered_deployment_fraction": sum(item.delivered_deployment_fraction for item in group) / len(group),
            "peak_motor_wheel_power_kw": max(item.motor_wheel_power_w for item in group) / 1_000.0,
            "deployment_j": sum(item.deployment_j for item in group),
            "harvest_j": sum(item.harvest_j for item in group),
            "stored_energy_start_j": group[0].stored_energy_before_j,
            "stored_energy_end_j": group[-1].stored_energy_after_j,
        })
    return rows


def _action_episodes(decisions: tuple[DiagnosticDecision, ...]) -> list[dict[str, object]]:
    groups: list[list[DiagnosticDecision]] = []
    current: list[DiagnosticDecision] = []
    for decision in decisions:
        if decision.manoeuvre in (Manoeuvre.ATTACK, Manoeuvre.DEFEND):
            if current and (
                decision.manoeuvre is not current[-1].manoeuvre
                or decision.lap_index != current[-1].lap_index
            ):
                groups.append(current)
                current = []
            current.append(decision)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return [{
        "path": group[0].manoeuvre.value,
        "lap": group[0].lap_index,
        "start_time_s": group[0].time_s,
        "end_time_s": group[-1].time_s,
        "ticks": len(group),
        "maximum_uncalibrated_action_probability": max(item.action_probability for item in group),
        "deployment_j": sum(item.deployment_j for item in group),
        "harvest_j": sum(item.harvest_j for item in group),
        "peak_motor_wheel_power_kw": max(item.motor_wheel_power_w for item in group) / 1_000.0,
        "attack_opportunity_present": any(item.attack_opportunity for item in group),
        "defence_threat_present": any(item.defence_threat for item in group),
    } for group in groups]


def _lap_rows(decisions: tuple[DiagnosticDecision, ...]) -> list[dict[str, object]]:
    grouped: dict[int, list[DiagnosticDecision]] = {}
    for decision in decisions:
        grouped.setdefault(decision.lap_index, []).append(decision)
    rows: list[dict[str, object]] = []
    for lap, group in sorted(grouped.items()):
        requested = [item.requested_deployment_fraction for item in group]
        rows.append({
            "lap": lap,
            "start_time_s": group[0].time_s,
            "end_time_s": group[-1].time_s,
            "start_position": group[0].observed_position,
            "end_position": group[-1].observed_position,
            "start_progress_m": group[0].observed_progress_m,
            "end_progress_m": group[-1].observed_progress_m,
            "reward": sum(item.reward for item in group),
            "deployment_j": sum(item.deployment_j for item in group),
            "harvest_j": sum(item.harvest_j for item in group),
            "stored_energy_start_j": group[0].stored_energy_before_j,
            "stored_energy_end_j": group[-1].stored_energy_after_j,
            "mean_requested_deployment_fraction": sum(requested) / len(requested),
            "maximum_motor_wheel_power_kw": max(item.motor_wheel_power_w for item in group) / 1_000.0,
            "attack_opportunity_ticks": sum(item.attack_opportunity for item in group),
            "attack_ticks": sum(item.manoeuvre is Manoeuvre.ATTACK for item in group),
            "defence_threat_ticks": sum(item.defence_threat for item in group),
            "defend_ticks": sum(item.manoeuvre is Manoeuvre.DEFEND for item in group),
        })
    return rows


def _report_decisions(decisions: tuple[DiagnosticDecision, ...]) -> dict[str, object]:
    attack = _episode_rows(decisions, "attack")
    defence = _episode_rows(decisions, "defence")
    return {
        "laps": _lap_rows(decisions),
        "opportunity_episodes": attack + defence,
        "policy_action_episodes": _action_episodes(decisions),
        "opportunity_totals": {
            "attack_episodes": len(attack),
            "attack_taken": sum(bool(row["taken"]) for row in attack),
            "attack_missed": sum(not bool(row["taken"]) for row in attack),
            "defence_episodes": len(defence),
            "defence_taken": sum(bool(row["taken"]) for row in defence),
            "defence_missed": sum(not bool(row["taken"]) for row in defence),
        },
    }


def validate_profile_policy(
    model: RecurrentActorCritic,
    traces: tuple[DiagnosticTrace, ...],
    profile: FittedProfile,
    prior: DeploymentPrior,
    warmup_traces: tuple[DiagnosticTrace, ...] = (),
    interaction_prior: RaceInteractionPrior | None = None,
) -> dict[str, object]:
    """Validate withheld laps after a deterministic causal warmup."""
    if not traces:
        raise ValueError("profile validation requires withheld traces")
    interaction = interaction_prior or RaceInteractionPrior()
    state = LapEnergyState.full(prior)
    hidden: torch.Tensor | None = None
    for trace in warmup_traces:
        result = evaluate_diagnostic_trace(model, trace, profile, prior, state, interaction, hidden)
        state = result.final_state.next_lap()
        hidden = result.final_hidden
    decisions: list[DiagnosticDecision] = []
    for trace in traces:
        result = evaluate_diagnostic_trace(model, trace, profile, prior, state, interaction, hidden)
        decisions.extend(result.decisions)
        state = result.final_state.next_lap()
        hidden = result.final_hidden
    report = _report_decisions(tuple(decisions))
    report.update({
        "status": "diagnostic_only",
        "entry": profile.entry,
        "validation_laps": len(traces),
        "warmup_laps": len(warmup_traces),
        "probability_semantics": "uncalibrated_action_selection_probability",
        "gross_deployment_j": sum(item.deployment_j for item in decisions),
        "gross_harvest_j": sum(item.harvest_j for item in decisions),
        "final_stored_energy_j": state.stored_energy_j,
    })
    return report


def _select_action(
    model: RecurrentActorCritic,
    observation: tuple[float, ...],
    hidden: torch.Tensor | None,
    deployment_available: bool,
    defence_available: bool,
) -> tuple[Manoeuvre, float, float, torch.Tensor]:
    features = torch.tensor(observation, dtype=torch.float32).reshape(1, 1, -1)
    feature_mask = torch.ones_like(features, dtype=torch.bool)
    action_mask = torch.tensor((True, deployment_available, defence_available), dtype=torch.bool).reshape(1, -1)
    with torch.no_grad():
        logits, alpha, beta, _, next_hidden = model(features, feature_mask, action_mask, hidden)
        manoeuvre_distribution = Categorical(logits=logits)
        index = int(manoeuvre_distribution.probs.argmax(dim=-1).item())
        probability = float(manoeuvre_distribution.probs[0, index].item())
        deployment = float(Beta(alpha, beta).mean.item()) if deployment_available else 0.0
    return model.schema.manoeuvres[index], probability, deployment, next_hidden.detach()


def _field_hz(field_ticks: tuple[RaceFieldTick, ...]) -> float:
    intervals = [after.time_s - before.time_s for before, after in zip(field_ticks, field_ticks[1:])]
    if not intervals or min(intervals) <= 0.0:
        raise ValueError("P23 diagnostic requires ordered source field ticks")
    return 1.0 / median(intervals)


def _nearest_traffic(
    ego_progress: float,
    ego_speed: float,
    progress: dict[str, float],
    speed: dict[str, float],
    route_length_m: float,
    own_entry: str | None = None,
) -> tuple[float, float, float, float]:
    """Nearest lap-wrapped traffic ahead and behind the ego's on-track position."""
    ego_on_track = ego_progress % route_length_m
    ahead: list[tuple[float, float]] = []
    behind: list[tuple[float, float]] = []
    for entry, value in progress.items():
        if entry == own_entry:
            continue
        other_on_track = value % route_length_m
        forward = (other_on_track - ego_on_track) % route_length_m
        backward = (ego_on_track - other_on_track) % route_length_m
        if forward > 0.0:
            ahead.append((forward, speed[entry]))
        if backward > 0.0:
            behind.append((backward, speed[entry]))
    ahead_distance, ahead_speed = min(ahead, default=(10_000.0, ego_speed))
    behind_distance, behind_speed = min(behind, default=(10_000.0, ego_speed))
    return (
        ahead_distance / max(ego_speed, 1.0),
        max(0.0, ego_speed - ahead_speed),
        behind_distance / max(behind_speed, 1.0),
        max(0.0, behind_speed - ego_speed),
    )


def run_p23_diagnostic(
    model: RecurrentActorCritic,
    field_ticks: tuple[RaceFieldTick, ...],
    reference_profiles: dict[str, FittedProfile],
    profile: FittedProfile,
    prior: DeploymentPrior,
    scenario: P23ScenarioPrior,
    interaction_prior: RaceInteractionPrior | None = None,
    route_length_m: float = 5_000.0,
    major_events: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    """Advance an independent ego against held source-native field evidence."""
    if len(field_ticks) < 2 or route_length_m <= 0.0:
        raise ValueError("P23 diagnostic needs field history and a route length")
    interaction = interaction_prior or RaceInteractionPrior()
    source_hz = _field_hz(field_ticks)
    first_progress = dict(field_ticks[0].progress_by_entry)
    first_speed = dict(field_ticks[0].speed_by_entry)
    first_throttle = dict(field_ticks[0].throttle_by_entry)
    first_brake = dict(field_ticks[0].brake_by_entry)
    identities = tuple(sorted(first_progress))
    if not identities or any(set(values) != set(first_progress) for values in (
        first_speed, first_throttle, first_brake, reference_profiles,
    )):
        raise ValueError("reference field identities, controls and profiles differ")
    if profile.entry not in first_progress:
        raise ValueError("P23 diagnostic needs the ego profile in the reference field")
    ordered_progress = sorted(first_progress.values(), reverse=True)
    adjacent = [before - after for before, after in zip(ordered_progress, ordered_progress[1:]) if before > after]
    tail_gap_m = median(adjacent) if adjacent else max(5.0, median(first_speed.values()) / source_hz)
    grid_offset_m = first_progress[profile.entry] - min(first_progress.values()) + tail_gap_m
    ego_progress = first_progress[profile.entry] - grid_offset_m
    ego_speed = first_speed[profile.entry]
    initial_progress = ego_progress
    additive_progress_m = 0.0
    ego_evidence_end_s = max(
        (tick.time_s for tick in field_ticks if profile.entry in dict(tick.speed_by_entry)),
        default=field_ticks[0].time_s,
    )
    state = LapEnergyState.full(prior)
    hidden: torch.Tensor | None = None
    field_progress = first_progress.copy()
    field_speed = first_speed.copy()
    field_throttle = first_throttle.copy()
    field_brake = first_brake.copy()
    frame_index = 0
    start_time = field_ticks[0].time_s
    end_time = field_ticks[-1].time_s
    dt = 1.0 / scenario.decision_hz
    decision_count = int((end_time - start_time) * scenario.decision_hz) + 1
    decisions: list[DiagnosticDecision] = []
    current_lap = 1
    stale_decisions = 0
    held_baseline_decisions = 0
    baseline_speed = ego_speed
    for step in range(decision_count):
        time_s = min(end_time, start_time + step * dt)
        if time_s > ego_evidence_end_s + 1e-9:
            break
        while frame_index + 1 < len(field_ticks) and field_ticks[frame_index + 1].time_s <= time_s + 1e-9:
            frame_index += 1
            field_throttle.update(dict(field_ticks[frame_index].throttle_by_entry))
            field_brake.update(dict(field_ticks[frame_index].brake_by_entry))
        stale_decisions += int(field_ticks[frame_index].time_s < time_s - 1e-9)
        field_progress.update(dict(field_ticks[frame_index].progress_by_entry))
        field_speed.update(dict(field_ticks[frame_index].speed_by_entry))
        # Without a current sample the ego coasts at its last speed rather than holding a stale pedal.
        own_sample = dict(field_ticks[frame_index].speed_by_entry)
        if profile.entry in own_sample:
            baseline_speed = field_speed[profile.entry]
            baseline_throttle = field_throttle[profile.entry]
            baseline_brake = field_brake[profile.entry]
        else:
            baseline_throttle = 0.0
            baseline_brake = 0.0
            held_baseline_decisions += 1
        ahead_gap_s, ahead_closing, behind_gap_s, behind_closing = _nearest_traffic(
            ego_progress, ego_speed, field_progress, field_speed, route_length_m, profile.entry,
        )
        opportunity, threat = classify_race_interaction(
            interaction, ahead_gap_s, ahead_closing, behind_gap_s, behind_closing, baseline_brake > 0.0,
        )
        remaining = max(0.0, (decision_count - step) / decision_count)
        observation = (
            ego_speed / 100.0, baseline_throttle, baseline_brake, state.stored_energy_j / prior.usable_store_j,
            ahead_gap_s, ahead_closing / 20.0, behind_gap_s, behind_closing / 20.0, remaining,
        )
        deployment_available = baseline_brake == 0.0 and baseline_throttle > 0.0 and state.stored_energy_j > 0.0
        manoeuvre, probability, requested_fraction, hidden = _select_action(
            model, observation, hidden, deployment_available, deployment_available and threat,
        )
        before = state
        allocation = allocate_additive_power(
            prior, state, max(baseline_speed, 1.0), baseline_throttle, baseline_brake, requested_fraction,
            profile.maximum_drive_force_n, profile.maximum_brake_force_n, dt,
        )
        state = allocation.state
        deployment_j = state.gross_deployment_j - before.gross_deployment_j
        harvest_j = state.gross_harvest_j - before.gross_harvest_j
        delivered_fraction = allocation.motor_wheel_power_w / prior.maximum_electric_power_w
        additive_speed_ms = 0.0
        if allocation.ice_wheel_power_w > 0.0 and allocation.motor_wheel_power_w > 0.0:
            power_ratio = 1.0 + allocation.motor_wheel_power_w / allocation.ice_wheel_power_w
            additive_speed_ms = min(
                scenario.maximum_additive_speed_ms,
                baseline_speed * (power_ratio ** (1.0 / 3.0) - 1.0),
            )
        ego_speed = baseline_speed + additive_speed_ms
        additive_progress_m += additive_speed_ms * dt
        next_progress = field_progress[profile.entry] - grid_offset_m + additive_progress_m
        position = 1 + sum(value > ego_progress for value in field_progress.values())
        reward = race_step_reward(
            interaction, delivered_fraction, deployment_j, remaining,
            1.0 / decision_count, opportunity, threat, manoeuvre,
        )
        decisions.append(DiagnosticDecision(
            time_s, current_lap, step, ego_progress, position, manoeuvre, probability,
            requested_fraction, min(1.0, max(0.0, delivered_fraction)), allocation.motor_wheel_power_w,
            deployment_j, harvest_j, before.stored_energy_j, state.stored_energy_j,
            ahead_gap_s, ahead_closing, behind_gap_s, behind_closing, opportunity, threat, reward,
        ))
        crossed_lap = int((next_progress - initial_progress) // route_length_m) + 1
        if crossed_lap > current_lap:
            state = state.next_lap()
            current_lap = crossed_lap
        ego_progress = next_progress
    retired_reference_entries = sum(
        1 for entry in identities if entry not in dict(field_ticks[-1].progress_by_entry)
    )
    final_position = 1 + sum(value > ego_progress for value in field_progress.values())
    leader_entry = max(field_progress, key=field_progress.get)
    leader_progress = field_progress[leader_entry]
    signed_gap_m = ego_progress - leader_progress
    reported = _report_decisions(tuple(decisions))
    attack = next((item for item in decisions if item.manoeuvre is Manoeuvre.ATTACK), None)
    event_decisions = []
    for event in major_events:
        nearest = min(decisions, key=lambda item: abs(item.time_s - float(event["time_s"])))
        event_decisions.append({
            "event": dict(event),
            "nearest_policy_decision": _decision_payload(nearest),
            "decision_time_delta_s": round(nearest.time_s - float(event["time_s"]), 9),
        })
    reported.update({
        "status": "diagnostic_only",
        "physics_admission": False,
        "ego_identity": f"policy-profile-{profile.entry}-p23",
        "profile_entry": profile.entry,
        "starting_grid_position": 23,
        "reference_entries": len(identities),
        "reference_identities": list(identities),
        "reference_mode": "source_native_reference_field_replay",
        "reference_policy_actions": 0,
        "reference_electric_deployment_j": 0.0,
        "retired_reference_entries": retired_reference_entries,
        "field_input_hz": source_hz,
        "decision_hz": scenario.decision_hz,
        "input_hold": "latest_source_sample",
        "ego_baseline": "own_profile_source_telemetry",
        "traffic_excludes_own_reference_entry": True,
        "held_ego_baseline_decisions": held_baseline_decisions,
        "maximum_additive_speed_ms": scenario.maximum_additive_speed_ms,
        "causal_demand_controller": "own_profile_source_telemetry_with_bounded_additive_power",
        "tail_gap_prior_m": tail_gap_m,
        "grid_offset_m": grid_offset_m,
        "additive_progress_m": additive_progress_m,
        "ego_evidence_end_s": ego_evidence_end_s,
        "ego_covered_span_s": ego_evidence_end_s - start_time,
        "ego_covered_span_fraction": (ego_evidence_end_s - start_time) / (end_time - start_time),
        "evidence_status": (
            "full_span" if ego_evidence_end_s >= end_time - 60.0 else "partial_span"
        ),
        "vehicle_mass_kg": scenario.vehicle_mass_kg,
        "maximum_brake_force_n": scenario.maximum_brake_force_n,
        "decision_ticks": len(decisions),
        "held_input_ticks": stale_decisions,
        "final_proxy_position": final_position,
        "final_progress_m": ego_progress,
        "signed_gap_to_leader_m": signed_gap_m,
        "signed_gap_to_leader_s": signed_gap_m / max(field_speed[leader_entry], 1.0),
        "gross_deployment_j": state.gross_deployment_j,
        "gross_harvest_j": state.gross_harvest_j,
        "final_stored_energy_j": state.stored_energy_j,
        "probability_semantics": "uncalibrated_action_selection_probability",
        "first_attack": _decision_payload(attack) if attack else None,
        "first_attack_absence_reason": None if attack else "policy_never_selected_attack",
        "major_event_decisions": event_decisions,
        "limitations": [
            "The final position and gaps are diagnostic proxies, not physically validated race outcomes.",
            "Reference cars simulate past-only source controls and do not react to the independent ego.",
            "The ego tracks its own profile's source position offset to P23; only the bounded electric gain adds distance.",
            "A partial_span report means the profile's own telemetry ends before the race does, so its race is cut to the evidence.",
            "The loaded checkpoint was trained under the old, broken energy model; this inference uses corrected physics, but the learned behaviour was shaped by an energy budget the car never actually had.",
        ],
    })
    return reported


def consolidate_profile_reports(reports: dict[str, dict[str, object]]) -> dict[str, object]:
    """Recompute cross-profile rankings, gaps and energy medians."""
    if not reports:
        raise ValueError("consolidation requires profile reports")
    ranking = sorted(({
        "profile_entry": entry,
        "final_proxy_position": int(report["p23"]["final_proxy_position"]),
        "final_progress_m": float(report["p23"]["final_progress_m"]),
        "signed_gap_to_leader_m": float(report["p23"]["signed_gap_to_leader_m"]),
        "signed_gap_to_leader_s": float(report["p23"]["signed_gap_to_leader_s"]),
        "gross_deployment_j": float(report["p23"]["gross_deployment_j"]),
        "gross_harvest_j": float(report["p23"]["gross_harvest_j"]),
    } for entry, report in reports.items()), key=lambda row: (-row["final_progress_m"], row["profile_entry"]))
    p23 = reports.get("23", {}).get("p23", {})
    deployment = [row["gross_deployment_j"] for row in ranking]
    harvest = [row["gross_harvest_j"] for row in ranking]
    gaps = [row["signed_gap_to_leader_m"] for row in ranking]
    gap_seconds = [row["signed_gap_to_leader_s"] for row in ranking]
    validation_deployment = [float(report["validation"]["gross_deployment_j"]) for report in reports.values()]
    validation_harvest = [float(report["validation"]["gross_harvest_j"]) for report in reports.values()]
    validation_lap_deployment = [
        float(lap["deployment_j"])
        for report in reports.values()
        for lap in report["validation"]["laps"]
    ]
    validation_lap_harvest = [
        float(lap["harvest_j"])
        for report in reports.values()
        for lap in report["validation"]["laps"]
    ]
    p23_lap_deployment = [
        float(lap["deployment_j"])
        for report in reports.values()
        for lap in report["p23"]["laps"]
    ]
    p23_lap_harvest = [
        float(lap["harvest_j"])
        for report in reports.values()
        for lap in report["p23"]["laps"]
    ]
    return {
        "status": "diagnostic_only",
        "profile_count": len(reports),
        "profile_scenario_ranking": ranking,
        "profile_23_first_attack": p23.get("first_attack"),
        "profile_23_first_attack_absence_reason": p23.get("first_attack_absence_reason"),
        "medians": {
            "p23_gross_deployment_j": median(deployment),
            "p23_gross_harvest_j": median(harvest),
            "p23_signed_gap_to_leader_m": median(gaps),
            "p23_signed_gap_to_leader_s": median(gap_seconds),
            "withheld_profile_gross_deployment_j": median(validation_deployment),
            "withheld_profile_gross_harvest_j": median(validation_harvest),
        },
        "lap_medians": {
            "withheld_deployment_j": median(validation_lap_deployment) if validation_lap_deployment else None,
            "withheld_harvest_j": median(validation_lap_harvest) if validation_lap_harvest else None,
            "p23_deployment_j": median(p23_lap_deployment) if p23_lap_deployment else None,
            "p23_harvest_j": median(p23_lap_harvest) if p23_lap_harvest else None,
        },
        "ranking_semantics": "independent_same-field_scenario_comparison_by_final_proxy_progress",
        "physics_admission": False,
    }
