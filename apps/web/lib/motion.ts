// Pure parts of the motion kit (components/motion/), kept apart so `npm test` checks them without a DOM.
// The timings mirror components/motion/motion.css; lib/motion.test.ts reads that file and fails if they drift.
import { formatTicker } from "./ticker.ts";

/** Milliseconds. Every single animation is at most 600 ms and a whole sequence at most 1.5 s (calm, no overshoot). */
export const MOTION = {
  rise: 450,
  fade: 300,
  grow: 500,
  draw: 600,
  flow: 450,
  after: 250,
  /** Gap between two staggered items. */
  step: 70,
  /** The longest a sequence may run, first start to last end. */
  sequence: 1500,
  /** Count-up of a figure, in ms (NumberTicker takes seconds). */
  count: 600,
} as const;

/** Ease-out with no overshoot (the brand voice is calm and precise: no bounce). */
export const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";

/**
 * The attribute the head script puts on <html> when motion may run: JavaScript is on and the user has not asked for
 * reduced motion. Without it every part of the kit renders its final state from the first paint.
 */
export const MOTION_OK = "data-motion-ok";
export const MOTION_LIVE = "data-motion-live";

/**
 * Runs in <head> before the first paint (app/layout.tsx). If the app has not hydrated four seconds later (a script
 * failed to load), it removes the flag, so nothing stays hidden.
 */
export const MOTION_HEAD_SCRIPT =
  `(function(){try{var d=document.documentElement;if(window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches)return;` +
  `d.setAttribute("${MOTION_OK}","");setTimeout(function(){if(!d.hasAttribute("${MOTION_LIVE}"))d.removeAttribute("${MOTION_OK}")},4000)}catch(e){}})()`;

export type MotionState = "pending" | "in" | "done";

// Plain data, kept out of the "use client" kit so a server component can import it too (an export of a client module
// reaches the server as a client reference, not as its value).
/** Spread on an element inside a root to make it a part (motion.css holds the start and end states). */
export const part = {
  rise: { "data-motion-rise": "" },
  fade: { "data-motion-fade": "" },
  growX: { "data-motion-grow": "x" },
  growY: { "data-motion-grow": "y" },
  draw: { "data-motion-draw": "", pathLength: 1 },
  /** Fades in once the root's main part has finished (grow or draw). */
  after: { "data-motion-after": "" },
} as const;

/** Subtle hover and focus elevation: 2 px up and a violet-tinted border; no shadow or glow (BRAND.md). */
export const lift =
  "motion-safe:transition-[translate,border-color] motion-safe:duration-200 motion-safe:ease-out hover:border-primary/40 focus-within:border-primary/40 " +
  "motion-safe:hover:-translate-y-0.5 motion-safe:focus-within:-translate-y-0.5";


/** Where a part starts: with reduced motion (or no motion flag) it is the final state at once, never a start state. */
export function initialState(reduced: boolean | null, motionOk: boolean): MotionState {
  return reduced || !motionOk ? "done" : "pending";
}

/** The value a figure shows on its first frame: the final one with reduced motion. */
export function firstFrame(value: number, reduced: boolean | null, start: number): number {
  return reduced ? value : start;
}

/** Delay of the item at `index` in a stagger, capped so the last item still starts in time to end within the sequence. */
export function staggerDelay(index: number, step: number = MOTION.step, duration: number = MOTION.rise): number {
  return Math.max(0, Math.min(index * step, MOTION.sequence - duration));
}

/** The step that fits `count` items in one sequence: never more than `step`, never past the sequence. */
export function fitStep(count: number, step: number = MOTION.step, duration: number = MOTION.rise, start = 0): number {
  if (count <= 1) return 0;
  return Math.max(0, Math.min(step, (MOTION.sequence - duration - start) / (count - 1)));
}

/** Width or height of a bar, in percent of its track: value over max, times the share of the track it may use. */
export function growTarget(value: number | null | undefined, max = 1, span = 100): number {
  if (value === null || value === undefined || !Number.isFinite(value) || max <= 0) return 0;
  return Math.min(span, Math.max(0, (value / max) * span));
}

/** A step-by-step walk through a diagram: node i rises, then the edge out of it flows, then node i + 1. */
export function walkSchedule(nodes: number, outputs = 0) {
  const outputStep = 60;
  // The main walk, then the outputs (if any) one step later, all inside one sequence.
  const room = MOTION.sequence - MOTION.rise - (outputs ? (outputs - 1) * outputStep : 0);
  const slots = nodes - 1 + (outputs ? 1 : 0);
  const step = slots > 0 ? Math.min(240, room / slots) : 0;
  const node = (i: number) => Math.round(i * step);
  /** The edge out of node i flows while node i + 1 starts to rise. */
  const edge = (i: number) => Math.round(i * step + step / 2);
  const outputsAt = outputs ? Math.round(nodes * step) : 0;
  const ends = [node(nodes - 1) + MOTION.rise, nodes > 1 ? edge(nodes - 2) + MOTION.flow : 0, outputs ? outputsAt + (outputs - 1) * outputStep + MOTION.rise : 0];
  return { step, node, edge, outputsAt, outputStep, end: Math.max(...ends) };
}

export type FigurePart = { text: string } | { value: number; decimals: number; text: string };

const NUMBER = /\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?/g;

/**
 * Splits a formatted line into text and numbers that can count up. A number is kept as a figure only when the ticker
 * formats it back to exactly the same text, so the final frame is always the original string.
 */
export function splitFigures(line: string): FigurePart[] {
  const parts: FigurePart[] = [];
  let last = 0;
  for (const match of line.matchAll(NUMBER)) {
    const raw = match[0];
    const at = match.index ?? 0;
    const prev = line[at - 1];
    const next = line[at + raw.length];
    // A number glued to a letter or a dash (v3, 2026-06-01, p95, 3x) is not a figure.
    if ((prev && /[A-Za-z\-_/]/.test(prev)) || (next && /[A-Za-z\-_/]/.test(next))) continue;
    const decimals = raw.includes(".") ? raw.split(".")[1].length : 0;
    const value = Number(raw.replace(/,/g, ""));
    if (!Number.isFinite(value) || formatTicker(value, decimals) !== raw) continue;
    if (at > last) parts.push({ text: line.slice(last, at) });
    parts.push({ value, decimals, text: raw });
    last = at + raw.length;
  }
  if (last < line.length) parts.push({ text: line.slice(last) });
  return parts;
}

/** The text a split line renders on its final frame: always the input. */
export const joinFigures = (parts: FigurePart[]) => parts.map((p) => p.text).join("");
