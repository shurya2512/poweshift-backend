import React from 'react';
import { Pause, Play, SkipForward } from 'lucide-react';
import { RaceEvent, RaceFrame, SessionInfo } from '@/lib/race/types';
import { PlaybackStatus } from '@/lib/race/useRaceSession';
import { Eyebrow, Panel, formatClock } from './primitives';

const RATES = [5, 10, 20, 50];

interface PlaybackBarProps {
  session: SessionInfo;
  frame: RaceFrame | null;
  events: RaceEvent[];
  status: PlaybackStatus;
  rate: number;
  onPause: () => void;
  onResume: () => void;
  onSeek: (t: number) => void;
  onRate: (rate: number) => void;
}

export function PlaybackBar({
  session,
  frame,
  events,
  status,
  rate,
  onPause,
  onResume,
  onSeek,
  onRate,
}: PlaybackBarProps) {
  const t = frame?.raceTimeS ?? 0;
  const playing = status === 'streaming';
  const nextEvent = events.find((e) => e.raceTimeS > t + 0.5);
  const branchPct = (session.branchPoint.raceTimeS / session.durationS) * 100;

  return (
    <Panel className="flex flex-col gap-4 p-5 px-6 lg:flex-row lg:items-center lg:gap-6">
      <button
        onClick={playing ? onPause : onResume}
        disabled={status === 'complete'}
        className="flex shrink-0 items-center gap-2 rounded-xl bg-white px-6 py-3 text-sm font-bold text-black transition-all hover:bg-neutral-200 active:scale-95 disabled:opacity-40"
      >
        {playing ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}
        {playing ? 'PAUSE' : status === 'complete' ? 'FINISHED' : 'PLAY'}
      </button>

      <div className="flex flex-1 items-center gap-4">
        <span className="w-16 shrink-0 text-right text-xs font-semibold tabular-nums text-white/60">
          {formatClock(t)}
        </span>

        <div className="relative flex-1">
          {/* The branch point is where the two worlds separate. */}
          <div
            className="pointer-events-none absolute -top-1.5 z-10 h-4 w-0.5 bg-amber-300/70"
            style={{ left: `${branchPct}%` }}
            title={`Branch — lap ${session.branchPoint.lap}`}
          />
          <input
            type="range"
            min={0}
            max={session.durationS}
            step={1}
            value={t}
            onChange={(e) => onSeek(Number(e.target.value))}
            className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-white"
          />
        </div>

        <span className="w-16 shrink-0 text-xs font-semibold tabular-nums text-white/40">
          {formatClock(session.durationS)}
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-4">
        <div className="hidden min-w-[150px] flex-col lg:flex">
          <Eyebrow>Next event</Eyebrow>
          <span className="mt-0.5 flex items-center gap-1.5 truncate text-[11px] font-medium text-white/60">
            {nextEvent ? (
              <>
                <SkipForward size={11} className="shrink-0 text-white/30" />
                {nextEvent.label}
              </>
            ) : (
              <span className="text-white/25">none remaining</span>
            )}
          </span>
        </div>

        <select
          value={rate}
          onChange={(e) => onRate(Number(e.target.value))}
          className="cursor-pointer rounded-xl border border-white/[0.08] bg-white/[0.05] px-3 py-3 text-sm font-medium text-white focus:outline-none"
        >
          {RATES.map((r) => (
            <option key={r} value={r} className="bg-neutral-900">
              {r}× race time
            </option>
          ))}
        </select>
      </div>
    </Panel>
  );
}
