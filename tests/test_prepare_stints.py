from datetime import date

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from poweshift_backend.contracts.acquisition import SessionIdentity
from poweshift_backend.contracts.preparation import (
    ArtifactProvenance,
    CoverageState,
    PreprocessingSpec,
    SplitManifest,
)
from poweshift_backend.prepare.runs import (
    RunBoundaryReason,
    RunSegment,
    TyreContext,
    garage_stop_intervals_s,
    red_flag_intervals_s,
    split_into_runs,
    tyre_history,
    tyre_replacement_times_s,
)
from poweshift_backend.prepare.windows import (
    FrozenScaler,
    OriginKind,
    StintPackage,
    build_stint_packages,
    causal_smooth,
    chunk_run_indices,
    fit_scaler,
    resolve_split,
    window_capacity_for_run,
)


def _provenance(source_rows: tuple[int, ...] = (0, 1, 2)) -> ArtifactProvenance:
    identity = SessionIdentity(
        year=2026,
        test_number=1,
        day_number=1,
        date=date(2026, 2, 11),
        venue="Bahrain",
        session_kind="preseason_test",
    )
    return ArtifactProvenance(
        source_identity=identity,
        source_rows=tuple(str(r) for r in source_rows),
        coverage_state=CoverageState.ADMITTED,
        config_version="v1",
    )


def _spec(**overrides) -> PreprocessingSpec:
    fields = {
        "gap_limit_s": 15.0,
        "staleness_limit_s": 2.0,
        "smoothing_limit_s": 1.0,
        "window_limit_s": 100.0,
        "availability_convention": "current_past_prefix",
    }
    fields.update(overrides)
    return PreprocessingSpec(**fields)


def _tyre() -> TyreContext:
    return TyreContext(stint=1, compound="MEDIUM", tyre_life=1.0, fresh_tyre=True, tyre_set_id=None)


def _split_manifest() -> SplitManifest:
    return SplitManifest(
        training="Test 1",
        selection=date(2026, 2, 18),
        final_evaluation=(date(2026, 2, 19), date(2026, 2, 20)),
    )


# --- Time and split boundaries ---------------------------------------------------------------


def test_split_into_runs_drops_samples_inside_a_garage_stop_and_ends_the_prior_run_there() -> None:
    times = pd.Series([0.0, 1.0, 2.0, 50.0, 300.0, 301.0])
    excluded = [(40.0, 290.0, RunBoundaryReason.GARAGE_STOP)]

    runs = split_into_runs("1", times, excluded, [], gap_limit_s=1000.0)

    assert [r.sample_indices for r in runs] == [(0, 1, 2), (4, 5)]
    assert runs[0].end_boundary_reason == RunBoundaryReason.GARAGE_STOP
    assert runs[1].end_boundary_reason == RunBoundaryReason.RUN_END


def test_red_flag_intervals_bound_a_run_boundary_and_are_dropped_from_the_run() -> None:
    track_status = pd.DataFrame(
        {
            "Time": pd.to_timedelta(["0:00:00", "0:00:40", "0:02:00"]),
            "Status": ["1", "5", "2"],
        }
    )
    intervals = red_flag_intervals_s(track_status)
    assert intervals == [(40.0, 120.0, RunBoundaryReason.RED_FLAG)]

    times = pd.Series([0.0, 30.0, 60.0, 130.0, 160.0])
    runs = split_into_runs("1", times, intervals, [], gap_limit_s=1000.0)

    assert [r.sample_indices for r in runs] == [(0, 1), (3, 4)]
    assert runs[0].end_boundary_reason == RunBoundaryReason.RED_FLAG


def test_red_flag_intervals_closes_a_trailing_red_period_at_the_last_known_status_time() -> None:
    track_status = pd.DataFrame(
        {
            "Time": pd.to_timedelta(["0:00:00", "0:00:40", "0:01:30"]),
            "Status": ["1", "5", "5"],
        }
    )

    intervals = red_flag_intervals_s(track_status)

    assert intervals == [(40.0, 90.0, RunBoundaryReason.RED_FLAG)]


def test_split_into_runs_breaks_at_a_tyre_replacement_time() -> None:
    times = pd.Series([0.0, 10.0, 20.0, 30.0])

    runs = split_into_runs("1", times, [], [20.0], gap_limit_s=1000.0)

    assert [r.sample_indices for r in runs] == [(0, 1), (2, 3)]
    assert runs[0].end_boundary_reason == RunBoundaryReason.TYRE_REPLACEMENT


