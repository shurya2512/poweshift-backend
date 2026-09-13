"""Create per-track qualifying inference reports from final profile policies."""

from hashlib import sha256
import json
from pathlib import Path
from statistics import mean, median

import pandas as pd
import torch

from poweshift_backend.energy.allocator import DeploymentPrior, LapEnergyState
from poweshift_backend.policy.curriculum import (
    load_curriculum_checkpoint,
    load_promoted_profiles,
    load_qualifying_replay_traces,
    load_qualifying_test_traces,
)
from poweshift_backend.policy.diagnostic import create_diagnostic_model, evaluate_diagnostic_trace
from poweshift_backend.policy.race_validation import bounded_additive_lap_time_proxy


ROOT = Path(__file__).resolve().parents[2]
CURRICULUM = ROOT / "data/policy_phase8/multi_weekend_all_profiles_v1"
OUTPUT = ROOT / "data/policy_phase8/runtime_inference_reports_v3/qualifying"
PROFILES = ROOT / "data/representation_phase4/race_full_weekend_japan_v1_diagnostic/promoted_profiles_v1.json"
TRAINING = ROOT / "data/policy_phase8/training_qualifying_replay_exports_v1.json"
MADRING = ROOT / "data/representation_phase4/qualifying_madring_test_v1/qualifying_test_export.json"
SEED = 20260913


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: dict[str, object]) -> None:
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _lap_times(manifest: dict, entry: str) -> dict[float, float]:
    laps = pd.read_parquet(manifest["exports"]["laps"]["path"])
    rows = laps.loc[
        (laps["DriverNumber"].astype(str) == entry)
        & laps["LapNumber"].notna()
        & laps["LapTime"].notna()
        & laps["IsAccurate"].fillna(False).astype(bool)
        & ~laps["Deleted"].fillna(False).astype(bool)
    ]
    return {
        float(row.LapNumber): float(pd.Timedelta(row.LapTime).total_seconds())
        for row in rows.itertuples(index=False)
    }


def _profile_report(model, traces, profile, prior, observed: dict[float, float]) -> dict[str, object]:
    state = LapEnergyState.full(prior)
    hidden = None
    laps = []
    for trace in traces:
        result = evaluate_diagnostic_trace(model, trace, profile, prior, state, initial_hidden=hidden)
        lap_number = float(trace.trace_id.rsplit("lap-", 1)[-1])
        observed_s = observed.get(lap_number)
        delivered = mean(item.delivered_deployment_fraction for item in result.decisions)
        ice_wheel_power_w = profile.maximum_drive_force_n * mean(trace.speed_ms)
        additive_fraction = prior.maximum_electric_power_w / ice_wheel_power_w
        attainable_s, gain_s = (
            bounded_additive_lap_time_proxy(observed_s, additive_fraction, delivered)
            if observed_s else (None, None)
        )
        laps.append({
            "source_lap": lap_number,
            "observed_lap_time_s": observed_s,
            "diagnostic_time_gain_proxy_s": gain_s,
            "diagnostic_attainable_lap_time_s": attainable_s,
            "mean_delivered_deployment_fraction": delivered,
            "mean_uncalibrated_action_probability": mean(
                item.action_probability for item in result.decisions
            ),
            "mean_requested_deployment_fraction": mean(
                item.requested_deployment_fraction for item in result.decisions
            ),
            "gross_deployment_j": sum(item.deployment_j for item in result.decisions),
            "gross_harvest_j": sum(item.harvest_j for item in result.decisions),
            "peak_motor_wheel_power_kw": max(item.motor_wheel_power_w for item in result.decisions) / 1_000.0,
            "stored_energy_start_j": result.decisions[0].stored_energy_before_j,
            "stored_energy_end_j": result.decisions[-1].stored_energy_after_j,
            "path": "hold",
        })
        state = result.final_state.next_lap()
        hidden = result.final_hidden
    attainable = [row["diagnostic_attainable_lap_time_s"] for row in laps if row["diagnostic_attainable_lap_time_s"]]
    return {
        "laps": laps,
        "best_observed_lap_time_s": min(observed.values()) if observed else None,
        "best_diagnostic_attainable_lap_time_s": min(attainable) if attainable else None,
        "gross_deployment_j": sum(row["gross_deployment_j"] for row in laps),
        "gross_harvest_j": sum(row["gross_harvest_j"] for row in laps),
        "final_stored_energy_j": state.stored_energy_j,
    }


