"""Hash candidate historical rule documents and record missing coverage."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class RuleSourceRequest:
    """Candidate document and its intended historical coverage."""

    source_id: str
    path: Path
    season: int
    event_id: str
    session: str
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None or self.ends_at <= self.starts_at:
            raise ValueError("rule source applicability must be a timezone-aware interval")
        object.__setattr__(self, "starts_at", self.starts_at.astimezone(timezone.utc))
        object.__setattr__(self, "ends_at", self.ends_at.astimezone(timezone.utc))


@dataclass(frozen=True)
class RuleSourceInventoryEntry:
    """One hashed candidate or explicit missing-source result."""

    source_id: str
    season: int
    event_id: str
    session: str
    starts_at: datetime
    ends_at: datetime
    supported: bool
    content_sha256: str | None
    reason: str | None


def inventory_rule_sources(requests: tuple[RuleSourceRequest, ...]) -> tuple[RuleSourceInventoryEntry, ...]:
    """Inventory exact files without substituting nearby documents."""
    results = []
    for request in requests:
        if not request.path.is_file():
            results.append(
                RuleSourceInventoryEntry(
                    request.source_id,
                    request.season,
                    request.event_id,
                    request.session,
                    request.starts_at,
                    request.ends_at,
                    False,
                    None,
                    "source document is missing",
                )
            )
            continue
        digest = sha256(request.path.read_bytes()).hexdigest()
        results.append(
            RuleSourceInventoryEntry(
                request.source_id,
                request.season,
                request.event_id,
                request.session,
                request.starts_at,
                request.ends_at,
                True,
                digest,
                None,
            )
        )
    return tuple(results)
