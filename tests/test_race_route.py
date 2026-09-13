import json

import numpy as np
import pandas as pd
import pytest

from poweshift_backend.geometry.race_route import (
    RouteProjectionConfig,
    LapFinishCrossing,
    bounded_checkpoint_times,
    build_lap_source_streams,
    build_closed_route_for_lap,
    build_closed_static_route,
    build_static_route,
    interpolate_controls_with_mask,
    project_positions_to_route,
    source_finish_crossing,
    unwrap_route_progress,
    write_static_route_artifact,
)


def test_closed_route_ignores_consecutive_duplicate_position_samples() -> None:
    position = pd.DataFrame(
        {
            "source_row": ["a", "b", "c", "d", "e", "f"],
            "SessionTime": pd.to_timedelta([-0.1, 0.4, 0.8, 1.2, 1.6, 2.1], unit="s"),
            "X": [0.0, 100.0, 100.0, 100.0, 0.0, 0.0],
            "Y": [0.0, 0.0, 100.0, 100.0, 100.0, 0.0],
        }
    )

    route = build_closed_route_for_lap(
        position,
        pd.Timedelta(0),
        pd.Timedelta(seconds=2),
        RouteProjectionConfig(5.0, 1.0, 20.0, 5.0, 180.0, 2.0),
        position_max_offset_s=1.0,
    )

    assert route.closed is True
    assert len(route.source_rows) == 5


def test_static_route_projects_metric_positions_and_rejects_nearby_branches() -> None:
    route = build_static_route(
        pd.DataFrame(
            {
                "source_row": ["a", "b", "c", "d", "e", "f"],
                "X": [0.0, 100.0, 100.0, 0.0, 0.0, 100.0],
                "Y": [0.0, 0.0, 100.0, 100.0, 20.0, 20.0],
            }
        )
    )
    projected = project_positions_to_route(
        pd.DataFrame({"source_row": ["p", "q"], "X": [50.0, 50.0], "Y": [0.0, 10.0]}),
        route,
        RouteProjectionConfig(max_route_distance_m=1.5, branch_ambiguity_separation_m=1.5, branch_neighborhood_m=2.0, max_closure_m=1.0, max_seam_heading_delta_deg=10.0, control_max_offset_s=1.1),
    )

    assert projected.supported_mask.tolist() == [True, False]
    assert projected.distance_m[0] == 5.0
    assert np.isnan(projected.distance_m[1])
    assert projected.source_rows == ("p", "q")


def test_closed_route_uses_source_bounded_start_finish_datum() -> None:
    route = build_closed_static_route(
        pd.DataFrame({"source_row": ["a", "b", "c"], "X": [100.0, 100.0, -100.0], "Y": [0.0, 100.0, 0.0]}),
        start_xy_decimetres=(0.0, 0.0),
        end_xy_decimetres=(2.0, 0.0),
        boundary_source_brackets=(("start_left", "start_right"), ("end_left", "end_right")),
        max_closure_m=0.3,
        max_seam_heading_delta_deg=10.0,
    )

    assert route.closed is True
    assert route.loop_closure_m == pytest.approx(0.2)
    assert route.x_m[[0, -1]].tolist() == [0.1, 0.1]


def test_closed_route_treats_both_sides_of_the_datum_as_one_neighborhood() -> None:
    route = build_closed_static_route(
        pd.DataFrame({"source_row": ["a", "b", "c"], "X": [100.0, 100.0, -100.0], "Y": [0.0, 100.0, 0.0]}),
        start_xy_decimetres=(0.0, 0.0),
        end_xy_decimetres=(2.0, 0.0),
        boundary_source_brackets=(("start_left", "start_right"), ("end_left", "end_right")),
        max_closure_m=0.3,
        max_seam_heading_delta_deg=10.0,
    )

    projected = project_positions_to_route(
        pd.DataFrame({"source_row": ["datum"], "X": [1.0], "Y": [0.0]}),
        route,
        RouteProjectionConfig(1.0, 0.1, 2.0, 1.0, 10.0, 2.0),
    )

    assert projected.supported_mask.tolist() == [True]


def test_control_mask_preserves_only_bounded_recorded_brackets() -> None:
    controls = pd.DataFrame(
        {
            "source_row": ["0", "1", "2"],
            "SessionTime": pd.to_timedelta([0.0, 1.0, 2.4], unit="s"),
            "Throttle": [10.0, 20.0, 30.0],
            "Brake": [0.0, 0.0, 1.0],
        }
    )
    result = interpolate_controls_with_mask(
        controls,
        pd.to_timedelta([0.5, 1.5, 2.4], unit="s"),
        max_time_offset_s=1.1,
    )

    assert result.supported_mask.tolist() == [True, False, True]
    assert result.throttle_pct.tolist()[0] == 15.0
    assert np.isnan(result.throttle_pct[1])
    assert result.inferred_mask.tolist() == [True, False, False]
    assert result.source_brackets == (("0", "1"), None, ("2", "2"))


