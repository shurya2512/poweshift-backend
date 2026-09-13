"""Train the diagnostic policy through preseason and one race weekend."""

from hashlib import sha256
import json
from pathlib import Path

import torch

from poweshift_backend.energy.allocator import DeploymentPrior
from poweshift_backend.policy.curriculum import (
    load_curriculum_checkpoint,
    load_preseason_traces,
    load_promoted_profiles,
    load_qualifying_traces,
    load_race_traces,
    save_curriculum_checkpoint,
)
from poweshift_backend.policy.diagnostic import (
    DiagnosticTrace,
    RaceInteractionPrior,
    create_diagnostic_model,
    evaluate_diagnostic_policy,
    run_diagnostic_updates,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "policy_phase8" / "full_curriculum_preseason_australia_v2"
PRESEASON = ROOT / "data" / "preparation_verified_698aaed" / "reconstruction_inputs"
REPRESENTATION = ROOT / "data" / "representation_phase4"
PROFILE_PATH = REPRESENTATION / "race_full_weekend_japan_v1_diagnostic" / "promoted_profiles_v1.json"
QUALIFYING_FOLDER = REPRESENTATION / "qualifying_smoke_australia_v8_diagnostic"
RACE_BATCH_PATH = REPRESENTATION / "race_full_weekend_australia_v1_diagnostic" / "race_batches.pt"
RACE_REPORT_PATH = REPRESENTATION / "race_full_weekend_australia_v2_diagnostic" / "full_race.json"
PRESEASON_DAYS = ("2026-02-11", "2026-02-12", "2026-02-13")
SEED = 20260913


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _json_write_once(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _evaluation_delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {key: after[key] - before[key] for key in before if key in after}


def _run_stage(
    name: str,
    traces: tuple[DiagnosticTrace, ...],
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    profiles,
    prior: DeploymentPrior,
    interaction_prior: RaceInteractionPrior,
    completed_updates: int,
    sources: dict[str, str],
    seed: int,
    carry_energy: bool = False,
) -> tuple[dict[str, object], int]:
    checkpoint = OUTPUT / "checkpoints" / f"{name}.pt"
    report_path = OUTPUT / "reports" / f"{name}.json"
    expected_updates = completed_updates + len(traces)
    if checkpoint.exists() or report_path.exists():
        if not checkpoint.exists() or not report_path.exists():
            raise RuntimeError(f"stage {name} is incomplete and cannot be resumed safely")
        metadata = load_curriculum_checkpoint(checkpoint, model, optimizer)
        if metadata["stage"] != name or metadata["completed_updates"] != expected_updates:
            raise RuntimeError(f"stage {name} checkpoint metadata does not match")
        if metadata["sources"] != sources:
            raise RuntimeError(f"stage {name} source identities changed")
        print(f"resumed {name} at update {expected_updates}", flush=True)
        return json.loads(report_path.read_text()), expected_updates
    evaluation_traces = traces[: min(20, len(traces))] if not carry_energy else traces
    before = evaluate_diagnostic_policy(
        model, evaluation_traces, profiles, prior, seed,
        carry_energy_across_traces=carry_energy,
        interaction_prior=interaction_prior,
    )
    print(f"training {name}: {len(traces)} PPO updates", flush=True)
    training = run_diagnostic_updates(
        traces,
        profiles,
        prior,
        len(traces),
        seed + 1,
        model=model,
        carry_energy_across_updates=carry_energy,
        interaction_prior=interaction_prior,
        optimizer=optimizer,
    )
    after = evaluate_diagnostic_policy(
        model, evaluation_traces, profiles, prior, seed,
        carry_energy_across_traces=carry_energy,
        interaction_prior=interaction_prior,
    )
    report: dict[str, object] = {
        "status": "diagnostic_only",
        "stage": name,
        "stage_updates": len(traces),
        "completed_updates": expected_updates,
        "sources": sources,
        "evaluation_before": before,
        "training": training,
        "evaluation_after": after,
        "evaluation_delta": _evaluation_delta(before, after),
    }
    save_curriculum_checkpoint(checkpoint, model, optimizer, name, expected_updates, sources)
    _json_write_once(report_path, report)
    print(f"completed {name} at update {expected_updates}", flush=True)
    return report, expected_updates


def _verify_final_checkpoint(path: Path, expected_updates: int) -> dict[str, object]:
    model = create_diagnostic_model(SEED + 100)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    metadata = load_curriculum_checkpoint(path, model, optimizer)
    if metadata["completed_updates"] != expected_updates:
        raise RuntimeError("restricted checkpoint verification found an update mismatch")
    return {
        "restricted_load": True,
        "schema_id": model.schema.schema_id,
        "completed_updates": expected_updates,
        "checkpoint_sha256": _digest(path),
    }


def main() -> None:
    """Run or resume the fixed diagnostic curriculum."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "checkpoints").mkdir(exist_ok=True)
    (OUTPUT / "reports").mkdir(exist_ok=True)
    registry = load_promoted_profiles(PROFILE_PATH)
    profiles = registry.profiles
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    interaction_prior = RaceInteractionPrior()
    model = create_diagnostic_model(SEED)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    completed_updates = 0
    reports: list[dict[str, object]] = []
    profile_digest = _digest(PROFILE_PATH)
    singleton_packages = 0

    for index, day in enumerate(PRESEASON_DAYS, start=1):
        manifest_path = PRESEASON / f"stint_packages__{day}.json"
        table_path = PRESEASON / f"stint_packages__{day}.parquet"
        package_manifest = json.loads(manifest_path.read_text())
        singleton_packages += sum(
            package["end_time_s"] <= package["start_time_s"]
            for package in package_manifest["packages"]
        )
        traces = load_preseason_traces(manifest_path, table_path, profiles)
        sources = {
            "profile_registry": profile_digest,
            "package_manifest": _digest(manifest_path),
            "package_table": _digest(table_path),
        }
        report, completed_updates = _run_stage(
            f"0{index}-preseason-{day}", traces, model, optimizer, profiles, prior,
            interaction_prior, completed_updates, sources, SEED + index * 10,
        )
        reports.append(report)

    qualifying_path = QUALIFYING_FOLDER / "qualifying_batches.pt"
    qualifying_binding = QUALIFYING_FOLDER / "source_binding.json"
    qualifying = load_qualifying_traces(qualifying_path, qualifying_binding)
    qualifying_sources = {
        "profile_registry": profile_digest,
        "qualifying_batches": _digest(qualifying_path),
        "qualifying_binding": _digest(qualifying_binding),
    }
    qualifying_report, completed_updates = _run_stage(
        "04-australia-qualifying", qualifying, model, optimizer, profiles, prior,
        interaction_prior, completed_updates, qualifying_sources, SEED + 40,
    )
    reports.append(qualifying_report)

    race, route_length_m, race_speeds = load_race_traces(RACE_BATCH_PATH, RACE_REPORT_PATH, "1")
    race_sources = {
        "profile_registry": profile_digest,
        "race_batches": _digest(RACE_BATCH_PATH),
        "race_report": _digest(RACE_REPORT_PATH),
    }
    race_report, completed_updates = _run_stage(
        "05-australia-race", race, model, optimizer, profiles, prior,
        interaction_prior, completed_updates, race_sources, SEED + 50, carry_energy=True,
    )
    reports.append(race_report)

    final_checkpoint = OUTPUT / "checkpoints" / "05-australia-race.pt"
    verification = _verify_final_checkpoint(final_checkpoint, completed_updates)
    summary: dict[str, object] = {
        "status": "diagnostic_only",
        "curriculum": "preseason_test_1_then_australia_weekend",
        "total_ppo_updates": completed_updates,
        "preseason": {
            "dates": list(PRESEASON_DAYS),
            "package_updates": sum(int(report["stage_updates"]) for report in reports[:3]),
            "sampling": "64 chronological samples per admitted package",
            "step_duration": "package elapsed time divided by sampled intervals",
            "singleton_packages": singleton_packages,
            "singleton_handling": "repeat the measured row once at the diagnosed 0.24 s training cadence",
        },
        "race_weekend": {
            "event": "Australia",
            "qualifying_trace_updates": int(qualifying_report["stage_updates"]),
            "race_lap_updates": int(race_report["stage_updates"]),
            "race_ego_entry": "1",
            "route_length_m": route_length_m,
            "observed_race_speed_ms": {
                "median": float(torch.tensor(race_speeds).median()),
                "p90": float(torch.quantile(torch.tensor(race_speeds), 0.9)),
            },
        },
        "profile_registry": {
            "status": registry.status,
            "profile_admission_id": registry.admission_id,
            "active_profiles": len(profiles),
            "physics_admission": registry.physics_admitted,
            "user_authorization": "provisional promoted profiles accepted for this diagnostic run",
        },
        "energy_prior": {
            "maximum_electric_power_w": prior.maximum_electric_power_w,
            "usable_store_j": prior.usable_store_j,
            "harvest_cap_j_per_lap": prior.harvest_cap_j_per_lap,
            "motor_efficiency": prior.motor_efficiency,
            "harvest_efficiency": prior.harvest_efficiency,
        },
        "race_reward": race_report["training"]["race_interaction_prior"],
        "stage_reports": reports,
        "checkpoint_verification": verification,
        "protected_partitions": {
            "selection_2026-02-18": "unopened",
            "final_2026-02-19_to_2026-02-20": "unopened",
        },
        "limitations": [
            "The promoted profiles remain provisional and are not physically admitted.",
            "Japan-fitted provisional profiles are reused for the Australia diagnostic weekend.",
            "Preseason packages are reduced to 64 chronological samples with an elapsed-time step approximation.",
            "Traffic gaps are source-derived, while attack and defence labels use declared heuristic thresholds.",
            "Incremental progress is a force-derived proxy, not demonstrated lap time, position, or strategy superiority.",
        ],
    }
    summary_path = OUTPUT / "summary.json"
    if summary_path.exists():
        existing = json.loads(summary_path.read_text())
        if existing != summary:
            raise RuntimeError("existing immutable summary differs from the completed run")
    else:
        _json_write_once(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
