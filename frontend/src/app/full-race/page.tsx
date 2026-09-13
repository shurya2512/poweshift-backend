import React, { Suspense } from 'react';
import { FullRaceView } from './FullRaceView';

export default function FullRacePage() {
  return (
    <div className="relative min-h-screen w-full flex-1 font-sans text-white">
      <div className="pointer-events-none fixed left-[-5%] top-[-10%] z-0 h-[60%] w-[55%] rounded-full bg-blue-600/12 blur-[180px]" />
      <div className="pointer-events-none fixed bottom-[-15%] right-[-5%] z-0 h-[60%] w-[50%] rounded-full bg-emerald-700/8 blur-[180px]" />
      <div className="relative z-10">
        <Suspense fallback={<div className="p-10 text-white/50">Loading race selection…</div>}>
          <FullRaceView />
        </Suspense>
      </div>
    </div>
  );
}
