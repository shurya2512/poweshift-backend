import React from 'react';
import { Participant, ParticipantState } from '@/lib/race/types';
import { Valued, isSupported } from '@/lib/race/valued';
import { Eyebrow, Panel, formatGap } from '../primitives';
import { StatusValue } from '../StatusValue';
import { TyreValue } from '../TyreMarker';

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-white/[0.05] py-2">
      <span className="shrink-0 text-[10px] uppercase tracking-wider text-white/35">{label}</span>
      <span className="text-right text-[12px] font-semibold text-white/85">{children}</span>
    </div>
  );
}

/**
 * A filled bar for a supplied quantity. An unsupported one draws an empty dashed
 * track and says so — it never renders as an empty bar that reads like zero.
 */
function Meter({ value, max, tone }: { value: Valued<number>; max: number; tone: string }) {
  if (!isSupported(value)) {
    return (
      <div
        className="flex h-4 w-full items-center justify-center rounded border border-dashed border-white/10 bg-white/[0.02]"
        title={value.reason}
      >
        <span className="text-[8px] uppercase tracking-widest text-white/25">not available</span>
      </div>
    );
  }
  const pct = Math.max(0, Math.min(100, (value.value / max) * 100));
  return (
    <div className="h-4 w-full overflow-hidden rounded border border-white/[0.08] bg-black/50">
      <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

/**
 * Each sector has its own colour rather than a number, so which third of the lap the
 * car is in reads at a glance. The sector still names itself on hover, and a sector
 * the source cannot supply leaves all three unlit and says so.
 */
const SECTOR_COLOR: Record<number, string> = { 1: '#38bdf8', 2: '#fbbf24', 3: '#a78bfa' };

function Sector({ value }: { value: Valued<number> }) {
  const current = isSupported(value) ? value.value : null;
  return (
    <span className="flex items-center gap-1.5">
      {[1, 2, 3].map((s) => {
        const lit = current === s;
        return (
          <span
            key={s}
            title={`Sector ${s}`}
            className="h-2.5 w-7 rounded-full transition-colors"
            style={{
              background: lit ? SECTOR_COLOR[s] : 'rgba(255,255,255,0.08)',
              boxShadow: lit ? `0 0 10px ${SECTOR_COLOR[s]}80` : undefined,
            }}
          />
        );
      })}
      {current === null && <span className="ml-1 text-[10px] italic text-white/25">unavailable</span>}
    </span>
  );
}

const MAX_STORED_MJ = 4.0;

/** Our car: what it is running on, how fast, where on the lap, and how much energy it is holding. */
export function OurCarPanel({
  driver,
  car,
  state,
}: {
  driver: Participant | null;
  car?: string;
  state: ParticipantState | undefined;
}) {
  return (
    <Panel className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-white/[0.07] px-4 py-3.5">
        <div className="flex items-center gap-2.5">
          <span
            className="h-7 w-1 shrink-0 rounded-full"
            style={{ background: driver?.teamColor ?? 'rgba(255,255,255,0.2)' }}
          />
          <div className="min-w-0">
            <p className="truncate text-[13px] font-bold text-white">
              {driver ? `${driver.code} · ${driver.name}` : 'No entry selected'}
            </p>
            <p className="truncate text-[10px] uppercase tracking-widest text-white/35">
              {driver?.team ?? '—'}
              {car ? ` · ${car}` : ''}
            </p>
          </div>
        </div>
      </div>

      {!state ? (
        <p className="p-5 text-[11px] italic text-white/25">This entry is not present in the race.</p>
      ) : (
        <div className="flex flex-col gap-4 px-4 py-3.5">
          <div>
            <Line label="Position">
              <span className="text-lg font-black tabular-nums text-white">P{state.rank}</span>
            </Line>
            <Line label="Gap to leader">
              <StatusValue value={state.gapS} format={formatGap} />
            </Line>
            <Line label="Lap">
              L{state.lap}
              {state.lapsDown > 0 && <span className="ml-1 text-amber-300/70">+{state.lapsDown}L</span>}
            </Line>
          </div>

          {/* Energy leads: it is the quantity this car is being driven to manage, and
              the two bars read better stacked with the live one on top. */}
          <div>
            <div className="mb-1.5 flex items-baseline justify-between">
              <Eyebrow>Stored energy</Eyebrow>
              <span className="text-[13px] font-black tabular-nums text-white">
                <StatusValue value={state.energy.storedMj} format={(v) => `${v.toFixed(2)} MJ`} />
              </span>
            </div>
            <Meter
              value={state.energy.storedMj}
              max={MAX_STORED_MJ}
              tone="bg-gradient-to-r from-sky-500/80 to-sky-300/80"
            />
            {/* Deployment, recovery and curtailment are separate quantities — a single
                net battery figure never stands in for them. */}
            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
              {(
                [
                  ['Requested', state.energy.requestedKw, 'text-white/60'],
                  ['Delivered', state.energy.deliveredKw, 'text-rose-300/80'],
                  ['Recovered', state.energy.recoveredKw, 'text-emerald-300/80'],
                  ['Curtailed', state.energy.curtailedKw, 'text-amber-300/80'],
                ] as const
              ).map(([label, value, tone]) => (
                <span key={label} className="flex items-baseline justify-between gap-2">
                  <span className="text-[9px] uppercase tracking-wider text-white/30">{label}</span>
                  <span className={`text-[10px] font-semibold tabular-nums ${tone}`}>
                    <StatusValue value={value} format={(v) => `${v} kW`} hideMark />
                  </span>
                </span>
              ))}
            </div>
          </div>

          <div>
            <Eyebrow className="mb-1.5">Tyre condition</Eyebrow>
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="flex items-center gap-2">
                <TyreValue value={state.tyre.compound} size="md" />
                <span className="text-[12px] font-semibold text-white/85">
                  <StatusValue value={state.tyre.compound} hideMark />
                </span>
              </span>
              <span className="text-[11px] tabular-nums text-white/50">
                <StatusValue value={state.tyre.ageLaps} format={(v) => `${v} laps old`} hideMark />
              </span>
            </div>
            <Meter value={state.tyre.conditionPct} max={100} tone="bg-gradient-to-r from-rose-500/70 to-amber-300/80" />
            <p className="mt-1.5 text-[11px] font-semibold tabular-nums text-white/80">
              <StatusValue value={state.tyre.conditionPct} format={(v) => `${v.toFixed(0)}% left`} />
            </p>
          </div>

          <div>
            <Line label="Speed">
              <span className="text-lg font-black tabular-nums text-white">
                <StatusValue value={state.speedKmh} format={(v) => `${v}`} hideMark />
              </span>
              <span className="ml-1 text-[10px] font-medium text-white/40">km/h</span>
            </Line>
            <Line label="Sector">
              <Sector value={state.sector} />
            </Line>
            <Line label="Fuel">
              <StatusValue value={state.fuelKg} format={(v) => `${v} kg`} hideMark />
            </Line>
          </div>

          <div className="border-t border-white/[0.05] pt-2">
            <Line label="Pace target">
              <StatusValue value={state.paceTarget} hideMark />
            </Line>
            <Line label="Energy target">
              <StatusValue value={state.energyTarget} hideMark />
            </Line>
          </div>
        </div>
      )}
    </Panel>
  );
}
