'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { CornerDownRight } from 'lucide-react';

/** Subsections of "What is Power-Shift", each marked with a nested arrow in its accent colour. */
const subsections = [
  {
    title: 'Machine Learning',
    description: 'A HistGradientBoostingClassifier dynamically evaluates the track and telemetry to predict optimal battery deployment.',
    color: 'text-blue-500',
    headingClassName: 'translate-y-px',
  },
  {
    title: 'Real Physics Engine',
    description: 'Every lap is simulated in real-time, accounting for 798kg mass, aero drag, tyre traction limits, and the 4MJ battery cap.',
    color: 'text-orange-400',
  },
  {
    title: 'Adversarial Testing',
    description: 'The AI is tested strictly on held-out circuits it has never seen, racing against the actual historical team telemetry.',
    color: 'text-red-500',
  },
];

const TITLE_SPEED_MS = 55;
const DESCRIPTION_SPEED_MS = 10;

/** Types `text` one character at a time while `active`, then calls `onDone`. Untyped characters stay invisible so the layout never shifts. */
function Typewriter({ text, active, speed, onDone }: { text: string; active: boolean; speed: number; onDone: () => void }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!active) return;
    if (count === text.length) {
      onDone();
      return;
    }
    const timeout = setTimeout(() => setCount(count + 1), speed);
    return () => clearTimeout(timeout);
  }, [active, count, text.length, speed, onDone]);

  return (
    <>
      {text.slice(0, count)}
      {active && (
        // Inline border, not inline-block: an inline-block cursor lets a half-typed word wrap onto the wrong line.
        <span aria-hidden="true" className="border-l-2 border-current -mr-[2px] animate-pulse" />
      )}
      <span className="invisible">{text.slice(count)}</span>
    </>
  );
}

/** Reveals the subsections in order: each heading types out, then its description, then the next subsection. */
export function PowerShiftSubsections() {
  const ref = useRef<HTMLDivElement>(null);
  // Text currently typing: subsection i's heading is step 2i, its description 2i + 1. -1 until scrolled into view.
  const [step, setStep] = useState(-1);
  const advance = useCallback(() => setStep((s) => s + 1), []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setStep(0);
          observer.disconnect();
        }
      },
      { rootMargin: '0px 0px -20% 0px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className="space-y-12">
      {subsections.map(({ title, description, color, headingClassName }, i) => (
        <div
          key={title}
          className={`grid grid-cols-1 md:grid-cols-[280px_1px_1fr] gap-8 md:gap-12 text-left transition-opacity duration-500 ${step >= 2 * i ? 'opacity-100' : 'opacity-0'}`}
        >
          <div className="flex items-start gap-3 md:pl-6">
            <CornerDownRight className={`${color} shrink-0 mt-0.5`} size={24} aria-hidden="true" />
            <h3 className={`text-xl md:text-2xl font-bold uppercase tracking-tight leading-tight ${headingClassName ?? ''}`}>
              <Typewriter text={title} active={step === 2 * i} speed={TITLE_SPEED_MS} onDone={advance} />
            </h3>
          </div>

          <div className="h-px w-full bg-neutral-800 md:h-full md:w-px" aria-hidden="true" />

          <p className="text-base text-white leading-relaxed">
            <Typewriter text={description} active={step === 2 * i + 1} speed={DESCRIPTION_SPEED_MS} onDone={advance} />
          </p>
        </div>
      ))}
    </div>
  );
}
