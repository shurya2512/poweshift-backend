import { RaceMessage, RaceSource, SessionRequest } from '../source';
import { FixtureRace, buildFixtureRace } from './build';
import { RaceSpec } from './report';

const TICK_HZ = 4;

/**
 * Replays a generated race on a timer. Phase 3 adds a WebSocket source behind the
 * same interface; no view knows which one is talking.
 */
export class FixtureRaceSource implements RaceSource {
  constructor(private spec: RaceSpec | null = null) {}

  private race: FixtureRace | null = null;
  private handlers = new Set<(msg: RaceMessage) => void>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private raceTimeS = 0;
  private rate = 20;

  subscribe(handler: (msg: RaceMessage) => void): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  private emit(msg: RaceMessage): void {
    for (const handler of this.handlers) handler(msg);
  }

  start(_request: SessionRequest): void {
    this.stopTimer();
    this.race = buildFixtureRace(this.spec);
    this.raceTimeS = 0;
    this.emit({ type: 'session', session: this.race.session });
    this.emit({ type: 'events', events: this.race.events });
    this.emit({ type: 'comparison', comparison: this.race.comparison });
    this.emit({ type: 'battles', battles: this.race.battles });
    this.emit({ type: 'support', state: 'ready' });
    this.tick();
    this.resume();
  }

  private tick(): void {
    if (!this.race) return;
    this.emit({ type: 'frame', frame: this.race.frameAt(this.raceTimeS) });
  }

  private stopTimer(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  pause(): void {
    this.stopTimer();
  }

  resume(): void {
    if (this.timer || !this.race) return;
    this.timer = setInterval(() => {
      const race = this.race;
      if (!race) return;
      this.raceTimeS = Math.min(race.durationS, this.raceTimeS + this.rate / TICK_HZ);
      this.tick();
      if (this.raceTimeS >= race.durationS) this.stopTimer();
    }, 1000 / TICK_HZ);
  }

  seek(raceTimeS: number): void {
    if (!this.race) return;
    this.raceTimeS = Math.max(0, Math.min(this.race.durationS, raceTimeS));
    this.tick();
  }

  setRate(rate: number): void {
    this.rate = rate;
  }

  select(_participantId: string): void {
    // Phase 1 keeps selection in session state; the fixture serves the whole field
    // every frame, so nothing needs to be re-requested.
  }

  stop(): void {
    this.stopTimer();
    this.race = null;
    this.raceTimeS = 0;
  }
}
