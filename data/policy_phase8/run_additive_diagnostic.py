"""Run the bounded qualifying-to-race additive-energy diagnostic."""

import json
from pathlib import Path
from statistics import median

import torch

from poweshift_backend.energy.allocator import DeploymentPrior
from poweshift_backend.policy.diagnostic import (
    DiagnosticTrace,
    FittedProfile,
    RaceInteractionPrior,
    create_diagnostic_model,
    evaluate_diagnostic_policy,
    run_diagnostic_updates,
)


ROOT = Path(__file__).resolve().parents[2]
REPRESENTATION = ROOT / "data" / "representation_phase4"


def _profiles() -> tuple[dict[str, FittedProfile], dict[str, object]]:
    path = REPRESENTATION / "race_full_weekend_australia_v2_diagnostic" / "diagnostic_profiles_v2.json"
    payload = json.loads(path.read_text())
    profiles = {
        entry: FittedProfile(
            entry,
            values["parameters"]["max_drive_force_n"],
            values["parameters"]["drag_n_per_ms2"],
            values["parameters"]["rolling_resistance_n"],
        )
        for entry, values in payload["profiles"].items()
    }
    return profiles, payload


def _normalization(path: Path) -> tuple[torch.Tensor, torch.Tensor]:
    payload = json.loads(path.read_text())
    values = payload.get("feature_normalization") or payload["source_binding"]["feature_normalization"]
    return torch.tensor(values["mean"], dtype=torch.float64), torch.tensor(values["scale"], dtype=torch.float64)


def _qualifying_traces() -> tuple[DiagnosticTrace, ...]:
    folder = REPRESENTATION / "qualifying_smoke_australia_v8_diagnostic"
    payload = torch.load(folder / "qualifying_batches.pt", weights_only=True)
    mean, scale = _normalization(folder / "source_binding.json")
    traces: list[DiagnosticTrace] = []
    for batch, diagnostic in zip(payload["batches"], payload["diagnostics"]):
        features = batch["features"].to(torch.float64) * scale + mean
        step_s = float(diagnostic["horizon_s"]) / (features.shape[1] - 1)
        for car, entry in enumerate(diagnostic["entries"]):
            rows = features[car]
            traces.append(DiagnosticTrace(
                "training",
                f"{batch['logical_batch_id']}:{entry}",
                tuple(float(value) for value in rows[:, 0]),
                tuple(float(value) for value in rows[:, 1]),
                tuple(float(value) for value in rows[:, 2]),
                step_s,
                entry,
            ))
    return tuple(traces)


def _traffic_gaps(progress: torch.Tensor, ego: int, route_length_m: float) -> tuple[list[float], list[float]]:
    ahead: list[float] = []
    behind: list[float] = []
    for row in progress:
        relative = torch.remainder(row - row[ego] + route_length_m / 2.0, route_length_m) - route_length_m / 2.0
        valid = torch.isfinite(relative)
        valid[ego] = False
        positive = relative[(relative > 0.0) & valid]
        negative = relative[(relative < 0.0) & valid]
        ahead.append(float(positive.min()) if positive.numel() else route_length_m / 2.0)
        behind.append(float(-negative.max()) if negative.numel() else route_length_m / 2.0)
    return ahead, behind


def _closing_rate(gaps: list[float], step_s: float) -> list[float]:
    rates = [0.0]
    rates.extend(max(0.0, min(20.0, (before - after) / step_s)) for before, after in zip(gaps, gaps[1:]))
    return rates


