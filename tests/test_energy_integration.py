import pytest

from poweshift_backend.contracts.powertrain import (
    ElectricalPowerInput,
    EnergyStoreSpec,
    EvidenceOrigin,
    PowerInput,
    PowertrainAllocation,
)
from poweshift_backend.energy.accounting import AccountingConfig
from poweshift_backend.energy.integration import CoupledEnergyState, EnergyStage, integrate_energy_stages
from poweshift_backend.energy.state import EnergyState
from poweshift_backend.physics.state import MechanicsState
from poweshift_backend.reconstruction.replay import replay_offline_energy


def _allocation(motor_dc_w: float, bundle_id: str = "bundle-a") -> PowertrainAllocation:
    return PowertrainAllocation(
        1_000.0,
        1_000.0,
        0.0,
        PowerInput(200_000.0, 200_000.0, EvidenceOrigin.SOURCE_DERIVED, "ice-a"),
        ElectricalPowerInput(motor_dc_w, motor_dc_w, motor_dc_w, EvidenceOrigin.SOURCE_DERIVED, "motor-a"),
        200_000.0 + motor_dc_w,
        bundle_id,
    )


def _config() -> AccountingConfig:
    return AccountingConfig(
        EnergyStoreSpec(1_000.0, 0.0, 1_000.0, EvidenceOrigin.SOURCE_DERIVED, "store-a"),
        40_000_000.0,
        0.5,
        0.8,
        0.0,
        "accounting-a",
    )


def test_energy_stages_split_source_transitions_and_update_fuel_once() -> None:
    initial = CoupledEnergyState(
        MechanicsState(0.0, 20.0, 0.0, 0.0, 10.0),
        EnergyState(500.0, 0.0, 0.0),
        "bundle-a",
    )
    states = integrate_energy_stages(initial, (EnergyStage(0.001, _allocation(100.0)), EnergyStage(0.002, _allocation(-100.0))), _config())

    assert states[-1].mechanics.time_s == pytest.approx(0.002)
    assert states[-1].mechanics.fuel_mass_kg == pytest.approx(9.99998)
    assert states[-1].energy.discharge_throughput_j == pytest.approx(0.1)
    assert states[-1].energy.recharge_throughput_j == pytest.approx(0.1)
    with pytest.raises(ValueError, match="bundle"):
        integrate_energy_stages(initial, (EnergyStage(0.001, _allocation(0.0, "other")),), _config())


def test_energy_replay_is_separately_selected_and_never_runtime_enabled() -> None:
    initial = CoupledEnergyState(
        MechanicsState(0.0, 20.0, 0.0, 0.0, 10.0),
        EnergyState(500.0, 0.0, 0.0),
        "bundle-a",
    )

    replay = replay_offline_energy(initial, (EnergyStage(0.001, _allocation(100.0)),), _config())

    assert replay.mode == "offline_energy"
    assert replay.runtime_enabled is False
    assert replay.accounting_evidence_id == "accounting-a"
