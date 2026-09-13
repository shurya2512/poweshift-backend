import Link from "next/link";
import { ArrowRight } from "lucide-react";

const ROOT_CLASS =
  "group relative inline-flex items-center justify-center overflow-hidden rounded-full p-[4px] transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[-8px_0_25px_rgba(59,130,246,0.35),8px_0_25px_rgba(239,68,68,0.35)]";

// Masks the border layers down to the 4px padding ring, so a hollow surface can stay see-through.
// `exclude` sits inside the shorthand: `mask` resets mask-composite, so a separate class loses to it.
const RING_MASK = "p-[4px] [mask:linear-gradient(#fff_0_0)_content-box_exclude,linear-gradient(#fff_0_0)]";

// Blue→red edge beam. --beam-gap (registered in globals.css) is the unlit share of the ring.
const BEAM_GRADIENT =
  "bg-[conic-gradient(from_90deg_at_50%_50%,transparent_0%,transparent_var(--beam-gap),#3b82f6_calc(var(--beam-gap)_+_25%),#ef4444_100%)]";

const BEAM_MOTION = {
  spin: "animate-[spin_3s_linear_infinite]",
  once: "group-hover:animate-[beam-lap-fill_2s_ease-in-out_forwards]",
};

const SIZES = {
  default: {
    surface: "px-12 py-5 text-lg md:text-xl gap-3",
    icon: "w-6 h-6",
    leftArrow: "absolute w-6 h-6 left-[-25%] z-[9] group-hover:left-5 transition-all duration-[800ms] ease-[cubic-bezier(0.34,1.56,0.64,1)]",
    rightArrow: "absolute w-6 h-6 right-5 z-[9] group-hover:right-[-25%] transition-all duration-[800ms] ease-[cubic-bezier(0.34,1.56,0.64,1)]",
    textShift: "relative z-[1] -translate-x-4 group-hover:translate-x-4 transition-all duration-[800ms] ease-out",
    circle: "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-4 bg-[#111111] rounded-[50%] opacity-0 group-hover:w-[400px] group-hover:h-[400px] group-hover:opacity-100 transition-all duration-[800ms] ease-[cubic-bezier(0.19,1,0.22,1)]",
  },
  sm: {
    surface: "px-5 py-2 text-xs md:text-sm gap-2",
    icon: "w-4 h-4",
    leftArrow: "absolute w-4 h-4 left-[-25%] z-[9] group-hover:left-3 transition-all duration-[800ms] ease-[cubic-bezier(0.34,1.56,0.64,1)]",
    rightArrow: "absolute w-4 h-4 right-3 z-[9] group-hover:right-[-25%] transition-all duration-[800ms] ease-[cubic-bezier(0.34,1.56,0.64,1)]",
    textShift: "relative z-[1] -translate-x-2 group-hover:translate-x-2 transition-all duration-[800ms] ease-out",
    circle: "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 bg-[#111111] rounded-[50%] opacity-0 group-hover:w-[250px] group-hover:h-[250px] group-hover:opacity-100 transition-all duration-[800ms] ease-[cubic-bezier(0.19,1,0.22,1)]",
  },
};

/**
 * Pill button. On hover a blue→red beam lights its edge, the text slides
 * right and the arrow swaps from the right edge to the left.
 * "solid" fill: white surface that a dark circle floods on hover, turning the text white.
 * "hollow" fill: transparent surface with only the edge drawn, staying transparent on hover.
 * Renders a Link when `href` is given, otherwise a button calling `onClick`.
 */
export function SpinningBorderButton({
  text = "Request Demo",
  href,
  onClick,
  size = "default",
  arrowMode = "slide",
  fill = "solid",
  beam = "spin",
}: {
  text?: string;
  href?: string;
  onClick?: () => void;
  size?: keyof typeof SIZES;
  /** "slide": right arrow slides out, left arrow slides in (default). "flip": a single arrow stays on the left and reverses direction on hover. */
  arrowMode?: "slide" | "flip";
  /** "solid": white surface (default). "hollow": transparent inside, only the edge is drawn. */
  fill?: "solid" | "hollow";
  /** "spin": the beam circles the edge while hovered (default). "once": one lap, then it fills the whole edge and stops. */
  beam?: keyof typeof BEAM_MOTION;
}) {
  const s = SIZES[size];
  const hollow = fill === "hollow";
  const surfaceColors = hollow ? "bg-transparent text-white" : "bg-white text-black group-hover:text-white";
  const circle = hollow ? null : <span className={s.circle} />;

  const content = (
    <>
      <span className={`absolute inset-0 overflow-hidden rounded-full ${hollow ? RING_MASK : ""}`}>
        {/* Blue→red border beam (visible on hover), matching the grid gradient */}
        <span className={`absolute inset-[-100%] opacity-0 transition-opacity duration-300 group-hover:opacity-100 ${BEAM_GRADIENT} ${BEAM_MOTION[beam]}`} />

        {/* Default static border */}
        <span className="absolute inset-0 rounded-full bg-neutral-300 transition-opacity duration-300 group-hover:opacity-0" />
      </span>

      {/* Button surface; arrows inherit the text colour */}
      <span className={`relative flex h-full w-full items-center justify-center overflow-hidden rounded-full font-bold uppercase tracking-widest transition-colors duration-[600ms] ease-[cubic-bezier(0.23,1,0.32,1)] ${surfaceColors} ${s.surface}`}>
        {arrowMode === "flip" ? (
          <>
            {/* Arrow stays on the left; points right at rest, flips to point left on hover */}
            <ArrowRight className={`relative z-[1] transition-transform duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)] group-hover:rotate-180 ${s.icon}`} />
            <span className="relative z-[1]">{text}</span>
            {circle}
          </>
        ) : (
          <>
            {/* Left arrow — slides in on hover */}
            <ArrowRight className={s.leftArrow} />

            <span className={s.textShift}>
              {text}
            </span>

            {/* Dark circle that expands to fill the surface */}
            {circle}

            {/* Right arrow — slides out on hover */}
            <ArrowRight className={s.rightArrow} />
          </>
        )}
      </span>
    </>
  );

  if (href) {
    return <Link href={href} className={ROOT_CLASS}>{content}</Link>;
  }
  return <button type="button" onClick={onClick} className={ROOT_CLASS}>{content}</button>;
}
