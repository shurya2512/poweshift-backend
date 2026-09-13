"use client";

import { useState } from "react";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { motion, useScroll, useSpring, useTransform, useMotionValueEvent } from "framer-motion";

export default function F1ScrollTracker() {
  const pathname = usePathname();
  const [percent, setPercent] = useState(0);
  const { scrollYProgress } = useScroll();
  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 100,
    damping: 30,
    restDelta: 0.001
  });

  useMotionValueEvent(smoothProgress, "change", (latest) => {
    setPercent(Math.round(latest * 100));
  });

  // Framer Motion cannot interpolate between different units like "0vw" and "calc()".
  // We use a function to generate the exact transform string on every frame based on the 0-1 progress.
  const x = useTransform(smoothProgress, (val) => {
    const p = val * 100;
    return `calc(${p}vw - ${p}%)`;
  });
  // Car indicator width (`w-36` below) — kept in sync so the trail lines up with its center.
  const CAR_WIDTH_REM = 9;
  // The trail's width must land on the car's visual center, not its left edge: it uses the
  // same left-edge formula as `x` above, plus half the car's own width.
  const width = useTransform(smoothProgress, (val) => {
    const p = val * 100;
    return `calc(${p}vw - ${(p * CAR_WIDTH_REM) / 100}rem + ${CAR_WIDTH_REM / 2}rem)`;
  });

  /** Scroll the page to the fraction of the bar under the pointer. */
  const scrollToPointer = (clientX: number) => {
    const fraction = Math.min(Math.max(clientX / window.innerWidth, 0), 1);
    const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
    window.scrollTo({ top: fraction * maxScroll, behavior: "instant" });
  };

  // The report is a read-only document; the car scrubber stays off it.
  if (pathname === "/report") return null;

  return (
    <div
      className="group fixed bottom-0 left-0 w-full h-10 z-[9999] overflow-visible bg-neutral-950/50 backdrop-blur-md border-t border-white/[0.05] cursor-pointer select-none touch-none"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        scrollToPointer(e.clientX);
      }}
      onPointerMove={(e) => {
        // Only scrub while the pointer is held down (captured).
        if (e.currentTarget.hasPointerCapture(e.pointerId)) scrollToPointer(e.clientX);
      }}
    >

      {/* Laser Progress Trail */}
      <motion.div
        className="absolute left-0 top-1/2 -translate-y-1/2 h-[3px] group-hover:h-[5px] transition-[height] bg-gradient-to-r from-blue-500 to-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]"
        style={{ width }}
      >
        {/* Glowing Leading Dot */}
        <div className="absolute right-0 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-white shadow-[0_0_12px_4px_rgba(255,255,255,0.8)]"></div>
      </motion.div>
      
      {/* Car Indicator */}
      <motion.div 
        className="absolute w-36 h-[34px] top-1/2 -mt-[17px]"
        style={{ x }}
      >
        {/* Percentage on the left of the car */}
        <div className="absolute top-1/2 -translate-y-1/2 right-full mr-3 text-white font-medium text-[10px] bg-black/80 px-2 py-0.5 rounded shadow-[0_0_8px_rgba(59,130,246,0.6)] border border-blue-500 backdrop-blur-sm whitespace-nowrap">
          {percent}%
        </div>

        <Image 
          src="/haas_car2.png"
          alt="Haas F1 Car Scroll Indicator"
          fill
          className="object-contain drop-shadow-[4px_4px_4px_rgba(0,0,0,0.8)]"
          priority
        />
      </motion.div>
    </div>
  );
}
