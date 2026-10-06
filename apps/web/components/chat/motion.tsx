"use client";

// The one motion adapter of /chat (spec 07 AC-26, AC-27). Every chat animation goes through these primitives, named like
// the shared web motion kit (Reveal, Stagger, DrawCheck, Collapse, useReducedMotionGuard), so the kit can replace this
// file in one place. No chat component imports `motion` itself. The timing rules live in lib/chat-motion.ts (tested
// offline); with prefers-reduced-motion nothing moves: no animated props, the content shows at once.
import { motion, useReducedMotion } from "motion/react";
import { Children, type ComponentProps, type ReactNode } from "react";
import { type EnterKind, EASE_OUT, cardDelay, enter } from "@/lib/chat-motion";

/** True when the visitor asked for reduced motion: every primitive below renders still. */
export function useReducedMotionGuard(): boolean {
  return useReducedMotion() ?? false;
}

/** Fades and rises (or slides, or scales, by `kind`) once, when it mounts. */
export function Reveal({ kind = "part", delay, ...props }: { kind?: EnterKind; delay?: number } & ComponentProps<typeof motion.div>) {
  const reduce = useReducedMotionGuard();
  return <motion.div {...enter(kind, { reduce, delay })} {...props} />;
}

/** Reveals each child `gap` seconds after the one before (option cards rise 40 ms apart). */
export function Stagger({ kind = "card", base = 0, children, className, role }: { kind?: EnterKind; base?: number; children: ReactNode; className?: string; role?: string }) {
  return (
    <div className={className} role={role}>
      {Children.toArray(children).map((child, i) => (
        <Reveal key={(child as { key?: string | null }).key ?? i} kind={kind} delay={cardDelay(i, base)} role={role === "list" ? "listitem" : undefined}>
          {child}
        </Reveal>
      ))}
    </div>
  );
}

/** A check drawn with its stroke (pathLength, the motion form of stroke-dashoffset) over 250 ms. */
export function DrawCheck({ className }: { className?: string }) {
  const reduce = useReducedMotionGuard();
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden className={className}>
      <motion.path d="M20 6 9 17l-5-5" {...(reduce ? {} : { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { duration: 0.25, ease: EASE_OUT } })} />
    </svg>
  );
}

/** Opens and closes with a height animation (200 ms ease-out); under reduced motion it just shows or hides. */
export function Collapse({ open, children, className, id }: { open: boolean; children: ReactNode; className?: string; id?: string }) {
  const reduce = useReducedMotionGuard();
  if (reduce) return open ? <div id={id} className={className}>{children}</div> : null;
  return (
    <motion.div
      id={id}
      className={className}
      initial={false}
      animate={open ? { height: "auto", opacity: 1 } : { height: 0, opacity: 0 }}
      transition={{ duration: 0.2, ease: EASE_OUT }}
      style={{ overflow: "hidden" }}
      aria-hidden={!open || undefined}
      inert={!open || undefined}
    >
      {children}
    </motion.div>
  );
}

/** One brief pulse when it appears (the "verified" state). */
export function Pulse({ on, children, className }: { on: boolean; children: ReactNode; className?: string }) {
  const reduce = useReducedMotionGuard();
  const pulse = on && !reduce ? { initial: { scale: 0.9, opacity: 0.6 }, animate: { scale: [0.9, 1.06, 1], opacity: 1 }, transition: { duration: 0.3, ease: EASE_OUT } } : {};
  return (
    <motion.span {...pulse} className={className}>
      {children}
    </motion.span>
  );
}

/** A number that ticks in once (the deadline countdown); its value is final from the first render. */
export function TickIn({ children, delay = 0.45 }: { children: ReactNode; delay?: number }) {
  const reduce = useReducedMotionGuard();
  if (reduce) return <span className="tabular-nums">{children}</span>;
  return (
    <motion.span className="inline-block tabular-nums" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25, delay, ease: EASE_OUT }}>
      {children}
    </motion.span>
  );
}
