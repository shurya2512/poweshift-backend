"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Award,
  Cloud,
  Globe,
  LayoutDashboard,
  Pizza,
  ShieldCheck,
  Smartphone,
  Store,
  Users,
  WandSparkles,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface FeatureItem {
  id: string;
  label: string;
  icon: LucideIcon;
  description: React.ReactNode;
  /** Fills the card — an image, a diagram, anything that covers it. */
  media: React.ReactNode;
  /** Caption at the top left of the active card. */
  tag?: string;
}

const photo = (src: string, alt: string) => (
  // eslint-disable-next-line @next/next/no-img-element
  <img src={src} alt={alt} className="h-full w-full object-cover" />
);

/** Demo content, shown when no items are passed. */
const FEATURES: FeatureItem[] = [
  {
    id: "sustainable",
    label: "Sustainable Sourcing",
    icon: Pizza,
    media: photo(
      "https://cdn.21st.dev/assets/mirror/c4/c48702475dc62d18bff61e34fb6b240e41d0e33808066607c819abc51c708de5.jpg",
      "Sustainable Sourcing"
    ),
    description: "Ethically sourced ingredients from local farmers.",
  },
  {
    id: "community",
    label: "Community Focused",
    icon: Users,
    media: photo(
      "https://cdn.21st.dev/assets/mirror/c7/c7f3916c2cdc545b8254cc8ce6ae0e4de3f44ad0428502f9be8e0fe1134ecb81.jpg",
      "Community Focused"
    ),
    description: "Building stronger bonds through shared experiences.",
  },
  {
    id: "global",
    label: "Global Reach",
    icon: Globe,
    media: photo(
      "https://cdn.21st.dev/assets/mirror/e0/e02da34643b79ef162a713de4eb8dd88f8249f5bcffe0409a6d447c9918d50aa.jpg",
      "Global Reach"
    ),
    description: "Connecting visionaries across all continents.",
  },
  {
    id: "award",
    label: "Award Winning",
    icon: Award,
    media: photo(
      "https://cdn.21st.dev/assets/mirror/ce/ce089361785f3d1b45326b5a5e6478fba2c133d475401377354ef55f2e153289.jpg",
      "Award Winning"
    ),
    description: "Recognized excellence in design and innovation.",
  },
  {
    id: "cloud",
    label: "Cloud Ready",
    icon: Cloud,
    media: photo(
      "https://cdn.21st.dev/assets/mirror/fa/fa833daf43d62353c6d39bbc0ca40a9396e461c81c61b8195df01eb983f0bc95.jpg",
      "Cloud Ready"
    ),
    description: "Scale your infrastructure with seamless ease.",
  },
  {
    id: "mobile",
    label: "Mobile First",
    icon: Smartphone,
    media: photo(
      "https://cdn.21st.dev/assets/mirror/24/2490eb35d201db5bb6758f8e5508f2301462c803f72cc38e34097d74f6d30578.jpg",
      "Mobile First"
    ),
    description: "A world-class experience on every single device.",
  },
  {
    id: "analytics",
    label: "Real-time Analytics",
    icon: LayoutDashboard,
    media: photo(
      "https://images.unsplash.com/photo-1551288049-bbda38a10ad5?q=80&w=1200",
      "Real-time Analytics"
    ),
    description: "Insights at your fingertips, updated in real-time.",
  },
  {
    id: "security",
    label: "Enterprise Security",
    icon: ShieldCheck,
    media: photo(
      "https://cdn.21st.dev/assets/mirror/8a/8acb03b53b306de4389cc3fd7b4317a9941714060e94a8a19f19853faefc033e.jpg",
      "Enterprise Security"
    ),
    description: "Bank-grade security protocols for your data.",
  },
  {
    id: "magic",
    label: "Magic Automations",
    icon: WandSparkles,
    media: photo(
      "https://cdn.21st.dev/assets/mirror/f7/f7b431dacfc2e3322286eac990b187bd031079e0cd3330d88c6293027a71ed04.jpg",
      "Magic Automations"
    ),
    description: "Let AI handle the repetitive tasks for you.",
  },
  {
    id: "local",
    label: "Locally Owned",
    icon: Store,
    media: photo(
      "https://cdn.21st.dev/assets/mirror/a7/a7c0cea7f9109a4f193768199927768e14de429f3b41a69ffb9b55bbda4a9abc.jpg",
      "Locally Owned"
    ),
    description: "Supporting local businesses and creators.",
  },
];

const AUTO_PLAY_INTERVAL = 3000;
const ITEM_HEIGHT = 56;

const wrap = (min: number, max: number, v: number) => {
  const rangeSize = max - min;
  return ((((v - min) % rangeSize) + rangeSize) % rangeSize) + min;
};

/**
 * A rolling list of chips on the left (a fifth of the width) driving a stack of cards
 * on the right. Both halves are transparent, so it sits on whatever is behind it.
 * Autoplay pauses while the pointer is anywhere over it.
 */
