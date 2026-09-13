import React from 'react';
import { Valued } from '@/lib/race/valued';

/**
 * A compound drawn as the tyre itself, seen from the side: rubber, the coloured
 * sidewall band that names the compound, and the rim inside it.
 *
 * Compound names are supplied text, so an unfamiliar one keeps a neutral band rather
 * than being dropped. No compound at all draws a dashed band — the tyre never guesses
 * which rubber is on the car. The full name and any caption ride on the title, so
 * nothing the picture cannot say is lost.
 */
const COMPOUND: Record<string, string> = {
  SOFT: '#EF4444',
  MEDIUM: '#FACC15',
  HARD: '#E8E8E8',
  INTERMEDIATE: '#22C55E',
  WET: '#3B82F6',
};

const SIZE = { sm: 18, md: 26, lg: 34, xl: 52 } as const;

export type TyreMarkerSize = keyof typeof SIZE;

/** Five spokes, drawn from the hub to the rim. Omitted where they would be mush. */
const SPOKES = [0, 72, 144, 216, 288];

interface TyreMarkerProps {
  /** Absent means no compound was supplied, not that the car is on nothing. */
  compound?: string;
  size?: TyreMarkerSize;
  title?: string;
}

export function TyreMarker({ compound, size = 'md', title }: TyreMarkerProps) {
  const px = SIZE[size];
  const known = compound ? COMPOUND[compound.trim().toUpperCase()] : undefined;
  const band = known ?? (compound ? 'rgba(255,255,255,0.45)' : 'rgba(255,255,255,0.22)');
  const detailed = px >= SIZE.md;

  return (
    <svg
      viewBox="0 0 48 48"
      width={px}
      height={px}
      role="img"
      aria-label={compound ? `${compound} tyre` : 'Compound unavailable'}
      className="shrink-0"
    >
      <title>{title ?? compound ?? 'No compound supplied'}</title>

      {/* Rubber, with the tread shoulder a shade lighter than the carcass. */}
      <circle cx={24} cy={24} r={22.5} fill="#0b0b0b" />
      <circle cx={24} cy={24} r={20} fill="none" stroke="#1e1e1e" strokeWidth={4} />

      {/* The compound band — the only part that carries colour. */}
      <circle
        cx={24}
        cy={24}
        r={16.2}
        fill="none"
        stroke={band}
        strokeWidth={detailed ? 3 : 4}
        strokeDasharray={compound ? undefined : '4 3.5'}
      />

      {/* Sidewall and rim. */}
      <circle cx={24} cy={24} r={13.2} fill="#101010" />
      {detailed && (
        <>
          <circle cx={24} cy={24} r={10.6} fill="#191919" stroke="#3a3a3a" strokeWidth={1.2} />
          {SPOKES.map((deg) => (
            <line
              key={deg}
              x1={24}
              y1={24}
              x2={24 + 9.4 * Math.cos((deg * Math.PI) / 180)}
              y2={24 + 9.4 * Math.sin((deg * Math.PI) / 180)}
              stroke="#2f2f2f"
              strokeWidth={2.2}
              strokeLinecap="round"
            />
          ))}
          <circle cx={24} cy={24} r={3.4} fill="#2b2b2b" stroke="#454545" strokeWidth={1} />
        </>
      )}
      {!detailed && <circle cx={24} cy={24} r={6} fill="#242424" />}
    </svg>
  );
}

/** The same tyre for a supplied value, so an unsupported compound reads as absent. */
export function TyreValue({ value, size }: { value: Valued<string>; size?: TyreMarkerSize }) {
  return value.status === 'unsupported' ? (
    <TyreMarker size={size} title={value.reason} />
  ) : (
    <TyreMarker compound={value.value} size={size} />
  );
}
