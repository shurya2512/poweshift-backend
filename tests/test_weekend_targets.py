from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from poweshift_backend.targets.weekend import extract_qualifying_targets, extract_race_targets
from poweshift_backend.targets.bundle import TargetStatus


_SOURCE_HASH = "a" * 64


def _lap_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "DriverNumber": ["1", "2", "3", "4", "1", "2", "1", "2"],
            "LapTime": pd.to_timedelta([90, 91, 92, None, 89, 90, 88, 89], unit="s"),
            "Time": pd.to_timedelta([100, 101, 102, 103, 200, 201, 300, 301], unit="s"),
            "IsAccurate": [True, True, True, False, True, True, True, True],
            "Deleted": [False, False, True, False, False, False, False, False],
            "FastF1Generated": [False] * 8,
            "PitInTime": [pd.NaT] * 8,
            "PitOutTime": [pd.NaT] * 8,
            "TrackStatus": ["1"] * 8,
            "Compound": ["SOFT"] * 8,
            "NativeSourceRow": list(range(8)),
        }
    )


def test_qualifying_extraction_keeps_invalid_laps_and_builds_same_segment_pairs() -> None:
    laps = _lap_rows()
    targets = extract_qualifying_targets(
        laps,
        (laps.iloc[:4], laps.iloc[4:6], laps.iloc[6:]),
        source_hash=_SOURCE_HASH,
        session_key="2026-03-07_Qualifying",
        cutoff_s=400.0,
        weather_known=True,
    )

    assert [pair.qualifying_segment for pair in targets.timing_pairs] == ["Q1", "Q2", "Q3"]
    assert {item.target.status for item in targets.laps} == {TargetStatus.VALID, TargetStatus.DELETED, TargetStatus.NO_TIME}
    assert all(pair.first_session_key == pair.second_session_key for pair in targets.timing_pairs)
    assert all(pair.first_segment == pair.second_segment == pair.qualifying_segment for pair in targets.timing_pairs)
    assert all(pair.fuel_known is False and pair.traffic_clear is False for pair in targets.timing_pairs)
    assert all(pair.comparison_mask is True for pair in targets.timing_pairs)


def test_practice_requires_known_fuel_and_matched_tyres_before_comparison() -> None:
    laps = _lap_rows().iloc[:2]
    targets = extract_qualifying_targets(
        laps,
        (),
        source_hash=_SOURCE_HASH,
        session_key="2026-03-06_Practice_1",
        cutoff_s=200.0,
        weather_known=True,
        session_kind="practice",
    )

    assert len(targets.timing_pairs) == 1
    pair = targets.timing_pairs[0]
    assert pair.session_kind == "practice"
    assert pair.tyre_matched is True
    assert pair.fuel_known is False
    assert pair.comparison_mask is False


def test_timing_pairs_exclude_laps_observed_after_the_cutoff() -> None:
    laps = _lap_rows().iloc[:2].copy()
    laps.loc[laps.index[1], "Time"] = pd.Timedelta(seconds=201)

    targets = extract_qualifying_targets(
        laps,
        (laps, None, None),
        source_hash=_SOURCE_HASH,
        session_key="2026-03-07_Qualifying",
        cutoff_s=200.0,
        weather_known=True,
    )

    assert targets.timing_pairs == ()


def test_qualifying_extraction_refuses_an_observation_without_a_finite_availability_time() -> None:
    laps = _lap_rows().iloc[:1].copy()
    laps.loc[laps.index[0], "Time"] = pd.NaT

    import pytest

    with pytest.raises(ValueError, match="availability time"):
        extract_qualifying_targets(
            laps,
            (laps, None, None),
            source_hash=_SOURCE_HASH,
            session_key="2026-03-07_Qualifying",
            cutoff_s=200.0,
            weather_known=True,
        )


