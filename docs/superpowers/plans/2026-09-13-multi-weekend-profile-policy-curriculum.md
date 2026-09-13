# Multi-Weekend Profile Policy Curriculum Implementation Plan

> **Execution:** Use `superpowers:executing-plans` inline. Do not delegate, commit or push.

**Goal:** Continue all 22 Japan-trained profile policies through the remaining training weekends, using free practice for energy learning and races for energy plus tactics, then produce a fixed-field P23 comparison for every ego profile.

**Architecture:** Export immutable practice controls, prepare route-bound 4 Hz race artifacts, and run sessions in date order. Practice masks tactical actions but retains continuous deployment and harvesting. Each race withholds its final 20% of complete laps. A final additional P23 ego runs one profile policy at a time against the same 22 policy-free, electric-free fitted references.

**Tech stack:** Python 3.11, FastF1 3.8-compatible session loading, pandas/pyarrow artifacts, PyTorch PPO, pytest, immutable JSON reports.

**Durable decisions:** `docs/PHASE_8_PLAN.md` and `docs/TRACKSHIFT_FULL_REVISED_ARCHITECTURE_v05.md`

## Constraints

- Use only Miami, Canada, Monaco, Barcelona, Austria and Britain after Japan.
- Keep Belgium, Hungary, Netherlands and Italy unopened.
- Use FP1/FP2/FP3 only; never sprint qualifying.
- Carry model and optimizer across sessions, but reset battery and recurrent state at each session.
- Carry battery and recurrent state across laps within a session.
- Use native 4 Hz simulation and a held latest state for 5 Hz decisions.
- Preserve the 20% additive-electric prior, 5 MJ store, 5 MJ/lap fallback harvest cap, 0.95 motor efficiency and 0.8 harvest efficiency.
- Report uncalibrated action-selection probability, never pass-success probability.
- Label all outputs diagnostic-only and `physics_admission=false`.
- Keep comments and docstrings to one or two short lines.

---

### Task 1: Practice tactical firewall

**Files:**
- Modify: `tests/test_policy_diagnostic.py`
- Modify: `src/poweshift_backend/policy/diagnostic.py`

- [x] Add a failing test proving a non-race trace can deploy/harvest energy while every tactical decision remains `HOLD`.
- [x] Run the focused test and confirm the current action mask exposes `ATTACK`.
- [x] Separate electrical availability from tactical availability in the mask.
- [x] Run `tests/test_policy_diagnostic.py`.

### Task 2: Immutable practice exports and 4 Hz energy traces

**Files:**
- Create: `tests/test_practice_export.py`
- Create: `src/poweshift_backend/data/practice_export.py`
- Modify: `tests/test_policy_curriculum.py`
- Modify: `src/poweshift_backend/policy/curriculum.py`

- [x] Add failing tests for audited training-only FP selection, immutable source hashes, sprint-session refusal and causal 4 Hz resampling.
- [x] Implement a practice exporter following the existing isolated-cache exporter pattern and export lap/car tables plus a source-bound manifest.
- [x] Implement `load_practice_traces` from the exported tables with past-only 4 Hz sampling and explicit missing coverage.
- [x] Run the practice exporter and curriculum tests.

### Task 3: Later-race route and artifact preparation

**Files:**
- Create: `tests/test_training_event_prep.py`
- Create: `src/poweshift_backend/representation/training_event_prep.py`
- Create: `data/policy_phase8/prepare_later_training_weekends.py`

- [x] Add failing tests for deterministic route-lap selection, verified training-partition enforcement and immutable reruns.
- [x] Select an accurate complete lap deterministically from each verified race export and build a closed route using the established route thresholds.
- [x] Build the route-bound 4 Hz race artifact and bind its hashes to the acquisition manifest and source audit.
- [x] Prepare Miami, Canada, Monaco, Barcelona, Austria and Britain serially.
- [x] Inspect every source binding for 4 Hz cadence, training partition and recorded identity coverage; missing complete fields remain unavailable.

### Task 4: Chronological multi-weekend curriculum

