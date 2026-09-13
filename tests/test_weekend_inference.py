from hashlib import sha256
import json
from pathlib import Path

import pytest
import torch

from poweshift_backend.contracts.action import Manoeuvre
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.contracts.runtime import WeekendRunManifest
from poweshift_backend.evaluation.weekend import score_weekend_inference
from poweshift_backend.policy.checkpoint import PolicyCheckpointMetadata, save_policy_checkpoint
from poweshift_backend.policy.model import RecurrentActorCritic
from poweshift_backend.policy.schema import PolicySchema
from poweshift_backend.runtime.artifacts import ArtifactRegistry
from poweshift_backend.runtime.weekend import run_weekend_inference


def _write_inputs(tmp_path: Path) -> tuple[ArtifactRegistry, WeekendRunManifest, Path]:
    schema = PolicySchema("schema-a", ("speed_ms", "stored_energy_j"), tuple(Manoeuvre), 3, "beta-v1")
    bundle = EnergyBundleCompatibility(
        "bundle-a", True, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a"
    )
    model = RecurrentActorCritic(schema)
    for parameter in model.parameters():
        torch.nn.init.zeros_(parameter)
    with torch.no_grad():
        model.manoeuvre_head.bias[1] = 1.0
    checkpoint = tmp_path / "checkpoint.pt"
    save_policy_checkpoint(
        checkpoint,
        model,
        PolicyCheckpointMetadata.from_energy_bundle(schema, bundle, "pit-a", "scenario-a"),
    )
    source = tmp_path / "selection-source.json"
    source.write_text(json.dumps({
        "schema": {
            "schema_id": "schema-a",
            "feature_names": ["speed_ms", "stored_energy_j"],
            "manoeuvres": [item.value for item in Manoeuvre],
            "recurrent_width": 3,
            "action_transform_id": "beta-v1",
        },
        "energy_bundle": {
            "bundle_id": "bundle-a",
            "admitted": True,
            "physics_id": "physics-a",
            "rules_id": "rules-a",
            "response_id": "response-a",
            "accounting_id": "accounting-a",
            "continuous_profile_id": "profile-a",
        },
        "pit_manifest_id": "pit-a",
        "route_id": "route-a",
        "scenario_id": "scenario-a",
        "observations": [
            {
                "sequence": 0,
                "observed_at_s": 0.0,
                "values": [20.0, 4_000_000.0],
                "feature_mask": [True, True],
                "action_mask": [True, True, True, True],
                "deployment_available": True,
                "news_prior_ids": [],
            },
            {
                "sequence": 1,
                "observed_at_s": 0.2,
                "values": [21.0, 3_900_000.0],
                "feature_mask": [True, True],
                "action_mask": [True, True, True, True],
                "deployment_available": True,
                "news_prior_ids": [],
            },
        ],
    }, sort_keys=True))
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"artifacts": {
        "checkpoint-a": {
            "kind": "policy_checkpoint",
            "path": checkpoint.name,
            "sha256": sha256(checkpoint.read_bytes()).hexdigest(),
        },
        "selection-source": {
            "kind": "weekend_source",
            "path": source.name,
            "sha256": sha256(source.read_bytes()).hexdigest(),
        },
        "protected-target": {
            "kind": "protected_target",
            "path": "protected-target.json",
            "sha256": "c" * 64,
        },
    }}, sort_keys=True))
    manifest = WeekendRunManifest(
        run_id="selection-run",
        partition="selection",
        checkpoint_id="checkpoint-a",
        source_id="selection-source",
        target_id="protected-target",
        schema_id="schema-a",
        energy_bundle_id="bundle-a",
        continuous_profile_id="profile-a",
        physics_id="physics-a",
        rules_id="rules-a",
        pit_manifest_id="pit-a",
        route_id="route-a",
        scenario_id="scenario-a",
        inference_subdeadline_ns=1_000_000_000,
        recommendation_ttl_ns=200_000_000,
    )
    return ArtifactRegistry.load(registry_path), manifest, tmp_path


def test_inference_freezes_recommendations_without_opening_protected_targets(tmp_path: Path) -> None:
    registry, manifest, root = _write_inputs(tmp_path)
    output = root / "run"

    report = run_weekend_inference(manifest, registry, output)

    assert report.status == "completed"
    assert report.recommendation_count == 2
    assert report.target_id == "protected-target"
    assert not (root / "protected-target.json").exists()
    rows = [json.loads(line) for line in (output / "recommendations.jsonl").read_text().splitlines()]
    assert [row["sequence"] for row in rows] == [0, 1]
    assert {row["intent"] for row in rows} == {"attack"}


