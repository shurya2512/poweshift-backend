"""Create event-bound P23 runtime reports for every later training race."""

from hashlib import sha256
import json
from pathlib import Path
from statistics import mean, median

import torch

from poweshift_backend.energy.allocator import DeploymentPrior
from poweshift_backend.policy.curriculum import (
    load_curriculum_checkpoint,
    load_native_race_data,
    load_promoted_profiles,
)
from poweshift_backend.policy.diagnostic import RaceInteractionPrior, create_diagnostic_model
from poweshift_backend.policy.race_validation import (
    P23ScenarioPrior,
    load_major_race_events,
    run_p23_diagnostic,
)


ROOT = Path(__file__).resolve().parents[2]
REPRESENTATION = ROOT / "data/representation_phase4"
CURRICULUM = ROOT / "data/policy_phase8/multi_weekend_all_profiles_v1"
OUTPUT = ROOT / "data/policy_phase8/runtime_inference_reports_v2/race"
PROFILES = REPRESENTATION / "race_full_weekend_japan_v1_diagnostic/promoted_profiles_v1.json"
SEED = 20260913
EVENTS = (
    ("Miami Grand Prix", "miami"),
    ("Canadian Grand Prix", "canadian"),
    ("Monaco Grand Prix", "monaco"),
    ("Barcelona Grand Prix", "barcelona"),
    ("Austrian Grand Prix", "austrian"),
    ("British Grand Prix", "british"),
)


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _write(path: Path, payload: dict[str, object]) -> None:
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text() != content:
        raise RuntimeError(f"immutable race report differs: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _complete_field_index(field_ticks, required: set[str]) -> int | None:
    return next((
        index for index, tick in enumerate(field_ticks)
        if all(set(dict(values)) == required for values in (
            tick.progress_by_entry,
            tick.speed_by_entry,
            tick.throttle_by_entry,
            tick.brake_by_entry,
        ))
    ), None)


def _metric(values, key: str) -> dict[str, float | None]:
    numbers = [float(value[key]) for value in values if value.get(key) is not None]
    return {
        "mean": mean(numbers) if numbers else None,
        "median": median(numbers) if numbers else None,
    }


def _track_summary(event_name: str, reports: dict[str, dict[str, object]], events) -> dict[str, object]:
    p23 = [report["p23"] for report in reports.values()]
    ranking = sorted(({
        "profile_entry": entry,
        "final_proxy_position": report["p23"]["final_proxy_position"],
        "final_progress_m": report["p23"]["final_progress_m"],
        "signed_gap_to_leader_s": report["p23"]["signed_gap_to_leader_s"],
        "gross_deployment_j": report["p23"]["gross_deployment_j"],
        "gross_harvest_j": report["p23"]["gross_harvest_j"],
        "final_stored_energy_j": report["p23"]["final_stored_energy_j"],
    } for entry, report in reports.items()), key=lambda row: (-row["final_progress_m"], int(row["profile_entry"])))
    opportunity = [row["opportunity_totals"] for row in p23]
    major = []
    for event_index, event in enumerate(events):
        decisions = [row["major_event_decisions"][event_index]["nearest_policy_decision"] for row in p23]
        major.append({
            "event": event,
            "profile_decisions": {
                entry: reports[entry]["p23"]["major_event_decisions"][event_index]["nearest_policy_decision"]
                for entry in sorted(reports, key=int)
            },
            "averages": {
                "uncalibrated_action_probability": _metric(decisions, "uncalibrated_action_probability"),
                "requested_deployment_fraction": _metric(decisions, "requested_deployment_fraction"),
                "motor_wheel_power_kw": _metric(decisions, "motor_wheel_power_kw"),
                "deployment_j": _metric(decisions, "deployment_j"),
                "harvest_j": _metric(decisions, "harvest_j"),
                "stored_energy_after_j": _metric(decisions, "stored_energy_after_j"),
            },
        })
    return {
        "status": "diagnostic_only",
        "physics_admission": False,
        "event_name": event_name,
        "starting_grid_position": 23,
        "profile_count": len(reports),
        "profile_scenario_ranking": ranking,
        "final_metrics": {
            "final_proxy_position": _metric(p23, "final_proxy_position"),
            "signed_gap_to_leader_m": _metric(p23, "signed_gap_to_leader_m"),
            "signed_gap_to_leader_s": _metric(p23, "signed_gap_to_leader_s"),
            "gross_deployment_j": _metric(p23, "gross_deployment_j"),
            "gross_harvest_j": _metric(p23, "gross_harvest_j"),
            "final_stored_energy_j": _metric(p23, "final_stored_energy_j"),
        },
        "overtake_decisions": {
            "attack_opportunities": sum(row["attack_episodes"] for row in opportunity),
            "attack_taken": sum(row["attack_taken"] for row in opportunity),
            "attack_missed": sum(row["attack_missed"] for row in opportunity),
            "defence_threats": sum(row["defence_episodes"] for row in opportunity),
            "defence_taken": sum(row["defence_taken"] for row in opportunity),
            "defence_missed": sum(row["defence_missed"] for row in opportunity),
        },
        "major_event_decisions": major,
        "probability_semantics": "uncalibrated_action_selection_probability",
        "ranking_semantics": "same_source_field_diagnostic_comparison_by_final_proxy_progress",
        "reports": {entry: f"reports/entry-{entry}.json" for entry in sorted(reports, key=int)},
    }


def main() -> None:
    registry = load_promoted_profiles(PROFILES)
    entries = tuple(sorted(registry.profiles, key=int))
    required = set(entries)
    prior = DeploymentPrior(0.20, 5_000_000.0, 5_000_000.0, 0.95, 0.8)
    scenario = P23ScenarioPrior(5.0, 800.0, 16_000.0)
    interaction = RaceInteractionPrior()
    index_rows = []
    for event_name, slug in EVENTS:
        race_path = REPRESENTATION / f"race_full_weekend_{slug}_v1_diagnostic/race_batches.pt"
        binding_path = REPRESENTATION / f"race_full_weekend_{slug}_v1_diagnostic/source_binding.json"
        native = load_native_race_data(race_path, binding_path, entries, allow_missing_entries=True)
        first_complete = _complete_field_index(native.field_ticks, required)
        if first_complete is None:
            summary = {
                "status": "unavailable",
                "physics_admission": False,
                "event_name": event_name,
                "reason": "no_source_tick_contains_all_22_fixed_reference_profiles",
                "optimizer_updates": 0,
            }
            _write(OUTPUT / slug / "summary.json", summary)
            index_rows.append({"event_name": event_name, "status": "unavailable", "summary": f"{slug}/summary.json"})
            print(f"unavailable race report {event_name}", flush=True)
            continue
        field_ticks = native.field_ticks[first_complete:]
        events = tuple(
            event for event in load_major_race_events(binding_path, field_ticks[-1].time_s)
            if event["time_s"] >= field_ticks[0].time_s
        )
        reports = {}
        for index, entry in enumerate(entries, start=1):
            checkpoint = CURRICULUM / "checkpoints/british" / f"entry-{entry}.pt"
            model = create_diagnostic_model(SEED + index)
            optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
            metadata = load_curriculum_checkpoint(checkpoint, model, optimizer)
            p23 = run_p23_diagnostic(
                model,
                field_ticks,
                registry.profiles,
                registry.profiles[entry],
                prior,
                scenario,
                interaction,
                native.route_length_m,
                events,
            )
            report = {
                "status": "diagnostic_only",
                "physics_admission": False,
                "event_name": event_name,
                "profile_entry": entry,
                "optimizer_updates": 0,
                "checkpoint_stage": metadata["stage"],
                "checkpoint_sha256": _digest(checkpoint),
                "race_artifact_sha256": _digest(race_path),
                "source_binding_sha256": _digest(binding_path),
                "p23": p23,
            }
            _write(OUTPUT / slug / "reports" / f"entry-{entry}.json", report)
            reports[entry] = report
            print(f"completed race report {slug} entry {entry}", flush=True)
        summary = _track_summary(event_name, reports, events)
        _write(OUTPUT / slug / "summary.json", summary)
        index_rows.append({"event_name": event_name, "status": "diagnostic_only", "summary": f"{slug}/summary.json"})
    _write(OUTPUT / "index.json", {
        "status": "diagnostic_only",
        "physics_admission": False,
        "tracks": index_rows,
        "energy_prior": {
            "additive_electric_wheel_power_fraction": 0.20,
            "usable_store_j": 5_000_000.0,
            "harvest_cap_j_per_lap": 5_000_000.0,
            "motor_efficiency": 0.95,
            "harvest_efficiency": 0.8,
        },
        "frontend_inference": {
            "websocket": "/runs/{run_id}/live",
            "input_hz": 4.0,
            "decision_hz": 5.0,
        },
        "limitations": [
            "Positions, gaps and attainable performance are diagnostic proxies, not physically admitted predictions.",
            "All 22 reference cars are policy-free and electric-free and do not react to the added ego.",
            "Major events are source-bound; each policy row is the nearest 5 Hz decision.",
        ],
    })
    _write(OUTPUT.parent / "index.json", {
        "status": "diagnostic_only",
        "physics_admission": False,
        "qualifying_index": "qualifying/index.json",
        "race_index": "race/index.json",
        "frontend_inference": {
            "websocket": "/runs/{run_id}/live",
            "input_hz": 4.0,
            "decision_hz": 5.0,
        },
    })


if __name__ == "__main__":
    main()
