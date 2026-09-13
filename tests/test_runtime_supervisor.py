from hashlib import sha256
import json
from pathlib import Path
import time

from test_weekend_inference import _write_inputs

from poweshift_backend.runtime.supervisor import RunSupervisor


def registered_run(tmp_path: Path) -> tuple[Path, Path]:
    _registry, manifest, root = _write_inputs(tmp_path)
    manifest_path = root / "selection-run.json"
    manifest_path.write_text(manifest.model_dump_json())
    registry_path = root / "registry.json"
    payload = json.loads(registry_path.read_text())
    payload["artifacts"][manifest.run_id] = {
        "kind": "run_manifest",
        "path": manifest_path.name,
        "sha256": sha256(manifest_path.read_bytes()).hexdigest(),
    }
    registry_path.write_text(json.dumps(payload, sort_keys=True))
    return registry_path, root / "runs"


def test_spawned_supervisor_runs_one_registered_weekend(tmp_path: Path) -> None:
    registry_path, outputs = registered_run(tmp_path)
    supervisor = RunSupervisor(registry_path, outputs)
    try:
        started = supervisor.start("selection-run")
        assert started.status in {"running", "completed"}
        deadline = time.monotonic() + 10.0
        status = supervisor.status("selection-run")
        while status.status == "running" and time.monotonic() < deadline:
            time.sleep(0.01)
            status = supervisor.status("selection-run")

        assert status.status == "completed"
        assert status.recommendation_count == 2
        assert supervisor.latest("selection-run").sequence == 1
        assert supervisor.report("selection-run").target_id == "protected-target"
    finally:
        supervisor.shutdown()


def test_spawned_supervisor_persists_a_worker_failure(tmp_path: Path) -> None:
    registry_path, outputs = registered_run(tmp_path)
    (tmp_path / "selection-source.json").write_text("{}")
    supervisor = RunSupervisor(registry_path, outputs)
    try:
        supervisor.start("selection-run")
        deadline = time.monotonic() + 10.0
        status = supervisor.status("selection-run")
        while status.status == "running" and time.monotonic() < deadline:
            time.sleep(0.01)
            status = supervisor.status("selection-run")

        assert status.status == "failed"
        persisted = json.loads((outputs / "selection-run" / "status.json").read_text())
        assert persisted["status"] == "failed"
        assert "hash differs" in persisted["error"]
    finally:
        supervisor.shutdown()
