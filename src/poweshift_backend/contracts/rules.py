"""Historical rule snapshots with strict source and applicability binding."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite


@dataclass(frozen=True)
class RuleApplicability:
    """Event, session and UTC interval covered by a rule source."""

    season: int
    event_id: str
    session: str
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        if self.season < 1950 or not self.event_id or not self.session:
            raise ValueError("rule applicability identity is invalid")
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("rule applicability timestamps must be timezone-aware")
        object.__setattr__(self, "starts_at", self.starts_at.astimezone(timezone.utc))
        object.__setattr__(self, "ends_at", self.ends_at.astimezone(timezone.utc))
        if self.ends_at <= self.starts_at:
            raise ValueError("rule applicability interval must advance")


@dataclass(frozen=True)
class RuleLimit:
    """One source-defined limit and its measurement boundary."""

    name: str
    value: float
    unit: str
    measurement_boundary: str
    line_map_id: str | None

    def __post_init__(self) -> None:
        if not self.name or not self.unit or not self.measurement_boundary or not isfinite(self.value):
            raise ValueError("rule limit is incomplete")


@dataclass(frozen=True)
class RegulatoryRuleSnapshot:
    """Canonical immutable rules selected for one historical context."""

    snapshot_id: str
    source_sha256: str
    applicability: RuleApplicability
    limits: tuple[RuleLimit, ...]
    line_maps: tuple[str, ...]
    unsupported_modes: frozenset[str]
    content_sha256: str

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        source_sha256: str,
        applicability: RuleApplicability,
        limits: tuple[RuleLimit, ...],
        line_maps: tuple[str, ...],
        unsupported_modes: frozenset[str],
    ) -> "RegulatoryRuleSnapshot":
        """Create a snapshot with a canonical content hash."""
        snapshot = cls(snapshot_id, source_sha256, applicability, limits, line_maps, unsupported_modes, "pending")
        return cls(snapshot_id, source_sha256, applicability, limits, line_maps, unsupported_modes, snapshot.recomputed_sha256())

    def __post_init__(self) -> None:
        if not self.snapshot_id or len(self.source_sha256) != 64:
            raise ValueError("rule snapshot source provenance is invalid")
        try:
            int(self.source_sha256, 16)
        except ValueError as error:
            raise ValueError("rule snapshot source provenance is invalid") from error
        if len({limit.name for limit in self.limits}) != len(self.limits):
            raise ValueError("rule limits must have unique names")
        if len(set(self.line_maps)) != len(self.line_maps):
            raise ValueError("rule line maps must be unique")
        if self.content_sha256 != "pending" and self.content_sha256 != self.recomputed_sha256():
            raise ValueError("rule snapshot content hash is invalid")

    def recomputed_sha256(self) -> str:
        """Return the canonical hash excluding the hash field itself."""
        payload = {
            "snapshot_id": self.snapshot_id,
            "source_sha256": self.source_sha256,
            "applicability": {
                "season": self.applicability.season,
                "event_id": self.applicability.event_id,
                "session": self.applicability.session,
                "starts_at": self.applicability.starts_at.isoformat(),
                "ends_at": self.applicability.ends_at.isoformat(),
            },
            "limits": [limit.__dict__ for limit in self.limits],
            "line_maps": list(self.line_maps),
            "unsupported_modes": sorted(self.unsupported_modes),
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def applies_to(self, season: int, event_id: str, session: str, at: datetime) -> bool:
        """Return whether this exact historical context is covered."""
        target = self.applicability
        return (
            at.tzinfo is not None
            and season == target.season
            and event_id == target.event_id
            and session == target.session
            and target.starts_at <= at <= target.ends_at
        )
