'use client';

import React, { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { OvertakeMove } from '@/lib/race/report';
import { Participant } from '@/lib/race/types';
import { Eyebrow, Panel, formatClock } from '../primitives';
import { StatusValue } from '../StatusValue';
import { OvertakeModal } from './OvertakeModal';

const FACE = 'absolute inset-0 flex flex-col rounded-3xl border p-5';
const HIDDEN: React.CSSProperties = { backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden' };

const DEFENCE_SENTENCE: Record<string, string> = {
  best: 'the best answer available to it',
  typical: 'its typical answer',
  distribution: 'a spread of answers rather than one',
};

const Stat = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="min-w-0">
    <p className="truncate text-[9px] uppercase tracking-widest text-white/30">{label}</p>
    <p className="mt-1 truncate text-[13px] font-bold tabular-nums text-white/85">{children}</p>
  </div>
);

/** Which race the window belongs to. Before the branch, both races are the same race. */
function raceOf(lap: number, side: string, branchLap: number): { label: string; className: string } {
  if (lap <= branchLap) return { label: 'Both races', className: 'text-white/45' };
  return side === 'baseline'
    ? { label: 'Recorded race', className: 'text-sky-400' }
    : { label: 'Our plan', className: 'text-emerald-400' };
}

function Card({
  move,
  participants,
  branchLap,
  onOpen,
}: {
  move: OvertakeMove;
  participants: Map<string, Participant>;
  branchLap: number;
  onOpen: () => void;
}) {
  const [flipped, setFlipped] = useState(false);
  const { battle, chosen, chosenAction } = move;
  const attacker = participants.get(battle.attackerId);
  const defender = participants.get(battle.defenderId);
  const race = raceOf(battle.lap, battle.baselineSide, branchLap);
  const ourLines = battle.actions.filter((a) => a.participantId === battle.attackerId).length;
  const flips = battle.sensitivity.filter((s) => s.changesRecommendation);

  return (
    <div className="h-[330px]" style={{ perspective: 1400 }}>
      <motion.div
        animate={{ rotateY: flipped ? 180 : 0 }}
        transition={{ type: 'spring', stiffness: 220, damping: 26 }}
        style={{ transformStyle: 'preserve-3d' }}
        className="relative h-full w-full"
      >
        {/* Front — what happened. */}
        <div
          style={HIDDEN}
          className={`${FACE} border-white/[0.08] bg-neutral-950/80 shadow-[0_12px_40px_rgba(0,0,0,0.5)]`}
        >
          <div className="flex items-start justify-between gap-3">
            <Eyebrow className={race.className}>{race.label}</Eyebrow>
            <span className="shrink-0 font-mono text-[10px] uppercase tracking-widest text-white/35">
              Lap {battle.lap} · {formatClock(battle.windowStartS)}
            </span>
          </div>

          <div className="mt-4 flex items-center gap-2.5">
            <span
              className="h-8 w-1 shrink-0 rounded-full"
              style={{ background: attacker?.teamColor ?? 'rgba(255,255,255,0.25)' }}
            />
            <p className="text-xl font-black tracking-tight text-white">
              {attacker?.code ?? battle.attackerId}
              <span className="mx-2 text-white/25">on</span>
              {defender?.code ?? battle.defenderId}
            </p>
            <span
              className="h-8 w-1 shrink-0 rounded-full"
              style={{ background: defender?.teamColor ?? 'rgba(255,255,255,0.25)' }}
            />
          </div>
          <p className="mt-1.5 line-clamp-2 text-[11px] leading-relaxed text-white/35">{battle.location}</p>

          <div className="mt-4 rounded-2xl border border-emerald-400/25 bg-emerald-400/[0.07] px-3.5 py-3">
            <p className="text-[9px] uppercase tracking-widest text-emerald-300/70">Line taken</p>
            <p className="mt-1 line-clamp-2 text-[13px] font-semibold leading-snug text-white">
              {chosenAction?.label ?? chosen.label}
            </p>
          </div>

          <div className="mt-auto grid grid-cols-3 gap-3 border-t border-white/[0.06] pt-3.5">
            <Stat label="Sticks">
              <StatusValue value={chosen.outcome.passChance} format={(v) => `${(v * 100).toFixed(0)}%`} hideMark />
            </Stat>
            <Stat label="Gap out">
              <StatusValue value={chosen.outcome.resultingGapS} format={(v) => `${v.toFixed(2)}s`} hideMark />
            </Stat>
            {/* The range is dropped here and printed in full in the breakdown behind. */}
            <Stat label="Energy">
              <StatusValue
                value={chosen.outcome.energyCostMj}
                format={(v) => `${v.toFixed(2)} MJ`}
                hideMark
                hideInterval
              />
            </Stat>
          </div>

          <button
            onClick={() => setFlipped(true)}
            className="mt-3 w-full rounded-xl border border-white/[0.08] bg-white/[0.04] py-2 text-[10px] font-bold uppercase tracking-widest text-white/55 transition-colors hover:bg-white/[0.1] hover:text-white"
          >
            How it happened →
          </button>
        </div>

        {/* Back — how it happened. */}
        <div
          style={{ ...HIDDEN, transform: 'rotateY(180deg)' }}
          className={`${FACE} border-emerald-400/20 bg-neutral-950/90 shadow-[0_12px_40px_rgba(0,0,0,0.5)]`}
        >
          <Eyebrow className="text-emerald-400/70">How it happened</Eyebrow>

          <p className="mt-3 text-[12px] leading-[1.7] text-white/60">
            {attacker?.code ?? battle.attackerId} arrived{' '}
            <StatusValue value={battle.startingGapS} format={(v) => `${v.toFixed(2)}s`} hideMark /> behind with{' '}
            {ourLines} {ourLines === 1 ? 'line' : 'lines'} open. The window was solved as a {battle.moveStructure} move
            against {DEFENCE_SENTENCE[chosen.response.kind] ?? 'the declared response'} — {chosen.response.label} — and
            the model returned: {chosenAction?.label ?? chosen.label}.
          </p>

          <p className="mt-3 text-[12px] leading-[1.7] text-white/60">
            Out of the window the order is{' '}
            {chosen.outcome.resultingOrder.map((id) => participants.get(id)?.code ?? id).join(' · ')}. Risk carried:{' '}
            {chosen.outcome.riskLabel}.
          </p>

          {flips.length > 0 && (
            <p className="mt-3 border-l-2 border-amber-400/30 pl-3 text-[11px] leading-relaxed text-amber-200/60">
              {flips.length === 1 ? 'One supported opponent model' : `${flips.length} supported opponent models`}{' '}
              would have recommended a different line.
            </p>
          )}

          <div className="mt-auto flex gap-2 pt-3">
            <button
              onClick={() => setFlipped(false)}
              className="rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-white/50 transition-colors hover:bg-white/[0.1] hover:text-white"
            >
              ← Back
            </button>
            <button
              onClick={onOpen}
              className="flex-1 rounded-xl border border-emerald-400/30 bg-emerald-400/10 py-2 text-[10px] font-bold uppercase tracking-widest text-emerald-300 transition-colors hover:bg-emerald-400/20"
            >
              Full breakdown
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

/**
 * One card per pass our car made: the facts on the front, how it came about on the
 * back, and the whole decision — every line that was open, its cost, and the model's
 * reasoning — in the breakdown behind it.
 *
 * Only windows the model actually solved appear here. A fight with no returned solution
 * is not a pass, and none is drawn for it.
 */
export function OvertakeFlashCards({
  moves,
  participants,
  branchLap,
}: {
  moves: OvertakeMove[];
  participants: Map<string, Participant>;
  branchLap: number;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const open = moves.find((m) => `${m.battle.id}:${m.chosen.id}` === openId) ?? null;

  return (
    <Panel className="p-6 px-7">
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <Eyebrow>Overtakes · {moves.length} solved</Eyebrow>
          <p className="mt-1.5 text-[12px] leading-relaxed text-white/40">
            Every window our car came out of ahead of the car it was behind. Flip a card for how it happened, or open
            the breakdown for the lines it turned down.
          </p>
        </div>
      </div>

      {moves.length === 0 ? (
        <p className="text-[12px] italic text-white/25">
          No decision window in either race has a solution that puts our car ahead, so there is nothing to card here.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {moves.map((move) => (
            <Card
              key={`${move.battle.id}:${move.chosen.id}`}
              move={move}
              participants={participants}
              branchLap={branchLap}
              onOpen={() => setOpenId(`${move.battle.id}:${move.chosen.id}`)}
            />
          ))}
        </div>
      )}

      <AnimatePresence>
        {open && <OvertakeModal move={open} participants={participants} onClose={() => setOpenId(null)} />}
      </AnimatePresence>
    </Panel>
  );
}
