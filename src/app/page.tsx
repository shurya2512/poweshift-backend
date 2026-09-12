import React from 'react';
import FeaturesGrid from "@/components/FeaturesGrid";
import { SpinningBorderButton } from "@/components/ui/spinning-border-button";

export const metadata = {
  title: "Power-Shift | Energy Deployment Intelligence",
  description: "A machine learning model trained to optimally deploy 350kW of electrical power under the strict 2026 Formula 1 regulations.",
};

export default function LandingPage() {
  return (
    <main className="flex-1 w-full bg-transparent text-white font-sans">
      <div className="flex flex-col items-center justify-center text-center px-6 pt-40 pb-20 max-w-5xl mx-auto space-y-8 min-h-screen pointer-events-none">
        
        <div className="flex items-center gap-4 mb-2 justify-center">
          <div className="h-[2px] w-12 bg-blue-500" aria-hidden="true" />
          <span className="font-mono text-xs tracking-[0.5em] text-blue-500 uppercase">
            2026 F1 REGULATIONS PROTOTYPE
          </span>
          <div className="h-[2px] w-12 bg-blue-500" aria-hidden="true" />
        </div>

        <div className="space-y-4">
          <h1 className="text-6xl md:text-8xl lg:text-[120px] font-bold tracking-tighter uppercase leading-[0.85] select-none drop-shadow-sm text-white">
            POWER<span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-red-500">-SHIFT</span>
          </h1>
          <p className="text-lg md:text-xl text-neutral-400 font-medium leading-relaxed max-w-3xl mx-auto">
            Energy Deployment Intelligence. A machine learning model trained to optimally deploy 350kW of electrical power under the strict 2026 Formula 1 regulations.
          </p>
        </div>
        
        <div className="flex flex-wrap justify-center pointer-events-auto mt-12 mb-16 gap-5">
          <SpinningBorderButton href="/setup" text="Qualifying" />
          <SpinningBorderButton href="/full-race" text="Full race" />
        </div>

        {/* Features Grid */}
        <FeaturesGrid />

      </div>
    </main>
  );
}
