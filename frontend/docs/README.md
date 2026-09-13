# Full-Race Frontend — Analysis and Phase Plan

**Source spec:** `../track-shift/docs/FULL_RACE_FRONTEND_SPEC.md`
**Status:** All three phases implemented at `/full-race`, driven by the fixture source.
The WebSocket source is written and validated but not yet pointed at a live backend.

---

## 1. Where the frontend is today

| Piece | Current shape |
|---|---|
| `src/lib/types.ts` | Lap-shaped contract: `InitMessage` (track geometry, one driver, one policy), `FrameMessage` with exactly two `CarState`s (`reference`, `policy`) |
| `src/lib/useSimulation.ts` | One reducer, one WebSocket to `ws://localhost:8000/api/stream/simulation`, appends every frame to a flat `history[]` |
| `src/components/Dashboard.tsx` | 508 lines. Owns layout, modals, config picker, charts, playback, and the headline result |
| `src/components/TrackMap.tsx` | SVG outline + **one** car marker |
| `src/components/BatteryMeter.tsx` | Single SoC bar, 0–4 MJ, one ghost tick |
| Routes | `/` landing, `/setup` picker, `/race` dashboard |

The current review experience is a 23-car fixture race plus source-bound qualifying and P23
diagnostic reports. Historical limitations below describe the original foundation, not the report UI.

## 2. What the spec asks for that does not exist

Ordered by how much new structure each one forces.

1. **Two independent race worlds.** Not two cars — two complete fields with *separate* lap counts,
   order, events, and finish states, sharing only a comparison clock. Nothing in the current state
   model can express "these two orderings are not the same race".
2. **A full field.** 23 participants per world, each with position, gap, interval, sector, pit
   state, tyre stint, energy flows, traffic state. The fixture now renders the full 23-car field.
3. **Information status on every value.** Observed / inferred / predicted / simulated /
   unsupported, carried all the way down from a race result to a lap or telemetry detail.
   Currently no value carries provenance at all, and missing values fall back to defaults
   (`socMj ?? 4.0`) — which the spec explicitly forbids: absence must read as unavailable, never
   as zero or an average-car substitute.
4. **A branch-aware shared timeline.** Shared history before the branch point, separate aligned
   lanes after it, for pits, flags, weather, penalties, and model updates.
5. **Nine layout states.** Preparing, partial, streaming, paused, complete, disconnected,
   unsupported, abstained, failed. Today there are five (`idle/computing/playing/paused/finished`
   plus `error`) and none of them preserve the question when the answer is unavailable.
6. **Battle / game-theory region.** Actions, move structure, objectives, responses, solution
   status, local branch replay, sensitivity. Roughly a third of the spec on its own.
7. **Richer energy accounting.** Requested / converted / stored / recovered / curtailed as
   separate quantities. Today: one `soc` number and one signed `p_kw`.

## 3. The constraint that shapes everything

**The backend has no full-race contract.** The spec says so itself, and the current API
(`src/api/main.py`, `streaming_service.py`) serves a single-lap `reference` vs `policy` playback.

**Decision:** build the frontend now against a contract we define here, driven by a local fixture
race. Every phase renders real, moving, internally coherent data — it is just generated locally.
All data entry to the app goes through one `RaceSource` interface, so wiring the real backend
later is a new implementation of that interface, not a rewrite of the views.

This has a second benefit the spec cares about: the fixture race can be *scripted* to produce the
awkward cases (a safety car in one world only, a retirement, unresolved energy, two valid game
solutions), which is the only practical way to verify the honesty rules before real data exists.

## 4. Agreed decisions

| Decision | Choice | Reason |
|---|---|---|
| Data source | Frontend contract + local fixture race behind one `RaceSource` interface | Backend not ready; keeps every phase demoable |
| Route | New `/full-race`; `/race` untouched | The single-lap replay stays the working demo throughout, as the spec's status note requires |
| Field rendering | Track map **and** timing tower per race world | Closest to the spec layout; heaviest work sits in Phase 2 |
| Phase 3 | Battle + sensitivity; honesty machinery lands in Phases 1–2 | Degraded/abstained behaviour must not arrive last |

## 5. Phase map

| Phase | Delivers | Demoable result |
|---|---|---|
| **[Phase 1](./PHASE_1_FOUNDATION.md)** — *implemented* | Full-race contract, fixture source, session state, top context band, two field-order towers, delta column, playback band, information-status rendering | `/full-race` plays a scripted 20-car race in two worlds on one clock, every value labelled by source status |
| **[Phase 2](./PHASE_2_RACE_REPLAY.md)** — *implemented* | Full-field track maps per world, branch-aware shared timeline, selected-driver comparison, strategy comparison + assumptions region, remaining layout states, narrow layout | The complete non-battle spec layout, verified against the spec's review cases |
| **[Phase 3](./PHASE_3_BATTLE_AND_WIRING.md)** — *implemented* | Battle/game-theory region, local decision-branch replay, sensitivity, robustness and decision stability, backend `RaceSource` swap | A focused battle view opened from the race, plus the seam the real backend plugs into |

## 6. Explicitly not in scope (from the spec)

- Colour, typography, spacing, icon, interaction styling — the existing dark-glass system stays.
- Client-side physics, ranking, probability, or equilibrium calculation. The fixture *generates*
  a coherent race; the views never compute one.
- Choosing which game model is correct. The frontend displays the model used and its sensitivity.
- Endpoint, message, storage, or service design. The contract in Phase 1 is what the frontend
  needs; the backend team owns delivery.

## 7. Open questions for the backend, recorded here so Phase 3 can close them

The adapter (`src/lib/race/websocketSource.ts`) is written against the contract in
`src/lib/race/types.ts` and coerces every incoming message in `src/lib/race/boundary.ts`.
These five points still need agreement with the backend before it can be pointed at a live
endpoint — the fixture answers each one locally in the meantime:

1. Does a frame carry the whole field every tick, or deltas against the previous frame?
2. Is the comparison clock elapsed race time, or time since branch? The spec allows either;
   the frontend needs one declared per session.
3. Are comparison deltas computed backend-side (spec says yes — "the backend owns … comparison
   deltas"), including for the selected driver across different pit cycles?
4. How is a scenario selected — request parameter, or does the backend push the available set?
5. What identifies a battle window, and who decides which battles are worth surfacing?
