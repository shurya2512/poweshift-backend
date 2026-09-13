"""Strict contracts for registered weekend inference and outputs."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from pydantic import Field, model_validator

from poweshift_backend.contracts.acquisition import StrictModel
from poweshift_backend.contracts.action import ActionRequest


class ObservationFrame(StrictModel):
    """One source-bound policy observation at a known sequence."""

    sequence: int = Field(ge=0)
    observed_at_s: float
    values: tuple[float, ...]
    feature_mask: tuple[bool, ...]
    action_mask: tuple[bool, ...]
    deployment_available: bool
    news_prior_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_shapes(self) -> "ObservationFrame":
        """Reject malformed or nonfinite observation rows."""
        if not self.values or len(self.values) != len(self.feature_mask):
            raise ValueError("observation values and feature mask must align")
        if not self.action_mask or not any(self.action_mask):
            raise ValueError("observation needs an available manoeuvre")
        if not isfinite(self.observed_at_s) or not all(isfinite(value) for value in self.values):
            raise ValueError("observation values must be finite")
        return self


@dataclass(frozen=True)
class InferenceResult:
    """Accepted proposal or finite fallback from one policy request."""

    run_id: str
    request_id: str
    sequence: int
    status: Literal["accepted", "fallback"]
    action: ActionRequest
    memory_version: int
    started_monotonic_ns: int
    completed_monotonic_ns: int
    policy_id: str
    energy_bundle_id: str
    continuous_profile_id: str
    physics_id: str
    rules_id: str
    pit_manifest_id: str
    route_id: str
    scenario_id: str
    news_prior_ids: tuple[str, ...]
    binding_reasons: tuple[str, ...] = ()


class RecommendationFrame(StrictModel):
    """Expiring recommendation without future realised delivery."""

    run_id: str
    request_id: str
    sequence: int = Field(ge=0)
    intent: str
    deployment_fraction: float = Field(ge=0.0, le=1.0)
    requested_power_w: float | None
    reachable_power_w: float | None
    evidence_status: Literal["retrospective_inference", "unsupported_fallback"]
    binding_reasons: tuple[str, ...]
    created_monotonic_ns: int = Field(ge=0)
    expires_monotonic_ns: int = Field(ge=0)
    memory_version: int = Field(ge=0)
    policy_id: str
    energy_bundle_id: str
    continuous_profile_id: str
    physics_id: str
    rules_id: str
    pit_manifest_id: str
    route_id: str
    scenario_id: str
    news_prior_ids: tuple[str, ...]
    retrospective: Literal[True] = True


class LiveRecommendationFrame(StrictModel):
    """One 5 Hz decision bound to the latest 4 Hz source frame."""

    decision_sequence: int = Field(ge=0)
    source_sequence: int = Field(ge=0)
    source_observed_at_s: float
    input_hz: Literal[4.0] = 4.0
    decision_hz: Literal[5.0] = 5.0
    held_source_frame: bool
    partition: Literal["selection", "final_evaluation"]
    recommendation: RecommendationFrame


class WeekendRunManifest(StrictModel):
    """Registered checkpoint and protected-weekend inference boundary."""

    run_id: str = Field(min_length=1)
    partition: Literal["selection", "final_evaluation"]
    checkpoint_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    schema_id: str = Field(min_length=1)
    energy_bundle_id: str = Field(min_length=1)
    continuous_profile_id: str = Field(min_length=1)
    physics_id: str = Field(min_length=1)
    rules_id: str = Field(min_length=1)
    pit_manifest_id: str = Field(min_length=1)
    route_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    news_prior_ids: tuple[str, ...] = ()
    inference_subdeadline_ns: int = Field(gt=0)
    recommendation_ttl_ns: int = Field(gt=0)


class WeekendRunReport(StrictModel):
    """Frozen inference completion without protected-target access."""

    run_id: str
    status: Literal["completed", "stopped"]
    partition: Literal["selection", "final_evaluation"]
    source_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_id: str
    checkpoint_id: str
    recommendation_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    recommendations_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_id: str
    energy_bundle_id: str
    continuous_profile_id: str
    physics_id: str
    rules_id: str
    pit_manifest_id: str
    route_id: str
    scenario_id: str
    limitations: tuple[str, ...]


class WeekendEvaluationReport(StrictModel):
    """Descriptive score produced after frozen inference completes."""

    run_id: str
    status: Literal["measured_descriptive"]
    partition: Literal["selection", "final_evaluation"]
    target_id: str
    target_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    recommendations_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    matched_count: int = Field(ge=1)
    manoeuvre_agreement_rate: float = Field(ge=0.0, le=1.0)
    deployment_mae: float = Field(ge=0.0, le=1.0)
    strategy_claim: Literal[False] = False
    limitations: tuple[str, ...]


class RunStatus(StrictModel):
    """Current supervisor state for one registered run."""

    run_id: str
    status: Literal["running", "paused", "completed", "stopped", "failed"]
    recommendation_count: int = Field(ge=0)
    error: str | None = None
