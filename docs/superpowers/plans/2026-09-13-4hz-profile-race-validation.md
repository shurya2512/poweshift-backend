# 4 Hz Profile Race Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train isolated race policies for all 22 promoted profiles at native 4 Hz and produce withheld lap plus independently controlled grid-P23 diagnostic reports.

**Architecture:** Build native 4 Hz lap and control streams from the existing Japan race artifact with past-only control joins. Each profile starts from the same qualifying checkpoint, carries recurrent and energy state through its own chronological race, and is frozen before validation. A diagnostic N+1 simulation advances the 22 fitted ICE references without policy or electrical deployment, then holds their latest 4 Hz state for the independent ego's 5 Hz policy tick.

**Tech Stack:** Python 3.11, PyTorch, immutable JSON reports, restricted state-dict checkpoints, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-4hz-profile-race-validation-design.md`

## Global Constraints

- Use native 4 Hz observations and past-only control joins.
- Start each profile policy from the same post-qualifying checkpoint.
- Keep validation laps out of optimizer updates.
- Carry recurrent and battery state within a profile and reset them between profiles.
- Keep the 20% additive-electric prior, 5 MJ store and 5 MJ per-lap harvest cap.
- Actor probability is uncalibrated action-selection probability, never pass-success probability.
- P23 is an additional independent ego behind all 22 reference entries.
- P23 results are diagnostic proxy ranks and gaps, not physically validated outcomes.
- No code comment or docstring exceeds two short lines.
- Do not commit or push.

---

### Task 1: Native 4 Hz race inputs and chronological splits

**Files:**
- Modify: `src/poweshift_backend/policy/curriculum.py`
- Modify: `tests/test_policy_curriculum.py`

**Interfaces:**
- Produces: `RaceFieldTick(time_s, progress_by_entry, speed_by_entry)`.
- Produces: `NativeRaceData(traces_by_entry, field_ticks, route_length_m, observation_hz)`.
- Produces: `load_native_race_data(batch_path, report_path, entries) -> NativeRaceData`.
- Produces: `split_race_traces(traces, training_fraction=0.8) -> (training, validation)`.

- [x] **Step 1: Write the failing native-cadence test**

```python
def test_native_race_loader_uses_four_hz_and_past_controls(tmp_path):
    data = load_native_race_data(batch_path, report_path, ("1",))
    trace = data.traces_by_entry["1"][0]
    assert trace.step_s == 0.25
    assert trace.sample_time_s[:3] == (0.0, 0.25, 0.5)
    assert trace.throttle[:3] == (0.1, 0.1, 0.4)
```

- [x] **Step 2: Run the focused test and verify the loader is missing**

Run: `UV_CACHE_DIR=/tmp/trackshift-uv-cache uv run pytest tests/test_policy_curriculum.py::test_native_race_loader_uses_four_hz_and_past_controls -q`

Expected: FAIL because `load_native_race_data` is unavailable.

- [x] **Step 3: Implement native stream contracts and loading**

```python
@dataclass(frozen=True)
class RaceFieldTick:
    time_s: float
    progress_by_entry: tuple[tuple[str, float], ...]
    speed_by_entry: tuple[tuple[str, float], ...]

@dataclass(frozen=True)
class NativeRaceData:
    traces_by_entry: dict[str, tuple[DiagnosticTrace, ...]]
    field_ticks: tuple[RaceFieldTick, ...]
    route_length_m: float
    observation_hz: float
```

Use the latest control timestamp not later than each observation timestamp. Deduplicate shared 30-second window boundaries, preserve session time, progress and observed position, and refuse a cadence other than 4 Hz.

- [x] **Step 4: Write the failing split-firewall test**

```python
def test_race_split_is_chronological_and_disjoint():
    training, validation = split_race_traces(traces, 0.8)
    assert [x.trace_id for x in training] == ["lap-1", "lap-2", "lap-3", "lap-4"]
    assert [x.trace_id for x in validation] == ["lap-5"]
```

- [x] **Step 5: Implement and verify the split**

Run: `UV_CACHE_DIR=/tmp/trackshift-uv-cache uv run pytest tests/test_policy_curriculum.py -q`

Expected: PASS.

---

### Task 2: Long-horizon recurrent training and deterministic decisions

**Files:**
- Modify: `src/poweshift_backend/policy/diagnostic.py`
- Modify: `tests/test_policy_diagnostic.py`

**Interfaces:**
- Produces: `DiagnosticDecision` with time, lap, manoeuvre, action probability, deployment, power, energy, battery, gaps and opportunity fields.
- Extends: race training and evaluation with `carry_hidden_across_updates: bool`.
- Produces: deterministic trace evaluation returning final energy, final hidden state, metrics and decisions.

- [x] **Step 1: Write the failing hidden-carry test**

```python
def test_race_training_carries_hidden_state_between_laps(monkeypatch):
    report = run_diagnostic_updates(
        traces, profiles, prior, 2, 4,
        carry_energy_across_updates=True,
        carry_hidden_across_updates=True,
    )
    assert report["recurrent_state_carried"] is True
```

- [x] **Step 2: Verify the test fails for the missing argument**

Run: `UV_CACHE_DIR=/tmp/trackshift-uv-cache uv run pytest tests/test_policy_diagnostic.py::test_race_training_carries_hidden_state_between_laps -q`

Expected: FAIL because the carry argument is unavailable.

- [x] **Step 3: Carry detached hidden state through lap fragments**

Initialise hidden once per profile, pass it into each rollout and retain the detached final hidden state. Existing callers continue to reset hidden by default.

- [x] **Step 4: Write failing deterministic-decision tests**

```python
def test_deterministic_validation_records_action_probability_and_energy():
    result = evaluate_diagnostic_trace(model, trace, profile, prior)
    decision = result.decisions[0]
    assert decision.manoeuvre in (Manoeuvre.HOLD, Manoeuvre.ATTACK, Manoeuvre.DEFEND)
    assert 0.0 <= decision.action_probability <= 1.0
    assert decision.deployment_j >= 0.0
    assert decision.harvest_j >= 0.0
