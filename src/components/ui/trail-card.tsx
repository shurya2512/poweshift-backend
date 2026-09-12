"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

// Adapted from 21st.dev's TrailCard: generic labels so it can show more than trails,
// React 19 ref-as-prop instead of forwardRef, and the action button revealed on card hover.

type Stat = { label: string; value: string };

interface TrailCardProps extends React.ComponentProps<typeof motion.div> {
  imageUrl: string;
  /** Extra classes for the hero image, e.g. `object-top` to keep a portrait's face in frame. */
  imageClassName?: string;
  thumbnailUrl: string;
  title: string;
  subtitle: string;
  highlight: string;
  caption: string;
  stats: Stat[];
  actionLabel: string;
  onAction?: () => void;
}

const StatItem = ({ label, value }: Stat) => (
  <div className="flex flex-col">
    <span className="text-sm font-semibold text-card-foreground">{value}</span>
    <span className="text-xs text-muted-foreground">{label}</span>
  </div>
);

// The card lifts on hover and passes the "hover" label down, which slides the action button in.
const cardVariants = { rest: { y: 0, scale: 1 }, hover: { y: -5, scale: 1.02 } };
const actionVariants = { rest: { opacity: 0, x: 20 }, hover: { opacity: 1, x: 0 } };

function TrailCard({
  className,
  imageUrl,
  imageClassName,
  thumbnailUrl,
  title,
  subtitle,
  highlight,
  caption,
  stats,
  actionLabel,
  onAction,
  ...props
}: TrailCardProps) {
  return (
    <motion.div
      className={cn(
        "flex w-full max-w-sm flex-col overflow-hidden rounded-2xl bg-card text-card-foreground shadow-lg",
        className
      )}
      initial="rest"
      animate="rest"
      whileHover="hover"
      variants={cardVariants}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
      {...props}
    >
      {/* Hero image with the title overlaid; grows to fill when the card is stretched */}
      <div className="relative min-h-60 w-full flex-1">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={imageUrl} alt={title} className={cn("absolute inset-0 h-full w-full object-cover", imageClassName)} />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/30 to-transparent" />
        <div className="absolute bottom-0 left-0 flex w-full items-end justify-between p-4">
          <div className="text-white">
            <h3 className="text-xl font-bold">{title}</h3>
            <p className="text-sm text-white/90">{subtitle}</p>
          </div>
          <motion.div variants={actionVariants} transition={{ duration: 0.3, ease: "easeInOut" }}>
            <Button variant="secondary" onClick={onAction} aria-label={`${actionLabel}: ${title}`}>
              {actionLabel}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </motion.div>
        </div>
      </div>

      {/* Details */}
      <div className="p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-bold text-card-foreground">{highlight}</p>
            <p className="text-xs text-muted-foreground">{caption}</p>
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={thumbnailUrl} alt="" className="h-10 w-20 object-contain" />
        </div>
        <div className="my-4 h-px w-full bg-border" />
        <div className="flex justify-between">
          {stats.map(stat => (
            <StatItem key={stat.label} {...stat} />
          ))}
        </div>
      </div>
    </motion.div>
  );
}

export { TrailCard };
