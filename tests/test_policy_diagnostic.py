import pytest

from poweshift_backend.energy.allocator import DeploymentPrior
from poweshift_backend.policy.diagnostic import (
    DiagnosticTrace,
    FittedProfile,
    RaceInteractionPrior,
    classify_race_interaction,
    create_diagnostic_model,
    evaluate_diagnostic_policy,
    race_reserve_penalty,
    race_step_reward,
    run_diagnostic_updates,
)


def test_diagnostic_updates_preserve_additive_energy_ledgers() -> None:
    prior = DeploymentPrior(0.2, 5_000_000.0, 5_000_000.0, 0.95, 0.8)
    trace = DiagnosticTrace("training", "trace-a", (40.0, 42.0, 38.0, 35.0), (1.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 1.0), 1.0)
    profile = FittedProfile("1", 7_000.0, 0.8, 120.0)
    report = run_diagnostic_updates((trace,), {"1": profile}, prior, updates=2, seed=3)
    assert report["updates"] == 2
    assert report["gross_deployment_j"] >= 0.0
    assert report["gross_harvest_j"] > 0.0
    assert report["electric_boost_fraction"] == 0.2
    assert report["harvest_cap_j_per_lap"] == 5_000_000.0


def test_race_interaction_requires_a_close_and_closing_opponent() -> None:
    prior = RaceInteractionPrior()
    opportunity, threat = classify_race_interaction(prior, 0.9, 0.6, 0.7, 0.1, braking=False)
    assert opportunity is True
    assert threat is False
    assert classify_race_interaction(prior, 0.9, 0.1, 0.7, 0.6, braking=False) == (False, True)
    assert classify_race_interaction(prior, 0.9, 0.6, 0.7, 0.6, braking=True) == (False, False)


def test_race_reward_prioritises_traffic_and_charges_early_energy() -> None:
    prior = RaceInteractionPrior()
    free_air = race_step_reward(prior, 0.5, 100_000.0, 1.0, 1.0, False, False)
    attack = race_step_reward(prior, 0.5, 100_000.0, 1.0, 1.0, True, False)
    late_attack = race_step_reward(prior, 0.5, 100_000.0, 0.0, 1.0, True, False)
    assert attack > free_air
    assert late_attack > attack


def test_race_reward_is_invariant_to_trace_resolution() -> None:
    prior = RaceInteractionPrior()
    one_step = race_step_reward(prior, 0.5, 100_000.0, 0.5, 1.0, True, False)
    two_half_steps = 2.0 * race_step_reward(prior, 0.5, 50_000.0, 0.5, 0.5, True, False)
    assert two_half_steps == pytest.approx(one_step)


def test_race_reserve_penalty_releases_the_store_on_the_final_lap() -> None:
    prior = RaceInteractionPrior()
    assert race_reserve_penalty(prior, state_of_charge=0.2, target_fraction=0.8) < 0.0
    assert race_reserve_penalty(prior, state_of_charge=0.0, target_fraction=0.0) == 0.0


def test_policy_evaluation_reports_requested_deployment() -> None:
    prior = DeploymentPrior(0.2, 5_000_000.0, 5_000_000.0, 0.95, 0.8)
    trace = DiagnosticTrace("training", "trace-a", (40.0, 42.0), (1.0, 1.0), (0.0, 0.0), 1.0)
    profile = FittedProfile("1", 7_000.0, 0.8, 120.0)
    report = evaluate_diagnostic_policy(create_diagnostic_model(4), (trace,), {"1": profile}, prior, seed=4)
    assert 0.0 < report["mean_requested_deployment_fraction"] < 1.0
