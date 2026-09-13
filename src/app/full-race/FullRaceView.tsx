'use client';

import React, { useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { SpinningBorderButton } from '@/components/ui/spinning-border-button';
import { FixtureRaceSource } from '@/lib/race/fixtures/source';
import { useRaceSession } from '@/lib/race/useRaceSession';
import { findOvertakeMoves } from '@/lib/race/report';
import { RaceEvent, SupportState, WorldSide } from '@/lib/race/types';
import { RaceTimeline } from '@/components/race/RaceTimeline';
import { StateBanner } from '@/components/race/StateBanner';
import { LiveFeed } from '@/components/race/full/LiveFeed';
import { OurCarPanel } from '@/components/race/full/OurCarPanel';
import { RaceHeader } from '@/components/race/full/RaceHeader';
import { StandingsPanel } from '@/components/race/full/StandingsPanel';
import { OvertakeCarousel } from '@/components/race/overtake/OvertakeCarousel';
import { Panel } from '@/components/race/primitives';
import { BackendRuntimePanel } from '@/components/race/BackendRuntimePanel';

const REQUEST = {
  season: 2026,
  event: 'Fixture Grand Prix',
  scenarioId: 'alt-one-stop',
};

/** The one race this page shows. */
const SIDE: WorldSide = 'alternative';

/** States that replace the race regions rather than sitting above them. */
const BLOCKING: SupportState[] = ['unsupported', 'abstained', 'failed'];

function Preparing() {
  return (
    <Panel className="p-10 text-center">
      <div className="mx-auto mb-5 h-10 w-10 animate-spin rounded-full border-b-2 border-t-2 border-sky-400" />
      <h2 className="text-sm font-bold uppercase tracking-widest text-white">Preparing race</h2>
      <p className="mt-2 text-xs text-white/40">
        {REQUEST.season} {REQUEST.event}
      </p>
    </Panel>
  );
}

export function FullRaceView() {
  const search = useSearchParams();
  const diagnosticTrack = search.get('track') ?? 'Miami Grand Prix';
  const profileEntry = search.get('profile') ?? '1';
  const reportParams = new URLSearchParams({ mode: 'race', track: diagnosticTrack, profile: profileEntry });
  const source = useMemo(() => new FixtureRaceSource(), []);
  const { state, controls } = useRaceSession(source, REQUEST);
  const { session, frame } = state;
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

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
  const ours = frame?.[SIDE].field.find((p) => p.participantId === state.selectedParticipantId);

  const onSelectEvent = (event: RaceEvent) => {
    setSelectedEventId(event.id);
    controls.seek(event.raceTimeS);
  };

  return (
    <div className="mx-auto flex max-w-[1600px] flex-col gap-5 px-4 py-8 sm:px-6 lg:px-10">
      {/* Same pill as the setup page's Return to Home: back flips its arrow, forward slides. */}
      <div className="flex items-center justify-between gap-4">
        <SpinningBorderButton href="/setup-full-race" text="Setup" size="sm" arrowMode="flip" fill="hollow" beam="once" />
        <SpinningBorderButton href={`/report?${reportParams.toString()}`} text="Report" size="sm" fill="hollow" beam="once" />
      </div>

      <BackendRuntimePanel track={diagnosticTrack} profileEntry={profileEntry} />

      <Panel className="border-sky-400/20 px-5 py-4 text-xs leading-relaxed text-white/55">
        The animated race below is the labelled 23-car fixture stream. The selected {diagnosticTrack} profile is shown
        in the backend report, where its P23 start, decisions, energy and final proxy position remain source-bound.
      </Panel>

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
          {/* The track leads, with the timeline that scrubs it directly beneath. At full
              width the map would grow to its own aspect ratio, so its height is held. */}
          <div className="lg:h-[600px]">
            <LiveFeed
              world={frame[SIDE]}
              track={session.track}
              participants={session.participants}
              selectedId={state.selectedParticipantId}
              raceTimeS={frame.raceTimeS}
              onSelect={controls.select}
            />
          </div>

          <RaceTimeline
            session={session}
            events={state.events}
            side={SIDE}
            currentTimeS={frame.raceTimeS}
            selectedEventId={selectedEventId}
            status={state.playback}
            onSeek={controls.seek}
            onSelectEvent={onSelectEvent}
            onPause={controls.pause}
            onResume={controls.resume}
          />

          {/* Then the order, and our car in it. */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <StandingsPanel
              world={frame[SIDE]}
              participants={session.participants}
              selectedId={state.selectedParticipantId}
              onSelect={controls.select}
            />
            <OurCarPanel driver={selected} car={session.brief?.car} state={ours} />
          </div>

          <OvertakeCarousel moves={moves} participants={participants} />
        </>
      )}
    </div>
  );
}
