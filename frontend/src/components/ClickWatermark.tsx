"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { motion } from "framer-motion";

type Mark = { id: number; x: number; y: number };

const SIZE = 96;
export const INTERACTIVE ="a, button, input, select, textarea, label, [role='button']";

/**
 * Stamps a faint Haas logo wherever the background is clicked, then fades it out.
 * Sits above the grid (z-5) but below page content (z-10), so it only shows
 * through empty background areas.
 */
export default function ClickWatermark() {
  const [marks, setMarks] = useState<Mark[]>([]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if ((e.target as Element).closest(INTERACTIVE)) return;
      setMarks((prev) => [...prev, { id: e.timeStamp, x: e.clientX, y: e.clientY }]);
    };
    window.addEventListener("click", handleClick);
    return () => window.removeEventListener("click", handleClick);
  }, []);

  const remove = (id: number) => setMarks((prev) => prev.filter((m) => m.id !== id));

  return (
    <div className="fixed inset-0 z-[5] pointer-events-none">
      {marks.map((m) => (
        <motion.div
          key={m.id}
          className="absolute"
          style={{ left: m.x - SIZE / 2, top: m.y - SIZE / 2, width: SIZE, height: SIZE }}
          initial={{ opacity: 0.6, scale: 0.8 }}
          animate={{ opacity: 0, scale: 1.1 }}
          transition={{ duration: 2.5, ease: "easeOut" }}
          onAnimationComplete={() => remove(m.id)}
        >
          <Image src="/haas_logo.png" alt="" fill sizes={`${SIZE}px`} className="grayscale brightness-200" />
        </motion.div>
      ))}
    </div>
  );
}
