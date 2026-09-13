from datetime import datetime, timezone
from pathlib import Path

import pytest

from poweshift_backend.contracts.rules import RuleApplicability, RuleLimit, RegulatoryRuleSnapshot
from poweshift_backend.rules.resolve import RuleContext, resolve_snapshot
from poweshift_backend.sources.rules_inventory import RuleSourceRequest, inventory_rule_sources


def _snapshot(event_id: str = "event-a") -> RegulatoryRuleSnapshot:
    return RegulatoryRuleSnapshot.create(
        snapshot_id=f"rules-{event_id}",
        source_sha256="a" * 64,
        applicability=RuleApplicability(
            2026,
            event_id,
            "R",
            datetime(2026, 3, 1, 9, tzinfo=timezone.utc),
            datetime(2026, 3, 1, 12, tzinfo=timezone.utc),
        ),
        limits=(RuleLimit("motor_power", 350_000.0, "W", "dc_bus", "timing_line"),),
        line_maps=("timing_line",),
        unsupported_modes=frozenset(),
    )


def test_inventory_hashes_existing_sources_and_records_missing_coverage(tmp_path: Path) -> None:
    document = tmp_path / "rules.pdf"
    document.write_bytes(b"rules")
    results = inventory_rule_sources(
        (
            RuleSourceRequest(
                "available",
                document,
                2026,
                "event-a",
                "R",
                datetime(2026, 3, 1, 9, tzinfo=timezone.utc),
                datetime(2026, 3, 1, 12, tzinfo=timezone.utc),
            ),
            RuleSourceRequest(
                "missing",
                tmp_path / "missing.pdf",
                2026,
                "event-b",
                "R",
                datetime(2026, 3, 8, 9, tzinfo=timezone.utc),
                datetime(2026, 3, 8, 12, tzinfo=timezone.utc),
            ),
        )
    )

    assert results[0].content_sha256 is not None
    assert results[0].supported is True
    assert results[0].starts_at == datetime(2026, 3, 1, 9, tzinfo=timezone.utc)
    assert results[1].supported is False
    assert results[1].reason == "source document is missing"


def test_resolver_never_substitutes_another_event_or_edition() -> None:
    context = RuleContext(2026, "event-b", "R", datetime(2026, 3, 1, 10, tzinfo=timezone.utc))

    with pytest.raises(ValueError, match="coverage"):
        resolve_snapshot((_snapshot("event-a"),), context)
