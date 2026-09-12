"use client";

import { useEffect, useRef, useState } from "react";
import { SvgPathDrawingTextAnimation } from "@/components/ui/path-drawing-portfolio-hero";

const TEXT = "-SHIFT";
/** Extra width on each side of the word, so the outline is never clipped. */
const SIDE_PAD = 0.15;

type Box = {
  width: number;
  height: number;
  /** Baseline offset from the top of the word, in px. */
  baseline: number;
  fontSize: number;
  fontFamily: string;
  fontWeight: string;
  letterSpacing: string;
};
/** draw: intro outline → fill: gradient fades in → idle → hover: looping outline. */
type Phase = "draw" | "fill" | "idle" | "hover";

/**
 * The gradient "-SHIFT" of the landing title. On load its outline is drawn once,
 * then the gradient fill fades in. On hover the fill fades out and the outline
 * is path-drawn in a loop until the pointer leaves.
 */
export function ShiftHoverText() {
  const ref = useRef<HTMLSpanElement>(null);
  const probeRef = useRef<HTMLSpanElement>(null);
  const [box, setBox] = useState<Box | null>(null);
  const [phase, setPhase] = useState<Phase>("draw");

  // Measure the word so the outline overlays it exactly (1 viewBox unit = 1px).
  const measure = () => {
    const rect = ref.current!.getBoundingClientRect();
    const style = getComputedStyle(ref.current!);
    setBox({
      width: rect.width,
      height: rect.height,
      // The empty inline-block probe's bottom edge sits on the text baseline.
      baseline: probeRef.current!.getBoundingClientRect().bottom - rect.top,
      fontSize: parseFloat(style.fontSize),
      fontFamily: style.fontFamily,
      fontWeight: style.fontWeight,
      letterSpacing: style.letterSpacing,
    });
  };

  // Measure after web fonts load, which starts the intro draw.
  useEffect(() => {
    document.fonts.ready.then(measure);
  }, []);

  const onEnter = () => {
    if (phase !== "idle") return;
    measure();
    setPhase("hover");
  };

  const filled = phase === "fill" || phase === "idle";
  const outlined = box && phase !== "idle";

  return (
    <span
      ref={ref}
      onMouseEnter={onEnter}
      onMouseLeave={() => phase === "hover" && setPhase("idle")}
      className="relative inline-block pointer-events-auto"
    >
      <span
        onTransitionEnd={() => phase === "fill" && setPhase("idle")}
        className={`text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-red-500 transition-opacity duration-500 ${filled ? "opacity-100" : "opacity-0"}`}
      >
        {TEXT}
      </span>
      <span ref={probeRef} aria-hidden className="inline-block" />

      {outlined && (
        <div className="absolute inset-y-0 -inset-x-[15%] flex items-center justify-center pointer-events-none">
          <SvgPathDrawingTextAnimation
            text={TEXT}
            fromColor="#3b82f6"
            toColor="#ef4444"
            viewBoxWidth={box.width * (1 + 2 * SIDE_PAD)}
            viewBoxHeight={box.height}
            fontSize={box.fontSize}
            fontFamily={box.fontFamily}
            fontWeight={box.fontWeight}
            letterSpacing={box.letterSpacing}
            origin={{ x: box.width * SIDE_PAD, y: box.baseline }}
            strokeWidth={2.4}
            durationSec={2.5}
            loop={false}
            onComplete={() => setPhase("fill")}
          />
        </div>
      )}
    </span>
  );
}
