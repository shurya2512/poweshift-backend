import React from 'react';
import { Participant, PlannedStint, SessionInfo, StrategyBrief, SupportState } from '@/lib/race/types';
import { Eyebrow, Panel } from '../primitives';
import { StatusValue } from '../StatusValue';
import { TyreMarker } from '../TyreMarker';

const SUPPORT_STYLE: Record<SupportState, string> = {
  ready: 'text-emerald-300 border-emerald-400/30 bg-emerald-400/10',
  partial: 'text-amber-300 border-amber-400/30 bg-amber-400/10',
  stale: 'text-amber-300 border-amber-400/30 bg-amber-400/10',
  unsupported: 'text-white/50 border-white/15 bg-white/5',
  abstained: 'text-violet-300 border-violet-400/30 bg-violet-400/10',
  failed: 'text-red-300 border-red-400/30 bg-red-400/10',
};

/**
 * The stint plan as the tyres themselves, one per stint, in the order they go on.
 *
 * Only the tyres are drawn. The compound name, the laps it covers and the stop that
 * ends it ride on each tyre's title, so the strip reads as a plan at a glance and
 * still answers the detail on hover.
 */
export function StintPlan({ stints, pitLaps }: { stints: PlannedStint[]; pitLaps: number[] }) {
  if (stints.length === 0) {
    return <p className="text-[11px] italic text-white/25">No stint plan was supplied.</p>;
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      {stints.map((stint, i) => (
        <TyreMarker
          key={`${stint.compound}-${stint.fromLap}`}
          compound={stint.compound}
          size="xl"
          title={
            `${stint.compound} · laps ${stint.fromLap}–${stint.toLap}` +
            (pitLaps[i] !== undefined ? ` · pit on lap ${pitLaps[i]}` : '')
          }
        />
      ))}
    </div>
  );
}

function Brief({ brief, driver }: { brief: StrategyBrief; driver: Participant | null }) {
  // The bracket beside a 36px figure is unreadable, so the expectation's range is
  // spelled out under it instead of being dropped.
  const expected = brief.expectedFinishPosition;
  const range =
    (expected.status === 'predicted' || expected.status === 'inferred') && expected.interval
      ? expected.interval
      : null;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto]">
      <div>
        <Eyebrow>Replicating</Eyebrow>
        <div className="mt-2 flex items-center gap-3">
          <span
            className="h-9 w-1 shrink-0 rounded-full"
            style={{ background: driver?.teamColor ?? 'rgba(255,255,255,0.2)' }}
          />
          <div>
            <p className="text-base font-bold leading-tight text-white">
              {brief.car} · {driver ? `#${driver.raceNumber}` : 'car unavailable'}
            </p>
            <p className="mt-0.5 text-[12px] text-white/45">
              {driver ? `${driver.name} · ${driver.team}` : 'No entry selected'}
            </p>
          </div>
        </div>
      </div>

      <div className="lg:border-l lg:border-white/[0.06] lg:pl-6">
        <Eyebrow>Pit-stop strategy · {brief.author}</Eyebrow>
        <div className="mt-3">
          <StintPlan stints={brief.stints} pitLaps={brief.pitLaps} />
        </div>
      </div>

      <div className="lg:border-l lg:border-white/[0.06] lg:pl-6">
        <Eyebrow>Expected finish</Eyebrow>
        {/* The position alone. The range and who called it are on the title. */}
        <p
          className="mt-2 text-4xl font-black tracking-tighter text-white"
          title={`${brief.author}'s call, before the start${range ? ` · P${range[0]}–P${range[1]}` : ''}`}
        >
          <StatusValue value={brief.expectedFinishPosition} format={(v) => `P${v}`} hideMark hideInterval />
        </p>
      </div>
    </div>
  );
}

/**
 * What this page is, before any of it moves: the race being replicated, the car and
 * team, and the plan we were given to run — including where it is expected to finish.
 * Everything below the header is the race answering it.
 */
export function RaceHeader({
  session,
  driver,
  support,
}: {
  session: SessionInfo;
  driver: Participant | null;
  /** The live support state, not the one the session was opened with. */
  support: SupportState;
}) {
  const { identity, brief } = session;

  return (
    <Panel className="overflow-hidden">
      {/* The race, and nothing else. The support state stays because it is live —
          everything that only described the page has gone. */}
      <div className="flex flex-wrap items-center justify-between gap-6 p-7 pb-6 sm:px-9">
        <h1 className="min-w-0 text-[34px] font-black uppercase leading-[0.92] tracking-tighter text-white md:text-[46px]">
          {identity.event}
        </h1>
        <span
          className={`shrink-0 rounded-full border px-3 py-0.5 text-[10px] font-semibold uppercase tracking-widest ${SUPPORT_STYLE[support]}`}
        >
          {support}
        </span>
      </div>

      <div className="border-t border-white/[0.06] bg-black/25 p-7 sm:px-9">
        {brief ? (
          <Brief brief={brief} driver={driver} />
        ) : (
          <p className="text-[12px] italic text-white/30">
            No strategy brief was supplied for this session, so no plan or expected finish is shown.
          </p>
        )}
      </div>

      <div className="border-t border-white/[0.06] px-7 py-3.5 sm:px-9">
        <p className="font-mono text-[10px] uppercase tracking-widest text-white/25">
          Rules {identity.rulesVersion} · branch lap {session.branchPoint.lap} — {session.branchPoint.description}
        </p>
      </div>
    </Panel>
  );
}
