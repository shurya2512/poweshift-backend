import React from 'react';
import { Battle, Participant, RaceFrame, WorldSide } from '@/lib/race/types';
import { isSupported } from '@/lib/race/valued';
import { Eyebrow } from '../primitives';

/** Cars whose state changes materially inside the window, nearest pair first. */
function relevant(battle: Battle): string[] {
  return [battle.attackerId, battle.defenderId, ...battle.affectedIds];
}

function WorldStrip({
  frame,
  side,
  battle,
  participants,
  title,
  accent,
}: {
  frame: RaceFrame;
  side: WorldSide;
  battle: Battle;
  participants: Map<string, Participant>;
  title: string;
  accent: string;
}) {
  const ids = relevant(battle);
  const states = frame[side].field
    .filter((p) => ids.includes(p.participantId))
    .sort((a, b) => a.rank - b.rank);

  if (states.length === 0) {
    return (
      <div className="flex-1 p-4">
        <Eyebrow className={accent}>{title}</Eyebrow>
        <p className="mt-3 text-[11px] italic text-white/25">These entries are not running in this world.</p>
      </div>
    );
  }

  const leader = states[0];
  const leaderGap = isSupported(leader.gapS) ? leader.gapS.value : 0;
  const offsets = states.map((s) => (isSupported(s.gapS) ? s.gapS.value - leaderGap : null));
  const span = Math.max(1.5, ...offsets.map((o) => o ?? 0));

  return (
    <div className="flex-1 p-4">
      <Eyebrow className={accent}>{title}</Eyebrow>

      <div className="relative mt-4 h-24 rounded-2xl border border-white/[0.06] bg-white/[0.02]">
        {/* Track direction */}
        <div className="absolute left-4 right-4 top-1/2 h-px -translate-y-1/2 bg-white/10" />
        {states.map((s, i) => {
          const offset = offsets[i];
          if (offset === null) return null;
          const pct = 4 + (1 - offset / span) * 88;
          const p = participants.get(s.participantId);
          return (
            <div
              key={s.participantId}
              className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 text-center"
              style={{ left: `${pct}%` }}
            >
              <div
                className="mx-auto h-3.5 w-3.5 rounded-full border-2 border-black/40"
                style={{ backgroundColor: p?.teamColor }}
              />
              <p className="mt-1 text-[9px] font-bold text-white/80">{p?.code}</p>
              <p className="text-[8px] tabular-nums text-white/35">
                P{s.rank} {offset > 0 ? `+${offset.toFixed(2)}s` : 'ahead'}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * The battle window in both worlds.
 *
 * After the decision window the full field continues from the chosen branch — opponents
 * are not reset to their recorded positions, which is the difference between a
 * counterfactual and a recorded replay.
 */
export function BattleReplay({
  battle,
  frame,
  participants,
}: {
  battle: Battle;
  frame: RaceFrame;
  participants: Map<string, Participant>;
}) {
  const inWindow = frame.raceTimeS >= battle.windowStartS && frame.raceTimeS <= battle.windowEndS;

  return (
    <div className="border-b border-white/[0.07]">
      <div className="flex items-center justify-between px-6 pt-5">
        <Eyebrow>Local replay — battle window</Eyebrow>
        <span
          className={`rounded-full border px-2.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${
            inWindow
              ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300'
              : 'border-white/10 bg-white/[0.04] text-white/40'
          }`}
        >
          {inWindow ? 'playhead inside window' : 'playhead outside window'}
        </span>
      </div>

      <div className="flex flex-col divide-y divide-white/[0.06] px-2 md:flex-row md:divide-x md:divide-y-0">
        <WorldStrip
          frame={frame}
          side="baseline"
          battle={battle}
          participants={participants}
          title="Baseline battle replay"
          accent="text-sky-400"
        />
        <WorldStrip
          frame={frame}
          side="alternative"
          battle={battle}
          participants={participants}
          title="Selected decision branch"
          accent="text-emerald-400"
        />
      </div>

      <p className="px-6 pb-5 text-[10px] leading-relaxed text-white/30">
        Both cars are shown, plus any other entry whose state changes materially in this window. After the
        window the field continues from the chosen branch; opponents are not reset to their recorded
        positions. In this scenario the opponents are recorded and do not react to the changed decision —
        that fixed-opponent assumption applies to every number here.
      </p>
    </div>
  );
}
