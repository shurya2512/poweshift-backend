import React, { useRef } from 'react';
import { motion } from 'framer-motion';
import { Pause, Play } from 'lucide-react';
import { EventKind, RaceEvent, SessionInfo, WorldSide } from '@/lib/race/types';
import { PlaybackStatus } from '@/lib/race/useRaceSession';
import { Panel, formatClock } from './primitives';

/** What the timeline marks: our car's own moments, and the flags that neutralise the race. */
type MarkedKind = Extract<
  EventKind,
  'overtake' | 'overtaken' | 'pit_stop' | 'virtual_safety_car' | 'safety_car' | 'red_flag'
>;

/**
 * The colour of each marked kind, in the order the legend reads.
 *
 * Colours are inline styles rather than utility classes, so a kind can be added here
 * without a matching class having to exist somewhere for the CSS scanner to find.
 */
const KIND: Record<MarkedKind, { label: string; color: string }> = {
  overtake: { label: 'We overtake', color: '#34d399' },
  overtaken: { label: 'We are passed', color: '#fb7185' },
  pit_stop: { label: 'Pit stop', color: '#38bdf8' },
  virtual_safety_car: { label: 'Virtual safety car', color: '#fbbf24' },
  safety_car: { label: 'Safety car', color: '#f97316' },
  red_flag: { label: 'Red flag', color: '#ef4444' },
};

const MARKED = Object.keys(KIND) as MarkedKind[];

const isMarked = (e: RaceEvent): boolean => !!e.kind && e.kind in KIND;

/** One source tick, in seconds. The playhead is interpolated across exactly this. */
const TICK_S = 0.25;

const colorOf = (event: RaceEvent): string => KIND[event.kind as MarkedKind].color;

interface LaneProps {
  events: RaceEvent[];
  durationS: number;
  selectedEventId: string | null;
  onSelectEvent: (event: RaceEvent) => void;
}

function Lane({ events, durationS, selectedEventId, onSelectEvent }: LaneProps) {
  const pct = (t: number) => (t / durationS) * 100;
  const isPeriod = (e: RaceEvent) => e.periodEndS !== undefined;

  return (
    <div className="relative h-7 rounded-lg bg-white/[0.03]">
      {/*
       * An event that lasts is drawn across the laps it lasts for, in its own colour,
       * so a safety car reads as a stretch of the race rather than a moment in it.
       * An event that happens at an instant is a line at that instant.
       */}
      {events.map((e) => {
        const selected = e.id === selectedEventId;
        const color = colorOf(e);
        const open = (ev: React.MouseEvent) => {
          ev.stopPropagation();
          onSelectEvent(e);
        };

        if (isPeriod(e)) {
          const end = e.periodEndS as number;
          return (
            <button
              key={e.id}
              onClick={open}
              title={`${e.label} — ${formatClock(e.raceTimeS)} to ${formatClock(end)}`}
              className="absolute inset-y-1 z-10 rounded-[3px] transition-all hover:brightness-150"
              style={{
                left: `${pct(e.raceTimeS)}%`,
                width: `${Math.max(0.6, pct(end - e.raceTimeS))}%`,
                background: `${color}38`,
                borderLeft: `2px solid ${color}`,
                borderRight: `2px solid ${color}`,
                boxShadow: selected ? `0 0 0 1.5px #fff` : undefined,
              }}
            />
          );
        }

        return (
          <button
            key={e.id}
            onClick={open}
            title={`${e.label} — lap ${e.lap}, ${formatClock(e.raceTimeS)}`}
            // A wider transparent hit area than the line it draws, so a 2px mark
            // is still comfortably clickable.
            className="group/mark absolute inset-y-0 z-10 flex w-3 -translate-x-1/2 items-center justify-center"
            style={{ left: `${pct(e.raceTimeS)}%` }}
          >
            <span
              className={`block rounded-full transition-all group-hover/mark:w-[3px] ${
                selected ? 'h-full w-[3px]' : 'h-[70%] w-[2px]'
              }`}
              style={{ background: color, boxShadow: selected ? '0 0 0 1px #fff' : undefined }}
            />
          </button>
        );
      })}
    </div>
  );
}

