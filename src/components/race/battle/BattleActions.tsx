import React from 'react';
import { Battle, Participant } from '@/lib/race/types';
import { Eyebrow } from '../primitives';
import { StatusValue } from '../StatusValue';

/**
 * Sequential games place the first move before the response; simultaneous games put
 * both action sets on equal footing. The layout follows the supplied structure rather
 * than forcing one interpretation.
 */
export function BattleActions({
  battle,
  participants,
}: {
  battle: Battle;
  participants: Map<string, Participant>;
}) {
  const sides = [battle.attackerId, battle.defenderId];
  const sequential = battle.moveStructure === 'sequential';

  return (
    <div className="grid grid-cols-1 gap-6 border-b border-white/[0.07] px-6 py-5 md:grid-cols-3">
      <div className="md:col-span-2">
        <Eyebrow className="mb-3">Available actions · feasibility and cost</Eyebrow>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {sides.map((id, i) => (
            <div key={id}>
              <p className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-widest text-white/40">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: participants.get(id)?.teamColor }} />
                {participants.get(id)?.code}
                {sequential && (
                  <span className="rounded-full border border-white/10 px-1.5 text-[8px] text-white/35">
                    {i === 0 ? 'moves first' : 'responds'}
                  </span>
                )}
              </p>
              <ul className="space-y-2">
                {battle.actions
                  .filter((a) => a.participantId === id)
                  .map((a) => (
                    <li key={a.id} className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
                      <p className="text-[11px] font-semibold text-white/80">{a.label}</p>
                      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-white/45">
                        <span>
                          Energy <StatusValue value={a.feasibility.energyCostMj} format={(v) => `${v.toFixed(2)} MJ`} />
                        </span>
                        <span>
                          Tyre <StatusValue value={a.feasibility.tyreCostLaps} format={(v) => `${v.toFixed(2)} laps`} />
                        </span>
                        {!a.feasibility.available && <span className="text-rose-300/70">not physically available</span>}
                      </div>
                      {a.feasibility.ruleConstraints.length > 0 && (
                        <p className="mt-1 text-[10px] italic text-white/30">
                          {a.feasibility.ruleConstraints.join('; ')}
                        </p>
                      )}
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      <div>
        <Eyebrow className="mb-3">Objectives</Eyebrow>
        <ul className="space-y-1.5">
          {battle.objectives.terms.map((t) => (
            <li key={t} className="flex gap-2 text-[11px] text-white/60">
              <span className="text-white/25">·</span>
              {t}
            </li>
          ))}
        </ul>
        {battle.objectives.combinedUtility && (
          <p className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.03] p-3 text-[10px] leading-relaxed text-white/45">
            Supplied utility: {battle.objectives.combinedUtility}
          </p>
        )}

        <Eyebrow className="mb-2 mt-5">Information sets</Eyebrow>
        {battle.informationSets.map((s) => (
          <div key={s.participantId} className="mb-2">
            <p className="text-[10px] font-semibold text-white/55">{participants.get(s.participantId)?.code} knows</p>
            <ul className="mt-0.5 space-y-0.5">
              {s.knows.map((k) => (
                <li key={k} className="flex gap-1.5 text-[10px] text-white/40">
                  <span className="text-white/20">·</span>
                  {k}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
