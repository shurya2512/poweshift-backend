from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from poweshift_backend.energy.allocator import DeploymentPrior
from poweshift_backend.policy.curriculum import RaceFieldTick
from poweshift_backend.policy.diagnostic import (
    DiagnosticTrace,
    FittedProfile,
    create_diagnostic_model,
)
from poweshift_backend.policy.race_validation import (
    P23ScenarioPrior,
    bounded_additive_lap_time_proxy,
    consolidate_profile_reports,
    load_major_race_events,
    run_p23_diagnostic,
    validate_profile_policy,
)


def _prior() -> DeploymentPrior:
    return DeploymentPrior(0.2, 5_000_000.0, 5_000_000.0, 0.95, 0.8)


def _profile(entry: str = "1") -> FittedProfile:
    return FittedProfile(entry, 7_000.0, 0.8, 120.0)


def _trace() -> DiagnosticTrace:
    return DiagnosticTrace(
        "training", "lap-1", (40.0, 41.0, 42.0), (1.0, 1.0, 0.0), (0.0, 0.0, 1.0), 0.25,
        "1", True, (0.8, 0.7, 0.6), (0.6, 0.7, 0.8), (2.0, 2.0, 0.7), (0.0, 0.0, 0.7), 1, 1,
        (0.0, 0.25, 0.5), (100.0, 110.0, 120.0), (23, 22, 22),
    )


def test_validation_accounts_for_every_attack_opportunity() -> None:
    report = validate_profile_policy(create_diagnostic_model(2), (_trace(),), _profile(), _prior())

    totals = report["opportunity_totals"]
    assert totals["attack_taken"] + totals["attack_missed"] == totals["attack_episodes"]
    assert totals["defence_taken"] + totals["defence_missed"] == totals["defence_episodes"]
    assert report["laps"][0]["deployment_j"] >= 0.0
    assert report["probability_semantics"] == "uncalibrated_action_selection_probability"


def test_qualifying_lap_proxy_is_bounded_by_delivered_additive_power() -> None:
    attainable, gain = bounded_additive_lap_time_proxy(100.0, 0.20, 0.50)

    assert attainable == 100.0 / 1.10
    assert gain == 100.0 - attainable


def test_p23_replay_keeps_reference_field_and_adds_independent_ego() -> None:
    ticks = (
        RaceFieldTick(0.0, (("1", 100.0), ("2", 90.0)), (("1", 20.0), ("2", 19.0)),
                      (("1", 0.5), ("2", 0.4)), (("1", 0.0), ("2", 0.0))),
        RaceFieldTick(0.25, (("1", 105.0), ("2", 94.75)), (("1", 20.0), ("2", 19.0)),
                      (("1", 0.5), ("2", 0.4)), (("1", 0.0), ("2", 0.0))),
        RaceFieldTick(0.5, (("1", 110.0), ("2", 99.5)), (("1", 20.0), ("2", 19.0)),
                      (("1", 0.5), ("2", 0.4)), (("1", 0.0), ("2", 0.0))),
    )
    reference_profiles = {"1": _profile("1"), "2": _profile("2")}

    report = run_p23_diagnostic(
        create_diagnostic_model(3), ticks, reference_profiles, _profile(), _prior(),
        P23ScenarioPrior(decision_hz=5.0, vehicle_mass_kg=800.0, maximum_brake_force_n=16_000.0),
    )

    assert report["starting_grid_position"] == 23
    assert report["reference_entries"] == 2
    assert report["ego_identity"] not in report["reference_identities"]
    assert 1 <= report["final_proxy_position"] <= 3
    assert report["field_input_hz"] == 4.0
    assert report["decision_hz"] == 5.0
    assert report["input_hold"] == "latest_source_sample"
    assert report["signed_gap_to_leader_s"] <= 0.0
    assert report["reference_mode"] == "ice_profile_simulation_from_source_controls"
    assert report["reference_policy_actions"] == 0
    assert report["reference_electric_deployment_j"] == 0.0


