import React from 'react';
import { motion } from 'framer-motion';
import { Participant, ParticipantState, RaceWorld } from '@/lib/race/types';
import { valueOf } from '@/lib/race/valued';
import { Eyebrow, Panel, formatGap } from '../primitives';
import { StatusValue } from '../StatusValue';
import { TyreValue } from '../TyreMarker';

const BADGE: Record<ParticipantState['participation'], string | null> = {
  running: null,
  in_pit: 'PIT',
  retired: 'RET',
  finished: 'FIN',
  disqualified: 'DSQ',
};

function Row({
  state,
  participant,
  selected,
  onSelect,
}: {
  state: ParticipantState;
  participant: Participant;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const badge = BADGE[state.participation];
  const out = state.participation === 'retired' || state.participation === 'disqualified';
  const age = valueOf(state.tyre.ageLaps);

  return (
    <motion.button
      // Keyed by entry rather than by position, so a car that changes place slides to
      // its new row instead of the whole order snapping to a different arrangement.
      layout="position"
      transition={{ type: 'spring', stiffness: 520, damping: 42 }}
      onClick={() => onSelect(state.participantId)}
      className={`grid w-full grid-cols-[18px_3px_34px_minmax(0,1fr)_minmax(0,1fr)_44px] items-center gap-x-2 px-3 py-[5px] text-left transition-colors ${
        selected ? 'bg-white/[0.1]' : 'hover:bg-white/[0.04]'
      } ${out ? 'opacity-45' : ''}`}
    >
      <span className="text-right text-[11px] font-bold tabular-nums text-white/45">
        {out ? '–' : state.rank}
      </span>
      <span className="h-4 rounded-full" style={{ background: participant.teamColor }} />
      <span className="text-[11px] font-bold tracking-wide text-white">{participant.code}</span>

      <span className="truncate text-[10px] tabular-nums text-white/60">
        {out ? (
          <span className="italic text-white/35">lap {state.lap}</span>
        ) : (
          <StatusValue value={state.gapS} format={formatGap} hideMark />
        )}
      </span>

      <span className="truncate text-right text-[10px] tabular-nums text-white/35">
        {out ? '' : <StatusValue value={state.intervalS} format={(v) => `+${v.toFixed(2)}`} hideMark />}
      </span>

      <span className="flex items-center justify-end gap-1">
        {badge ? (
          <span className="rounded border border-white/15 px-1 text-[8px] font-bold text-white/50">{badge}</span>
        ) : null}
        <TyreValue value={state.tyre.compound} size="sm" />
        <span className="w-[14px] text-right text-[9px] tabular-nums text-white/35">{age ?? '–'}</span>
      </span>
    </motion.button>
  );
}

/**
 * The order: position, both gaps, and the tyre each car is on.
 *
 * Retired and lapped entries keep their classification rather than a running position.
 */
export function StandingsPanel({
  world,
  participants,
  selectedId,
  onSelect,
}: {
  world: RaceWorld;
  participants: Participant[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const lookup = new Map(participants.map((p) => [p.id, p]));

  return (
    <Panel className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-white/[0.07] px-4 py-3.5">
        <Eyebrow>Standings</Eyebrow>
        <p className="mt-1 text-[11px] text-white/45">
          Lap {world.leaderLap}/{world.totalLaps} · {world.field.filter((p) => p.participation === 'running').length}{' '}
          running
        </p>
        <p className="mt-1 text-[10px] leading-snug text-amber-300/60">
          Our car&apos;s position and energy are measured from its report; the rest of the order is illustrative.
        </p>
      </div>

      <div className="grid grid-cols-[18px_3px_34px_minmax(0,1fr)_minmax(0,1fr)_44px] gap-x-2 border-b border-white/[0.06] px-3 py-1.5 text-[9px] uppercase tracking-widest text-white/25">
        <span className="text-right">P</span>
        <span />
        <span>Car</span>
        <span>Leader</span>
        <span className="text-right">Int</span>
        <span className="text-right">Tyre</span>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
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
