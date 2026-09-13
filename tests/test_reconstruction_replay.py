import numpy as np

from poweshift_backend.contracts.reconstruction import (
    DeclaredAssumption, EffectiveComponent, EffectiveProfile, MechanicsAssumptions, SupportState,
)
from poweshift_backend.contracts.representation import NumericalPolicy
from poweshift_backend.driver.controller import DriverMode
from poweshift_backend.reconstruction.baseline import FittedBaseline, runtime_from_profile
from poweshift_backend.reconstruction.inputs import TelemetryChunk
from poweshift_backend.reconstruction.replay import is_verified_continuation, replay_chunk


def test_verified_continuation_allows_the_recorded_positive_sample_gap() -> None:
    continuation = ("2026-02-19", "1", "run", 0, 1)

    assert is_verified_continuation("2026-02-19", "1", "run", 0, 1, {continuation})


def test_forecast_replay_does_not_read_future_recorded_controls() -> None:
    assumed = SupportState.ASSUMED
    profile = EffectiveProfile(
        components=(
            EffectiveComponent(name="propulsion", value=3000.0, unit="N", support=assumed),
            EffectiveComponent(name="resistance", value=1.0, unit="N/(m/s)^2", support=assumed),
            EffectiveComponent(name="braking", value=3000.0, unit="N", support=assumed),
            EffectiveComponent(name="grip", value=2.0, unit="1", support=assumed),
        ),
        assumptions=MechanicsAssumptions(
            reference_mass_kg=DeclaredAssumption(value=800.0, unit="kg", support=assumed, source="test"),
            fuel_load_kg=DeclaredAssumption(value=30.0, unit="kg", support=assumed, source="test"),
            front_axle_distance_m=DeclaredAssumption(value=1.6, unit="m", support=assumed, source="test"),
            rear_axle_distance_m=DeclaredAssumption(value=1.6, unit="m", support=assumed, source="test"),
        ),
    )
    runtime = runtime_from_profile(profile, NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12))
    baseline = FittedBaseline(profile, runtime, {}, {}, ())

    def chunk(future_throttle: np.ndarray) -> TelemetryChunk:
        return TelemetryChunk(
            "test", "1", "run", 0, "selection", np.array([0.0, 0.1, 0.2]), np.array([10.0, 10.0, 10.0]),
            {"throttle_pct": future_throttle, "brake": np.array([0.0, 0.0, 0.0]), "n_gear": np.ones(3)},
            {"speed_ms": np.ones(3, dtype=np.bool_), "throttle_pct": np.array([True, False, False]), "brake": np.array([True, False, False]), "n_gear": np.ones(3, dtype=np.bool_)},
            {}, (),
        )

    first, _ = replay_chunk(chunk(np.array([50.0, 0.0, 0.0])), baseline, DriverMode.FORECAST)
    second, _ = replay_chunk(chunk(np.array([50.0, 100.0, 100.0])), baseline, DriverMode.FORECAST)

    assert first.exclusion is None
    assert np.allclose(first.predicted_speed_ms, second.predicted_speed_ms)
