import json

import pandas as pd
import pytest
import torch

from poweshift_backend.policy.curriculum import (
    load_curriculum_checkpoint,
    load_preseason_traces,
    load_promoted_profiles,
    load_qualifying_traces,
    load_race_traces,
    load_native_race_data,
    load_practice_traces,
    save_curriculum_checkpoint,
    split_race_traces,
)
from poweshift_backend.policy.diagnostic import DiagnosticTrace, create_diagnostic_model


def _write_registry(path, *, compatible: bool = True) -> None:
    path.write_text(json.dumps({
        "status": "promoted_provisional",
        "compatible_with_downstream_contract": compatible,
        "physics_admission": False,
        "profile_admission_id": "admission-a",
        "active_profiles": {
            "1": {
                "active": True,
                "profile": {
                    "parameters": {
                        "max_drive_force_n": 6_000.0,
                        "drag_n_per_ms2": 0.8,
                        "rolling_resistance_n": 120.0,
                    }
                },
            }
        },
    }))


def test_load_promoted_profiles_preserves_provisional_boundary(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    _write_registry(path)

    registry = load_promoted_profiles(path)

    assert tuple(registry.profiles) == ("1",)
    assert registry.admission_id == "admission-a"
    assert registry.physics_admitted is False


def test_load_promoted_profiles_rejects_incompatible_registry(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    _write_registry(path, compatible=False)

    with pytest.raises(ValueError, match="downstream-compatible"):
        load_promoted_profiles(path)


def test_load_preseason_traces_uses_every_admitted_package_in_manifest_order(tmp_path) -> None:
    manifest_path = tmp_path / "packages.json"
    table_path = tmp_path / "packages.parquet"
    manifest_path.write_text(json.dumps({
        "session_key": "2026-02-11",
        "packages": [
            {
                "package_id": "package-b",
                "entry": "1",
                "programme_context": "preseason_test",
                "quality_context": "measured",
                "split": "training",
                "provenance": {"coverage_state": "admitted"},
                "start_time_s": 10.0,
                "end_time_s": 14.0,
            },
            {
                "package_id": "package-a",
                "entry": "1",
                "programme_context": "preseason_test",
                "quality_context": "measured",
                "split": "training",
                "provenance": {"coverage_state": "admitted"},
                "start_time_s": 20.0,
                "end_time_s": 22.0,
            },
        ],
    }))
    rows = []
    for package_id, count in (("package-a", 3), ("package-b", 5)):
        for index in range(count):
            rows.append({
                "package_id": package_id,
                "row_index": index,
                "padding": package_id == "package-b" and index == 2,
                "X__speed_ms": 40.0 + index,
                "valid__speed_ms": True,
                "X__throttle_pct": 50.0 + index,
                "valid__throttle_pct": True,
                "X__brake": float(index == count - 1),
                "valid__brake": True,
            })
    pd.DataFrame(rows).to_parquet(table_path)

    registry_path = tmp_path / "profiles.json"
    _write_registry(registry_path)
    profiles = load_promoted_profiles(registry_path).profiles
    traces = load_preseason_traces(manifest_path, table_path, profiles, sample_count=3)

    assert [trace.trace_id for trace in traces] == ["package-b", "package-a"]
    assert traces[0].speed_ms == (40.0, 41.0, 44.0)
    assert traces[0].throttle == pytest.approx((0.5, 0.51, 0.54))
    assert traces[0].step_s == pytest.approx(2.0)
    assert all(trace.source_partition == "training" for trace in traces)


def test_load_preseason_traces_rejects_nontraining_package(tmp_path) -> None:
    manifest_path = tmp_path / "packages.json"
    table_path = tmp_path / "packages.parquet"
    manifest_path.write_text(json.dumps({
        "session_key": "2026-02-18",
        "packages": [{
            "package_id": "selection-package",
            "entry": "1",
            "programme_context": "preseason_test",
            "quality_context": "measured",
            "split": "selection",
            "provenance": {"coverage_state": "admitted"},
            "start_time_s": 0.0,
            "end_time_s": 1.0,
        }],
    }))
    pd.DataFrame({
        "package_id": ["selection-package", "selection-package"],
        "row_index": [0, 1],
        "padding": [False, False],
        "X__speed_ms": [40.0, 41.0],
        "valid__speed_ms": [True, True],
        "X__throttle_pct": [50.0, 51.0],
        "valid__throttle_pct": [True, True],
        "X__brake": [0.0, 0.0],
        "valid__brake": [True, True],
    }).to_parquet(table_path)

    registry_path = tmp_path / "profiles.json"
    _write_registry(registry_path)
    profiles = load_promoted_profiles(registry_path).profiles
    with pytest.raises(ValueError, match="training preseason"):
        load_preseason_traces(manifest_path, table_path, profiles)


def test_load_preseason_traces_retains_admitted_singleton_with_nominal_step(tmp_path) -> None:
    manifest_path = tmp_path / "packages.json"
    table_path = tmp_path / "packages.parquet"
    manifest_path.write_text(json.dumps({
        "session_key": "2026-02-11",
        "packages": [{
            "package_id": "singleton",
            "entry": "1",
            "programme_context": "preseason_test",
            "quality_context": "measured",
            "split": "training",
            "provenance": {"coverage_state": "admitted"},
            "start_time_s": 10.0,
            "end_time_s": 10.0,
        }],
    }))
    pd.DataFrame({
        "package_id": ["singleton"],
        "row_index": [0],
        "padding": [False],
        "X__speed_ms": [40.0],
        "valid__speed_ms": [True],
        "X__throttle_pct": [50.0],
        "valid__throttle_pct": [True],
        "X__brake": [0.0],
        "valid__brake": [True],
    }).to_parquet(table_path)
    registry_path = tmp_path / "profiles.json"
    _write_registry(registry_path)

    trace = load_preseason_traces(
        manifest_path, table_path, load_promoted_profiles(registry_path).profiles,
    )[0]

    assert trace.speed_ms == (40.0, 40.0)
    assert trace.step_s == pytest.approx(0.24)


def test_curriculum_checkpoint_round_trips_with_restricted_loading(tmp_path) -> None:
    path = tmp_path / "stage.pt"
    model = create_diagnostic_model(7)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    save_curriculum_checkpoint(path, model, optimizer, "preseason-day-1", 12, {"source": "abc"})

    restored_model = create_diagnostic_model(8)
    restored_optimizer = torch.optim.Adam(restored_model.parameters(), lr=3e-4)
    metadata = load_curriculum_checkpoint(path, restored_model, restored_optimizer)

    assert metadata == {
        "stage": "preseason-day-1",
        "completed_updates": 12,
        "sources": {"source": "abc"},
    }
    for expected, actual in zip(model.parameters(), restored_model.parameters()):
        assert torch.equal(expected, actual)


def test_weekend_loaders_preserve_all_qualifying_traces_and_complete_race_laps(tmp_path) -> None:
    normalization = {
        "mean": [0.0] * 9,
        "scale": [1.0] * 9,
    }
    qualifying_path = tmp_path / "qualifying.pt"
    binding_path = tmp_path / "binding.json"
    torch.save({
        "batches": [{"logical_batch_id": "q-1", "features": torch.ones(2, 3, 9)}],
        "diagnostics": [{"horizon_s": 2.0, "entries": ["1", "2"]}],
    }, qualifying_path)
    binding_path.write_text(json.dumps({"feature_normalization": normalization}))

    qualifying = load_qualifying_traces(qualifying_path, binding_path)

    assert [trace.trace_id for trace in qualifying] == ["q-1:1", "q-1:2"]
    assert all(trace.race_context is False for trace in qualifying)

    race_path = tmp_path / "race.pt"
    report_path = tmp_path / "race.json"
    progress = torch.stack((torch.linspace(0.0, 900.0, 101), torch.linspace(10.0, 910.0, 101)), dim=1)
    torch.save({
        "batches": [{"features": torch.ones(2, 101, 9), "observed_progress": progress}],
        "diagnostics": [{"entries": ["1", "2"]}],
    }, race_path)
    report_path.write_text(json.dumps({
        "source_binding": {"feature_normalization": normalization, "route_length_m": 1_000.0}
    }))

    race, route_length_m, _ = load_race_traces(race_path, report_path, "1")

    assert route_length_m == 1_000.0
    assert len(race) == 1
    assert race[0].lap_index == 1
    assert race[0].total_laps == 1
    assert race[0].race_context is True


def test_native_race_loader_uses_four_hz_and_past_controls(tmp_path) -> None:
    batch_path = tmp_path / "race.pt"
    report_path = tmp_path / "race.json"
    observation_times = torch.tensor((0.0, 0.25, 0.5, 0.75, 1.0), dtype=torch.float64)
    control_times = torch.tensor((0.0, 0.4, 0.8), dtype=torch.float64)
    controls = torch.tensor([
        ((0.1, 0.0), (0.2, 0.0)),
        ((0.4, 0.0), (0.5, 0.0)),
        ((0.8, 1.0), (0.9, 0.0)),
    ], dtype=torch.float64)
    progress = torch.tensor([
        (0.0, 0.2), (0.9, 1.1), (1.8, 2.0), (2.7, 2.9), (3.6, 3.8),
    ], dtype=torch.float64)
    torch.save({
        "batches": [{
            "observation_times_s": observation_times,
            "control_times_s": control_times,
            "controls": controls,
            "observed_progress": progress,
            "observed_speed": torch.full((5, 2), 40.0, dtype=torch.float64),
        }],
        "diagnostics": [{"start_s": 0.0, "end_s": 1.0, "entries": ["1", "2"]}],
    }, batch_path)
    report_path.write_text(json.dumps({
        "source_binding": {"route_length_m": 4.0, "observation_clock_hz": 4.0}
    }))

    data = load_native_race_data(batch_path, report_path, ("1", "2"))
    trace = data.traces_by_entry["1"][0]

    assert data.observation_hz == 4.0
    assert trace.step_s == 0.25
    assert trace.sample_time_s == pytest.approx((0.0, 0.25, 0.5, 0.75, 1.0))
    assert trace.throttle == pytest.approx((0.1, 0.1, 0.4, 0.4, 0.8))
    assert trace.observed_position == (2, 2, 2, 2, 2)
    assert len(data.field_ticks) == 5
    assert dict(data.field_ticks[2].throttle_by_entry)["1"] == pytest.approx(0.4)
    assert dict(data.field_ticks[2].brake_by_entry)["1"] == pytest.approx(0.0)


def test_race_split_is_chronological_and_disjoint() -> None:
    traces = tuple(DiagnosticTrace(
        "training", f"lap-{lap}", (40.0, 41.0), (1.0, 1.0), (0.0, 0.0), 0.25,
        lap_index=lap, total_laps=5,
    ) for lap in range(1, 6))

    training, validation = split_race_traces(traces, 0.8)

    assert [trace.trace_id for trace in training] == ["lap-1", "lap-2", "lap-3", "lap-4"]
    assert [trace.trace_id for trace in validation] == ["lap-5"]


def test_practice_loader_resamples_causally_at_four_hz(tmp_path) -> None:
    laps_path = tmp_path / "laps.parquet"
    car_path = tmp_path / "car.parquet"
    manifest_path = tmp_path / "practice_export.json"
    pd.DataFrame({
        "DriverNumber": ["1"],
        "LapNumber": [1.0],
        "LapStartTime": [pd.Timedelta(seconds=0.0)],
        "Time": [pd.Timedelta(seconds=1.0)],
        "IsAccurate": [True],
        "Deleted": [False],
        "source_row": [0],
    }).to_parquet(laps_path)
    pd.DataFrame({
        "DriverNumber": ["1", "1", "1"],
        "SessionTime": pd.to_timedelta([0.0, 0.4, 0.8], unit="s"),
        "Speed": [144.0, 180.0, 216.0],
        "Throttle": [10.0, 40.0, 80.0],
        "Brake": [False, False, True],
        "source_row": [0, 1, 2],
    }).to_parquet(car_path)
    import hashlib
    manifest_path.write_text(json.dumps({
        "kind": "source_bound_practice_export_v1",
        "identity": {"partition": "training", "session_id": "miami-fp1"},
        "exports": {
            "laps": {"path": str(laps_path), "sha256": hashlib.sha256(laps_path.read_bytes()).hexdigest()},
            "car": {"path": str(car_path), "sha256": hashlib.sha256(car_path.read_bytes()).hexdigest()},
        },
    }))
    registry_path = tmp_path / "profiles.json"
    _write_registry(registry_path)

    data = load_practice_traces(
        manifest_path, load_promoted_profiles(registry_path).profiles,
    )
    trace = data.traces_by_entry["1"][0]

    assert data.observation_hz == 4.0
    assert trace.sample_time_s == pytest.approx((0.0, 0.25, 0.5, 0.75, 1.0))
    assert trace.speed_ms == pytest.approx((40.0, 40.0, 50.0, 50.0, 60.0))
    assert trace.throttle == pytest.approx((0.1, 0.1, 0.4, 0.4, 0.8))
    assert trace.brake == pytest.approx((0.0, 0.0, 0.0, 0.0, 1.0))
    assert trace.race_context is False
