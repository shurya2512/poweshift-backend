"use client";

import { useEffect, useRef } from "react";
import { INTERACTIVE } from "@/components/ClickWatermark";

const RED = "#ff3b3b";
const BLUE = "#3b8bff";
/** Hotspot inside the SVG (arrow tip and index fingertip), placed on the pointer. */
const HOT_X = 9;
const HOT_Y = 2;
/** Where red meets blue across each shape's width: 40% red, 60% blue. */
const SPLIT = 0.4;
/** Half-width of the red→blue blend, as a fraction of the shape's width. */
const BLEND = 0.15;
/** Elements that swap the arrow for the pointing hand, like the native cursor. */
const CLICKABLE = `${INTERACTIVE}, .cursor-pointer`;

const ARROW = "M9 2 L9 19 L13.5 14.8 L16.4 21.4 L19.2 20.2 L16.4 13.8 L22.4 13.8 Z";
const HAND =
  "M7 12.5 L7 4 A2 2 0 0 1 11 4 L11 10.5 A2 2 0 0 1 15 10.5 L15 11.5 A2 2 0 0 1 19 11.5 " +
  "L19 13 A1.5 1.5 0 0 1 22 13 L22 17.5 C22 21 20 23.5 17 23.5 L12.5 23.5 " +
  "C10.5 23.5 9.2 22.5 8 21 L3.6 15.8 A1.6 1.6 0 0 1 6 13.7 L7 14.7 Z";
const EDGE = {
  fill: "black",
  stroke: "url(#edge-gradient)",
  strokeWidth: 1.6,
  strokeLinejoin: "round",
} as const;

/**
 * A black cursor with a 40/60 red→blue edge that follows the mouse: an arrow,
 * or a pointing hand over clickable elements. The half on the pointer's side of
 * the screen (red left, blue right) glows brightest.
 */
export default function EdgeCursor() {
  const ref = useRef<HTMLDivElement>(null);
  const gradientRef = useRef<SVGLinearGradientElement>(null);
  const arrowRef = useRef<SVGPathElement>(null);
  const handRef = useRef<SVGPathElement>(null);

  useEffect(() => {
    const el = ref.current!;
    const stops = gradientRef.current!.querySelectorAll("stop");
    const arrow = arrowRef.current!;
    const hand = handRef.current!;
    const move = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      const fx = e.clientX / window.innerWidth;
      const red = String(0.8 + 0.2 * (1 - fx));
      const blue = String(0.8 + 0.2 * fx);
      stops.forEach((s, i) => s.setAttribute("stop-opacity", i < 2 ? red : blue));
      const clickable = (e.target as Element).closest(CLICKABLE) !== null;
      arrow.style.display = clickable ? "none" : "";
      hand.style.display = clickable ? "" : "none";
      el.style.transform = `translate(${e.clientX - HOT_X}px, ${e.clientY - HOT_Y}px)`;
      el.style.opacity = "1";
    };
    const leave = () => {
      el.style.opacity = "0";
    };

    window.addEventListener("pointermove", move);
    document.documentElement.addEventListener("pointerleave", leave);
    return () => {
      window.removeEventListener("pointermove", move);
      document.documentElement.removeEventListener("pointerleave", leave);
    };
  }, []);

  return (
    <div
      ref={ref}
      aria-hidden
      className="fixed left-0 top-0 z-[100000] pointer-events-none opacity-0"
    >
      <svg width="24" height="25" viewBox="0 0 24 25" className="block">
        <defs>
          <linearGradient ref={gradientRef} id="edge-gradient" x1="0" x2="1">
            <stop offset="0" stopColor={RED} />
            <stop offset={SPLIT - BLEND} stopColor={RED} />
            <stop offset={SPLIT + BLEND} stopColor={BLUE} />
            <stop offset="1" stopColor={BLUE} />
          </linearGradient>
        </defs>
        <path ref={arrowRef} d={ARROW} {...EDGE} />
        <path ref={handRef} d={HAND} {...EDGE} style={{ display: "none" }} />
      </svg>
    </div>
  );
}