def test_split_into_runs_breaks_on_a_gap_beyond_the_limit() -> None:
    times = pd.Series([0.0, 5.0, 10.0, 500.0, 505.0])

    runs = split_into_runs("1", times, [], [], gap_limit_s=15.0)

    assert [r.sample_indices for r in runs] == [(0, 1, 2), (3, 4)]
    assert runs[0].end_boundary_reason == RunBoundaryReason.EXCESSIVE_GAP


def test_garage_stop_intervals_pair_pit_in_and_pit_out_for_one_entry() -> None:
    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "1", "2"],
            "LapNumber": [1, 2, 1],
            "PitInTime": [pd.Timedelta("0:01:00"), pd.NaT, pd.NaT],
            "PitOutTime": [pd.NaT, pd.Timedelta("0:01:30"), pd.NaT],
        }
    )

    intervals = garage_stop_intervals_s(laps, "1")

    assert intervals == [(60.0, 90.0, RunBoundaryReason.GARAGE_STOP)]


def test_garage_stop_intervals_resolve_a_both_populated_row_against_the_pending_stop_first() -> None:
    """A row's PitOutTime can belong to an earlier stop than its own PitInTime."""
    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "1", "1"],
            "LapNumber": [1, 2, 3],
            "PitInTime": [pd.Timedelta("0:10:00"), pd.Timedelta("0:25:00"), pd.NaT],
            "PitOutTime": [pd.NaT, pd.Timedelta("0:15:00"), pd.Timedelta("0:30:00")],
        }
    )

    intervals = garage_stop_intervals_s(laps, "1")

    assert intervals == [
        (600.0, 900.0, RunBoundaryReason.GARAGE_STOP),
        (1500.0, 1800.0, RunBoundaryReason.GARAGE_STOP),
    ]


def test_garage_stop_intervals_pair_an_in_laps_pit_in_with_the_next_out_laps_pit_out() -> None:
    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "1", "1", "1"],
            "LapNumber": [1, 2, 3, 4],
            "PitInTime": [pd.NaT, pd.Timedelta("5:34:57.162"), pd.NaT, pd.NaT],
            "PitOutTime": [pd.Timedelta("5:30:31.076"), pd.NaT, pd.Timedelta("5:52:38.791"), pd.NaT],
        }
    )

    intervals = garage_stop_intervals_s(laps, "1")

    assert intervals == [
        (
            pd.Timedelta("5:34:57.162").total_seconds(),
            pd.Timedelta("5:52:38.791").total_seconds(),
            RunBoundaryReason.GARAGE_STOP,
        )
    ]


def test_garage_stop_intervals_drops_an_unpaired_trailing_pit_in_without_crashing() -> None:
    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "1"],
            "LapNumber": [1, 2],
            "PitInTime": [pd.NaT, pd.Timedelta("0:01:00")],
            "PitOutTime": [pd.NaT, pd.NaT],
        }
    )

    intervals = garage_stop_intervals_s(laps, "1")

    assert intervals == []


def test_tyre_replacement_times_detects_a_fresh_tyre_at_a_new_stint() -> None:
    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "1", "1"],
            "LapNumber": [1, 2, 3],
            "Stint": [1, 1, 2],
            "FreshTyre": [True, True, True],
            "Time": [pd.Timedelta("0:01:00"), pd.Timedelta("0:02:00"), pd.Timedelta("0:03:00")],
        }
    )

    assert tyre_replacement_times_s(laps, "1") == [180.0]


def test_tyre_replacement_times_does_not_count_a_missing_fresh_tyre_value_as_a_replacement() -> None:
    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "1"],
            "LapNumber": [1, 2],
            "Stint": [1, 2],
            "FreshTyre": pd.array([True, None], dtype="boolean"),
            "Time": [pd.Timedelta("0:01:00"), pd.Timedelta("0:02:00")],
        }
    )

    assert tyre_replacement_times_s(laps, "1") == []


