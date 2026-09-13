from pathlib import Path
import json

import numpy as np
import pandas as pd
import pytest

from poweshift_backend.geometry.alignment import (
    align_supported_observations,
    audit_full_race_geometry,
    build_full_race_geometry,
    build_full_lap_geometry,
    road_at_predicted_progress,
    rebuild_source_linked_path,
    source_crossing_time_at_progress,
    source_crossing_time_at_unwrapped_progress,
    source_progress_at_wall_time,
    write_full_lap_geometry_artifact,
    write_full_race_geometry_artifact,
)


def test_rebuild_source_linked_path_uses_only_profile_source_rows(tmp_path: Path) -> None:
    positions = tmp_path / "positions.parquet"
    pd.DataFrame(
        {"source_row": [2, 3, 4], "DriverNumber": ["1", "1", "1"], "X": [0.0, 10.0, 20.0], "Y": [0.0, 0.0, 0.0]}
    ).to_parquet(positions)

    path = rebuild_source_linked_path(("2", "4"), positions, "1")

    assert path.source_rows == ("2", "4")
    assert path.distance_m.tolist() == [0.0, 2.0]


def test_alignment_refuses_observations_without_recorded_coordinates(tmp_path: Path) -> None:
    positions = tmp_path / "positions.parquet"
    pd.DataFrame({"source_row": [2, 4], "DriverNumber": ["1", "1"], "X": [0.0, 20.0], "Y": [0.0, 0.0]}).to_parquet(positions)
    path = rebuild_source_linked_path(("2", "4"), positions, "1")

    with pytest.raises(ValueError, match="recorded X/Y"):
        align_supported_observations(pd.DataFrame({"speed_ms": [10.0]}), path)


def test_alignment_maps_finite_recorded_coordinates_to_route_progress(tmp_path: Path) -> None:
    positions = tmp_path / "positions.parquet"
    pd.DataFrame({"source_row": [2, 4], "DriverNumber": ["1", "1"], "X": [0.0, 20.0], "Y": [0.0, 0.0]}).to_parquet(positions)
    path = rebuild_source_linked_path(("2", "4"), positions, "1")

    aligned = align_supported_observations(
        pd.DataFrame({"X": [0.0, 20.0], "Y": [0.0, 0.0]}), path, max_distance_m=0.1, ambiguity_margin_m=0.01
    )

    assert aligned.distance_m.tolist() == [0.0, 2.0]
    assert aligned.progress.tolist() == [0.0, 1.0]


def test_alignment_refuses_distant_or_ambiguous_coordinates(tmp_path: Path) -> None:
    positions = tmp_path / "positions.parquet"
    pd.DataFrame({"source_row": [2, 4], "DriverNumber": ["1", "1"], "X": [0.0, 20.0], "Y": [0.0, 0.0]}).to_parquet(positions)
    path = rebuild_source_linked_path(("2", "4"), positions, "1")

    with pytest.raises(ValueError, match="distance"):
        align_supported_observations(
            pd.DataFrame({"X": [100.0], "Y": [0.0]}), path, max_distance_m=1.0, ambiguity_margin_m=0.01
        )
    with pytest.raises(ValueError, match="ambiguous"):
        align_supported_observations(
            pd.DataFrame({"X": [10.0], "Y": [0.0]}), path, max_distance_m=2.0, ambiguity_margin_m=0.01
        )


