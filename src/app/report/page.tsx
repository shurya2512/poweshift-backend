import React from 'react';
import { ReportView } from './ReportView';

export const metadata = {
  title: 'Race report | Power-Shift',
  description: 'The finished race: classification, events, decisions and the assumptions behind them.',
};

export default function ReportPage() {
  return (
    <div className="relative min-h-screen w-full flex-1 font-sans text-white">
      {/* The document sits on plain black — the site's moving grid would read as texture
          behind body copy and compete with the tables. */}
      <div className="pointer-events-none fixed inset-0 z-0 bg-black" />
      <div className="relative z-10">
        <ReportView />
      </div>
    </div>
  );
}
