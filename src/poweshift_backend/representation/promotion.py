"""One-active-version promotion with retained physical profile provenance."""

from dataclasses import dataclass
from math import isclose, isfinite

from poweshift_backend.contracts.representation import ComparisonPolicy, ModelRecord
from poweshift_backend.representation.evaluation import ComparisonReport
from poweshift_backend.representation.training import policy_identifier


@dataclass(frozen=True)
class ProfileVersion:
    """One archived or active physical profile and its source identities."""

    entry: str
    candidate: str
    version: int
    active: bool
    policy_id: str
    physical_values: tuple[float, ...] = ()
    profile_component_names: tuple[str, ...] = ()
    transform_id: str = ""
    training_input_sha256: str = ""
    teacher_fit_sha256: str = ""
    admission_id: str = ""


@dataclass(frozen=True)
class PromotionDecision:
    """Bound admission, policy and selection evidence for one activation."""

    entry: str
    candidate: str
    policy: ComparisonPolicy
    policy_id: str
    model: ModelRecord
    numerical_ready: bool
    admission_id: str
    admitted_entries: tuple[str, ...]
    selection_report: ComparisonReport
    baseline_metric: float
    candidate_metric: float
    baseline_coverage: dict[str, int]
    candidate_coverage: dict[str, int]
    physical_values: tuple[float, ...]


def promote_profile(versions: tuple[ProfileVersion, ...], decision: PromotionDecision) -> tuple[ProfileVersion, ...]:
    """Archive an entry's active profile before activating bound evidence."""
    if not decision.numerical_ready:
        raise ValueError("numerical readiness has not passed")
    expected_policy_id = policy_identifier(decision.policy)
    if decision.policy_id != expected_policy_id or decision.selection_report.policy_id != expected_policy_id:
        raise ValueError("promotion policy does not match its actual policy hash")
    if not decision.admission_id or decision.entry not in decision.admitted_entries:
        raise ValueError("promotion entry is not admitted by the bound admission record")
    if decision.selection_report.selected_candidate != decision.candidate:
        raise ValueError("selection report did not select the promotion candidate")
    if decision.model.candidate != decision.candidate or decision.model.policy_id != decision.policy_id:
        raise ValueError("model provenance does not match the promotion decision")
    _check_coverage(decision)
    _check_metrics(decision)
    _check_physical_values(decision)
    entry_versions = [version for version in versions if version.entry == decision.entry]
    others = [version for version in versions if version.entry != decision.entry]
    if any(version.policy_id != decision.policy_id for version in entry_versions):
        raise ValueError("existing entry profile has incompatible policy provenance")
    archived = [
        ProfileVersion(
            version.entry, version.candidate, version.version, False, version.policy_id,
            version.physical_values, version.profile_component_names, version.transform_id,
            version.training_input_sha256, version.teacher_fit_sha256, version.admission_id,
        )
        for version in entry_versions
    ]
    next_version = max((version.version for version in entry_versions), default=0) + 1
    active = ProfileVersion(
        decision.entry, decision.candidate, next_version, True, decision.policy_id,
        decision.physical_values, decision.model.profile_component_names, decision.model.transform_id,
        decision.model.training_input_sha256, decision.model.teacher_fit_sha256, decision.admission_id,
    )
    return tuple(others + archived + [active])


def retain_baseline(
    versions: tuple[ProfileVersion, ...], policy: ComparisonPolicy, selection_report: ComparisonReport
) -> tuple[ProfileVersion, ...]:
    """Keep the current registry unchanged when sequential selection retains baseline."""
    if selection_report.selected_candidate != "baseline":
        raise ValueError("baseline retention requires a baseline selection report")
    if selection_report.policy_id != policy_identifier(policy):
        raise ValueError("baseline retention report does not match its actual policy hash")
    if any(sum(version.active for version in versions if version.entry == entry) > 1 for entry in {item.entry for item in versions}):
        raise ValueError("profile registry has more than one active version for an entry")
    return versions


def _check_coverage(decision: PromotionDecision) -> None:
    if decision.baseline_coverage != decision.candidate_coverage or not decision.baseline_coverage:
        raise ValueError("candidate and baseline coverage must match")
    if any(count < 1 for count in decision.baseline_coverage.values()):
        raise ValueError("promotion coverage has unsupported regimes")
    if any(not key.startswith(f"{decision.entry}:") for key in decision.baseline_coverage):
        raise ValueError("promotion coverage names an unauthorized entry")
    required = {f"{decision.entry}:{regime}" for regime in ("braking", "coast", "propulsion")}
    if not required.issubset(decision.baseline_coverage):
        raise ValueError("promotion coverage lacks a required regime")


def _check_metrics(decision: PromotionDecision) -> None:
    if not isfinite(decision.baseline_metric) or not isfinite(decision.candidate_metric):
        raise ValueError("promotion metrics must be finite positive values")
    if decision.baseline_metric <= 0.0 or decision.candidate_metric < 0.0:
        raise ValueError("promotion metrics must be finite positive values")
    if not isclose(decision.baseline_metric, decision.selection_report.selection_baseline_metric):
        raise ValueError("promotion baseline metric does not match its selection report")
    if not isclose(decision.candidate_metric, decision.selection_report.selected_candidate_metric):
        raise ValueError("promotion candidate metric does not match its selection report")
    required = decision.baseline_metric * (1.0 - decision.policy.minimum_relative_improvement)
    if decision.candidate_metric > required:
        raise ValueError("candidate does not meet the frozen improvement rule")
    if decision.candidate_metric >= decision.baseline_metric:
        raise ValueError("candidate must have nonnegative improvement over baseline")


def _check_physical_values(decision: PromotionDecision) -> None:
    if len(decision.physical_values) != len(decision.model.profile_component_names):
        raise ValueError("physical profile values do not match component provenance")
    if not all(isfinite(value) and value >= 0.0 for value in decision.physical_values):
        raise ValueError("physical profile values must be finite and nonnegative")
    if any(value > bound for value, bound in zip(decision.physical_values, decision.model.profile_upper_bounds)):
        raise ValueError("physical profile values exceed the model's bounded decoder")
