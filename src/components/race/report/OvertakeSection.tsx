'use client';

import React, { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { OvertakeMove } from '@/lib/race/report';
import { Participant } from '@/lib/race/types';
import { formatClock } from '../primitives';
import { StatusValue } from '../StatusValue';
import { OvertakeModal } from '../overtake/OvertakeModal';
import { P, Section } from './article';

export function OvertakeSection({
  moves,
  participants,
}: {
  moves: OvertakeMove[];
  participants: Map<string, Participant>;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const open = moves.find((m) => `${m.battle.id}:${m.chosen.id}` === openId) ?? null;

  if (moves.length === 0) return null;

  return (
    <Section
      title={moves.length === 1 ? 'The move' : 'The moves'}
      standfirst="Where our car came out of a fight ahead of the one it was behind — and the lines it turned down to do it."
    >
      {moves.map((move) => {
        const { battle, chosen, chosenAction } = move;
        const defender = participants.get(battle.defenderId);
        const attacker = participants.get(battle.attackerId);
        const ourLines = battle.actions.filter((a) => a.participantId === battle.attackerId).length;
        const id = `${battle.id}:${chosen.id}`;

        return (
          <div key={id}>
            <P>
              On lap {battle.lap}, {formatClock(battle.windowStartS)} in, {attacker?.name ?? battle.attackerId} arrived{' '}
              <StatusValue value={battle.startingGapS} format={(v) => `${v.toFixed(2)}s`} /> behind{' '}
              {defender?.name ?? battle.defenderId} at {battle.location}. {ourLines}{' '}
              {ourLines === 1 ? 'line was' : 'lines were'} open into that corner. The one taken —{' '}
              {chosenAction?.label ?? chosen.label} — put the order out of the window at{' '}
              {chosen.outcome.resultingOrder.map((p) => participants.get(p)?.code ?? p).join(' · ')}, with{' '}
              <StatusValue value={chosen.outcome.resultingGapS} format={(v) => `${v.toFixed(2)}s`} /> in hand and{' '}
              <StatusValue value={chosen.outcome.energyCostMj} format={(v) => `${v.toFixed(2)} MJ`} /> spent.
            </P>

            <button
              onClick={() => setOpenId(id)}
              className="group mt-2 flex w-full items-center justify-between gap-6 rounded-2xl border border-emerald-400/25 bg-emerald-400/[0.06] px-6 py-5 text-left transition-colors hover:border-emerald-400/50 hover:bg-emerald-400/[0.12]"
            >
              <span>
                <span className="block text-[15px] font-semibold text-white">See the lines it had, and why this one</span>
                <span className="mt-1 block text-[12px] text-white/40">
                  Schematic of the corner, every option with its cost, and the reasoning behind the call
                </span>
              </span>
              <span className="shrink-0 font-mono text-[11px] uppercase tracking-[0.2em] text-emerald-300/80 transition-transform group-hover:translate-x-1">
                Open →
              </span>
            </button>
          </div>
        );
      })}

      <AnimatePresence>
        {open && <OvertakeModal move={open} participants={participants} onClose={() => setOpenId(null)} />}
      </AnimatePresence>
    </Section>
  );
}
