import { FlagState, RacePhase, RaceWorld, ScenarioIdentity, WorldSide } from '../types';
import { ROSTER } from './roster';
import { FixtureTrack } from './track';
import { buildParticipantState } from './state';
import {
  Progress,
  TOTAL_LAPS,
  WorldPlan,
  WorldTiming,
  compoundsFor,
  neutralisationAt,
  pitLapsFor,
  progressAt,
} from './model';

interface Ranked {
  entry: (typeof ROSTER)[number];
  progress: Progress;
  /** Race time this entry took the flag, or undefined while still running. */
  finishTimeS?: number;
  /** Race time at the end of lap one — the slower it is, the further back the car started. */
  lapOneS: number;
}

/**
 * Running entries by distance covered, finished entries by when they took the flag,
 * retired entries at the back. Finished entries all sit at the same distance, so
 * without the finish-time tie-break they would order arbitrarily. Running entries at
 * the same distance — everyone at the start — order by lap one, so the grid holds.
 */
function order(rows: Ranked[]): Ranked[] {
  const finished = rows.filter((r) => r.progress.finished);
  const running = rows.filter((r) => !r.progress.finished && !r.progress.retired);
  const retired = rows.filter((r) => r.progress.retired);
  finished.sort((a, b) => (a.finishTimeS ?? 0) - (b.finishTimeS ?? 0));
  running.sort((a, b) => b.progress.distance - a.progress.distance || a.lapOneS - b.lapOneS);
  retired.sort((a, b) => b.progress.distance - a.progress.distance);
  return [...finished, ...running, ...retired];
}

/** The flag follows the neutralisation the leader is inside, and its kind. */
function flagAt(plan: WorldPlan, leaderLap: number): FlagState {
  return neutralisationAt(plan, leaderLap)?.kind ?? 'green';
}

function phaseAt(allDone: boolean, t: number): RacePhase {
  if (allDone) return 'finished';
  return t <= 0 ? 'formation' : 'racing';
}

export function buildWorld(
  side: WorldSide,
  scenario: ScenarioIdentity,
  plan: WorldPlan,
  timing: WorldTiming,
  track: FixtureTrack,
  t: number,
): RaceWorld {
  const rows: Ranked[] = ROSTER.map((entry) => {
    const ends = timing.get(entry.id) ?? [];
    return {
      entry,
      progress: progressAt(plan, timing, entry.id, t),
      finishTimeS: ends[ends.length - 1],
      lapOneS: ends[0] ?? Infinity,
    };
  });
  const ordered = order(rows);
  const leaderDistance = ordered[0]?.progress.distance ?? 0;

  const field = ordered.map((row, i) =>
    buildParticipantState({
      side,
      entry: row.entry,
      progress: row.progress,
      pitLaps: pitLapsFor(plan, row.entry.id),
      compounds: compoundsFor(plan, row.entry.id),
      track,
      raceTimeS: t,
      rank: i + 1,
      leaderDistance,
      aheadDistance: i === 0 ? undefined : ordered[i - 1].progress.distance,
      aheadId: i === 0 ? undefined : ordered[i - 1].entry.id,
      behindId: i === ordered.length - 1 ? undefined : ordered[i + 1].entry.id,
      finishTimeS: row.finishTimeS,
      leaderFinishTimeS: ordered[0]?.finishTimeS,
      aheadFinishTimeS: i === 0 ? undefined : ordered[i - 1].finishTimeS,
    }),
  );

  const leaderLap = ordered[0]?.progress.lap ?? 1;
  const allDone = rows.every((r) => r.progress.finished || r.progress.retired);
  const neutralised = neutralisationAt(plan, leaderLap);

  return {
    side,
    scenario,
    leaderLap,
    totalLaps: TOTAL_LAPS,
    phase: phaseAt(allDone, t),
    flag: allDone ? 'chequered' : flagAt(plan, leaderLap),
    weather: 'Dry, 27 °C track',
    trackCondition: allDone ? 'Race over' : neutralised ? 'Neutralised' : 'Racing',
    field,
    finished: allDone,
  };
}
