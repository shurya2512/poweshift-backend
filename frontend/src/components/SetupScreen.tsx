'use client';

import React from 'react';
import SetupPanel, { SetupMode } from '@/components/ui/setup-panel';
import { SpinningBorderButton } from '@/components/ui/spinning-border-button';
import { ShiftHoverText } from '@/components/ShiftHoverText';

/**
 * The setup screen both sessions use.
 *
 * Qualifying and the full race are set up the same way and must look the same way, so
 * they share this shell and differ only in `mode` — which changes wording inside the
 * panel — and in where the start button sends the run.
 */
export function SetupScreen({
  mode,
  onStart,
}: {
  mode: SetupMode;
  onStart: (track: string, driver: string, policy: string) => void;
}) {
  return (
    <div className="flex-1 w-full min-h-screen text-white font-sans relative overflow-hidden">
      {/* Ambient glows */}
      <div className="absolute top-[-10%] left-[-5%] w-[55%] h-[60%] bg-blue-600/12 blur-[180px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-15%] right-[-5%] w-[50%] h-[60%] bg-red-700/8 blur-[180px] rounded-full pointer-events-none" />
      <div className="absolute top-[35%] left-[35%] w-[35%] h-[45%] bg-blue-500/5 blur-[140px] rounded-full pointer-events-none" />

      {/* Page content */}
      <div className="max-w-7xl mx-auto px-6 lg:px-10 pt-14 pb-10 lg:pt-20 lg:pb-14">
        {/* Top Header Row */}
        <div className="relative mb-8 flex w-full flex-col items-start gap-8 sm:items-center sm:justify-center">
          {/*
           * Back button. The title's drop-shadow is a filter, which gives the heading
           * its own stacking context — so its full-width box paints over this button
           * and swallows the click. An explicit z-index puts the button back on top,
           * and it stays positioned at every width so that z-index always applies.
           */}
          <div className="relative z-10 sm:absolute sm:left-0 sm:top-1/2 sm:-translate-y-1/2">
            <SpinningBorderButton href="/" text="Return to Home" size="sm" arrowMode="flip" fill="hollow" beam="once" />
          </div>

          {/* Page title */}
          <div className="w-full text-center">
            <p className="text-[10px] font-medium tracking-widest text-blue-400 uppercase mb-3">
              2026 F1 Regulations Prototype
            </p>
            <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-white uppercase drop-shadow-xl">
              Power<ShiftHoverText italic />
            </h1>
          </div>
        </div>

        <SetupPanel mode={mode} onStart={onStart} />
      </div>
    </div>
  );
}
