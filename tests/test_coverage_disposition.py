from datetime import date
from hashlib import sha256

from poweshift_backend.contracts.preparation import CoverageChoice
from poweshift_backend.data.coverage_disposition import build_admission_disposition


def _bundle() -> dict:
    return {
        "sessions": [
            {
                "identity": {"date": "2026-02-11"},
                "roster": ["1", "3", "6"],
                "exclusions": {"6": "missing_tyre_context"},
            },
            {
                "identity": {"date": "2026-02-12"},
                "roster": ["1", "3"],
                "exclusions": {},
            },
        ]
    }


def test_build_admission_disposition_admits_the_roster_minus_that_days_exclusions(tmp_path) -> None:
    bundle_path = tmp_path / "acquisition_bundle.json"
    bundle_path.write_text("sealed bundle content")

    disposition = build_admission_disposition(_bundle(), bundle_path, reviewer="coverage-reviewer", recorded_on=date(2026, 9, 12))

    assert disposition.choice is CoverageChoice.ADMIT_NAMED_ENTRIES
    assert disposition.admitted_entries == {"2026-02-11": ["1", "3"], "2026-02-12": ["1", "3"]}


def test_build_admission_disposition_mirrors_the_bundles_exclusions_exactly(tmp_path) -> None:
    bundle_path = tmp_path / "acquisition_bundle.json"
    bundle_path.write_text("sealed bundle content")

    disposition = build_admission_disposition(_bundle(), bundle_path, reviewer="coverage-reviewer", recorded_on=date(2026, 9, 12))

    assert disposition.excluded_entries == {"2026-02-11": {"6": "missing_tyre_context"}, "2026-02-12": {}}


def test_build_admission_disposition_binds_to_the_actual_bundle_file_hash(tmp_path) -> None:
    bundle_path = tmp_path / "acquisition_bundle.json"
    bundle_path.write_text("sealed bundle content")

    disposition = build_admission_disposition(_bundle(), bundle_path, reviewer="coverage-reviewer", recorded_on=date(2026, 9, 12))

    assert disposition.bundle_sha256 == sha256(bundle_path.read_bytes()).hexdigest()


def test_build_admission_disposition_records_the_reviewer_and_date(tmp_path) -> None:
    bundle_path = tmp_path / "acquisition_bundle.json"
    bundle_path.write_text("sealed bundle content")

    disposition = build_admission_disposition(_bundle(), bundle_path, reviewer="coverage-reviewer", recorded_on=date(2026, 9, 12))

    assert disposition.reviewer == "coverage-reviewer"
    assert disposition.recorded_on == date(2026, 9, 12)
