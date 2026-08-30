import React, { Suspense } from 'react';
import { DashboardWrapper } from './DashboardWrapper';

export default function RacePage() {
  return (
    <Suspense fallback={<div className="flex-1 w-full flex items-center justify-center text-white font-mono bg-transparent z-10 relative">Loading Race...</div>}>
      <DashboardWrapper />
    </Suspense>
  );
}
