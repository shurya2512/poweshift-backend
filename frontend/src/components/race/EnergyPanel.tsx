import React from 'react';
import { EnergyState } from '@/lib/race/types';
import { isSupported } from '@/lib/race/valued';
import { Eyebrow } from './primitives';
import { StatusValue } from './StatusValue';

const MAX_MJ = 4.0;

const Flow = ({ label, value, tone }: { label: string; value: EnergyState[keyof EnergyState]; tone: string }) => (
  <div className="flex items-baseline justify-between gap-2">
    <span className="text-[10px] uppercase tracking-wider text-white/35">{label}</span>
    <span className={`text-[11px] font-semibold tabular-nums ${tone}`}>
      <StatusValue value={value as never} format={(v) => `${v} kW`} />
    </span>
  </div>
);

/**
 * Stored energy and the four flows kept apart.
 *
 * A single net battery number never stands in for these — deployment, recovery and
 * curtailment are different quantities and the spec requires them shown as such.
 */
export function EnergyPanel({ energy }: { energy: EnergyState }) {
  const stored = energy.storedMj;
  const pct = isSupported(stored) ? Math.max(0, Math.min(100, (stored.value / MAX_MJ) * 100)) : null;

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <Eyebrow>Stored energy</Eyebrow>
        <span className="text-sm font-bold tabular-nums text-white">
          <StatusValue value={stored} format={(v) => `${v.toFixed(2)} MJ`} />
        </span>
      </div>

      {pct === null ? (
        <div className="flex h-5 w-full items-center justify-center rounded-md border border-dashed border-white/10 bg-white/[0.02]">
          <span className="text-[9px] uppercase tracking-widest text-white/25">no state of charge available</span>
        </div>
      ) : (
        <div className="h-5 w-full overflow-hidden rounded-md border border-white/[0.08] bg-neutral-900">
          <div className="h-full bg-gradient-to-r from-sky-500/70 to-sky-300/70" style={{ width: `${pct}%` }} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-x-5 gap-y-1.5 border-t border-white/[0.06] pt-2.5">
        <Flow label="Requested" value={energy.requestedKw} tone="text-white/70" />
        <Flow label="Delivered" value={energy.deliveredKw} tone="text-rose-300/80" />
        <Flow label="Recovered" value={energy.recoveredKw} tone="text-emerald-300/80" />
        <Flow label="Curtailed" value={energy.curtailedKw} tone="text-amber-300/80" />
      </div>
    </div>
  );
}
