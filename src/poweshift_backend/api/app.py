"""FastAPI routes over the spawned inference supervisor."""

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from pydantic import Field

from poweshift_backend.contracts.acquisition import StrictModel
from poweshift_backend.contracts.runtime import ObservationFrame
from poweshift_backend.runtime.supervisor import RunSupervisor


class RunStart(StrictModel):
    """Start one server-registered run."""

    run_id: str = Field(min_length=1)


class RunControl(StrictModel):
    """Bounded command accepted by a run worker."""

    command: Literal["pause", "resume", "stop"]


def _live_observation(payload: dict) -> ObservationFrame:
    values = dict(payload)
    for name in ("values", "feature_mask", "action_mask", "news_prior_ids"):
        values[name] = tuple(values.get(name, ()))
    return ObservationFrame.model_validate(values)


def create_app(
    supervisor: RunSupervisor,
    diagnostic_report_root: Path | None = None,
) -> FastAPI:
    """Create the local API around one supervisor."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        supervisor.shutdown()

    app = FastAPI(title="Poweshift Backend", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    def diagnostic_report(path: str) -> dict:
        if diagnostic_report_root is None:
            raise HTTPException(status_code=404, detail="diagnostic reports are not configured")
        root = diagnostic_report_root.resolve()
        candidate = (root / path).resolve()
        if candidate.suffix != ".json" or not candidate.is_relative_to(root) or not candidate.is_file():
            raise HTTPException(status_code=404, detail="diagnostic report is not registered")
        return json.loads(candidate.read_text())

    @app.get("/diagnostics/reports")
    def get_diagnostic_report_index():
        return diagnostic_report("index.json")

    @app.get("/diagnostics/reports/{report_path:path}")
    def get_diagnostic_report(report_path: str):
        return diagnostic_report(report_path)

    @app.post("/runs", status_code=202)
    def start_run(request: RunStart):
        try:
            return supervisor.start(request.run_id)
        except (KeyError, FileNotFoundError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, FileExistsError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        try:
            return supervisor.status(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/runs/{run_id}/control")
    def control_run(run_id: str, request: RunControl):
        try:
            return supervisor.control(run_id, request.command)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/runs/{run_id}/recommendation")
    def get_recommendation(run_id: str):
        try:
            return supervisor.latest(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except LookupError as error:
            raise HTTPException(status_code=425, detail=str(error)) from error

    @app.get("/runs/{run_id}/report")
    def get_report(run_id: str):
        try:
            return supervisor.report(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except LookupError as error:
            raise HTTPException(status_code=425, detail=str(error)) from error

    @app.websocket("/runs/{run_id}/stream")
    async def stream_run(websocket: WebSocket, run_id: str, after_sequence: int = -1, speed: float = 1.0):
        await websocket.accept()
        speed = min(50.0, max(1.0, speed))
        sequence = after_sequence
        while True:
            try:
                frames = supervisor.stream(run_id, sequence)
                status = supervisor.status(run_id)
            except KeyError:
                await websocket.close(code=1008, reason="run is not known")
                return
            for frame in frames:
                await websocket.send_json(frame.model_dump(mode="json"))
                sequence = frame.sequence
            if status.status in {"completed", "stopped", "failed"}:
                await websocket.close(code=1000)
                return
            await asyncio.sleep(0.02 / speed)

    @app.websocket("/runs/{run_id}/live")
    async def live_run(websocket: WebSocket, run_id: str, speed: float = 1.0):
        await websocket.accept()
        speed = min(50.0, max(1.0, speed))
        period = 0.2 / speed
        try:
            session = supervisor.live(run_id)
        except (KeyError, FileNotFoundError, ValueError) as error:
            await websocket.close(code=1008, reason=str(error))
            return
        loop = asyncio.get_running_loop()
        receive = asyncio.create_task(websocket.receive_json())
        next_decision: float | None = None
        try:
            while True:
                if next_decision is None:
                    payload = await receive
                    session.ingest(_live_observation(payload))
                    receive = asyncio.create_task(websocket.receive_json())
                    next_decision = loop.time() + period
                    continue
                timeout = max(0.0, next_decision - loop.time())
                done, _ = await asyncio.wait((receive,), timeout=timeout)
                if receive in done:
                    payload = receive.result()
                    session.ingest(_live_observation(payload))
                    receive = asyncio.create_task(websocket.receive_json())
                    continue
                await websocket.send_json(session.decide().model_dump(mode="json"))
                next_decision += period
        except WebSocketDisconnect:
            return
        except (LookupError, ValidationError, ValueError) as error:
            await websocket.close(code=1008, reason=str(error))
        finally:
            if not receive.done():
                receive.cancel()

    return app
