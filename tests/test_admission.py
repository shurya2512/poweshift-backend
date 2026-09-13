from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from poweshift_backend.contracts.preparation import (
    CoverageChoice,
    CoverageDisposition,
    EvaluationSpec,
    PreprocessingSpec,
    SplitManifest,
    TargetKind,
)
from poweshift_backend.prepare.admission import (
    bundle_sha256,
    resolve_admitted_entries,
    validate_disposition,
)


def _write_bundle(tmp_path, content: str = '{"sessions": []}') -> Path:
    bundle_path = tmp_path / "acquisition_bundle.json"
    bundle_path.write_text(content)
    return bundle_path


def _disposition(bundle_hash: str, **overrides) -> CoverageDisposition:
    fields = {
        "choice": CoverageChoice.ADMIT_NAMED_ENTRIES,
        "admitted_entries": {"2026-02-11": ["1", "3"]},
        "excluded_entries": {"2026-02-11": {"6": "missing_tyre_context"}},
        "reviewer": "coverage-reviewer",
        "recorded_on": date(2026, 2, 21),
        "bundle_sha256": bundle_hash,
    }
    fields.update(overrides)
    return CoverageDisposition(**fields)


def test_validate_disposition_rejects_an_absent_disposition(tmp_path) -> None:
    bundle_path = _write_bundle(tmp_path)

    with pytest.raises(ValueError, match="no coverage disposition"):
        validate_disposition(None, bundle_path)


def test_validate_disposition_rejects_a_disposition_bound_to_a_different_bundle(tmp_path) -> None:
    bundle_path = _write_bundle(tmp_path)
    disposition = _disposition(bundle_hash="0" * 64)

    with pytest.raises(ValueError, match="does not match"):
        validate_disposition(disposition, bundle_path)


def test_validate_disposition_rejects_a_choice_that_blocks_phase_2(tmp_path) -> None:
    bundle_path = _write_bundle(tmp_path)
    bundle_hash = bundle_sha256(bundle_path)
    disposition = _disposition(
        bundle_hash=bundle_hash,
        choice=CoverageChoice.BLOCK_PHASE_2,
        admitted_entries={},
        excluded_entries={},
    )

    with pytest.raises(ValueError, match="blocks phase 2"):
        validate_disposition(disposition, bundle_path)


def test_validate_disposition_accepts_a_matching_admitting_disposition(tmp_path) -> None:
    bundle_path = _write_bundle(tmp_path)
    bundle_hash = bundle_sha256(bundle_path)
    disposition = _disposition(bundle_hash=bundle_hash)

    assert validate_disposition(disposition, bundle_path) is disposition


def test_resolve_admitted_entries_returns_only_the_named_entries(tmp_path) -> None:
    bundle_path = _write_bundle(tmp_path)
    disposition = _disposition(bundle_hash=bundle_sha256(bundle_path))
    session = {"roster": ["1", "3", "6"], "exclusions": {"6": "missing_tyre_context"}}

    assert resolve_admitted_entries(disposition, session, "2026-02-11") == ["1", "3"]


def test_resolve_admitted_entries_rejects_an_entry_outside_the_roster(tmp_path) -> None:
    bundle_path = _write_bundle(tmp_path)
    disposition = _disposition(
        bundle_hash=bundle_sha256(bundle_path),
        admitted_entries={"2026-02-11": ["1", "99"]},
        excluded_entries={"2026-02-11": {}},
    )
    session = {"roster": ["1", "3"], "exclusions": {}}

    with pytest.raises(ValueError, match="outside the roster"):
        resolve_admitted_entries(disposition, session, "2026-02-11")


def test_resolve_admitted_entries_rejects_an_entry_phase_1_excluded(tmp_path) -> None:
    bundle_path = _write_bundle(tmp_path)
    disposition = _disposition(
        bundle_hash=bundle_sha256(bundle_path),
        admitted_entries={"2026-02-11": ["1", "6"]},
        excluded_entries={"2026-02-11": {"6": "missing_tyre_context"}},
    )
    session = {"roster": ["1", "3", "6"], "exclusions": {"6": "missing_tyre_context"}}

    with pytest.raises(ValueError, match="excluded by phase 1"):
        resolve_admitted_entries(disposition, session, "2026-02-11")


def test_resolve_admitted_entries_rejects_an_unnamed_session(tmp_path) -> None:
    bundle_path = _write_bundle(tmp_path)
    disposition = _disposition(bundle_hash=bundle_sha256(bundle_path))
    session = {"roster": ["1", "3"], "exclusions": {}}

    with pytest.raises(ValueError, match="does not name session"):
        resolve_admitted_entries(disposition, session, "2026-02-12")


