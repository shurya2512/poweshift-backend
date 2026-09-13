import React, { Suspense } from 'react';
import { ReportView } from './ReportView';

export const metadata = {
  title: 'Diagnostic report | Power-Shift',
  description: 'Source-bound qualifying and P23 race diagnostics, decisions and assumptions.',
};

export default function ReportPage() {
  return (
    <div className="relative min-h-screen w-full flex-1 font-sans text-white">
      {/* The document sits on plain black — the site's moving grid would read as texture
          behind body copy and compete with the tables. */}
      <div className="pointer-events-none fixed inset-0 z-0 bg-black" />
      <div className="relative z-10">
        <Suspense fallback={<div className="p-10 text-white/50">Loading diagnostic report…</div>}>
          <ReportView />
        </Suspense>
      </div>
    </div>
  );
}
