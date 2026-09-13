import pytest

from poweshift_backend.contracts.representation import NumericalPolicy
from poweshift_backend.contracts.reconstruction import (
    DeclaredAssumption,
    EffectiveComponent,
    EffectiveProfile,
    MechanicsAssumptions,
    SupportState,
)
from poweshift_backend.reconstruction.baseline import runtime_from_profile
from poweshift_backend.reconstruction.comparison import NumericalCheck, select_numerical_policy


def test_readiness_selects_only_a_predeclared_passing_numerical_policy() -> None:
    coarse = NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12)
    refined = NumericalPolicy(step_s=0.02, axle_tolerance_n=0.05, event_time_tolerance_s=1e-12)
    checks = (
        NumericalCheck(coarse, "training:propulsion", 0.04, 0.04),
        NumericalCheck(coarse, "selection:braking", 0.04, 0.04),
        NumericalCheck(refined, "training:propulsion", 0.001, 0.001, 0.001),
        NumericalCheck(refined, "training:braking", 0.001, 0.001, 0.001),
        NumericalCheck(refined, "training:coast", 0.001, 0.001, 0.001),
        NumericalCheck(refined, "selection:propulsion", 0.001, 0.001, 0.001),
        NumericalCheck(refined, "selection:braking", 0.001, 0.001, 0.001),
        NumericalCheck(refined, "selection:coast", 0.001, 0.001, 0.001),
    )

    selected = select_numerical_policy((coarse, refined), checks, maximum_difference_ms=0.01)

    assert selected == refined


def test_readiness_fails_closed_when_a_controlled_regime_is_missing() -> None:
    policy = NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12)

    with pytest.raises(ValueError, match="missing"):
        select_numerical_policy(
            (policy,),
            (NumericalCheck(policy, "training:propulsion", 0.001, 0.001, 0.001),),
            maximum_difference_ms=0.01,
        )


def test_runtime_reloads_selected_numerical_policy_without_hard_coded_tolerances() -> None:
    assumed = SupportState.ASSUMED
    profile = EffectiveProfile(
        components=(
            EffectiveComponent(name="propulsion", value=100.0, unit="N", support=assumed),
            EffectiveComponent(name="resistance", value=1.0, unit="N/(m/s)^2", support=assumed),
            EffectiveComponent(name="braking", value=100.0, unit="N", support=assumed),
            EffectiveComponent(name="grip", value=1.0, unit="1", support=assumed),
        ),
        assumptions=MechanicsAssumptions(
            reference_mass_kg=DeclaredAssumption(value=800.0, unit="kg", support=assumed, source="test"),
            fuel_load_kg=DeclaredAssumption(value=30.0, unit="kg", support=assumed, source="test"),
            front_axle_distance_m=DeclaredAssumption(value=1.6, unit="m", support=assumed, source="test"),
            rear_axle_distance_m=DeclaredAssumption(value=1.6, unit="m", support=assumed, source="test"),
        ),
    )
    policy = NumericalPolicy(step_s=0.02, axle_tolerance_n=0.03, event_time_tolerance_s=4e-8, axle_max_iterations=17)

    runtime = runtime_from_profile(profile, policy)

    assert runtime.integration.step_s == 0.02
    assert runtime.integration.event_time_tolerance_s == 4e-8
    assert runtime.solve_config.tolerance_n == 0.03
    assert runtime.solve_config.max_iterations == 17


def test_readiness_rejects_nonfinite_or_conflicting_regime_measurements() -> None:
    policy = NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12)
    checks = tuple(
        NumericalCheck(policy, regime, 0.001, 0.001, 0.001)
        for regime in ("training:propulsion", "training:braking", "training:coast", "selection:propulsion", "selection:braking", "selection:coast")
    )

    with pytest.raises(ValueError, match="conflicting"):
        select_numerical_policy((policy,), checks + (checks[0],), maximum_difference_ms=0.01)
    with pytest.raises(ValueError, match="finite"):
        select_numerical_policy((policy,), checks[:-1] + (NumericalCheck(policy, "selection:coast", float("nan"), 0.001, 0.001),), maximum_difference_ms=0.01)
