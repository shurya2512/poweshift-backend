from poweshift_backend.contracts.representation import ComparisonPolicy, NumericalPolicy
from poweshift_backend.representation.inputs import UpdateUnit
from poweshift_backend.representation.evaluation import CandidateScore, EvaluationEntry, choose_candidate, evaluate_sequential
from poweshift_backend.representation.update import UpdateResult, UpdateState
import numpy as np


def test_final_evaluation_is_reported_but_cannot_select_a_candidate() -> None:
    policy = ComparisonPolicy(
        numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12),
        metric="speed_mae_ms",
        minimum_relative_improvement=0.05,
        evaluation_reuse="reused_evaluation",
        per_update_refit_budget=1,
    )
    scores = (
        CandidateScore("baseline", "selection", 2.0, {"1:braking": 2, "1:propulsion": 1}),
        CandidateScore("gru", "selection", 1.8, {"1:braking": 2, "1:propulsion": 1}),
        CandidateScore("gru", "final_evaluation", 0.1, {"1:braking": 2, "1:propulsion": 1}),
    )

    report = choose_candidate(policy, scores)

    assert report.selected_candidate == "gru"
    assert report.final_evaluation_reused is True


def test_selection_refuses_candidate_that_hides_an_eligible_regime() -> None:
    policy = ComparisonPolicy(
        numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12),
        metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=1,
    )

    try:
        choose_candidate(policy, (
            CandidateScore("baseline", "selection", 2.0, {"1:braking": 2, "1:propulsion": 1}),
            CandidateScore("gru", "selection", 1.0, {"1:braking": 2}),
        ))
    except ValueError as error:
        assert "coverage" in str(error)
    else:
        raise AssertionError("candidate with missing regime was considered")


def test_sequential_evaluation_scores_before_matched_updates() -> None:
    unit = UpdateUnit(
        entry="1", session_key="test", run_id="run", split="selection", completed_cutoff_s=1.0,
        features=np.array([[1.0]], dtype=np.float32), valid=np.array([[True]], dtype=np.bool_), padding=np.array([False], dtype=np.bool_),
    )
    policy = ComparisonPolicy(
        numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12),
        metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=1,
    )
    events = []

    entry = EvaluationEntry(unit, regime="braking", target=1.5, target_cutoff_s=2.0, chronology_index=0)
    report = evaluate_sequential(
        policy, (entry,),
        baseline_predict=lambda _: events.append("baseline_predict") or 2.0,
        candidate_predict=lambda _: events.append("candidate_predict") or 1.0,
        baseline_refit=lambda _: events.append("baseline_refit"),
        candidate_update=lambda _: events.append("candidate_update"),
    )

    assert report.accepted_units == 1
    assert events == ["baseline_predict", "candidate_predict", "baseline_refit", "candidate_update"]
    assert report.metrics["1:braking"].candidate_absolute_error == 0.5
    assert report.metrics["1:braking"].run_coverage == ("test:run",)


def test_predictions_receive_an_immutable_prefix_not_later_target_values() -> None:
    prefix = UpdateUnit(
        entry="1", session_key="a", run_id="run", split="selection", completed_cutoff_s=1.0,
        features=np.array([[1.0]], dtype=np.float32), valid=np.array([[True]], dtype=np.bool_), padding=np.array([False], dtype=np.bool_),
    )
    target = np.array([2.0], dtype=np.float32)
    entry = EvaluationEntry(prefix, regime="braking", target=float(target[0]), target_cutoff_s=2.0, chronology_index=0)
    policy = ComparisonPolicy(numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12), metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=0)
    seen = []

    first = evaluate_sequential(policy, (entry,), baseline_predict=lambda context: seen.append(context) or float(context.features[0, 0]), candidate_predict=lambda context: float(context.features[0, 0]), baseline_refit=lambda _: None, candidate_update=lambda _: None)
    target[0] = 999.0
    second = evaluate_sequential(policy, (entry,), baseline_predict=lambda context: float(context.features[0, 0]), candidate_predict=lambda context: float(context.features[0, 0]), baseline_refit=lambda _: None, candidate_update=lambda _: None)

    assert seen[0].features.flags.writeable is False
    assert first.predictions == second.predictions


