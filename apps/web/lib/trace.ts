// The /chat trace panel (spec 07 AC-03, AC-08): what the agent did on the last turn, built only from what the web
// receives — the api's customer turn (D-013: no zone, no score, no policy ids, no internal trace) and the progress
// labels streamed during the run. Constitution #4: an action is "verified" only when the api's action record says so.
// Every label is in the conversation language (es or pt), never the UI locale: the panel is customer-visible and the
// streamed labels already arrive in that language (spec 07 AC-03, spec 16 AC-06). The words live in messages/trace.ts.
import { trace as TRACE } from "../messages/trace.ts";
import { isLocale, type Locale, translator } from "./i18n.ts";
import type { TraceStep } from "./types.ts";

export interface TraceProgress {
  step: string;
  label: string;
  state?: string;
}

/** The fields of the api's `CustomerTurn` (packages/nick_of_time/contracts.py) the trace reads. */
export interface TraceTurn {
  /** The session's conversation language: the trace speaks it. */
  language?: string | null;
  decision?: string | null;
  intent?: string | null;
  case_id?: string | null;
  plan?: string[];
  progress?: TraceProgress[];
  actions?: { tool: string; state: string; verification_id?: string | null; read_at?: string | null }[];
  guardrails_triggered?: string[];
  denials?: { guardrail_id?: string | null; detail: string }[];
}

type Words = Record<"step" | "decision" | "state" | "intent" | "guardrail" | "kind", Record<string, string>>;
const dict = (lang: Locale) => TRACE[lang] as unknown as Words;
const pick = (map: Record<string, string>, key: string): string | undefined => (Object.hasOwn(map, key) ? map[key] : undefined);
const asWords = (key: string) => key.replaceAll("_", " ");

/**
 * The guardrails of `contracts/policies.yaml` (`guardrails:`) the trace names in plain words. The id stays beside the
 * name; a policy id (POL-…) is never shown (spec 07 AC-03). `lib/trace.test.ts` checks the ids match.
 */
export const GUARDRAIL_IDS: readonly string[] = Object.keys(TRACE.en.guardrail);

/** A guardrail's plain name in `lang`; an unknown id is shown as words, never dropped. */
export function guardrailLabel(id: string, lang: Locale): string {
  return pick(dict(lang).guardrail, id) ?? asWords(id);
}

/** The engine's decision (`Decision` in contracts.py) in plain words in `lang`. */
export function decisionLabel(decision: string, lang: Locale): string {
  return pick(dict(lang).decision, decision) ?? asWords(decision);
}

/** A row's badge in `lang` ("verified ✓", "requested"…): "requested" is never shown as verified (constitution #4). */
export function kindLabel(kind: TraceStep["kind"], lang: Locale): string {
  return pick(dict(lang).kind, kind) ?? asWords(kind);
}

/**
 * One trace row as the panel shows it (design pass 1, finding 4): a known step leads with its plain name in `lang` and
 * keeps the result as detail; a streamed progress step (`reading_message`, `deciding`…) leads with the label it
 * streamed (already in the conversation language), and its node key is dropped. "verify block_card" is the step
 * `verify_block_card`. The panel always passes the session's language; English is only the default for callers that
 * predate it.
 */
export function traceRow(t: TraceStep, lang: Locale = "en"): { title: string; detail: string | null } {
  const title = pick(dict(lang).step, t.step.replaceAll(" ", "_"));
  if (title) return { title, detail: t.result || null };
  return { title: t.result || asWords(t.step), detail: null };
}

/** The four action states of spec 04 AC-18 as trace kinds: "requested" is shown as accepted, never as verified. */
export function kindOf(state: string | undefined): TraceStep["kind"] {
  switch (state) {
    case "verified":
      return "verified";
    case "requested":
      return "accepted";
    case "not_confirmed":
      return "not_confirmed";
    case "in_progress":
      return "in_progress";
    default:
      return "ok";
  }
}

/**
 * The turn's steps in order: the labels the run streamed (each ran), what the agent understood, what the rules
 * decided, the plan, each action with its state and verification, the verification summary, then any denial. Every
 * word is in `lang`, by default the turn's own conversation language (spec 07 AC-03, spec 16 AC-06).
 */
export function traceFromTurn(
  turn: TraceTurn,
  streamed: TraceProgress[] = [],
  lang: Locale = isLocale(turn.language) ? turn.language : "es",
): TraceStep[] {
  const t = translator(lang);
  const words = dict(lang);
  const steps: TraceStep[] = [];
  const seen = new Set<string>();
  // A streamed label is in progress while the run goes; once the turn ended, the step ran ("done"). A label the turn
  // itself carries keeps its state, so a write it reports as verified or requested says so.
  for (const p of [...(turn.progress ?? []), ...streamed]) {
    if (seen.has(p.step)) continue;
    seen.add(p.step);
    const kind = p.state && p.state !== "in_progress" ? kindOf(p.state) : "ok";
    steps.push({ step: p.step, result: p.label, kind });
  }
  if (turn.intent) {
    const intent = pick(words.intent, turn.intent) ?? asWords(turn.intent);
    steps.push({ step: "understand", result: t("trace.request", { intent }), kind: "ok" });
  }
  if (turn.decision) {
    steps.push({ step: "decide", result: decisionLabel(turn.decision, lang), kind: turn.decision === "deny" ? "deny" : "ok" });
  }
  if (turn.plan?.length) steps.push({ step: "plan", result: turn.plan.join("\n"), kind: "ok" });
  const actions = turn.actions ?? [];
  for (const a of actions) {
    const state = pick(words.state, a.state) ?? asWords(a.state);
    const proof = a.verification_id ? ` · ${a.verification_id}` : "";
    steps.push({ step: a.tool, result: `${state}${proof}`, kind: kindOf(a.state) });
  }
  if (actions.length) {
    const verified = actions.filter((a) => a.state === "verified").length;
    const failed = actions.some((a) => a.state === "not_confirmed");
    steps.push({
      step: "verify",
      result: t("trace.verifySummary", { verified, total: actions.length }),
      kind: verified === actions.length ? "verified" : failed ? "not_confirmed" : "accepted",
    });
  }
  if (turn.case_id) steps.push({ step: "case", result: turn.case_id, kind: "ok" });
  for (const d of turn.denials ?? []) {
    steps.push({ step: "deny", result: d.guardrail_id ? `${guardrailLabel(d.guardrail_id, lang)}: ${d.detail}` : d.detail, kind: "deny" });
  }
  return steps;
}
