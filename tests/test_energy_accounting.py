import pytest

from poweshift_backend.contracts.powertrain import EnergyStoreSpec, EvidenceOrigin
from poweshift_backend.energy.accounting import AccountingConfig, account_energy_step
from poweshift_backend.energy.state import EnergyState


def _config() -> AccountingConfig:
    return AccountingConfig(
        store=EnergyStoreSpec(1_000.0, 0.0, 1_000.0, EvidenceOrigin.SOURCE_DERIVED, "store-a"),
        fuel_lower_heating_value_j_kg=40_000_000.0,
        ice_efficiency=0.5,
        charge_efficiency=0.8,
        named_store_loss_w=10.0,
        evidence_id="accounting-a",
    )


def test_positive_terminal_power_drains_storage_and_fuel_is_counted_once() -> None:
    result = account_energy_step(EnergyState(800.0, 0.0, 0.0), 10.0, 200_000.0, 100.0, 1.0, _config())

    assert result.state.stored_energy_j == pytest.approx(690.0)
    assert result.state.discharge_throughput_j == pytest.approx(100.0)
    assert result.fuel_mass_kg == pytest.approx(9.99)
    assert result.store_loss_j == pytest.approx(10.0)


def test_recovery_cannot_create_more_energy_than_reaches_the_store() -> None:
    result = account_energy_step(EnergyState(800.0, 0.0, 0.0), 10.0, 0.0, -100.0, 1.0, _config())

    assert result.state.stored_energy_j == pytest.approx(870.0)
    assert result.state.recharge_throughput_j == pytest.approx(100.0)
    assert result.stored_recovery_j == pytest.approx(80.0)


def test_store_saturation_is_explicitly_curtailed() -> None:
    result = account_energy_step(EnergyState(990.0, 0.0, 0.0), 10.0, 0.0, -100.0, 1.0, _config())

    assert result.state.stored_energy_j == pytest.approx(1_000.0)
    assert result.curtailed_energy_j == pytest.approx(60.0)
