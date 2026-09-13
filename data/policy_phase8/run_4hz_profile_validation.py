"""Train and validate every promoted profile on the native 4 Hz race."""

from hashlib import sha256
import json
from pathlib import Path

import torch

from poweshift_backend.energy.allocator import DeploymentPrior
from poweshift_backend.policy.curriculum import (
    load_curriculum_checkpoint,
    load_native_race_data,
    load_promoted_profiles,
    save_curriculum_checkpoint,
    split_race_traces,
)
from poweshift_backend.policy.diagnostic import RaceInteractionPrior, create_diagnostic_model, run_diagnostic_updates
from poweshift_backend.policy.race_validation import (
    P23ScenarioPrior,
    consolidate_profile_reports,
    run_p23_diagnostic,
    validate_profile_policy,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "policy_phase8" / "race_4hz_all_profiles_v1"
REPRESENTATION = ROOT / "data" / "representation_phase4" / "race_full_weekend_japan_v1_diagnostic"
PROFILE_PATH = REPRESENTATION / "promoted_profiles_v1.json"
RACE_BATCH_PATH = REPRESENTATION / "race_batches.pt"
RACE_REPORT_PATH = REPRESENTATION / "full_race.json"
BASE_CHECKPOINT = (
    ROOT / "data" / "policy_phase8" / "full_curriculum_preseason_australia_v2"
    / "checkpoints" / "04-australia-qualifying.pt"
)
SEED = 20260913


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _write_once(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _split_manifest(native, entries: tuple[str, ...]) -> dict[str, object]:
    profiles: dict[str, object] = {}
    for entry in entries:
        training, validation = split_race_traces(native.traces_by_entry[entry])
        profiles[entry] = {
            "training_trace_ids": [trace.trace_id for trace in training],
            "validation_trace_ids": [trace.trace_id for trace in validation],
            "training_laps": len(training),
            "validation_laps": len(validation),
        }
    return {
        "source_partition": "training",
        "split": "chronological_80_20",
        "observation_hz": native.observation_hz,
        "profiles": profiles,
    }


def _freeze_split(native, entries: tuple[str, ...]) -> tuple[dict[str, object], str]:
    expected = _split_manifest(native, entries)
    path = OUTPUT / "split_manifest.json"
    if path.exists():
        existing = json.loads(path.read_text())
        if existing != expected:
            raise RuntimeError("frozen race split differs from current source evidence")
    else:
        _write_once(path, expected)
    return expected, _digest(path)


def _verify_checkpoint(path: Path, stage: str, updates: int, sources: dict[str, str]) -> dict[str, object]:
    model = create_diagnostic_model(SEED + 90_000)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    metadata = load_curriculum_checkpoint(path, model, optimizer)
    if metadata != {"stage": stage, "completed_updates": updates, "sources": sources}:
        raise RuntimeError(f"restricted checkpoint verification failed for {stage}")
    return {"restricted_load": True, "sha256": _digest(path), "completed_updates": updates}


def _profile_run(
    entry: str,
    index: int,
    native,
    registry,
    split_digest: str,
    prior: DeploymentPrior,
    interaction: RaceInteractionPrior,
    scenario: P23ScenarioPrior,
) -> dict[str, object]:
    checkpoint = OUTPUT / "checkpoints" / f"entry-{entry}.pt"
    report_path = OUTPUT / "reports" / f"entry-{entry}.json"
    stage = f"japan-race-4hz-entry-{entry}"
    training, validation = split_race_traces(native.traces_by_entry[entry])
    sources = {
        "base_qualifying_checkpoint": _digest(BASE_CHECKPOINT),
        "profile_registry": _digest(PROFILE_PATH),
        "race_batches": _digest(RACE_BATCH_PATH),
        "race_report": _digest(RACE_REPORT_PATH),
        "split_manifest": split_digest,
    }
    if checkpoint.exists() or report_path.exists():
        if not checkpoint.exists() or not report_path.exists():
            raise RuntimeError(f"entry {entry} has a partial immutable result")
        model = create_diagnostic_model(SEED + index)
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
        metadata = load_curriculum_checkpoint(checkpoint, model, optimizer)
        if metadata != {"stage": stage, "completed_updates": len(training), "sources": sources}:
            raise RuntimeError(f"entry {entry} checkpoint identity changed")
        report = json.loads(report_path.read_text())
        if report.get("sources") != sources:
            raise RuntimeError(f"entry {entry} report identity changed")
        print(f"resumed entry {entry}", flush=True)
        return report
    model = create_diagnostic_model(SEED + index)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    base = load_curriculum_checkpoint(BASE_CHECKPOINT, model, optimizer)
    print(f"training entry {entry}: {len(training)} native-lap PPO updates", flush=True)
    training_report = run_diagnostic_updates(
        training,
        {entry: registry.profiles[entry]},
        prior,
        len(training),
        SEED + 1_000 + index,
        model=model,
        carry_energy_across_updates=True,
        interaction_prior=interaction,
        optimizer=optimizer,
        carry_hidden_across_updates=True,
    )
    save_curriculum_checkpoint(checkpoint, model, optimizer, stage, len(training), sources)
    verification = _verify_checkpoint(checkpoint, stage, len(training), sources)
    validation_report = validate_profile_policy(
        model, validation, registry.profiles[entry], prior, training, interaction,
    )
    print(f"validating entry {entry}: P23 against {len(native.field_ticks)} source ticks", flush=True)
    p23_report = run_p23_diagnostic(
        model,
        native.field_ticks,
        registry.profiles,
        registry.profiles[entry],
        prior,
        scenario,
        interaction,
        native.route_length_m,
    )
    report: dict[str, object] = {
        "status": "diagnostic_only",
        "physics_admission": False,
        "profile_entry": entry,
        "base_checkpoint_stage": base["stage"],
        "training_laps": len(training),
        "withheld_validation_laps": len(validation),
        "validation_trace_ids": [trace.trace_id for trace in validation],
        "training": training_report,
        "validation": validation_report,
        "p23": p23_report,
        "checkpoint_verification": verification,
        "sources": sources,
    }
    _write_once(report_path, report)
    print(f"completed entry {entry}", flush=True)
    return report


def main() -> None:
    """Run or safely resume the fixed all-profile diagnostic."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "checkpoints").mkdir(exist_ok=True)
    (OUTPUT / "reports").mkdir(exist_ok=True)
    registry = load_promoted_profiles(PROFILE_PATH)
    entries = tuple(sorted(registry.profiles, key=lambda value: int(value)))
    native = load_native_race_data(RACE_BATCH_PATH, RACE_REPORT_PATH, entries)
    split_manifest, split_digest = _freeze_split(native, entries)
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    interaction = RaceInteractionPrior()
    scenario = P23ScenarioPrior(5.0, 800.0, 16_000.0)
    reports = {
        entry: _profile_run(entry, index, native, registry, split_digest, prior, interaction, scenario)
        for index, entry in enumerate(entries, start=1)
    }
    consolidated = consolidate_profile_reports(reports)
    summary: dict[str, object] = {
        "status": "diagnostic_only",
        "physics_admission": False,
        "event": "Japan",
        "profiles": len(entries),
        "profile_entries": list(entries),
        "native_observation_hz": native.observation_hz,
        "policy_decision_hz": scenario.decision_hz,
        "reference_field_entries": len(entries),
        "additional_ego_start": "grid_position_23",
        "route_length_m": native.route_length_m,
        "source_field_ticks": len(native.field_ticks),
        "training_laps": sum(row["training_laps"] for row in split_manifest["profiles"].values()),
        "withheld_validation_laps": sum(row["validation_laps"] for row in split_manifest["profiles"].values()),
        "training_source_ticks_4hz": sum(
            len(trace.speed_ms)
            for entry in entries
            for trace in split_race_traces(native.traces_by_entry[entry])[0]
        ),
        "withheld_source_ticks_4hz": sum(
            len(trace.speed_ms)
            for entry in entries
            for trace in split_race_traces(native.traces_by_entry[entry])[1]
        ),
        "p23_decision_ticks_5hz": sum(int(report["p23"]["decision_ticks"]) for report in reports.values()),
        "reference_field_mode": "22_fitted_ice_profiles_with_source_controls_no_policy_or_electric",
        "energy_prior": {
            "maximum_electric_power_w": prior.maximum_electric_power_w,
            "usable_store_j": prior.usable_store_j,
            "harvest_cap_j_per_lap": prior.harvest_cap_j_per_lap,
            "motor_efficiency": prior.motor_efficiency,
            "harvest_efficiency": prior.harvest_efficiency,
        },
        "split_manifest_sha256": split_digest,
        "consolidated": consolidated,
        "reports": {entry: f"reports/entry-{entry}.json" for entry in entries},
        "limitations": [
            "All outputs are diagnostic-only and the provisional profiles are not physically admitted.",
            "Withheld laps are never used for optimizer updates.",
            "P23 is an additional independent ego; reference entries simulate source controls without policy or electric power.",
            "P23 ranks and gaps are proxy outcomes under a declared causal speed-controller prior.",
            "Categorical scores are uncalibrated action-selection probabilities, not success probabilities.",
        ],
    }
    summary_path = OUTPUT / "summary.json"
    if summary_path.exists():
        if json.loads(summary_path.read_text()) != summary:
            raise RuntimeError("existing immutable summary differs from the completed run")
    else:
        _write_once(summary_path, summary)
    print(json.dumps({
        "status": summary["status"],
        "profiles": summary["profiles"],
        "training_laps": summary["training_laps"],
        "withheld_validation_laps": summary["withheld_validation_laps"],
        "summary": str(summary_path),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
