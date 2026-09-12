import React, { useRef } from 'react';
import { motion } from 'framer-motion';
import { Pause, Play } from 'lucide-react';
import { EventKind, RaceEvent, SessionInfo, WorldSide } from '@/lib/race/types';
import { PlaybackStatus } from '@/lib/race/useRaceSession';
import { Panel, formatClock } from './primitives';

/**
 * The colour assigned to each kind of event. Kinds the timeline is asked to highlight
 * come first; the rest are here so nothing on the timeline is left unexplained.
 *
 * Colours are inline styles rather than utility classes, so a kind can be added here
 * without a matching class having to exist somewhere for the CSS scanner to find.
 */
const KIND: Record<EventKind, { label: string; color: string }> = {
  overtake: { label: 'We overtake', color: '#34d399' },
  overtaken: { label: 'We are passed', color: '#fb7185' },
  pit_stop: { label: 'Pit stop', color: '#38bdf8' },
  virtual_safety_car: { label: 'Virtual safety car', color: '#fbbf24' },
  safety_car: { label: 'Safety car', color: '#f97316' },
  red_flag: { label: 'Red flag', color: '#ef4444' },
  start: { label: 'Start', color: '#e5e5e5' },
  chequered: { label: 'Chequered flag', color: '#e5e5e5' },
  retirement: { label: 'Retirement', color: '#a78bfa' },
};

/** The order the legend reads in — the six the page highlights, then the rest. */
const LEGEND_ORDER: EventKind[] = [
  'overtake',
  'overtaken',
  'pit_stop',
  'virtual_safety_car',
  'safety_car',
  'red_flag',
  'start',
  'chequered',
  'retirement',
];

/** An event the backend did not classify keeps its group and no colour of its own. */
const UNCLASSIFIED = '#94a3b8';

/** Where the lanes start: the label column (w-24) plus the row gap (gap-3). */
const TRACK_INSET = 'calc(6rem + 0.75rem)';

/** One source tick, in seconds. The playhead is interpolated across exactly this. */
const TICK_S = 0.25;

const colorOf = (event: RaceEvent): string => (event.kind ? KIND[event.kind].color : UNCLASSIFIED);

interface LaneProps {
  label: string;
  accent: string;
  events: RaceEvent[];
  durationS: number;
  selectedEventId: string | null;
  onSelectEvent: (event: RaceEvent) => void;
  /** Shared history is drawn once, before the branch. */
  band?: { fromPct: number; toPct: number };
}

function Lane({ label, accent, events, durationS, selectedEventId, onSelectEvent, band }: LaneProps) {
  const pct = (t: number) => (t / durationS) * 100;
  const isPeriod = (e: RaceEvent) => e.periodEndS !== undefined;

  return (
    <div className="flex items-center gap-3">
      <span className={`w-24 shrink-0 text-[10px] font-semibold uppercase tracking-widest ${accent}`}>{label}</span>
      <div className="relative h-7 flex-1 rounded-lg bg-white/[0.03]">
        {band && (
          <div
            className="absolute inset-y-0 rounded-lg border border-white/[0.07] bg-white/[0.05]"
            style={{ left: `${band.fromPct}%`, width: `${band.toPct - band.fromPct}%` }}
          />
        )}

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
    </div>
  );
}

interface RaceTimelineProps {
  session: SessionInfo;
  events: RaceEvent[];
  currentTimeS: number;
  selectedEventId: string | null;
  status: PlaybackStatus;
  onSeek: (t: number) => void;
  onSelectEvent: (event: RaceEvent) => void;
  onPause: () => void;
  onResume: () => void;
}

/**
 * One timeline across both races. The period before the branch is shared history, drawn
 * once. After it, each race keeps its own lane — a pit stop, flag or safety car that
 * happened in only one of them has no counterpart in the other, and none is invented.
 *
 * The legend lists every kind the timeline can mark. A kind with nothing to mark this
 * race stays in the legend, dimmed, rather than quietly disappearing.
 */
export function RaceTimeline({
  session,
  events,
  currentTimeS,
  selectedEventId,
  status,
  onSeek,
  onSelectEvent,
  onPause,
  onResume,
}: RaceTimelineProps) {
  const { durationS, branchPoint } = session;
  const playing = status === 'streaming';
  const finished = status === 'complete';
  const branchPct = (branchPoint.raceTimeS / durationS) * 100;
  const nowPct = (currentTimeS / durationS) * 100;

  const selectedEvent = events.find((e) => e.id === selectedEventId) ?? null;
  const guidePct = selectedEvent ? (selectedEvent.raceTimeS / durationS) * 100 : null;

  const present = new Set(events.map((e) => e.kind).filter(Boolean) as EventKind[]);
  const hasUnclassified = events.some((e) => !e.kind);

  const forWorld = (side: WorldSide) => events.filter((e) => e.world === side);
  const shared = events.filter((e) => e.world === 'shared');

  // Seek off the lane area, not the whole row — the label column is not part of the race.
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
          {LEGEND_ORDER.map((kind) => {
            const seen = present.has(kind);
            return (
              <span
                key={kind}
                title={seen ? undefined : 'Nothing of this kind happened in either race'}
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
          {hasUnclassified && (
            <span className="flex items-center gap-1.5 text-[9px] uppercase tracking-widest text-white/45">
              <span className="h-2 w-2 rounded-full" style={{ background: UNCLASSIFIED }} />
              Unclassified
            </span>
          )}
        </div>
      </div>

      <div className="relative cursor-pointer space-y-1.5" onClick={seekFromClick}>
        {/*
         * The guides live in a layer inset to where the lanes actually start, so they
         * share one coordinate space with the marks — and so a click maps to the same
         * place the playhead is drawn, rather than being offset by the label column.
         */}
        <div
          ref={trackRef}
          className="pointer-events-none absolute inset-y-0 right-0 z-20"
          style={{ left: TRACK_INSET }}
        >
          {/* Branch point — where the two races separate. */}
          <div className="absolute inset-y-0 w-px bg-amber-300/80" style={{ left: `${branchPct}%` }} />

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

        <Lane
          label="Both races"
          accent="text-white/45"
          events={shared}
          durationS={durationS}
          selectedEventId={selectedEventId}
          onSelectEvent={onSelectEvent}
          band={{ fromPct: 0, toPct: branchPct }}
        />
        <Lane
          label="Recorded"
          accent="text-sky-400"
          events={forWorld('baseline')}
          durationS={durationS}
          selectedEventId={selectedEventId}
          onSelectEvent={onSelectEvent}
        />
        <Lane
          label="Our plan"
          accent="text-emerald-400"
          events={forWorld('alternative')}
          durationS={durationS}
          selectedEventId={selectedEventId}
          onSelectEvent={onSelectEvent}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-3">
        <p className="text-[10px] uppercase tracking-widest text-white/30">
          Branch lap {branchPoint.lap} · {formatClock(branchPoint.raceTimeS)} — {branchPoint.description}
        </p>
        {selectedEvent && (
          <p className="text-[10px] text-white/45">
            <span className="font-semibold text-white/70">{selectedEvent.label}</span>
            {selectedEvent.world === 'shared'
              ? ' — shared by both races'
              : ` — ${selectedEvent.world === 'baseline' ? 'recorded race' : 'our plan'} only. The dashed guide marks the same race time in the other race; there is no matching event there.`}
          </p>
        )}
      </div>
    </Panel>
  );
}