def test_qualifying_loader_refuses_a_mutated_source_before_fastf1_load(tmp_path: Path) -> None:
    from poweshift_backend.targets.weekend import load_qualifying_targets

    session = tmp_path / "2026" / "2026-03-08_Australian_Grand_Prix" / "2026-03-07_Qualifying"
    session.mkdir(parents=True)
    source = session / "timing_app_data.ff1pkl"
    source.write_bytes(b"original")
    digest = sha256()
    digest.update(b"2026-03-08_Australian_Grand_Prix/2026-03-07_Qualifying/timing_app_data.ff1pkl\0original")
    source.write_bytes(b"changed")

    import pytest

    with pytest.raises(ValueError, match="source hash"):
        load_qualifying_targets(session, tmp_path / "isolated", source_hash=digest.hexdigest())


def test_unknown_lap_accuracy_is_unavailable_not_valid() -> None:
    laps = _lap_rows().iloc[:1].copy()
    laps["IsAccurate"] = laps["IsAccurate"].astype(object)
    laps.loc[laps.index[0], "IsAccurate"] = float("nan")

    targets = extract_qualifying_targets(
        laps,
        (laps, None, None),
        source_hash=_SOURCE_HASH,
        session_key="2026-03-07_Qualifying",
        cutoff_s=200.0,
        weather_known=True,
    )

    assert targets.laps[0].target.status is TargetStatus.UNAVAILABLE


def test_race_extraction_uses_lap_counts_for_common_wall_time_and_never_invents_lap_deficit_seconds() -> None:
    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "1", "2", "3"],
            "LapNumber": [1, 2, 1, 1],
            "Time": pd.to_timedelta([90, 180, 92, 95], unit="s"),
            "LapTime": pd.to_timedelta([90, 90, 92, None], unit="s"),
            "IsAccurate": [True, True, True, False],
            "Deleted": [False] * 4,
            "FastF1Generated": [False] * 4,
            "PitInTime": [pd.NaT] * 4,
            "PitOutTime": [pd.NaT] * 4,
            "TrackStatus": ["1", "1", "1", "2"],
            "NativeSourceRow": list(range(4)),
        }
    )

    targets = extract_race_targets(laps, roster=("1", "2", "3"), source_hash=_SOURCE_HASH)

    status = next(item for item in targets.race_wall_time_statuses if item.wall_time_s == 92.0 and item.entry == "1")
    assert status.completed_laps == 1
    gap = next(item for item in targets.race_checkpoint_gaps if item.checkpoint_lap == 1 and item.first == "1" and item.second == "2")
    assert gap.value_s == -2.0
    deficit = next(item for item in targets.race_checkpoint_gaps if item.first == "1" and item.second == "2" and item.status is TargetStatus.LAP_DEFICIT)
    assert deficit.status is TargetStatus.LAP_DEFICIT
    assert deficit.value_s is None
    unavailable = next(item for item in targets.race_checkpoint_gaps if item.first == "1" and item.second == "3")
    assert unavailable.status is TargetStatus.UNAVAILABLE
    assert unavailable.value_s is None


def test_race_export_validates_its_manifest_hash_before_reading_tables(tmp_path: Path) -> None:
    manifest = tmp_path / "acquisition_bundle.json"
    manifest.write_text("{}")

    from poweshift_backend.targets.weekend import extract_race_export

    try:
        extract_race_export(tmp_path, manifest_sha256=_SOURCE_HASH)
    except ValueError as error:
        assert "manifest hash" in str(error)
    else:
        raise AssertionError("expected a manifest hash refusal")


def test_race_export_accepts_a_workspace_relative_table_path(tmp_path: Path, monkeypatch) -> None:
    from poweshift_backend.targets import weekend

    monkeypatch.chdir(tmp_path)
    table_path = tmp_path / "recorded" / "laps.parquet"
    table_path.parent.mkdir()
    table_path.write_bytes(b"recorded table")
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    manifest = {
        "exports": {"laps": {"path": "recorded/laps.parquet", "sha256": sha256(table_path.read_bytes()).hexdigest()}},
        "roster": ["1"],
        "source_snapshot_sha256": _SOURCE_HASH,
    }
    manifest_path = export_dir / "acquisition_bundle.json"
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(weekend.pd, "read_parquet", lambda path: pd.DataFrame(columns=["DriverNumber"]))

    targets = weekend.extract_race_export(
        export_dir,
        manifest_sha256=sha256(manifest_path.read_bytes()).hexdigest(),
    )

    assert targets.source_hash == _SOURCE_HASH
