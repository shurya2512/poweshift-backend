import React from 'react';
import { ComparisonResult, RaceOutcome } from '@/lib/race/types';
import { Eyebrow, Panel } from './primitives';
import { StatusValue } from './StatusValue';

const Outcome = ({ title, accent, outcome }: { title: string; accent: string; outcome: RaceOutcome }) => (
  <Panel className="p-6">
    <Eyebrow className={accent}>{title}</Eyebrow>
    <div className="mt-3 flex items-baseline gap-2">
      <span className="text-4xl font-black tracking-tighter text-white">
        <StatusValue value={outcome.finishPosition} format={(v) => `P${v}`} hideMark />
      </span>
      <span className="text-xs font-semibold uppercase tracking-widest text-white/35">
        {outcome.classifiedStatus}
      </span>
    </div>
    <dl className="mt-4 space-y-1.5 text-[11px]">
      <div className="flex justify-between text-white/45">
        <dt>Total time</dt>
        <dd className="text-white/70">
          <StatusValue value={outcome.totalTimeS} format={(v) => `${v.toFixed(2)}s`} />
        </dd>
      </div>
      <div className="flex justify-between text-white/45">
        <dt>Pit stops</dt>
        <dd className="text-white/70">{outcome.pitCount}</dd>
      </div>
      <div className="flex justify-between text-white/45">
        <dt>Tyre use</dt>
        <dd className="text-white/70">{outcome.tyreUse}</dd>
      </div>
    </dl>
  </Panel>
);

/**
 * The race-level answer. A comparison identifies its branch point and its common
 * evidence cutoff; results from different cutoffs are not compared directly.
 */
export function OutcomeRow({ comparison }: { comparison: ComparisonResult }) {
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
      <Outcome title="Baseline outcome" accent="text-sky-400" outcome={comparison.baseline} />

      <Panel className="flex flex-col justify-center p-6">
        <Eyebrow>Comparison delta</Eyebrow>
        <div className="mt-3 text-3xl font-black tracking-tighter text-white">
          <StatusValue
            value={comparison.relativePositions}
            format={(v) => (v === 0 ? 'Level' : v < 0 ? `${-v} place gain` : `${v} place loss`)}
          />
        </div>
        <div className="mt-3 text-[11px] text-white/45">
          Race time{' '}
          <StatusValue value={comparison.relativeTimeS} format={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}s`} />
        </div>
        <p className="mt-4 border-t border-white/[0.06] pt-3 text-[10px] leading-relaxed text-white/30">
          Branch: lap {comparison.branchPoint.lap} — {comparison.branchPoint.description}. Both outcomes share an
          evidence cutoff of {comparison.evidenceCutoffS.toFixed(0)} s. Raw race time spans different
          interruptions in each world; read it with the assumptions.
        </p>
      </Panel>

      <Outcome title="Alternative outcome" accent="text-emerald-400" outcome={comparison.alternative} />
    </div>
  );
}