def test_p23_report_binds_major_source_events_to_nearest_policy_decision() -> None:
    ticks = (
        RaceFieldTick(0.0, (("1", 100.0),), (("1", 20.0),), (("1", 0.5),), (("1", 0.0),)),
        RaceFieldTick(0.25, (("1", 105.0),), (("1", 20.0),), (("1", 0.5),), (("1", 0.0),)),
        RaceFieldTick(0.5, (("1", 110.0),), (("1", 20.0),), (("1", 0.5),), (("1", 0.0),)),
    )
    event = {"time_s": 0.24, "label": "yellow", "detail": "Yellow", "source_row": 7}

    report = run_p23_diagnostic(
        create_diagnostic_model(3), ticks, {"1": _profile("1")}, _profile(), _prior(),
        P23ScenarioPrior(decision_hz=5.0, vehicle_mass_kg=800.0, maximum_brake_force_n=16_000.0),
        major_events=(event,),
    )

    bound = report["major_event_decisions"][0]
    assert bound["event"] == event
    assert bound["nearest_policy_decision"]["time_s"] == 0.2
    assert bound["decision_time_delta_s"] == -0.04


def test_major_race_events_are_source_bound_and_race_relative(tmp_path: Path) -> None:
    laps = pd.DataFrame({"LapStartTime": pd.to_timedelta([100.0, 101.0], unit="s")})
    track = pd.DataFrame({
        "source_row": [0, 1, 2, 3],
        "Time": pd.to_timedelta([99.0, 110.0, 120.0, 130.0], unit="s"),
        "Status": ["1", "2", "6", "7"],
        "Message": ["AllClear", "Yellow", "VSCDeployed", "VSCEnding"],
    })
    laps_path = tmp_path / "laps.parquet"
    track_path = tmp_path / "track_status.parquet"
    laps.to_parquet(laps_path, index=False)
    track.to_parquet(track_path, index=False)
    digest = lambda path: sha256(path.read_bytes()).hexdigest()
    acquisition = {
        "identity": {"event_name": "Test Grand Prix", "session_kind": "race"},
        "exports": {
            "laps": {"path": str(laps_path), "sha256": digest(laps_path)},
            "track_status": {"path": str(track_path), "sha256": digest(track_path)},
        },
    }
    acquisition_path = tmp_path / "acquisition.json"
    acquisition_path.write_text(json.dumps(acquisition))
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps({
        "acquisition_manifest": str(acquisition_path),
        "acquisition_manifest_sha256": digest(acquisition_path),
    }))

    events = load_major_race_events(binding_path, end_time_s=25.0)

    assert [event["label"] for event in events] == ["yellow", "vsc_deployed"]
    assert [event["time_s"] for event in events] == [10.0, 20.0]


def test_consolidation_ranks_profiles_and_extracts_profile_23_attack() -> None:
    reports = {
        "1": {
            "p23": {"final_proxy_position": 8, "final_progress_m": 1_000.0, "signed_gap_to_leader_m": -30.0,
                    "signed_gap_to_leader_s": -1.5, "gross_deployment_j": 2_000_000.0,
                    "gross_harvest_j": 1_000_000.0, "laps": [{"deployment_j": 300.0, "harvest_j": 50.0}]},
            "validation": {"gross_deployment_j": 100.0, "gross_harvest_j": 50.0,
                           "laps": [{"deployment_j": 100.0, "harvest_j": 50.0}]},
        },
        "23": {
            "p23": {"final_proxy_position": 6, "final_progress_m": 1_020.0, "signed_gap_to_leader_m": -10.0,
                    "signed_gap_to_leader_s": -0.5, "gross_deployment_j": 3_000_000.0,
                    "gross_harvest_j": 2_000_000.0, "laps": [{"deployment_j": 500.0, "harvest_j": 70.0}],
                    "first_attack": {"time_s": 4.2, "uncalibrated_action_probability": 0.7}},
            "validation": {"gross_deployment_j": 200.0, "gross_harvest_j": 70.0,
                           "laps": [{"deployment_j": 200.0, "harvest_j": 70.0}]},
        },
    }

    summary = consolidate_profile_reports(reports)

    assert [row["profile_entry"] for row in summary["profile_scenario_ranking"]] == ["23", "1"]
    assert summary["profile_23_first_attack"]["time_s"] == 4.2
    assert summary["medians"]["p23_gross_deployment_j"] == 2_500_000.0
    assert summary["medians"]["p23_signed_gap_to_leader_s"] == -1.0
    assert summary["medians"]["withheld_profile_gross_harvest_j"] == 60.0
    assert summary["lap_medians"]["p23_harvest_j"] == 60.0
