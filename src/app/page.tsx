import React from 'react';
import { SpinningBorderButton } from "@/components/ui/spinning-border-button";
import { ShiftHoverText } from "@/components/ShiftHoverText";
import { TypewriterHeading } from "@/components/TypewriterHeading";
import { PowerShiftSubsections } from "@/components/PowerShiftSubsections";

export const metadata = {
  title: "Power-Shift | Energy Deployment Intelligence",
  description: "A machine learning model trained to optimally deploy 350kW of electrical power under the strict 2026 Formula 1 regulations.",
};

export default function LandingPage() {
  return (
    <main className="flex-1 w-full bg-transparent text-white font-sans">
      <div className="flex flex-col items-center justify-center text-center px-6 max-w-5xl mx-auto min-h-screen pointer-events-none">

        <span className="mb-6 -translate-y-1.5 font-mono text-xs tracking-[0.5em] text-blue-500 uppercase">
          2026 F1 REGULATIONS PROTOTYPE
        </span>

        <h1 className="text-[75px] md:text-[120px] lg:text-[150px] font-bold tracking-tighter uppercase leading-[0.85] select-none drop-shadow-sm text-white">
          POWER<ShiftHoverText italic />
        </h1>

        <div className="flex flex-wrap justify-center pointer-events-auto mt-12 gap-5">
          <SpinningBorderButton href="/setup?mode=full-race" text="Full race" />
          <SpinningBorderButton href="/setup" text="Qualifying" fill="hollow" />
        </div>
      </div>

      {/* What is Power-Shift */}
      <div className="px-6 pb-32 max-w-6xl mx-auto pointer-events-auto">
        <div className="grid grid-cols-1 md:grid-cols-[280px_1px_1fr] gap-8 md:gap-12 text-left mb-12">
          <TypewriterHeading
            text="What is Power-Shift"
            className="text-3xl md:text-4xl font-bold uppercase tracking-tight leading-tight"
          />

          <div className="h-px w-full bg-neutral-800 md:h-full md:w-px" aria-hidden="true" />

          <div className="space-y-4">
            <p className="text-lg md:text-xl text-white font-medium leading-relaxed">
              Energy Deployment Intelligence. A machine learning model trained to optimally deploy 350kW of electrical power under the strict 2026 Formula 1 regulations.
            </p>
            <p className="text-base text-white leading-relaxed">
              Trained on real F1 telemetry and a lap-by-lap physics simulation, the model learns when to deploy energy and when to hold back — balancing battery state, tyre wear, and track position to shave every possible tenth off the lap. Every strategy is validated on circuits it has never seen, racing head-to-head against actual historical team data.
            </p>
          </div>
        </div>

        <PowerShiftSubsections />
      </div>
    </main>
  );
}
