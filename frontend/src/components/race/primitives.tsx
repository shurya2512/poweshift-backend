import React from 'react';

export const Eyebrow = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <p className={`text-[10px] font-medium uppercase tracking-widest text-white/35 ${className}`}>{children}</p>
);

export const Panel = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <div
    className={`bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl shadow-[0_12px_40px_rgba(0,0,0,0.5)] ${className}`}
  >
    {children}
  </div>
);

export const formatGap = (v: number): string => (v <= 0 ? 'leader' : `+${v.toFixed(2)}s`);

export const formatClock = (s: number): string => {
  const m = Math.floor(s / 60);
  const rest = s % 60;
  return `${m}:${rest.toFixed(1).padStart(4, '0')}`;
};
