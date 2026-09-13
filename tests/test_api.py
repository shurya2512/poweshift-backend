import time
import json

from fastapi.testclient import TestClient

from poweshift_backend.api.app import create_app
from poweshift_backend.runtime.supervisor import RunSupervisor
from test_runtime_supervisor import registered_run


def test_api_starts_and_streams_a_registered_run(tmp_path) -> None:
    registry_path, outputs = registered_run(tmp_path)
    supervisor = RunSupervisor(registry_path, outputs)
    app = create_app(supervisor)

    with TestClient(app) as client:
        response = client.post("/runs", json={"run_id": "selection-run"})
        assert response.status_code == 202
        deadline = time.monotonic() + 10.0
        payload = client.get("/runs/selection-run").json()
        while payload["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.01)
            payload = client.get("/runs/selection-run").json()

        assert payload["status"] == "completed"
        recommendation = client.get("/runs/selection-run/recommendation")
        assert recommendation.status_code == 200
        assert recommendation.json()["sequence"] == 1
        report = client.get("/runs/selection-run/report")
        assert report.status_code == 200
        assert report.json()["target_id"] == "protected-target"
        with client.websocket_connect("/runs/selection-run/stream?after_sequence=-1") as stream:
            assert stream.receive_json()["sequence"] == 0
            assert stream.receive_json()["sequence"] == 1


def test_api_accepts_four_hz_input_and_streams_five_hz_decisions(tmp_path) -> None:
    registry_path, outputs = registered_run(tmp_path)
    supervisor = RunSupervisor(registry_path, outputs)
    app = create_app(supervisor)

    with TestClient(app) as client:
        with client.websocket_connect("/runs/selection-run/live") as stream:
            stream.send_json({
                "sequence": 0,
                "observed_at_s": 0.0,
                "values": [20.0, 4_000_000.0],
                "feature_mask": [True, True],
                "action_mask": [True, True, True, True],
                "deployment_available": True,
                "news_prior_ids": [],
            })
            first = stream.receive_json()

        assert first["source_sequence"] == 0
        assert first["decision_sequence"] == 0
        assert first["input_hz"] == 4.0
        assert first["decision_hz"] == 5.0
        assert first["recommendation"]["retrospective"] is True


def test_api_serves_registered_diagnostic_reports_to_local_frontend(tmp_path) -> None:
    registry_path, outputs = registered_run(tmp_path)
    reports = tmp_path / "reports"
    (reports / "race").mkdir(parents=True)
    (reports / "index.json").write_text(json.dumps({"status": "diagnostic_only", "race_index": "race/index.json"}))
    (reports / "race/index.json").write_text(json.dumps({"tracks": [{"event_name": "British Grand Prix"}]}))
    app = create_app(RunSupervisor(registry_path, outputs), diagnostic_report_root=reports)

    with TestClient(app) as client:
        index = client.get("/diagnostics/reports")
        nested = client.get("/diagnostics/reports/race/index.json")
        preflight = client.options(
            "/runs",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
        )

    assert index.json()["status"] == "diagnostic_only"
    assert nested.json()["tracks"][0]["event_name"] == "British Grand Prix"
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
