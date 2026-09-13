"""Fixed-pit schedule preparation and no-pit validation."""

from dataclasses import asdict
from hashlib import sha256
import json

from poweshift_backend.contracts.pits import FixedPitManifest, FixedPitSchedule, PitMappingMode, PitSourceBinding


_ALLOWED_FUTURE_FIELDS = frozenset({"lap", "entry_time_s", "exit_time_s", "serviced_items"})


def build_fixed_pit_schedule(source: PitSourceBinding) -> FixedPitSchedule:
    """Build a canonical schedule from paired source visits."""
    unknown = set(source.allowed_future_fields) - _ALLOWED_FUTURE_FIELDS
    if unknown:
        raise ValueError(f"unapproved future field: {sorted(unknown)[0]}")
    visits = source.visits
    if any((right.lap, right.entry_time_s) <= (left.lap, left.entry_time_s) for left, right in zip(visits, visits[1:])):
        raise ValueError("pit visits must be chronological")
    payload = {
        "source_id": source.source_id,
        "source_sha256": source.source_sha256,
        "mapping_mode": PitMappingMode.LAP_RELATIVE_FIXED.value,
        "visits": [asdict(visit) for visit in visits],
        "allowed_future_fields": sorted(source.allowed_future_fields),
    }
    schedule_id = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return FixedPitSchedule(schedule_id, PitMappingMode.LAP_RELATIVE_FIXED, visits)


def require_no_pit_window(manifest: FixedPitManifest, start_s: float, end_s: float) -> FixedPitManifest:
    """Return context only when its window contains no pit event."""
    if end_s <= start_s:
        raise ValueError("no-pit window must advance")
    if any(start_s <= event.time_s <= end_s for event in manifest.events):
        raise ValueError("pit event falls inside the declared no-pit window")
    return manifest


def require_no_pit_schedule(schedule: FixedPitSchedule, start_s: float, end_s: float) -> FixedPitSchedule:
    """Prove the fixed schedule has no visit in one episode."""
    if any(visit.entry_time_s <= end_s and visit.exit_time_s >= start_s for visit in schedule.visits):
        raise ValueError("fixed pit visit falls inside the declared no-pit window")
    return schedule
