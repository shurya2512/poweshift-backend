"""Frozen sequential comparison with explicit information and budget boundaries."""

from dataclasses import dataclass
from datetime import date
from math import isfinite
from types import MappingProxyType
from collections.abc import Callable, Mapping

import numpy as np

from poweshift_backend.contracts.representation import ComparisonPolicy
from poweshift_backend.representation.inputs import UpdateUnit
from poweshift_backend.representation.training import policy_identifier
from poweshift_backend.representation.update import UpdateQuality


@dataclass(frozen=True)
class CandidateScore:
    """One declared score under a shared evidence and update budget."""

    candidate: str
    split: str
    metric_value: float
    coverage: Mapping[str, int]
    evaluation_mode: str = "sequential"
    exclusions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComparisonReport:
    """Selection evidence that keeps frozen and final reporting separate."""

    selected_candidate: str
    selection_baseline_metric: float
    final_evaluation_reused: bool
    policy_id: str
    selected_candidate_metric: float
    frozen_secondary: tuple[CandidateScore, ...] = ()


@dataclass(frozen=True)
class PrefixContext:
    """Immutable observed context available to a prediction or update callback."""

    entry: str
    session_key: str
    run_id: str
    split: str
    completed_cutoff_s: float
    features: np.ndarray
    valid: np.ndarray
    padding: np.ndarray

    @classmethod
    def from_unit(cls, unit: UpdateUnit) -> "PrefixContext":
        """Copy one permitted prefix so later source changes cannot leak in."""
        fields = tuple(np.array(value, copy=True) for value in (unit.features, unit.valid, unit.padding))
        for value in fields:
            value.setflags(write=False)
        return cls(unit.entry, unit.session_key, unit.run_id, unit.split, unit.completed_cutoff_s, *fields)


@dataclass(frozen=True)
class EvaluationEntry:
    """One scored future observation and the prefix allowed to predict it."""

    prefix: UpdateUnit
    regime: str
    target: float
    target_cutoff_s: float
    chronology_index: int
    update_unit: UpdateUnit | None = None

    def __post_init__(self) -> None:
        if not self.regime or not isfinite(self.target) or self.target_cutoff_s < self.prefix.completed_cutoff_s:
            raise ValueError("evaluation entry needs a finite later target and named regime")
        if self.chronology_index < 0:
            raise ValueError("evaluation chronology index cannot be negative")
        if self.update_unit and self.update_unit.completed_cutoff_s <= self.prefix.completed_cutoff_s:
            raise ValueError("update unit must close after its prediction prefix")
        if self.update_unit and self.update_unit.entry != self.prefix.entry:
            raise ValueError("update unit must belong to the prediction entry")
        if self.update_unit and self.update_unit.split != self.prefix.split:
            raise ValueError("update unit must use the prediction split")


@dataclass(frozen=True)
class RegimeMetrics:
    """Absolute errors and retained run coverage for one entry and regime."""

    count: int
    baseline_absolute_error: float
    candidate_absolute_error: float
    run_coverage: tuple[str, ...]
    exclusions: tuple[str, ...]


@dataclass(frozen=True)
class Prediction:
    """One retained score produced before any update action."""

    entry: str
    session_key: str
    run_id: str
    regime: str
    target: float
    baseline: float
    candidate: float


@dataclass(frozen=True)
class SequentialReport:
    """Auditable sequential scores, support and bounded update evidence."""

    accepted_units: int
    exclusions: tuple[str, ...]
    metrics: Mapping[str, RegimeMetrics]
    predictions: tuple[Prediction, ...]
    baseline_refits: int
    candidate_updates: int
    telemetry_only_ablation: Mapping[str, float]
    withheld_updates: tuple[str, ...]
    reset_evidence: tuple[str, ...]


