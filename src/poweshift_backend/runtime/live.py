"""Live 4 Hz ingestion with held-state 5 Hz policy decisions."""

import json
import time

from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.contracts.runtime import (
    LiveRecommendationFrame,
    ObservationFrame,
    WeekendRunManifest,
)
from poweshift_backend.recommendations.frame import build_recommendation
from poweshift_backend.runtime.artifacts import ArtifactRegistry
from poweshift_backend.runtime.inference import ResidentPolicy
from poweshift_backend.runtime.weekend import _require_identities, _schema


class LivePolicySession:
    """Retain the latest source frame and resident policy memory."""

    def __init__(self, manifest: WeekendRunManifest, resident: ResidentPolicy) -> None:
        self.manifest = manifest
        self.resident = resident
        self.latest_observation: ObservationFrame | None = None
        self.decision_sequence = 0
        self.last_decision_source: int | None = None

    @classmethod
    def from_registered_run(cls, registry: ArtifactRegistry, run_id: str) -> "LivePolicySession":
        """Load one registered validation or test policy without its target."""
        manifest = WeekendRunManifest.model_validate_json(
            registry.resolve(run_id, "run_manifest").read_text(),
        )
        if manifest.run_id != run_id:
            raise ValueError("registered live manifest does not match the run ID")
        source = json.loads(registry.resolve(manifest.source_id, "weekend_source").read_text())
        schema = _schema(source["schema"])
        bundle = EnergyBundleCompatibility(**source["energy_bundle"])
        _require_identities(manifest, schema, bundle, source)
        registry.reference(manifest.target_id, "protected_target")
        resident = ResidentPolicy(
            registry.resolve(manifest.checkpoint_id, "policy_checkpoint"),
            schema,
            bundle,
            manifest.pit_manifest_id,
            manifest.route_id,
            manifest.scenario_id,
        )
        return cls(manifest, resident)

    def ingest(self, observation: ObservationFrame) -> None:
        """Accept the next source frame only on a strict 4 Hz clock."""
        previous = self.latest_observation
        if previous is not None:
            if observation.sequence != previous.sequence + 1:
                raise ValueError("live input must use the next sequence")
            if abs(observation.observed_at_s - previous.observed_at_s - 0.25) > 1e-6:
                raise ValueError("live source timestamps must use a 4 Hz cadence")
        elif observation.sequence != 0:
            raise ValueError("live input must start at sequence zero")
        if not set(observation.news_prior_ids).issubset(self.manifest.news_prior_ids):
            raise ValueError("live observation uses an unregistered news prior")
        self.latest_observation = observation

    def decide(self) -> LiveRecommendationFrame:
        """Emit one 5 Hz decision from the latest accepted source frame."""
        observation = self.latest_observation
        if observation is None:
            raise LookupError("live inference has no source observation")
        result = self.resident.infer(
            self.manifest.run_id,
            f"{self.manifest.run_id}:live:{self.decision_sequence}",
            observation,
            deadline_ns=time.monotonic_ns() + self.manifest.inference_subdeadline_ns,
        )
        recommendation = build_recommendation(
            result,
            expires_after_ns=self.manifest.recommendation_ttl_ns,
        )
        frame = LiveRecommendationFrame(
            decision_sequence=self.decision_sequence,
            source_sequence=observation.sequence,
            source_observed_at_s=observation.observed_at_s,
            held_source_frame=self.last_decision_source == observation.sequence,
            partition=self.manifest.partition,
            recommendation=recommendation,
        )
        self.last_decision_source = observation.sequence
        self.decision_sequence += 1
        return frame
