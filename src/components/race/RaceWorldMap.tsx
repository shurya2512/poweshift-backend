import React, { useMemo } from 'react';
import { Participant, ParticipantState, RaceWorld, TrackGeometry } from '@/lib/race/types';

interface RaceWorldMapProps {
  track: TrackGeometry;
  world: RaceWorld;
  participants: Participant[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** Point on the outline at a fraction of the way round, by point index. */
function pointAt(track: TrackGeometry, frac: number) {
  const i = Math.round(((frac % 1) + 1) % 1 * (track.x.length - 1));
  return { x: track.x[i], y: track.y[i] };
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export function RaceWorldMap({ track, world, participants, selectedId, onSelect }: RaceWorldMapProps) {
  const lookup = useMemo(() => new Map(participants.map((p) => [p.id, p])), [participants]);

  // The outline never changes, so it is built once per circuit.
  const view = useMemo(() => {
    const pad = 260;
    const minX = Math.min(...track.x) - pad;
    const maxX = Math.max(...track.x) + pad;
    const minY = Math.min(...track.y) - pad;
    const maxY = Math.max(...track.y) + pad;
    const path = `M ${track.x.map((x, i) => `${x},${track.y[i]}`).join(' L ')} Z`;
    const cx = track.x.reduce((a, b) => a + b, 0) / track.x.length;
    const cy = track.y.reduce((a, b) => a + b, 0) / track.y.length;

    // Pit lane: a chord across the start/finish, pulled in towards the middle.
    const a = pointAt(track, 0.94);
    const b = pointAt(track, 0.06);
    const pull = 0.16;
    const pit = {
      x1: lerp(a.x, cx, pull),
      y1: lerp(a.y, cy, pull),
      x2: lerp(b.x, cx, pull),
      y2: lerp(b.y, cy, pull),
    };

    return {
      box: `${minX} ${minY} ${maxX - minX} ${maxY - minY}`,
      scale: Math.max(maxX - minX, maxY - minY),
      path,
      pit,
      start: pointAt(track, 0),
    };
  }, [track]);

  // Cars in the pit lane are drawn on the pit lane, not at a position on the racing
  // line. Retired entries leave the map; the field order keeps their classification.
  const onTrack = world.field.filter((p) => p.participation === 'running' || p.participation === 'finished');
  const inPit = world.field.filter((p) => p.participation === 'in_pit');

  const r = view.scale * 0.011;

  const marker = (state: ParticipantState, x: number, y: number) => {
    const participant = lookup.get(state.participantId);
    if (!participant) return null;
    const selected = state.participantId === selectedId;
    return (
      <g
        key={state.participantId}
        onClick={() => onSelect(state.participantId)}
        className="cursor-pointer"
      >
        {selected && (
          <circle cx={x} cy={y} r={r * 2.4} fill="none" stroke="#fff" strokeWidth={r * 0.35} opacity={0.9} />
        )}
        <circle
          cx={x}
          cy={y}
          r={selected ? r * 1.35 : r}
          fill={participant.teamColor}
          stroke="rgba(0,0,0,0.55)"
          strokeWidth={r * 0.25}
        />
        <text
          x={x}
          y={y - r * 2.2}
          textAnchor="middle"
          fill={selected ? '#fff' : 'rgba(255,255,255,0.45)'}
          style={{ fontSize: r * 2.1, fontWeight: 700 }}
        >
          {participant.code}
        </text>
      </g>
    );
  };

  return (
    <div className="relative w-full">
      <svg viewBox={view.box} className="h-full w-full" preserveAspectRatio="xMidYMid meet">
        <path d={view.path} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={r * 3.4} strokeLinejoin="round" />
        <path d={view.path} fill="none" stroke="rgba(255,255,255,0.32)" strokeWidth={r * 0.5} strokeLinejoin="round" />

        {/* Start/finish */}
        <circle cx={view.start.x} cy={view.start.y} r={r * 0.6} fill="rgba(255,255,255,0.7)" />

        {/* Pit lane */}
        <line
          x1={view.pit.x1}
          y1={view.pit.y1}
          x2={view.pit.x2}
          y2={view.pit.y2}
          stroke="rgba(255,255,255,0.16)"
          strokeWidth={r * 1.6}
          strokeLinecap="round"
          strokeDasharray={`${r} ${r}`}
        />

        {onTrack.map((state) => marker(state, state.x, state.y))}

        {inPit.map((state, i) => {
          const t = (i + 1) / (inPit.length + 1);
          return marker(state, lerp(view.pit.x1, view.pit.x2, t), lerp(view.pit.y1, view.pit.y2, t));
        })}
      </svg>

      {inPit.length > 0 && (
        <p className="absolute bottom-1 left-2 text-[9px] uppercase tracking-widest text-white/30">
          {inPit.length} in pit lane
        </p>
      )}
    </div>
  );
}
