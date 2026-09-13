"""Spawned local supervisor for registered weekend inference."""

from dataclasses import dataclass
import json
import multiprocessing
from pathlib import Path
from queue import Empty, Full
import time
from typing import Any

from poweshift_backend.contracts.runtime import RecommendationFrame, RunStatus, WeekendRunManifest, WeekendRunReport
from poweshift_backend.runtime.artifacts import ArtifactRegistry
from poweshift_backend.runtime.live import LivePolicySession
from poweshift_backend.runtime.weekend import run_weekend_inference


def _run_worker(
    registry_path: str,
    run_id: str,
    output_path: str,
    commands: Any,
    events: Any,
) -> None:
    paused = False
    output = Path(output_path)

    def finish(status: str, recommendation_count: int, error: str | None) -> None:
        payload = {"status": status, "recommendation_count": recommendation_count, "error": error}
        output.mkdir(parents=True, exist_ok=True)
        (output / "status.json").write_text(json.dumps({"run_id": run_id, **payload}, sort_keys=True) + "\n")
        events.put(payload)

    def before_sequence(_sequence: int) -> bool:
        nonlocal paused
        while True:
            try:
                command = commands.get_nowait()
            except Empty:
                if paused:
                    time.sleep(0.01)
                    continue
                return True
            if command == "stop":
                return False
            if command == "pause":
                paused = True
            elif command == "resume":
                paused = False

    try:
        registry = ArtifactRegistry.load(Path(registry_path))
        manifest_path = registry.resolve(run_id, "run_manifest")
        manifest = WeekendRunManifest.model_validate_json(manifest_path.read_text())
        report = run_weekend_inference(
            manifest,
            registry,
            output,
            before_sequence=before_sequence,
        )
        finish(report.status, report.recommendation_count, None)
    except Exception as error:
        finish("failed", 0, str(error))


@dataclass
class _RunHandle:
    process: Any
    commands: Any
    events: Any
    status: RunStatus


class RunSupervisor:
    """Own bounded spawned workers and expose their persisted results."""

    def __init__(self, registry_path: Path, outputs_root: Path) -> None:
        self.registry_path = registry_path.resolve()
        self.outputs_root = outputs_root.resolve()
        self.registry = ArtifactRegistry.load(self.registry_path)
        self.context = multiprocessing.get_context("spawn")
        self.runs: dict[str, _RunHandle] = {}
        self.live_sessions: dict[str, LivePolicySession] = {}

    def live(self, run_id: str) -> LivePolicySession:
        """Return one resident live session for a registered protected run."""
        if run_id not in self.live_sessions:
            self.live_sessions[run_id] = LivePolicySession.from_registered_run(self.registry, run_id)
        return self.live_sessions[run_id]

    def start(self, run_id: str) -> RunStatus:
        """Start one registered run in a spawned worker."""
        if run_id in self.runs:
            raise ValueError("run is already known to this supervisor")
        manifest_path = self.registry.resolve(run_id, "run_manifest")
        manifest = WeekendRunManifest.model_validate_json(manifest_path.read_text())
        if manifest.run_id != run_id:
            raise ValueError("registered manifest does not match the requested run ID")
        output = self.outputs_root / run_id
        if output.exists():
            raise FileExistsError(f"run output already exists: {output}")
        self.outputs_root.mkdir(parents=True, exist_ok=True)
        commands = self.context.Queue(maxsize=8)
        events = self.context.Queue(maxsize=8)
        process = self.context.Process(
            target=_run_worker,
            args=(str(self.registry_path), run_id, str(output), commands, events),
            daemon=True,
        )
        status = RunStatus(run_id=run_id, status="running", recommendation_count=0)
        self.runs[run_id] = _RunHandle(process, commands, events, status)
        process.start()
        return status

    def status(self, run_id: str) -> RunStatus:
        """Return the latest state delivered by the worker."""
        handle = self._handle(run_id)
        while True:
            try:
                event = handle.events.get_nowait()
            except Empty:
                break
            handle.status = RunStatus(run_id=run_id, **event)
        if not handle.process.is_alive() and handle.status.status in {"running", "paused"}:
            handle.process.join(timeout=0.1)
            if handle.process.exitcode not in {0, None}:
                handle.status = RunStatus(
                    run_id=run_id,
                    status="failed",
                    recommendation_count=handle.status.recommendation_count,
                    error=f"worker exited with code {handle.process.exitcode}",
                )
        return handle.status

    def control(self, run_id: str, command: str) -> RunStatus:
        """Send pause, resume or stop to a running worker."""
        if command not in {"pause", "resume", "stop"}:
            raise ValueError("run control must be pause, resume or stop")
        handle = self._handle(run_id)
        if not handle.process.is_alive():
            return self.status(run_id)
        handle.commands.put_nowait(command)
        if command in {"pause", "resume"}:
            handle.status = handle.status.model_copy(update={"status": "paused" if command == "pause" else "running"})
        return handle.status

    def latest(self, run_id: str) -> RecommendationFrame:
        """Read the newest persisted recommendation."""
        frames = self.stream(run_id, -1)
        if not frames:
            raise LookupError("run has no recommendation yet")
        return frames[-1]

    def stream(self, run_id: str, after_sequence: int) -> tuple[RecommendationFrame, ...]:
        """Read persisted frames after one sequence position."""
        self._handle(run_id)
        path = self.outputs_root / run_id / "recommendations.jsonl"
        if not path.is_file():
            return ()
        return tuple(
            frame
            for line in path.read_text().splitlines()
            if line and (frame := RecommendationFrame.model_validate_json(line)).sequence > after_sequence
        )

    def report(self, run_id: str) -> WeekendRunReport:
        """Read a completed or stopped immutable run report."""
        self._handle(run_id)
        path = self.outputs_root / run_id / "report.json"
        if not path.is_file():
            raise LookupError("run report is not ready")
        return WeekendRunReport.model_validate_json(path.read_text())

    def shutdown(self) -> None:
        """Stop and join workers owned by this supervisor."""
        for handle in self.runs.values():
            if handle.process.is_alive():
                try:
                    handle.commands.put_nowait("stop")
                except Full:
                    pass
                handle.process.join(timeout=2.0)
                if handle.process.is_alive():
                    handle.process.terminate()
                    handle.process.join(timeout=1.0)

    def _handle(self, run_id: str) -> _RunHandle:
        try:
            return self.runs[run_id]
        except KeyError as error:
            raise KeyError(f"run is not known: {run_id}") from error
