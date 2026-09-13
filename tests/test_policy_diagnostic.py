import pytest
import torch

from poweshift_backend.contracts.action import Manoeuvre
from poweshift_backend.energy.allocator import DeploymentPrior
from poweshift_backend.policy.diagnostic import (
    DiagnosticTrace,
    FittedProfile,
    RaceInteractionPrior,
    classify_race_interaction,
    create_diagnostic_model,
    evaluate_diagnostic_policy,
    evaluate_diagnostic_trace,
    race_reserve_penalty,
    race_step_reward,
    run_diagnostic_updates,
)


def test_diagnostic_updates_preserve_additive_energy_ledgers() -> None:
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    trace = DiagnosticTrace("training", "trace-a", (40.0, 42.0, 38.0, 35.0), (1.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 1.0), 1.0)
    profile = FittedProfile("1", 7_000.0, 0.8, 120.0, 16_000.0)
    report = run_diagnostic_updates((trace,), {"1": profile}, prior, updates=2, seed=3)
    assert report["updates"] == 2
    assert report["gross_deployment_j"] >= 0.0
    assert report["gross_harvest_j"] > 0.0
    assert report["maximum_electric_power_w"] == 350_000.0
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
    free_air = race_step_reward(prior, 0.5, 100_000.0, 1.0, 1.0, False, False, Manoeuvre.HOLD)
    attack = race_step_reward(prior, 0.5, 100_000.0, 1.0, 1.0, True, False, Manoeuvre.ATTACK)
    late_attack = race_step_reward(prior, 0.5, 100_000.0, 0.0, 1.0, True, False, Manoeuvre.ATTACK)
    assert attack > free_air
    assert late_attack > attack


def test_race_reward_penalises_a_tactical_path_without_its_condition() -> None:
    prior = RaceInteractionPrior()
    aligned = race_step_reward(prior, 0.5, 0.0, 0.5, 1.0, True, False, Manoeuvre.ATTACK)
    missed = race_step_reward(prior, 0.5, 0.0, 0.5, 1.0, True, False, Manoeuvre.HOLD)
    unsupported = race_step_reward(prior, 0.5, 0.0, 0.5, 1.0, False, False, Manoeuvre.ATTACK)
    assert aligned > missed
    assert missed > unsupported


def test_race_reward_is_invariant_to_trace_resolution() -> None:
    prior = RaceInteractionPrior()
    one_step = race_step_reward(prior, 0.5, 100_000.0, 0.5, 1.0, True, False, Manoeuvre.ATTACK)
    two_half_steps = 2.0 * race_step_reward(
        prior, 0.5, 50_000.0, 0.5, 0.5, True, False, Manoeuvre.ATTACK,
    )
    assert two_half_steps == pytest.approx(one_step)


def test_race_reserve_penalty_releases_the_store_on_the_final_lap() -> None:
    prior = RaceInteractionPrior()
    assert race_reserve_penalty(prior, state_of_charge=0.2, target_fraction=0.8) < 0.0
    assert race_reserve_penalty(prior, state_of_charge=0.0, target_fraction=0.0) == 0.0


def test_policy_evaluation_reports_requested_deployment() -> None:
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    trace = DiagnosticTrace("training", "trace-a", (40.0, 42.0), (1.0, 1.0), (0.0, 0.0), 1.0)
    profile = FittedProfile("1", 7_000.0, 0.8, 120.0, 16_000.0)
    report = evaluate_diagnostic_policy(create_diagnostic_model(4), (trace,), {"1": profile}, prior, seed=4)
    assert 0.0 < report["mean_requested_deployment_fraction"] < 1.0


def test_practice_can_deploy_energy_but_only_selects_hold() -> None:
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    trace = DiagnosticTrace(
        "training", "practice-a", (40.0, 41.0), (1.0, 0.0), (0.0, 1.0), 0.25,
    )
    profile = FittedProfile("1", 7_000.0, 0.8, 120.0, 16_000.0)
    model = create_diagnostic_model(8)
    with torch.no_grad():
        model.manoeuvre_head.weight.zero_()
        model.manoeuvre_head.bias[:] = torch.tensor((0.0, 100.0, 0.0))

    report = evaluate_diagnostic_trace(model, trace, profile, prior)

    assert {decision.manoeuvre for decision in report.decisions} == {Manoeuvre.HOLD}
    assert report.decisions[0].deployment_j > 0.0
    assert report.decisions[1].harvest_j > 0.0


def test_protected_trace_can_be_evaluated_but_not_optimized() -> None:
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    trace = DiagnosticTrace(
        "final_evaluation", "madrid-qualifying", (40.0, 41.0), (1.0, 1.0), (0.0, 0.0), 0.25,
    )
    profile = FittedProfile("1", 7_000.0, 0.8, 120.0, 16_000.0)

    assert evaluate_diagnostic_trace(create_diagnostic_model(8), trace, profile, prior).decisions
    with pytest.raises(ValueError, match="training partition"):
        run_diagnostic_updates((trace,), {"1": profile}, prior, updates=1, seed=8)


def test_race_exhaustion_finding_reports_actual_update_count() -> None:
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    trace = DiagnosticTrace(
        "training", "race-a", (40.0, 40.0), (1.0, 1.0), (0.0, 0.0), 100.0,
        "1", True, (2.0, 2.0), (0.0, 0.0), (2.0, 2.0), (0.0, 0.0), 1, 2,
    )
    profile = FittedProfile("1", 7_000.0, 0.8, 120.0, 16_000.0)

    report = run_diagnostic_updates(
        (trace,), {"1": profile}, prior, updates=2, seed=3,
        carry_energy_across_updates=True,
    )

    assert "store was exhausted; 2 race updates did not yet adapt deployment to the shaped objective" in report["reward_findings"]


def test_race_training_carries_hidden_state_between_laps() -> None:
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    trace = DiagnosticTrace(
        "training", "race-a", (40.0, 41.0), (1.0, 1.0), (0.0, 0.0), 0.25,
        "1", True, (0.8, 0.7), (0.6, 0.7), (2.0, 2.0), (0.0, 0.0), 1, 2,
    )
    profile = FittedProfile("1", 7_000.0, 0.8, 120.0, 16_000.0)

    report = run_diagnostic_updates(
        (trace,), {"1": profile}, prior, updates=2, seed=4,
        carry_energy_across_updates=True,
        carry_hidden_across_updates=True,
    )

    assert report["recurrent_state_carried"] is True


def test_deterministic_validation_records_probability_and_energy() -> None:
    prior = DeploymentPrior(5_000_000.0, 5_000_000.0, 0.95, 0.8, 350_000.0)
    trace = DiagnosticTrace(
        "training", "race-a", (40.0, 41.0), (1.0, 0.0), (0.0, 1.0), 0.25,
        "1", True, (0.8, 0.7), (0.6, 0.7), (2.0, 2.0), (0.0, 0.0), 1, 1,
        (10.0, 10.25), (100.0, 110.0), (3, 3),
    )
    profile = FittedProfile("1", 7_000.0, 0.8, 120.0, 16_000.0)
    model = create_diagnostic_model(9)

    first = evaluate_diagnostic_trace(model, trace, profile, prior)
    second = evaluate_diagnostic_trace(model, trace, profile, prior)

    assert first.decisions == second.decisions
    decision = first.decisions[0]
    assert decision.manoeuvre.value in {"hold", "attack", "defend"}
    assert 0.0 <= decision.action_probability <= 1.0
    assert decision.deployment_j >= 0.0
    assert first.decisions[1].harvest_j > 0.0
    assert decision.time_s == 10.0
    assert decision.observed_position == 3
