'use client';

import React, { useEffect, useMemo, useRef } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { FixtureRaceSource } from '@/lib/race/fixtures/source';
import { useRaceSession } from '@/lib/race/useRaceSession';
import { buildReport } from '@/lib/race/report';
import { SupportState } from '@/lib/race/types';
import { Column, P } from '@/components/race/report/article';
import { ReportArticle } from '@/components/race/report/ReportArticle';

const REQUEST = {
  season: 2026,
  event: 'Fixture Grand Prix',
  scenarioId: 'alt-one-stop',
};

/** States that replace the report rather than qualifying it. */
const BLOCKING: SupportState[] = ['unsupported', 'abstained', 'failed'];

const BLOCKING_TITLE: Record<string, string> = {
  unsupported: 'Not supported by the available evidence',
  abstained: 'Abstained',
  failed: 'The comparison failed',
};

/** The requested question stays on the page even when there is no answer to print. */
function NoReport({ title, body }: { title: string; body: string }) {
  return (
    <Column className="py-24">
      <p className="font-mono text-[11px] uppercase tracking-[0.4em] text-white/30">Race report</p>
      <h1 className="mt-5 text-4xl font-black uppercase leading-[0.95] tracking-tighter text-white md:text-6xl">
        {title}
      </h1>
      <p className="mt-6 border-t border-white/10 pt-5 text-[11px] uppercase tracking-[0.15em] text-white/30">
        Requested — {REQUEST.season} {REQUEST.event}, baseline against {REQUEST.scenarioId}
      </p>
      <P className="mt-6">{body}</P>
    </Column>
  );
}

export function ReportView() {
  const source = useMemo(() => new FixtureRaceSource(), []);
  const { state, controls } = useRaceSession(source, REQUEST);
  const { session, frame, comparison } = state;

  // A report is the finished race, so it is read at the flag rather than replayed to it.
  const sought = useRef(false);
  useEffect(() => {
    if (!session || sought.current) return;
    sought.current = true;
    controls.pause();
    controls.seek(session.durationS);
  }, [session, controls]);

  // The delivered report wins; otherwise it is assembled from the finished session.
  const assembled = useMemo(
    () =>
      buildReport({
        session,
        frame,
        comparison,
        events: state.events,
        battles: state.battles,
        selectedParticipantId: state.selectedParticipantId,
      }),
    [session, frame, comparison, state.events, state.battles, state.selectedParticipantId],
  );
  const report = state.report ?? assembled;

  const participants = useMemo(
    () => new Map((session?.participants ?? []).map((p) => [p.id, p])),
    [session],
  );

  const blocked = BLOCKING.includes(state.supportState);

  return (
    <div className="px-6 py-10 sm:px-10">
      <Column className="mb-16 flex items-center justify-between border-b border-white/[0.07] pb-5">
        <Link
          href="/full-race"
          className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-white/40 transition-colors hover:text-white"
        >
          <ArrowLeft size={14} /> Race
        </Link>
        <span className="hidden font-mono text-[10px] uppercase tracking-[0.2em] text-white/20 sm:inline">
          Fixture source — no backend attached
        </span>
      </Column>

      {blocked ? (
        <NoReport
          title={BLOCKING_TITLE[state.supportState] ?? 'No report'}
          body={
            state.error ??
            state.supportReason ??
            'The backend could not answer this comparison with the inputs it has. The scenario and its inputs are preserved; nothing has been substituted for the missing result.'
          }
        />
      ) : !report ? (
        <NoReport
          title={session ? 'The race is not finished' : 'Assembling the report'}
          body={
            session
              ? 'A report is cut once both races have taken the flag. Until then there is no classification to print, and a partial one would not be a smaller report — it would be a different claim.'
              : 'Waiting for the session to arrive.'
          }
        />
      ) : (
        <>
          {(state.supportState !== 'ready' || state.stale) && (
            <Column className="mb-12 border-l-2 border-amber-400/40 pl-5">
              <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-amber-300/80">
                {state.stale ? 'Stale' : state.supportState}
              </p>
              <P className="mt-2">
                {state.supportReason ??
                  'Some values or one of the two races are incomplete. Everything the source did supply is printed below, and everything it did not reads as unavailable.'}
              </P>
            </Column>
          )}

          <ReportArticle report={report} participants={participants} />
        </>
      )}
    </div>
  );
}
