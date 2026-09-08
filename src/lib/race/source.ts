import { Battle, ComparisonResult, RaceEvent, RaceFrame, SessionInfo, SupportState } from './types';

/** What the view asks for. The source decides how to satisfy it. */
export interface SessionRequest {
  season: number;
  event: string;
  scenarioId: string;
  selectedParticipantId?: string;
}

export type RaceMessage =
  | { type: 'session'; session: SessionInfo }
  | { type: 'frame'; frame: RaceFrame }
  | { type: 'events'; events: RaceEvent[] }
  | { type: 'comparison'; comparison: ComparisonResult }
  | { type: 'battles'; battles: Battle[] }
  | { type: 'support'; state: SupportState; reason?: string }
  | { type: 'error'; code: string; message: string };

/**
 * The single door every race message comes through.
 *
 * Phase 1 ships `FixtureRaceSource`; Phase 3 adds a WebSocket implementation of the
 * same interface. No component outside `lib/race` imports a concrete source.
 */
export interface RaceSource {
  start(request: SessionRequest): void;
  pause(): void;
  resume(): void;
  seek(raceTimeS: number): void;
  setRate(rate: number): void;
  stop(): void;
  select(participantId: string): void;
  subscribe(handler: (msg: RaceMessage) => void): () => void;
}
