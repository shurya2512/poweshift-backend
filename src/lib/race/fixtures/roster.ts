import { EGO_PROFILES } from '@/lib/backend/profiles';
import { Participant } from '../types';

export interface FixtureEntry extends Participant {
  /** Seconds per lap slower than the fastest entry. */
  paceOffsetS: number;
  /** Tyre degradation, seconds added per lap of stint age. */
  degPerLapS: number;
}

/** Pace spread across the field, fastest first. The order is illustrative, the identities are not. */
const PACE_OFFSET_S = [
  0.0, 0.18, 0.31, 0.44, 0.52, 0.67, 0.81, 0.98, 1.12, 1.29, 1.41,
  1.58, 1.66, 1.73, 1.86, 1.94, 2.11, 2.28, 2.47, 2.69, 2.94, 4.35,
];
const DEG_PER_LAP_S = [
  0.045, 0.042, 0.048, 0.044, 0.043, 0.049, 0.046, 0.051, 0.047, 0.052, 0.050,
  0.053, 0.054, 0.051, 0.055, 0.055, 0.054, 0.052, 0.056, 0.055, 0.058, 0.061,
];

/** The real promoted entries the reports are built from, keyed by code. */
export const ROSTER: FixtureEntry[] = EGO_PROFILES.map((profile, index) => ({
  id: profile.code,
  code: profile.code,
  name: profile.name,
  team: profile.team,
  raceNumber: Number(profile.entry),
  teamColor: profile.color,
  paceOffsetS: PACE_OFFSET_S[index] ?? 3.0,
  degPerLapS: DEG_PER_LAP_S[index] ?? 0.055,
}));

export const byId = (id: string): FixtureEntry =>
  ROSTER.find((e) => e.id === id) ?? ROSTER[0];

export const codeForEntry = (entry: string): string =>
  EGO_PROFILES.find((profile) => profile.entry === entry)?.code ?? ROSTER[0].id;
