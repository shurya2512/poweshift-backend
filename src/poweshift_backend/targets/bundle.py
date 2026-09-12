"""TargetBundle: isolated, kind-separated target records that never feed reconstruction inputs."""

from enum import Enum
from math import isfinite
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


class ComparableTimingPair(StrictModel):
    """A signed timing comparison with complete observed context."""

    first: LapTimeTarget
    second: LapTimeTarget
    session_kind: Literal["practice", "qualifying"]
    qualifying_segment: Literal["Q1", "Q2", "Q3"] | None
    first_session_key: str
    second_session_key: str
    first_segment: str
    second_segment: str
    cutoff_s: float
    tyre_matched: bool
    fuel_known: bool
    weather_known: bool
    track_phase_known: bool
    traffic_clear: bool
    pit_free: bool
    coverage_complete: bool
    comparison_mask: bool

    @model_validator(mode="after")
    def _requires_complete_comparable_context(self) -> "ComparableTimingPair":
        if self.first.entry == self.second.entry:
            raise ValueError("a timing pair must contain two entries")
        if (
            self.first.units != "s"
            or self.second.units != "s"
            or self.first.value is None
            or self.second.value is None
            or not isfinite(self.first.value)
            or not isfinite(self.second.value)
            or not isfinite(self.cutoff_s)
        ):
            raise ValueError("a timing pair requires finite second values")
        if self.session_kind == "qualifying" and self.qualifying_segment is None:
            raise ValueError("a qualifying pair must name one segment")
        if self.session_kind == "practice" and self.qualifying_segment is not None:
            raise ValueError("a practice pair cannot name a qualifying segment")
        if (
            self.first_session_key != self.second_session_key
            or self.first_segment != self.second_segment
            or self.first_segment != (self.qualifying_segment or "practice")
            or self.first.observed_availability_time_s > self.cutoff_s
            or self.second.observed_availability_time_s > self.cutoff_s
        ):
            raise ValueError("a timing pair requires the same session, segment and cutoff")
        eligible = (
            self.first.status is TargetStatus.VALID
            and self.second.status is TargetStatus.VALID
            and self.first.comparison_mask
            and self.second.comparison_mask
            and self.weather_known
            and self.track_phase_known
            and self.pit_free
            and self.coverage_complete
        )
        if self.session_kind == "practice":
            eligible = eligible and self.tyre_matched and self.fuel_known and self.traffic_clear
        if self.comparison_mask and not eligible:
            raise ValueError("a true comparison mask requires complete comparable context")
        return self

    @property
    def signed_gap_s(self) -> float:
        """Return first minus second in seconds."""
        if self.first.value is None or self.second.value is None:
            raise ValueError("a signed gap requires valid timing values")
        return self.first.value - self.second.value


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
