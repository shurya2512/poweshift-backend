from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from poweshift_backend.contracts.acquisition import SessionIdentity
from poweshift_backend.contracts.preparation import ArtifactProvenance, CoverageState, EvaluationSpec, TargetKind
from poweshift_backend.information.projector import (
    PitEventKind,
    PitProjection,
    PitSourceRecord,
    pit_context_available_by,
    project_pit_records,
)
from poweshift_backend.targets.bundle import TargetBundle


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
        source_rows=("0", "1", "2"),
        coverage_state=CoverageState.ADMITTED,
        config_version="pit-v1",
    )


def _laps() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "DriverNumber": ["1", "1", "2"],
            "source_row": [0, 1, 2],
            "PitInTime": pd.to_timedelta(["0:10:00", None, None]),
            "PitOutTime": pd.to_timedelta([None, "0:11:30", None]),
            "Compound": ["SOFT", "SOFT", "MEDIUM"],
        }
    )


def test_project_pit_records_extracts_only_pit_in_and_pit_out_events() -> None:
    projection = project_pit_records(_laps(), _provenance())

    assert [record.event_kind for record in projection.records] == [PitEventKind.PIT_IN, PitEventKind.PIT_OUT]
    assert [record.event_time_s for record in projection.records] == [600.0, 690.0]
    assert [record.entry for record in projection.records] == ["1", "1"]


def test_pit_source_record_has_no_compound_or_schedule_field() -> None:
    assert set(PitSourceRecord.model_fields) == {
        "entry",
        "event_kind",
        "event_time_s",
        "retrospective_disclosure",
        "source_rows",
    }


def test_every_projected_pit_record_carries_the_retrospective_disclosure() -> None:
    projection = project_pit_records(_laps(), _provenance())

    assert all(record.retrospective_disclosure is True for record in projection.records)


def test_pit_source_record_rejects_a_disclosure_of_false() -> None:
    with pytest.raises(ValidationError):
        PitSourceRecord(
            entry="1",
            event_kind=PitEventKind.PIT_IN,
            event_time_s=600.0,
            retrospective_disclosure=False,
            source_rows=("0",),
        )


def test_a_pit_source_record_cannot_enter_a_target_bundle() -> None:
    projection = project_pit_records(_laps(), _provenance())
    evaluation = EvaluationSpec(
        target_kind=TargetKind.LAP_TIME,
        target_eligibility="observed accurate laps only",
        comparable_entry_rule="same session and tyre programme",
        status_treatment="deleted and no-time laps are excluded, not zeroed",
        valid_lap_rule="IsAccurate must be true",
    )

    with pytest.raises(ValidationError):
        TargetBundle(
            target_kind=TargetKind.LAP_TIME,
            provenance=_provenance(),
            evaluation=evaluation,
            records=(projection.records[0],),
        )


def test_pit_projection_is_frozen_against_later_record_reassignment() -> None:
    projection = project_pit_records(_laps(), _provenance())

    with pytest.raises(ValidationError):
        projection.records = ()


def test_pit_context_available_by_cutoff_is_unaffected_by_a_later_pit_event() -> None:
    projection_without_future = PitProjection(
        provenance=_provenance(),
        records=(
            PitSourceRecord(entry="1", event_kind=PitEventKind.PIT_IN, event_time_s=600.0, source_rows=("0",)),
        ),
    )
    projection_with_future = PitProjection(
        provenance=_provenance(),
        records=(
            PitSourceRecord(entry="1", event_kind=PitEventKind.PIT_IN, event_time_s=600.0, source_rows=("0",)),
            PitSourceRecord(entry="1", event_kind=PitEventKind.PIT_OUT, event_time_s=690.0, source_rows=("1",)),
        ),
    )

    before = pit_context_available_by(projection_without_future, cutoff_s=650.0)
    after = pit_context_available_by(projection_with_future, cutoff_s=650.0)

    assert before == after == (projection_without_future.records[0],)


def test_pit_context_available_by_cutoff_excludes_events_beyond_the_cutoff() -> None:
    projection = project_pit_records(_laps(), _provenance())

    assert pit_context_available_by(projection, cutoff_s=600.0) == (projection.records[0],)
    assert pit_context_available_by(projection, cutoff_s=690.0) == projection.records
