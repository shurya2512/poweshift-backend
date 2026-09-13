"""Source-bound two-corner route contracts."""

from dataclasses import dataclass
from math import isfinite

from poweshift_backend.contracts.powertrain import EvidenceOrigin


@dataclass(frozen=True)
class RouteSegment:
    """One connected route segment with source line distances."""

    segment_id: str
    start_node: str
    end_node: str
    length_m: float
    geometry_id: str
    source_sha256: str
    line_distances_m: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not all((self.segment_id, self.start_node, self.end_node, self.geometry_id)):
            raise ValueError("route segment identity is incomplete")
        if not isfinite(self.length_m) or self.length_m <= 0.0 or len(self.source_sha256) != 64:
            raise ValueError("route segment geometry provenance is invalid")
        names = [name for name, _ in self.line_distances_m]
        if len(names) != len(set(names)):
            raise ValueError("route line maps must be unique")
        if any(not isfinite(distance) or not 0.0 <= distance <= self.length_m for _, distance in self.line_distances_m):
            raise ValueError("route line distance is outside its segment")


@dataclass(frozen=True)
class TwoCornerRoute:
    """Exactly two connected corners plus supported continuation."""

    route_id: str
    corners: tuple[RouteSegment, RouteSegment]
    continuation_m: float
    origin: EvidenceOrigin

    def __post_init__(self) -> None:
        if not self.route_id or len(self.corners) != 2:
            raise ValueError("two-corner route needs exactly two segments")
        if self.corners[0].end_node != self.corners[1].start_node:
            raise ValueError("two-corner route segments must be connected")
        if self.corners[0].geometry_id != self.corners[1].geometry_id:
            raise ValueError("two-corner route segments must share source geometry")
        if not isfinite(self.continuation_m) or self.continuation_m <= 0.0:
            raise ValueError("two-corner route needs supported continuation")

    @property
    def total_length_m(self) -> float:
        """Return both corners and the supported continuation length."""
        return sum(corner.length_m for corner in self.corners) + self.continuation_m

    @property
    def line_maps(self) -> frozenset[str]:
        """Return all source-defined rule lines on the route."""
        return frozenset(name for corner in self.corners for name, _ in corner.line_distances_m)
