"""Versioned evidence and model contracts for offline entry updates."""

from typing import Literal

from pydantic import Field

from poweshift_backend.contracts.acquisition import StrictModel


class NumericalPolicy(StrictModel):
    """Numerical settings selected before any candidate scoring."""

    step_s: float = Field(gt=0.0)
    axle_tolerance_n: float = Field(gt=0.0)
    event_time_tolerance_s: float = Field(ge=0.0)
    axle_max_iterations: int = Field(default=32, ge=1)
    reference_rtol: float = Field(default=1e-9, gt=0.0)
    reference_atol: float = Field(default=1e-11, gt=0.0)


class WeekendAuditSession(StrictModel):
    """One cache session's source boundary."""

    weekend: str
    partition: Literal["training", "selection", "final_evaluation", "reserved"]
    event_date: str
    session_count: int = Field(ge=0)
    session_names: tuple[str, ...]
    stream_names: tuple[str, ...]
    source_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    content_access: Literal["hashed", "inventory_only"]
    source_state: Literal["verified", "missing", "incomplete", "unproved"]
    source_issues: tuple[str, ...]
    target_state: Literal["refused"] = "refused"
    target_issues: tuple[str, ...]


class RaceSourceAudit(StrictModel):
    """Bound provenance for one acquired race source."""

    manifest_path: str
    weekend: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    roster_size: int = Field(ge=0)
    source_state: Literal["verified", "incomplete"]
    coverage_notes: tuple[str, ...]
    target_state: Literal["refused"] = "refused"
    target_issues: tuple[str, ...]


class WeekendAudit(StrictModel):
    """Immutable source and target readiness evidence."""

    audit_kind: Literal["weekend_source_audit_v2"] = "weekend_source_audit_v2"
    cache_root: str
    sessions: tuple[WeekendAuditSession, ...]
    race_sources: tuple[RaceSourceAudit, ...]
    source_status: Literal["verified", "incomplete"]
    missing_race_weekends: tuple[str, ...]
    status: Literal["blocked"] = "blocked"
    blockers: tuple[str, ...]


class ComparisonPolicy(StrictModel):
    """Frozen evidence, metric and budget boundary for one comparison."""

    numerical: NumericalPolicy
    metric: Literal["speed_mae_ms"]
    minimum_relative_improvement: float = Field(gt=0.0, lt=1.0)
    evaluation_reuse: Literal["reused_evaluation", "fresh_confirmation"]
    per_update_refit_budget: int = Field(ge=0)
    training_teacher_budget: int = Field(default=80, ge=1)
    candidate_epochs: int = Field(default=20, ge=1)
    candidate_seed: int = Field(default=20260912, ge=0)
    candidate_learning_rate: float = Field(default=1e-3, gt=0.0)
    candidate_max_units: int = Field(default=80, ge=1)
    candidate_runtime_budget_s: float = Field(default=60.0, gt=0.0)
    update_mode: Literal["matched_refit", "disabled"] = "matched_refit"


class ModelRecord(StrictModel):
    """Architecture and frozen transform identity for a saved candidate."""

    candidate: Literal["gru", "transformer"]
    feature_names: tuple[str, ...]
    transform_id: str
    policy_id: str
    training_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    teacher_fit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_component_names: tuple[str, ...]
    profile_upper_bounds: tuple[float, ...]
    latent_width: int = Field(ge=1)
    hidden_width: int = Field(ge=1)
    layers: int = Field(ge=1)
    heads: int = Field(ge=1)
    feedforward_width: int = Field(ge=1)
    variance_floor: float = Field(gt=0.0)
    objective: Literal["gaussian_nll_full"]
