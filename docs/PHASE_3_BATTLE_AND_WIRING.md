# Phase 3 — Battle, Game Theory, Sensitivity, and the Backend Seam

**Goal:** the focused battle/decision view opened from the race, plus robustness and decision
stability in the comparison results, plus the real `RaceSource` implementation the backend plugs
into.

**Depends on:** Phase 1's contract and session state (selection lives there), Phase 2's timeline
(battles are opened from it).

---

## 3.1 Battle types — completing `src/lib/race/types.ts`

The stubs declared in Phase 1 are filled in:

| Type | Contents |
|---|---|
| `BattleIdentity` | Participants, roles, lap, location, approach window, starting gap |
| `InformationSet` | What each participant is assumed to know when choosing |
| `Action` | A supplied attack, defend, wait, line, pace, or energy choice |
| `Feasibility` | Physical availability, energy cost, tyre cost, rule constraints |
| `MoveStructure` | `'sequential' \| 'simultaneous' \| 'stochastic' \| 'learned'` |
| `Objectives` | Time, position, energy, tyre, risk, points, or a supplied combined utility |
| `Response` | Typical response, strategic best response, or a learned response distribution |
| `BattleOutcome` | Pass chance, resulting order, gaps, resource cost, risk, uncertainty |
| `SolutionStatus` | `'pure' \| 'mixed' \| 'multiple' \| 'none' \| 'solver_failure'` |
| `Sensitivity` | Outcome under another supported opponent belief or game formulation |

`SolutionStatus` being a first-class field, not a boolean, is the point: `multiple` and `none` are
outcomes the view must render honestly, not failure paths to hide.

## 3.2 Battle region — `src/components/race/battle/`

Opens around **one declared decision window**, not the whole race:

```
BATTLE CONTEXT · participants · roles · gap · location · resources · info
AVAILABLE ACTIONS │ MOVE / RESPONSE STRUCTURE │ OBJECTIVES AND COSTS
RECOMMENDED ACTION · EXPECTED RESPONSE · OUTCOME RANGE · SOLUTION STATUS
BASELINE BATTLE REPLAY │ SELECTED DECISION BRANCH REPLAY
SENSITIVITY · typical response · best response · other supported models
```

Structure follows the model, rather than forcing every interaction into one interpretation:

- **Sequential** — the first move is placed before the response.
- **Simultaneous** — both action sets sit on equal footing.
- **Stochastic / learned** — response distributions, not a single predicted move.

Hard rules the components enforce:

- No game result is labelled the opponent's actual intent.
- When the backend cannot justify a unique solution, **all** valid outcomes stay visible along
  with the fact that there is no unique answer.
- Pass probability states the opportunity window it describes; physical feasibility is a separate
  displayed value, never folded into the probability.

## 3.3 Local battle replay

Two synchronised local replays: baseline, and the selected decision branch.

- Shows both affected cars plus any other car whose state changes materially.
- After the decision window, the full field continues from the chosen branch — opponents are
  **not** reset to their recorded positions. This is the difference between a counterfactual and
  a recorded replay, and it is the thing most easily got wrong.
- If the branch uses recorded opponents, the fixed-opponent assumption stays visible throughout.

Reuses `RaceWorldMap` from Phase 2, scoped to the battle window rather than the whole lap.

## 3.4 Robustness and decision stability

Extends Phase 2's `<StrategyOutcome>` with the two remaining comparison-result groups:

- **Robustness** — the result across credible car, weather, interruption, and opponent
  assumptions.
- **Decision stability** — whether the preferred choice changes under another supported
  assumption. When it does, that is a headline result, shown beside the recommendation.

## 3.5 Fixture battles

The fixture gains scripted battle windows covering the spec's harder review cases:

- Two valid game solutions — both rendered, no unique answer claimed.
- Typical response and strategic best response disagreeing — recommendation sensitivity shown.
- A solver failure — preserved inputs, stated failure, no fabricated outcome.

## 3.6 Backend wiring — `src/lib/race/websocketSource.ts`

The second `RaceSource` implementation. Same interface, so no view changes.

- Connects to whatever endpoint the backend ships; sends `start`, `pause`, `resume`, `seek`,
  `rate`, `stop`; maps incoming messages to `RaceMessage`.
- **Validates at the boundary.** A field the backend omits becomes `unsupported` with a reason —
  it never becomes zero, and it never becomes an average-car substitute. This is the one place
  runtime shape-checking is worth the code, because it is where untrusted data enters.
- Late frames may be skipped; a frame with an older sequence id is dropped by Phase 1's reducer.
- A cached or precomputed replay is labelled replay, not live estimation. A live forecast uses
  only observations accepted by the declared cutoff.

`FixtureRaceSource` is kept permanently — it is how the review cases and layout states stay
testable without a live backend.

The open questions in `README.md` §7 are closed here, against the shipped backend contract.

## 3.7 Increment order

1. Battle types; sample battle frame type-checks.
2. Battle context + actions + move structure, static.
3. Recommended action / expected response / outcome range / solution status, including `multiple`
   and `none`.
4. Local dual replay with the branch continuing rather than resetting opponents.
5. Sensitivity strip.
6. Robustness and decision stability in the strategy outcome.
7. `WebSocketRaceSource` with boundary validation, behind a source switch.

## 3.8 Implementation notes

- `WebSocketRaceSource` defaults to `ws://localhost:8000/api/stream/full-race`, which does not
  exist yet. The view still constructs `FixtureRaceSource`; swapping the one line in
  `FullRaceView.tsx` is the whole change once the endpoint ships.
- The two review cases Phase 2 could not demonstrate (forecast horizon expiring, a live update
  changing the car profile) still need a real source. The contract carries both; nothing
  exercises them.
- Battles are declared against the recorded baseline and surface on the timeline as competition
  events, so clicking one on the timeline opens it.

## 3.9 Done when

- A battle opens from the timeline or field, showing structure, actions, outcomes, and solution
  status.
- Multiple-solution and no-stable-solution cases render honestly.
- The decision branch continues the field rather than resetting opponents.
- The frontend runs against either source with no change to any view, and an omitted backend
  field renders as unavailable.
