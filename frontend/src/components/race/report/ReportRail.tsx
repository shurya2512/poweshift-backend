'use client';

import React, { useMemo, useState, useSyncExternalStore } from 'react';

/** How far down the viewport a section's top must be to count as the one being read. */
const READING_LINE = 0.35;

/** The report's sections, each stamped with `data-title` and `data-standfirst` by `Section`. */
const sections = () => [...document.querySelectorAll<HTMLElement>('section[data-title]')];

/** Re-read the page whenever it scrolls or resizes. */
function subscribe(onChange: () => void) {
  window.addEventListener('scroll', onChange, { passive: true });
  window.addEventListener('resize', onChange);
  return () => {
    window.removeEventListener('scroll', onChange);
    window.removeEventListener('resize', onChange);
  };
}

/** Title and standfirst of every section, as JSON so the snapshot compares by value. */
const outline = () => JSON.stringify(sections().map((el) => [el.dataset.title, el.dataset.standfirst ?? '']));

/** The last section whose top has crossed the reading line — or the last one, at the page bottom. */
function reading() {
  const { innerHeight, scrollY } = window;
  if (innerHeight + scrollY >= document.documentElement.scrollHeight - 2) return sections().length - 1;
  return sections().findLastIndex((el) => el.getBoundingClientRect().top <= innerHeight * READING_LINE);
}

/** Line lengths in px by distance from the hovered line: it grows most, its neighbours less. */
const GROWTH = [44, 30, 20];

/** Line length in px: the section being read reads longer; lines near the pointer grow. */
function lineWidth(i: number, active: number, hovered: number | null) {
  const rest = i === active ? 20 : 12;
  if (hovered === null) return rest;
  return Math.max(rest, GROWTH[Math.abs(i - hovered)] ?? 0);
}

/**
 * One short line per report section, packed tight down the right edge; the section
 * being read is lit. Hovering a line shows that section's heading beside it, and
 * clicking it scrolls to the section.
 */
export function ReportRail() {
  const json = useSyncExternalStore(subscribe, outline, () => '[]');
  const active = useSyncExternalStore(subscribe, reading, () => -1);
  const entries = useMemo(() => JSON.parse(json) as [string, string][], [json]);
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <nav
      aria-label="Report sections"
      onPointerLeave={() => setHovered(null)}
      className="fixed right-3 top-1/2 z-50 hidden -translate-y-1/2 flex-col md:flex"
    >
      {/* Rows touch, so the pointer never falls between two lines and drops the card. */}
      {entries.map(([title, standfirst], i) => (
        <button
          key={title}
          type="button"
          aria-label={title}
          aria-current={i === active ? 'location' : undefined}
          onPointerEnter={() => setHovered(i)}
          onClick={() => sections()[i].scrollIntoView({ behavior: 'smooth', block: 'start' })}
          className="relative flex h-2.5 w-14 items-center justify-end"
        >
          <span
            className={`h-[2px] rounded-full transition-[width,background-color] duration-200 ${
              i === active || i === hovered ? 'bg-white' : 'bg-white/30'
            }`}
            style={{ width: lineWidth(i, active, hovered) }}
          />
          {i === hovered && (
            <span className="pointer-events-none absolute right-full top-1/2 mr-4 w-72 -translate-y-1/2 rounded-xl border border-white/10 bg-neutral-900/95 px-4 py-3 text-left shadow-xl backdrop-blur-md">
              <span className="block truncate text-[15px] font-semibold text-white">{title}</span>
              {standfirst && (
                <span className="mt-1 line-clamp-3 text-[14px] leading-snug text-white/45">{standfirst}</span>
              )}
            </span>
          )}
        </button>
      ))}
    </nav>
  );
}
