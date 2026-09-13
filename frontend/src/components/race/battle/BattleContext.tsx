import React from 'react';
import { Battle, MoveStructure, Participant } from '@/lib/race/types';
import { Eyebrow, formatClock } from '../primitives';
import { StatusValue } from '../StatusValue';

const STRUCTURE_NOTE: Record<MoveStructure, string> = {
  sequential: 'Sequential — the first move is committed before the response.',
  simultaneous: 'Simultaneous — both action sets are chosen without seeing the other.',
  stochastic: 'Stochastic — the opponent responds from a fitted distribution.',
  learned: 'Learned — the response distribution is estimated from comparable battles.',
};

export function BattleContext({
  battle,
  participants,
}: {
  battle: Battle;
  participants: Map<string, Participant>;
}) {
  const attacker = participants.get(battle.attackerId);
  const defender = participants.get(battle.defenderId);

  return (
    <div className="flex flex-wrap items-start justify-between gap-6 border-b border-white/[0.07] px-6 py-5">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="h-6 w-1 rounded-full" style={{ backgroundColor: attacker?.teamColor }} />
          <div>
            <p className="text-sm font-bold text-white">{attacker?.code}</p>
            <p className="text-[9px] uppercase tracking-widest text-white/35">attacking</p>
          </div>
        </div>
        <span className="text-white/20">vs</span>
        <div className="flex items-center gap-2">
          <span className="h-6 w-1 rounded-full" style={{ backgroundColor: defender?.teamColor }} />
          <div>
            <p className="text-sm font-bold text-white">{defender?.code}</p>
            <p className="text-[9px] uppercase tracking-widest text-white/35">defending</p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-8">
        <div>
          <Eyebrow>Lap · window</Eyebrow>
          <p className="mt-1 text-[11px] font-semibold text-white/75">
            L{battle.lap} · {formatClock(battle.windowStartS)}–{formatClock(battle.windowEndS)}
          </p>
        </div>
        <div>
          <Eyebrow>Starting gap</Eyebrow>
          <p className="mt-1 text-[11px] font-semibold text-white/75">
            <StatusValue value={battle.startingGapS} format={(v) => `${v.toFixed(2)}s`} />
          </p>
        </div>
        <div className="max-w-[240px]">
          <Eyebrow>Location</Eyebrow>
          <p className="mt-1 text-[11px] font-semibold text-white/75">{battle.location}</p>
        </div>
      </div>

      <div className="max-w-[280px]">
        <Eyebrow>Move structure</Eyebrow>
        <p className="mt-1 text-[11px] leading-relaxed text-white/60">{STRUCTURE_NOTE[battle.moveStructure]}</p>
      </div>
    </div>
  );
}