def choose_candidate(policy: ComparisonPolicy, scores: tuple[CandidateScore, ...]) -> ComparisonReport:
    """Choose only the sequential selection score with matching support."""
    selection = [score for score in scores if score.split == "selection" and score.evaluation_mode == "sequential"]
    baseline = next((score for score in selection if score.candidate == "baseline"), None)
    if baseline is None or not baseline.coverage or any(count < 1 for count in baseline.coverage.values()):
        raise ValueError("selection needs a supported baseline score")
    if not isfinite(baseline.metric_value) or baseline.metric_value <= 0.0:
        raise ValueError("selection baseline metric must be finite and positive")
    selected = "baseline"
    selected_metric = baseline.metric_value
    threshold = baseline.metric_value * (1.0 - policy.minimum_relative_improvement)
    for score in selection:
        if score.candidate == "baseline":
            continue
        if dict(score.coverage) != dict(baseline.coverage) or score.exclusions != baseline.exclusions:
            raise ValueError("candidate and baseline coverage and exclusions must match")
        if not isfinite(score.metric_value) or score.metric_value < 0.0:
            raise ValueError("candidate selection metric must be finite")
        if score.metric_value <= threshold and (selected == "baseline" or score.metric_value < threshold):
            selected = score.candidate
            threshold = score.metric_value
            selected_metric = score.metric_value
    frozen = tuple(score for score in scores if score.split == "selection" and score.evaluation_mode == "frozen")
    for score in frozen:
        if dict(score.coverage) != dict(baseline.coverage):
            raise ValueError("frozen secondary coverage must match the sequential baseline")
    return ComparisonReport(
        selected, baseline.metric_value, policy.evaluation_reuse == "reused_evaluation",
        policy_identifier(policy), selected_metric, frozen,
    )


def evaluate_sequential(
    policy: ComparisonPolicy,
    entries: tuple[EvaluationEntry, ...],
    *,
    baseline_predict: Callable[[PrefixContext], float],
    candidate_predict: Callable[[PrefixContext], float],
    baseline_refit: Callable[[PrefixContext], int | None],
    candidate_update: Callable[[PrefixContext], object],
    candidate_model: object | None = None,
    telemetry_only_predict: Callable[[PrefixContext], float] | None = None,
    update_quality: Callable[[PrefixContext], UpdateQuality] | None = None,
) -> SequentialReport:
    """Predict, score and then adapt with the same immutable accepted prefix."""
    accepted = 0
    baseline_refits = 0
    candidate_updates = 0
    exclusions: list[str] = []
    withheld_updates: list[str] = []
    reset_evidence: list[str] = []
    predictions: list[Prediction] = []
    metric_rows: dict[str, list[tuple[float, float, str]]] = {}
    regime_exclusions: dict[str, list[str]] = {}
    ablation_rows: dict[str, list[float]] = {}
    previous_index = -1
    previous_session_key = ""
    previous_cutoff = float("-inf")
    updated_units: set[tuple[str, str, str, float]] = set()
    frozen_weights = _weight_snapshot(candidate_model)
    for index, entry in enumerate(entries):
        if entry.chronology_index <= previous_index:
            raise ValueError("sequential entries must have strictly increasing declared chronology")
        if entry.prefix.session_key == previous_session_key and entry.prefix.completed_cutoff_s < previous_cutoff:
            raise ValueError("one session cannot move backward across sequential prefixes")
        if _source_date(entry.prefix.session_key) and _source_date(previous_session_key):
            if _source_date(entry.prefix.session_key) < _source_date(previous_session_key):
                raise ValueError("ISO source sessions cannot move backward across sequential prefixes")
        previous_index = entry.chronology_index
        previous_session_key = entry.prefix.session_key
        previous_cutoff = entry.prefix.completed_cutoff_s
        prefix = PrefixContext.from_unit(entry.prefix)
        baseline_value = baseline_predict(prefix)
        candidate_value = candidate_predict(prefix)
        _assert_weights_unchanged(candidate_model, frozen_weights)
        key = f"{prefix.entry}:{entry.regime}"
        if not all(isfinite(value) for value in (baseline_value, candidate_value, entry.target)):
            exclusion = f"{prefix.session_key}:{prefix.run_id}:nonfinite_score"
            exclusions.append(exclusion)
            regime_exclusions.setdefault(key, []).append(exclusion)
            continue
        baseline_error = abs(baseline_value - entry.target)
        candidate_error = abs(candidate_value - entry.target)
        run = f"{prefix.session_key}:{prefix.run_id}"
        metric_rows.setdefault(key, []).append((baseline_error, candidate_error, run))
        predictions.append(Prediction(prefix.entry, prefix.session_key, prefix.run_id, entry.regime, entry.target, baseline_value, candidate_value))
        accepted += 1
        if telemetry_only_predict is not None:
            ablated = telemetry_only_predict(prefix)
            if isfinite(ablated):
                ablation_rows.setdefault(key, []).append(abs(ablated - entry.target))
            else:
                exclusions.append(f"{run}:telemetry_only_nonfinite")
        update_unit = entry.update_unit or entry.prefix
        if index + 1 < len(entries):
            _check_update_before_next_prefix(update_unit, entries[index + 1].prefix)
        update_key = (update_unit.entry, update_unit.session_key, update_unit.run_id, update_unit.completed_cutoff_s)
        if policy.per_update_refit_budget and update_key not in updated_units:
            update_prefix = PrefixContext.from_unit(update_unit)
            quality = update_quality(update_prefix) if update_quality else UpdateQuality("accepted", 1.0)
            updated_units.add(update_key)
            if quality.status != "accepted":
                withheld_updates.append(f"{run}:{'missing' if quality.status == 'missing' else 'low_quality'}")
                continue
            used = baseline_refit(update_prefix)
            used = 1 if used is None else used
            if not isinstance(used, int) or used < 0 or used > policy.per_update_refit_budget:
                raise ValueError("baseline refit exceeded the fixed per-prefix budget")
            baseline_refits += used
            update_result = candidate_update(update_prefix)
            candidate_updates += 1
            withheld = getattr(update_result, "withheld_reason", None)
            reset = getattr(update_result, "reset_reason", None)
            if withheld:
                withheld_updates.append(f"{run}:{withheld}")
            if reset:
                reset_evidence.append(f"{run}:{reset}")
            _assert_weights_unchanged(candidate_model, frozen_weights)
    metric_keys = metric_rows.keys() | regime_exclusions.keys()
    metrics = {
        key: RegimeMetrics(
            len(metric_rows.get(key, [])),
            sum(row[0] for row in metric_rows.get(key, [])),
            sum(row[1] for row in metric_rows.get(key, [])),
            tuple(row[2] for row in metric_rows.get(key, [])),
            tuple(regime_exclusions.get(key, [])),
        )
        for key in metric_keys
    }
    ablation = {key: sum(values) / len(values) for key, values in ablation_rows.items()}
    _assert_weights_unchanged(candidate_model, frozen_weights)
    return SequentialReport(
        accepted, tuple(exclusions), MappingProxyType(metrics), tuple(predictions), baseline_refits,
        candidate_updates, MappingProxyType(ablation), tuple(withheld_updates), tuple(reset_evidence),
    )