def test_resolve_admitted_entries_rejects_exclusions_that_do_not_match_the_bundle(tmp_path) -> None:
    bundle_path = _write_bundle(tmp_path)
    disposition = _disposition(
        bundle_hash=bundle_sha256(bundle_path),
        admitted_entries={"2026-02-11": ["1"]},
        excluded_entries={"2026-02-11": {"6": "wrong_reason"}},
    )
    session = {"roster": ["1", "3", "6"], "exclusions": {"6": "missing_tyre_context"}}

    with pytest.raises(ValueError, match="do not match the bundle"):
        resolve_admitted_entries(disposition, session, "2026-02-11")


def test_coverage_disposition_rejects_a_session_key_that_is_not_an_iso_date() -> None:
    with pytest.raises(ValidationError):
        _disposition(
            bundle_hash="a" * 64,
            admitted_entries={"test-day-one": ["1", "3"]},
            excluded_entries={"test-day-one": {"6": "missing_tyre_context"}},
        )


def test_coverage_disposition_rejects_a_bundle_hash_that_is_not_a_sha256_hex_digest() -> None:
    with pytest.raises(ValidationError):
        _disposition(bundle_hash="not-a-hash")


@pytest.mark.parametrize(
    ("choice", "admitted_entries", "excluded_entries"),
    [
        (CoverageChoice.BLOCK_PHASE_2, {"2026-02-11": ["1"]}, {}),
        (CoverageChoice.ADMIT_NAMED_ENTRIES, {}, {}),
    ],
)
def test_coverage_disposition_rejects_a_choice_inconsistent_with_its_named_entries(
    choice: CoverageChoice, admitted_entries: dict, excluded_entries: dict
) -> None:
    with pytest.raises(ValidationError):
        _disposition(
            bundle_hash="a" * 64,
            choice=choice,
            admitted_entries=admitted_entries,
            excluded_entries=excluded_entries,
        )


@pytest.mark.parametrize(
    "missing_field",
    ["gap_limit_s", "staleness_limit_s", "smoothing_limit_s", "window_limit_s", "availability_convention"],
)
def test_preprocessing_spec_requires_every_threshold_with_no_invented_default(missing_field: str) -> None:
    fields = {
        "gap_limit_s": 5.0,
        "staleness_limit_s": 2.0,
        "smoothing_limit_s": 0.5,
        "window_limit_s": 10.0,
        "availability_convention": "current_past_prefix",
    }
    del fields[missing_field]

    with pytest.raises(ValidationError, match="missing"):
        PreprocessingSpec(**fields)


def test_preprocessing_spec_accepts_every_threshold_named_explicitly() -> None:
    spec = PreprocessingSpec(
        gap_limit_s=5.0,
        staleness_limit_s=2.0,
        smoothing_limit_s=0.5,
        window_limit_s=10.0,
        availability_convention="current_past_prefix",
    )

    assert spec.gap_limit_s == 5.0
    assert spec.availability_convention == "current_past_prefix"


def test_evaluation_spec_keeps_target_rules_as_separate_named_fields() -> None:
    spec = EvaluationSpec(
        target_kind=TargetKind.LAP_TIME,
        target_eligibility="observed accurate laps only",
        comparable_entry_rule="same session and tyre programme",
        status_treatment="deleted and no-time laps are excluded, not zeroed",
        valid_lap_rule="IsAccurate must be true",
    )

    assert spec.target_kind == TargetKind.LAP_TIME
    assert spec.status_treatment == "deleted and no-time laps are excluded, not zeroed"


def _split_manifest_fields(**overrides) -> dict:
    fields = {
        "training": "Test 1",
        "selection": date(2026, 2, 18),
        "final_evaluation": (date(2026, 2, 19), date(2026, 2, 20)),
    }
    fields.update(overrides)
    return fields


def test_split_manifest_records_it_is_a_phase_2_manifest_that_leaves_phase_1_inactive() -> None:
    manifest = SplitManifest(**_split_manifest_fields())

    assert manifest.manifest_kind == "phase_2_split"
    assert manifest.phase_1_proposal_activated is False


def test_split_manifest_rejects_dates_outside_the_approved_manifest() -> None:
    with pytest.raises(ValidationError, match="fixed to the approved dates"):
        SplitManifest(**_split_manifest_fields(selection=date(2026, 2, 19)))


def test_split_manifest_is_frozen_against_later_attribute_assignment() -> None:
    manifest = SplitManifest(**_split_manifest_fields())

    with pytest.raises(ValidationError):
        manifest.training = "Test 2"


@pytest.mark.parametrize("missing_field", ["training", "selection", "final_evaluation"])
def test_split_manifest_requires_training_selection_and_final_evaluation_to_be_stated(missing_field: str) -> None:
    fields = _split_manifest_fields()
    del fields[missing_field]

    with pytest.raises(ValidationError, match="missing"):
        SplitManifest(**fields)


def test_bundle_sha256_matches_a_manual_digest_of_the_file(tmp_path) -> None:
    bundle_path = _write_bundle(tmp_path, content='{"sessions": ["a"]}')

    assert bundle_sha256(bundle_path) == sha256(bundle_path.read_bytes()).hexdigest()
