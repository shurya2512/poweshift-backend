import pandas as pd
import pytest

from poweshift_backend.data.preparation_limits import TrainingDayPaths, derive_preprocessing_spec


def _write_fixture(tmp_path) -> TrainingDayPaths:
    # Ten 0.1s gaps then one 5.0s outlier gap, for one entry: quantiles land at hand-checkable points.
    times = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 6.0]
    car = pd.DataFrame({"Time": pd.to_timedelta(times, unit="s"), "DriverNumber": ["1"] * len(times)})
    car_path = tmp_path / "car.parquet"
    car.to_parquet(car_path, index=False)

    laps = pd.DataFrame(
        {
            "DriverNumber": pd.array([], dtype="object"),
            "LapNumber": pd.array([], dtype="float64"),
            "PitInTime": pd.to_timedelta([], unit="s"),
            "PitOutTime": pd.to_timedelta([], unit="s"),
            "Stint": pd.array([], dtype="float64"),
            "FreshTyre": pd.array([], dtype="boolean"),
            "Time": pd.to_timedelta([], unit="s"),
        }
    )
    laps_path = tmp_path / "laps.parquet"
    laps.to_parquet(laps_path, index=False)

    track_status = pd.DataFrame({"Time": pd.to_timedelta([], unit="s"), "Status": pd.array([], dtype="object")})
    track_status_path = tmp_path / "track_status.parquet"
    track_status.to_parquet(track_status_path, index=False)

    return TrainingDayPaths(date="2026-02-11", car_path=car_path, laps_path=laps_path, track_status_path=track_status_path)


def test_derive_preprocessing_spec_computes_gap_limit_as_the_stated_quantile_of_training_intervals(tmp_path) -> None:
    spec, derivation = derive_preprocessing_spec([_write_fixture(tmp_path)])

    # 11 sorted diffs [0.1]*10 + [5.0]; the 0.999 quantile (linear) sits 99% between the last two.
    assert spec.gap_limit_s == pytest.approx(0.1 + 0.99 * 4.9)
    assert derivation["sample_interval_statistic"]["gap_limit_s"]["quantile"] == 0.999
    assert derivation["sample_interval_statistic"]["n_intervals"] == 11


def test_derive_preprocessing_spec_computes_staleness_and_smoothing_as_median_and_p95(tmp_path) -> None:
    spec, derivation = derive_preprocessing_spec([_write_fixture(tmp_path)])

    assert spec.staleness_limit_s == pytest.approx(0.1)
    assert spec.smoothing_limit_s == pytest.approx(0.1 + 0.5 * 4.9)
    assert "not consumed" in derivation["sample_interval_statistic"]["staleness_limit_s"]["note"]


def test_derive_preprocessing_spec_computes_window_limit_from_training_run_durations(tmp_path) -> None:
    spec, derivation = derive_preprocessing_spec([_write_fixture(tmp_path)])

    # The 5.0s gap exceeds the derived gap_limit_s, splitting one run of duration 1.0s and one of 0.0s.
    assert spec.window_limit_s == pytest.approx(0.5)
    assert derivation["run_duration_statistic"]["n_runs"] == 2


def test_derive_preprocessing_spec_records_the_training_days_it_read(tmp_path) -> None:
    _, derivation = derive_preprocessing_spec([_write_fixture(tmp_path)])

    assert derivation["training_days"] == ["2026-02-11"]
    assert derivation["sample_interval_statistic"]["car_rows_per_day"] == {"2026-02-11": 12}
