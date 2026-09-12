'use client';

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { FixtureRaceSource } from '@/lib/race/fixtures/source';
import { useRaceSession } from '@/lib/race/useRaceSession';
import { RaceEvent, SupportState } from '@/lib/race/types';
import { AssumptionsPanel } from '@/components/race/AssumptionsPanel';
import { DeltaColumn } from '@/components/race/DeltaColumn';
import { DriverComparison } from '@/components/race/DriverComparison';
import { OutcomeRow } from '@/components/race/OutcomeRow';
import { PlaybackBar } from '@/components/race/PlaybackBar';
import { RaceTimeline } from '@/components/race/RaceTimeline';
import { RaceWorldPanel } from '@/components/race/RaceWorldPanel';
import { RobustnessPanel } from '@/components/race/RobustnessPanel';
import { BattleRegion } from '@/components/race/battle/BattleRegion';
import { StateBanner } from '@/components/race/StateBanner';
import { TopContextBand } from '@/components/race/TopContextBand';
import { Eyebrow, Panel } from '@/components/race/primitives';

const REQUEST = {
  season: 2026,
  event: 'Fixture Grand Prix',
  scenarioId: 'alt-one-stop',
};

/** States that replace the race regions rather than sitting above them. */
const BLOCKING: SupportState[] = ['unsupported', 'abstained', 'failed'];

const INJECTABLE: { label: string; state: SupportState | 'disconnected' | 'ready'; reason?: string }[] = [
  { label: 'Ready', state: 'ready' },
  { label: 'Partial', state: 'partial', reason: 'The alternative world is missing energy for four entries beyond lap 20.' },
  { label: 'Disconnected', state: 'disconnected' },
  { label: 'Unsupported', state: 'unsupported', reason: 'No validated tyre model exists for this compound at this circuit, so the stint cannot be extended.' },
  { label: 'Abstained', state: 'abstained', reason: 'The requested branch lies beyond the forecast horizon the backend can defend.' },
  { label: 'Failed', state: 'failed', reason: 'The alternative world failed to solve; baseline and scenario inputs are preserved.' },
];

function Preparing() {
  return (
    <Panel className="p-10 text-center">
      <div className="mx-auto mb-5 h-10 w-10 animate-spin rounded-full border-b-2 border-t-2 border-sky-400" />
      <h2 className="text-sm font-bold uppercase tracking-widest text-white">Preparing comparison</h2>
      <p className="mt-2 text-xs text-white/40">
        {REQUEST.season} {REQUEST.event} — baseline against scenario {REQUEST.scenarioId}
      </p>
    </Panel>
  );
}

export function FullRaceView() {
  const source = useMemo(() => new FixtureRaceSource(), []);
  const { state, controls } = useRaceSession(source, REQUEST);
  const { session, frame, comparison } = state;
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedBattleId, setSelectedBattleId] = useState<string | null>(null);

  const selected = useMemo(
    () => session?.participants.find((p) => p.id === state.selectedParticipantId) ?? null,
    [session, state.selectedParticipantId],
  );

  if (!session) return <Preparing />;

  const blocked = BLOCKING.includes(state.supportState);

  // Selecting an event moves to that event in its own world; the other world is shown
  // at the same elapsed race time, with no matching event invented for it.
  const onSelectEvent = (event: RaceEvent) => {
    setSelectedEventId(event.id);
    controls.seek(event.raceTimeS);
    // A competition event on the timeline opens its battle.
    const battle = state.battles.find((b) => `battle-event-${b.id}` === event.id);
    if (battle) setSelectedBattleId(battle.id);
  };

  const onSelectBattle = (id: string) => {
    setSelectedBattleId(id);
    const battle = state.battles.find((b) => b.id === id);
    if (battle) controls.seek(battle.windowStartS);
  };

  return (
    <div className="mx-auto flex max-w-[1600px] flex-col gap-5 px-4 py-8 sm:px-6 lg:px-10">
      <div className="flex items-center justify-between">
        <Link
          href="/setup"
          className="flex items-center gap-2 rounded-[14px] border border-white/[0.05] bg-white/[0.03] px-4 py-2 text-sm font-medium text-white/50 transition-colors hover:bg-white/[0.08] hover:text-white"
        >
          <ArrowLeft size={15} /> Setup
        </Link>
        <div className="flex items-center gap-4">
          <p className="text-[10px] uppercase tracking-widest text-white/25">Fixture source — no backend attached</p>
          <Link
            href="/report"
            className="flex items-center gap-2 rounded-[14px] border border-white/[0.05] bg-white/[0.03] px-4 py-2 text-sm font-medium text-white/50 transition-colors hover:bg-white/[0.08] hover:text-white"
          >
            Report <ArrowRight size={15} />
          </Link>
        </div>
      </div>

      <TopContextBand session={session} stale={state.stale} />

      <StateBanner
        session={session}
        support={state.supportState}
        playback={state.playback}
        reason={state.supportReason}
        error={state.error}
      />

      {!blocked && comparison && <OutcomeRow comparison={comparison} />}

      {!blocked && frame && (
        <>
          {/* Narrow layout: baseline, then alternative, then the deltas. */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_340px_1fr]">
            <div className="order-1 lg:order-1">
              <RaceWorldPanel
                world={frame.baseline}
                track={session.track}
                participants={session.participants}
                selectedId={state.selectedParticipantId}
                onSelect={controls.select}
                title="Baseline race world"
                accent="text-sky-400"
              />
            </div>
            <div className="order-3 lg:order-2">
              <DeltaColumn frame={frame} session={session} selected={selected} />
            </div>
            <div className="order-2 lg:order-3">
              <RaceWorldPanel
                world={frame.alternative}
                track={session.track}
                participants={session.participants}
                selectedId={state.selectedParticipantId}
                onSelect={controls.select}
                title="Alternative race world"
                accent="text-emerald-400"
              />
            </div>
          </div>

          <RaceTimeline
            session={session}
            events={state.events}
            currentTimeS={frame.raceTimeS}
            selectedEventId={selectedEventId}
            onSeek={controls.seek}
            onSelectEvent={onSelectEvent}
          />

          <DriverComparison frame={frame} participant={selected} />

          {state.battles.length > 0 && (
            <BattleRegion
              battles={state.battles}
              selectedId={selectedBattleId}
              onSelect={onSelectBattle}
              frame={frame}
              participants={session.participants}
            />
          )}

          {comparison?.stability && <RobustnessPanel stability={comparison.stability} />}
        </>
      )}

      <AssumptionsPanel session={session} frame={frame} />

      {!blocked && (
        <PlaybackBar
          session={session}
          frame={frame}
          events={state.events}
          status={state.playback}
          rate={state.rate}
          onPause={controls.pause}
          onResume={controls.resume}
          onSeek={controls.seek}
          onRate={controls.setRate}
        />
      )}

      {/* Fixture-only: makes every layout state reachable without a misbehaving backend. */}
      <Panel className="flex flex-wrap items-center gap-3 p-4 px-6">
        <Eyebrow>Layout states (fixture)</Eyebrow>
        {INJECTABLE.map((s) => (
          <button
            key={s.label}
            onClick={() =>
              s.state === 'disconnected'
                ? controls.injectDisconnect()
                : controls.injectSupport(s.state as SupportState, s.reason)
            }
            className="rounded-full border border-white/[0.08] bg-white/[0.04] px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-white/50 transition-colors hover:bg-white/[0.1] hover:text-white"
          >
            {s.label}
          </button>
        ))}
      </Panel>
    </div>
  );
}
