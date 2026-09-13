from datetime import datetime, timezone

import pytest

from poweshift_backend.contracts.powertrain import ElectricalPowerInput, EvidenceOrigin, PowerInput, PowertrainAllocation
from poweshift_backend.contracts.rules import RuleApplicability, RuleLimit, RegulatoryRuleSnapshot
from poweshift_backend.rules.state import enforce_powertrain_rules


def test_consumer_enforces_snapshot_boundary_and_line_map() -> None:
    snapshot = RegulatoryRuleSnapshot.create(
        snapshot_id="rules-a",
        source_sha256="a" * 64,
        applicability=RuleApplicability(
            2026,
            "event-a",
            "R",
            datetime(2026, 3, 1, 9, tzinfo=timezone.utc),
            datetime(2026, 3, 1, 12, tzinfo=timezone.utc),
        ),
        limits=(RuleLimit("motor_power", 350_000.0, "W", "dc_bus", "timing_line"),),
        line_maps=("timing_line",),
        unsupported_modes=frozenset({"charging"}),
    )
    allocation = PowertrainAllocation(
        5_000.0,
        5_000.0,
        0.0,
        PowerInput(100_000.0, 100_000.0, EvidenceOrigin.SOURCE_DERIVED, "ice-a"),
        ElectricalPowerInput(400_000.0, 380_000.0, 380_000.0, EvidenceOrigin.SOURCE_DERIVED, "motor-a"),
        450_000.0,
        "bundle-a",
    )

    with pytest.raises(ValueError, match="motor power"):
        enforce_powertrain_rules(snapshot, allocation, 2026, "event-a", "R", datetime(2026, 3, 1, 10, tzinfo=timezone.utc), "timing_line", "deployment")
    with pytest.raises(ValueError, match="line map"):
        enforce_powertrain_rules(snapshot, allocation, 2026, "event-a", "R", datetime(2026, 3, 1, 10, tzinfo=timezone.utc), "pit_exit", "deployment")
