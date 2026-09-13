import numpy as np
import pytest

from poweshift_backend.contracts.powertrain import EvidenceOrigin
from poweshift_backend.powertrain.experiment import FrozenResponseEvidence, compare_response_candidates
from poweshift_backend.powertrain.maps import SourcePowerMap
from poweshift_backend.powertrain.response import ResponseConfig, ResponseState, resolve_ice_response


def test_source_map_interpolates_only_inside_supported_speed() -> None:
    power_map = SourcePowerMap((6_000.0, 9_000.0, 12_000.0), (400_000.0, 500_000.0, 450_000.0), EvidenceOrigin.SOURCE_DERIVED, "map-a")

    assert power_map.maximum_power_w(7_500.0) == pytest.approx(450_000.0)
    with pytest.raises(ValueError, match="speed"):
        power_map.maximum_power_w(5_000.0)


def test_finite_response_respects_rate_and_refuses_shift_or_low_speed() -> None:
    power_map = SourcePowerMap((6_000.0, 12_000.0), (400_000.0, 500_000.0), EvidenceOrigin.SOURCE_DERIVED, "map-a")
    config = ResponseConfig(100_000.0, 200_000.0, 6_000.0, "response-a")

    result = resolve_ice_response(ResponseState(100_000.0), 500_000.0, 9_000.0, 0.5, power_map, config)

    assert result.delivered_power_w == pytest.approx(150_000.0)
    with pytest.raises(ValueError, match="shift"):
        resolve_ice_response(ResponseState(100_000.0), 200_000.0, 9_000.0, 0.1, power_map, config, shift_active=True)
    with pytest.raises(ValueError, match="low-speed"):
        resolve_ice_response(ResponseState(100_000.0), 200_000.0, 5_000.0, 0.1, power_map, config)


def test_matched_comparison_rejects_a_worse_neural_residual() -> None:
    evidence = FrozenResponseEvidence("evidence-a", "missing_turbo_lag", "source-a", "shaft_w", "rk4-0.01")
    observed = np.array([100.0, 120.0, 140.0])
    result = compare_response_candidates(
        evidence,
        observed,
        {
            "numerical": np.array([101.0, 119.0, 141.0]),
            "algebraic": np.array([100.0, 118.0, 144.0]),
            "finite": np.array([99.0, 121.0, 141.0]),
            "neural_residual": np.array([90.0, 130.0, 150.0]),
        },
        maximum_mae=2.0,
    )

    assert result.retained_candidate == "numerical"
    assert result.neural_accepted is False