@pytest.mark.parametrize(
    ("times", "window_limit_s", "expected_chunks"),
    [
        ([0.0, 1.0, 2.0], 10.0, [[0, 1, 2]]),
        ([0.0, 5.0, 11.0, 16.0], 10.0, [[0, 1], [2, 3]]),
    ],
)
def test_chunk_run_indices_bounds_each_chunk_to_the_window_duration_limit(
    times: list[float], window_limit_s: float, expected_chunks: list[list[int]]
) -> None:
    assert chunk_run_indices(times, window_limit_s) == expected_chunks


def test_stint_packages_never_span_two_separate_runs() -> None:
    times_s = pd.Series([0.0, 0.2, 500.0, 500.2])
    runs = split_into_runs("1", times_s, [], [], gap_limit_s=15.0)
    assert len(runs) == 2

    feature_columns = {"speed_ms": pd.Series([10.0, 11.0, 12.0, 13.0])}
    spec = _spec(window_limit_s=1000.0)
    packages = []
    for run in runs:
        packages += build_stint_packages(
            entry="1",
            session_key="d",
            run=run,
            times_s=times_s,
            feature_columns=feature_columns,
            tyre=_tyre(),
            programme_context="fp",
            quality_context="measured",
            split="training",
            spec=spec,
            provenance=_provenance(),
        )

    assert len(packages) == 2
    assert packages[0].end_time_s == 0.2
    assert packages[1].start_time_s == 500.0


def test_build_stint_packages_initial_interval_zero_and_later_valid_intervals_positive() -> None:
    times_s = pd.Series([0.0, 0.2, 0.4, 0.6])
    run = RunSegment(
        entry="1", sample_indices=(0, 1, 2, 3), start_time_s=0.0, end_time_s=0.6,
        end_boundary_reason=RunBoundaryReason.RUN_END,
    )
    feature_columns = {"speed_ms": pd.Series([10.0, 11.0, 12.0, 13.0])}
    spec = _spec(window_limit_s=1000.0)

    packages = build_stint_packages(
        entry="1", session_key="d", run=run, times_s=times_s, feature_columns=feature_columns,
        tyre=_tyre(), programme_context="fp", quality_context="measured",
        split="training", spec=spec, provenance=_provenance(),
    )

    assert len(packages) == 1
    package = packages[0]
    assert package.dt_s[0] == 0.0
    non_padding_later = ~package.padding[1:]
    assert (package.dt_s[1:][non_padding_later] > 0).all()
    assert package.X.dtype == np.float32
    assert package.valid.dtype == np.bool_
    assert package.origin.dtype == np.uint8
    assert np.isfinite(package.X).all()


def test_resolve_split_assigns_test_1_to_training_for_any_genuine_test_1_date() -> None:
    manifest = _split_manifest()

    assert resolve_split(date(2026, 2, 11), 1, manifest) == "training"
    assert resolve_split(date(2026, 2, 13), 1, manifest) == "training"


def test_resolve_split_rejects_a_test_1_claim_for_a_date_outside_test_1() -> None:
    manifest = _split_manifest()

    with pytest.raises(ValueError, match="not a Test 1 date"):
        resolve_split(date(2026, 2, 18), 1, manifest)


def test_resolve_split_assigns_the_approved_selection_and_final_evaluation_dates() -> None:
    manifest = _split_manifest()

    assert resolve_split(date(2026, 2, 18), 2, manifest) == "selection"
    assert resolve_split(date(2026, 2, 19), 2, manifest) == "final_evaluation"
    assert resolve_split(date(2026, 2, 20), 2, manifest) == "final_evaluation"


def test_resolve_split_rejects_a_date_outside_the_approved_manifest() -> None:
    manifest = _split_manifest()

    with pytest.raises(ValueError, match="not covered"):
        resolve_split(date(2026, 2, 21), 2, manifest)


# --- Stint provenance --------------------------------------------------------------------------


def test_tyre_history_never_invents_a_tyre_set_identity_from_fresh_tyre_alone() -> None:
    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "1"],
            "LapNumber": [1, 2],
            "Stint": [1, 1],
            "Compound": ["MEDIUM", "MEDIUM"],
            "TyreLife": [1.0, 2.0],
            "FreshTyre": [True, True],
        }
    )

    history = tyre_history(laps, "1")

    assert history == [
        TyreContext(stint=1, compound="MEDIUM", tyre_life=1.0, fresh_tyre=True, tyre_set_id=None)
    ]


