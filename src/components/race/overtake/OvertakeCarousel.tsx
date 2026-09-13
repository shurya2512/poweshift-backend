'use client';

import React, { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { ChevronsUp } from 'lucide-react';
import { FeatureCarousel, FeatureItem } from '@/components/ui/feature-carousel';
import { OvertakeMove } from '@/lib/race/report';
import { Participant } from '@/lib/race/types';
import { Eyebrow, Panel, formatClock } from '../primitives';
import { StatusValue } from '../StatusValue';
import { OvertakeModal } from './OvertakeModal';
import { OvertakePaths, assignShapes } from './OvertakePaths';

const keyOf = (move: OvertakeMove) => `${move.battle.id}:${move.chosen.id}`;

/** One pass as a carousel item: the schematic is the picture, the line taken the caption. */
function toItem(move: OvertakeMove, participants: Map<string, Participant>): FeatureItem {
  const { battle, chosen, chosenAction } = move;
  const attacker = participants.get(battle.attackerId);
  const defender = participants.get(battle.defenderId);
  const ours = battle.actions.filter((a) => a.participantId === battle.attackerId);

  return {
    id: keyOf(move),
    label: `L${battle.lap} · ${attacker?.code ?? battle.attackerId} on ${defender?.code ?? battle.defenderId}`,
    icon: ChevronsUp,
    tag: `Lap ${battle.lap} · ${formatClock(battle.windowStartS)}`,
    media: (
      // Held to the top of the card, clear of the caption over the bottom.
      <div className="h-full w-full bg-[#050505] px-4 pb-24 pt-10 [&>svg]:h-full [&>svg]:w-full">
        <OvertakePaths
          ours={assignShapes(ours)}
          chosenActionId={chosenAction?.id}
          attacker={attacker}
          defender={defender}
          responseLabel={chosen.response.label}
        />
      </div>
    ),
    description: (
      <>
        {chosenAction?.label ?? chosen.label}
        <span className="mt-2 block text-[11px] uppercase tracking-widest text-white/50">
          Sticks <StatusValue value={chosen.outcome.passChance} format={(v) => `${(v * 100).toFixed(0)}%`} hideMark />
          {' · '}Gap out <StatusValue value={chosen.outcome.resultingGapS} format={(v) => `${v.toFixed(2)}s`} hideMark />
          {' · '}
          <StatusValue value={chosen.outcome.energyCostMj} format={(v) => `${v.toFixed(2)} MJ`} hideMark hideInterval />
          {' · '}
          <span className="text-white/80">Open breakdown →</span>
        </span>
      </>
    ),
  };
}

/**
 * Our car's passes as a carousel: pick one on the left, and its card on the right opens
 * the whole decision — every line that was open, its cost, and the model's reasoning.
 *
 * Only windows the model actually solved appear here. A fight with no returned solution
 * is not a pass, and none is drawn for it.
 */
export function OvertakeCarousel({
  moves,
  participants,
}: {
  moves: OvertakeMove[];
  participants: Map<string, Participant>;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const open = moves.find((m) => keyOf(m) === openId) ?? null;

  return (
    <Panel className="p-6 px-7">
      <div className="mb-5">
        <Eyebrow>Overtakes · {moves.length} solved</Eyebrow>
        <p className="mt-1.5 text-[12px] leading-relaxed text-white/40">
          Every window our car came out of ahead of the car it was behind. Pick a pass on the left, then open its card
          for the lines it turned down.
        </p>
      </div>

      {moves.length === 0 ? (
        <p className="text-[12px] italic text-white/25">
          No decision window has a solution that puts our car ahead, so there is nothing to show here.
        </p>
      ) : (
        <FeatureCarousel items={moves.map((m) => toItem(m, participants))} onOpen={setOpenId} />
      )}

      <AnimatePresence>
        {open && <OvertakeModal move={open} participants={participants} onClose={() => setOpenId(null)} />}
      </AnimatePresence>
    </Panel>
  );
}