interface RaceTimelineProps {
  session: SessionInfo;
  events: RaceEvent[];
  /** The race being shown. Shared events belong to it too. */
  side: WorldSide;
  currentTimeS: number;
  selectedEventId: string | null;
  status: PlaybackStatus;
  onSeek: (t: number) => void;
  onSelectEvent: (event: RaceEvent) => void;
  onPause: () => void;
  onResume: () => void;
}

/**
 * One lane for our car: its overtakes, the times it is passed and its pit stops as
 * lines, and the virtual safety car, safety car and red flag as spans. Nothing else
 * is marked.
 *
 * The legend lists every kind the lane can mark. A kind with nothing to mark stays in
 * the legend, dimmed, rather than quietly disappearing.
 */
export function RaceTimeline({
  session,
  events,
  side,
  currentTimeS,
  selectedEventId,
  status,
  onSeek,
  onSelectEvent,
  onPause,
  onResume,
}: RaceTimelineProps) {
  const { durationS } = session;
  const playing = status === 'streaming';
  const finished = status === 'complete';
  const nowPct = (currentTimeS / durationS) * 100;

  const lane = events.filter((e) => (e.world === 'shared' || e.world === side) && isMarked(e));
  const present = new Set(lane.map((e) => e.kind));

  const selectedEvent = lane.find((e) => e.id === selectedEventId) ?? null;
  const guidePct = selectedEvent ? (selectedEvent.raceTimeS / durationS) * 100 : null;

  const trackRef = useRef<HTMLDivElement>(null);
  const seekFromClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    onSeek(frac * durationS);
  };

  return (
    <Panel className="p-5 px-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        {/* The transport lives on the timeline it drives. */}
        <div className="flex items-center gap-4">
          <button
            onClick={playing ? onPause : onResume}
            disabled={finished}
            aria-label={playing ? 'Pause' : 'Play'}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-black transition-all hover:bg-neutral-200 active:scale-95 disabled:opacity-40"
          >
            {playing ? <Pause size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" className="ml-0.5" />}
          </button>
          <p className="font-mono text-sm font-semibold tabular-nums text-white">
            {formatClock(currentTimeS)}
            <span className="text-white/30"> / {formatClock(durationS)}</span>
          </p>
          <span className="hidden text-[10px] uppercase tracking-widest text-white/25 sm:inline">
            {finished ? 'Race over' : 'Click the timeline to seek'}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {MARKED.map((kind) => {
            const seen = present.has(kind);
            return (
              <span
                key={kind}
                title={seen ? undefined : 'Nothing of this kind in this race'}
                className={`flex items-center gap-1.5 text-[9px] uppercase tracking-widest ${
                  seen ? 'text-white/45' : 'text-white/20'
                }`}
              >
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ background: KIND[kind].color, opacity: seen ? 1 : 0.3 }}
                />
                {KIND[kind].label}
              </span>
            );
          })}
        </div>
      </div>

      <div className="relative cursor-pointer" onClick={seekFromClick}>
        {/* The guides share one coordinate space with the marks, so a click maps to the
            same place the playhead is drawn. */}
        <div ref={trackRef} className="pointer-events-none absolute inset-0 z-20">
          {/*
           * Playhead. The source ticks four times a second, so left on its own the head
           * steps rather than runs; it is animated across each tick's own duration,
           * which turns the steps into continuous motion.
           */}
          <motion.div
            className="absolute inset-y-0 w-px bg-white"
            initial={false}
            animate={{ left: `${nowPct}%` }}
            transition={{ duration: TICK_S, ease: 'linear' }}
          />

          {guidePct !== null && (
            <div
              className="absolute inset-y-0 w-px border-l border-dashed border-white/40"
              style={{ left: `${guidePct}%` }}
            />
          )}
        </div>

        <Lane events={lane} durationS={durationS} selectedEventId={selectedEventId} onSelectEvent={onSelectEvent} />
      </div>
    </Panel>
  );
}
