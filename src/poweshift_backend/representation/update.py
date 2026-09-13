"""Quality-gated latent adaptation for completed telemetry prefixes."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class UpdateQuality:
    """Recorded quality decision for one completed prefix."""

    status: str
    score: float
    reset_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"accepted", "missing", "low"}:
            raise ValueError("update quality must be accepted, missing or low")
        if not np.isfinite(self.score) or not 0.0 <= self.score <= 1.0:
            raise ValueError("update quality score must be within zero and one")
        if self.reset_reason and self.status != "accepted":
            raise ValueError("only accepted quality can reset state")


@dataclass(frozen=True)
class UpdateState:
    """Saved latent state bound to one model and input transform."""

    model_id: str
    transform_id: str
    latent: np.ndarray
    update_count: int = 0
    reset_count: int = 0

    def __post_init__(self) -> None:
        if not self.model_id or not self.transform_id:
            raise ValueError("update state needs model and transform identities")
        if self.latent.dtype != np.float32 or self.latent.ndim != 1 or not np.isfinite(self.latent).all():
            raise ValueError("update state needs a finite float32 latent vector")
        if self.update_count < 0 or self.reset_count < 0:
            raise ValueError("update counters cannot be negative")
        self.latent.setflags(write=False)


@dataclass(frozen=True)
class UpdateResult:
    """State transition and retained reason for a withheld update."""

    state: UpdateState
    withheld_reason: str | None = None
    reset_reason: str | None = None


def assess_update_quality(valid: np.ndarray, padding: np.ndarray, minimum_valid_fraction: float) -> UpdateQuality:
    """Measure whether a telemetry-only prefix can update saved state."""
    if valid.dtype != np.bool_ or valid.ndim != 2 or padding.dtype != np.bool_ or padding.shape != (valid.shape[0],):
        raise ValueError("quality assessment needs matching boolean telemetry masks")
    if not 0.0 < minimum_valid_fraction <= 1.0:
        raise ValueError("minimum valid fraction must be within zero and one")
    observed = ~padding[:, None]
    available = int(observed.sum() * valid.shape[1])
    if not available:
        return UpdateQuality("missing", 0.0)
    score = float((valid & observed).sum() / available)
    return UpdateQuality("accepted" if score >= minimum_valid_fraction else "low", score)


def session_reset_reason(previous_session_key: str, session_key: str) -> str | None:
    """Record a reset only when a completed run changes session."""
    return "session_change" if previous_session_key and previous_session_key != session_key else None


def apply_quality_aware_update(
    state: UpdateState,
    next_latent: np.ndarray,
    quality: UpdateQuality,
    model_id: str,
    transform_id: str,
) -> UpdateResult:
    """Keep only high-quality state updates from a compatible prefix."""
    if state.model_id != model_id or state.transform_id != transform_id:
        raise ValueError("incompatible model or transform cannot reset update state")
    if quality.status == "missing":
        return UpdateResult(state, withheld_reason="missing")
    if quality.status == "low":
        return UpdateResult(state, withheld_reason="low_quality")
    if next_latent.dtype != np.float32 or next_latent.shape != state.latent.shape or not np.isfinite(next_latent).all():
        raise ValueError("accepted update needs a finite latent matching saved state")
    latent = np.array(next_latent, copy=True)
    if quality.reset_reason:
        return UpdateResult(UpdateState(model_id, transform_id, latent, 1, state.reset_count + 1), reset_reason=quality.reset_reason)
    return UpdateResult(UpdateState(model_id, transform_id, latent, state.update_count + 1, state.reset_count))
