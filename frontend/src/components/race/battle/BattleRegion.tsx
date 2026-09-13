import React from 'react';
import { Battle, Participant, RaceFrame } from '@/lib/race/types';
import { Eyebrow, Panel } from '../primitives';
import { BattleContext } from './BattleContext';
import { BattleActions } from './BattleActions';
import { BattleSolutions } from './BattleSolutions';
import { BattleReplay } from './BattleReplay';
import { BattleSensitivity } from './BattleSensitivity';

interface BattleRegionProps {
  battles: Battle[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  frame: RaceFrame;
  participants: Participant[];
}

/**
 * Opens around one declared decision window rather than the whole race at once.
 */
export function BattleRegion({ battles, selectedId, onSelect, frame, participants }: BattleRegionProps) {
  const lookup = React.useMemo(() => new Map(participants.map((p) => [p.id, p])), [participants]);
  const battle = battles.find((b) => b.id === selectedId) ?? battles[0];

  if (!battle) return null;

  return (
    <Panel className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] px-6 py-4">
        <Eyebrow>Selected battle / decision</Eyebrow>
        <div className="flex flex-wrap gap-2">
          {battles.map((b) => (
            <button
              key={b.id}
              onClick={() => onSelect(b.id)}
              className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                b.id === battle.id
                  ? 'border-white/25 bg-white/[0.1] text-white'
                  : 'border-white/[0.08] bg-white/[0.03] text-white/45 hover:text-white'
              }`}
            >
              L{b.lap} {b.attackerId} v {b.defenderId}
            </button>
          ))}
        </div>
      </div>

      <BattleContext battle={battle} participants={lookup} />
      <BattleActions battle={battle} participants={lookup} />
      <BattleSolutions battle={battle} participants={lookup} />
      <BattleReplay battle={battle} frame={frame} participants={lookup} />
      <BattleSensitivity battle={battle} />
    </Panel>
  );
}
