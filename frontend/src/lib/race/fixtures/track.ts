import { RouteGeometry } from '@/lib/backend/report';
import { TrackGeometry } from '../types';

const POINTS = 240;

/** A closed circuit-like loop, used only when no recorded route is available. */
function loopPoint(theta: number): [number, number] {
  const r = 1200 + 340 * Math.sin(3 * theta) + 150 * Math.cos(2 * theta);
  return [r * Math.cos(theta), r * Math.sin(theta) * 0.72];
}

export interface FixtureTrack {
  geometry: TrackGeometry;
  /** Position at a fraction (0..1) of the way round the lap, by arc length. */
  pointAt(frac: number): { x: number; y: number };
}

/** Centres a recorded centreline on the origin so it draws like the generated loop. */
function centred(route: RouteGeometry): { x: number[]; y: number[] } {
  const midX = (Math.min(...route.x_m) + Math.max(...route.x_m)) / 2;
  const midY = (Math.min(...route.y_m) + Math.max(...route.y_m)) / 2;
  return {
    x: route.x_m.map((value) => value - midX),
    y: route.y_m.map((value) => value - midY),
  };
}

export function buildTrack(name: string, route: RouteGeometry | null = null): FixtureTrack {
  let x: number[] = [];
  let y: number[] = [];
  if (route && route.x_m.length > 2) {
    ({ x, y } = centred(route));
  } else {
    for (let i = 0; i < POINTS; i++) {
      const [px, py] = loopPoint((i / POINTS) * Math.PI * 2);
      x.push(px);
      y.push(py);
    }
  }

  const count = x.length;

  // Cumulative arc length, so distance round the lap maps to a real position.
  const cumulative: number[] = [0];
  for (let i = 1; i <= count; i++) {
    const j = i % count;
    const dx = x[j] - x[i - 1];
    const dy = y[j] - y[i - 1];
    cumulative.push(cumulative[i - 1] + Math.hypot(dx, dy));
  }
  const lapLengthM = cumulative[count];

  const pointAt = (frac: number) => {
    const target = ((frac % 1) + 1) % 1 * lapLengthM;
    let i = 1;
    while (i < count && cumulative[i] < target) i++;
    const span = cumulative[i] - cumulative[i - 1];
    const t = span === 0 ? 0 : (target - cumulative[i - 1]) / span;
    const j = i % count;
    return {
      x: x[i - 1] + (x[j] - x[i - 1]) * t,
      y: y[i - 1] + (y[j] - y[i - 1]) * t,
    };
  };

  return { geometry: { name, x, y, lapLengthM }, pointAt };
}
