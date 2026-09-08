import React from 'react';
import { SessionInfo, SupportState } from '@/lib/race/types';
import { Eyebrow, Panel } from './primitives';
import { StatusLegend } from './StatusValue';

const MODE_LABEL: Record<SessionInfo['mode'], string> = {
  recorded_replay: 'Recorded replay',
  conditional_replay: 'Conditional replay',
  forward_forecast: 'Forward forecast',
  counterfactual: 'Counterfactual',
};

const SUPPORT_STYLE: Record<SupportState, string> = {
  ready: 'text-emerald-300 border-emerald-400/30 bg-emerald-400/10',
  partial: 'text-amber-300 border-amber-400/30 bg-amber-400/10',
  stale: 'text-amber-300 border-amber-400/30 bg-amber-400/10',
  unsupported: 'text-white/50 border-white/15 bg-white/5',
  abstained: 'text-violet-300 border-violet-400/30 bg-violet-400/10',
  failed: 'text-red-300 border-red-400/30 bg-red-400/10',
};

const Cell = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex flex-col gap-1">
    <Eyebrow>{label}</Eyebrow>
    <span className="text-sm font-semibold text-white">{children}</span>
  </div>
);

/** Event · mode · observation cutoff · freshness · support state. Always visible. */
export function TopContextBand({ session, stale }: { session: SessionInfo; stale: boolean }) {
  const { identity, timeBoundary } = session;
  const support: SupportState = stale ? 'stale' : session.supportState;

  return (
    <Panel className="p-6 px-8">
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <Cell label="Event">
            {identity.season} {identity.event} · {identity.circuit} · {identity.session}
          </Cell>
          <Cell label="Mode">{MODE_LABEL[session.mode]}</Cell>
          <Cell label="Observation cutoff">{timeBoundary.observationCutoffS.toFixed(0)} s race time</Cell>
          <Cell label="Freshness">
            {stale ? 'Last confirmed frame' : 'Current'}
          </Cell>
          <div className="flex flex-col gap-1">
            <Eyebrow>Support state</Eyebrow>
            <span
              className={`w-fit rounded-full border px-3 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${SUPPORT_STYLE[support]}`}
            >
              {support}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-white/[0.06] pt-4">
          <StatusLegend />
          <p className="text-[10px] uppercase tracking-widest text-white/30">
            Rules {identity.rulesVersion} · branch lap {session.branchPoint.lap} · {session.branchPoint.description}
          </p>
        </div>
      </div>
    </Panel>
  );
}