def test_full_lap_geometry_links_controls_to_exact_position_source_rows(tmp_path: Path) -> None:
    laps = tmp_path / "laps.parquet"
    positions = tmp_path / "positions.parquet"
    car = tmp_path / "car.parquet"
    pd.DataFrame(
        {
            "DriverNumber": ["1"],
            "LapNumber": [7.0],
            "LapStartTime": [pd.Timedelta(seconds=10)],
            "Time": [pd.Timedelta(seconds=12)],
            "IsAccurate": [True],
            "Deleted": [False],
            "PitInTime": [pd.NaT],
            "PitOutTime": [pd.NaT],
        }
    ).to_parquet(laps)
    pd.DataFrame({
        "source_row": [8, 9, 10, 11, 12, 13, 14], "DriverNumber": ["1"] * 7,
        "SessionTime": pd.to_timedelta([9.8, 9.9, 10.5, 11.0, 11.5, 12.1, 12.2], unit="s"),
        "X": [-2.0, -1.0, 5.0, 10.0, 15.0, 21.0, 22.0], "Y": [0.0] * 7,
        "Status": ["OnTrack"] * 7,
    }).to_parquet(positions)
    pd.DataFrame(
        {
            "source_row": [19, 20, 21, 22], "DriverNumber": ["1"] * 4,
            "SessionTime": pd.to_timedelta([9.9, 10.5, 11.5, 12.1], unit="s"),
            "Speed": [180.0, 180.0, 180.0, 180.0],
            "Throttle": [50.0, 60.0, 70.0, 80.0], "Brake": [0.0] * 4,
        }
    ).to_parquet(car)

    geometry = build_full_lap_geometry(laps, positions, car, "1", 7.0, max_time_offset_s=1.1)

    assert geometry.position_source_rows == ("8", "9", "10", "11", "12", "13", "14")
    assert geometry.control_source_rows == ("19", "20", "21", "22")
    assert geometry.time_s.tolist() == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0])
    assert geometry.control_time_s.tolist() == pytest.approx([0.0, 0.5, 1.5, 2.0])
    assert geometry.observed_speed_ms.tolist() == pytest.approx([50.0] * 9)
    assert geometry.distance_m[[0, -1]].tolist() == pytest.approx([0.0, 2.0])
    assert geometry.progress[[0, -1]].tolist() == [0.0, 1.0]
    assert geometry.motion_derived_mask.tolist() == [True, True, False, True, True, True, False, True, True]
    np.testing.assert_allclose(
        road_at_predicted_progress(geometry, np.array([0.0, 2.0])), [[0.0, 1.0], [0.0, 1.0]]
    )
    np.testing.assert_allclose(source_progress_at_wall_time(geometry, np.array([0.0, 2.0])), [0.0, 1.0])
    np.testing.assert_allclose(source_crossing_time_at_progress(geometry, np.array([0.0, 1.0])), [0.0, 2.0])
    manifest_path = write_full_lap_geometry_artifact(
        geometry,
        tmp_path / "artifact",
        source_manifest_path="source/acquisition_bundle.json",
        source_manifest_sha256="a" * 64,
        config={"max_time_offset_s": 1.1, "observation_interval_s": 0.25},
    )
    manifest = json.loads(manifest_path.read_text())
    assert manifest["source_binding"]["manifest_sha256"] == "a" * 64
    assert manifest["geometry_scope"] == "single supported lap; not a full-race rollout"
    with np.load(manifest_path.parent / manifest["arrays_path"], allow_pickle=False) as arrays:
        np.testing.assert_allclose(arrays["observed_speed_ms"], [50.0] * 9)
    audit = audit_full_race_geometry(laps, positions, car, "1", max_time_offset_s=1.1)
    assert audit.full_race_supported is False
    assert audit.lap_coverage[0].state == "supported"
    race = build_full_race_geometry(laps, positions, car, "1", max_time_offset_s=1.1)
    assert race.full_race_supported is False
    assert race.supported_mask.all()
    assert race.same_checkpoint_supported is False
    assert race.common_position_brackets[0] is not None
    assert race.common_speed_brackets[0] is not None
    np.testing.assert_allclose(race.unwrapped_progress_laps[[0, -1]], [6.0, 7.0])
    crossings = source_crossing_time_at_unwrapped_progress(race, np.array([6.0, 7.0]))
    assert crossings.supported_mask.all()
    np.testing.assert_allclose(crossings.time_s, [0.0, 2.0])
    race_manifest = write_full_race_geometry_artifact(
        race,
        tmp_path / "race_artifact",
        source_manifest_path="source/acquisition_bundle.json",
        source_manifest_sha256="a" * 64,
        config={"max_time_offset_s": 1.1, "observation_interval_s": 0.25},
    )
    race_payload = json.loads(race_manifest.read_text())
    assert race_payload["full_race_supported"] is False
    assert race_payload["lap_boundary_tolerance_s"] == pytest.approx(1e-6)
    field_laps = tmp_path / "field_laps.parquet"
    pd.concat(
        [
            pd.read_parquet(laps),
            pd.DataFrame(
                {
                    "DriverNumber": ["2"], "LapNumber": [1.0], "LapStartTime": [pd.Timedelta(seconds=0)],
                    "Time": [pd.Timedelta(seconds=2)], "IsAccurate": [True], "Deleted": [False],
                    "PitInTime": [pd.NaT], "PitOutTime": [pd.NaT],
                }
            ),
        ],
        ignore_index=True,
    ).to_parquet(field_laps)
    field_race = build_full_race_geometry(field_laps, positions, car, "1", max_time_offset_s=1.1)
    assert field_race.participation_start_s == 10.0
    assert field_race.full_race_supported is False
    np.testing.assert_allclose(field_race.unwrapped_progress_laps[40], 6.0)


def test_full_lap_geometry_refuses_nontrack_positions_or_missing_boundary_brackets(tmp_path: Path) -> None:
    laps = tmp_path / "laps.parquet"
    positions = tmp_path / "positions.parquet"
    car = tmp_path / "car.parquet"
    pd.DataFrame(
        {
            "DriverNumber": ["1"], "LapNumber": [1.0], "LapStartTime": [pd.Timedelta(seconds=0)],
            "Time": [pd.Timedelta(seconds=2)], "IsAccurate": [True], "Deleted": [False],
            "PitInTime": [pd.NaT], "PitOutTime": [pd.NaT],
        }
    ).to_parquet(laps)
    pd.DataFrame(
        {
            "source_row": [0, 1, 2, 3, 4, 5, 6], "DriverNumber": ["1"] * 7,
            "SessionTime": pd.to_timedelta([-0.2, -0.1, 0.0, 1.0, 2.0, 2.1, 2.2], unit="s"),
            "X": [-2.0, -1.0, 0.0, 10.0, 20.0, 21.0, 22.0],
            "Y": [0.0] * 7, "Status": ["OnTrack", "OnTrack", "OnTrack", "OffTrack", "OnTrack", "OnTrack", "OnTrack"],
        }
    ).to_parquet(positions)
    pd.DataFrame(
        {
            "source_row": [6, 7, 8], "DriverNumber": ["1"] * 3,
            "SessionTime": pd.to_timedelta([-0.1, 1.0, 2.1], unit="s"),
            "Speed": [10.0] * 3, "Throttle": [50.0] * 3, "Brake": [0.0] * 3,
        }
    ).to_parquet(car)

    with pytest.raises(ValueError, match="on-track"):
        build_full_lap_geometry(laps, positions, car, "1", 1.0, max_time_offset_s=1.1)


