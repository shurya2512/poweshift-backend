import React from 'react';
import { Participant, ParticipantState, RaceFrame } from '@/lib/race/types';
import { Eyebrow, Panel, formatGap } from './primitives';
import { StatusValue } from './StatusValue';
import { EnergyPanel } from './EnergyPanel';

const PARTICIPATION_LABEL: Record<ParticipantState['participation'], string> = {
  running: 'On track',
  in_pit: 'In pit lane',
  retired: 'Retired',
  finished: 'Finished',
  disqualified: 'Disqualified',
};

const Line = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex items-baseline justify-between gap-3 py-1">
    <span className="text-[10px] uppercase tracking-wider text-white/35">{label}</span>
    <span className="text-right text-[11px] font-semibold text-white/80">{children}</span>
  </div>
);

/** One world's column. Both columns carry the same categories in the same order. */
function Column({ state, title, accent }: { state: ParticipantState | undefined; title: string; accent: string }) {
  if (!state) {
    return (
      <div className="flex-1 p-5">
        <Eyebrow className={accent}>{title}</Eyebrow>
        <p className="mt-4 text-[11px] italic text-white/25">This entry is not present in this world.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-4 p-5">
      <div>
        <Eyebrow className={accent}>{title}</Eyebrow>
        <p className="mt-1 text-2xl font-black tabular-nums tracking-tighter text-white">
          P{state.rank} <span className="text-sm font-semibold text-white/40">{PARTICIPATION_LABEL[state.participation]}</span>
        </p>
      </div>

      <div className="divide-y divide-white/[0.05] border-y border-white/[0.05]">
        <Line label="Gap to leader">
          <StatusValue value={state.gapS} format={formatGap} />
        </Line>
        <Line label="Interval">
          <StatusValue value={state.intervalS} format={formatGap} />
        </Line>
        <Line label="Lap">
          L{state.lap}
          {state.lapsDown > 0 && <span className="ml-1 text-amber-300/70">+{state.lapsDown}L</span>}
        </Line>
        <Line label="Sector">
          <StatusValue value={state.sector} format={(v) => `S${v}`} />
        </Line>
        <Line label="Speed">
          <StatusValue value={state.speedKmh} format={(v) => `${v} km/h`} />
        </Line>
      </div>

      <div className="divide-y divide-white/[0.05] border-y border-white/[0.05]">
        <Line label="Compound">
          <StatusValue value={state.tyre.compound} />
        </Line>
        <Line label="Stint age">
          <StatusValue value={state.tyre.ageLaps} format={(v) => `${v} laps`} />
        </Line>
        <Line label="Tyre condition">
          <StatusValue value={state.tyre.conditionPct} format={(v) => `${v.toFixed(0)}%`} />
        </Line>
        <Line label="Fuel">
          <StatusValue value={state.fuelKg} format={(v) => `${v} kg`} />
        </Line>
      </div>

      <EnergyPanel energy={state.energy} />

      <div className="divide-y divide-white/[0.05] border-y border-white/[0.05]">
        <Line label="Pace target">
          <StatusValue value={state.paceTarget} />
        </Line>
        <Line label="Energy target">
          <StatusValue value={state.energyTarget} />
        </Line>
        <Line label="Instruction">
          <StatusValue value={state.strategyInstruction} />
        </Line>
      </div>
    </div>
  );
}

interface DriverComparisonProps {
  frame: RaceFrame;
  participant: Participant | null;
}

export function DriverComparison({ frame, participant }: DriverComparisonProps) {
  if (!participant) return null;
  const find = (side: 'baseline' | 'alternative') =>
    frame[side].field.find((p) => p.participantId === participant.id);

  return (
    <Panel className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="h-6 w-1 rounded-full" style={{ backgroundColor: participant.teamColor }} />
          <div>
            <p className="text-sm font-bold text-white">
              {participant.code} · {participant.name}
            </p>
            <p className="text-[10px] uppercase tracking-widest text-white/35">{participant.team}</p>
          </div>
        </div>
        {/* The alignment basis is always named next to the detail. */}
        <p className="text-[10px] uppercase tracking-widest text-white/30">
          Aligned to shared race clock
        </p>
      </div>

      <div className="flex flex-col divide-y divide-white/[0.06] md:flex-row md:divide-x md:divide-y-0">
        <Column state={find('baseline')} title="Baseline" accent="text-sky-400" />
        <Column state={find('alternative')} title="Alternative" accent="text-emerald-400" />
      </div>
    </Panel>
  );
}
