import React from 'react';
import { DecisionStability } from '@/lib/race/types';
import { Eyebrow, Panel } from './primitives';

/**
 * A preferred strategy is shown only with the assumptions that make it preferred.
 * When the preference changes under another supported assumption, that change is part
 * of the comparison result rather than a footnote to it.
 */
export function RobustnessPanel({ stability }: { stability: DecisionStability }) {
  return (
    <Panel className="p-6 px-8">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Eyebrow>Robustness · decision stability</Eyebrow>
        <span
          className={`rounded-full border px-3 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
            stability.changesUnderSupportedAssumption
              ? 'border-amber-400/30 bg-amber-400/10 text-amber-300'
              : 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300'
          }`}
        >
          {stability.changesUnderSupportedAssumption ? 'Preference is not stable' : 'Preference holds'}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-left">
          <thead>
            <tr className="border-b border-white/[0.07]">
              {['Assumption', 'Preferred', 'Outcome'].map((h) => (
                <th key={h} className="py-2 pr-4 text-[9px] font-medium uppercase tracking-widest text-white/35">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stability.cases.map((c) => {
              const flipped = c.preferredScenarioId !== stability.preferredScenarioId;
              const unresolved = c.preferredScenarioId === 'unresolved';
              return (
                <tr key={c.assumption} className={`border-b border-white/[0.04] ${flipped ? 'bg-amber-400/[0.04]' : ''}`}>
                  <td className="py-2.5 pr-4 text-[11px] text-white/65">{c.assumption}</td>
                  <td className="py-2.5 pr-4 text-[11px] font-semibold text-white/80">
                    {unresolved ? <span className="italic text-white/25">unavailable</span> : c.preferredScenarioId}
                  </td>
                  <td className="py-2.5 pr-4 text-[11px] text-white/45">{c.outcomeSummary}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-4 border-t border-white/[0.06] pt-3 text-[11px] leading-relaxed text-white/45">
        {stability.note}
      </p>
    </Panel>
  );
}