def _write_continuous_race_sources(tmp_path: Path, *, accurate: bool = True, track_status: str = "1", pit: bool = False) -> tuple[Path, Path, Path]:
    laps_path = tmp_path / "race_laps.parquet"
    position_path = tmp_path / "race_positions.parquet"
    car_path = tmp_path / "race_car.parquet"
    pd.DataFrame(
        {
            "DriverNumber": ["1", "1", "2"],
            "LapNumber": [1.0, 2.0, 1.0],
            "LapStartTime": pd.to_timedelta([0.0, 2.0, 0.0], unit="s"),
            "Time": pd.to_timedelta([2.0, 4.0, 6.0], unit="s"),
            "IsAccurate": [accurate, accurate, True],
            "Deleted": [False, False, False],
            "PitInTime": [pd.Timedelta(seconds=2) if pit else pd.NaT, pd.NaT, pd.NaT],
            "PitOutTime": [pd.NaT, pd.NaT, pd.NaT],
            "TrackStatus": [track_status, track_status, "1"],
        }
    ).to_parquet(laps_path)
    times = [-0.2, -0.1, 0.0, 0.8, 1.6, 2.0, 2.8, 3.6, 4.0, 4.1, 4.2]
    pd.DataFrame(
        {
            "source_row": list(range(len(times))),
            "DriverNumber": ["1"] * len(times),
            "SessionTime": pd.to_timedelta(times, unit="s"),
            "X": np.asarray(times) * 10.0,
            "Y": [0.0] * len(times),
            "Status": ["OnTrack"] * len(times),
        }
    ).to_parquet(position_path)
    control_times = [-0.1, 0.5, 1.5, 2.1, 3.0, 3.9, 4.1]
    pd.DataFrame(
        {
            "source_row": list(range(len(control_times))),
            "DriverNumber": ["1"] * len(control_times),
            "SessionTime": pd.to_timedelta(control_times, unit="s"),
            "Speed": [180.0] * len(control_times),
            "Throttle": [50.0] * len(control_times),
            "Brake": [0.0] * len(control_times),
        }
    ).to_parquet(car_path)
    return laps_path, position_path, car_path


def test_full_race_support_ends_at_declared_entry_participation(tmp_path: Path) -> None:
    laps, positions, car = _write_continuous_race_sources(tmp_path)

    audit = audit_full_race_geometry(laps, positions, car, "1", max_time_offset_s=1.1)
    race = build_full_race_geometry(laps, positions, car, "1", max_time_offset_s=1.1)

    assert audit.full_race_supported is True
    assert race.full_race_supported is True
    assert race.participation_end_s == 4.0
    assert race.time_s[-1] == 6.0
    assert not race.supported_mask[race.time_s > 4.0].any()


def test_timing_and_event_masks_do_not_remove_source_path_support(tmp_path: Path) -> None:
    laps, positions, car = _write_continuous_race_sources(tmp_path, accurate=False, track_status="6")

    audit = audit_full_race_geometry(laps, positions, car, "1", max_time_offset_s=1.1)
    race = build_full_race_geometry(laps, positions, car, "1", max_time_offset_s=1.1)

    assert audit.full_race_supported is True
    assert race.full_race_supported is True
    assert {item.state for item in race.lap_coverage} == {"timing_and_event_masked_geometry_present"}


def test_pit_geometry_is_not_a_supported_physics_rollout(tmp_path: Path) -> None:
    laps, positions, car = _write_continuous_race_sources(tmp_path, pit=True)

    race = build_full_race_geometry(laps, positions, car, "1", max_time_offset_s=1.1)

    assert race.full_race_supported is False
    assert race.lap_coverage[0].state == "pit_geometry_present"


def test_full_race_refuses_lap_overlap_below_the_observation_interval(tmp_path: Path) -> None:
    laps, positions, car = _write_continuous_race_sources(tmp_path)
    records = pd.read_parquet(laps)
    records.loc[(records["DriverNumber"] == "1") & (records["LapNumber"] == 2.0), "LapStartTime"] = pd.Timedelta(seconds=1.9)
    records.to_parquet(laps)

    audit = audit_full_race_geometry(laps, positions, car, "1", max_time_offset_s=1.1)
    race = build_full_race_geometry(laps, positions, car, "1", max_time_offset_s=1.1)

    assert audit.lap_boundaries_supported is False
    assert audit.full_race_supported is False
    assert race.lap_boundaries_supported is False
    assert race.full_race_supported is False
