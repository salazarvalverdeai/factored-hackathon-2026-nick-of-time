"use client";

// Small SVG motion primitives for /agent's drawings, built on `motion` (BRAND.md: 150–400 ms, ease-out, no glow or
// bounce). They are local on purpose: when a shared motion kit lands (components/motion/: Reveal, DrawPath,
// FlowConnector) these can be swapped for it without touching the drawings' data. The server render and
// `prefers-reduced-motion: reduce` show the final state; nothing here changes an element's box, so nothing shifts.
import { animate, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useRef, useState, type ComponentPropsWithoutRef, type ReactNode, type RefObject } from "react";
import { EASE_OUT, TIMING, firstPhase, pointAt, replayPhase, transitionFor, type Point, type RevealPhase } from "@/lib/agent-motion";

/**
 * The reveal state of a drawing: armed while below the fold, played when it scrolls into view, final afterwards.
 * `run` changes on every Replay so the drawing remounts from its hidden state.
 */
export function useReveal(ref: RefObject<Element | null>, { enabled = true, total }: { enabled?: boolean; total: number }) {
  const reduced = useReducedMotion() ?? false;
  const [phase, setPhase] = useState<RevealPhase>("final");
  const [run, setRun] = useState(0);
  const armed = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || !enabled || typeof IntersectionObserver === "undefined") return;
    let first = true;
    const observer = new IntersectionObserver(
      ([entry]) => {
        const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
        if (first) {
          first = false;
          const next = firstPhase({ reducedMotion: reduce, visible: entry.isIntersecting });
          if (next === "hidden") {
            armed.current = true;
            setPhase("hidden");
          } else observer.disconnect();
          return;
        }
        if (armed.current && entry.isIntersecting) {
          armed.current = false;
          setPhase("play");
          observer.disconnect();
        }
      },
      { threshold: 0.2 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, enabled]);

  useEffect(() => {
    if (phase !== "play") return;
    const timer = setTimeout(() => setPhase("final"), total * 1000 + 120);
    return () => clearTimeout(timer);
  }, [phase, run, total]);

  const replay = useCallback(() => {
    armed.current = false;
    const next = replayPhase(reduced);
    setPhase(next);
    if (next === "play") setRun((r) => r + 1);
  }, [reduced]);

  return { phase, run, replay, reduced };
}

/** Fades a group in (and lifts it a few units) at its delay while the drawing plays. */
export function Reveal({
  phase,
  delay,
  duration = TIMING.node,
  rise = 0,
  className,
  children,
}: { phase: RevealPhase; delay: number; duration?: number; rise?: number; className?: string; children: ReactNode }) {
  return (
    <motion.g
      initial={phase === "play" ? "hidden" : false}
      animate={phase === "hidden" ? "hidden" : "shown"}
      variants={{ hidden: { opacity: 0, y: rise }, shown: { opacity: 1, y: 0 } }}
      transition={transitionFor(phase, delay, duration)}
      className={className}
    >
      {children}
    </motion.g>
  );
}

/**
 * A path that draws itself from its start while the drawing plays, through a mask so dashed strokes and arrowheads
 * keep their style. In the final phase the mask is gone and the path is exactly the static one.
 */
export function DrawPath({
  phase,
  delay,
  duration = TIMING.edge,
  maskId,
  bounds,
  ...props
}: { phase: RevealPhase; delay: number; duration?: number; maskId: string; bounds: { width: number; height: number } } & ComponentPropsWithoutRef<"path">) {
  if (phase === "final") return <path {...props} />;
  return (
    <>
      <mask id={maskId} maskUnits="userSpaceOnUse" x={0} y={0} width={bounds.width} height={bounds.height}>
        <motion.path
          d={props.d}
          fill="none"
          stroke="white"
          strokeWidth={14}
          pathLength={1}
          strokeDasharray="1 1"
          initial={phase === "play" ? { strokeDashoffset: 1 } : false}
          animate={{ strokeDashoffset: phase === "hidden" ? 1 : 0 }}
          transition={transitionFor(phase, delay, duration)}
        />
      </mask>
      <path {...props} mask={`url(#${maskId})`} />
    </>
  );
}

/**
 * A dot that travels once along a polyline each time `play` changes, then rests at the end. Not rendered with reduced
 * motion: the highlighted path carries the same meaning.
 */
export function FlowDot({ points, play, className, duration = 0.6 }: { points: readonly Point[]; play: string | number; className?: string; duration?: number }) {
  const ref = useRef<SVGCircleElement>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) return;
    const move = (t: number) => {
      const p = pointAt(points, t);
      el.setAttribute("cx", String(p.x));
      el.setAttribute("cy", String(p.y));
    };
    move(0);
    el.style.opacity = "1";
    const controls = animate(0, 1, { duration, ease: EASE_OUT, onUpdate: move });
    return () => controls.stop();
  }, [points, play, duration, reduced]);
  if (reduced) return null;
  const [x, y] = points[0];
  return <circle ref={ref} cx={x} cy={y} r={4} className={className} style={{ opacity: 0 }} aria-hidden="true" />;
}
