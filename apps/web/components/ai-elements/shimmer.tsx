"use client";

// AI Elements `shimmer` (registry.ai-sdk.dev/shimmer.json). Local changes: plain muted text under prefers-reduced-motion,
// and the motion component of each tag (p, span, div) is created once instead of on every render.

import { cn } from "@/lib/utils";
import { motion, useReducedMotion } from "motion/react";
import {
  type CSSProperties,
  memo,
  useMemo,
} from "react";

export type TextShimmerProps = {
  children: string;
  as?: "p" | "span" | "div";
  className?: string;
  duration?: number;
  spread?: number;
};

// The motion component of each tag, created once at module load (not on every render).
const MOTION = { p: motion.p, span: motion.span, div: motion.div } as const;

const ShimmerComponent = ({
  children,
  as: Component = "p",
  className,
  duration = 2,
  spread = 2,
}: TextShimmerProps) => {
  const reduce = useReducedMotion();

  const dynamicSpread = useMemo(
    () => (children?.length ?? 0) * spread,
    [children, spread]
  );

  if (reduce) return <Component className={cn("text-muted-foreground", className)}>{children}</Component>;

  const MotionComponent = MOTION[Component];
  return (
    <MotionComponent
      animate={{ backgroundPosition: "0% center" }}
      className={cn(
        "relative inline-block bg-[length:250%_100%,auto] bg-clip-text text-transparent",
        "[--bg:linear-gradient(90deg,#0000_calc(50%-var(--spread)),var(--color-background),#0000_calc(50%+var(--spread)))] [background-repeat:no-repeat,padding-box]",
        className
      )}
      initial={{ backgroundPosition: "100% center" }}
      style={
        {
          "--spread": `${dynamicSpread}px`,
          backgroundImage:
            "var(--bg), linear-gradient(var(--color-muted-foreground), var(--color-muted-foreground))",
        } as CSSProperties
      }
      transition={{
        repeat: Number.POSITIVE_INFINITY,
        duration,
        ease: "linear",
      }}
    >
      {children}
    </MotionComponent>
  );
};

export const Shimmer = memo(ShimmerComponent);