export function FeatureCarousel({
  items = FEATURES,
  onOpen,
}: {
  items?: FeatureItem[];
  /** Called with the active item's id when its card is clicked. */
  onOpen?: (id: string) => void;
}) {
  const [step, setStep] = useState(0);
  const [isPaused, setIsPaused] = useState(false);

  const currentIndex = ((step % items.length) + items.length) % items.length;

  const nextStep = useCallback(() => {
    setStep((prev) => prev + 1);
  }, []);

  const handleChipClick = (index: number) => {
    const diff = (index - currentIndex + items.length) % items.length;
    if (diff > 0) setStep((s) => s + diff);
  };

  useEffect(() => {
    if (isPaused) return;
    const interval = setInterval(nextStep, AUTO_PLAY_INTERVAL);
    return () => clearInterval(interval);
  }, [nextStep, isPaused]);

  const getCardStatus = (index: number) => {
    const diff = index - currentIndex;
    const len = items.length;

    let normalizedDiff = diff;
    if (diff > len / 2) normalizedDiff -= len;
    if (diff < -len / 2) normalizedDiff += len;

    if (normalizedDiff === 0) return "active";
    if (normalizedDiff === -1) return "prev";
    if (normalizedDiff === 1) return "next";
    return "hidden";
  };

  return (
    <div
      className="w-full max-w-7xl mx-auto"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      <div className="relative overflow-hidden rounded-[2.5rem] lg:rounded-[4rem] flex flex-col lg:flex-row min-h-[560px] border border-white/[0.08]">
        {/* Chips fade out at the top and bottom through a mask, so no fill colour is needed. */}
        <div className="w-full lg:w-[20%] min-h-[350px] md:min-h-[450px] relative z-30 flex flex-col items-start justify-center overflow-hidden px-6 lg:px-5 [mask-image:linear-gradient(to_bottom,transparent,black_18%,black_82%,transparent)]">
          <div className="relative w-full h-full flex items-center justify-center lg:justify-start z-20">
            {items.map((feature, index) => {
              const isActive = index === currentIndex;
              const distance = index - currentIndex;
              const wrappedDistance = wrap(
                -(items.length / 2),
                items.length / 2,
                distance
              );
              const Icon = feature.icon;

              return (
                <motion.div
                  key={feature.id}
                  style={{
                    height: ITEM_HEIGHT,
                    width: "fit-content",
                  }}
                  animate={{
                    y: wrappedDistance * ITEM_HEIGHT,
                    opacity: 1 - Math.abs(wrappedDistance) * 0.25,
                  }}
                  transition={{
                    type: "spring",
                    stiffness: 90,
                    damping: 22,
                    mass: 1,
                  }}
                  className="absolute flex items-center justify-start"
                >
                  <button
                    onClick={() => handleChipClick(index)}
                    className={cn(
                      "relative flex items-center gap-3 px-5 lg:px-4 py-3 rounded-full transition-all duration-700 text-left group border",
                      isActive
                        ? "bg-white text-black border-white z-10"
                        : "bg-transparent text-white/60 border-white/20 hover:border-white/40 hover:text-white"
                    )}
                  >
                    <Icon
                      size={16}
                      strokeWidth={2}
                      className={cn(
                        "shrink-0 transition-colors duration-500",
                        isActive ? "text-black" : "text-white/40"
                      )}
                    />
                    <span className="font-normal text-xs md:text-[13px] tracking-tight whitespace-nowrap uppercase">
                      {feature.label}
                    </span>
                  </button>
                </motion.div>
              );
            })}
          </div>
        </div>

        <div className="flex-1 min-h-[420px] md:min-h-[520px] relative flex items-center justify-center py-12 px-6 md:px-12 lg:px-16 overflow-hidden border-t lg:border-t-0 lg:border-l border-white/[0.06]">
          <div className="relative w-full max-w-[640px] aspect-[16/10] flex items-center justify-center">
            {items.map((feature, index) => {
              const status = getCardStatus(index);
              const isActive = status === "active";
              const isPrev = status === "prev";
              const isNext = status === "next";

              return (
                <motion.div
                  key={feature.id}
                  initial={false}
                  animate={{
                    x: isActive ? 0 : isPrev ? -100 : isNext ? 100 : 0,
                    scale: isActive ? 1 : isPrev || isNext ? 0.85 : 0.7,
                    opacity: isActive ? 1 : isPrev || isNext ? 0.4 : 0,
                    rotate: isPrev ? -3 : isNext ? 3 : 0,
                    zIndex: isActive ? 20 : isPrev || isNext ? 10 : 0,
                    pointerEvents: isActive ? "auto" : "none",
                  }}
                  transition={{
                    type: "spring",
                    stiffness: 260,
                    damping: 25,
                    mass: 0.8,
                  }}
                  onClick={isActive && onOpen ? () => onOpen(feature.id) : undefined}
                  className="absolute inset-0 rounded-[2rem] md:rounded-[2.8rem] overflow-hidden border-4 md:border-8 border-neutral-950 bg-neutral-950 origin-center"
                >
                  <div
                    className={cn(
                      "w-full h-full transition-all duration-700",
                      isActive
                        ? "grayscale-0 blur-0"
                        : "grayscale blur-[2px] brightness-75"
                    )}
                  >
                    {feature.media}
                  </div>

                  <AnimatePresence>
                    {isActive && (
                      <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 10 }}
                        className="absolute inset-x-0 bottom-0 p-6 md:p-8 pt-20 bg-linear-to-t from-black/90 via-black/40 to-transparent flex flex-col justify-end pointer-events-none"
                      >
                        <div className="bg-neutral-950 text-white px-4 py-1.5 rounded-full text-[11px] font-normal uppercase tracking-[0.2em] w-fit shadow-lg mb-3 border border-white/10">
                          {index + 1} • {feature.label}
                        </div>
                        <div className="text-white font-normal text-lg md:text-2xl leading-tight drop-shadow-md tracking-tight">
                          {feature.description}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  <div
                    className={cn(
                      "absolute top-6 left-6 md:top-8 md:left-8 flex items-center gap-3 transition-opacity duration-300",
                      isActive ? "opacity-100" : "opacity-0"
                    )}
                  >
                    <div className="w-2 h-2 rounded-full bg-white shadow-[0_0_10px_white]" />
                    <span className="text-white/80 text-[10px] font-normal uppercase tracking-[0.3em] font-mono">
                      {feature.tag ?? "Live Session"}
                    </span>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default FeatureCarousel;