**Files:**
- Create: `tests/test_policy_weekend_curriculum.py`
- Create: `src/poweshift_backend/policy/weekend_curriculum.py`
- Create: `data/policy_phase8/run_multi_weekend_profile_curriculum.py`

- [x] Add failing tests for strict event/session order, per-race disjoint 80/20 splits, state reset boundaries, checkpoint provenance and resume refusal on hash mismatch.
- [x] Define a frozen curriculum manifest containing session identities, source hashes, split trace IDs and the Japan checkpoint hash for each profile.
- [x] Continue each profile's policy and optimizer from its Japan checkpoint with practice energy-only updates before race updates.
- [x] Reset recurrent/battery state at session boundaries while retaining learned weights and long-horizon state within a session.
- [x] Save per-event checkpoints and validation reports atomically; resume only from an exact matching manifest.
- [x] After Britain, run 22 P23 scenarios against identical fixed references and consolidate proxy ranks, gaps, lap/episode evidence and energy distributions.
- [x] Run the focused policy tests.

### Task 5: Execute, verify and document measured results

**Files:**
- Create: `data/policy_phase8/multi_weekend_all_profiles_v1/`
- Modify: `docs/PHASE_8_PLAN.md`
- Modify: `docs/TRACKSHIFT_FULL_REVISED_ARCHITECTURE_v05.md`
- Delete: `docs/superpowers/specs/2026-09-13-multi-weekend-profile-policy-curriculum-design.md`

- [x] Export all audited free-practice sessions serially and record missing entry/lap coverage without inventing data.
- [x] Run all 22 curricula serially through Britain.
- [x] Verify optimizer trace IDs exclude withheld laps, energy ledgers reconcile and every admitted P23 scenario uses 22 fixed references plus one independent ego.
- [x] Produce lap-by-lap and attack/defence reports including path, probability, electrical power, deployment, harvest, battery, proxy position and final gap.
- [x] Run `UV_CACHE_DIR=/tmp/trackshift-uv-cache uv run pytest -q`; 421 tests pass with one existing performance warning.
- [x] Update durable docs with measured coverage/results and remaining physical-admission blockers, then remove the temporary design brief.

### Task 6: Protected Madring test and frontend live path

**Files:**
- Create: `src/poweshift_backend/runtime/live.py`
- Modify: `src/poweshift_backend/contracts/runtime.py`
- Modify: `src/poweshift_backend/runtime/supervisor.py`
- Modify: `src/poweshift_backend/api/app.py`
- Create: `data/policy_phase8/acquire_madring_qualifying_test.py`
- Create: `data/policy_phase8/run_madring_qualifying_validation.py`
- Create: `tests/test_live_inference.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_policy_diagnostic.py`

- [x] Add failing tests for held 4 Hz inputs, 5 Hz decisions and protected-trace optimizer refusal.
- [x] Implement the registered-run live WebSocket without opening protected targets.
- [x] Acquire and seal the Sep 12 Madring qualifying source as final-evaluation-only data.
- [x] Evaluate all available promoted profiles with zero optimizer updates after curriculum training.
- [x] Record missing qualifying identity/lap coverage and the no-race-data limitation.

### Task 7: Runtime inference reports

**Files:**
- Create: `data/policy_phase8/run_qualifying_runtime_reports.py`
- Create: `data/policy_phase8/run_race_runtime_reports.py`
- Modify: `src/poweshift_backend/policy/race_validation.py`
- Modify: `tests/test_policy_race_validation.py`

- [x] Produce per-track, per-profile qualifying lap reports with observed time, diagnostic time-gain fields, action probability, power and energy.
- [x] Produce full-race P23 reports with lap rows, every attack/defence opportunity, action episodes, final proxy position, gaps and energy.
- [x] Bind yellow, safety-car, red and VSC events to their nearest 5 Hz policy decision using verified source rows.
- [x] Consolidate means, medians and same-field profile rankings without treating them as physical results.
- [x] Mark Canada and Monaco race reports unavailable because neither source has a complete 22-reference tick.