def test_tyre_history_keeps_the_set_identity_unknown_without_a_fresh_tyre_event() -> None:
    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "1"],
            "LapNumber": [1, 2],
            "Stint": [1, 1],
            "Compound": ["MEDIUM", "MEDIUM"],
            "TyreLife": [5.0, 6.0],
            "FreshTyre": [False, False],
        }
    )

    history = tyre_history(laps, "1")

    assert history[0].tyre_set_id is None
    assert history[0].fresh_tyre is False


def test_padded_trailing_rows_are_invalid_derived_and_do_not_violate_interval_rules() -> None:
    times_s = pd.Series([0.0, 1.0])
    run = RunSegment(
        entry="1", sample_indices=(0, 1), start_time_s=0.0, end_time_s=1.0,
        end_boundary_reason=RunBoundaryReason.RUN_END,
    )
    feature_columns = {"speed_ms": pd.Series([10.0, 11.0])}
    spec = _spec(window_limit_s=10.0)

    packages = build_stint_packages(
        entry="1", session_key="d", run=run, times_s=times_s, feature_columns=feature_columns,
        tyre=_tyre(), programme_context="fp", quality_context="measured",
        split="training", spec=spec, provenance=_provenance(),
    )
    package = packages[0]

    assert package.X.shape[0] > 2
    assert package.padding[2:].all()
    assert not package.valid[2:].any()
    assert (package.origin[2:] == OriginKind.DERIVED).all()
    assert (package.dt_s[2:] == 0.0).all()


def test_missing_raw_feature_values_stay_finite_and_masked_invalid() -> None:
    times_s = pd.Series([0.0, 0.2])
    run = RunSegment(
        entry="1", sample_indices=(0, 1), start_time_s=0.0, end_time_s=0.2,
        end_boundary_reason=RunBoundaryReason.RUN_END,
    )
    feature_columns = {"speed_ms": pd.Series([10.0, np.nan])}
    spec = _spec(window_limit_s=1.0)

    packages = build_stint_packages(
        entry="1", session_key="d", run=run, times_s=times_s, feature_columns=feature_columns,
        tyre=_tyre(), programme_context="fp", quality_context="measured",
        split="training", spec=spec, provenance=_provenance(),
    )
    package = packages[0]

    assert not package.valid[1, 0]
    assert package.X[1, 0] == 0.0
    assert np.isfinite(package.X).all()


def test_a_non_finite_raw_feature_value_stays_finite_and_masked_invalid() -> None:
    times_s = pd.Series([0.0, 0.2])
    run = RunSegment(
        entry="1", sample_indices=(0, 1), start_time_s=0.0, end_time_s=0.2,
        end_boundary_reason=RunBoundaryReason.RUN_END,
    )
    feature_columns = {"speed_ms": pd.Series([10.0, np.inf])}
    spec = _spec(window_limit_s=1.0)

    packages = build_stint_packages(
        entry="1", session_key="d", run=run, times_s=times_s, feature_columns=feature_columns,
        tyre=_tyre(), programme_context="fp", quality_context="measured",
        split="training", spec=spec, provenance=_provenance(),
    )
    package = packages[0]

    assert not package.valid[1, 0]
    assert package.X[1, 0] == 0.0
    assert package.origin[1, 0] == OriginKind.DERIVED
    assert np.isfinite(package.X).all()


def test_stint_packages_share_one_stable_run_id_across_chunks_of_the_same_run() -> None:
    times_s = pd.Series([0.0, 5.0, 11.0, 16.0])
    run = RunSegment(
        entry="1", sample_indices=(0, 1, 2, 3), start_time_s=0.0, end_time_s=16.0,
        end_boundary_reason=RunBoundaryReason.RUN_END,
    )
    feature_columns = {"speed_ms": pd.Series([10.0, 11.0, 12.0, 13.0])}
    spec = _spec(window_limit_s=10.0)

    packages = build_stint_packages(
        entry="1", session_key="d", run=run, times_s=times_s, feature_columns=feature_columns,
        tyre=_tyre(), programme_context="fp", quality_context="measured",
        split="training", spec=spec, provenance=_provenance(),
    )

    assert len(packages) == 2
    assert packages[0].run_id == packages[1].run_id
    assert packages[0].chunk_index == 0
    assert packages[1].chunk_index == 1


