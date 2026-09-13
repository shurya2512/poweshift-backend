# Phase 1 — Contract, Two Race Worlds, and the Honesty Layer

**Goal:** `/full-race` plays a scripted 20-car race as two independent worlds on one shared clock,
with every displayed value carrying its source status. No track maps, no timeline lanes, no
battle view — those are Phases 2 and 3.

**Why this is first:** the contract and the information-status rule reach into every later
component. Retrofitting provenance onto finished views is the one mistake that makes the rest of
the spec unimplementable.

---

## 1.1 The contract — `src/lib/race/types.ts`

New file. Does not touch `src/lib/types.ts` (the single-lap contract stays where it is).

### The value wrapper

Every supplied value or related group of values carries one status. This is the spine of the
whole spec, so it is a type, not a convention:

```ts
type SourceStatus = 'observed' | 'inferred' | 'predicted' | 'simulated' | 'unsupported';

type Valued<T> =
  | { status: 'observed';   value: T; source: string; observedAt: number }
  | { status: 'inferred';   value: T; interval?: [number, number]; alternatives?: T[] }
  | { status: 'predicted';  value: T; interval?: [number, number]; cutoff: number; horizon: number }
  | { status: 'simulated';  value: T; scenarioId: string; assumptions: string[] }
  | { status: 'unsupported'; reason: string };          // no `value` field, by construction
```

The `unsupported` variant carrying no `value` is deliberate: TypeScript then makes
`socMj ?? 4.0` a compile error rather than a silent lie.

### The rest, grouped as the spec groups it

| Type | Covers | Spec section |
|---|---|---|
| `RaceIdentity` | Season, event, circuit, session, rules version | Race identity and freshness |
| `ExperienceMode` | `'recorded_replay' \| 'conditional_replay' \| 'forward_forecast' \| 'counterfactual'` | Race identity and freshness |
| `TimeBoundary` | Observation cutoff, generated time, latest accepted update | Race identity and freshness |
| `SupportState` | `'ready' \| 'partial' \| 'stale' \| 'unsupported' \| 'abstained' \| 'failed'` | Race identity and freshness |
| `ScenarioIdentity` | Stable id, short name, purpose, parent branch, opponent formulation | Scenario identity |
| `BranchPoint` | Race time, lap, event, or decision where worlds separate | Scenario identity |
| `Participant` | Driver, team, entry, number, participation state | Participant and car state |
| `ParticipantState` | Position, motion, energy, tyres, race load, traffic — each field `Valued<>` | Participant and car state |
| `EnergyState` | `stored`, `requested`, `delivered`, `recovered`, `curtailed` — five separate `Valued<number>` | Participant and car state |
| `RaceWorld` | One coherent ordered field + track state + its own lap count and events | Race frame |
| `RaceFrame` | Playback time, sequence id, leader lap, phase, flag, weather, one `RaceWorld` per side, deltas, freshness | Race frame |
| `RaceEvent` | Session control / strategy / competition / environment / outcome / model, each tagged with its world (or `shared`) | Race events and timeline |
| `ComparisonResult` | Race outcome, relative outcome, strategy outcome, forecast outcome, with branch point and evidence cutoff | Comparison results |

Battle and game-theory types are **declared as stubs only** in Phase 1 (so the frame type is
complete) and filled in Phase 3.

**Validation:** the file compiles, and a hand-written sample frame type-checks. Confirm that
assigning a raw `number` where a `Valued<number>` is expected fails to compile.

## 1.2 The source seam — `src/lib/race/source.ts`

```ts
interface RaceSource {
  start(request: SessionRequest): void;
  pause(): void;
  resume(): void;
  seek(raceTimeS: number): void;
  setRate(rate: number): void;
  stop(): void;
  subscribe(handler: (msg: RaceMessage) => void): () => void;
}
```

`RaceMessage` is a discriminated union mirroring what the backend will eventually send:
`session`, `frame`, `events`, `comparison`, `support`, `error`.

Two implementations over the project's life. Phase 1 ships the first; Phase 3 adds the second:

- `FixtureRaceSource` — replays a generated race locally on a timer.
- `WebSocketRaceSource` — Phase 3.

**Nothing outside `src/lib/race/` may import a concrete source.** The hook takes a `RaceSource`.

## 1.3 The fixture race — `src/lib/race/fixtures/`

