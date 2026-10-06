// The /chat motion system (spec 07 AC-26, AC-27): calm and short, 150–300 ms ease-out, no glow, no bounce
// (docs/brand/BRAND.md voice). Every entrance is a `motion` prop set built here, so one rule decides it and the
// reduced-motion branch is tested offline (lib/chat-reveal.test.ts): with prefers-reduced-motion there are no animated
// props at all, everything shows at once, and the steps still show in order.

/** ease-out (a cubic-bezier close to CSS `ease-out`, without overshoot). */
export const EASE_OUT: [number, number, number, number] = [0.22, 1, 0.36, 1];
/** Gap between the parts of one agent reply, and between option cards. */
export const PART_STAGGER_S = 0.06;
export const CARD_STAGGER_S = 0.04;

/** The fixed order of an agent reply (the approved mock): steps → text → cards → chips. */
export const REPLY_PARTS = ["steps", "text", "cards", "chips"] as const;
export type ReplyPart = (typeof REPLY_PARTS)[number];

export type EnterKind = "user" | "agent" | "part" | "card" | "receipt" | "seal" | "chips" | "fade";

/** What a `motion` element receives; empty under reduced motion (no `initial`, no `animate`, no `transition`). */
export interface EnterProps {
  initial?: Record<string, number | string>;
  animate?: Record<string, number | string>;
  transition?: { duration: number; delay: number; ease: [number, number, number, number] };
}

const FROM: Record<EnterKind, Record<string, number | string>> = {
  user: { opacity: 0, y: 8, x: 12 },
  agent: { opacity: 0, y: 8, x: -12 },
  part: { opacity: 0, y: 8 },
  card: { opacity: 0, y: 8 },
  receipt: { opacity: 0, scale: 0.97 },
  seal: { opacity: 0, scale: 1.15 },
  chips: { opacity: 0, y: 6 },
  fade: { opacity: 0 },
};

const DURATION_S: Record<EnterKind, number> = { user: 0.2, agent: 0.2, part: 0.2, card: 0.2, receipt: 0.25, seal: 0.2, chips: 0.2, fade: 0.15 };

/** The entrance of one element; `delay` in seconds. Reduced motion: nothing animates. */
export function enter(kind: EnterKind, options: { reduce: boolean; delay?: number }): EnterProps {
  if (options.reduce) return {};
  const to = Object.fromEntries(Object.keys(FROM[kind]).map((k) => [k, k === "opacity" || k === "scale" ? 1 : 0]));
  return { initial: FROM[kind], animate: to, transition: { duration: DURATION_S[kind], delay: options.delay ?? 0, ease: EASE_OUT } };
}

/** The delay of a part of a reply: its place among the parts this reply has, 60 ms apart, in the fixed order. */
export function partDelay(part: ReplyPart, present: readonly ReplyPart[]): number {
  const shown = REPLY_PARTS.filter((p) => present.includes(p));
  const i = shown.indexOf(part);
  return i < 0 ? 0 : Number((i * PART_STAGGER_S).toFixed(3));
}

/** The n-th option card rises 40 ms after the one before. */
export function cardDelay(index: number, base = 0): number {
  return Number((base + index * CARD_STAGGER_S).toFixed(3));
}
