from datetime import date

import pytest
from pydantic import ValidationError

from poweshift_backend.contracts.acquisition import SessionIdentity
from poweshift_backend.contracts.preparation import ArtifactProvenance, CoverageState, EvaluationSpec, TargetKind
from poweshift_backend.targets.bundle import (
    LapTimeTarget,
    LiveProgressTarget,
    RaceGapTarget,
    TargetBundle,
    TargetStatus,
    build_target_bundle,
    targets_available_by,
)


def _provenance() -> ArtifactProvenance:
    session = SessionIdentity(
        year=2026,
        test_number=1,
        day_number=1,
        date=date(2026, 2, 11),
        venue="Bahrain",
        session_kind="preseason_test",
    )
    return ArtifactProvenance(
        source_identity=session,
        source_rows=("0", "1"),
        coverage_state=CoverageState.ADMITTED,
        config_version="targets-v1",
    )


def _evaluation(target_kind: TargetKind) -> EvaluationSpec:
    return EvaluationSpec(
        target_kind=target_kind,
        target_eligibility="observed accurate laps only",
        comparable_entry_rule="same session and tyre programme",
        status_treatment="deleted and no-time laps are excluded, not zeroed",
        valid_lap_rule="IsAccurate must be true",
    )


def _lap_time_target(availability_s: float, value: float, entry: str = "1") -> LapTimeTarget:
    return LapTimeTarget(
        entry=entry,
        observed_availability_time_s=availability_s,
        units="s",
        value=value,
        status=TargetStatus.VALID,
        status_detail=None,
        comparison_mask=True,
        source_rows=(str(availability_s),),
    )


def test_build_target_bundle_refuses_race_gap_target_support_from_a_testing_session() -> None:
    with pytest.raises(ValueError, match="race_gap.*not approved"):
        build_target_bundle(TargetKind.RACE_GAP, _provenance(), _evaluation(TargetKind.RACE_GAP), ())


def test_build_target_bundle_refuses_classification_target_support_from_a_testing_session() -> None:
    with pytest.raises(ValueError, match="classification.*not approved"):
        build_target_bundle(TargetKind.CLASSIFICATION, _provenance(), _evaluation(TargetKind.CLASSIFICATION), ())


def test_target_bundle_refuses_race_gap_target_when_constructed_directly_bypassing_the_factory() -> None:
    with pytest.raises(ValidationError, match="race_gap.*not approved"):
        TargetBundle(
            target_kind=TargetKind.RACE_GAP,
            provenance=_provenance(),
            evaluation=_evaluation(TargetKind.RACE_GAP),
            records=(),
        )


def test_target_bundle_refuses_classification_target_when_constructed_directly_bypassing_the_factory() -> None:
    with pytest.raises(ValidationError, match="classification.*not approved"):
        TargetBundle(
            target_kind=TargetKind.CLASSIFICATION,
            provenance=_provenance(),
            evaluation=_evaluation(TargetKind.CLASSIFICATION),
            records=(),
        )


def test_build_target_bundle_permits_lap_time_target_support_from_a_testing_session() -> None:
    bundle = build_target_bundle(
        TargetKind.LAP_TIME, _provenance(), _evaluation(TargetKind.LAP_TIME), (_lap_time_target(10.0, 91.2),)
    )

    assert bundle.target_kind is TargetKind.LAP_TIME
    assert bundle.provenance.source_identity.session_kind == "preseason_test"


def test_build_target_bundle_permits_live_progress_target_support_from_a_testing_session() -> None:
    progress = LiveProgressTarget(
        entry="1",
        observed_availability_time_s=5.0,
        units="fraction",
        value=0.25,
        status=TargetStatus.VALID,
        status_detail=None,
        comparison_mask=True,
        source_rows=("0",),
    )

    bundle = build_target_bundle(
        TargetKind.LIVE_PROGRESS, _provenance(), _evaluation(TargetKind.LIVE_PROGRESS), (progress,)
    )

    assert bundle.records == (progress,)


def test_lap_time_target_rejects_a_convenient_value_on_a_deleted_lap() -> None:
    with pytest.raises(ValidationError, match="non-valid status cannot carry a convenient value"):
        LapTimeTarget(
            entry="1",
            observed_availability_time_s=10.0,
            units="s",
            value=91.234,
            status=TargetStatus.DELETED,
            status_detail="track limits",
            comparison_mask=False,
            source_rows=("0",),
        )


