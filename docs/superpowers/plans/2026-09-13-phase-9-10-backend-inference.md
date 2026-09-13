# Phase 9 and 10 Backend Inference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build chronological news/adaptation records and a registered, target-isolated backend inference path for validation and final-test weekends.

**Architecture:** Phase 9 prepares immutable zero-influence news context and training-only update manifests. Phase 10 loads the existing phase 8 schema and checkpoint contracts once, runs deterministic recurrent inference in a spawned worker, persists sequenced recommendations and exposes them through a local API. Protected outcomes are opened only by a separate scorer after inference is frozen.

**Tech Stack:** Python 3.11, Pydantic v2, PyTorch 2.8, FastAPI, Uvicorn, HTTPX, Beautiful Soup, multiprocessing spawn and pytest.

**Spec:** `docs/PHASE_9_PLAN.md`, `docs/PHASE_10_PLAN.md` and `docs/TRACKSHIFT_FULL_REVISED_ARCHITECTURE_v05.md`.

## Global Constraints

- Preserve the exact phase 8 schema, energy, profile, physics, rules, pit and scenario identities.
- Use only registered IDs at the API boundary; paths and URLs remain server-owned configuration.
- Validation and final-evaluation inputs never update weights or active profiles.
- Protected targets stay unopened until the inference artifact is complete and immutable.
- News has zero numerical influence until matched later evidence proves benefit.
- Comments and docstrings are one or two short plain-language lines.
- Do not run training or the complete suite concurrently with the active phase 8 process.
- Do not commit or push.

---

### Task 1: Chronological news and learning boundary

**Files:**
- Create: `src/poweshift_backend/contracts/news.py`
- Create: `src/poweshift_backend/news/capture.py`
- Create: `src/poweshift_backend/news/review.py`
- Create: `src/poweshift_backend/learning/chronology.py`
- Test: `tests/test_news_chronology.py`

**Interfaces:**
- Consumes: registered HTTPS source details, visible article text and completed-stint metadata.
- Produces: `ArticleSnapshot`, `NewsPrior`, `ProfileUpdateManifest` and `ModelPromotionReport`.

- [x] Write tests that fail because article capture, cutoff checks, partition refusal and zero-influence promotion records are missing.
- [x] Run `.venv/bin/pytest -q tests/test_news_chronology.py` and confirm missing imports cause the failure.
- [x] Add strict immutable contracts, bounded capture, review and chronology services.
- [x] Run `.venv/bin/pytest -q tests/test_news_chronology.py` and confirm it passes.

### Task 2: Weekend inference contracts and resident policy

**Files:**
- Create: `src/poweshift_backend/contracts/runtime.py`
- Create: `src/poweshift_backend/recommendations/frame.py`
- Create: `src/poweshift_backend/runtime/inference.py`
- Test: `tests/test_runtime_inference.py`

**Interfaces:**
- Consumes: `PolicySchema`, `PolicyCheckpointMetadata`, checkpoint path, observation rows and a monotonic deadline.
- Produces: `InferenceResult`, `RecommendationFrame` and accepted recurrent memory.

- [x] Write tests that fail because deterministic inference, fallback and compatibility-bound frames are missing.
- [x] Run `.venv/bin/pytest -q tests/test_runtime_inference.py` and confirm missing imports cause the failure.
- [x] Implement one-time restricted checkpoint loading, deterministic recurrent action selection and a hold fallback that does not advance memory.
- [x] Run `.venv/bin/pytest -q tests/test_runtime_inference.py` and confirm it passes.

### Task 3: Registered weekend runner and target firewall

**Files:**
- Create: `src/poweshift_backend/runtime/artifacts.py`
- Create: `src/poweshift_backend/runtime/weekend.py`
- Create: `src/poweshift_backend/evaluation/weekend.py`
- Test: `tests/test_weekend_inference.py`

**Interfaces:**
- Consumes: server-owned registry, phase 8-compatible checkpoint, validation or final-evaluation observation binding and protected target identity.
- Produces: immutable recommendation JSONL, run report and separately generated evaluation report.

- [x] Write tests that fail because identity validation, inference-only execution and separate scoring are missing.
- [x] Run `.venv/bin/pytest -q tests/test_weekend_inference.py` and confirm missing imports cause the failure.
- [x] Implement registered artifact resolution, canonical hash checks, inference output freezing and the separate scorer.
- [x] Run `.venv/bin/pytest -q tests/test_weekend_inference.py` and confirm it passes.

### Task 4: Spawned supervisor and local API

**Files:**
- Create: `src/poweshift_backend/runtime/supervisor.py`
- Create: `src/poweshift_backend/api/app.py`
- Create: `src/poweshift_backend/api/__main__.py`
- Create: `src/poweshift_backend/runtime/__main__.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/test_runtime_supervisor.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: registered run IDs and pause, resume or stop controls.
- Produces: run status, latest recommendation, read-only sequence stream and final report.

- [x] Write tests that fail because the supervisor and API routes are missing.
- [x] Run `.venv/bin/pytest -q tests/test_runtime_supervisor.py tests/test_api.py` and confirm missing imports cause the failure.
- [x] Add pinned web dependencies after official documentation review.
- [x] Implement bounded spawned workers, persistent run state, localhost API routes and WebSocket replay.
- [x] Run `.venv/bin/pytest -q tests/test_runtime_supervisor.py tests/test_api.py` and confirm they pass.

### Task 5: Documentation and proportional verification

**Files:**
- Modify: `docs/TRACKSHIFT_FULL_REVISED_ARCHITECTURE_v05.md`
- Modify: `docs/PARALLEL_POLICY_PLAN.md`
- Create: `docs/PHASE_9_HANDOFF.md`
- Create: `docs/PHASE_10_HANDOFF.md`

**Interfaces:**
- Consumes: measured focused checks and the actual delivered boundary.
- Produces: durable run commands, limitations and the exact post-training next action.

- [x] Update permanent docs so the implemented boundary and remaining evidence gaps are explicit.
- [x] Run all new phase 9 and 10 tests together.
- [x] Run the directly affected phase 7 and 8 contract/checkpoint tests.
- [x] The complete suite was initially deferred while training was active, then passed after the run completed.
- [x] Run `git diff --check` and Python compilation.
- [x] Read the whole diff and record omitted live-data and sustained-runtime checks.
