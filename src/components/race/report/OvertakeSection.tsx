'use client';

import React, { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import { OvertakeMove } from '@/lib/race/report';
import { Participant } from '@/lib/race/types';
import { formatClock } from '../primitives';
import { StatusValue } from '../StatusValue';
import { Aside, DataList, Datum, P, Section, Subhead } from './article';
import { OvertakePaths, SHAPES, assignShapes } from './OvertakePaths';

const MOVE_STRUCTURE_SENTENCE: Record<string, string> = {
  sequential: 'our line was committed first and the defence answered it',
  simultaneous: 'both cars chose without seeing the other',
  stochastic: 'the defence was drawn from fitted behaviour rather than chosen',
  learned: 'the defence was estimated from comparable battles',
};

const RESPONSE_LABEL: Record<string, string> = {
  best: 'the strategic best response',
  typical: 'the typical response',
  distribution: 'a distribution of responses',
};

function Modal({
  move,
  participants,
  onClose,
}: {
  move: OvertakeMove;
  participants: Map<string, Participant>;
  onClose: () => void;
}) {
  const { battle, chosen, chosenAction, rejected, response } = move;
  const attacker = participants.get(battle.attackerId);
  const defender = participants.get(battle.defenderId);
  const ourActions = battle.actions.filter((a) => a.participantId === battle.attackerId);
  const shapes = assignShapes(ourActions);
  const knows = battle.informationSets.find((s) => s.participantId === battle.attackerId);
  const flips = battle.sensitivity.filter((s) => s.changesRecommendation);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
      className="fixed inset-0 z-[99999] flex items-start justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-xl sm:p-8"
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label={`How the pass on lap ${battle.lap} was chosen`}
        initial={{ opacity: 0, y: 24, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 24, scale: 0.98 }}
        transition={{ type: 'spring', stiffness: 320, damping: 32 }}
        onClick={(e) => e.stopPropagation()}
        className="my-auto w-full max-w-[860px] rounded-3xl border border-white/12 bg-black/90 p-7 shadow-[0_30px_80px_rgba(0,0,0,0.9)] sm:p-10"
      >
        <div className="flex items-start justify-between gap-6">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-emerald-400/70">
              Lap {battle.lap} · the pass
            </p>
            <h3 className="mt-3 text-2xl font-black tracking-tight text-white sm:text-3xl">
              {attacker?.name ?? battle.attackerId} on {defender?.name ?? battle.defenderId}
            </h3>
            <p className="mt-2 text-[13px] text-white/40">
              {battle.location} · {formatClock(battle.windowStartS)}–{formatClock(battle.windowEndS)}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-full border border-white/10 bg-white/[0.06] p-2 text-white/50 transition-colors hover:bg-white/[0.14] hover:text-white"
          >
            <X size={16} />
          </button>
        </div>

        <div className="mt-8 rounded-2xl border border-white/[0.07] bg-white/[0.02] p-3">
          <OvertakePaths
            ours={shapes}
            chosenActionId={chosenAction?.id}
            attacker={attacker}
            defender={defender}
            responseLabel={chosen.response.label}
          />
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-white/30">
          Schematic. The options, their costs, the line taken and the outcome are supplied by the model; the corner and
          the curves are drawn to show them and are not recorded positions.
        </p>

        <Subhead>The lines that were open</Subhead>
        <ul className="mt-3 flex flex-col gap-2">
          {shapes.map(({ action, shape }) => {
            const isChosen = action.id === chosenAction?.id;
            return (
              <li
                key={action.id}
                className={`rounded-2xl border p-4 ${
                  isChosen ? 'border-emerald-400/40 bg-emerald-400/[0.07]' : 'border-white/[0.07] bg-white/[0.02]'
                }`}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <p className={`text-[15px] font-semibold ${isChosen ? 'text-white' : 'text-white/60'}`}>
                    {action.label}
                  </p>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-widest ${
                      isChosen ? 'bg-emerald-400/20 text-emerald-300' : 'text-white/30'
                    }`}
                  >
                    {isChosen ? 'Taken' : 'Not taken'}
                  </span>
                </div>
                <p className="mt-1.5 text-[11px] uppercase tracking-[0.12em] text-white/25">{SHAPES[shape].name}</p>
                <p className="mt-2 flex flex-wrap gap-x-4 text-[12px] text-white/45">
                  <span>
                    Energy <StatusValue value={action.feasibility.energyCostMj} format={(v) => `${v.toFixed(2)} MJ`} />
                  </span>
                  <span>
                    Tyre <StatusValue value={action.feasibility.tyreCostLaps} format={(v) => `${v.toFixed(2)} laps`} />
                  </span>
                  {!action.feasibility.available && <span className="text-amber-300/70">Not available</span>}
                  {action.feasibility.ruleConstraints.map((c) => (
                    <span key={c}>{c}</span>
                  ))}
                </p>
              </li>
            );
          })}
        </ul>

        <Subhead>Why this line</Subhead>
        <P className="mt-2">
          The window was solved as a {battle.moveStructure} move —{' '}
          {MOVE_STRUCTURE_SENTENCE[battle.moveStructure] ?? 'the structure the backend declared'}. Against{' '}
          {RESPONSE_LABEL[chosen.response.kind] ?? 'the declared response'}, {chosen.response.label}, the line taken is
          the one the model returned: {chosen.label}.
        </P>
        <DataList>
          {knows && (
            <Datum label={`What ${attacker?.code ?? 'we'} knew`}>
              <span className="text-[13px] font-normal text-white/60">{knows.knows.join('; ')}</span>
            </Datum>
          )}
          <Datum label="Weighed against">
            <span className="text-[13px] font-normal text-white/60">
              {battle.objectives.terms.join(', ')}
              {battle.objectives.combinedUtility ? ` — ${battle.objectives.combinedUtility}` : ''}
            </span>
          </Datum>
          <Datum label={`What ${defender?.code ?? 'the car ahead'} was expected to do`}>
            <span className="text-[13px] font-normal text-white/60">{response?.label ?? chosen.response.label}</span>
            {response && (
              <span className="ml-3 text-[12px] font-normal text-white/35">
                <StatusValue value={response.feasibility.energyCostMj} format={(v) => `${v.toFixed(2)} MJ`} />
                {response.feasibility.ruleConstraints.length > 0 && ` · ${response.feasibility.ruleConstraints.join('; ')}`}
              </span>
            )}
          </Datum>
          {chosen.response.probability && (
            <Datum label="Chance of that answer">
              <StatusValue value={chosen.response.probability} format={(v) => `${(v * 100).toFixed(0)}%`} />
            </Datum>
          )}
          <Datum label="Chance the move sticks">
            <StatusValue value={chosen.outcome.passChance} format={(v) => `${(v * 100).toFixed(0)}%`} />
          </Datum>
          <Datum label="Order out of the window">
            {chosen.outcome.resultingOrder.map((id) => participants.get(id)?.code ?? id).join(' · ')}
          </Datum>
          <Datum label="Gap out of the window">
            <StatusValue value={chosen.outcome.resultingGapS} format={(v) => `${v.toFixed(2)}s`} />
          </Datum>
          <Datum label="Energy it cost">
            <StatusValue value={chosen.outcome.energyCostMj} format={(v) => `${v.toFixed(2)} MJ`} />
          </Datum>
          <Datum label="Risk carried">{chosen.outcome.riskLabel}</Datum>
        </DataList>

        {rejected.length > 0 && (
          <P className="mt-4">
            The {rejected.length === 1 ? 'other line' : `other ${rejected.length} lines`} stayed open the whole time
            {rejected.some((a) => a.kind === 'wait') ? ', including simply staying put' : ''}. They are not worse in
            every respect — several cost less energy and less tyre — they are the lines the model did not return under
            the opponent belief it was given.
          </P>
        )}

        <Subhead>What would have changed it</Subhead>
        {battle.sensitivity.length === 0 ? (
          <Aside>No alternative formulation was supplied for this window.</Aside>
        ) : (
          <>
            <DataList>
              {battle.sensitivity.map((s) => (
                <Datum key={s.assumption} label={s.assumption}>
                  <span className={s.changesRecommendation ? 'text-amber-300' : 'text-white/70'}>
                    {s.recommendedLabel}
                  </span>
                  <span className="ml-3 text-[12px] font-normal text-white/35">{s.outcomeSummary}</span>
                </Datum>
              ))}
            </DataList>
            {flips.length > 0 && (
              <Aside>
                Under {flips.length === 1 ? 'one supported opponent model' : `${flips.length} supported opponent models`}{' '}
                a different line is recommended. The pass happened; which line was right is a question the evidence here
                does not settle.
              </Aside>
            )}
          </>
        )}

        <p className="mt-8 border-t border-white/10 pt-4 text-[11px] leading-relaxed text-white/30">
          Chance the move sticks describes behaviour inside the declared window only — it is not the physical
          feasibility of the line, which is listed with each option above.
        </p>
      </motion.div>
    </motion.div>
  );
}

export function OvertakeSection({
  index,
  moves,
  participants,
}: {
  index: string;
  moves: OvertakeMove[];
  participants: Map<string, Participant>;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const open = moves.find((m) => `${m.battle.id}:${m.chosen.id}` === openId) ?? null;

  if (moves.length === 0) return null;

  return (
    <Section
      index={index}
      title={moves.length === 1 ? 'The move' : 'The moves'}
      standfirst="Where our car came out of a fight ahead of the one it was behind — and the lines it turned down to do it."
    >
      {moves.map((move) => {
        const { battle, chosen, chosenAction } = move;
        const defender = participants.get(battle.defenderId);
        const attacker = participants.get(battle.attackerId);
        const id = `${battle.id}:${chosen.id}`;

        return (
          <div key={id}>
            <P>
              On lap {battle.lap}, {formatClock(battle.windowStartS)} in, {attacker?.name ?? battle.attackerId} arrived{' '}
              <StatusValue value={battle.startingGapS} format={(v) => `${v.toFixed(2)}s`} /> behind{' '}
              {defender?.name ?? battle.defenderId} at {battle.location}. Three lines were open into that corner. The one
              taken — {chosenAction?.label ?? chosen.label} — put the order out of the window at{' '}
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
        {open && <Modal move={open} participants={participants} onClose={() => setOpenId(null)} />}
      </AnimatePresence>
    </Section>
  );
}
