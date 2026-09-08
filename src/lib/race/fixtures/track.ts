import { TrackGeometry } from '../types';

const POINTS = 240;

/** A closed circuit-like loop. Deterministic, so every session draws the same track. */
function loopPoint(theta: number): [number, number] {
  const r = 1200 + 340 * Math.sin(3 * theta) + 150 * Math.cos(2 * theta);
  return [r * Math.cos(theta), r * Math.sin(theta) * 0.72];
}

export interface FixtureTrack {
  geometry: TrackGeometry;
  /** Position at a fraction (0..1) of the way round the lap, by arc length. */
  pointAt(frac: number): { x: number; y: number };
}

export function buildTrack(name: string): FixtureTrack {
  const x: number[] = [];
  const y: number[] = [];
  for (let i = 0; i < POINTS; i++) {
    const [px, py] = loopPoint((i / POINTS) * Math.PI * 2);
    x.push(px);
    y.push(py);
  }

  // Cumulative arc length, so distance round the lap maps to a real position.
  const cumulative: number[] = [0];
  for (let i = 1; i <= POINTS; i++) {
    const j = i % POINTS;
    const dx = x[j] - x[i - 1];
    const dy = y[j] - y[i - 1];
    cumulative.push(cumulative[i - 1] + Math.hypot(dx, dy));
  }
  const lapLengthM = cumulative[POINTS];

  const pointAt = (frac: number) => {
    const target = ((frac % 1) + 1) % 1 * lapLengthM;
    let i = 1;
    while (i < POINTS && cumulative[i] < target) i++;
    const span = cumulative[i] - cumulative[i - 1];
    const t = span === 0 ? 0 : (target - cumulative[i - 1]) / span;
    const j = i % POINTS;
    return {
      x: x[i - 1] + (x[j] - x[i - 1]) * t,
      y: y[i - 1] + (y[j] - y[i - 1]) * t,
    };
  };

  return { geometry: { name, x, y, lapLengthM }, pointAt };
}
