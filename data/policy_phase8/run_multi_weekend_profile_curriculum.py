"""Continue every profile through later practice and race training weekends."""

from hashlib import sha256
import json
from pathlib import Path

import torch

from poweshift_backend.energy.allocator import DeploymentPrior
from poweshift_backend.policy.curriculum import (
    load_curriculum_checkpoint,
    load_native_race_data,
    load_practice_traces,
    load_promoted_profiles,
    save_curriculum_checkpoint,
    split_race_traces,
)
from poweshift_backend.policy.diagnostic import (
    RaceInteractionPrior,
    create_diagnostic_model,
    run_diagnostic_updates,
)
from poweshift_backend.policy.race_validation import (
    P23ScenarioPrior,
    consolidate_profile_reports,
    run_p23_diagnostic,
    validate_profile_policy,
)
from poweshift_backend.policy.weekend_curriculum import freeze_curriculum_manifest


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/policy_phase8/multi_weekend_all_profiles_v1"
REPRESENTATION = ROOT / "data/representation_phase4"
PROFILE_PATH = REPRESENTATION / "race_full_weekend_japan_v1_diagnostic/promoted_profiles_v1.json"
JAPAN_OUTPUT = ROOT / "data/policy_phase8/race_4hz_all_profiles_v1"
PRACTICE_SUMMARY = ROOT / "data/policy_phase8/later_training_practice_exports_v1.json"
SEED = 20260913
EVENTS = (
    ("2026-05-03", "Miami Grand Prix", "miami"),
    ("2026-05-24", "Canadian Grand Prix", "canadian"),
    ("2026-06-07", "Monaco Grand Prix", "monaco"),
    ("2026-06-14", "Barcelona Grand Prix", "barcelona"),
    ("2026-06-28", "Austrian Grand Prix", "austrian"),
    ("2026-07-05", "British Grand Prix", "british"),
)


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _write_once(path: Path, payload: dict[str, object]) -> None:
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text() != content:
        raise RuntimeError(f"immutable report differs: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _practice_paths() -> dict[str, tuple[Path, ...]]:
    payload = json.loads(PRACTICE_SUMMARY.read_text())
    grouped: dict[str, list[Path]] = {}
    for value in payload.get("manifests", ()):
        path = Path(value)
        manifest = json.loads(path.read_text())
        grouped.setdefault(str(manifest["identity"]["event_name"]), []).append(path)
    return {event: tuple(sorted(paths)) for event, paths in grouped.items()}


def _race_paths(slug: str) -> tuple[Path, Path]:
    directory = REPRESENTATION / f"race_full_weekend_{slug}_v1_diagnostic"
    return directory / "race_batches.pt", directory / "source_binding.json"


def _split_available_race(traces):
    if len(traces) < 2:
        return (), traces
    return split_race_traces(traces)


def _manifest(registry, entries: tuple[str, ...], practice_paths: dict[str, tuple[Path, ...]]) -> dict[str, object]:
    sessions: list[dict[str, object]] = []
    for event_date, event_name, slug in EVENTS:
        for path in practice_paths.get(event_name, ()):
            data = load_practice_traces(path, {entry: registry.profiles[entry] for entry in entries})
            sessions.append({
                "event_date": event_date,
                "event_name": event_name,
                "session_kind": "practice",
                "session_id": data.session_id,
                "source_manifest": str(path),
                "source_sha256": _digest(path),
                "profiles": {
                    entry: {
                        "training_trace_ids": [trace.trace_id for trace in data.traces_by_entry[entry]],
                        "validation_trace_ids": [],
                    }
                    for entry in entries
                },
            })
        race_path, binding_path = _race_paths(slug)
        native = load_native_race_data(race_path, binding_path, entries, allow_missing_entries=True)
        sessions.append({
            "event_date": event_date,
            "event_name": event_name,
            "session_kind": "race",
            "session_id": f"{slug}-race",
            "race_artifact": str(race_path),
            "race_artifact_sha256": _digest(race_path),
            "source_binding": str(binding_path),
            "source_binding_sha256": _digest(binding_path),
            "profiles": {
                entry: {
                    "training_trace_ids": [
                        trace.trace_id for trace in _split_available_race(native.traces_by_entry[entry])[0]
                    ],
                    "validation_trace_ids": [
                        trace.trace_id for trace in _split_available_race(native.traces_by_entry[entry])[1]
                    ],
                }
                for entry in entries
            },
        })
    return {
        "status": "diagnostic_only",
        "physics_admission": False,
        "source_partition": "training",
        "curriculum": "japan_checkpoint_then_later_practice_and_race",
        "profile_registry_sha256": _digest(PROFILE_PATH),
        "profiles": list(entries),
        "sessions": sessions,
        "protected_partitions_opened": [],
    }


def _train_event_entry(
    registry,
    entry: str,
    index: int,
    event_date: str,
    event_name: str,
    slug: str,
    model,
    optimizer,
    cumulative_updates: int,
    previous_checkpoint: Path,
    practice_data,
    native,
    manifest_hash: str,
    prior,
    interaction,
) -> tuple[int, Path, dict[str, object]]:
    checkpoint = OUTPUT / "checkpoints" / slug / f"entry-{entry}.pt"
    report_path = OUTPUT / "reports" / slug / f"entry-{entry}.json"
    training, validation = _split_available_race(native.traces_by_entry[entry])
    practice_updates = sum(len(data.traces_by_entry[entry]) for _, data in practice_data)
    completed_updates = cumulative_updates + practice_updates + len(training)
    stage = f"{event_date}-{slug}-entry-{entry}"
    sources = {
        "curriculum_manifest": manifest_hash,
        "previous_checkpoint": _digest(previous_checkpoint),
        "race_artifact": _digest(_race_paths(slug)[0]),
        "race_source_binding": _digest(_race_paths(slug)[1]),
        **{f"practice_{ordinal}": _digest(path) for ordinal, (path, _) in enumerate(practice_data, start=1)},
    }
    if checkpoint.exists() or report_path.exists():
        if not checkpoint.exists() or not report_path.exists():
            raise RuntimeError(f"partial immutable result for {slug} entry {entry}")
        metadata = load_curriculum_checkpoint(checkpoint, model, optimizer)
        expected = {"stage": stage, "completed_updates": completed_updates, "sources": sources}
        if metadata != expected:
            raise RuntimeError(f"checkpoint identity changed for {slug} entry {entry}")
        report = json.loads(report_path.read_text())
        if report.get("sources") != sources:
            raise RuntimeError(f"report identity changed for {slug} entry {entry}")
        print(f"resumed {slug} entry {entry}", flush=True)
        return completed_updates, checkpoint, report
    practice_reports = []
    for session_index, (path, data) in enumerate(practice_data, start=1):
        traces = data.traces_by_entry[entry]
        if not traces:
            practice_reports.append({
                "session_id": data.session_id,
                "source_manifest": str(path),
                "updates": 0,
                "coverage": "no_complete_supported_laps_for_profile",
            })
            continue
        report = run_diagnostic_updates(
            traces,
            {entry: registry.profiles[entry]},
            prior,
            len(traces),
            SEED + index * 1_000 + session_index,
            model=model,
            carry_energy_across_updates=True,
            interaction_prior=interaction,
            optimizer=optimizer,
            carry_hidden_across_updates=True,
        )
        practice_reports.append({
            "session_id": data.session_id,
            "source_manifest": str(path),
            "coverage": "complete_supported_laps",
            **report,
        })
    race_report = run_diagnostic_updates(
        training,
        {entry: registry.profiles[entry]},
        prior,
        len(training),
        SEED + index * 10_000,
        model=model,
        carry_energy_across_updates=True,
        interaction_prior=interaction,
        optimizer=optimizer,
        carry_hidden_across_updates=True,
    ) if training else {"updates": 0, "coverage": "no_training_laps_after_holdout"}
    validation_report = validate_profile_policy(
        model,
        validation,
        registry.profiles[entry],
        prior,
        training,
        interaction,
    ) if validation else {"validation_laps": 0, "coverage": "no_complete_supported_laps"}
    save_curriculum_checkpoint(
        checkpoint, model, optimizer, stage, completed_updates, sources,
    )
    verification_model = create_diagnostic_model(SEED + 900_000 + index)
    verification_optimizer = torch.optim.Adam(verification_model.parameters(), lr=3e-4)
    verification = load_curriculum_checkpoint(checkpoint, verification_model, verification_optimizer)
    if verification != {"stage": stage, "completed_updates": completed_updates, "sources": sources}:
        raise RuntimeError(f"restricted checkpoint verification failed for {slug} entry {entry}")
    report = {
        "status": "diagnostic_only",
        "physics_admission": False,
        "event_date": event_date,
        "event_name": event_name,
        "profile_entry": entry,
        "practice": practice_reports,
        "race_training": race_report,
        "race_validation": validation_report,
        "race_training_trace_ids": [trace.trace_id for trace in training],
        "race_validation_trace_ids": [trace.trace_id for trace in validation],
        "completed_updates": completed_updates,
        "checkpoint_sha256": _digest(checkpoint),
        "checkpoint_restricted_load": True,
        "sources": sources,
    }
    _write_once(report_path, report)
    print(f"completed {slug} entry {entry}", flush=True)
    return completed_updates, checkpoint, report


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    registry = load_promoted_profiles(PROFILE_PATH)
    entries = tuple(sorted(registry.profiles, key=int))
    practice_paths = _practice_paths()
    manifest = _manifest(registry, entries, practice_paths)
    manifest_path = OUTPUT / "curriculum_manifest.json"
    freeze_curriculum_manifest(manifest_path, manifest)
    manifest_hash = _digest(manifest_path)
    prior = DeploymentPrior(0.20, 5_000_000.0, 5_000_000.0, 0.95, 0.8)
    interaction = RaceInteractionPrior()
    scenario = P23ScenarioPrior(5.0, 800.0, 16_000.0)
    models = {entry: create_diagnostic_model(SEED + index) for index, entry in enumerate(entries, start=1)}
    optimizers = {entry: torch.optim.Adam(models[entry].parameters(), lr=3e-4) for entry in entries}
    completed_updates: dict[str, int] = {}
    previous_checkpoints: dict[str, Path] = {}
    for entry in entries:
        path = JAPAN_OUTPUT / "checkpoints" / f"entry-{entry}.pt"
        metadata = load_curriculum_checkpoint(path, models[entry], optimizers[entry])
        completed_updates[entry] = int(metadata["completed_updates"])
        previous_checkpoints[entry] = path
    all_event_reports: dict[str, dict[str, object]] = {entry: {} for entry in entries}
    final_native = None
    for event_date, event_name, slug in EVENTS:
        practice_data = tuple(
            (path, load_practice_traces(path, registry.profiles))
            for path in practice_paths.get(event_name, ())
        )
        race_path, binding_path = _race_paths(slug)
        native = load_native_race_data(race_path, binding_path, entries, allow_missing_entries=True)
        for index, entry in enumerate(entries, start=1):
            updates, checkpoint, report = _train_event_entry(
                registry,
                entry,
                index,
                event_date,
                event_name,
                slug,
                models[entry],
                optimizers[entry],
                completed_updates[entry],
                previous_checkpoints[entry],
                practice_data,
                native,
                manifest_hash,
                prior,
                interaction,
            )
            completed_updates[entry] = updates
            previous_checkpoints[entry] = checkpoint
            all_event_reports[entry][slug] = report
        final_native = native
    if final_native is None:
        raise RuntimeError("curriculum has no final race field")
    required = set(entries)
    first_complete = next((
        index for index, tick in enumerate(final_native.field_ticks)
        if set(dict(tick.progress_by_entry)) == required
        and set(dict(tick.speed_by_entry)) == required
        and set(dict(tick.throttle_by_entry)) == required
        and set(dict(tick.brake_by_entry)) == required
    ), None)
    if first_complete is None:
        raise RuntimeError("final race has no complete 22-car P23 field state")
    p23_field_ticks = final_native.field_ticks[first_complete:]
    final_reports: dict[str, dict[str, object]] = {}
    for entry in entries:
        path = OUTPUT / "p23" / f"entry-{entry}.json"
        if path.exists():
            p23 = json.loads(path.read_text())
        else:
            p23 = run_p23_diagnostic(
                models[entry],
                p23_field_ticks,
                registry.profiles,
                registry.profiles[entry],
                prior,
                scenario,
                interaction,
                final_native.route_length_m,
            )
            _write_once(path, p23)
        final_reports[entry] = {
            "status": "diagnostic_only",
            "physics_admission": False,
            "profile_entry": entry,
            "events": all_event_reports[entry],
            "final_checkpoint_sha256": _digest(previous_checkpoints[entry]),
            "validation": all_event_reports[entry]["british"]["race_validation"],
            "p23": p23,
        }
    consolidated = consolidate_profile_reports(final_reports)
    summary = {
        "status": "diagnostic_only",
        "physics_admission": False,
        "profiles": len(entries),
        "events": [event_name for _, event_name, _ in EVENTS],
        "native_observation_hz": 4.0,
        "policy_decision_hz": 5.0,
        "additional_ego_start": "grid_position_23",
        "reference_field_mode": "22_fitted_ice_profiles_with_source_controls_no_policy_or_electric",
        "energy_prior": {
            "additive_electric_wheel_power_fraction": prior.electric_boost_fraction,
            "usable_store_j": prior.usable_store_j,
            "harvest_cap_j_per_lap": prior.harvest_cap_j_per_lap,
            "motor_efficiency": prior.motor_efficiency,
            "harvest_efficiency": prior.harvest_efficiency,
        },
        "curriculum_manifest_sha256": manifest_hash,
        "total_completed_updates": completed_updates,
        "consolidated": consolidated,
        "reports": {entry: f"p23/entry-{entry}.json" for entry in entries},
        "protected_partitions_opened": [],
        "limitations": [
            "All results are diagnostic proxies from provisional profiles without physical admission.",
            "Practice supplies energy controls only and never tactical or rank labels.",
            "Each race withholds its final chronological 20 percent of complete laps from updates.",
            "P23 is additional; all 22 references remain policy-free and electric-free.",
            "Action probabilities are uncalibrated selection probabilities.",
        ],
    }
    _write_once(OUTPUT / "summary.json", summary)
    print(json.dumps({
        "status": summary["status"],
        "profiles": len(entries),
        "events": len(EVENTS),
        "summary": str(OUTPUT / "summary.json"),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
