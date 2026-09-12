from datetime import datetime, timedelta, timezone

import pytest

from poweshift_backend.contracts.powertrain import (
    ElectricalPowerInput,
    EnergyStoreSpec,
    EvidenceOrigin,
    PowerInput,
    PowertrainAllocation,
)
from poweshift_backend.contracts.rules import RuleApplicability, RuleLimit, RegulatoryRuleSnapshot


def test_electrical_input_uses_one_signed_motor_bus_convention() -> None:
    motoring = ElectricalPowerInput(80_000.0, 72_000.0, 76_000.0, EvidenceOrigin.SOURCE_DERIVED, "map-a")
    recovery = ElectricalPowerInput(-40_000.0, -30_000.0, -28_000.0, EvidenceOrigin.SOURCE_DERIVED, "map-a")

    assert motoring.motor_dc_power_w > 0.0
    assert recovery.motor_dc_power_w < 0.0
    with pytest.raises(ValueError, match="same direction"):
        ElectricalPowerInput(10_000.0, 8_000.0, -7_000.0, EvidenceOrigin.ASSUMED, "bad")


def test_store_capacity_is_not_recharge_throughput() -> None:
    store = EnergyStoreSpec(4_000_000.0, 400_000.0, 3_800_000.0, EvidenceOrigin.SOURCE_DERIVED, "store-a")

    assert store.state_of_charge(2_100_000.0) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="capacity"):
        EnergyStoreSpec(0.0, 0.0, 0.0, EvidenceOrigin.ASSUMED, "missing")


def test_allocation_balances_demand_without_double_counting() -> None:
    allocation = PowertrainAllocation(
        requested_axle_force_n=5_000.0,
        delivered_axle_force_n=4_500.0,
        unmet_axle_force_n=500.0,
        ice=PowerInput(90_000.0, 85_000.0, EvidenceOrigin.SOURCE_DERIVED, "ice-a"),
        electrical=ElectricalPowerInput(20_000.0, 18_000.0, 19_000.0, EvidenceOrigin.SOURCE_DERIVED, "motor-a"),
        wheel_power_w=98_000.0,
        bundle_id="bundle-a",
    )

    assert allocation.delivered_axle_force_n + allocation.unmet_axle_force_n == pytest.approx(
        allocation.requested_axle_force_n
    )
    with pytest.raises(ValueError, match="balance"):
        PowertrainAllocation(
            5_000.0,
            4_500.0,
            0.0,
            allocation.ice,
            allocation.electrical,
            98_000.0,
            "bundle-a",
        )


def test_rule_snapshot_is_source_bound_and_strictly_applicable() -> None:
    snapshot = RegulatoryRuleSnapshot.create(
        snapshot_id="rules-a",
        source_sha256="a" * 64,
        applicability=RuleApplicability(
            2026,
            "event-a",
            "Q",
            datetime(2026, 3, 1, 9, tzinfo=timezone.utc),
            datetime(2026, 3, 1, 12, tzinfo=timezone.utc),
        ),
        limits=(RuleLimit("motor_power", 350_000.0, "W", "dc_bus", None),),
        line_maps=("pit_entry",),
        unsupported_modes=frozenset({"charging"}),
    )

    assert snapshot.content_sha256 == snapshot.recomputed_sha256()
    assert snapshot.applies_to(2026, "event-a", "Q", datetime(2026, 3, 1, 10, tzinfo=timezone.utc))
    assert not snapshot.applies_to(2026, "event-a", "R", datetime(2026, 3, 1, 10, tzinfo=timezone.utc))


def test_rule_snapshot_canonicalizes_equivalent_times_to_utc() -> None:
    utc = RuleApplicability(
        2026,
        "event-a",
        "Q",
        datetime(2026, 3, 1, 9, tzinfo=timezone.utc),
        datetime(2026, 3, 1, 12, tzinfo=timezone.utc),
    )
    india = RuleApplicability(
        2026,
        "event-a",
        "Q",
        datetime(2026, 3, 1, 14, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        datetime(2026, 3, 1, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    )

    def snapshot(applicability: RuleApplicability) -> RegulatoryRuleSnapshot:
        return RegulatoryRuleSnapshot.create(
            snapshot_id="rules-a",
            source_sha256="a" * 64,
            applicability=applicability,
            limits=(RuleLimit("motor_power", 350_000.0, "W", "dc_bus", None),),
            line_maps=("pit_entry",),
            unsupported_modes=frozenset(),
        )

    assert utc.starts_at.tzinfo is timezone.utc
    assert india.starts_at.tzinfo is timezone.utc
    assert snapshot(utc).content_sha256 == snapshot(india).content_sha256