A generated, internally coherent race. Not physics — a scripted sequence built once and replayed.

- `buildFixtureRace(seed)` produces: 23 participants, ~30 laps, a baseline world, one alternative
  world branching at a declared pit decision, an event list per world, and per-frame comparison
  deltas.
- Deliberately includes, from the start, the cases the spec's review table names:
  a driver pitting in one world and staying out in the other; one world finishing first;
  a retirement; a lapped car; a participant whose energy is `unsupported`.
- Emits at a fixed rate with a monotonic sequence id, so the "newer state never appears behind
  older state" rule is testable.

**Validation:** a script printing frames at t=0, mid-race, and finish shows two orders that
genuinely diverge after the branch and never after-the-fact rewrite shared history.

## 1.4 Session state — `src/lib/race/useRaceSession.ts`

One reducer. Holds:

- `sessionState` — support state, mode, identity, time boundary, freshness.
- `frame` — the latest accepted frame (not an append-everything `history[]`; Phase 2's timeline
  reads the event list, and charts read a bounded window).
- `events` — accumulated, world-tagged.
- `comparison` — the latest comparison result.
- `playback` — status, rate, current race time.
- `selection` — selected driver, selected event, selected scenario. Selection is session state,
  not component state, because Phase 2's timeline and Phase 3's battle view both read it.

Rules enforced here, once, rather than in every view:

- A frame with a sequence id older than the current one is dropped.
- On disconnect, the last confirmed frame is retained and marked stale.
- Paused freezes both worlds and every derived comparison at one received time.

**Validation:** unit-level checks by driving the reducer directly — out-of-order frame dropped,
stale flag set on disconnect, pause freezes the frame.

## 1.5 Rendering the honesty layer — `src/components/race/`

| Component | Responsibility |
|---|---|
| `<StatusValue>` | Renders a `Valued<T>`: the number, its status marker, its interval or alternatives, and — for `unsupported` — the word unavailable plus the reason. Never renders a fallback number. |
| `<TopContextBand>` | Event · mode · observation cutoff · freshness · support state |
| `<OutcomeRow>` | Baseline outcome │ comparison delta │ alternative outcome |
| `<FieldOrder>` | One world's ordered field: position, driver, gap, interval, pit/retired/lapped state |
| `<DeltaColumn>` | Differences only — order, gaps, strategy divergence, confidence/horizon. Never a third world. |
| `<PlaybackBar>` | Current time/lap, start, pause, seek, rate, next event |

`<FieldOrder>` renders retired, lapped, and finished participants by classification, not by a
numeric ordering that implies they are still racing.

## 1.6 The route — `src/app/full-race/`

`page.tsx` + a client `FullRaceView`. Layout, top to bottom, matching the spec's reading order,
with Phase 2 and 3 regions left out rather than stubbed with placeholders:

```
TOP CONTEXT BAND
BASELINE OUTCOME │ COMPARISON DELTA │ ALTERNATIVE OUTCOME
BASELINE WORLD (field order) │ LIVE DIFFERENCES │ ALTERNATIVE WORLD (field order)
PLAYBACK
```

Baseline stays on the left for the entire experience, in every phase.

## 1.7 Layout states in this phase

Preparing, streaming, paused, complete. Each keeps the event, mode, assumptions, and the
requested comparison visible. The remaining five land in Phase 2 alongside the regions that need
them.

## 1.8 Increment order

1. `types.ts` compiles; sample frame type-checks.
2. `source.ts` interface + `FixtureRaceSource` emitting frames to a console subscriber.
3. Fixture race generator; verify divergence and the scripted edge cases.
4. `useRaceSession` reducer; verify ordering, staleness, pause.
5. `<StatusValue>`; verify each of the five statuses renders, and `unsupported` renders no number.
6. `<TopContextBand>` + `<PlaybackBar>` on the route, wired to the fixture.
7. `<FieldOrder>` ×2 + `<DeltaColumn>` + `<OutcomeRow>`.

Each step validated before the next.

## 1.9 Done when

- `/full-race` plays the fixture race end to end; both worlds' orders diverge after the branch.
- Pausing freezes both worlds at one time; seeking moves both to the same elapsed race time.
- Every displayed value shows a source status; the unsupported-energy participant shows
  unavailable, not a number.
- `/race` and `/setup` are unchanged and still work.