def test_sequential_evaluation_uses_declared_cross_session_chronology_and_keeps_metrics() -> None:
    policy = ComparisonPolicy(numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12), metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=0)
    earlier = UpdateUnit("1", "z-session", "early", "selection", 3.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    later = UpdateUnit("1", "a-session", "later", "selection", 1.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    entries = (EvaluationEntry(earlier, "coast", 2.0, 4.0, 4), EvaluationEntry(later, "propulsion", 3.0, 2.0, 5))

    report = evaluate_sequential(policy, entries, baseline_predict=lambda _: 1.0, candidate_predict=lambda _: 2.0, baseline_refit=lambda _: None, candidate_update=lambda _: None)

    assert report.accepted_units == 2
    assert set(report.metrics) == {"1:coast", "1:propulsion"}
    assert report.metrics["1:coast"].baseline_absolute_error == 1.0


def test_refit_budget_and_frozen_candidate_weights_are_enforced() -> None:
    import pytest
    import torch

    unit = UpdateUnit("1", "session", "run", "selection", 1.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    entry = EvaluationEntry(unit, "braking", 1.0, 2.0, 0)
    policy = ComparisonPolicy(numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12), metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=1)
    model = torch.nn.Linear(1, 1)

    with pytest.raises(ValueError, match="weights"):
        evaluate_sequential(policy, (entry,), baseline_predict=lambda _: 1.0, candidate_predict=lambda _: 1.0, baseline_refit=lambda _: None, candidate_update=lambda _: model.weight.data.add_(1.0), candidate_model=model)


def test_sequential_report_retains_withheld_and_reset_update_evidence() -> None:
    unit = UpdateUnit("1", "session", "run", "selection", 1.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    entry = EvaluationEntry(unit, "braking", 1.0, 2.0, 0)
    policy = ComparisonPolicy(numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12), metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=1)
    state = UpdateState("model", "transform", np.zeros(1, dtype=np.float32))

    report = evaluate_sequential(policy, (entry,), baseline_predict=lambda _: 1.0, candidate_predict=lambda _: 1.0, baseline_refit=lambda _: 1, candidate_update=lambda _: UpdateResult(state, withheld_reason="low_quality", reset_reason=None))

    assert report.withheld_updates == ("session:run:low_quality",)


def test_nonfinite_score_is_retained_as_an_entry_regime_exclusion() -> None:
    unit = UpdateUnit("1", "session", "run", "selection", 1.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    entry = EvaluationEntry(unit, "braking", 1.0, 2.0, 0)
    policy = ComparisonPolicy(numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12), metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=0)

    report = evaluate_sequential(policy, (entry,), baseline_predict=lambda _: float("nan"), candidate_predict=lambda _: 1.0, baseline_refit=lambda _: None, candidate_update=lambda _: None)

    assert report.metrics["1:braking"].count == 0
    assert report.metrics["1:braking"].exclusions == ("session:run:nonfinite_score",)


def test_evaluation_rejects_predictor_weight_mutation_without_an_update() -> None:
    import pytest
    import torch

    unit = UpdateUnit("1", "session", "run", "selection", 1.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    entry = EvaluationEntry(unit, "braking", 1.0, 2.0, 0)
    policy = ComparisonPolicy(numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12), metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=0)
    model = torch.nn.Linear(1, 1)

    with pytest.raises(ValueError, match="weights"):
        evaluate_sequential(policy, (entry,), baseline_predict=lambda _: 1.0, candidate_predict=lambda _: model.weight.data.add_(1.0) or 1.0, baseline_refit=lambda _: None, candidate_update=lambda _: None, candidate_model=model)


def test_update_quality_withholds_the_same_prefix_from_both_matched_updates() -> None:
    from poweshift_backend.representation.update import UpdateQuality

    unit = UpdateUnit("1", "session", "run", "selection", 1.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    entry = EvaluationEntry(unit, "braking", 1.0, 2.0, 0)
    policy = ComparisonPolicy(numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12), metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=1)
    calls = []

    report = evaluate_sequential(policy, (entry,), baseline_predict=lambda _: 1.0, candidate_predict=lambda _: 1.0, baseline_refit=lambda _: calls.append("baseline") or 1, candidate_update=lambda _: calls.append("candidate"), update_quality=lambda _: UpdateQuality("low", 0.2))

    assert calls == []
    assert report.withheld_updates == ("session:run:low_quality",)


def test_same_completed_prefix_is_updated_once_even_with_multiple_scores() -> None:
    unit = UpdateUnit("1", "session", "run", "selection", 1.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    entries = (EvaluationEntry(unit, "braking", 1.0, 2.0, 0), EvaluationEntry(unit, "coast", 1.0, 2.0, 1))
    policy = ComparisonPolicy(numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12), metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=1)
    calls = []

    report = evaluate_sequential(policy, entries, baseline_predict=lambda _: 1.0, candidate_predict=lambda _: 1.0, baseline_refit=lambda _: calls.append("baseline") or 1, candidate_update=lambda _: calls.append("candidate"))

    assert report.accepted_units == 2
    assert report.baseline_refits == 1
    assert calls == ["baseline", "candidate"]


def test_updates_receive_only_the_completed_target_unit_after_scoring() -> None:
    prefix = UpdateUnit("1", "session", "prior", "selection", 1.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    completed = UpdateUnit("1", "session", "target", "selection", 2.0, np.full((1, 1), 2.0, dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    entry = EvaluationEntry(prefix, "braking", 1.0, 3.0, 0, completed)
    policy = ComparisonPolicy(numerical=NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12), metric="speed_mae_ms", minimum_relative_improvement=0.05, evaluation_reuse="reused_evaluation", per_update_refit_budget=1)
    calls = []

    evaluate_sequential(policy, (entry,), baseline_predict=lambda context: calls.append(("predict", context.run_id)) or 1.0, candidate_predict=lambda context: calls.append(("candidate", context.run_id)) or 1.0, baseline_refit=lambda context: calls.append(("refit", context.run_id)) or 1, candidate_update=lambda context: calls.append(("update", context.run_id)))

    assert calls == [("predict", "prior"), ("candidate", "prior"), ("refit", "target"), ("update", "target")]


def test_update_unit_must_match_the_entry_and_stay_before_the_next_prefix() -> None:
    import pytest

    prefix = UpdateUnit("1", "2026-01-01", "prior", "selection", 1.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))
    wrong_entry = UpdateUnit("2", "2026-01-02", "target", "selection", 2.0, np.ones((1, 1), dtype=np.float32), np.ones((1, 1), dtype=np.bool_), np.zeros(1, dtype=np.bool_))

    with pytest.raises(ValueError, match="entry"):
        EvaluationEntry(prefix, "braking", 1.0, 2.0, 0, wrong_entry)
