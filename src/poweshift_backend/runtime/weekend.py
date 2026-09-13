"""Target-isolated inference over a registered weekend source."""

from hashlib import sha256
import json
from pathlib import Path
import time
from collections.abc import Callable

from poweshift_backend.contracts.action import Manoeuvre
from poweshift_backend.contracts.news import NewsPrior
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.contracts.runtime import ObservationFrame, WeekendRunManifest, WeekendRunReport
from poweshift_backend.policy.schema import PolicySchema
from poweshift_backend.recommendations.frame import build_recommendation
from poweshift_backend.runtime.artifacts import ArtifactRegistry
from poweshift_backend.runtime.inference import ResidentPolicy


def _schema(payload: dict[str, object]) -> PolicySchema:
    values = dict(payload)
    values["feature_names"] = tuple(values["feature_names"])
    values["manoeuvres"] = tuple(Manoeuvre(value) for value in values["manoeuvres"])
    return PolicySchema(**values)


def _observation(payload: dict[str, object]) -> ObservationFrame:
    values = dict(payload)
    for name in ("values", "feature_mask", "action_mask", "news_prior_ids"):
        values[name] = tuple(values.get(name, ()))
    return ObservationFrame.model_validate(values)


def _source_observations(source: dict[str, object]) -> tuple[ObservationFrame, ...]:
    raw = source.get("observations")
    if raw is not None:
        return tuple(_observation(value) for value in raw)
    steps = source.get("steps", ())
    rows = []
    for sequence, step in enumerate(steps):
        if "observed_at_s" not in step:
            raise ValueError("phase 8 rollout steps need source-bound observation times for inference")
        rows.append(_observation({
            "sequence": sequence,
            "observed_at_s": step["observed_at_s"],
            "values": step["observation"],
            "feature_mask": step["feature_mask"],
            "action_mask": step["action_mask"],
            "deployment_available": step.get("deployment_available", True),
            "news_prior_ids": step.get("news_prior_ids", ()),
        }))
    return tuple(rows)


def _require_identities(
    manifest: WeekendRunManifest,
    schema: PolicySchema,
    bundle: EnergyBundleCompatibility,
    source: dict[str, object],
) -> None:
    expected = {
        "schema": (manifest.schema_id, schema.schema_id),
        "energy bundle": (manifest.energy_bundle_id, bundle.bundle_id),
        "continuous profile": (manifest.continuous_profile_id, bundle.continuous_profile_id),
        "physics": (manifest.physics_id, bundle.physics_id),
        "rules": (manifest.rules_id, bundle.rules_id),
        "pit manifest": (manifest.pit_manifest_id, source.get("pit_manifest_id")),
        "route": (manifest.route_id, source.get("route_id")),
        "scenario": (manifest.scenario_id, source.get("scenario_id")),
    }
    for name, pair in expected.items():
        if pair[0] != pair[1]:
            raise ValueError(f"weekend {name} identity is incompatible")


def run_weekend_inference(
    manifest: WeekendRunManifest,
    registry: ArtifactRegistry,
    output: Path,
    *,
    before_sequence: Callable[[int], bool] | None = None,
) -> WeekendRunReport:
    """Freeze recommendations without resolving the protected target."""
    if output.exists():
        raise FileExistsError(f"weekend inference output already exists: {output}")
    source_ref = registry.reference(manifest.source_id, "weekend_source")
    source_path = registry.resolve(manifest.source_id, "weekend_source")
    checkpoint_path = registry.resolve(manifest.checkpoint_id, "policy_checkpoint")
    registry.reference(manifest.target_id, "protected_target")
    source = json.loads(source_path.read_text())
    schema = _schema(source["schema"])
    bundle = EnergyBundleCompatibility(**source["energy_bundle"])
    _require_identities(manifest, schema, bundle, source)
    rows = _source_observations(source)
    if not rows or tuple(row.sequence for row in rows) != tuple(range(len(rows))):
        raise ValueError("weekend observations must be nonempty and sequential")
    permitted_news = set(manifest.news_prior_ids)
    for prior_id in permitted_news:
        prior = NewsPrior.model_validate_json(registry.resolve(prior_id, "news_prior").read_text())
        if prior.prior_id != prior_id:
            raise ValueError("registered news prior identity differs from its content")
    if any(not set(row.news_prior_ids).issubset(permitted_news) for row in rows):
        raise ValueError("weekend observation uses a news prior not registered for the run")

    output.mkdir(parents=True)
    recommendations_path = output / "recommendations.jsonl"
    resident = ResidentPolicy(
        checkpoint_path,
        schema,
        bundle,
        manifest.pit_manifest_id,
        manifest.route_id,
        manifest.scenario_id,
    )
    recommendation_count = 0
    fallback_count = 0
    digest = sha256()
    with recommendations_path.open("x") as stream:
        for row in rows:
            if before_sequence is not None and not before_sequence(row.sequence):
                break
            deadline = time.monotonic_ns() + manifest.inference_subdeadline_ns
            result = resident.infer(
                manifest.run_id,
                f"{manifest.run_id}:{row.sequence}",
                row,
                deadline_ns=deadline,
            )
            fallback_count += result.status == "fallback"
            recommendation = build_recommendation(
                result,
                expires_after_ns=manifest.recommendation_ttl_ns,
            )
            line = f"{recommendation.model_dump_json()}\n"
            stream.write(line)
            stream.flush()
            digest.update(line.encode())
            recommendation_count += 1
    report = WeekendRunReport(
        run_id=manifest.run_id,
        status="completed" if recommendation_count == len(rows) else "stopped",
        partition=manifest.partition,
        source_id=manifest.source_id,
        source_sha256=source_ref.sha256,
        target_id=manifest.target_id,
        checkpoint_id=manifest.checkpoint_id,
        recommendation_count=recommendation_count,
        fallback_count=fallback_count,
        recommendations_sha256=digest.hexdigest(),
        policy_id=schema.schema_id,
        energy_bundle_id=bundle.bundle_id,
        continuous_profile_id=bundle.continuous_profile_id,
        physics_id=bundle.physics_id,
        rules_id=bundle.rules_id,
        pit_manifest_id=manifest.pit_manifest_id,
        route_id=manifest.route_id,
        scenario_id=manifest.scenario_id,
        limitations=(
            "retrospective weekend observations do not establish live-feed latency",
            "recommendations are not realised delivery or strategy superiority evidence",
        ),
    )
    (output / "report.json").write_text(report.model_dump_json(indent=2) + "\n")
    return report
