import React from 'react';
import { WorldSide } from '@/lib/race/types';

/**
 * Which of the two races the live regions are reading.
 *
 * One at a time, always named. The two races keep separate orders, laps and flags, so
 * a single feed showing both at once would be a third race that nobody ran.
 */
export const WORLD_LABEL: Record<WorldSide, string> = {
  baseline: 'Recorded race',
  alternative: 'Our plan',
};

export const WORLD_ACCENT: Record<WorldSide, string> = {
  baseline: 'text-sky-400',
  alternative: 'text-emerald-400',
};

const ON: Record<WorldSide, string> = {
  baseline: 'bg-sky-400/15 text-sky-300 border-sky-400/40',
  alternative: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/40',
};

const OFF = 'border-transparent text-white/35 hover:text-white/70';

export function WorldSwitch({
  value,
  onChange,
}: {
  value: WorldSide;
  onChange: (side: WorldSide) => void;
}) {
  return (
    <div className="flex shrink-0 items-center gap-1 rounded-full border border-white/[0.07] bg-black/40 p-1">
      {(['baseline', 'alternative'] as WorldSide[]).map((side) => (
        <button
          key={side}
          onClick={() => onChange(side)}
          aria-pressed={value === side}
          className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-widest transition-colors ${
            value === side ? ON[side] : OFF
          }`}
        >
          {WORLD_LABEL[side]}
        </button>
      ))}
    </div>
  );
}