def test_lap_time_target_rejects_a_convenient_value_on_a_no_time_lap() -> None:
    with pytest.raises(ValidationError, match="non-valid status cannot carry a convenient value"):
        LapTimeTarget(
            entry="1",
            observed_availability_time_s=10.0,
            units="s",
            value=0.0,
            status=TargetStatus.NO_TIME,
            status_detail="did not cross the line",
            comparison_mask=False,
            source_rows=("0",),
        )


def test_lap_time_target_accepts_a_deleted_lap_with_no_value_and_a_status_reason() -> None:
    target = LapTimeTarget(
        entry="1",
        observed_availability_time_s=10.0,
        units="s",
        value=None,
        status=TargetStatus.DELETED,
        status_detail="track limits",
        comparison_mask=False,
        source_rows=("0",),
    )

    assert target.value is None
    assert target.comparison_mask is False


def test_lap_time_target_requires_a_value_when_status_is_valid() -> None:
    with pytest.raises(ValidationError, match="valid status must carry a value"):
        LapTimeTarget(
            entry="1",
            observed_availability_time_s=10.0,
            units="s",
            value=None,
            status=TargetStatus.VALID,
            status_detail=None,
            comparison_mask=True,
            source_rows=("0",),
        )


def test_target_bundle_rejects_a_record_whose_kind_does_not_match_the_bundle_kind() -> None:
    race_gap_record = RaceGapTarget(
        entry="1",
        entry_pair=("1", "2"),
        observed_availability_time_s=10.0,
        units="s",
        value=1.2,
        status=TargetStatus.VALID,
        status_detail=None,
        comparison_mask=True,
        source_rows=("0",),
    )

    with pytest.raises(ValidationError, match="share the bundle's target kind"):
        TargetBundle(
            target_kind=TargetKind.LAP_TIME,
            provenance=_provenance(),
            evaluation=_evaluation(TargetKind.LAP_TIME),
            records=(race_gap_record,),
        )


def test_target_bundle_rejects_an_evaluation_spec_for_a_different_target_kind() -> None:
    with pytest.raises(ValidationError, match="same kind as the bundle"):
        TargetBundle(
            target_kind=TargetKind.LAP_TIME,
            provenance=_provenance(),
            evaluation=_evaluation(TargetKind.CLASSIFICATION),
            records=(),
        )


def test_target_bundle_is_frozen_against_later_record_reassignment() -> None:
    bundle = build_target_bundle(
        TargetKind.LAP_TIME, _provenance(), _evaluation(TargetKind.LAP_TIME), (_lap_time_target(10.0, 91.2),)
    )

    with pytest.raises(ValidationError):
        bundle.records = ()


def test_targets_available_by_cutoff_is_unaffected_by_a_later_target_value() -> None:
    early = _lap_time_target(availability_s=10.0, value=91.2)
    late = _lap_time_target(availability_s=50.0, value=90.0)
    bundle_without_future = build_target_bundle(
        TargetKind.LAP_TIME, _provenance(), _evaluation(TargetKind.LAP_TIME), (early,)
    )
    bundle_with_future = build_target_bundle(
        TargetKind.LAP_TIME, _provenance(), _evaluation(TargetKind.LAP_TIME), (early, late)
    )

    assert targets_available_by(bundle_without_future, cutoff_s=20.0) == (early,)
    assert targets_available_by(bundle_with_future, cutoff_s=20.0) == (early,)


def test_targets_available_by_cutoff_excludes_future_records_beyond_the_cutoff() -> None:
    on_time = _lap_time_target(availability_s=20.0, value=91.2)
    exactly_at_cutoff = _lap_time_target(availability_s=30.0, value=90.5)
    future = _lap_time_target(availability_s=31.0, value=90.0)
    bundle = build_target_bundle(
        TargetKind.LAP_TIME,
        _provenance(),
        _evaluation(TargetKind.LAP_TIME),
        (on_time, exactly_at_cutoff, future),
    )

    assert targets_available_by(bundle, cutoff_s=30.0) == (on_time, exactly_at_cutoff)
