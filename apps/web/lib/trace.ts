// The /chat trace panel (spec 07 AC-03, AC-08): what the agent did on the last turn, built only from what the web
// receives — the api's customer turn (D-013: no zone, no score, no policy ids, no internal trace) and the progress
// labels streamed during the run. Constitution #4: an action is "verified" only when the api's action record says so.
import type { TraceStep } from "./types.ts";

export interface TraceProgress {
  step: string;
  label: string;
  state?: string;
}

/** The fields of the api's `CustomerTurn` (packages/nick_of_time/contracts.py) the trace reads. */
export interface TraceTurn {
  decision?: string | null;
  intent?: string | null;
  case_id?: string | null;
  plan?: string[];
  progress?: TraceProgress[];
  actions?: { tool: string; state: string; verification_id?: string | null; read_at?: string | null }[];
  guardrails_triggered?: string[];
  denials?: { guardrail_id?: string | null; detail: string }[];
}

/**
 * Plain-language names of the guardrails of `contracts/policies.yaml` (`guardrails:`), for the jury. The id stays
 * beside the name; a policy id (POL-…) is never shown (spec 07 AC-03). `lib/trace.test.ts` checks the ids match.
 */
export const GUARDRAIL_LABELS: Record<string, string> = {
  "G-IN-01": "Prompt injection detected",
  "G-IN-02": "Customer-supplied data used only to search",
  "G-IN-03": "Language or ambiguity: asked to clarify",
  "G-IN-04": "Personal data or out of scope",
  "G-SES-01": "Identity and session check",
  "G-SES-02": "Another customer's data refused",
  "G-TOOL-01": "Allowed tools and strict schemas",
  "G-TOOL-02": "Controlled write: approval, idempotency, post-condition",
  "G-POL-01": "Default deny: no rule allows it",
  "G-OUT-01": "Grounding: an unverified fact was dropped",
  "G-OUT-02": "Only verified results are stated",
  "G-OUT-03": "Leak filter on the answer",
  "G-OUT-04": "Tone and abstention",
  "G-OPS-01": "Budget cap or retries",
  "G-OPS-02": "Immutable audit",
};

/** A guardrail's plain name; an unknown id is shown as words, never dropped. */
export function guardrailLabel(id: string): string {
  return GUARDRAIL_LABELS[id] ?? id.replaceAll("_", " ");
}

/** The engine's decision (`Decision` in contracts.py) in plain words. */
export const DECISION_LABELS: Record<string, string> = {
  block_and_open_case: "Block the card and open a case",
  confirm: "State the plan and wait for the customer's yes",
  ask: "Ask the customer to clarify",
  handoff: "Hand the case to a person",
  answer_status: "Answer from a fresh system read",
  connect_person: "Connect the customer with a person",
  deny: "Refuse the request",
  reauthenticate: "Ask the customer to verify again",
  escalate_unconfirmed_action: "Escalate: an action was not confirmed",
};

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

const STATE_WORDS: Record<string, string> = {
  in_progress: "in progress",
  requested: "requested",
  verified: "verified",
  not_confirmed: "not confirmed",
};

/**
 * The turn's steps in order: the labels the run streamed (each ran), what the agent understood, what the rules
 * decided, the plan, each action with its state and verification, the verification summary, then any denial.
 */
export function traceFromTurn(turn: TraceTurn, streamed: TraceProgress[] = []): TraceStep[] {
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
  if (turn.intent) steps.push({ step: "understand", result: `Request: ${turn.intent.replaceAll("_", " ")}`, kind: "ok" });
  if (turn.decision) {
    steps.push({
      step: "decide",
      result: DECISION_LABELS[turn.decision] ?? turn.decision.replaceAll("_", " "),
      kind: turn.decision === "deny" ? "deny" : "ok",
    });
  }
  if (turn.plan?.length) steps.push({ step: "plan", result: turn.plan.join("\n"), kind: "ok" });
  const actions = turn.actions ?? [];
  for (const a of actions) {
    const words = STATE_WORDS[a.state] ?? a.state.replaceAll("_", " ");
    const proof = a.verification_id ? ` · ${a.verification_id}` : "";
    steps.push({ step: a.tool, result: `${words}${proof}`, kind: kindOf(a.state) });
  }
  if (actions.length) {
    const verified = actions.filter((a) => a.state === "verified").length;
    const failed = actions.some((a) => a.state === "not_confirmed");
    steps.push({
      step: "verify",
      result: `${verified} of ${actions.length} confirmed by re-reading the system`,
      kind: verified === actions.length ? "verified" : failed ? "not_confirmed" : "accepted",
    });
  }
  if (turn.case_id) steps.push({ step: "case", result: turn.case_id, kind: "ok" });
  for (const d of turn.denials ?? []) {
    steps.push({ step: "deny", result: d.guardrail_id ? `${guardrailLabel(d.guardrail_id)}: ${d.detail}` : d.detail, kind: "deny" });
  }
  return steps;
}
