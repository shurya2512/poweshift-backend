"use client";

import React, { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { 
  motion, 
  useMotionValue, 
  useMotionTemplate, 
  useAnimationFrame 
} from "framer-motion";

interface InfiniteGridProps {
  children?: React.ReactNode;
}

export const TheInfiniteGrid = ({ children }: InfiniteGridProps) => {
  const containerRef = useRef<HTMLDivElement>(null);

  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const { left, top } = e.currentTarget.getBoundingClientRect();
    mouseX.set(e.clientX - left);
    mouseY.set(e.clientY - top);
  };

  const gridOffsetX = useMotionValue(0);
  const gridOffsetY = useMotionValue(0);

  const speedX = 0.5; 
  const speedY = 0.5;

  useAnimationFrame(() => {
    const currentX = gridOffsetX.get();
    const currentY = gridOffsetY.get();
    gridOffsetX.set((currentX + speedX) % 40);
    gridOffsetY.set((currentY + speedY) % 40);
  });

  const maskImage = useMotionTemplate`radial-gradient(600px circle at ${mouseX}px ${mouseY}px, black, transparent)`;

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      className={cn(
        "relative w-full min-h-screen flex flex-col overflow-x-hidden bg-black"
      )}
    >
      <div className="absolute inset-0 z-0 opacity-[0.05]">
        <GridPattern offsetX={gridOffsetX} offsetY={gridOffsetY} />
      </div>
      <motion.div 
        className="absolute inset-0 z-0 opacity-80"
        style={{ maskImage, WebkitMaskImage: maskImage }}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-blue-500/30 to-red-500/30" />
        <GridPattern offsetX={gridOffsetX} offsetY={gridOffsetY} />
      </motion.div>

      <div className="relative z-10 flex flex-col w-full h-full pointer-events-auto">
        {children}
      </div>
    </div>
  );
};

const GridPattern = ({ offsetX, offsetY, id = "grid" }: { offsetX: import('framer-motion').MotionValue<number>, offsetY: import('framer-motion').MotionValue<number>, id?: string }) => {
  return (
    <svg className="w-full h-full">
      <defs>
        <linearGradient id={`${id}-grad`} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#ef4444" />
        </linearGradient>
        <motion.pattern
          id={`${id}-pattern`}
          width="40"
          height="40"
          patternUnits="userSpaceOnUse"
          x={offsetX}
          y={offsetY}
        >
          <path
            d="M 40 0 L 0 0 0 40"
            fill="none"
            stroke={`url(#${id}-grad)`}
            strokeWidth="1"
            className="opacity-40"
          />
        </motion.pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id}-pattern)`} />
    </svg>
  );
};

/**
 * The page's drifting grid plus its cursor spotlight, toned down for use on a
 * modal backdrop. Absolutely positioned, so the parent must be positioned;
 * siblings that should sit above it need a stacking context of their own.
 *
 * The layer is `pointer-events-none`, so the cursor is tracked on the window
 * and converted to layer-local coordinates.
 */
export const SubtleGridBackground = ({ id = "card-grid" }: { id?: string }) => {
  const ref = useRef<HTMLDivElement>(null);
  const offsetX = useMotionValue(0);
  const offsetY = useMotionValue(0);
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  useAnimationFrame(() => {
    offsetX.set((offsetX.get() + 0.5) % 40);
    offsetY.set((offsetY.get() + 0.5) % 40);
  });

  useEffect(() => {
    // Park the spotlight mid-layer so it is lit before the cursor first moves.
    const rect = ref.current?.getBoundingClientRect();
    if (rect) {
      mouseX.set(rect.width / 2);
      mouseY.set(rect.height / 2);
    }

    const handleMouseMove = (e: MouseEvent) => {
      const bounds = ref.current?.getBoundingClientRect();
      if (!bounds) return;
      mouseX.set(e.clientX - bounds.left);
      mouseY.set(e.clientY - bounds.top);
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [mouseX, mouseY]);

  const maskImage = useMotionTemplate`radial-gradient(600px circle at ${mouseX}px ${mouseY}px, black, transparent)`;

  return (
    <div ref={ref} className="absolute inset-0 z-0 pointer-events-none">
      <div className="absolute inset-0 opacity-[0.13]">
        <GridPattern offsetX={offsetX} offsetY={offsetY} id={id} />
      </div>
      <motion.div
        className="absolute inset-0 opacity-70"
        style={{ maskImage, WebkitMaskImage: maskImage }}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-blue-500/30 to-red-500/30" />
        <GridPattern offsetX={offsetX} offsetY={offsetY} id={`${id}-lit`} />
      </motion.div>
    </div>
  );
};
