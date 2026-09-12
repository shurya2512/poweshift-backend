# Phase 3 handoff

## Delivered scope

Phase 3 admits pinned preparation evidence, recovers the source-linked reference route, and adds a
shared effective mechanics path. The numerical baseline fits propulsion, resistance, braking and
grip separately for each entry using training chunks. It writes immutable settings, fit and
held-out evidence artifacts outside the Phase 2 evidence tree.

Known-input replay uses recorded controls inside each scored chunk and holds its last recorded
demand across an admitted inter-chunk interval. Forecast mode holds one declared prefix demand
across chunks and does not read future target controls. Unverified links remain separate anchors.

## Commands and checks

The final suite reported 161 passing tests. The bounded real-data command for entry 1 completed in 9.03 seconds with four held-out chunks from one moving run and no replay exclusions. It reported 588 braking, 153 coast and 2,111 propulsion observations. Their speed MAEs were 8.033, 5.953 and 5.006 m/s respectively. These errors are weak effective-baseline results, not a predictive-performance claim.

Run a bounded per-entry artifact build with:

```sh
uv run python -m poweshift_backend.reconstruction \
  --entry 1 --sample-budget 24 --heldout-chunk-budget 4 \
  --output-dir data/reconstruction_phase3/baseline_entry_1_next
```

The command reads `data/preparation_verified_698aaed/phase2_evidence_manifest.json` and `data/reconstruction_phase3/phase3_admission.json`. Its output directory must be new because the artifact writer does not overwrite an existing result. The measured run used `data/reconstruction_phase3/baseline_entry_1_continuity`.

Context7 was unavailable; API checks used official SciPy and Pydantic documentation plus existing project usage.

## Frozen decisions and limits

The optimizer is bounded SciPy trust-region least squares with a fixed 80-function-evaluation cap. Its upper bounds are calculated from that entry's admitted training acceleration and speed scales; the recipe and numbers are recorded in `settings.json`. Mass, fuel, axle dimensions, CG height, brake share, fuel policy, zero rolling/downforce terms and numerical settings are illustrative assumptions, not measured factory values.

The 0.04 s RK4 step and axle-solve settings are initial numerical settings, not convergence-selected values. The evidence report includes a zero-control numerical fixture using held-out initial state and timing, an adaptive `solve_ivp` comparison, and a half-step difference whenever enough feasible samples exist. This fixture checks integration only; it does not validate a held-out trajectory.

## Limitations and next decision

This is an effective, assumption-conditioned entry baseline. It does not identify factory maps, tyre state, energy actuation, grade, aerodynamic downforce, cornering behaviour, rank, strategy or full-lap performance. Package observations lack aligned X/Y coordinates, so the recovered reference route cannot provide their curvature. Held-out counts are bounded chunk samples and must not be read as complete-session coverage.

The implementation work is split across input admission commit `3130d7c`, shared mechanics commit
`a285821`, and fitting commit `d431b4a`. The final replay, evidence and handoff commit records the
verified state carry, bounded moving-run evaluation and the result above.
