"""Run one-update race training and persist complete diagnostic errors."""

from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
from random import Random
import resource
from time import perf_counter

import torch

from poweshift_backend.physics.differentiable import DifferentiableMechanics
from poweshift_backend.representation.race_evaluation import evaluate_race_model
from poweshift_backend.representation.weekend_model import WeekendModelConfig, WeekendTelemetryModel
from poweshift_backend.representation.weekend_training import WeekendTrajectoryBatch, save_smoke_checkpoint, train_trajectory


def run_full_race_training(
    artifact: Path,
    source_binding: Path,
    runtime: DifferentiableMechanics,
    output: Path,
    *,
    initial_checkpoint: Path | None = None,
    seed: int = 0,
) -> dict[str, object]:
    """Train once per shuffled race batch and evaluate the final model."""
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "full_race.json"
    if report_path.exists():
        raise FileExistsError(f"immutable diagnostic exists: {report_path}")
    started = perf_counter()
    report: dict[str, object] = {"mode": "full_race", "seed": seed, "steps": 0, "status": "failed"}
    try:
        binding = json.loads(source_binding.read_text())
        payload = torch.load(artifact, weights_only=True)
        if payload.get("source_binding_sha256") != sha256(source_binding.read_bytes()).hexdigest():
            raise ValueError("race batch artifact source binding differs")
        batches = tuple(WeekendTrajectoryBatch(**value) for value in payload["batches"])
        diagnostics = list(payload["diagnostics"])
        config = WeekendModelConfig(**payload["model_config"])
        torch.manual_seed(seed)
        model = WeekendTelemetryModel(config)
        if initial_checkpoint is not None:
            checkpoint = torch.load(initial_checkpoint, weights_only=True)
            if checkpoint.get("model_config") != asdict(config):
                raise ValueError("initial checkpoint model configuration differs")
            model.load_state_dict(checkpoint["model_state"], strict=True)
        optimizer = torch.optim.Adam(model.parameters(), lr=float(payload["learning_rate"]))
        order = list(range(len(batches)))
        Random(seed).shuffle(order)
        records = []
        training_exclusions = []
        training_hotfixes = []
        training_started = perf_counter()
        for index in order:
            try:
                records.append(train_trajectory(model, runtime, optimizer, batches[index], updates=1))
            except ValueError as error:
                if str(error) == "required predicted checkpoint crossing is unavailable":
                    rank_only = replace(
                        batches[index],
                        timing_pair_mask=torch.zeros_like(batches[index].timing_pair_mask),
                        source_context=f"{batches[index].source_context}; timing pairs unavailable from prediction",
                    )
                    records.append(train_trajectory(model, runtime, optimizer, rank_only, updates=1))
                    training_hotfixes.append(
                        {
                            "logical_batch_id": batches[index].logical_batch_id,
                            "action": "rank-only update; timing error retained as missing prediction coverage",
                        }
                    )
                else:
                    training_exclusions.append({"logical_batch_id": batches[index].logical_batch_id, "failure": str(error)})
        training_seconds = perf_counter() - training_started
        if not records:
            raise ValueError("no race batch completed its optimizer update")
        checkpoint_path = output / "full_race.pt"
        save_smoke_checkpoint(checkpoint_path, model, tuple(records))
        evaluation_started = perf_counter()
        metrics, profiles = evaluate_race_model(model, runtime, batches, diagnostics)
        evaluation_seconds = perf_counter() - evaluation_started
        profiles_path = output / "diagnostic_profiles.json"
        _write_immutable_json(
            profiles_path,
            {
                "artifact_kind": "diagnostic_full_weekend_car_profiles_v1",
                "admission_eligible": False,
                "checkpoint": str(checkpoint_path),
                "checkpoint_sha256": sha256(checkpoint_path.read_bytes()).hexdigest(),
                "profiles": profiles,
            },
        )
        report.update(
            status="passed",
            admission_eligible=False,
            steps=len(records),
            requested_batches=len(batches),
            training_exclusions=training_exclusions,
            training_hotfixes=training_hotfixes,
            source_binding=binding,
            artifact_sha256=sha256(artifact.read_bytes()).hexdigest(),
            initial_checkpoint=str(initial_checkpoint) if initial_checkpoint else None,
            initial_checkpoint_sha256=sha256(initial_checkpoint.read_bytes()).hexdigest() if initial_checkpoint else None,
            model_config=asdict(config),
            records=[asdict(record) for record in records],
            checkpoint=str(checkpoint_path),
            checkpoint_sha256=sha256(checkpoint_path.read_bytes()).hexdigest(),
            profiles=str(profiles_path),
            error_metrics=metrics,
            training_seconds=training_seconds,
            evaluation_seconds=evaluation_seconds,
        )
    except Exception as error:
        report["failure"] = str(error)
    report.update(
        wall_seconds=perf_counter() - started,
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    _write_immutable_json(report_path, report)
    if report["status"] != "passed":
        raise ValueError(str(report["failure"]))
    return report


def _write_immutable_json(path: Path, value: dict[str, object]) -> None:
    content = json.dumps(value, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text() != content:
        raise FileExistsError(f"immutable diagnostic differs: {path}")
    path.write_text(content)
