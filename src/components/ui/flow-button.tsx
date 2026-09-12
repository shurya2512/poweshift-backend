import Link from "next/link";
import { ArrowRight } from "lucide-react";

/**
 * White pill link that morphs on hover: a dark circle floods the pill, the
 * text turns white and slides right, and the arrow swaps from the right edge
 * to the left.
 */
export function FlowButton({ text = "Modern Button", href }: { text?: string; href: string }) {
  return (
    <Link
      href={href}
      className="group relative flex items-center gap-1 overflow-hidden rounded-[100px] border-[1.5px] border-white bg-white px-12 py-5 text-lg md:text-xl font-bold uppercase tracking-wider text-black shadow-xl cursor-pointer transition-all duration-[600ms] ease-[cubic-bezier(0.23,1,0.32,1)] hover:border-transparent hover:text-white hover:rounded-[12px] active:scale-[0.95]"
    >
      {/* Left arrow — slides in on hover */}
      <ArrowRight className="absolute w-6 h-6 left-[-25%] stroke-black fill-none z-[9] group-hover:left-5 group-hover:stroke-white transition-all duration-[800ms] ease-[cubic-bezier(0.34,1.56,0.64,1)]" />

      <span className="relative z-[1] -translate-x-4 group-hover:translate-x-4 transition-all duration-[800ms] ease-out">
        {text}
      </span>

      {/* Dark circle that expands to fill the pill */}
      <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-4 bg-[#111111] rounded-[50%] opacity-0 group-hover:w-[400px] group-hover:h-[400px] group-hover:opacity-100 transition-all duration-[800ms] ease-[cubic-bezier(0.19,1,0.22,1)]" />

      {/* Right arrow — slides out on hover */}
      <ArrowRight className="absolute w-6 h-6 right-5 stroke-black fill-none z-[9] group-hover:right-[-25%] group-hover:stroke-white transition-all duration-[800ms] ease-[cubic-bezier(0.34,1.56,0.64,1)]" />
    </Link>
  );
}
