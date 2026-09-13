import React from 'react';
import { Battle } from '@/lib/race/types';
import { Eyebrow } from '../primitives';

/**
 * The same battle under other supported opponent beliefs and formulations. Where the
 * typical response and the strategic best response disagree, the recommendation is
 * sensitive to a belief the backend cannot verify — and that is the finding.
 */
export function BattleSensitivity({ battle }: { battle: Battle }) {
  if (battle.sensitivity.length === 0) {
    return (
      <div className="px-6 py-5">
        <Eyebrow>Sensitivity</Eyebrow>
        <p className="mt-2 text-[11px] italic text-white/25">
          No alternative formulation was supplied for this battle.
        </p>
      </div>
    );
  }

  const disagrees = battle.sensitivity.some((s) => s.changesRecommendation);

  return (
    <div className="px-6 py-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <Eyebrow>Sensitivity · typical response · best response · other supported models</Eyebrow>
        {disagrees && (
          <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300">
            Recommendation changes with opponent belief
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left">
          <thead>
            <tr className="border-b border-white/[0.07]">
              {['Assumption', 'Formulation', 'Recommended', 'Outcome'].map((h) => (
                <th key={h} className="py-2 pr-4 text-[9px] font-medium uppercase tracking-widest text-white/35">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {battle.sensitivity.map((s) => (
              <tr
                key={s.assumption}
                className={`border-b border-white/[0.04] ${s.changesRecommendation ? 'bg-amber-400/[0.04]' : ''}`}
              >
                <td className="py-2.5 pr-4 text-[11px] text-white/65">{s.assumption}</td>
                <td className="py-2.5 pr-4 text-[11px] capitalize text-white/45">{s.moveStructure}</td>
                <td className="py-2.5 pr-4 text-[11px] font-semibold text-white/80">
                  {s.recommendedLabel}
                  {s.changesRecommendation && <span className="ml-2 text-amber-300/70">changes</span>}
                </td>
                <td className="py-2.5 pr-4 text-[11px] text-white/45">{s.outcomeSummary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {disagrees && (
        <p className="mt-3 text-[10px] leading-relaxed text-white/35">
          The preferred action is not stable across the supplied opponent models. Which one is correct is not
          something this view decides — the disagreement itself is the result.
        </p>
      )}
    </div>
  );
}
