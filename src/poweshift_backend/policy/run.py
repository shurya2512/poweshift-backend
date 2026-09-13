"""Immutable runner for source-bound physical PPO updates."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

import torch

from poweshift_backend.contracts.action import ActionRequest, Manoeuvre
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.policy.artifact import load_policy_training_artifact
from poweshift_backend.policy.buffer import ActionRecord, RolloutStep
from poweshift_backend.policy.checkpoint import PolicyCheckpointMetadata, load_policy_checkpoint, save_policy_checkpoint
from poweshift_backend.policy.model import RecurrentActorCritic
from poweshift_backend.policy.ppo import PpoUpdateRecord, RecurrentFragment, evaluate_sampled_actions, ppo_update
from poweshift_backend.policy.schema import PolicySchema
from poweshift_backend.policy.train import PhysicalTrainingGate, require_policy_training_ready


@dataclass(frozen=True)
class PolicyTrainingReport:
    """Immutable outcome of a requested training mode."""

    status: Literal["passed", "failed"]
    updates: int
    artifact_sha256: str
    records: tuple[PpoUpdateRecord, ...]
    failure: str | None


def _action(values: list[object]) -> ActionRequest:
    return ActionRequest(Manoeuvre(values[0]), float(values[1]))


def _fragment(payload: dict[str, object]) -> RecurrentFragment:
    steps = []
    for item in payload["steps"]:
        action = ActionRecord(
            _action(item["sampled"]), _action(item["issued"]), _action(item["delivered"]),
            float(item["sampled_joint_log_probability"]), tuple(item.get("binding_reasons", ())),
        )
        steps.append(RolloutStep(
            tuple(item["observation"]), tuple(item["feature_mask"]), action,
            tuple(item["recurrent_state_before"]), tuple(item["recurrent_state_after"]),
            float(item["value"]), float(item["reward"]), bool(item["terminated"]), bool(item["truncated"]),
            tuple(item["action_mask"]), bool(item.get("deployment_available", True)),
        ))
    return RecurrentFragment(tuple(steps), int(payload.get("burn_in", 0)), float(payload.get("bootstrap_value", 0.0)))


def _write_report(output: Path, report: PolicyTrainingReport) -> None:
    payload = asdict(report)
    output.joinpath("report.json").write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _binding_payload(manifest: object) -> dict[str, object]:
    payload = asdict(manifest)
    for field in ("run_id", "mode", "updates"):
        payload.pop(field)
    return payload


def run_policy_training(
    artifact: Path,
    source_binding: Path,
    output: Path,
    *,
    mode: Literal["preflight", "smoke"],
) -> PolicyTrainingReport:
    """Run an exact update count and persist success or failure."""
    if output.exists():
        raise FileExistsError(f"policy training output already exists: {output}")
    output.mkdir(parents=True)
    artifact_id = ""
    records: list[PpoUpdateRecord] = []
    try:
        frozen = load_policy_training_artifact(artifact)
        artifact_id = frozen.artifact_sha256
        manifest = frozen.manifest
        if mode != manifest.mode:
            raise ValueError("requested mode does not match the training artifact")
        if sha256(source_binding.read_bytes()).hexdigest() != manifest.training_source_sha256:
            raise ValueError("source hash does not match the training artifact")
        if mode == "smoke":
            preflight_path = output.parent / "preflight" / "report.json"
            preflight = json.loads(preflight_path.read_text())
            preflight_artifact = load_policy_training_artifact(output.parent / "preflight" / "frozen_artifact.json")
            if preflight.get("status") != "passed" or _binding_payload(preflight_artifact.manifest) != _binding_payload(manifest):
                raise ValueError("smoke requires a matching passed preflight")
        source = json.loads(source_binding.read_text())
        bundle = EnergyBundleCompatibility(**source["energy_bundle"])
        gate = PhysicalTrainingGate(bundle, manifest.continuous_profile_id, manifest.held_out_measure_id, manifest.acceptance_criteria_id)
        require_policy_training_ready(manifest, gate)
        if (source["pit_manifest_id"], source["route_id"], source["scenario_id"]) != (manifest.pit_manifest_id, manifest.route_id, manifest.scenario_id):
            raise ValueError("source scenario identities do not match the training artifact")
        schema_values = dict(source["schema"])
        schema_values["feature_names"] = tuple(schema_values["feature_names"])
        schema_values["manoeuvres"] = tuple(Manoeuvre(value) for value in schema_values["manoeuvres"])
        schema = PolicySchema(**schema_values)
        if schema.schema_id != manifest.schema_id:
            raise ValueError("source schema does not match the training artifact")
        fragment = _fragment(source)
        torch.manual_seed(manifest.seed)
        model = RecurrentActorCritic(schema)
        optimizer = torch.optim.Adam(model.parameters(), lr=manifest.config.learning_rate)
        for _ in range(manifest.updates):
            records.append(ppo_update(model, optimizer, fragment, manifest.config))
        metadata = PolicyCheckpointMetadata.from_energy_bundle(schema, bundle, manifest.pit_manifest_id, manifest.scenario_id)
        checkpoint = output / "checkpoint.pt"
        save_policy_checkpoint(checkpoint, model, metadata)
        expected = evaluate_sampled_actions(model, fragment).joint_log_probability.detach()
        restored = RecurrentActorCritic(schema)
        load_policy_checkpoint(checkpoint, restored, metadata)
        actual = evaluate_sampled_actions(restored, fragment).joint_log_probability.detach()
        torch.testing.assert_close(actual, expected)
        output.joinpath("frozen_artifact.json").write_bytes(artifact.read_bytes())
        report = PolicyTrainingReport("passed", len(records), artifact_id, tuple(records), None)
    except Exception as error:
        report = PolicyTrainingReport("failed", len(records), artifact_id, tuple(records), str(error))
    _write_report(output, report)
    return report
