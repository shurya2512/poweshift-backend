import React from 'react';
import { Participant, ParticipantState, RaceWorld, TrackGeometry } from '@/lib/race/types';
import { RaceWorldMap } from './RaceWorldMap';
import { valueOf } from '@/lib/race/valued';
import { Eyebrow, Panel, formatGap } from './primitives';
import { StatusValue } from './StatusValue';

const CLASSIFICATION: Record<ParticipantState['participation'], string | null> = {
  running: null,
  in_pit: 'PIT',
  retired: 'RET',
  finished: 'FIN',
  disqualified: 'DSQ',
};

interface RowProps {
  state: ParticipantState;
  participant: Participant;
  selected: boolean;
  onSelect: (id: string) => void;
}

function Row({ state, participant, selected, onSelect }: RowProps) {
  const badge = CLASSIFICATION[state.participation];
  const isOut = state.participation === 'retired' || state.participation === 'disqualified';

  return (
    <button
      onClick={() => onSelect(state.participantId)}
      className={`flex w-full items-center gap-3 px-4 py-1.5 text-left transition-colors ${
        selected ? 'bg-white/[0.09]' : 'hover:bg-white/[0.04]'
      } ${isOut ? 'opacity-45' : ''}`}
    >
      <span className="w-5 text-right text-xs font-bold tabular-nums text-white/45">
        {isOut ? '–' : state.rank}
      </span>
      <span className="h-4 w-[3px] shrink-0 rounded-full" style={{ backgroundColor: participant.teamColor }} />
      <span className="w-10 text-xs font-bold tracking-wide text-white">{participant.code}</span>

      <span className="flex-1 text-[11px] tabular-nums text-white/60">
        {isOut ? (
          <span className="italic text-white/35">retired, lap {state.lap}</span>
        ) : (
          <StatusValue value={state.gapS} format={formatGap} hideMark />
        )}
      </span>

      <span className="w-16 text-right text-[11px] tabular-nums text-white/45">
        {isOut ? '' : `L${state.lap}`}
        {state.lapsDown > 0 && <span className="ml-1 text-amber-300/70">+{state.lapsDown}L</span>}
      </span>

      <span className="w-9 text-right text-[10px] font-semibold text-white/40">
        {valueOf(state.tyre.compound)?.[0] ?? '·'}
      </span>

      {badge && (
        <span className="w-8 rounded border border-white/15 px-1 text-center text-[9px] font-bold text-white/50">
          {badge}
        </span>
      )}
      {!badge && <span className="w-8" />}
    </button>
  );
}

interface RaceWorldPanelProps {
  world: RaceWorld;
  track: TrackGeometry;
  participants: Participant[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  title: string;
  accent: string;
}

/**
 * One race world: its own track state and its own ordered field. Retired, lapped and
 * finished entries are shown by classification, never by a numeric position that
 * implies they are still racing.
 */
export function RaceWorldPanel({
  world,
  track,
  participants,
  selectedId,
  onSelect,
  title,
  accent,
}: RaceWorldPanelProps) {
  const lookup = new Map(participants.map((p) => [p.id, p]));

  return (
    <Panel className="flex flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
        <div>
          <Eyebrow className={accent}>{title}</Eyebrow>
          <p className="mt-1 text-sm font-semibold text-white">{world.scenario.name}</p>
        </div>
        <div className="text-right">
          <p className="text-xs font-semibold text-white">
            Lap {world.leaderLap}/{world.totalLaps}
          </p>
          <p className="text-[10px] uppercase tracking-widest text-white/35">
            {world.flag.replace(/_/g, ' ')}
          </p>
        </div>
      </div>
      <div className="aspect-[16/10] w-full border-b border-white/[0.06] px-2 pt-2">
        <RaceWorldMap
          track={track}
          world={world}
          participants={participants}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      </div>

      <div className="max-h-[380px] overflow-y-auto py-1">
        {world.field.map((state) => {
          const participant = lookup.get(state.participantId);
          if (!participant) return null;
          return (
            <Row
              key={state.participantId}
              state={state}
              participant={participant}
              selected={state.participantId === selectedId}
              onSelect={onSelect}
            />
          );
        })}
      </div>
    </Panel>
  );
}
