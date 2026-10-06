// The paced reveal of a chat turn (spec 07 AC-16 to AC-18): display only, and honest. The steps did happen in the order
// shown; a fast backend only makes them flash by, so each step stays on screen for a minimum dwell, and the reply is
// revealed word by word. Nothing is invented or reordered, and `prefers-reduced-motion` shows everything at once.
// Pure logic with an injectable clock, so the timing rules are tested with fake timers (lib/chat-reveal.test.ts).
import { stableMarkdown } from "./chat-stream.ts";
import type { ActionCard, ToolEvent } from "./chat-stream.ts";
import { CHAT_STRINGS } from "./chat-strings.ts";
import type { Language } from "./types.ts";

/** Minimum time a step shows as the running one before its result replaces it. */
export const STEP_DWELL_MS = 350;
/** Reveal speed of the reply text. */
export const WORDS_PER_SECOND = 35;

// --- the pacer ---------------------------------------------------------------------------------------------------

export interface PacerClock {
  now: () => number;
  setTimeout: (fn: () => void, ms: number) => unknown;
  clearTimeout: (handle: unknown) => void;
}

const realClock: PacerClock = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

/**
 * Releases items in the order they were pushed, never sooner than `gapFor(item)` ms after the previous release. With
 * `instant` every item is released as soon as it is pushed (reduced motion).
 */
export class Pacer<T> {
  private queue: T[] = [];
  private last = Number.NEGATIVE_INFINITY;
  private timer: unknown = null;
  private stopped = false;
  private readonly clock: PacerClock;
  private readonly instant: boolean;
  private readonly onRelease: (item: T) => void;
  private readonly gapFor: (item: T) => number;

  constructor(onRelease: (item: T) => void, gapFor: (item: T) => number, options: { clock?: PacerClock; instant?: boolean } = {}) {
    this.onRelease = onRelease;
    this.gapFor = gapFor;
    this.clock = options.clock ?? realClock;
    this.instant = options.instant ?? false;
  }

  push(item: T): void {
    if (this.stopped) return;
    this.queue.push(item);
    if (this.timer === null) this.pump();
  }

  /** Items waiting for their turn. */
  get pending(): number {
    return this.queue.length;
  }

  /** Stops for good: nothing queued is released (a cancelled or replaced turn). */
  cancel(): void {
    this.stopped = true;
    this.queue = [];
    if (this.timer !== null) this.clock.clearTimeout(this.timer);
    this.timer = null;
  }

  private pump(): void {
    while (!this.stopped && this.queue.length > 0) {
      const next = this.queue[0];
      const wait = this.instant ? 0 : Math.max(0, this.last + this.gapFor(next) - this.clock.now());
      if (wait > 0) {
        this.timer = this.clock.setTimeout(() => {
          this.timer = null;
          this.pump();
        }, wait);
        return;
      }
      this.queue.shift();
      this.last = this.clock.now();
      this.onRelease(next);
    }
  }
}

/** What a turn streams, in arrival order: a step label, a tool call, a text chunk, and finally the whole reply. */
export type TurnFrame<R> =
  | { kind: "progress"; label: string }
  | { kind: "tool"; event: ToolEvent }
  | { kind: "text"; delta: string; messageId: string }
  | { kind: "reply"; reply: R };

/**
 * The dwell rule: a step's result (done or failed) waits until the step has shown as running for STEP_DWELL_MS; a new
 * progress label waits the same after the previous one. A new step, text and the final reply follow at once.
 */
export function frameGap<R>(frame: TurnFrame<R>): number {
  if (frame.kind === "tool") return frame.event.status === "running" ? 0 : STEP_DWELL_MS;
  if (frame.kind === "progress") return STEP_DWELL_MS;
  return 0;
}

// --- the word reveal ---------------------------------------------------------------------------------------------

const LIST_MARK = /^(?:[-*+]|\d+[.)])\s+$/;

/** Words with the whitespace after them; a list marker ("- ", "1. ") travels with the word after it. */
export function wordTokens(text: string): string[] {
  const raw = text.match(/^\s+|\S+\s*/g) ?? [];
  const out: string[] = [];
  for (let i = 0; i < raw.length; i++) {
    if (LIST_MARK.test(raw[i]) && i + 1 < raw.length) {
      out.push(raw[i] + raw[i + 1]);
      i++;
    } else out.push(raw[i]);
  }
  return out;
}

