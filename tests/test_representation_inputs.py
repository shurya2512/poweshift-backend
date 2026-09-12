import numpy as np
import pytest

from poweshift_backend.representation.inputs import RunClosure, UpdateSegment, assemble_update_units


def _segment(index: int, *, start: float, end: float) -> UpdateSegment:
    return UpdateSegment(
        entry="1",
        session_key="test",
        run_id="run",
        chunk_index=index,
        completed_cutoff_s=end,
        start_time_s=start,
        end_time_s=end,
        split="training",
        features=np.array([[1.0, 2.0]], dtype=np.float32),
        valid=np.array([[True, True]], dtype=np.bool_),
        padding=np.array([False], dtype=np.bool_),
    )


def _closure() -> RunClosure:
    return RunClosure("1", "test", "run", "training", (0,), 1.0)


def test_assembly_refuses_a_gap_between_chronological_segments() -> None:
    with pytest.raises(ValueError, match="gap"):
        assemble_update_units(
            (_segment(0, start=0.0, end=1.0), _segment(1, start=2.0, end=3.0)),
            (RunClosure("1", "test", "run", "training", (0, 1), 3.0),),
        )


def test_assembly_preserves_completed_cutoff_and_mask() -> None:
    unit = assemble_update_units((_segment(0, start=0.0, end=1.0),), (_closure(),))[0]

    assert unit.completed_cutoff_s == 1.0
    assert unit.valid.tolist() == [[True, True]]
    assert unit.features.flags.writeable is False


def test_assembly_refuses_a_segment_without_a_pinned_run_closure() -> None:
    with pytest.raises(ValueError, match="closure"):
        assemble_update_units((_segment(0, start=0.0, end=1.0),), ())


def test_assembly_refuses_a_noncontiguous_run_without_a_pinned_continuation() -> None:
    with pytest.raises(ValueError, match="continuation"):
        assemble_update_units(
            (_segment(0, start=0.0, end=1.0), _segment(1, start=1.1, end=2.0)),
            (RunClosure("1", "test", "run", "training", (0, 1), 2.0),),
        )


def test_assembly_accepts_only_a_pinned_permitted_continuation() -> None:
    unit = assemble_update_units(
        (_segment(0, start=0.0, end=1.0), _segment(1, start=1.1, end=2.0)),
        (RunClosure("1", "test", "run", "training", (0, 1), 2.0, ((0, 1),)),),
    )[0]

    assert unit.features.shape == (2, 2)
