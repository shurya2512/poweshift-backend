import React from 'react';
import { EventGroup, RaceEvent, SessionInfo, WorldSide } from '@/lib/race/types';
import { Eyebrow, Panel, formatClock } from './primitives';

const GROUP_COLOR: Record<EventGroup, string> = {
  session_control: 'bg-amber-400',
  strategy: 'bg-sky-400',
  competition: 'bg-violet-400',
  environment: 'bg-teal-400',
  outcome: 'bg-rose-400',
  model: 'bg-white/60',
};

interface RaceTimelineProps {
  session: SessionInfo;
  events: RaceEvent[];
  currentTimeS: number;
  selectedEventId: string | null;
  onSeek: (t: number) => void;
  onSelectEvent: (event: RaceEvent) => void;
}

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
        {events.map((e) => {
          const pct = (e.raceTimeS / durationS) * 100;
          const selected = e.id === selectedEventId;
          return (
            <button
              key={e.id}
              onClick={(ev) => {
                ev.stopPropagation();
                onSelectEvent(e);
              }}
              title={`${e.label} — lap ${e.lap}, ${formatClock(e.raceTimeS)}`}
              style={{ left: `${pct}%` }}
              className={`absolute top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 rounded-full transition-transform hover:scale-150 ${
                GROUP_COLOR[e.group]
              } ${selected ? 'h-3.5 w-3.5 ring-2 ring-white' : 'h-2.5 w-2.5'}`}
            />
          );
        })}
      </div>
    </div>
  );
}

/**
 * One timeline across both worlds. The period before the branch is shared history,
 * drawn once. After it, each world keeps its own lane — a pit stop, flag or safety car
 * that happened in only one world has no counterpart in the other, and none is invented.
 */
export function RaceTimeline({
  session,
  events,
  currentTimeS,
  selectedEventId,
  onSeek,
  onSelectEvent,
}: RaceTimelineProps) {
  const { durationS, branchPoint } = session;
  const branchPct = (branchPoint.raceTimeS / durationS) * 100;
  const nowPct = (currentTimeS / durationS) * 100;

  const selectedEvent = events.find((e) => e.id === selectedEventId) ?? null;
  const guidePct = selectedEvent ? (selectedEvent.raceTimeS / durationS) * 100 : null;

  const forWorld = (side: WorldSide) => events.filter((e) => e.world === side);
  const shared = events.filter((e) => e.world === 'shared');

  const seekFromClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    onSeek(((e.clientX - rect.left) / rect.width) * durationS);
  };

  return (
    <Panel className="p-5 px-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Eyebrow>Full-race timeline</Eyebrow>
        <div className="flex flex-wrap items-center gap-3">
          {(Object.keys(GROUP_COLOR) as EventGroup[]).map((g) => (
            <span key={g} className="flex items-center gap-1.5 text-[9px] uppercase tracking-widest text-white/30">
              <span className={`h-2 w-2 rounded-full ${GROUP_COLOR[g]}`} />
              {g.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      </div>

      <div className="relative cursor-pointer space-y-1.5" onClick={seekFromClick}>
        {/* Branch point — where the two worlds separate. */}
        <div
          className="pointer-events-none absolute inset-y-0 z-20 w-px bg-amber-300/80"
          style={{ left: `calc(6rem + 0.75rem + (100% - 6rem - 0.75rem) * ${branchPct / 100})` }}
        />
        {/* Playhead — both worlds sit at this same elapsed race time. */}
        <div
          className="pointer-events-none absolute inset-y-0 z-20 w-px bg-white"
          style={{ left: `calc(6rem + 0.75rem + (100% - 6rem - 0.75rem) * ${nowPct / 100})` }}
        />
        {guidePct !== null && (
          <div
            className="pointer-events-none absolute inset-y-0 z-20 w-px border-l border-dashed border-white/40"
            style={{ left: `calc(6rem + 0.75rem + (100% - 6rem - 0.75rem) * ${guidePct / 100})` }}
          />
        )}

        <Lane
          label="Shared"
          accent="text-white/45"
          events={shared}
          durationS={durationS}
          selectedEventId={selectedEventId}
          onSelectEvent={onSelectEvent}
          band={{ fromPct: 0, toPct: branchPct }}
        />
        <Lane
          label="Baseline"
          accent="text-sky-400"
          events={forWorld('baseline')}
          durationS={durationS}
          selectedEventId={selectedEventId}
          onSelectEvent={onSelectEvent}
        />
        <Lane
          label="Alternative"
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
              ? ' — shared by both worlds'
              : ` — ${selectedEvent.world} world only. The dashed guide marks the same race time in the other world; there is no matching event there.`}
          </p>
        )}
      </div>
    </Panel>
  );
}
