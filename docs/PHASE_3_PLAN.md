# Phase 3 approval plan: numerical profile and canonical mechanics

## Purpose

Phase 2 prepared traceable Bahrain testing telemetry, targets and a limited planar reference path.
It did not fit car behaviour or establish energy, ranking, strategy, qualifying or race readiness.
Phase 3 will create a reproducible numerical baseline of supported *effective* entry motion
components and one shared axle-aware mechanics path for fitting and replay.

The outcome is an evidence-bound baseline and a report of unsupported components. It will not
identify factory vehicle maps, separate driver and programme effects, enable electrical deployment,
or make a full-lap or race-performance claim.

~~~mermaid
flowchart LR
    Evidence["Phase 2 evidence<br/>traceable prepared telemetry"] --> Admit{"Inputs and decisions<br/>accepted for this run?"}
    Admit -->|"no"| Stop["Stop with a missing-input report"]
    Admit -->|"yes"| Align["Align only supported<br/>telemetry to the route"]
    Align --> Kernel["One common effective<br/>axle-aware mechanics path"]
    Kernel --> Fit["Fit bounded effective<br/>components on training runs"]
    Fit --> Freeze["Freeze profile and<br/>selection settings"]
    Freeze --> Replay["Replay held-out<br/>continuous runs"]
    Replay --> Report["Baseline profile, report<br/>and unresolved components"]
    classDef evidence fill:#1d4ed8,color:#ffffff,stroke:#1e3a8a
    classDef gate fill:#b45309,color:#ffffff,stroke:#78350f
    classDef process fill:#0f766e,color:#ffffff,stroke:#134e4a
    classDef output fill:#7c3aed,color:#ffffff,stroke:#4c1d95
    class Evidence evidence
    class Admit gate
    class Align,Kernel,Fit,Freeze,Replay process
    class Stop,Report output
~~~

## Approval boundary

Human approval must resolve the proposed defaults and decisions below before implementation begins.
The accepted Phase 2 coverage disposition and split remain pinned; Phase 3 does not reopen them.
The fixed chronology is Test 1, 11-13 February, for training; 18 February for selection; and
19-20 February for final evaluation. Final-evaluation data cannot select settings, bounds or fits.

The pending Phase 2 gates are the preparation limits and stated limitations. Proposed reuse is a
1.160 s gap, 0.440 s smoothing and 190.761 s window, subject to approval. The recorded 0.240 s
staleness statistic stays unused: it is a sampling interval, not a staleness policy. The current
gap rule makes a run a telemetry segment, not a programme run. Phase 3 will not loosen that rule or
bridge its breaks without a new human decision and immutable preparation artifact.

## Carried decisions and proposed defaults

| Topic | Carried decision | Proposed working default | Rationale |
|---|---|---|---|
| Evidence | Use only admitted, source-linked Phase 2 records. | Pin the Phase 2 manifest, coverage decision, split and preprocessing artifact by hash. | A fit cannot be reused with different evidence. |
| Chronology | Test 1 trains, 18 February selects, and 19-20 February evaluate. | Exclude final-evaluation records from fitting and selection. | The held-out result must remain independent. |
| Profile | The architecture requires effective components. | Publish bounded effective propulsion, resistance, braking and grip terms with support and assumptions. | The telemetry does not identify factory maps or remove driver, fuel and programme effects. |
| Geometry | Phase 2 stores one training-lap profile with progress, distance, curvature mask, transform and source rows, but not X/Y coordinates. | Reconstruct that provisional path from pinned acquisition position records and source rows; reject records that cannot align. | Normalized progress alone cannot support nearest-route mapping or a survey claim. |
| Chunks | Every package starts with `dt_s = 0`. | Recover the first sample from `start_time_s`, then accumulate later intervals. Carry state only across verified chronological chunks of one run. | This avoids both chunk resets and gap stitching. |
| Units | Packages store physical/native values; `FrozenScaler` is separate. | Validate units and use `speed_ms` directly. Apply a frozen scaler only where an explicit later model needs one. | Mechanics must not assume serialized values are standardised or invert a scaler blindly. |
| Mechanics | One path must serve fitting and replay. | Use CPU float64 fixed-step RK4, configured event splitting, axle-aware loads/grip and deterministic driver demand. | It is a testable common baseline before energy actuation. |
| State assumptions | Reference mass, fuel, axle geometry, load transfer, tyre condition and driver response are not measured vehicle parameters. | Declare a source or assumption label for each, including mass inclusion and fuel-load evolution; freeze the set before fitting. Grade remains unavailable, not measured flat. | No physical parameter may be fabricated from unsupported telemetry. |
| Tyres | Phase 3 needs a shared tyre-condition policy but cannot identify a full tyre model. | Add a minimal support-limited condition policy with named assumptions and explicit exclusion states. | It lets the mechanics report unsupported tyre effects instead of hiding them. |
| Live progress | A trustworthy target needs unavailable position mapping. | Defer it; do not fabricate a target. | Testing-session preparation does not supply it. |
| Fitting | Selection precedes final evaluation. | Choose bounds, regularisation and numerical tolerances from training and selection evidence; freeze them before final evaluation. | No arbitrary constant becomes an accepted threshold. |

