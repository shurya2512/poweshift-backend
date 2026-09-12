from poweshift_backend.reconstruction.replay import is_verified_continuation


def test_verified_continuation_allows_the_recorded_positive_sample_gap() -> None:
    continuation = ("2026-02-19", "1", "run", 0, 1)

    assert is_verified_continuation("2026-02-19", "1", "run", 0, 1, {continuation})
