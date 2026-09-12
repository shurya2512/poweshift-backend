"""Masked motion residuals used by the effective baseline."""

import numpy as np


def masked_residuals(predicted: np.ndarray, observed: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return prediction errors only where both values are admitted."""
    predicted = np.asarray(predicted, dtype=np.float64)
    observed = np.asarray(observed, dtype=np.float64)
    mask = np.asarray(mask, dtype=np.bool_)
    if predicted.shape != observed.shape or predicted.shape != mask.shape:
        raise ValueError("residual inputs must share one shape")
    keep = mask & np.isfinite(predicted) & np.isfinite(observed)
    return predicted[keep] - observed[keep]


def mean_absolute_error(predicted: np.ndarray, observed: np.ndarray, mask: np.ndarray) -> float:
    """Calculate the finite masked absolute residual mean."""
    residuals = masked_residuals(predicted, observed, mask)
    return float(np.mean(np.abs(residuals))) if len(residuals) else float("nan")
