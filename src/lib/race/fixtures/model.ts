import { WorldSide } from '../types';
import { RaceSpec, setMeasuredEnergy } from './report';
import { ROSTER } from './roster';

const DEFAULT_TOTAL_LAPS = 30;
const DEFAULT_BASE_LAP_S = 88.0;
const DEFAULT_SELECTED_ID = 'VER';

// Live bindings so a loaded report can retune the race without rewiring every reader.
export let TOTAL_LAPS = DEFAULT_TOTAL_LAPS;
export let BASE_LAP_S = DEFAULT_BASE_LAP_S;
export const PIT_LOSS_S = 22.0;

export type NeutralisationKind = 'safety_car' | 'virtual_safety_car';

/** A stretch of laps the race is neutralised for. Both bounds inclusive. */
export interface Neutralisation {
  kind: NeutralisationKind;
  fromLap: number;
  toLap: number;
}

/** Extra seconds per lap while the race is neutralised, by kind. */
const NEUTRALISATION_LAP_PENALTY_S: Record<NeutralisationKind, number> = {
  safety_car: 34.0,
  virtual_safety_car: 13.0,
};

/** The one entry whose energy the fixture deliberately cannot resolve. */
export const NO_ENERGY_TELEMETRY_ID = 'BOR';
/** Retires on lap 8 — before the branch, so both worlds share it. */
export const RETIREMENT_ID = 'STR';
export const RETIREMENT_LAP = 8;
/**
 * The field runs two offset strategies, so the order genuinely shuffles through the
 * pit windows instead of holding pace order all race. Lap 10 is shared history.
 */
const FIELD_TWO_STOP = [10, 22];
const FIELD_ONE_STOP = [14];

export let SELECTED_ID = DEFAULT_SELECTED_ID;
let activeSpec: RaceSpec | null = null;
export const BRANCH_LAP = 12;

/** Retunes the race to a report's measured lap count, lap time and ego. */
export function applyRaceSpec(spec: RaceSpec | null): void {
  activeSpec = spec;
  setMeasuredEnergy(spec);
  TOTAL_LAPS = spec ? spec.totalLaps : DEFAULT_TOTAL_LAPS;
  BASE_LAP_S = spec ? spec.baseLapS : DEFAULT_BASE_LAP_S;
  SELECTED_ID = spec ? spec.selectedId : DEFAULT_SELECTED_ID;
}

export interface WorldPlan {
  side: WorldSide;
  /** Pit laps for the selected driver. This is what the two worlds disagree about. */
  selectedPitLaps: number[];
  /** Compound per stint for the selected driver, in order. One more than the stops. */
  selectedCompounds: string[];
  neutralisations: Neutralisation[];
}

/**
 * A virtual safety car early enough to sit in shared history, so both races carry it
 * identically. Every entry pays the same per-lap penalty over the same laps, so the
 * order and every gap are untouched by it — it is there to be seen, not to decide
 * anything.
 */
const SHARED_VSC: Neutralisation = { kind: 'virtual_safety_car', fromLap: 5, toLap: 6 };

/** Baseline: the recorded two-stop, soft to medium to soft. */
export const BASELINE_PLAN: WorldPlan = {
  side: 'baseline',
  selectedPitLaps: [12, 24],
  selectedCompounds: ['SOFT', 'MEDIUM', 'SOFT'],
  neutralisations: [SHARED_VSC],
};

/**
 * The alternative stays out at lap 12 and takes its single stop on lap 16, while the
 * safety car is out — the stop is cheap because the field is neutralised. That
 * interruption exists only in this world, which is why it stays in the assumptions.
 */
export const ALTERNATIVE_PLAN: WorldPlan = {
  side: 'alternative',
  selectedPitLaps: [16],
  selectedCompounds: ['SOFT', 'MEDIUM'],
  neutralisations: [SHARED_VSC, { kind: 'safety_car', fromLap: 15, toLap: 17 }],
};

/** Pit loss while the race is neutralised — the field is slowed, so the stop is cheap. */
const NEUTRALISED_PIT_LOSS_S = 9.0;

export const neutralisationAt = (plan: WorldPlan, lap: number): Neutralisation | undefined =>
  plan.neutralisations.find((n) => lap >= n.fromLap && lap <= n.toLap);

export const pitLapsFor = (plan: WorldPlan, id: string): number[] => {
  if (id === SELECTED_ID) return activeSpec ? activeSpec.pitLaps : plan.selectedPitLaps;
  return ROSTER.findIndex((e) => e.id === id) % 2 === 0 ? FIELD_TWO_STOP : FIELD_ONE_STOP;
};

