from dataclasses import replace

import pytest

from poweshift_backend.contracts.pits import PitSourceBinding, PitVisit
from poweshift_backend.pits.manifest import build_fixed_pit_schedule


def test_schedule_pairs_source_visits_and_hashes_canonical_content() -> None:
    visit = PitVisit(10, 100.0, 125.0, ("tyres",))
    source = PitSourceBinding("source-a", "a" * 64, (visit,), ("lap", "entry_time_s", "exit_time_s", "serviced_items"))
    first = build_fixed_pit_schedule(source)
    second = build_fixed_pit_schedule(source)
    assert first == second
    assert first.visits == (visit,)


def test_schedule_refuses_future_leakage_and_invalid_visit_pairing() -> None:
    visit = PitVisit(10, 100.0, 125.0, ("tyres",))
    with pytest.raises(ValueError, match="future field"):
        build_fixed_pit_schedule(PitSourceBinding("source-a", "a" * 64, (visit,), ("future_speed",)))
    with pytest.raises(ValueError, match="exit"):
        replace(visit, exit_time_s=100.0)
    with pytest.raises(ValueError, match="chronological"):
        build_fixed_pit_schedule(PitSourceBinding("source-a", "a" * 64, (visit, PitVisit(9, 200.0, 210.0, ())), ()))
