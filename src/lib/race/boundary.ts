import { RaceMessage } from './source';
import { EnergyState, ParticipantState, RaceFrame, TyreState } from './types';
import { Valued, unsupported } from './valued';

/**
 * Coercion at the untrusted boundary.
 *
 * This is the one place runtime shape-checking earns its keep: a value the backend
 * omits becomes `unsupported` with a reason, so a missing battery reads as unavailable
 * rather than as a plausible number the view invents.
 */

const MISSING = (field: string) => unsupported(`${field} was not supplied by the backend`);

function valued<T>(raw: unknown, field: string): Valued<T> {
  if (raw === null || raw === undefined) return MISSING(field);
  if (typeof raw !== 'object' || !('status' in (raw as object))) return MISSING(field);
  const v = raw as Valued<T>;
  if (v.status === 'unsupported') return v;
  if (!('value' in v) || v.value === null || v.value === undefined) return MISSING(field);
  return v;
}

function tyre(raw: Record<string, unknown> | undefined): TyreState {
  return {
    compound: valued(raw?.compound, 'Tyre compound'),
    ageLaps: valued(raw?.ageLaps, 'Tyre age'),
    conditionPct: valued(raw?.conditionPct, 'Tyre condition'),
  };
}

function energy(raw: Record<string, unknown> | undefined): EnergyState {
  return {
    storedMj: valued(raw?.storedMj, 'Stored energy'),
    requestedKw: valued(raw?.requestedKw, 'Requested power'),
    deliveredKw: valued(raw?.deliveredKw, 'Delivered power'),
    recoveredKw: valued(raw?.recoveredKw, 'Recovered power'),
    curtailedKw: valued(raw?.curtailedKw, 'Curtailed power'),
  };
}

function participantState(raw: Record<string, unknown>): ParticipantState {
  const traffic = (raw.traffic ?? {}) as Record<string, unknown>;
  return {
    participantId: String(raw.participantId ?? ''),
    participation: (raw.participation as ParticipantState['participation']) ?? 'running',
    rank: Number(raw.rank ?? 0),
    lap: Number(raw.lap ?? 0),
    distanceM: Number(raw.distanceM ?? 0),
    x: Number(raw.x ?? 0),
    y: Number(raw.y ?? 0),
    speedKmh: valued(raw.speedKmh, 'Speed'),
    gapS: valued(raw.gapS, 'Gap'),
    intervalS: valued(raw.intervalS, 'Interval'),
    sector: valued(raw.sector, 'Sector'),
    lapsDown: Number(raw.lapsDown ?? 0),
    tyre: tyre(raw.tyre as Record<string, unknown> | undefined),
    energy: energy(raw.energy as Record<string, unknown> | undefined),
    fuelKg: valued(raw.fuelKg, 'Fuel'),
    paceTarget: valued(raw.paceTarget, 'Pace target'),
    energyTarget: valued(raw.energyTarget, 'Energy target'),
    strategyInstruction: valued(raw.strategyInstruction, 'Strategy instruction'),
    traffic: {
      aheadId: traffic.aheadId as string | undefined,
      behindId: traffic.behindId as string | undefined,
      gapAheadS: valued(traffic.gapAheadS, 'Gap ahead'),
      gapBehindS: valued(traffic.gapBehindS, 'Gap behind'),
    },
  };
}

function frame(raw: Record<string, unknown>): RaceFrame {
  const world = (side: 'baseline' | 'alternative') => {
    const w = (raw[side] ?? {}) as Record<string, unknown>;
    return {
      ...(w as unknown as RaceFrame['baseline']),
      field: ((w.field ?? []) as Record<string, unknown>[]).map(participantState),
    };
  };
  const delta = (raw.delta ?? {}) as Record<string, unknown>;
  return {
    ...(raw as unknown as RaceFrame),
    baseline: world('baseline'),
    alternative: world('alternative'),
    delta: {
      positionDelta: valued(delta.positionDelta, 'Position delta'),
      timeDeltaS: valued(delta.timeDeltaS, 'Time delta'),
      strategyDivergence: (delta.strategyDivergence as string[]) ?? [],
    },
  };
}

/** Returns null for a message shape the frontend does not recognise. */
export function coerceMessage(raw: unknown): RaceMessage | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const msg = raw as Record<string, unknown>;

  switch (msg.type) {
    case 'session':
    case 'events':
    case 'comparison':
    case 'battles':
    case 'support':
    case 'error':
      return msg as unknown as RaceMessage;
    case 'frame':
      return { type: 'frame', frame: frame(msg.frame as Record<string, unknown>) };
    default:
      return null;
  }
}
