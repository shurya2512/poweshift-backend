"""Matched offline response comparison with fail-closed retention."""

from dataclasses import dataclass
from math import isfinite

import numpy as np


@dataclass(frozen=True)
class FrozenResponseEvidence:
    """Evidence identity and shared comparison boundaries."""

    evidence_id: str
    residual_mechanism: str
    source_id: str
    power_boundary: str
    integrator_id: str

    def __post_init__(self) -> None:
        if not all((self.evidence_id, self.residual_mechanism, self.source_id, self.power_boundary, self.integrator_id)):
            raise ValueError("response evidence must be frozen before comparison")


@dataclass(frozen=True)
class ResponseComparison:
    """Measured errors and the retained supported candidate."""

    evidence_id: str
    errors: tuple[tuple[str, float], ...]
    retained_candidate: str | None
    neural_accepted: bool


def compare_response_candidates(
    evidence: FrozenResponseEvidence,
    observed: np.ndarray,
    candidates: dict[str, np.ndarray],
    *,
    maximum_mae: float,
) -> ResponseComparison:
    """Compare candidates on matched rows without promoting worse output."""
    required = {"numerical", "algebraic", "finite", "neural_residual"}
    observed = np.asarray(observed, dtype=np.float64)
    if set(candidates) != required or observed.ndim != 1 or len(observed) == 0:
        raise ValueError("matched comparison needs every declared candidate")
    if not isfinite(maximum_mae) or maximum_mae < 0.0:
        raise ValueError("comparison acceptance must be frozen")
    errors = {}
    for name, predicted in candidates.items():
        predicted = np.asarray(predicted, dtype=np.float64)
        if predicted.shape != observed.shape or not np.isfinite(predicted).all():
            raise ValueError("candidate outputs must match finite observed rows")
        errors[name] = float(np.mean(np.abs(predicted - observed)))
    supported = {name: error for name, error in errors.items() if error <= maximum_mae}
    priority = {"numerical": 0, "algebraic": 1, "finite": 2, "neural_residual": 3}
    retained = min(supported, key=lambda name: (supported[name], priority[name])) if supported else None
    non_neural_best = min(errors[name] for name in required - {"neural_residual"})
    neural_accepted = errors["neural_residual"] <= maximum_mae and errors["neural_residual"] < non_neural_best
    if retained == "neural_residual" and not neural_accepted:
        retained = min(required - {"neural_residual"}, key=lambda name: (errors[name], priority[name]))
        if errors[retained] > maximum_mae:
            retained = None
    return ResponseComparison(evidence.evidence_id, tuple(sorted(errors.items())), retained, neural_accepted)