export function wordCount(text: string): number {
  return wordTokens(text).length;
}

/** How many words show after `elapsedMs` at `rate` words per second. */
export function wordsAt(elapsedMs: number, rate = WORDS_PER_SECOND): number {
  return Math.max(0, Math.floor((elapsedMs * rate) / 1000));
}

/**
 * The first `n` words of a markdown reply, safe to render: a mark or a link that is not closed yet is held back
 * (`stableMarkdown`), so the customer never sees half a `**` or a bare `[`. All words: the text as it is.
 */
export function revealMarkdown(text: string, n: number): string {
  const tokens = wordTokens(text);
  if (n >= tokens.length) return text;
  return stableMarkdown(tokens.slice(0, Math.max(0, n)).join("").trimEnd()).trimEnd();
}

// --- the one-line summary of the steps ---------------------------------------------------------------------------

type Phrase = { key: string; rank: number; words: Record<Language, string> };

const action = (t: ToolEvent): ActionCard | undefined => t.cards.find((c): c is ActionCard => c.type === "action");

/** What a finished step did, in the past tense; an action that was not verified never reads as done (constitution #4). */
function phraseOf(t: ToolEvent): Phrase | null {
  const failed = t.status === "failed";
  const state = action(t)?.state;
  switch (t.step) {
    case "search_transaction":
    case "list_recent_transactions":
      return { key: "charges", rank: 1, words: { es: "revisó tus cargos", pt: "revisou suas cobranças" } };
    case "evaluate_policy":
      return { key: "rule", rank: 2, words: { es: "aplicó la regla", pt: "aplicou a regra" } };
    case "block_card":
      if (failed || state === "not_confirmed") return { key: "block", rank: 3, words: { es: "intentó bloquear la tarjeta", pt: "tentou bloquear o cartão" } };
      if (state === "verified") return { key: "block", rank: 3, words: { es: "bloqueó la tarjeta", pt: "bloqueou o cartão" } };
      return { key: "block", rank: 3, words: { es: "pidió el bloqueo", pt: "pediu o bloqueio" } };
    case "open_case":
    case "get_case":
      if (failed) return { key: "case", rank: 4, words: { es: "intentó abrir el caso", pt: "tentou abrir o caso" } };
      return { key: "case", rank: 4, words: { es: "abrió el caso", pt: "abriu o caso" } };
    case "request_call":
      return { key: "call", rank: 5, words: { es: "pidió una llamada", pt: "pediu uma ligação" } };
    case "compute_deadline":
      return { key: "deadline", rank: 6, words: { es: "calculó el plazo", pt: "calculou o prazo" } };
    case "get_case_status":
      return { key: "status", rank: 7, words: { es: "leyó el estado del caso", pt: "leu a situação do caso" } };
    default:
      return null;
  }
}

function joinPhrases(parts: string[], lang: Language): string {
  if (parts.length === 0) return "";
  const and = lang === "es" ? " y " : " e ";
  const text = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")}${and}${parts[parts.length - 1]}`;
  return text[0].toUpperCase() + text.slice(1);
}

/**
 * The collapsed line of "how I decided": what the steps did, then how many there were, e.g. "Revisó tus cargos, aplicó
 * la regla y abrió el caso · 4 pasos". At most four phrases, the most consequential kept, in the order they happened.
 */
export function stepsSummary(tools: readonly ToolEvent[], lang: Language): string {
  const seen = new Map<string, Phrase & { order: number }>();
  tools.forEach((t, order) => {
    const p = phraseOf(t);
    if (p && !seen.has(p.key)) seen.set(p.key, { ...p, order });
  });
  const kept = [...seen.values()].sort((a, b) => a.rank - b.rank).slice(0, 4).sort((a, b) => a.order - b.order);
  const failed = tools.filter((t) => t.status === "failed").length;
  const count = CHAT_STRINGS.steps[lang](tools.length);
  const head = joinPhrases(kept.map((p) => p.words[lang]), lang) || CHAT_STRINGS.howDecided[lang];
  return [head, count, failed ? CHAT_STRINGS.notCompleted[lang](failed) : null].filter(Boolean).join(" · ");
}
