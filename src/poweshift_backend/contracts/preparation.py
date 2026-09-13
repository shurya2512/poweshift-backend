"""Contracts for the Phase 2 coverage decision, split and preparation limits."""

from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from poweshift_backend.contracts.acquisition import SessionIdentity, StrictModel


class CoverageChoice(str, Enum):
    BLOCK_PHASE_2 = "block_phase_2"
    ADMIT_NAMED_ENTRIES = "admit_named_entries"


# Session keys are the bundle's ISO dates, e.g. "2026-02-11".
_SessionKey = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class CoverageDisposition(StrictModel):
    """The human coverage decision, bound to the exact Phase 1 bundle it was made against."""

    choice: CoverageChoice
    admitted_entries: dict[_SessionKey, list[str]]
    excluded_entries: dict[_SessionKey, dict[str, str]]
    reviewer: str
    recorded_on: date
    bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _choice_matches_named_entries(self) -> "CoverageDisposition":
        if self.choice is CoverageChoice.BLOCK_PHASE_2 and (self.admitted_entries or self.excluded_entries):
            raise ValueError("a blocking disposition names no sessions")
        if self.choice is CoverageChoice.ADMIT_NAMED_ENTRIES and not self.admitted_entries:
            raise ValueError("an admitting disposition must name at least one session")
        return self


_SPLIT_SELECTION = date(2026, 2, 18)
_SPLIT_FINAL_EVALUATION = (date(2026, 2, 19), date(2026, 2, 20))


class SplitManifest(StrictModel):
    """The immutable Phase 2 split; distinct from the inactive Phase 1 proposed split."""

    manifest_kind: Literal["phase_2_split"] = "phase_2_split"
    training: Literal["Test 1"]
    selection: date
    final_evaluation: tuple[date, date]
    phase_1_proposal_activated: Literal[False] = False

    @model_validator(mode="after")
    def _fixed_to_the_approved_dates(self) -> "SplitManifest":
        if self.selection != _SPLIT_SELECTION or self.final_evaluation != _SPLIT_FINAL_EVALUATION:
            raise ValueError("the phase 2 split manifest is fixed to the approved dates")
        return self


class PreprocessingSpec(StrictModel):
    """Preparation limits. No threshold has a default; each must be chosen and recorded."""

    gap_limit_s: float
    staleness_limit_s: float
    smoothing_limit_s: float
    window_limit_s: float
    availability_convention: Literal["current_past_prefix"]


class TargetKind(str, Enum):
    LAP_TIME = "lap_time"
    RACE_GAP = "race_gap"
    CLASSIFICATION = "classification"
    LIVE_PROGRESS = "live_progress"


class EvaluationSpec(StrictModel):
    """Target eligibility and comparability rules, kept as separate named fields."""

    target_kind: TargetKind
    target_eligibility: str
    comparable_entry_rule: str
    status_treatment: str
    valid_lap_rule: str


class CoverageState(str, Enum):
    ADMITTED = "admitted"
    EXCLUDED = "excluded"


class ArtifactProvenance(StrictModel):
    """Identity and provenance every Phase 2 output carries."""

    source_identity: SessionIdentity
    source_rows: tuple[str, ...]
    coverage_state: CoverageState
    config_version: str
