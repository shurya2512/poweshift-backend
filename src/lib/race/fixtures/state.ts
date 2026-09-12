import { EnergyState, ParticipantState, ParticipationState, TyreState, WorldSide } from '../types';
import { Valued, inferred, observed, simulated, unsupported } from '../valued';
import { FixtureTrack } from './track';
import { FixtureEntry } from './roster';
import { NO_ENERGY_TELEMETRY_ID, Progress } from './model';

const COMPOUNDS = ['SOFT', 'MEDIUM', 'HARD'];

/**
 * Baseline is a recorded world, so its values are observed or inferred.
 * The alternative never happened, so every one of its values is simulated.
 */
function mark<T>(side: WorldSide, value: T, at: number, kind: 'measured' | 'estimated'): Valued<T> {
  if (side === 'alternative') return simulated(value, 'alt-one-stop', ['fixed-opponent replay']);
  return kind === 'measured' ? observed(value, 'timing feed', at) : inferred(value);
}

function speedKmh(p: Progress): number {
  if (p.inPit) return 62;
  const phase = p.frac * Math.PI * 2;
  return 215 + 78 * Math.sin(3 * phase) + 34 * Math.cos(5 * phase);
}

function stintAge(pitLaps: number[], lap: number): number {
  const last = pitLaps.filter((l) => l <= lap).pop() ?? 0;
  return lap - last;
}

function tyre(
  side: WorldSide,
  pitLaps: number[],
  compounds: string[] | undefined,
  p: Progress,
  t: number,
): TyreState {
  const stintIndex = pitLaps.filter((l) => l <= p.lap).length;
  const age = stintAge(pitLaps, p.lap);
  // An entry whose stints were planned runs those compounds; the rest of the field has
  // no supplied plan, so it cycles the three dry compounds in order.
  const compound = compounds?.[stintIndex] ?? COMPOUNDS[stintIndex % COMPOUNDS.length];
  return {
    compound: mark(side, compound, t, 'measured'),
    ageLaps: mark(side, age, t, 'measured'),
    conditionPct: mark(side, Math.max(8, 100 - age * 3.4), t, 'estimated'),
  };
}

/**
 * Five separate energy quantities. A net battery number never stands in for these.
 * One entry has no coverage at all and stays unsupported throughout.
 */
function energy(side: WorldSide, entry: FixtureEntry, p: Progress, t: number): EnergyState {
  if (entry.id === NO_ENERGY_TELEMETRY_ID) {
    const reason = 'No energy telemetry coverage for this entry';
    return {
      storedMj: unsupported(reason),
      requestedKw: unsupported(reason),
      deliveredKw: unsupported(reason),
      recoveredKw: unsupported(reason),
      curtailedKw: unsupported(reason),
    };
  }

  const phase = p.frac * Math.PI * 2;
  const swing = Math.sin(2 * phase);
  const stored = p.inPit ? 3.4 : 2.6 + 1.3 * swing;
  const deploying = Math.cos(2 * phase) < 0;
  const magnitude = p.inPit ? 0 : Math.abs(Math.cos(2 * phase)) * 340;

  return {
    storedMj: mark(side, Number(stored.toFixed(2)), t, 'estimated'),
    requestedKw: mark(side, Math.round(deploying ? magnitude * 1.06 : 0), t, 'estimated'),
    deliveredKw: mark(side, Math.round(deploying ? magnitude : 0), t, 'estimated'),
    recoveredKw: mark(side, Math.round(deploying ? 0 : magnitude * 0.78), t, 'estimated'),
    curtailedKw: mark(side, Math.round(deploying ? magnitude * 0.06 : 0), t, 'estimated'),
  };
}

export interface StateInput {
  side: WorldSide;
  entry: FixtureEntry;
  progress: Progress;
  pitLaps: number[];
  /** Planned compound per stint, when a plan was supplied for this entry. */
  compounds?: string[];
  track: FixtureTrack;
  raceTimeS: number;
  rank: number;
  leaderDistance: number;
  aheadDistance?: number;
  aheadId?: string;
  behindId?: string;
  /** Race time this entry took the flag. Used once distance stops separating the field. */
  finishTimeS?: number;
  leaderFinishTimeS?: number;
  aheadFinishTimeS?: number;
}

function participation(p: Progress): ParticipationState {
  if (p.retired) return 'retired';
  if (p.finished) return 'finished';
  return p.inPit ? 'in_pit' : 'running';
}

/** Gap in seconds, from a distance difference in laps and this entry's own pace. */
const gapFrom = (laps: number, entry: FixtureEntry): number =>
  Number((laps * (88 + entry.paceOffsetS)).toFixed(2));

export function buildParticipantState(input: StateInput): ParticipantState {
  const { side, entry, progress: p, track, raceTimeS: t, pitLaps } = input;
  const point = track.pointAt(p.frac);
  const behindLeaderLaps = input.leaderDistance - p.distance;
  const lapsDown = Math.floor(behindLeaderLaps);
  const gapAhead =
    input.aheadDistance === undefined ? undefined : input.aheadDistance - p.distance;

  // Every finisher sits at the same distance, so a distance-derived gap collapses to
  // zero at the flag. A classified entry is separated by when it crossed the line.
  const finishGap = (otherFinishS: number | undefined): number | undefined =>
    p.finished && input.finishTimeS !== undefined && otherFinishS !== undefined
      ? Number((input.finishTimeS - otherFinishS).toFixed(2))
      : undefined;

  const gapS = finishGap(input.leaderFinishTimeS) ?? gapFrom(behindLeaderLaps, entry);
  const intervalS =
    gapAhead === undefined ? undefined : finishGap(input.aheadFinishTimeS) ?? gapFrom(gapAhead, entry);

  return {
    participantId: entry.id,
    participation: participation(p),
    rank: input.rank,
    lap: p.lap,
    distanceM: p.frac * track.geometry.lapLengthM,
    x: point.x,
    y: point.y,
    speedKmh: mark(side, Math.round(speedKmh(p)), t, 'measured'),
    gapS: mark(side, gapS, t, 'measured'),
    intervalS:
      intervalS === undefined
        ? unsupported('Leader has no car ahead')
        : mark(side, intervalS, t, 'measured'),
    sector: mark(side, Math.min(3, Math.floor(p.frac * 3) + 1), t, 'measured'),
    lapsDown: lapsDown > 0 ? lapsDown : 0,
    tyre: tyre(side, pitLaps, input.compounds, p, t),
    energy: energy(side, entry, p, t),
    fuelKg: mark(side, Number(Math.max(2, 104 - p.distance * 3.3).toFixed(1)), t, 'estimated'),
    paceTarget: mark(side, stintAge(pitLaps, p.lap) > 10 ? 'Manage' : 'Push', t, 'estimated'),
    energyTarget: mark(side, p.inPit ? 'Recharge' : 'Balanced deployment', t, 'estimated'),
    strategyInstruction: unsupported('Team radio and instructions are not supplied'),
    traffic: {
      aheadId: input.aheadId,
      behindId: input.behindId,
      gapAheadS:
        gapAhead === undefined
          ? unsupported('Leader has no car ahead')
          : mark(side, gapFrom(gapAhead, entry), t, 'measured'),
      gapBehindS: unsupported('Not supplied by the fixture source'),
    },
  };
}
