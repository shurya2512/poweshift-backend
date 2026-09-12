'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import SetupPanel from '@/components/ui/setup-panel';
import { SpinningBorderButton } from '@/components/ui/spinning-border-button';

export default function SetupPage() {
  const router = useRouter();

  const handleStart = (track: string, driver: string, policy: string) => {
    const params = new URLSearchParams({ track, driver, policy, year: '2026' });
    router.push(`/race?${params.toString()}`);
  };

  return (
    <div className="flex-1 w-full min-h-screen text-white font-sans relative overflow-hidden">
      {/* Ambient glows */}
      <div className="absolute top-[-10%] left-[-5%] w-[55%] h-[60%] bg-blue-600/12 blur-[180px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-15%] right-[-5%] w-[50%] h-[60%] bg-red-700/8 blur-[180px] rounded-full pointer-events-none" />
      <div className="absolute top-[35%] left-[35%] w-[35%] h-[45%] bg-blue-500/5 blur-[140px] rounded-full pointer-events-none" />

      {/* Page content */}
      <div className="max-w-7xl mx-auto px-6 lg:px-10 pt-14 pb-10 lg:pt-20 lg:pb-14">
        {/* Top Header Row */}
        <div className="relative flex items-center justify-center mb-6 w-full">
          {/* Back Button */}
          <div className="absolute left-0 top-1/2 -translate-y-1/2">
            <SpinningBorderButton href="/" text="Return to Home" size="sm" />
          </div>

          {/* Page title */}
          <div className="text-center">
            <p className="text-[10px] font-medium tracking-widest text-blue-400 uppercase mb-3">
              2026 F1 Regulations Prototype
            </p>
            <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-white uppercase drop-shadow-xl">
              Power<span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-red-500">-Shift</span>
            </h1>
          </div>
        </div>

        <SetupPanel onStart={handleStart} />
      </div>
    </div>
  );
}