/** Only the selected entry's compounds are planned; the field falls back to the cycle. */
export const compoundsFor = (plan: WorldPlan, id: string): string[] | undefined => {
  if (id !== SELECTED_ID) return undefined;
  return activeSpec && activeSpec.compounds.length > 0 ? activeSpec.compounds : plan.selectedCompounds;
};

/**
 * Cumulative time at the end of each lap, per entry.
 * Index 0 is the end of lap 1. A retired entry's array stops at its final lap.
 */
export type WorldTiming = Map<string, number[]>;

/**
 * Our car starts from the back: its first lap carries this much extra time, and it runs
 * this much quicker per lap than its roster pace, so it climbs through the field all race.
 */
const SELECTED_START_DEFICIT_S = 30.0;
const SELECTED_PACE_GAIN_S = 0.4;

export function buildTiming(plan: WorldPlan): WorldTiming {
  const timing: WorldTiming = new Map();

  for (const entry of ROSTER) {
    const pitLaps = pitLapsFor(plan, entry.id);
    const ends: number[] = [];
    let elapsed = 0;
    let stintAge = 0;
    const lastLap = entry.id === RETIREMENT_ID ? Math.min(RETIREMENT_LAP, TOTAL_LAPS) : TOTAL_LAPS;

    for (let lap = 1; lap <= lastLap; lap++) {
      // Tyre loss is mildly non-linear in stint age, not runaway quadratic:
      // a 20-lap stint costs about 1.5 s/lap at the end, which is realistic.
      const tyreLoss = (entry.degPerLapS / 6) * stintAge * stintAge;
      const neutralised = neutralisationAt(plan, lap);
      let lapTime = BASE_LAP_S + entry.paceOffsetS + tyreLoss;
      if (entry.id === SELECTED_ID) {
        lapTime -= SELECTED_PACE_GAIN_S;
        if (lap === 1) lapTime += SELECTED_START_DEFICIT_S;
      }
      if (pitLaps.includes(lap)) {
        lapTime += neutralised ? NEUTRALISED_PIT_LOSS_S : PIT_LOSS_S;
        stintAge = 0;
      } else {
        stintAge += 1;
      }
      if (neutralised) {
        lapTime += NEUTRALISATION_LAP_PENALTY_S[neutralised.kind];
      }
      elapsed += lapTime;
      ends.push(elapsed);
    }
    timing.set(entry.id, ends);
  }

  return timing;
}

export interface Progress {
  /** Laps fully completed. */
  lapsCompleted: number;
  /** Lap currently being run, 1-based. Clamped to the last lap once finished. */
  lap: number;
  /** Fraction of the current lap covered, 0..1. */
  frac: number;
  /** Total laps + fraction, used for ordering. */
  distance: number;
  finished: boolean;
  retired: boolean;
  /** True while inside the pit-lane time loss on a pit lap. */
  inPit: boolean;
}

export function progressAt(
  plan: WorldPlan,
  timing: WorldTiming,
  id: string,
  t: number,
): Progress {
  const ends = timing.get(id) ?? [];
  const retiresEarly = id === RETIREMENT_ID;
  const finalEnd = ends[ends.length - 1] ?? 0;

  if (t >= finalEnd) {
    const lapsCompleted = ends.length;
    return {
      lapsCompleted,
      lap: lapsCompleted,
      frac: 1,
      distance: lapsCompleted,
      finished: !retiresEarly,
      retired: retiresEarly,
      inPit: false,
    };
  }

  let lapsCompleted = 0;
  while (lapsCompleted < ends.length && ends[lapsCompleted] <= t) lapsCompleted++;

  const lapStart = lapsCompleted === 0 ? 0 : ends[lapsCompleted - 1];
  const lapEnd = ends[lapsCompleted];
  const frac = (t - lapStart) / (lapEnd - lapStart);
  const lap = lapsCompleted + 1;

  const inPit = pitLapsFor(plan, id).includes(lap) && frac > 0.72 && frac < 0.95;

  return {
    lapsCompleted,
    lap,
    frac,
    distance: lapsCompleted + frac,
    finished: false,
    retired: false,
    inPit,
  };
}

/** Race seconds until the last entry finishes, in this world. */
export function worldDuration(timing: WorldTiming): number {
  let max = 0;
  for (const ends of timing.values()) {
    const last = ends[ends.length - 1] ?? 0;
    if (last > max) max = last;
  }
  return max;
}
