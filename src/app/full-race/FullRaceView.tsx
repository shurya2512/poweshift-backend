'use client';

import React, { useMemo, useState } from 'react';
import { SpinningBorderButton } from '@/components/ui/spinning-border-button';
import { FixtureRaceSource } from '@/lib/race/fixtures/source';
import { useRaceSession } from '@/lib/race/useRaceSession';
import { findOvertakeMoves } from '@/lib/race/report';
import { RaceEvent, SupportState, WorldSide } from '@/lib/race/types';
import { AssumptionsPanel } from '@/components/race/AssumptionsPanel';
import { RaceTimeline } from '@/components/race/RaceTimeline';
import { StateBanner } from '@/components/race/StateBanner';
import { LiveFeed } from '@/components/race/full/LiveFeed';
import { OurCarPanel } from '@/components/race/full/OurCarPanel';
import { RaceHeader } from '@/components/race/full/RaceHeader';
import { StandingsPanel } from '@/components/race/full/StandingsPanel';
import { OvertakeFlashCards } from '@/components/race/overtake/OvertakeFlashCards';
import { Panel } from '@/components/race/primitives';

const REQUEST = {
  season: 2026,
  event: 'Fixture Grand Prix',
  scenarioId: 'alt-one-stop',
};

/** States that replace the race regions rather than sitting above them. */
const BLOCKING: SupportState[] = ['unsupported', 'abstained', 'failed'];

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
  const { session, frame } = state;
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  // The live regions read one race at a time, and say which. Our plan leads, because
  // it is the one the page is asking about; the recorded race is a switch away.
  const [side, setSide] = useState<WorldSide>('alternative');

  const selected = useMemo(
    () => session?.participants.find((p) => p.id === state.selectedParticipantId) ?? null,
    [session, state.selectedParticipantId],
  );

  const participants = useMemo(
    () => new Map((session?.participants ?? []).map((p) => [p.id, p])),
    [session],
  );

  const moves = useMemo(
    () => (state.selectedParticipantId ? findOvertakeMoves(state.battles, state.selectedParticipantId) : []),
    [state.battles, state.selectedParticipantId],
  );

  if (!session) return <Preparing />;

  const blocked = BLOCKING.includes(state.supportState);
  const other: WorldSide = side === 'baseline' ? 'alternative' : 'baseline';
  const stateOf = (world: WorldSide) =>
    frame?.[world].field.find((p) => p.participantId === state.selectedParticipantId);

  // Selecting an event moves to that event in its own race; the other race is shown at
  // the same elapsed race time, with no matching event invented for it.
  const onSelectEvent = (event: RaceEvent) => {
    setSelectedEventId(event.id);
    controls.seek(event.raceTimeS);
    if (event.world !== 'shared') setSide(event.world);
  };

  return (
    <div className="mx-auto flex max-w-[1600px] flex-col gap-5 px-4 py-8 sm:px-6 lg:px-10">
      {/* Same pill as the setup page's Return to Home: back flips its arrow, forward slides. */}
      <div className="flex items-center justify-between gap-4">
        <SpinningBorderButton href="/setup-full-race" text="Setup" size="sm" arrowMode="flip" fill="hollow" beam="once" />
        <SpinningBorderButton href="/report" text="Report" size="sm" fill="hollow" beam="once" />
      </div>

      <RaceHeader
        session={session}
        driver={selected}
        support={state.stale ? 'stale' : state.supportState}
      />

      <StateBanner
        session={session}
        support={state.supportState}
        playback={state.playback}
        reason={state.supportReason}
        error={state.error}
      />

      {!blocked && frame && (
        <>
          {/* Standings, then our car, then the feed — the order the pit wall reads them. */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-[minmax(0,320px)_minmax(0,340px)_minmax(0,1fr)]">
            <StandingsPanel
              world={frame[side]}
              participants={session.participants}
              selectedId={state.selectedParticipantId}
              onSelect={controls.select}
            />
            <OurCarPanel
              driver={selected}
              car={session.brief?.car}
              side={side}
              state={stateOf(side)}
              other={stateOf(other)}
            />
            <div className="lg:col-span-2 xl:col-span-1">
              <LiveFeed
                world={frame[side]}
                track={session.track}
                participants={session.participants}
                selectedId={state.selectedParticipantId}
                raceTimeS={frame.raceTimeS}
                onSelect={controls.select}
                onWorld={setSide}
              />
            </div>
          </div>

          <RaceTimeline
            session={session}
            events={state.events}
            currentTimeS={frame.raceTimeS}
            selectedEventId={selectedEventId}
            status={state.playback}
            onSeek={controls.seek}
            onSelectEvent={onSelectEvent}
            onPause={controls.pause}
            onResume={controls.resume}
          />

          <OvertakeFlashCards
            moves={moves}
            participants={participants}
            branchLap={session.branchPoint.lap}
          />
        </>
      )}

      <AssumptionsPanel session={session} frame={frame} />
    </div>
  );
}
