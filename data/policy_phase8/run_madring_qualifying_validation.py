"""Evaluate final profile policies on protected Madring qualifying controls."""

from hashlib import sha256
import json
from pathlib import Path
from statistics import median

import torch

from poweshift_backend.energy.allocator import DeploymentPrior
from poweshift_backend.policy.curriculum import (
    load_curriculum_checkpoint,
    load_promoted_profiles,
    load_qualifying_test_traces,
)
from poweshift_backend.policy.diagnostic import create_diagnostic_model
from poweshift_backend.policy.race_validation import validate_profile_policy


ROOT = Path(__file__).resolve().parents[2]
CURRICULUM = ROOT / "data/policy_phase8/multi_weekend_all_profiles_v1"
OUTPUT = ROOT / "data/policy_phase8/madring_qualifying_validation_v1"
MANIFEST = ROOT / "data/representation_phase4/qualifying_madring_test_v1/qualifying_test_export.json"
PROFILES = ROOT / "data/representation_phase4/race_full_weekend_japan_v1_diagnostic/promoted_profiles_v1.json"
SEED = 20260913


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_once(path: Path, payload: dict[str, object]) -> None:
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text() != content:
        raise RuntimeError(f"immutable Madring report differs: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def main() -> None:
    registry = load_promoted_profiles(PROFILES)
    entries = tuple(sorted(registry.profiles, key=int))
    data = load_qualifying_test_traces(MANIFEST, registry.profiles)
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    reports = {}
    for index, entry in enumerate(entries, start=1):
        checkpoint = CURRICULUM / "checkpoints/british" / f"entry-{entry}.pt"
        model = create_diagnostic_model(SEED + index)
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
        metadata = load_curriculum_checkpoint(checkpoint, model, optimizer)
        traces = data.traces_by_entry[entry]
        if traces:
            validation = validate_profile_policy(
                model, traces, registry.profiles[entry], prior,
            )
            coverage = "complete_accurate_qualifying_laps"
        else:
            validation = {
                "status": "diagnostic_only",
                "validation_laps": 0,
                "coverage": "no_complete_accurate_qualifying_laps_for_profile",
            }
            coverage = validation["coverage"]
        report = {
            "status": "diagnostic_only",
            "physics_admission": False,
            "partition": "final_evaluation",
            "event": "2026 Spanish Grand Prix",
            "circuit": "Madring",
            "session": "Qualifying",
            "profile_entry": entry,
            "coverage": coverage,
            "optimizer_updates": 0,
            "checkpoint_stage": metadata["stage"],
            "checkpoint_sha256": _digest(checkpoint),
            "source_manifest_sha256": _digest(MANIFEST),
            "validation": validation,
        }
        _write_once(OUTPUT / "reports" / f"entry-{entry}.json", report)
        reports[entry] = report
    covered = [row for row in reports.values() if row["validation"]["validation_laps"]]
    summary = {
        "status": "diagnostic_only",
        "physics_admission": False,
        "partition": "final_evaluation",
        "event": "2026 Spanish Grand Prix",
        "circuit": "Madring",
        "session": "Qualifying",
        "race_source_state": "not_available_at_acquisition",
        "profiles_requested": len(entries),
        "profiles_with_accurate_laps": len(covered),
        "profiles_without_accurate_laps": [
            entry for entry, row in reports.items() if not row["validation"]["validation_laps"]
        ],
        "qualifying_laps": sum(row["validation"]["validation_laps"] for row in covered),
        "source_ticks_4hz": sum(
            len(trace.speed_ms) for traces in data.traces_by_entry.values() for trace in traces
        ),
        "median_gross_deployment_j": median(
            row["validation"]["gross_deployment_j"] for row in covered
        ) if covered else None,
        "median_gross_harvest_j": median(
            row["validation"]["gross_harvest_j"] for row in covered
        ) if covered else None,
        "optimizer_updates": 0,
        "frontend_inference_contract": {
            "websocket": "/runs/{run_id}/live",
            "input_hz": 4.0,
            "decision_hz": 5.0,
            "input": "ObservationFrame",
            "output": "LiveRecommendationFrame",
            "held_input_flag": "held_source_frame",
            "registration_state": "awaiting_physics_and_energy_admission",
        },
        "reports": {entry: f"reports/entry-{entry}.json" for entry in entries},
        "limitations": [
            "Madring qualifying is protected evaluation data and produced no optimizer updates.",
            "Three promoted profile identities lack complete accurate qualifying laps in this source.",
            "The race had not been acquired, so no race tactics or P23 result is claimed for Madring.",
            "Frontend live registration remains blocked until the diagnostic policy receives admitted physics and energy identities.",
        ],
    }
    _write_once(OUTPUT / "summary.json", summary)
    print(json.dumps({
        "profiles_with_accurate_laps": len(covered),
        "qualifying_laps": summary["qualifying_laps"],
        "source_ticks_4hz": summary["source_ticks_4hz"],
        "summary": str(OUTPUT / "summary.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
