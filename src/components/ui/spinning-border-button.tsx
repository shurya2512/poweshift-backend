import Link from "next/link";
import { ArrowRight } from "lucide-react";

const ROOT_CLASS =
  "group relative inline-flex items-center justify-center overflow-hidden rounded-full p-[4px] transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[-8px_0_25px_rgba(59,130,246,0.35),8px_0_25px_rgba(239,68,68,0.35)]";

const SIZES = {
  default: {
    surface: "px-12 py-5 text-lg md:text-xl",
    leftArrow: "absolute w-6 h-6 left-[-25%] z-[9] group-hover:left-5 transition-all duration-[800ms] ease-[cubic-bezier(0.34,1.56,0.64,1)]",
    rightArrow: "absolute w-6 h-6 right-5 z-[9] group-hover:right-[-25%] transition-all duration-[800ms] ease-[cubic-bezier(0.34,1.56,0.64,1)]",
    textShift: "relative z-[1] -translate-x-4 group-hover:translate-x-4 transition-all duration-[800ms] ease-out",
    circle: "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-4 bg-[#111111] rounded-[50%] opacity-0 group-hover:w-[400px] group-hover:h-[400px] group-hover:opacity-100 transition-all duration-[800ms] ease-[cubic-bezier(0.19,1,0.22,1)]",
  },
  sm: {
    surface: "px-5 py-2 text-xs md:text-sm",
    leftArrow: "absolute w-4 h-4 left-[-25%] z-[9] group-hover:left-3 transition-all duration-[800ms] ease-[cubic-bezier(0.34,1.56,0.64,1)]",
    rightArrow: "absolute w-4 h-4 right-3 z-[9] group-hover:right-[-25%] transition-all duration-[800ms] ease-[cubic-bezier(0.34,1.56,0.64,1)]",
    textShift: "relative z-[1] -translate-x-2 group-hover:translate-x-2 transition-all duration-[800ms] ease-out",
    circle: "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 bg-[#111111] rounded-[50%] opacity-0 group-hover:w-[250px] group-hover:h-[250px] group-hover:opacity-100 transition-all duration-[800ms] ease-[cubic-bezier(0.19,1,0.22,1)]",
  },
};

/**
 * White pill button. On hover a blue→red beam spins around its edge while a dark
 * circle floods the surface, the text turns white and slides right, and the
 * arrow swaps from the right edge to the left.
 * Renders a Link when `href` is given, otherwise a button calling `onClick`.
 */
export function SpinningBorderButton({
  text = "Request Demo",
  href,
  onClick,
  size = "default",
}: {
  text?: string;
  href?: string;
  onClick?: () => void;
  size?: keyof typeof SIZES;
}) {
  const s = SIZES[size];

  const content = (
    <>
      {/* Spinning blue→red border beam (visible on hover), matching the grid gradient */}
      <span className="absolute inset-[-100%] animate-[spin_3s_linear_infinite] bg-[conic-gradient(from_90deg_at_50%_50%,transparent_0%,transparent_50%,#3b82f6_75%,#ef4444_100%)] opacity-0 transition-opacity duration-300 group-hover:opacity-100" />

      {/* Default static border */}
      <span className="absolute inset-0 rounded-full bg-neutral-300 transition-opacity duration-300 group-hover:opacity-0" />

      {/* Button surface; arrows inherit the text colour */}
      <span className={`relative flex h-full w-full items-center justify-center overflow-hidden rounded-full bg-white font-bold uppercase tracking-widest text-black transition-colors duration-[600ms] ease-[cubic-bezier(0.23,1,0.32,1)] group-hover:text-white ${s.surface}`}>
        {/* Left arrow — slides in on hover */}
        <ArrowRight className={s.leftArrow} />

        <span className={s.textShift}>
          {text}
        </span>

        {/* Dark circle that expands to fill the surface */}
        <span className={s.circle} />

        {/* Right arrow — slides out on hover */}
        <ArrowRight className={s.rightArrow} />
      </span>
    </>
  );

  if (href) {
    return <Link href={href} className={ROOT_CLASS}>{content}</Link>;
  }
  return <button type="button" onClick={onClick} className={ROOT_CLASS}>{content}</button>;
}
