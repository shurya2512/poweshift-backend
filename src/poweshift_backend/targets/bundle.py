"""TargetBundle: isolated, kind-separated target records that never feed reconstruction inputs."""

from enum import Enum
from typing import Literal

from pydantic import model_validator

from poweshift_backend.contracts.acquisition import StrictModel
from poweshift_backend.contracts.preparation import ArtifactProvenance, EvaluationSpec, TargetKind

# No approved source coverage exists yet for these kinds from a testing session.
_TESTING_UNSUPPORTED_KINDS = frozenset({TargetKind.RACE_GAP, TargetKind.CLASSIFICATION})


class TargetStatus(str, Enum):
    VALID = "valid"
    DELETED = "deleted"
    NO_TIME = "no_time"
    DISQUALIFIED = "disqualified"
    LAP_DEFICIT = "lap_deficit"
    PENALTY = "penalty"
    UNAVAILABLE = "unavailable"


class _TargetRecord(StrictModel):
    """Fields shared by every target record; a value never stands in for a categorical status."""

    entry: str
    observed_availability_time_s: float
    units: str
    value: float | None
    status: TargetStatus
    status_detail: str | None
    comparison_mask: bool
    source_rows: tuple[str, ...]

    @model_validator(mode="after")
    def _value_matches_status(self) -> "_TargetRecord":
        if self.status is TargetStatus.VALID and self.value is None:
            raise ValueError("a valid status must carry a value")
        if self.status is not TargetStatus.VALID and self.value is not None:
            raise ValueError("a non-valid status cannot carry a convenient value")
        return self


class LapTimeTarget(_TargetRecord):
    target_kind: Literal[TargetKind.LAP_TIME] = TargetKind.LAP_TIME


class RaceGapTarget(_TargetRecord):
    target_kind: Literal[TargetKind.RACE_GAP] = TargetKind.RACE_GAP
    entry_pair: tuple[str, str]


class ClassificationTarget(_TargetRecord):
    target_kind: Literal[TargetKind.CLASSIFICATION] = TargetKind.CLASSIFICATION


class LiveProgressTarget(_TargetRecord):
    target_kind: Literal[TargetKind.LIVE_PROGRESS] = TargetKind.LIVE_PROGRESS


TargetRecord = LapTimeTarget | RaceGapTarget | ClassificationTarget | LiveProgressTarget


class TargetBundle(StrictModel):
    """One target kind's records, kept out of reconstruction inputs and never merged with another kind."""

    target_kind: TargetKind
    provenance: ArtifactProvenance
    evaluation: EvaluationSpec
    records: tuple[LapTimeTarget | RaceGapTarget | ClassificationTarget | LiveProgressTarget, ...]

    @model_validator(mode="after")
    def _records_match_the_bundle_kind(self) -> "TargetBundle":
        if self.evaluation.target_kind is not self.target_kind:
            raise ValueError("the evaluation spec must target the same kind as the bundle")
        for record in self.records:
            if record.target_kind is not self.target_kind:
                raise ValueError("every record in a bundle must share the bundle's target kind")
        return self

    @model_validator(mode="after")
    def _refuses_testing_session_race_gap_and_classification(self) -> "TargetBundle":
        is_testing_session = self.provenance.source_identity.session_kind == "preseason_test"
        if is_testing_session and self.target_kind in _TESTING_UNSUPPORTED_KINDS:
            raise ValueError(f"{self.target_kind.value} target support is not approved from a testing session")
        return self


def build_target_bundle(
    target_kind: TargetKind,
    provenance: ArtifactProvenance,
    evaluation: EvaluationSpec,
    records: tuple[TargetRecord, ...],
) -> TargetBundle:
    """Build a TargetBundle; the testing-session refusal is enforced by the model itself."""
    return TargetBundle(target_kind=target_kind, provenance=provenance, evaluation=evaluation, records=records)


def targets_available_by(bundle: TargetBundle, cutoff_s: float) -> tuple[TargetRecord, ...]:
    """Return only records observed at or before the cutoff; later records never affect this result."""
    return tuple(record for record in bundle.records if record.observed_availability_time_s <= cutoff_s)
