"""Build a supported TrackProfile from approved planar position coordinates."""

from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, model_validator

from poweshift_backend.contracts.acquisition import StrictModel
from poweshift_backend.contracts.preparation import ArtifactProvenance

# FastF1 position X/Y are recorded in 1/10 metre increments; this is the only conversion applied.
_NATIVE_TO_METRE = 0.1

# Fields the architecture names for TrackProfile that no approved source in this bundle supports.
UNSUPPORTED_GEOMETRY = frozenset(
    {"grade", "width", "corner_boundaries", "connected_routes", "pit_branch", "rule_line_mappings"}
)


class CoordinateTransform(StrictModel):
    """The recorded scale from native position units to metres."""

    kind: Literal["decimetre_to_metre_scale"] = "decimetre_to_metre_scale"
    source_unit: Literal["decimetre"] = "decimetre"
    target_unit: Literal["metre"] = "metre"
    scale: Literal[0.1] = 0.1
    origin_x_native: float
    origin_y_native: float


class TrackProfile(BaseModel):
    """Planar geometry supported by approved coordinates only; other fields stay masked."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, arbitrary_types_allowed=True)

    provenance: ArtifactProvenance
    coordinate_transform: CoordinateTransform
    reference_progress: np.ndarray
    actual_distance_m: np.ndarray
    curvature_m_inv: np.ndarray
    curvature_valid_mask: np.ndarray

    @model_validator(mode="after")
    def _arrays_are_aligned_finite_and_immutable(self) -> "TrackProfile":
        length = len(self.reference_progress)
        for array in (self.reference_progress, self.actual_distance_m, self.curvature_m_inv):
            if array.dtype != np.float64 or array.ndim != 1 or len(array) != length:
                raise ValueError("geometry arrays must be aligned float64 1-D arrays")
            if not np.isfinite(array).all():
                raise ValueError("geometry arrays must hold only finite values")
            array.setflags(write=False)
        mask = self.curvature_valid_mask
        if mask.dtype != np.bool_ or mask.ndim != 1 or len(mask) != length:
            raise ValueError("curvature_valid_mask must be an aligned boolean 1-D array")
        mask.setflags(write=False)
        return self


def build_track_profile(reference_path: pd.DataFrame, provenance: ArtifactProvenance) -> TrackProfile:
    """Build TrackProfile from an ordered, approved X/Y coordinate path."""
    if len(reference_path) < 2:
        raise ValueError("a track profile needs at least two ordered coordinate samples")

    x_m = reference_path["X"].to_numpy(dtype=np.float64) * _NATIVE_TO_METRE
    y_m = reference_path["Y"].to_numpy(dtype=np.float64) * _NATIVE_TO_METRE

    step_m = np.hypot(np.diff(x_m), np.diff(y_m))
    if np.any(step_m <= 0.0):
        raise ValueError("reference path coordinates must strictly advance between samples")

    actual_distance_m = np.concatenate(([0.0], np.cumsum(step_m)))
    reference_progress = actual_distance_m / actual_distance_m[-1]

    dx = np.gradient(x_m, actual_distance_m, edge_order=1)
    dy = np.gradient(y_m, actual_distance_m, edge_order=1)
    ddx = np.gradient(dx, actual_distance_m, edge_order=1)
    ddy = np.gradient(dy, actual_distance_m, edge_order=1)
    curvature_m_inv = (dx * ddy - dy * ddx) / np.hypot(dx, dy) ** 3

    # The one-sided differences at the first and last sample are an artifact of the
    # differencing scheme, not a measurement; mark them unsupported rather than dropping them.
    curvature_valid_mask = np.ones(len(curvature_m_inv), dtype=np.bool_)
    curvature_valid_mask[0] = False
    curvature_valid_mask[-1] = False

    transform = CoordinateTransform(
        origin_x_native=float(reference_path["X"].iloc[0]),
        origin_y_native=float(reference_path["Y"].iloc[0]),
    )

    return TrackProfile(
        provenance=provenance,
        coordinate_transform=transform,
        reference_progress=reference_progress,
        actual_distance_m=actual_distance_m,
        curvature_m_inv=curvature_m_inv,
        curvature_valid_mask=curvature_valid_mask,
    )
