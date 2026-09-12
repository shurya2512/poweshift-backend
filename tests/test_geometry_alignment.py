from pathlib import Path

import pandas as pd
import pytest

from poweshift_backend.geometry.alignment import align_supported_observations, rebuild_source_linked_path


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
