import React, { Suspense } from 'react';
import { DashboardWrapper } from './DashboardWrapper';

export default function RacePage() {
  return (
    <div className="flex-1 w-full min-h-screen text-white font-sans relative overflow-hidden">
      {/* Ambient glows */}
      <div className="fixed top-[-10%] left-[-5%] w-[55%] h-[60%] bg-blue-600/12 blur-[180px] rounded-full pointer-events-none z-0" />
      <div className="fixed bottom-[-15%] right-[-5%] w-[50%] h-[60%] bg-red-700/8 blur-[180px] rounded-full pointer-events-none z-0" />
      
      <Suspense fallback={<div className="flex-1 w-full min-h-screen flex items-center justify-center text-white font-mono z-10 relative">Loading Race...</div>}>
        <DashboardWrapper />
      </Suspense>
    </div>
  );
}
