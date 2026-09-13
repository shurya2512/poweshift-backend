import React from 'react';
import { Battle, BattleSolution, Participant, SolutionStatus } from '@/lib/race/types';
import { Eyebrow } from '../primitives';
import { StatusValue } from '../StatusValue';

const STATUS_COPY: Record<SolutionStatus, { label: string; tone: string; note: string }> = {
  pure: {
    label: 'Pure result',
    tone: 'text-emerald-300 border-emerald-400/30 bg-emerald-400/10',
    note: 'One action is optimal under the declared model and opponent belief.',
  },
  mixed: {
    label: 'Mixed result',
    tone: 'text-sky-300 border-sky-400/30 bg-sky-400/10',
    note: 'The solution randomises over actions; no single action is optimal on its own.',
  },
  multiple: {
    label: 'Multiple results',
    tone: 'text-amber-300 border-amber-400/30 bg-amber-400/10',
    note: 'More than one outcome is valid under this model. There is no justified rule for choosing between them, so both are shown.',
  },
  none: {
    label: 'No stable result',
    tone: 'text-white/60 border-white/15 bg-white/[0.05]',
    note: 'No stable solution exists for this formulation. Nothing is recommended.',
  },
  solver_failure: {
    label: 'Solver failure',
    tone: 'text-rose-300 border-rose-400/30 bg-rose-400/10',
    note: 'The solver did not return a result. The inputs are preserved; no outcome is inferred from them.',
  },
};

function Solution({
  solution,
  participants,
  index,
  multiple,
}: {
  solution: BattleSolution;
  participants: Map<string, Participant>;
  index: number;
  multiple: boolean;
}) {
  const { outcome, response } = solution;

  return (
    <div className="flex-1 rounded-2xl border border-white/[0.07] bg-white/[0.03] p-4">
      {multiple && (
        <p className="mb-2 text-[9px] uppercase tracking-widest text-white/35">Valid outcome {index + 1}</p>
      )}
      <p className="text-sm font-bold text-white">{solution.label}</p>

      <div className="mt-3 space-y-2 border-t border-white/[0.06] pt-3">
        <div className="flex justify-between text-[11px]">
          <span className="text-white/40">
            {response.kind === 'best'
              ? 'Strategic best response'
              : response.kind === 'typical'
                ? 'Typical response'
                : 'Response distribution'}
          </span>
          <span className="text-right font-semibold text-white/75">{response.label}</span>
        </div>
        {response.probability && (
          <div className="flex justify-between text-[11px]">
            <span className="text-white/40">Response likelihood</span>
            <span className="font-semibold text-white/75">
              <StatusValue value={response.probability} format={(v) => `${(v * 100).toFixed(0)}%`} />
            </span>
          </div>
        )}
        <div className="flex justify-between text-[11px]">
          <span className="text-white/40">Pass chance</span>
          <span className="font-semibold text-white/75">
            <StatusValue value={outcome.passChance} format={(v) => `${(v * 100).toFixed(0)}%`} />
          </span>
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="text-white/40">Resulting order</span>
          <span className="font-semibold text-white/75">
            {outcome.resultingOrder.map((id) => participants.get(id)?.code ?? id).join(' · ')}
          </span>
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="text-white/40">Resulting gap</span>
          <span className="font-semibold text-white/75">
            <StatusValue value={outcome.resultingGapS} format={(v) => `${v.toFixed(2)}s`} />
          </span>
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="text-white/40">Energy cost</span>
          <span className="font-semibold text-white/75">
            <StatusValue value={outcome.energyCostMj} format={(v) => `${v.toFixed(2)} MJ`} />
          </span>
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="text-white/40">Risk</span>
          <span className="text-right font-semibold text-white/75">{outcome.riskLabel}</span>
        </div>
      </div>
    </div>
  );
}

/**
 * No result here is the opponent's actual intent. Where the backend cannot justify a
 * unique solution, every valid outcome stays visible along with the absence of a
 * unique answer — and a failed solve is reported, never replaced by a guess.
 */
export function BattleSolutions({
  battle,
  participants,
}: {
  battle: Battle;
  participants: Map<string, Participant>;
}) {
  const status = STATUS_COPY[battle.solutionStatus];
  const multiple = battle.solutionStatus === 'multiple';

  return (
    <div className="border-b border-white/[0.07] px-6 py-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Eyebrow>Recommended action · expected response · outcome range</Eyebrow>
        <span className={`rounded-full border px-3 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${status.tone}`}>
          {status.label}
        </span>
      </div>

      <p className="mb-4 text-[11px] leading-relaxed text-white/45">{status.note}</p>

      {battle.solutions.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/12 bg-white/[0.02] p-5">
          <p className="text-[11px] leading-relaxed text-white/55">
            {battle.solverNote ?? 'No result was returned.'}
          </p>
          <p className="mt-3 text-[10px] uppercase tracking-widest text-white/25">
            Battle context, actions and costs above remain as supplied
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-4 md:flex-row">
            {battle.solutions.map((s, i) => (
              <Solution key={s.id} solution={s} participants={participants} index={i} multiple={multiple} />
            ))}
          </div>

          <p className="mt-4 border-t border-white/[0.06] pt-3 text-[10px] leading-relaxed text-white/30">
            Pass chance describes behaviour inside the declared opportunity window ({battle.location}). Physical
            feasibility is listed separately with each action and is not folded into this probability. No response
            shown here is a claim about what the opponent actually intended.
          </p>
        </>
      )}
    </div>
  );
}
