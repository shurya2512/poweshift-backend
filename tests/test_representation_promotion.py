import pytest

from poweshift_backend.contracts.representation import ComparisonPolicy, ModelRecord, NumericalPolicy
from poweshift_backend.representation.promotion import ProfileVersion, PromotionDecision, promote_profile, retain_baseline
from poweshift_backend.representation.training import policy_identifier
from poweshift_backend.representation.evaluation import CandidateScore, choose_candidate


def _decision(**overrides) -> PromotionDecision:
    policy = ComparisonPolicy(
        numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12),
        metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=1,
    )
    fields = {
        "entry": "1",
        "candidate": "gru",
        "policy": policy,
        "policy_id": policy_identifier(policy),
        "model": ModelRecord(
            candidate="gru", feature_names=("speed_ms",), transform_id="transform-a", policy_id=policy_identifier(policy),
            training_input_sha256="a" * 64, teacher_fit_sha256="b" * 64,
            profile_component_names=("propulsion", "resistance", "braking", "grip"), profile_upper_bounds=(1.0, 1.0, 1.0, 1.0),
            latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16,
            variance_floor=1e-4, objective="gaussian_nll_full",
        ),
        "numerical_ready": True,
        "admission_id": "admission-a",
        "admitted_entries": ("1",),
        "selection_report": choose_candidate(policy, (
            CandidateScore("baseline", "selection", 2.0, {"1:braking": 2, "1:coast": 1, "1:propulsion": 1}),
            CandidateScore("gru", "selection", 1.8, {"1:braking": 2, "1:coast": 1, "1:propulsion": 1}),
        )),
        "baseline_metric": 2.0,
        "candidate_metric": 1.8,
        "baseline_coverage": {"1:braking": 2, "1:coast": 1, "1:propulsion": 1},
        "candidate_coverage": {"1:braking": 2, "1:coast": 1, "1:propulsion": 1},
        "physical_values": (1.0, 1.0, 1.0, 1.0),
    }
    fields.update(overrides)
    return PromotionDecision(**fields)


def test_promotion_archives_prior_profile_and_keeps_one_active_version() -> None:
    prior = ProfileVersion("1", "baseline", 1, True, policy_identifier(_decision().policy), physical_values=(1.0,))

    versions = promote_profile((prior,), _decision())

    assert [version.active for version in versions] == [False, True]
    assert versions[-1].candidate == "gru"
    assert versions[-1].physical_values == (1.0, 1.0, 1.0, 1.0)


def test_promotion_refuses_unsupported_entry() -> None:
    with pytest.raises(ValueError, match="readiness"):
        promote_profile((), _decision(numerical_ready=False))


def test_promotion_refuses_mismatched_or_insufficient_evidence() -> None:
    with pytest.raises(ValueError, match="coverage"):
        promote_profile((), _decision(candidate_coverage={"1:braking": 2}))
    with pytest.raises(ValueError, match="selection"):
        promote_profile((), _decision(candidate_metric=1.95))
    with pytest.raises(ValueError, match="policy"):
        promote_profile((), _decision(policy_id="other"))


def test_promotion_refuses_an_unbound_policy_or_nonpositive_candidate_gain() -> None:
    with pytest.raises(ValueError, match="policy"):
        promote_profile((), _decision(policy_id="not-the-policy"))
    with pytest.raises(ValueError, match="selection"):
        promote_profile((), _decision(candidate_metric=2.0))


def test_promotion_refuses_entry_coverage_owned_by_another_entry() -> None:
    with pytest.raises(ValueError, match="entry"):
        promote_profile((), _decision(baseline_coverage={"2:braking": 2}, candidate_coverage={"2:braking": 2}))


def test_promotion_refuses_physical_values_outside_the_recorded_bounds() -> None:
    with pytest.raises(ValueError, match="bounded"):
        promote_profile((), _decision(physical_values=(2.0, 1.0, 1.0, 1.0)))


def test_promotion_refuses_a_selection_without_all_required_regimes() -> None:
    with pytest.raises(ValueError, match="required regime"):
        promote_profile((), _decision(baseline_coverage={"1:braking": 2, "1:propulsion": 1}, candidate_coverage={"1:braking": 2, "1:propulsion": 1}))


def test_baseline_retention_does_not_create_another_profile_version() -> None:
    decision = _decision()
    current = ProfileVersion("1", "baseline", 1, True, decision.policy_id)
    report = choose_candidate(decision.policy, (CandidateScore("baseline", "selection", 2.0, {"1:braking": 2}),))

    retained = retain_baseline((current,), decision.policy, report)

    assert retained == (current,)


def test_promotion_binds_metrics_to_the_selected_report_and_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="selection"):
        promote_profile((), _decision(candidate_metric=1.7))
    with pytest.raises(ValueError, match="finite"):
        promote_profile((), _decision(candidate_metric=-0.1))