def _weight_snapshot(model: object | None) -> tuple[tuple[str, object], ...]:
    if model is None:
        return ()
    state = getattr(model, "state_dict", None)
    if state is None:
        raise ValueError("candidate model must expose state_dict")
    return tuple((name, value.detach().clone()) for name, value in state().items())


def _assert_weights_unchanged(model: object | None, snapshot: tuple[tuple[str, object], ...]) -> None:
    if model is None:
        return
    current = model.state_dict()
    changed = tuple(current) != tuple(name for name, _ in snapshot)
    changed = changed or any(not np.array_equal(current[name].detach().cpu().numpy(), value.detach().cpu().numpy()) for name, value in snapshot)
    if changed:
        raise ValueError("candidate weights changed during sequential adaptation")


def _source_date(session_key: str) -> date | None:
    try:
        return date.fromisoformat(session_key[:10])
    except ValueError:
        return None


def _check_update_before_next_prefix(update_unit: UpdateUnit, next_prefix: UpdateUnit) -> None:
    if update_unit.entry != next_prefix.entry:
        return
    if update_unit.session_key == next_prefix.session_key and update_unit.completed_cutoff_s > next_prefix.completed_cutoff_s:
        raise ValueError("update unit extends beyond the next prediction prefix")
    if _source_date(update_unit.session_key) and _source_date(next_prefix.session_key):
        if _source_date(update_unit.session_key) > _source_date(next_prefix.session_key):
            raise ValueError("update unit extends beyond the next prediction session")
