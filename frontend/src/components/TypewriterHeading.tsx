'use client';

import React, { useEffect, useRef, useState } from 'react';

export function TypewriterHeading({ text, className }: { text: string; className?: string }) {
  const ref = useRef<HTMLHeadingElement>(null);
  const [displayed, setDisplayed] = useState('');
  const [started, setStarted] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setStarted(true);
          observer.disconnect();
        }
      },
      { threshold: 0.6 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!started) return;

    let i = 0;
    const interval = setInterval(() => {
      i += 1;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) clearInterval(interval);
    }, 55);

    return () => clearInterval(interval);
  }, [started, text]);

  const done = displayed.length >= text.length;

  return (
    <h2 ref={ref} className={className}>
      {displayed}
      <span
        aria-hidden="true"
        className={`inline-block w-[2px] h-[0.85em] -mb-[0.1em] ml-1 bg-current align-middle ${done ? 'opacity-0' : 'animate-pulse'}`}
      />
    </h2>
  );
}
