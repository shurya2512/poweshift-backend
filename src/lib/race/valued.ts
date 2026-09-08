/**
 * Source status for every value the frontend displays.
 *
 * The spec requires each value to carry where it came from, all the way down from
 * a race result to a telemetry detail. `unsupported` deliberately carries no `value`
 * field, so a fallback like `soc ?? 4.0` fails to compile rather than inventing a number.
 */
export type SourceStatus =
  | 'observed'
  | 'inferred'
  | 'predicted'
  | 'simulated'
  | 'unsupported';

export interface Observed<T> {
  status: 'observed';
  value: T;
  source: string;
  /** Race time in seconds at which the observation was taken. */
  observedAtS: number;
}

export interface Inferred<T> {
  status: 'inferred';
  value: T;
  interval?: [number, number];
  /** Unresolved alternatives when the estimate does not collapse to one answer. */
  alternatives?: T[];
}

export interface Predicted<T> {
  status: 'predicted';
  value: T;
  interval?: [number, number];
  /** Observation cutoff the forecast was made from, in race seconds. */
  cutoffS: number;
  /** How far beyond the cutoff the forecast is supported, in seconds. */
  horizonS: number;
}

export interface Simulated<T> {
  status: 'simulated';
  value: T;
  scenarioId: string;
  assumptions: string[];
}

export interface Unsupported {
  status: 'unsupported';
  reason: string;
}

export type Valued<T> =
  | Observed<T>
  | Inferred<T>
  | Predicted<T>
  | Simulated<T>
  | Unsupported;

/** Narrows to the variants that carry a value. Use before reading `.value`. */
export function isSupported<T>(
  v: Valued<T>,
): v is Observed<T> | Inferred<T> | Predicted<T> | Simulated<T> {
  return v.status !== 'unsupported';
}

/** The value, or `undefined` when unsupported. Never substitutes a default. */
export function valueOf<T>(v: Valued<T>): T | undefined {
  return isSupported(v) ? v.value : undefined;
}

export const observed = <T>(value: T, source: string, observedAtS: number): Observed<T> => ({
  status: 'observed',
  value,
  source,
  observedAtS,
});

export const inferred = <T>(value: T, interval?: [number, number]): Inferred<T> => ({
  status: 'inferred',
  value,
  interval,
});

export const simulated = <T>(value: T, scenarioId: string, assumptions: string[] = []): Simulated<T> => ({
  status: 'simulated',
  value,
  scenarioId,
  assumptions,
});

export const unsupported = (reason: string): Unsupported => ({
  status: 'unsupported',
  reason,
});
