"""Source-bound direct smoke entry point."""

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
import resource

import torch

from poweshift_backend.physics.differentiable import DifferentiableMechanics, StaticRoadLookup
from poweshift_backend.representation.weekend_model import WeekendModelConfig, WeekendTelemetryModel
from poweshift_backend.representation.weekend_training import WeekendTrajectoryBatch, _controls_at, run_smoke, save_smoke_checkpoint, train_trajectory


def run_weekend_smoke(artifact: Path, source_binding: Path, runtime: DifferentiableMechanics, output: Path, *, mode: str, seed: int = 0) -> dict[str, object]:
    """Run one preflight or bounded smoke from verified adapter tensors."""
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / f"{mode}.json"
    if report_path.exists():
        raise FileExistsError(f"immutable diagnostic exists: {report_path}")
    started = perf_counter()
    report = {"mode": mode, "seed": seed, "steps": 0, "status": "failed"}
    try:
        if mode not in {"preflight", "smoke"} or not artifact.is_file() or not source_binding.is_file():
            raise ValueError("verified batch artifact, binding, and mode are required")
        torch.manual_seed(seed)
        binding = json.loads(source_binding.read_text())
        payload = torch.load(artifact, weights_only=True)
        if payload.get("source_binding_sha256") != sha256(source_binding.read_bytes()).hexdigest(): raise ValueError("batch artifact source binding differs")
        batches = tuple(WeekendTrajectoryBatch(**value) for value in payload["batches"])
        config = WeekendModelConfig(**payload["model_config"])
        model = WeekendTelemetryModel(config)
        initial = model(batches[0].features)
        report["initial_batch"] = payload.get("diagnostics", [{}])[0]
        report["initial_state"] = batches[0].initial_state.tolist()
        report["initial_parameters"] = initial.parameters.tolist()
        optimizer = torch.optim.Adam(model.parameters(), lr=float(payload["learning_rate"]))
        records = (train_trajectory(model, runtime, optimizer, batches[0]),) if mode == "preflight" else run_smoke(model, runtime, optimizer, batches, total_updates=100, seed=seed)
        checkpoint = output / f"{mode}.pt"; save_smoke_checkpoint(checkpoint, model, records)
        report.update(status="passed", steps=sum(item.updates for item in records), source_binding=binding, artifact_sha256=sha256(artifact.read_bytes()).hexdigest(), model_config=asdict(config), records=[asdict(item) for item in records], checkpoint=str(checkpoint))
    except Exception as error:
        report["failure"] = str(error)
        if "batches" in locals() and "initial" in locals():
            report["runtime_support"] = _runtime_support(runtime, batches[0], initial.parameters)
    report.update(wall_seconds=perf_counter() - started, peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    if report["status"] != "passed": raise ValueError(report["failure"])
    return report


def _runtime_support(runtime: DifferentiableMechanics, batch: WeekendTrajectoryBatch, parameters: torch.Tensor) -> dict[str, object]:
    """Locate the first unsupported 4 Hz interval for the frozen initial profile."""
    route = StaticRoadLookup(batch.road_progress_m, batch.road_curvature_m_inv)
    state = batch.initial_state
    controls = _controls_at(batch)
    previous = batch.observation_times_s[0]
    for time_s in batch.observation_times_s[1:]:
        try:
            state = runtime.integrate(state, torch.stack((previous, time_s)), controls, route, parameters)[-1]
        except Exception as error:
            return {
                "last_safe_time_s": float(previous),
                "failing_observation_s": float(time_s),
                "last_safe_state": state.tolist(),
                "parameters": parameters.tolist(),
                "failure": str(error),
            }
        previous = time_s
    return {"status": "no_repeatable_interval_failure"}