def test_static_route_artifact_binds_source_rows_and_config(tmp_path) -> None:
    route = build_static_route(
        pd.DataFrame({"source_row": ["a", "b", "c"], "X": [0.0, 100.0, 100.0], "Y": [0.0, 0.0, 100.0]})
    )
    manifest_path = write_static_route_artifact(
        route,
        tmp_path / "route",
        source_manifest_path="source/acquisition_bundle.json",
        source_manifest_sha256="a" * 64,
        config=RouteProjectionConfig(max_route_distance_m=5.0, branch_ambiguity_separation_m=1.0, branch_neighborhood_m=2.0, max_closure_m=1.0, max_seam_heading_delta_deg=10.0, control_max_offset_s=2.0),
    )

    payload = json.loads(manifest_path.read_text())
    assert payload["config"]["control_max_offset_s"] == 2.0
    assert payload["source_rows"] == ["a", "b", "c"]


def test_checkpoint_times_do_not_bridge_masked_progress() -> None:
    crossings = bounded_checkpoint_times(
        np.array([0.0, 10.0, 20.0]),
        np.array([0.0, 0.25, 0.5]),
        np.array([True, False, True]),
        np.array([0.0, 10.0, 20.0]),
    )

    assert crossings.supported_mask.tolist() == [True, False, True]
    assert crossings.time_s.tolist()[0] == 0.0
    assert np.isnan(crossings.time_s[1])
    assert crossings.time_s.tolist()[2] == 0.5


def test_lap_streams_keep_position_and_control_support_separate() -> None:
    route = build_static_route(
        pd.DataFrame({"source_row": ["r0", "r1", "r2"], "X": [0.0, 100.0, 200.0], "Y": [0.0, 0.0, 0.0]})
    )
    position = pd.DataFrame(
        {"source_row": ["p0", "p1", "p2", "p3"], "SessionTime": pd.to_timedelta([-0.1, 0.5, 1.5, 2.1], unit="s"), "X": [-10.0, 50.0, 150.0, 210.0], "Y": [0.0] * 4}
    )
    controls = pd.DataFrame(
        {"source_row": ["c0", "c1", "c2"], "SessionTime": pd.to_timedelta([-0.1, 0.5, 2.1], unit="s"), "Throttle": [10.0, 20.0, 30.0], "Brake": [0.0, 0.0, 1.0]}
    )
    streams = build_lap_source_streams(
        position,
        controls,
        pd.Timedelta(seconds=0),
        pd.Timedelta(seconds=2),
        route,
        RouteProjectionConfig(max_route_distance_m=1.0, branch_ambiguity_separation_m=0.0, branch_neighborhood_m=20.0, max_closure_m=1.0, max_seam_heading_delta_deg=10.0, control_max_offset_s=2.0),
        position_max_offset_s=1.1,
        observation_interval_s=1.0,
    )

    assert streams.position_supported_mask.tolist() == [True, True, True]
    assert streams.control_supported_mask.tolist() == [True, True, True]
    assert streams.control_inferred_mask.tolist() == [True, True, True]


def test_unwrapped_progress_preserves_offset_and_finish_event_uses_source_bracket() -> None:
    route = build_static_route(
        pd.DataFrame({"source_row": ["r0", "r1", "r2"], "X": [0.0, 500.0, 1000.0], "Y": [0.0, 0.0, 0.0]})
    )
    position = pd.DataFrame(
        {
            "source_row": ["p0", "p1", "p2"],
            "SessionTime": pd.to_timedelta([0.8, 4.9, 5.2], unit="s"),
            "X": [200.0, 980.0, 10.0],
            "Y": [0.0, 0.0, 0.0],
        }
    )
    config = RouteProjectionConfig(5.0, 0.0, 2.0, 1.0, 10.0, 2.0)
    unwrapped = unwrap_route_progress(np.array([98.0, 2.0, 8.0]), np.array([True, True, True]), route_length_m=100.0)
    finish = source_finish_crossing(
        position,
        pd.Timedelta(seconds=0),
        pd.Timedelta(seconds=5),
        route,
        config,
        position_max_offset_s=1.1,
        post_lap_margin_s=1.0,
    )

    assert unwrapped.tolist() == [98.0, 102.0, 108.0]
    assert isinstance(finish, LapFinishCrossing)
    assert finish.official_time_s == 5.0
    assert finish.spatial_crossing_time_s == pytest.approx(5.1)
    assert finish.supported is True
    assert finish.position_source_bracket == ("p1", "p2")
    assert finish.source_cutoff_extension_s == pytest.approx(0.2)