def test_inference_refuses_a_manifest_identity_mismatch(tmp_path: Path) -> None:
    registry, manifest, root = _write_inputs(tmp_path)
    mismatched = manifest.model_copy(update={"physics_id": "physics-b"})

    with pytest.raises(ValueError, match="physics"):
        run_weekend_inference(mismatched, registry, root / "mismatch")

    wrong_route = manifest.model_copy(update={"route_id": "route-b"})
    with pytest.raises(ValueError, match="route"):
        run_weekend_inference(wrong_route, registry, root / "route-mismatch")


def test_registry_refuses_a_path_escape_before_target_access(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"artifacts": {
        "protected-target": {
            "kind": "protected_target",
            "path": "../protected-target.json",
            "sha256": "c" * 64,
        },
    }}))

    with pytest.raises(ValueError, match="inside"):
        ArtifactRegistry.load(registry_path)


def test_inference_accepts_the_phase8_rollout_step_shape(tmp_path: Path) -> None:
    _registry, manifest, root = _write_inputs(tmp_path)
    source_path = root / "selection-source.json"
    source = json.loads(source_path.read_text())
    observations = source.pop("observations")
    source["steps"] = [
        {
            "observation": row["values"],
            "feature_mask": row["feature_mask"],
            "action_mask": row["action_mask"],
            "deployment_available": row["deployment_available"],
            "observed_at_s": row["observed_at_s"],
        }
        for row in observations
    ]
    source_path.write_text(json.dumps(source, sort_keys=True))
    registry_path = root / "phase8-registry.json"
    registry_payload = json.loads((root / "registry.json").read_text())
    registry_payload["artifacts"]["selection-source"]["sha256"] = sha256(source_path.read_bytes()).hexdigest()
    registry_path.write_text(json.dumps(registry_payload, sort_keys=True))

    report = run_weekend_inference(
        manifest,
        ArtifactRegistry.load(registry_path),
        root / "phase8-shape-run",
    )

    assert report.status == "completed"
    assert report.recommendation_count == 2


def test_inference_refuses_news_that_is_not_registered_for_the_run(tmp_path: Path) -> None:
    _registry, manifest, root = _write_inputs(tmp_path)
    source_path = root / "selection-source.json"
    source = json.loads(source_path.read_text())
    source["observations"][0]["news_prior_ids"] = ["news-a"]
    source_path.write_text(json.dumps(source, sort_keys=True))
    registry_path = root / "news-registry.json"
    registry_payload = json.loads((root / "registry.json").read_text())
    registry_payload["artifacts"]["selection-source"]["sha256"] = sha256(source_path.read_bytes()).hexdigest()
    registry_path.write_text(json.dumps(registry_payload, sort_keys=True))

    with pytest.raises(ValueError, match="news prior"):
        run_weekend_inference(
            manifest,
            ArtifactRegistry.load(registry_path),
            root / "unregistered-news-run",
        )


def test_scoring_opens_the_registered_target_only_after_inference(tmp_path: Path) -> None:
    registry, manifest, root = _write_inputs(tmp_path)
    run_output = root / "run"
    run_weekend_inference(manifest, registry, run_output)
    target = root / "protected-target.json"
    target.write_text(json.dumps({
        "sequences": [0, 1],
        "manoeuvres": ["attack", "hold"],
        "deployment_fractions": [0.5, 0.25],
    }, sort_keys=True))
    registry_path = root / "scoring-registry.json"
    original = json.loads((root / "registry.json").read_text())
    original["artifacts"]["protected-target"]["sha256"] = sha256(target.read_bytes()).hexdigest()
    registry_path.write_text(json.dumps(original, sort_keys=True))

    report = score_weekend_inference(
        manifest,
        ArtifactRegistry.load(registry_path),
        run_output,
        root / "evaluation.json",
    )

    assert report.status == "measured_descriptive"
    assert report.matched_count == 2
    assert report.manoeuvre_agreement_rate == 0.5
    assert report.deployment_mae == pytest.approx(0.125)
    assert report.strategy_claim is False