def main() -> None:
    registry = load_promoted_profiles(PROFILES)
    entries = tuple(sorted(registry.profiles, key=int))
    paths = [Path(value) for value in json.loads(TRAINING.read_text())["manifests"]] + [MADRING]
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    index_rows = []
    for manifest_path in paths:
        manifest = json.loads(manifest_path.read_text())
        identity = manifest["identity"]
        protected = identity.get("partition") == "final_evaluation"
        data = (
            load_qualifying_test_traces(manifest_path, registry.profiles)
            if protected else load_qualifying_replay_traces(manifest_path, registry.profiles)
        )
        slug = "_".join(
            word.lower() for word in identity["event_name"].split()
            if word.lower() not in {"grand", "prix"}
        )
        reports = {}
        for index, entry in enumerate(entries, start=1):
            checkpoint = CURRICULUM / "checkpoints/british" / f"entry-{entry}.pt"
            model = create_diagnostic_model(SEED + index)
            optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
            metadata = load_curriculum_checkpoint(checkpoint, model, optimizer)
            traces = data.traces_by_entry[entry]
            result = _profile_report(
                model, traces, registry.profiles[entry], prior, _lap_times(manifest, entry),
            ) if traces else {
                "laps": [],
                "best_observed_lap_time_s": None,
                "best_diagnostic_attainable_lap_time_s": None,
                "gross_deployment_j": 0.0,
                "gross_harvest_j": 0.0,
                "final_stored_energy_j": None,
            }
            report = {
                "status": "diagnostic_only",
                "physics_admission": False,
                "partition": "final_evaluation" if protected else "training_replay",
                "event_name": identity["event_name"],
                "session": "Qualifying",
                "profile_entry": entry,
                "optimizer_updates": 0,
                "checkpoint_stage": metadata["stage"],
                "checkpoint_sha256": _digest(checkpoint),
                "source_manifest_sha256": _digest(manifest_path),
                **result,
                "probability_semantics": "uncalibrated_action_selection_probability",
                "lap_time_semantics": "idealized_additive_power_ratio_proxy_not_physical_prediction",
            }
            _write(OUTPUT / slug / "reports" / f"entry-{entry}.json", report)
            reports[entry] = report
        ranked = sorted(
            (
                (entry, row["best_diagnostic_attainable_lap_time_s"])
                for entry, row in reports.items()
                if row["best_diagnostic_attainable_lap_time_s"] is not None
            ),
            key=lambda item: item[1],
        )
        summary = {
            "status": "diagnostic_only",
            "physics_admission": False,
            "partition": "final_evaluation" if protected else "training_replay",
            "event_name": identity["event_name"],
            "session": "Qualifying",
            "profiles_with_laps": len(ranked),
            "profiles_without_laps": [entry for entry, row in reports.items() if not row["laps"]],
            "proxy_ranking": [
                {"rank": rank, "profile_entry": entry, "diagnostic_attainable_lap_time_s": value}
                for rank, (entry, value) in enumerate(ranked, start=1)
            ],
            "median_best_diagnostic_attainable_lap_time_s": median(value for _, value in ranked) if ranked else None,
            "optimizer_updates": 0,
            "reports": {entry: f"reports/entry-{entry}.json" for entry in entries},
        }
        _write(OUTPUT / slug / "summary.json", summary)
        index_rows.append({
            "event_name": identity["event_name"],
            "partition": summary["partition"],
            "profiles_with_laps": len(ranked),
            "summary": f"{slug}/summary.json",
        })
        print(f"completed qualifying report {identity['event_name']}", flush=True)
    _write(OUTPUT / "index.json", {
        "status": "diagnostic_only",
        "physics_admission": False,
        "tracks": index_rows,
        "frontend_inference": {
            "websocket": "/runs/{run_id}/live",
            "input_hz": 4.0,
            "decision_hz": 5.0,
        },
    })


if __name__ == "__main__":
    main()
