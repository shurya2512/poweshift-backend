import Link from "next/link";
import React from 'react';
import { ArrowRight } from 'lucide-react';
import FeaturesGrid from "@/components/FeaturesGrid";

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
        
        <div className="flex flex-col items-center pointer-events-auto mt-12 mb-16 gap-5">
          <Link
            href="/setup"
            passHref
            className="
              group relative flex items-center justify-center px-12 py-5
              bg-white text-black
              rounded-full
              font-sans font-bold tracking-wider uppercase
              shadow-xl
              transition-all duration-300 transform hover:scale-[1.05] active:scale-[0.95]
              hover:bg-neutral-200
              overflow-hidden
            "
          >
            <div className="flex items-center gap-3 z-10 relative">
              <span className="text-lg md:text-xl">INITIALIZE SIMULATION</span>
              <ArrowRight size={24} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </Link>

          {/* Full-race comparison — fixture data, no backend attached yet. */}
          <Link
            href="/full-race"
            className="group flex items-center gap-2.5 text-sm font-medium text-white/45 hover:text-white transition-colors"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/70" aria-hidden="true" />
            <span className="tracking-wide uppercase text-xs">Full-race comparison</span>
            <span className="text-[10px] uppercase tracking-widest text-white/25 border border-white/10 rounded-full px-2 py-0.5">
              Preview
            </span>
            <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>

        {/* Features Grid */}
        <FeaturesGrid />

      </div>
    </main>
  );
}