```

- [x] **Step 5: Implement deterministic selection and evidence**

Select the highest-probability permitted manoeuvre and the conditional Beta mean. Record the normalized categorical probability as `action_probability`; do not create any pass-success field.

- [x] **Step 6: Run diagnostic tests**

Run: `UV_CACHE_DIR=/tmp/trackshift-uv-cache uv run pytest tests/test_policy_diagnostic.py -q`

Expected: PASS.

---

### Task 3: Lap, encounter and grid-P23 diagnostic reports

**Files:**
- Create: `src/poweshift_backend/policy/race_validation.py`
- Create: `tests/test_policy_race_validation.py`

**Interfaces:**
- Produces: `validate_profile_policy(model, traces, profile, prior) -> dict[str, object]`.
- Produces: `run_p23_diagnostic(model, field_ticks, profile, prior, scenario) -> dict[str, object]`.
- Produces: `consolidate_profile_reports(reports) -> dict[str, object]`.

- [x] **Step 1: Write failing lap and encounter accounting tests**

```python
def test_validation_accounts_for_every_attack_opportunity():
    report = validate_profile_policy(model, traces, profile, prior)
    totals = report["opportunity_totals"]
    assert totals["attack_taken"] + totals["attack_missed"] == totals["attack_episodes"]
    assert report["laps"][0]["deployment_j"] >= 0.0
```

- [x] **Step 2: Verify the report module is missing**

Run: `UV_CACHE_DIR=/tmp/trackshift-uv-cache uv run pytest tests/test_policy_race_validation.py -q`

Expected: FAIL during import.

- [x] **Step 3: Implement deterministic lap and episode aggregation**

Group consecutive opportunity/threat ticks without discarding counts. Every episode records start/end time, lap, kind, selected paths, maximum action probability, requested/delivered deployment, power, energy and battery change.

- [x] **Step 4: Write failing P23 identity and rank tests**

```python
def test_p23_replay_keeps_reference_field_and_adds_independent_ego():
    report = run_p23_diagnostic(model, field_ticks, profile, prior, scenario)
    assert report["starting_grid_position"] == 23
    assert report["reference_entries"] == 22
    assert report["ego_identity"] not in report["reference_identities"]
    assert 1 <= report["final_proxy_position"] <= 23
```

- [x] **Step 5: Implement the causal 5 Hz P23 diagnostic**

Advance the 22 reference profiles from past-only source controls at 4 Hz with zero policy actions and zero electric deployment. Hold that simulated field state at each 0.2-second ego decision tick. Use a declared current-field speed controller for ego throttle/brake, fitted force/resistance parameters for longitudinal advance and policy output for ego manoeuvre/electric deployment.

- [x] **Step 6: Write and implement consolidation tests**

Recompute final proxy rankings, signed gaps, energy totals, profile medians and field medians from the individual reports. Extract profile 23's first ATTACK request as a named summary; use `null` with an explicit reason when none occurs.

- [x] **Step 7: Run validation tests**

Run: `UV_CACHE_DIR=/tmp/trackshift-uv-cache uv run pytest tests/test_policy_race_validation.py -q`

Expected: PASS.

---

### Task 4: Immutable all-profile runner, execution and durable documentation

**Files:**
- Create: `data/policy_phase8/run_4hz_profile_validation.py`
- Create: `data/policy_phase8/race_4hz_all_profiles_v1/`
- Modify: `docs/TRACKSHIFT_FULL_REVISED_ARCHITECTURE_v05.md`
- Modify: `docs/PHASE_8_PLAN.md`
- Delete after durable docs are updated: `docs/superpowers/specs/2026-09-13-4hz-profile-race-validation-design.md`

**Interfaces:**
- Consumes the base qualifying checkpoint, promoted profile registry and native Japan race artifact.
- Produces 22 immutable checkpoints, 22 withheld reports, 22 P23 reports and one consolidated summary.

- [x] **Step 1: Implement the resumable runner**

Freeze the split manifest before training. For each profile, restore the same qualifying checkpoint, train only its training laps, save the profile checkpoint, validate its withheld laps and run the independent P23 diagnostic. Refuse partial or hash-mismatched profile outputs.

- [x] **Step 2: Run all focused tests**

Run: `UV_CACHE_DIR=/tmp/trackshift-uv-cache uv run pytest tests/test_policy_curriculum.py tests/test_policy_diagnostic.py tests/test_policy_race_validation.py -q`

Expected: PASS.

- [x] **Step 3: Run training and validation serially**

Run: `UV_CACHE_DIR=/tmp/trackshift-uv-cache uv run python data/policy_phase8/run_4hz_profile_validation.py`

Expected: 22 completed profile checkpoints and reports, restricted checkpoint reloads and a consolidated diagnostic summary.

- [x] **Step 4: Inspect invariants and profile 23 report**

Verify each validation split was untouched by training, all energy ledgers reconcile, every profile starts P23, the reference field remains unchanged and profile 23's first attack contains probability, path, power and energy evidence.

- [x] **Step 5: Run the complete backend suite**

Run: `UV_CACHE_DIR=/tmp/trackshift-uv-cache uv run pytest -q`

Expected: all tests pass; report any existing warnings separately.

- [x] **Step 6: Update permanent documentation and remove the temporary spec**

Record measured cadence, coverage, training counts, validation findings, P23 proxy limitations and output paths in the existing architecture and phase documents. Delete the temporary approval brief once those decisions are durable.
