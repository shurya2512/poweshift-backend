"""Completed chronological update units with explicit refusal boundaries."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class UpdateSegment:
    """One completed observed segment eligible for offline representation work."""

    entry: str
    session_key: str
    run_id: str
    chunk_index: int
    completed_cutoff_s: float
    start_time_s: float
    end_time_s: float
    split: str
    features: np.ndarray
    valid: np.ndarray
    padding: np.ndarray

    def __post_init__(self) -> None:
        if self.features.dtype != np.float32 or self.features.ndim != 2:
            raise ValueError("features must be float32 [time, feature]")
        if self.valid.shape != self.features.shape or self.valid.dtype != np.bool_:
            raise ValueError("valid must be a bool feature mask")
        if self.padding.shape != (self.features.shape[0],) or self.padding.dtype != np.bool_:
            raise ValueError("padding must be a bool time mask")
        if self.completed_cutoff_s < self.end_time_s or self.end_time_s < self.start_time_s:
            raise ValueError("segment cutoff and interval must be chronological")
        for values in (self.features, self.valid, self.padding):
            values.setflags(write=False)


@dataclass(frozen=True)
class RunClosure:
    """Pinned inventory and closing cutoff that proves a source run is complete."""

    entry: str
    session_key: str
    run_id: str
    split: str
    chunk_indexes: tuple[int, ...]
    completed_cutoff_s: float
    permitted_continuations: tuple[tuple[int, int], ...] = ()

    def __post_init__(self) -> None:
        if not self.chunk_indexes or self.chunk_indexes != tuple(range(len(self.chunk_indexes))):
            raise ValueError("run closure must name every consecutive chunk index")
        if any(later != earlier + 1 or earlier not in self.chunk_indexes for earlier, later in self.permitted_continuations):
            raise ValueError("run closure has an invalid permitted continuation")


@dataclass(frozen=True)
class UpdateUnit:
    """One completed run assembled without filling an unobserved gap."""

    entry: str
    session_key: str
    run_id: str
    split: str
    completed_cutoff_s: float
    features: np.ndarray
    valid: np.ndarray
    padding: np.ndarray

    def __post_init__(self) -> None:
        for values in (self.features, self.valid, self.padding):
            values.setflags(write=False)


def assemble_update_units(
    segments: tuple[UpdateSegment, ...], closures: tuple[RunClosure, ...]
) -> tuple[UpdateUnit, ...]:
    """Join only contiguous segments that share one chronological run identity."""
    closure_by_key = {(item.entry, item.session_key, item.run_id, item.split): item for item in closures}
    if len(closure_by_key) != len(closures):
        raise ValueError("run closures must not repeat an identity")
    grouped: dict[tuple[str, str, str, str], list[UpdateSegment]] = {}
    run_splits: dict[tuple[str, str, str], str] = {}
    for segment in segments:
        run_key = (segment.entry, segment.session_key, segment.run_id)
        prior_split = run_splits.setdefault(run_key, segment.split)
        if prior_split != segment.split:
            raise ValueError("one source run cannot span multiple splits")
        grouped.setdefault((segment.entry, segment.session_key, segment.run_id, segment.split), []).append(segment)
    units = []
    for key, run_segments in grouped.items():
        closure = closure_by_key.get(key)
        if closure is None:
            raise ValueError("update segments need a pinned complete-run closure")
        ordered = sorted(run_segments, key=lambda item: item.chunk_index)
        if tuple(item.chunk_index for item in ordered) != closure.chunk_indexes:
            raise ValueError("update segments do not match the pinned run closure")
        for previous, current in zip(ordered, ordered[1:]):
            contiguous = np.isclose(previous.end_time_s, current.start_time_s, rtol=0.0, atol=1e-12)
            permitted = (previous.chunk_index, current.chunk_index) in closure.permitted_continuations
            if not contiguous and not permitted:
                raise ValueError("gap between update segments has no pinned continuation")
        if not np.isclose(ordered[-1].completed_cutoff_s, closure.completed_cutoff_s, rtol=0.0, atol=1e-12):
            raise ValueError("update cutoff does not match the pinned run closure")
        first = ordered[0]
        units.append(
            UpdateUnit(
                entry=key[0],
                session_key=key[1],
                run_id=key[2],
                split=key[3],
                completed_cutoff_s=ordered[-1].completed_cutoff_s,
                features=np.concatenate([item.features for item in ordered]),
                valid=np.concatenate([item.valid for item in ordered]),
                padding=np.concatenate([item.padding for item in ordered]),
            )
        )
    return tuple(units)