def test_building_the_same_run_twice_produces_identical_stint_packages() -> None:
    times_s = pd.Series([0.0, 0.2, 0.4])
    run = RunSegment(
        entry="1", sample_indices=(0, 1, 2), start_time_s=0.0, end_time_s=0.4,
        end_boundary_reason=RunBoundaryReason.RUN_END,
    )
    feature_columns = {"speed_ms": pd.Series([10.0, 11.0, 12.0])}
    spec = _spec(window_limit_s=1000.0)
    kwargs = dict(
        entry="1", session_key="d", run=run, times_s=times_s, feature_columns=feature_columns,
        tyre=_tyre(), programme_context="fp", quality_context="measured",
        split="training", spec=spec, provenance=_provenance(),
    )

    first = build_stint_packages(**kwargs)[0]
    second = build_stint_packages(**kwargs)[0]

    assert np.array_equal(first.X, second.X)
    assert np.array_equal(first.valid, second.valid)
    assert np.array_equal(first.origin, second.origin)
    assert np.array_equal(first.dt_s, second.dt_s)
    assert np.array_equal(first.padding, second.padding)
    assert first.feature_names == second.feature_names
    assert first.quality_context == second.quality_context == "measured"
    assert first.provenance == second.provenance


def test_stint_package_rejects_non_finite_feature_values() -> None:
    with pytest.raises(ValidationError, match="finite"):
        StintPackage(
            entry="1", session_key="d", run_id="r", chunk_index=0, start_time_s=0.0, end_time_s=0.0,
            completed_cutoff_s=0.0, X=np.array([[np.nan]], dtype=np.float32),
            valid=np.array([[False]]), origin=np.array([[OriginKind.DERIVED]], dtype=np.uint8),
            dt_s=np.array([0.0]), padding=np.array([False]), feature_names=("speed_ms",),
            tyre=_tyre(), programme_context="fp", quality_context="measured",
            availability_convention="current_past_prefix", split="training", provenance=_provenance(),
        )


def test_stint_package_rejects_a_nonzero_initial_interval() -> None:
    with pytest.raises(ValidationError, match="initial interval"):
        StintPackage(
            entry="1", session_key="d", run_id="r", chunk_index=0, start_time_s=0.0, end_time_s=0.2,
            completed_cutoff_s=0.2, X=np.zeros((2, 1), dtype=np.float32),
            valid=np.ones((2, 1), dtype=bool), origin=np.zeros((2, 1), dtype=np.uint8),
            dt_s=np.array([0.1, 0.2]), padding=np.array([False, False]), feature_names=("speed_ms",),
            tyre=_tyre(), programme_context="fp", quality_context="measured",
            availability_convention="current_past_prefix", split="training", provenance=_provenance(),
        )


def test_stint_package_rejects_a_non_positive_later_valid_interval() -> None:
    with pytest.raises(ValidationError, match="later valid"):
        StintPackage(
            entry="1", session_key="d", run_id="r", chunk_index=0, start_time_s=0.0, end_time_s=0.2,
            completed_cutoff_s=0.2, X=np.zeros((2, 1), dtype=np.float32),
            valid=np.ones((2, 1), dtype=bool), origin=np.zeros((2, 1), dtype=np.uint8),
            dt_s=np.array([0.0, 0.0]), padding=np.array([False, False]), feature_names=("speed_ms",),
            tyre=_tyre(), programme_context="fp", quality_context="measured",
            availability_convention="current_past_prefix", split="training", provenance=_provenance(),
        )


def test_stint_package_feature_array_is_immutable_after_construction() -> None:
    package = StintPackage(
        entry="1", session_key="d", run_id="r", chunk_index=0, start_time_s=0.0, end_time_s=0.0,
        completed_cutoff_s=0.0, X=np.zeros((1, 1), dtype=np.float32),
        valid=np.ones((1, 1), dtype=bool), origin=np.zeros((1, 1), dtype=np.uint8),
        dt_s=np.array([0.0]), padding=np.array([False]), feature_names=("speed_ms",),
        tyre=_tyre(), programme_context="fp", quality_context="measured",
        availability_convention="current_past_prefix", split="training", provenance=_provenance(),
    )

    with pytest.raises(ValueError, match="read-only"):
        package.X[0, 0] = 1.0


# --- Transform isolation -----------------------------------------------------------------------