def _race_traces(entry: str = "1") -> tuple[tuple[DiagnosticTrace, ...], float, list[float]]:
    artifact = REPRESENTATION / "race_full_weekend_australia_v1_diagnostic" / "race_batches.pt"
    report = REPRESENTATION / "race_full_weekend_australia_v2_diagnostic" / "full_race.json"
    payload = torch.load(artifact, weights_only=True)
    mean, scale = _normalization(report)
    route_length_m = float(json.loads(report.read_text())["source_binding"]["route_length_m"])
    samples: list[tuple[float, float, float, float, float, float]] = []
    all_speeds: list[float] = []
    step_s = 30.0 / 63.0
    for batch, diagnostic in zip(payload["batches"], payload["diagnostics"]):
        if entry not in diagnostic["entries"]:
            continue
        ego = diagnostic["entries"].index(entry)
        features = batch["features"].to(torch.float64) * scale + mean
        indices = torch.linspace(0, batch["observed_progress"].shape[0] - 1, features.shape[1]).round().to(torch.long)
        progress = batch["observed_progress"][indices]
        ahead, behind = _traffic_gaps(progress, ego, route_length_m)
        rows = features[ego]
        for index, row in enumerate(rows):
            speed = max(1.0, float(row[0]))
            samples.append((float(progress[index, ego]), speed, float(row[1]), float(row[2]), ahead[index], behind[index]))
            all_speeds.append(speed)
    lap_groups: dict[int, list[tuple[float, float, float, float, float, float]]] = {}
    for sample in samples:
        lap_groups.setdefault(int(sample[0] // route_length_m), []).append(sample)
    complete = [rows for _, rows in sorted(lap_groups.items()) if len(rows) >= 100 and rows[-1][0] - rows[0][0] >= route_length_m * 0.8]
    if len(complete) < 10:
        raise ValueError("race source does not contain ten complete diagnostic laps")
    traces: list[DiagnosticTrace] = []
    for lap, rows in enumerate(complete[:10], start=1):
        speed = [row[1] for row in rows]
        ahead_distance = [row[4] for row in rows]
        behind_distance = [row[5] for row in rows]
        traces.append(DiagnosticTrace(
            "training",
            f"australia-race:{entry}:lap-{lap}",
            tuple(speed),
            tuple(row[2] for row in rows),
            tuple(row[3] for row in rows),
            step_s,
            entry,
            True,
            tuple(distance / current_speed for distance, current_speed in zip(ahead_distance, speed)),
            tuple(_closing_rate(ahead_distance, step_s)),
            tuple(distance / current_speed for distance, current_speed in zip(behind_distance, speed)),
            tuple(_closing_rate(behind_distance, step_s)),
            lap,
            10,
        ))
    return tuple(traces), route_length_m, all_speeds


def main() -> None:
    """Train qualifying first, then continue over ten race laps."""
    output = ROOT / "data" / "policy_phase8" / "diagnostic_reward_v2"
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")
    profiles, profile_payload = _profiles()
    qualifying = _qualifying_traces()
    race, route_length_m, race_speeds = _race_traces()
    force_values = [profile.maximum_drive_force_n for profile in profiles.values()]
    speeds = torch.tensor(race_speeds, dtype=torch.float64)
    median_speed = float(speeds.median())
    speed_p90 = float(torch.quantile(speeds, 0.9))
    boost_fraction = 0.20
    prior = DeploymentPrior(boost_fraction, 5_000_000.0, 5_000_000.0, 0.95, 0.8)
    interaction_prior = RaceInteractionPrior()
    seed = 20260913
    model = create_diagnostic_model(seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    qualifying_eval = qualifying[:20]
    qualifying_before = evaluate_diagnostic_policy(model, qualifying_eval, profiles, prior, seed + 1)
    qualifying_report = run_diagnostic_updates(
        qualifying, profiles, prior, 100, seed, model=model, optimizer=optimizer,
    )
    qualifying_after = evaluate_diagnostic_policy(model, qualifying_eval, profiles, prior, seed + 1)
    race_before = evaluate_diagnostic_policy(
        model, race, profiles, prior, seed + 2, True, interaction_prior,
    )
    race_report = run_diagnostic_updates(
        race, profiles, prior, 10, seed + 3, model=model,
        carry_energy_across_updates=True, interaction_prior=interaction_prior, optimizer=optimizer,
    )
    race_after = evaluate_diagnostic_policy(
        model, race, profiles, prior, seed + 2, True, interaction_prior,
    )
    diagnosis = {
        "profile_artifact_admission_eligible": profile_payload["admission_eligible"],
        "profile_count": len(profiles),
        "maximum_drive_force_n": {
            "minimum": min(force_values),
            "median": median(force_values),
            "maximum": max(force_values),
        },
        "observed_race_speed_ms": {"median": median_speed, "p90": speed_p90},
        "selected_electric_boost_fraction": boost_fraction,
        "selection_basis": "The fitted profiles identify aggregate effective drive force, not an ICE/electric split. Twenty percent is an explicit additive diagnostic prior, not a fitted result.",
        "electric_power_scale_w": {
            "at_median_profile_and_speed": median(force_values) * median_speed * boost_fraction,
            "at_median_profile_and_p90_speed": median(force_values) * speed_p90 * boost_fraction,
        },
        "usable_store_basis": "5 MJ diagnostic fallback because no admitted usable-store value is available.",
        "harvest_cap_basis": "5 MJ per lap fallback requested for circuits without an available cap.",
    }
    summary = {
        "status": "diagnostic_only",
        "source_partition": "training",
        "profile_diagnosis": diagnosis,
        "qualifying": {
            "updates": 100,
            "traffic_intelligence_enabled": False,
            "evaluation_before": qualifying_before,
            "training": qualifying_report,
            "evaluation_after": qualifying_after,
            "evaluation_delta": {
                key: qualifying_after[key] - qualifying_before[key]
                for key in ("mean_reward", "gross_deployment_j", "gross_harvest_j", "incremental_progress_proxy_m")
            },
        },
        "race": {
            "laps": 10,
            "updates": 10,
            "ego_entry": "1",
            "field_context_entries": len(profiles),
            "route_length_m": route_length_m,
            "traffic_intelligence_enabled": True,
            "evaluation_before": race_before,
            "training": race_report,
            "evaluation_after": race_after,
            "evaluation_delta": {
                key: race_after[key] - race_before[key]
                for key in ("mean_reward", "gross_deployment_j", "gross_harvest_j", "incremental_progress_proxy_m")
            },
        },
        "limitations": [
            "The fitted car profiles and source adapters are diagnostic and not admission eligible.",
            "Traffic gaps are source-derived, but pass and defence labels use declared heuristic thresholds rather than a validated interaction world.",
            "Incremental progress is a proxy from added longitudinal force, not a demonstrated lap-time or finishing-position gain.",
            "Ten race updates test reward direction but do not establish convergence of the deployment distribution.",
        ],
    }
    output.mkdir(parents=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    torch.save({"schema_id": model.schema.schema_id, "state_dict": model.state_dict()}, output / "policy_state_dict.pt")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