## Scope

Included:

- Strict Phase 3 input, alignment, effective-profile and fit-report contracts.
- A source-linked route-alignment artifact and explicit rejection of unavailable mapping.
- One canonical mechanics kernel: deterministic demand, axle loads, combined grip, effective
  longitudinal forces, declared reference-mass/fuel assumptions, support-limited tyre condition and
  float64 RK4 event splitting.
- Bounded effective-component fitting, frozen reports, held-out replay and numerical checks.

Deferred:

- Network 1 encoders or neural fitting.
- Independent electrical deployment, battery accounting, source-response maps and rules.
- Tyre-state identification, weather/wake effects, grade, width, corner boundaries, pit branch and
  rule-line mapping.
- Qualifying, race, live-progress, ranking, overtaking, pit or strategy conclusions.

| Not doing | Reason |
|---|---|
| Factory vehicle identification | The available telemetry does not resolve it. |
| Invented coordinates or route metadata | Phase 2 marks those fields unsupported. |
| Joining disconnected runs | A preparation break has no observed continuous state. |
| Treating known-input replay as forecast | Recorded controls and future observations are unavailable to a forecast. |
| Changing Phase 2 artifacts or decisions | This phase consumes them by hash. |

## Planned work and commits

Every code-producing task starts with Context7: resolve each library, then check the exact
signature and behaviour before edits. The planned checks cover Pydantic, NumPy, pandas and SciPy.
If Context7 is unavailable, use official documentation and current repository usage, then record
that uncertainty in the handoff. Comments and docstrings stay to one or two short plain-language
lines.

### Commit 1: Admit inputs and align only supported telemetry

Update the existing architecture documentation in the same commit whenever an implementation
decision changes; the final commit consolidates evidence and the handoff.

| Planned files | Change |
|---|---|
| `pyproject.toml`, `uv.lock` | Add the bounded numerical fitting dependency after checking compatibility and API. |
| `src/poweshift_backend/contracts/reconstruction.py` | Add strict input-manifest, alignment, effective-profile, fit-report and missing-component contracts. |
| `src/poweshift_backend/reconstruction/inputs.py` | Read pinned artifacts, validate feature meaning and recover physical chunk timelines. |
| `src/poweshift_backend/geometry/alignment.py` | Rebuild the source-linked X/Y path and map only supported observations to route progress/distance. |
| `tests/test_reconstruction_inputs.py`, `tests/test_geometry_alignment.py` | Cover hash pinning, physical speed, scaler separation, first-chunk time, no cross-run join and mapping refusal. |

Blast radius: new Phase 3 readers and alignment only; Phase 1 and Phase 2 artifacts remain
unchanged.

### Commit 2: Establish the common effective mechanics kernel

| Planned files | Change |
|---|---|
| `src/poweshift_backend/driver/controller.py` | Add declared deterministic demand for known-input and forecast modes. |
| `src/poweshift_backend/physics/state.py`, `src/poweshift_backend/tyres/condition.py` | Add minimal dynamic state plus frozen mass, fuel, axle, driver and tyre-condition assumptions with explicit support limits. |
| `src/poweshift_backend/physics/axle_loads.py`, `src/poweshift_backend/physics/grip.py` | Calculate bounded front/rear loads and combined grip; report infeasibility or non-convergence. |
| `src/poweshift_backend/physics/forces.py`, `src/poweshift_backend/physics/integrate.py` | Calculate effective forces and advance float64 RK4 with event splitting and no endpoint repair. |
| `tests/test_physics_axles.py`, `tests/test_physics_integration.py`, `tests/test_tyre_condition.py` | Check synthetic analytic straight-line/braking fixtures, load/grip limits, event order, closure and unsupported paths. |

Blast radius: new mechanics modules only. Electrical sources, battery state and allocation remain
disabled.

### Commit 3: Fit and freeze bounded effective profiles

| Planned files | Change |
|---|---|
| `src/poweshift_backend/reconstruction/baseline.py`, `src/poweshift_backend/reconstruction/losses.py` | Fit bounded effective components on training runs and calculate masked residuals and regularity. |
| `src/poweshift_backend/reconstruction/report.py`, `src/poweshift_backend/reconstruction/__init__.py` | Emit immutable settings, provenance, support, missing components and diagnostics. |
| `tests/test_reconstruction_baseline.py`, `tests/test_reconstruction_reports.py` | Verify bounds, reproducibility, training-only selection, frozen final-evaluation settings, masks and separate missing components. |

