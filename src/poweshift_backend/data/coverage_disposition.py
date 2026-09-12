"""Record the human coverage decision: admit every entry Phase 1 did not exclude."""

from datetime import date
from pathlib import Path

from poweshift_backend.contracts.preparation import CoverageChoice, CoverageDisposition
from poweshift_backend.prepare.admission import bundle_sha256


def build_admission_disposition(bundle: dict, bundle_path: Path, reviewer: str, recorded_on: date) -> CoverageDisposition:
    """Build the recorded disposition: admitted = roster minus exclusions, on every session."""
    admitted_entries: dict[str, list[str]] = {}
    excluded_entries: dict[str, dict[str, str]] = {}
    for session in bundle["sessions"]:
        session_key = session["identity"]["date"]
        exclusions = session["exclusions"]
        roster = session["roster"]
        admitted_entries[session_key] = [entry for entry in roster if entry not in exclusions]
        excluded_entries[session_key] = dict(exclusions)
    return CoverageDisposition(
        choice=CoverageChoice.ADMIT_NAMED_ENTRIES,
        admitted_entries=admitted_entries,
        excluded_entries=excluded_entries,
        reviewer=reviewer,
        recorded_on=recorded_on,
        bundle_sha256=bundle_sha256(bundle_path),
    )
