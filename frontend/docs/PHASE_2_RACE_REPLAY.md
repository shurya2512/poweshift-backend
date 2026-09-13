# Phase 2 — Race Worlds, Timeline, Driver Comparison, Strategy

**Goal:** the complete non-battle spec layout. Two full-field track maps, a branch-aware shared
timeline, the selected-driver comparison, the strategy comparison and assumptions region, and the
remaining layout states — verified against the spec's own review cases.

**Depends on:** Phase 1's contract, fixture source, session state, and `<StatusValue>`.

---

## 2.1 Full-field track map — `src/components/race/RaceWorldMap.tsx`

`TrackMap.tsx` draws one car and is kept as-is for `/race`. `RaceWorldMap` is a new component,
not a refactor of it, because the requirements genuinely differ.

- Renders the circuit outline once, then a marker per participant in **that world's** field.
- The selected driver stays visually identifiable in both worlds — including after different pit
  cycles, retirements, or lapping events, where the two markers are at different track positions
  and on different laps.
- Pit-lane state is drawn as pit-lane state, not as a position on the racing line.
- Retired participants leave the map; the field order keeps their classification.
- Positions may move smoothly between supplied locations. Measured and inferred readouts keep the
  backend's cadence and precision — the interpolation is positional only, never applied to energy,
  tyre, or fuel values.

**Performance note:** 20 markers × 2 worlds × the frame rate. Markers update via transform on a
static outline; the outline path is memoised on track identity.

**Validation:** a mid-race frame where the two worlds' orders differ shows visibly different car
distributions, and the selected driver is findable in both.

## 2.2 Shared full-race timeline — `src/components/race/RaceTimeline.tsx`

The single most spec-specific component.

- Spans both worlds. The period before the branch point is drawn as **shared history**, once.
- After the branch, scenario-specific pit stops, passes, flags, weather, penalties, and model
  updates occupy separate aligned lanes per world.
- Lanes follow the spec's event groups: session control, strategy, competition, environment,
  outcome, model.
- An event is marked `shared` only when it remains identical after the branch point.
- **Selecting a moment** moves both worlds to the same elapsed race time.
- **Selecting an event** moves to that event in its own world and identifies the corresponding
  time in the other world — it does not invent a matching event there.
- If one world finishes first, its final state is held while the other continues.

**Validation:** each of those five behaviours checked against the fixture race, which is scripted
to contain a one-world-only safety car and a staggered finish.

## 2.3 Selected-driver comparison — `src/components/race/DriverComparison.tsx`

Matched baseline and alternative columns, same categories in the same order:

- Position, gap, interval, lap, sector, pit state.
- Current tyre stint and remaining supported tyre estimate.
- Fuel or mass estimate when supported.
- Stored energy plus **separate** deployment, recovery, and curtailment flows — the spec forbids
  collapsing these into one net battery number when the richer values exist. `BatteryMeter.tsx`
  shows a single 0–4 MJ bar and cannot express this, so a new `EnergyPanel` is written; the old
  meter stays for `/race`.
- Current pace target, energy target, supplied strategy instruction.
- Source status and uncertainty for every inferred or predicted value.

**Alignment basis is named next to the detail.** Race-time views stay on the shared playback
clock; corner and lap analysis switches to distance within the selected lap. The label saying
which one is in force is a requirement, not a nicety.

## 2.4 Strategy comparison and assumptions

- `<StrategyOutcome>` — expected finish, points or declared utility, total time, pit plan, tyre
  use, uncertainty. When several alternatives exist it may summarise all supplied scenarios, while
  the main replay continues to compare baseline against **one** selected alternative.
- A preferred strategy is shown only with the assumptions that make it preferred. If the
  preference changes across supported weather, interruption, car-profile, or opponent assumptions,
  that changing decision is part of the main comparison result — not a footnote.
- `<AssumptionsPanel>` — weather, interruptions, pit loss, tyre sets, starting states, opponent
  beliefs, data coverage, missing inputs, permitted evidence, warnings, and every unsupported
  value with its reason.

Results from different evidence cutoffs are never presented as a direct strategy comparison; the
component checks the cutoffs match and shows a warning instead if they do not.

## 2.5 Remaining layout states

Phase 1 shipped preparing, streaming, paused, complete. Phase 2 adds:

| State | Behaviour |
|---|---|
| Partial | Preserve available race regions; identify which values or worlds are incomplete |
| Disconnected | Retain the last confirmed frame, mark it stale until continuity returns |
| Unsupported | Keep the requested question visible; state which evidence or capability is missing |
| Abstained | Show the backend's reason, supported horizon, and any safe fallback result |
| Failed | Preserve scenario inputs; identify whether baseline, alternative, or comparison failed |

The fixture source gains a way to inject each of these so all nine are reachable in the demo.

## 2.6 Narrow layout

Baseline precedes alternative, followed by deltas, on one shared clock. Not a hidden column and
not a tab that makes a comparison invisible.

## 2.7 Review cases — the acceptance checklist

Straight from the spec. Each is scripted into the fixture race and checked by hand:

| Case | Must remain clear |
|---|---|
| Identical before a pit branch | Shared history and exact branch point |
| Safety car in one world only | Separate event histories, coherent field order |
| Pits in one world, stays out in the other | Position change, tyre tradeoff, later consequences |
| One world finishes earlier | Final state held while the other continues |
| Retirement or lapping | Classification and gaps without false numeric ordering |
| Energy or fuel unresolved | Unavailable or uncertain, never zero |
| Recorded opponents in a counterfactual | Fixed-opponent assumption visible throughout |
| Forecast horizon expires mid-race | Later output marked unsupported or degraded |
| Live update changes the car profile | Update time, affected forecast, widened or narrowed uncertainty |
| Narrow layout | Baseline, then alternative, then deltas, one clock |

## 2.8 Increment order

1. `RaceWorldMap` with a static frame, then wired to playback.
2. Timeline: shared history and branch point only.
3. Timeline: per-world lanes and event selection.
4. `DriverComparison` columns, `EnergyPanel` with the five separate flows.
5. `StrategyOutcome` + `AssumptionsPanel`.
6. Remaining layout states, each injectable from the fixture.
7. Narrow layout.
8. Walk the review-case checklist.

## 2.9 Implementation notes

Two cases in §2.7 are **not** demonstrable against this fixture, and were deliberately not
faked to make the checklist look complete:

- **Forecast horizon expires mid-race.** The fixture runs in `counterfactual` mode with no
  forecast horizon, so nothing can expire. The equivalent honesty path — the backend declining
  to answer — is reachable through the injectable `abstained` state instead.
- **A live update changes the car profile.** The fixture has no live updates; the contract
  carries `latestAcceptedUpdateMs` for it, but nothing exercises it until a real source does.

Both close in Phase 3 against the real adapter.

## 2.10 Done when

Every review case in §2.7 passes against the fixture race, all nine layout states are reachable,
and the full spec layout minus the battle region renders on one shared clock.
