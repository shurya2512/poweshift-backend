"""Admit only the entries a bundle-bound coverage disposition names. Phase 1 evidence is read-only."""

from hashlib import sha256
from pathlib import Path

from poweshift_backend.contracts.preparation import CoverageChoice, CoverageDisposition


def bundle_sha256(bundle_path: Path) -> str:
    """Hash the immutable Phase 1 bundle without modifying it."""
    return sha256(bundle_path.read_bytes()).hexdigest()


def validate_disposition(disposition: CoverageDisposition | None, bundle_path: Path) -> CoverageDisposition:
    """Admit a coverage disposition only when it is bound to this bundle and does not block Phase 2."""
    if disposition is None:
        raise ValueError("no coverage disposition recorded")
    if disposition.bundle_sha256 != bundle_sha256(bundle_path):
        raise ValueError("coverage disposition does not match the acquisition bundle")
    if disposition.choice is CoverageChoice.BLOCK_PHASE_2:
        raise ValueError("coverage disposition blocks phase 2")
    return disposition


def resolve_admitted_entries(disposition: CoverageDisposition, session: dict, session_key: str) -> list[str]:
    """Resolve admitted entries for one session; a named entry can never exceed the roster or reverse an exclusion."""
    if session_key not in disposition.admitted_entries:
        raise ValueError(f"coverage disposition does not name session {session_key}")
    if disposition.excluded_entries.get(session_key, {}) != session["exclusions"]:
        raise ValueError(f"recorded exclusions for {session_key} do not match the bundle")
    roster = set(session["roster"])
    excluded = set(session["exclusions"])
    named = disposition.admitted_entries[session_key]
    for entry in named:
        if entry not in roster:
            raise ValueError(f"admitted entry {entry} is outside the roster for {session_key}")
        if entry in excluded:
            raise ValueError(f"admitted entry {entry} was excluded by phase 1 for {session_key}")
    return list(named)
