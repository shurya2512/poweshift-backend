"""Strict historical rule snapshot resolution."""

from dataclasses import dataclass
from datetime import datetime

from poweshift_backend.contracts.rules import RegulatoryRuleSnapshot


@dataclass(frozen=True)
class RuleContext:
    """Historical context requested by a consumer."""

    season: int
    event_id: str
    session: str
    at: datetime


def resolve_snapshot(snapshots: tuple[RegulatoryRuleSnapshot, ...], context: RuleContext) -> RegulatoryRuleSnapshot:
    """Resolve exactly one applicable source without edition fallback."""
    matches = tuple(
        snapshot
        for snapshot in snapshots
        if snapshot.applies_to(context.season, context.event_id, context.session, context.at)
    )
    if len(matches) != 1:
        raise ValueError("historical rule coverage must resolve exactly one snapshot")
    snapshot = matches[0]
    if snapshot.content_sha256 != snapshot.recomputed_sha256():
        raise ValueError("historical rule snapshot hash is invalid")
    return snapshot
