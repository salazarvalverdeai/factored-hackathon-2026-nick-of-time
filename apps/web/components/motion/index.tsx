"use client";

// Motion kit of the web app (README.md in this folder). Every component plays once, when it first enters the viewport,
// for at most 600 ms (a whole sequence at most 1.5 s), with an ease-out and no overshoot. With reduced motion nothing
// moves: each one renders its final state. Only transform, opacity and stroke-dashoffset animate, so nothing shifts.
import { useEffect, useRef, type ComponentPropsWithoutRef, type ReactNode } from "react";
import { useReducedMotion } from "motion/react";
import { NumberTicker } from "@/components/ui/number-ticker";
import { EASE, MOTION, splitFigures } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { MotionGroup, part, type MotionGroupProps, type MotionTag } from "./motion-group";

export { MotionGroup, MotionReady, part, useMotionOnce } from "./motion-group";
export { NumberTicker };
export { MOTION, fitStep, growTarget, staggerDelay, walkSchedule } from "@/lib/motion";

type Without<T extends MotionTag> = Omit<MotionGroupProps<T>, "kind">;

/** Fades and rises 8 px when it enters the viewport, once. `fade` drops the rise (for marks that must not move). */
export function Reveal<T extends MotionTag = "div">({ fade = false, ...props }: Without<T> & { fade?: boolean }) {
  return <MotionGroup {...(props as MotionGroupProps<T>)} kind="reveal" {...(fade ? part.fade : part.rise)} span={(props.delay ?? 0) + MOTION.rise} />;
}

/**
 * Its direct children rise in sequence (no wrapper element, so grids and lists keep their layout). The step shrinks
 * so that the last child still ends within the 1.5 s sequence.
 */
export function Stagger<T extends MotionTag = "div">({ step = MOTION.step, count, ...props }: Without<T> & { count?: number }) {
  const fitted = count ? Math.min(step, (MOTION.sequence - MOTION.rise - (props.delay ?? 0)) / Math.max(1, Math.min(count, 13) - 1)) : step;
  return <MotionGroup {...(props as MotionGroupProps<T>)} kind="stagger" step={Math.max(0, fitted)} />;
}

/**
 * A bar that grows from 0 to its size along `axis` (scale, so the space is reserved from the first frame). Set its
 * size with `growTarget()`; every div prop passes through, so the bar itself can take focus and carry the tooltip.
 */
export function GrowBar({ axis = "x", ...props }: Without<"div"> & { axis?: "x" | "y" }) {
  return <MotionGroup {...props} kind="grow" {...(axis === "x" ? part.growX : part.growY)} span={(props.delay ?? 0) + MOTION.grow} />;
}

/**
 * A composite mark: spread `part.growX` / `part.growY` on the bar inside it and `part.after` on what fades in once the
 * bar is drawn (an interval band, a dot, a label).
 */
export function GrowGroup<T extends MotionTag = "div">(props: Without<T>) {
  return <MotionGroup {...(props as MotionGroupProps<T>)} kind="grow" span={(props.delay ?? 0) + MOTION.grow + MOTION.after + 100} />;
}

/** An SVG line that draws itself along its length (pathLength = 1). Pass `points` for a polyline or `d` for a path. */
export function DrawPath({ delay = 0, ...props }: Omit<ComponentPropsWithoutRef<"path">, "ref"> & { points?: string; delay?: number }) {
  const as = props.points !== undefined ? "polyline" : "path";
  return <MotionGroup {...(props as MotionGroupProps<"path">)} as={as} kind="draw" delay={delay} {...part.draw} span={delay + MOTION.draw} />;
}

const FLOW = {
  right: (l: number) => ({ w: l, h: 10, line: `M0 5 H${l - 2}`, head: `${l - 5},2 ${l - 1},5 ${l - 5},8` }),
  left: (l: number) => ({ w: l, h: 10, line: `M${l} 5 H2`, head: `5,2 1,5 5,8` }),
  down: (l: number) => ({ w: 10, h: l, line: `M5 0 V${l - 2}`, head: `2,${l - 5} 5,${l - 1} 8,${l - 5}` }),
  up: (l: number) => ({ w: 10, h: l, line: `M5 ${l} V2`, head: `2,5 5,1 8,5` }),
} as const;

/**
 * A short dashed edge with an arrowhead, for diagrams: on entering the viewport the dashes flow once toward the head,
 * then the head fades in. `loop` keeps the dashes moving (only for an edge that is live right now). Decorative: it is
 * aria-hidden, the diagram's text carries the order.
 */
export function FlowConnector({ direction = "right", length = 16, delay = 0, loop = false, className }: {
  direction?: keyof typeof FLOW; length?: number; delay?: number; loop?: boolean; className?: string;
}) {
  const g = FLOW[direction](length);
  return (
    <MotionGroup as="span" kind="flow" delay={delay} after={MOTION.flow} span={delay + MOTION.flow + MOTION.after} aria-hidden
      className={cn("pointer-events-none inline-block text-muted-foreground", className)}>
      <svg width={g.w} height={g.h} viewBox={`0 0 ${g.w} ${g.h}`} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="block overflow-visible">
        <path d={g.line} strokeDasharray="3 3" data-motion-flow="" {...(loop ? { "data-motion-loop": "" } : {})} />
        <polyline points={g.head} {...part.after} />
      </svg>
    </MotionGroup>
  );
}

/** Subtle hover and focus elevation: 2 px up and a violet-tinted border; no shadow or glow (BRAND.md). */
export const lift =
  "motion-safe:transition-[translate,border-color] motion-safe:duration-200 motion-safe:ease-out hover:border-primary/40 focus-within:border-primary/40 " +
  "motion-safe:hover:-translate-y-0.5 motion-safe:focus-within:-translate-y-0.5";

export function Lift<T extends "div" | "li" | "article" | "section" = "div">({ as, className, ...props }: { as?: T } & ComponentPropsWithoutRef<T>) {
  const reduced = useReducedMotion();
  const Tag = (as ?? "div") as "div";
  return <Tag {...(props as ComponentPropsWithoutRef<"div">)} className={cn(reduced ? "hover:border-primary/40 focus-within:border-primary/40" : lift, className)} />;
}

/**
 * Crossfades its content when `id` changes (a switch, a tab), without remounting it: open tables, focus and scroll stay.
 * The first render never animates.
 */
export function Crossfade({ id, className, children }: { id: string; className?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const last = useRef(id);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (last.current === id) return;
    last.current = id;
    const el = ref.current;
    if (!el || reduced || typeof el.animate !== "function") return;
    el.animate([{ opacity: 0.2 }, { opacity: 1 }], { duration: MOTION.fade, easing: EASE });
  }, [id, reduced]);
  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}

/**
 * A formatted line whose numbers count up ("88.9%", "12 tables · 1,234,567 rows [data]"). A number counts only when the
 * ticker formats it back to the same text, so the last frame is always `text`; anything else stays plain text.
 */
export function CountText({ text, delay = 0, className }: { text: string; delay?: number; className?: string }) {
  return (
    <span className={className}>
      {splitFigures(text).map((p, i) =>
        // keyed by its text: a new value remounts the ticker, so React never updates digits the ticker wrote itself
        "value" in p ? <NumberTicker key={`${i}:${p.text}`} value={p.value} decimalPlaces={p.decimals} duration={MOTION.count / 1000} delay={delay / 1000} /> : p.text,
      )}
    </span>
  );
}
