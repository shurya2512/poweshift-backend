import React from 'react';
import { SourceStatus, Valued } from '@/lib/race/valued';

const MARKS: Record<SourceStatus, { mark: string; className: string; title: string }> = {
  observed: { mark: 'O', className: 'text-sky-300/70 border-sky-300/30', title: 'Observed' },
  inferred: { mark: 'I', className: 'text-amber-300/70 border-amber-300/30', title: 'Inferred' },
  predicted: { mark: 'P', className: 'text-violet-300/70 border-violet-300/30', title: 'Predicted' },
  simulated: { mark: 'S', className: 'text-emerald-300/70 border-emerald-300/30', title: 'Simulated' },
  unsupported: { mark: '—', className: 'text-white/25 border-white/10', title: 'Unsupported' },
};

export function StatusMark({ status, detail }: { status: SourceStatus; detail?: string }) {
  const m = MARKS[status];
  return (
    <span
      title={detail ? `${m.title} — ${detail}` : m.title}
      className={`inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[4px] border text-[8px] font-bold leading-none ${m.className}`}
    >
      {m.mark}
    </span>
  );
}

/**
 * Interval bounds arrive as raw floats, so an arithmetic bound reads as
 * `0.44000000000000006`. Four significant figures drops the binary noise without
 * moving the bound anywhere a reader could see.
 */
const trim = (n: number): string => String(Number(n.toPrecision(4)));

interface StatusValueProps<T> {
  value: Valued<T>;
  format?: (v: T) => string;
  className?: string;
  /** Hide the status mark where a whole region already declares one status. */
  hideMark?: boolean;
  /**
   * Drop the uncertainty interval where there is no room to print it. Only for a
   * summary that leads somewhere the interval is shown in full — a clipped range is
   * worse than none, but a range that is never reachable is not an option.
   */
  hideInterval?: boolean;
}

/**
 * The only way a supplied value reaches the screen.
 *
 * An unsupported value renders the word unavailable and its reason — never a zero,
 * an average, or any other stand-in number.
 */
export function StatusValue<T>({
  value,
  format,
  className = '',
  hideMark,
  hideInterval,
}: StatusValueProps<T>) {
  if (value.status === 'unsupported') {
    return (
      <span className={`inline-flex items-center gap-1.5 ${className}`} title={value.reason}>
        {!hideMark && <StatusMark status="unsupported" detail={value.reason} />}
        <span className="text-white/25 italic">unavailable</span>
      </span>
    );
  }

  const text = format ? format(value.value) : String(value.value);
  const detail =
    value.status === 'observed'
      ? `${value.source}, race time ${value.observedAtS.toFixed(1)} s`
      : value.status === 'simulated'
        ? `scenario ${value.scenarioId}${value.assumptions.length ? ` — ${value.assumptions.join('; ')}` : ''}`
        : value.status === 'predicted'
          ? `cutoff ${value.cutoffS.toFixed(0)} s, horizon ${value.horizonS.toFixed(0)} s`
          : undefined;

  const interval =
    !hideInterval && (value.status === 'inferred' || value.status === 'predicted') && value.interval
      ? `${trim(value.interval[0])}–${trim(value.interval[1])}`
      : null;

  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      {!hideMark && <StatusMark status={value.status} detail={detail} />}
      <span>{text}</span>
      {interval && <span className="text-[10px] text-white/30">[{interval}]</span>}
    </span>
  );
}

/** Legend for the four supported statuses plus unavailable. */
export function StatusLegend() {
  return (
    <div className="flex flex-wrap items-center gap-4">
      {(Object.keys(MARKS) as SourceStatus[]).map((s) => (
        <span key={s} className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-white/35">
          <StatusMark status={s} />
          {s === 'unsupported' ? 'unavailable' : s}
        </span>
      ))}
    </div>
  );
}
