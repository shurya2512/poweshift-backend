# Phase 10 handoff

## Delivered scope

- A server-owned artifact registry accepts only relative, hashed checkpoint, weekend source, news,
  protected-target and run-manifest records.
- The compatibility gate binds schema, profile, energy, physics, rules, fixed pits, route and scenario.
- One resident recurrent policy loads through restricted state-dict deserialization and uses
  deterministic action selection. Late or nonfinite inference emits hold with zero deployment and
  discards candidate memory.
- The weekend runner accepts sealed observation rows or the stable Phase 8 rollout step shape when
  each row includes its source-bound observation time.
- Recommendations are flushed incrementally to JSONL. The completed file and report are hashed before
  a separate scorer can open the registered protected target.
- A spawned local worker uses bounded command and event queues and persists terminal failure state.
  The FastAPI control plane exposes run creation, status, pause/resume/stop, latest recommendation,
  final report and WebSocket replay.
- The duplex `/runs/{run_id}/live` endpoint accepts ordered `ObservationFrame` rows at 4 Hz and emits
  `LiveRecommendationFrame` rows at 5 Hz, marking decisions that hold the latest source input.
- Runtime report artifacts include ten qualifying sources and four complete P23 race sources. Their
  lap, event, action-probability and energy fields are frontend-ready JSON, but remain diagnostic.
  The combined index is `data/policy_phase8/runtime_inference_reports_v2/index.json`.

## Run after Phase 8

Register the completed checkpoint, one sealed weekend source, its protected target and the run
manifest in a registry JSON file. Then use:

```bash
uv run python -m poweshift_backend.runtime REGISTRY RUN_ID infer RUN_OUTPUT
uv run python -m poweshift_backend.runtime REGISTRY RUN_ID score RUN_OUTPUT EVALUATION_JSON
uv run python -m poweshift_backend.api REGISTRY OUTPUTS_ROOT
```

To expose the generated diagnostic report bundle to the local frontend, add:

```bash
--diagnostic-reports data/policy_phase8/runtime_inference_reports_v2
```

The API allows only the local frontend origins on port 3000. The frontend uses
`NEXT_PUBLIC_POWESHIFT_API_URL` and optionally `NEXT_PUBLIC_POWESHIFT_RUN_ID`; without a run ID it
shows report availability but does not claim a live recommendation.

The source must carry the exact Phase 8 schema and energy bundle plus fixed-pit, route and scenario
IDs. Its `observations` rows contain sequence, `observed_at_s`, values, feature mask, action mask and
deployment availability. A Phase 8 `steps` array is also accepted when each step adds
`observed_at_s`; time is never invented.

## Verification

The complete backend suite passes 421 tests with one existing non-contiguous `torch.searchsorted`
performance warning. Live tests cover strict sequence/cadence refusal, held input and protected-target
isolation. A sustained target-Mac timing run remains outstanding.

## Remaining gate

This is a retrospective inference scaffold, not a closed-loop physical runtime. It does not yet
advance the world, produce realised DeliveryRecord or restorable SimulationSnapshot artifacts,
separate world and actor into distinct processes, or demonstrate the 200 ms cycle on the target Mac.
The diagnostic Phase 8 checkpoints do not carry admitted physics and energy identities, so the live
registry correctly refuses them. These gaps prevent a complete Phase 10 runtime claim but do not
block registered end-to-end inference once an admitted checkpoint exists.