Blast radius: new baseline artifacts only. It cannot create an energy-ready profile, neural model or
identified vehicle claim.

### Commit 4: Verify continuous replay and numerical convergence

| Planned files | Change |
|---|---|
| `src/poweshift_backend/reconstruction/replay.py` | Replay a frozen profile across verified chunks of one continuous run and label known-input and forecast outputs separately. |
| `src/poweshift_backend/physics/reference_solver.py` | Add an independent solver used only to check the shared equations. |
| `src/poweshift_backend/reconstruction/evidence.py` | Produce held-out motion metrics and counts by entry/regime, braking/cornering support flags, exclusions and numerical diagnostics. |
| `docs/TRACKSHIFT_FULL_REVISED_ARCHITECTURE_v05.md`, `docs/PHASE_3_HANDOFF.md` | Move any changed durable decision into the architecture and record delivered scope, checks, limits and remaining decisions in the handoff. |
| `tests/test_reconstruction_replay.py`, `tests/test_physics_convergence.py`, `tests/test_phase3_evidence.py` | Check no chunk reset, no gap stitching, held-out isolation, analytic agreement, solver agreement and refined-step convergence. |

Blast radius: new replay and evidence reporting only. Solver agreement is a numerical check, not
proof that the effective mechanics are physically complete.

## Known-input and forecast boundary

~~~mermaid
flowchart TB
    Records["Recorded controls and telemetry<br/>inside one admitted continuous run"] --> Known["Known-input replay<br/>labelled reconstruction"]
    Prefix["Current state and available prefix"] --> Forecast["Forecast replay<br/>with declared assumptions"]
    Known --> Common["Same frozen profile<br/>and mechanics kernel"]
    Forecast --> Common
    Common --> Labels["Separate outputs, masks<br/>and limitation labels"]
    classDef input fill:#1d4ed8,color:#ffffff,stroke:#1e3a8a
    classDef process fill:#0f766e,color:#ffffff,stroke:#134e4a
    classDef output fill:#7c3aed,color:#ffffff,stroke:#4c1d95
    class Records,Prefix input
    class Known,Forecast,Common process
    class Labels output
~~~

Known-input reconstruction may use recorded throttle, brake and gear over its scored interval and
must disclose that use. Forecast replay uses only the current prefix, fitted profile and declared
driver/initial-state assumptions: it receives no target-future controls or positions and never
resets simulated progress from held-out positions. Neither mode receives protected targets or future
pit records. Short chunks are storage units, not independent restarts or a license to add their
scores as a full lap.

## Acceptance and test evidence

| Evidence | Acceptance condition |
|---|---|
| Input admission | Every fit names exact Phase 2 evidence and decisions; a missing, changed or unapproved item stops fitting. |
| Units, time and geometry | Physical speed is used directly; time starts at the package anchor; state only crosses verified chunks of one run; unavailable geometry is rejected. |
| Mechanics | The same axle-aware equations serve fitting and replay; forces and masses close within configured numerical tolerances; infeasible states remain explicit. |
| Fitting | Bounds and selection settings come from training/selection evidence, freeze before final evaluation and remain in the report. |
| Held-out replay | Report actual held-out motion metrics and counts by entry and propulsion/coast/braking/corner regime; final-evaluation values do not select a fit. |
| Profile support | Report braking and cornering investigation support or missing flags separately; numerical completion does not grant predictive admission or complete-profile status. |
| Numerical checks | Synthetic analytic fixtures and a separate solver agree within convergence-selected tolerances; refined steps report adequacy. These are not real-data validation. |
| Regression | Existing preparation, firewall, geometry and reproducibility tests pass with the new focused tests. |

Passing checks demonstrates traceability, code behaviour and numerical consistency only. It does not
demonstrate car differentiation, energy accuracy, rank fidelity, strategy quality or real-time
readiness.

## Decisions needed for approval

1. Approve or replace the proposed reuse of the 1.160 s gap, 0.440 s smoothing and 190.761 s
   window limits, and say whether their current segmentation is acceptable for Phase 3. Confirm
   that staleness remains recorded but unused.
2. Accept the proposed source-row geometry recovery, or keep alignment unavailable and defer
   position-dependent fitting.
3. Accept the effective-component scope and the known-input versus forecast separation.
4. Accept the declared-and-frozen reference mass/fuel, axle, driver and tyre assumption policy;
   unsupported values remain absent rather than fabricated.
5. Accept CPU float64 RK4, event splitting, synthetic analytic fixtures and an independent solver
   as the numerical verification baseline.

After the fourth commit, Phase 3 stops for a handoff covering delivered scope, checks, limits,
changed decisions and remaining decisions. This temporary approval plan is retired only after its
durable decisions are moved into the handoff and permanent architecture documentation.
