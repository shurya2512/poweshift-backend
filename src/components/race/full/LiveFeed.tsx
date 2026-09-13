import React from 'react';
import { FlagState, Participant, RaceWorld, TrackGeometry } from '@/lib/race/types';
import { Panel, formatClock } from '../primitives';
import { RaceWorldMap, energyRing } from '../RaceWorldMap';

const FLAG: Record<FlagState, { label: string; className: string }> = {
  green: { label: 'Green', className: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-300' },
  yellow: { label: 'Yellow', className: 'border-amber-400/40 bg-amber-400/10 text-amber-300' },
  virtual_safety_car: { label: 'Virtual safety car', className: 'border-amber-400/50 bg-amber-400/15 text-amber-200' },
  safety_car: { label: 'Safety car', className: 'border-orange-500/50 bg-orange-500/15 text-orange-300' },
  red: { label: 'Red flag', className: 'border-red-500/50 bg-red-500/15 text-red-300' },
  chequered: { label: 'Chequered', className: 'border-white/25 bg-white/10 text-white/80' },
};

const Count = ({ label, value }: { label: string; value: number }) => (
  <span className="flex items-baseline gap-1.5">
    <span className="text-[11px] font-bold tabular-nums text-white/70">{value}</span>
    <span className="text-[9px] uppercase tracking-widest text-white/30">{label}</span>
  </span>
);

/**
 * Where every car is, right now.
 *
 * Cars in the pit lane are drawn on the pit lane and retired entries leave the map, so
 * a position on the racing line always means a car that is on it.
 */
export function LiveFeed({
  world,
  track,
  participants,
  selectedId,
  raceTimeS,
  onSelect,
}: {
  world: RaceWorld;
  track: TrackGeometry;
  participants: Participant[];
  selectedId: string | null;
  raceTimeS: number;
  onSelect: (id: string) => void;
}) {
  const flag = FLAG[world.flag];
  const count = (kind: string) => world.field.filter((p) => p.participation === kind).length;
  // Says in words what the ring around our car is saying in colour.
  const ours = world.field.find((p) => p.participantId === selectedId);
  const energy = ours ? energyRing(ours) : null;

  return (
    <Panel className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-end gap-2 border-b border-white/[0.07] px-5 py-3">
        <span className={`rounded-full border px-2.5 py-0.5 text-[9px] font-bold uppercase tracking-widest ${flag.className}`}>
          {flag.label}
        </span>
        <span className="text-[11px] font-semibold tabular-nums text-white/70">
          Lap {world.leaderLap}/{world.totalLaps}
        </span>
      </div>

      <div className="min-h-[280px] flex-1 px-2 pt-2">
        <RaceWorldMap
          track={track}
          world={world}
          participants={participants}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-white/[0.06] px-5 py-3">
        <div className="flex flex-wrap items-center gap-5">
          <Count label="on track" value={count('running')} />
          <Count label="in pit" value={count('in_pit')} />
          <Count label="finished" value={count('finished')} />
          <Count label="retired" value={count('retired')} />
        </div>
        <div className="flex items-center gap-4">
          {energy && (
            <span className="flex items-center gap-2">
              <span
                aria-hidden
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: energy.color, boxShadow: `0 0 8px ${energy.color}` }}
              />
              <span className="text-[9px] uppercase tracking-widest text-white/45">{energy.label}</span>
            </span>
          )}
          <span className="font-mono text-[10px] uppercase tracking-widest text-white/25">
            {formatClock(raceTimeS)} race time
          </span>
        </div>
      </div>
    </Panel>
  );
}
