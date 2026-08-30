'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import SetupPanel from '@/components/ui/setup-panel';

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
      <div className="max-w-7xl mx-auto px-6 lg:px-10 py-10 lg:py-14">
        {/* Back Button */}
        <button 
          onClick={() => router.push('/')} 
          className="flex items-center gap-2 text-white/50 hover:text-white transition-colors text-xs font-semibold tracking-wider uppercase mb-10 group"
        >
          <ArrowLeft size={14} className="group-hover:-translate-x-1 transition-transform" />
          Return to Home
        </button>

        {/* Page title */}
        <div className="mb-10">
          <p className="text-[10px] font-medium tracking-widest text-blue-400 uppercase mb-3">
            2026 F1 Regulations Prototype
          </p>
          <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-white uppercase drop-shadow-xl">
            Power<span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-red-500">-Shift</span>
          </h1>
        </div>

        <SetupPanel onStart={handleStart} />
      </div>
    </div>
  );
}
