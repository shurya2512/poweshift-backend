import React from 'react';
import { Action, Participant } from '@/lib/race/types';

/**
 * A schematic of the lines that were open in one decision window.
 *
 * The backend supplies the options, their costs and which one was taken — it does not
 * supply path geometry, so the corner and the lines are drawn to illustrate those
 * options and are not recorded positions. The caption beneath says so on the page.
 */

const ROAD = 'M 40 300 L 320 300 C 460 300 520 262 548 186 C 568 124 612 92 700 70';

/** One drawn line per kind of option. Assigned by the action's own kind and order. */
const SHAPES = {
  inside: {
    d: 'M 48 274 L 330 274 C 446 274 492 246 514 182 C 532 128 578 100 700 84',
    name: 'Inside line, early apex',
  },
  switchback: {
    d: 'M 48 328 L 330 328 C 472 328 544 292 572 206 C 592 140 624 104 700 56',
    name: 'Wide entry, switchback on exit',
  },
  hold: {
    d: 'M 48 300 L 300 300 C 372 300 414 288 442 262',
    name: 'Hold station behind',
  },
} as const;

/** The defender's cover, drawn tighter than our inside line so both stay readable. */
const COVER = 'M 250 262 L 336 262 C 440 262 480 236 500 176 C 516 126 560 96 700 92';

type ShapeKey = keyof typeof SHAPES;

const shapeFor = (action: Action, attackIndex: number): ShapeKey =>
  action.kind === 'wait' || action.kind === 'pace' ? 'hold' : attackIndex === 0 ? 'inside' : 'switchback';

/** Our options in the order given, each with the line drawn for it. */
export function assignShapes(actions: Action[]): { action: Action; shape: ShapeKey }[] {
  let attacks = 0;
  return actions.map((action) => {
    const isHold = action.kind === 'wait' || action.kind === 'pace';
    const shape = shapeFor(action, attacks);
    if (!isHold) attacks += 1;
    return { action, shape };
  });
}

interface OvertakePathsProps {
  ours: { action: Action; shape: ShapeKey }[];
  chosenActionId?: string;
  attacker?: Participant;
  defender?: Participant;
  /** The defender's expected answer, drawn as the line it covers. */
  responseLabel?: string;
}

export function OvertakePaths({ ours, chosenActionId, attacker, defender, responseLabel }: OvertakePathsProps) {
  const ourColor = attacker?.teamColor ?? '#34d399';
  const theirColor = defender?.teamColor ?? '#94a3b8';

  return (
    <svg viewBox="0 0 760 380" className="h-auto w-full" role="img" aria-label="Schematic of the lines open into the corner">
      {/* Track surface: one stroke for the edges, a darker one over it for the road. */}
      <path d={ROAD} fill="none" stroke="rgba(255,255,255,0.13)" strokeWidth={96} strokeLinecap="round" />
      <path d={ROAD} fill="none" stroke="#080808" strokeWidth={88} strokeLinecap="round" />
      {/* Apex kerb */}
      <path
        d="M 486 214 C 502 198 512 176 516 152"
        fill="none"
        stroke="rgba(239,68,68,0.55)"
        strokeWidth={7}
        strokeDasharray="9 9"
        strokeLinecap="round"
      />

      {/* The defender's expected answer. */}
      <path
        d={COVER}
        fill="none"
        stroke={theirColor}
        strokeWidth={3.5}
        strokeOpacity={0.75}
        strokeDasharray="3 8"
        strokeLinecap="round"
      />

      {/* Our options. The chosen one is drawn solid; the rest stay visible but quiet. */}
      {ours.map(({ action, shape }) => {
        const chosen = action.id === chosenActionId;
        return (
          <path
            key={action.id}
            d={SHAPES[shape].d}
            fill="none"
            stroke={chosen ? ourColor : 'rgba(255,255,255,0.3)'}
            strokeWidth={chosen ? 5 : 2.5}
            strokeDasharray={chosen ? undefined : '10 8'}
            strokeLinecap="round"
            style={chosen ? { filter: `drop-shadow(0 0 10px ${ourColor})` } : undefined}
          />
        );
      })}

      {/* Where the held line stops, so it does not read as a path that was cut off. */}
      {ours.some(({ shape }) => shape === 'hold') && (
        <circle cx={442} cy={262} r={4} fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth={2} />
      )}

      {/* Cars at the start of the window: ours behind, the defender ahead. */}
      <g>
        <circle cx={250} cy={262} r={9} fill={theirColor} stroke="#000" strokeWidth={2} />
        <text x={250} y={240} textAnchor="middle" className="fill-white/70" fontSize={13} fontWeight={700}>
          {defender?.code ?? 'Ahead'}
        </text>
        <circle cx={96} cy={300} r={9} fill={ourColor} stroke="#000" strokeWidth={2} />
        <text x={96} y={278} textAnchor="middle" className="fill-white" fontSize={13} fontWeight={700}>
          {attacker?.code ?? 'Us'}
        </text>
      </g>

      {/* Direction of travel and the corner label. */}
      <text x={120} y={348} className="fill-white/30" fontSize={12} letterSpacing={2}>
        BRAKING ZONE →
      </text>
      <text x={566} y={158} className="fill-white/30" fontSize={12} letterSpacing={2}>
        APEX
      </text>
      {responseLabel && (
        <text x={716} y={318} textAnchor="end" fill={theirColor} fillOpacity={0.8} fontSize={12}>
          {responseLabel}
        </text>
      )}
    </svg>
  );
}

export { SHAPES };
