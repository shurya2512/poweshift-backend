import { WorldSide } from '../types';
import { ROSTER } from './roster';

export const TOTAL_LAPS = 30;
export const BASE_LAP_S = 88.0;
export const PIT_LOSS_S = 22.0;
/** Extra seconds per lap while a safety car is out. */
const SAFETY_CAR_LAP_PENALTY_S = 34.0;

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

export const SELECTED_ID = 'VER';
export const BRANCH_LAP = 12;

export interface WorldPlan {
  side: WorldSide;
  /** Pit laps for the selected driver. This is what the two worlds disagree about. */
  selectedPitLaps: number[];
  safetyCar?: { fromLap: number; toLap: number };
}

/** Baseline: the recorded two-stop. Alternative: stay out at 12, one stop on 20. */
export const BASELINE_PLAN: WorldPlan = {
  side: 'baseline',
  selectedPitLaps: [12, 24],
};

/**
 * The alternative stays out at lap 12 and takes its single stop on lap 16, while the
 * safety car is out — the stop is cheap because the field is neutralised. That
 * interruption exists only in this world, which is why it stays in the assumptions.
 */
export const ALTERNATIVE_PLAN: WorldPlan = {
  side: 'alternative',
  selectedPitLaps: [16],
  safetyCar: { fromLap: 15, toLap: 17 },
};

/** Pit loss while the race is neutralised. */
const SAFETY_CAR_PIT_LOSS_S = 9.0;

export const pitLapsFor = (plan: WorldPlan, id: string): number[] => {
  if (id === SELECTED_ID) return plan.selectedPitLaps;
  return ROSTER.findIndex((e) => e.id === id) % 2 === 0 ? FIELD_TWO_STOP : FIELD_ONE_STOP;
};

/**
 * Cumulative time at the end of each lap, per entry.
 * Index 0 is the end of lap 1. A retired entry's array stops at its final lap.
 */
export type WorldTiming = Map<string, number[]>;

export function buildTiming(plan: WorldPlan): WorldTiming {
  const timing: WorldTiming = new Map();

  for (const entry of ROSTER) {
    const pitLaps = pitLapsFor(plan, entry.id);
    const ends: number[] = [];
    let elapsed = 0;
    let stintAge = 0;
    const lastLap = entry.id === RETIREMENT_ID ? RETIREMENT_LAP : TOTAL_LAPS;

    for (let lap = 1; lap <= lastLap; lap++) {
      // Tyre loss is mildly non-linear in stint age, not runaway quadratic:
      // a 20-lap stint costs about 1.5 s/lap at the end, which is realistic.
      const tyreLoss = (entry.degPerLapS / 6) * stintAge * stintAge;
      const neutralised =
        !!plan.safetyCar && lap >= plan.safetyCar.fromLap && lap <= plan.safetyCar.toLap;
      let lapTime = BASE_LAP_S + entry.paceOffsetS + tyreLoss;
      if (pitLaps.includes(lap)) {
        lapTime += neutralised ? SAFETY_CAR_PIT_LOSS_S : PIT_LOSS_S;
        stintAge = 0;
      } else {
        stintAge += 1;
      }
      if (neutralised) {
        lapTime += SAFETY_CAR_LAP_PENALTY_S;
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
