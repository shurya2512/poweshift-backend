import { RaceMessage, RaceSource, SessionRequest } from './source';
import { coerceMessage } from './boundary';

const DEFAULT_URL = 'ws://localhost:8000/api/stream/full-race';

/**
 * The real backend behind the same interface the fixture uses. No view changes when
 * this replaces `FixtureRaceSource`.
 *
 * Every message is coerced at this boundary: a field the backend omits becomes an
 * unsupported value with a reason, never a zero and never an average-car substitute.
 */
export class WebSocketRaceSource implements RaceSource {
  private ws: WebSocket | null = null;
  private handlers = new Set<(msg: RaceMessage) => void>();
  private url: string;

  constructor(url: string = DEFAULT_URL) {
    this.url = url;
  }

  subscribe(handler: (msg: RaceMessage) => void): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  private emit(msg: RaceMessage): void {
    for (const handler of this.handlers) handler(msg);
  }

  private send(payload: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(payload));
  }

  start(request: SessionRequest): void {
    this.ws?.close();
    const ws = new WebSocket(this.url);
    this.ws = ws;

    ws.onopen = () => this.send({ type: 'start', ...request });

    ws.onmessage = (event) => {
      if (this.ws !== ws) return;
      const message = coerceMessage(JSON.parse(event.data));
      if (message) this.emit(message);
    };

    ws.onerror = () => {
      if (this.ws === ws) {
        this.emit({ type: 'error', code: 'connection', message: `Could not reach ${this.url}` });
      }
    };
  }

  pause(): void {
    this.send({ type: 'pause' });
  }

  resume(): void {
    this.send({ type: 'resume' });
  }

  seek(raceTimeS: number): void {
    this.send({ type: 'seek', t: raceTimeS });
  }

  setRate(rate: number): void {
    this.send({ type: 'rate', value: rate });
  }

  select(participantId: string): void {
    this.send({ type: 'select', participantId });
  }

  stop(): void {
    this.send({ type: 'stop' });
    this.ws?.close();
    this.ws = null;
  }
}