def test_changing_a_non_training_split_run_cannot_alter_the_training_fitted_scaler() -> None:
    feature_names = ("speed_ms",)
    spec = _spec(window_limit_s=1000.0)

    def _build_packages(selection_speed_values: list[float]) -> list[StintPackage]:
        packages = []
        training_run = RunSegment(
            entry="1", sample_indices=(0, 1, 2), start_time_s=0.0, end_time_s=0.4,
            end_boundary_reason=RunBoundaryReason.RUN_END,
        )
        packages += build_stint_packages(
            entry="1", session_key="test_1_day_1", run=training_run,
            times_s=pd.Series([0.0, 0.2, 0.4]),
            feature_columns={"speed_ms": pd.Series([10.0, 12.0, 14.0])},
            tyre=_tyre(), programme_context="fp", quality_context="measured",
            split="training", spec=spec, provenance=_provenance(),
        )
        selection_run = RunSegment(
            entry="1", sample_indices=(0, 1), start_time_s=0.0, end_time_s=0.2,
            end_boundary_reason=RunBoundaryReason.RUN_END,
        )
        packages += build_stint_packages(
            entry="1", session_key="test_2_day_1", run=selection_run,
            times_s=pd.Series([0.0, 0.2]),
            feature_columns={"speed_ms": pd.Series(selection_speed_values)},
            tyre=_tyre(), programme_context="fp", quality_context="measured",
            split="selection", spec=spec, provenance=_provenance(),
        )
        return packages

    def _fit_training_only(packages: list[StintPackage]) -> FrozenScaler:
        training = [p for p in packages if p.split == "training"]
        return fit_scaler(feature_names, [p.X for p in training], [p.valid for p in training])

    scaler_before = _fit_training_only(_build_packages([50.0, 60.0]))
    scaler_after = _fit_training_only(_build_packages([999999.0, -999999.0]))

    assert scaler_after.mean == pytest.approx(scaler_before.mean)
    assert scaler_after.scale == pytest.approx(scaler_before.scale)


def test_fitted_scaler_parameters_are_unaffected_by_later_mutation_of_the_training_arrays() -> None:
    feature_names = ("speed_ms",)
    training_X = [np.array([[10.0], [20.0]], dtype=np.float32)]
    training_valid = [np.array([[True], [True]])]

    scaler = fit_scaler(feature_names, training_X, training_valid)
    original_mean = float(scaler.mean[0])

    training_X[0][0, 0] = 9999.0

    assert float(scaler.mean[0]) == original_mean


def test_causal_smooth_averages_only_past_samples_within_the_window() -> None:
    times = np.array([0.0, 1.0, 2.0])
    values = np.array([10.0, 20.0, 30.0])
    valid = np.array([True, True, True])

    smoothed = causal_smooth(times, values, valid, smoothing_limit_s=1.5)

    assert smoothed[0] == pytest.approx(10.0)
    assert smoothed[1] == pytest.approx(15.0)
    assert smoothed[2] == pytest.approx(25.0)


def test_causal_smooth_excludes_invalid_samples_and_outputs_zero_where_invalid() -> None:
    times = np.array([0.0, 1.0, 2.0])
    values = np.array([10.0, 0.0, 30.0])
    valid = np.array([True, False, True])

    smoothed = causal_smooth(times, values, valid, smoothing_limit_s=5.0)

    assert smoothed[1] == 0.0
    assert smoothed[2] == pytest.approx(20.0)


def test_frozen_transform_output_before_a_cutoff_is_unaffected_by_rows_added_after_it() -> None:
    smoothing_limit_s = 2.0
    times_full = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    values_full = np.array([10.0, 12.0, 14.0, 999.0, 999.0])
    valid_full = np.array([True, True, True, True, True])
    cutoff = 2

    smoothed_prefix_only = causal_smooth(
        times_full[: cutoff + 1], values_full[: cutoff + 1], valid_full[: cutoff + 1], smoothing_limit_s
    )
    smoothed_full = causal_smooth(times_full, values_full, valid_full, smoothing_limit_s)

    assert smoothed_prefix_only == pytest.approx(smoothed_full[: cutoff + 1])


def test_window_capacity_reflects_the_run_own_native_sample_rate() -> None:
    times = [0.0, 1.0, 2.0]

    assert window_capacity_for_run(times, window_limit_s=10.0) == 11
    assert window_capacity_for_run([], window_limit_s=10.0) == 0
