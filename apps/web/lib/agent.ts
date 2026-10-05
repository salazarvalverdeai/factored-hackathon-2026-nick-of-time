// Display logic of /agent (spec 04 AC-08, spec 02 T6). The facts come from lib/agent-reference.ts, generated from
// the repo's sources; this file only adds what each graph node does and the model inventory rows, each tied to the
// file it was read from. `lib/agent.test.ts` fails when a node or a source changes without this file.
import { AGENT_REFERENCE } from "./agent-reference.ts";

export const REPO_URL = "https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/blob/main";
export const CONSTITUTION = "The LLM understands, the rules decide, the tools act, verification confirms, a person closes.";

/** The published copy of the architecture diagram and the docs file it is copied from (README.md shows the same). */
export const DIAGRAM = { src: "/agent/architecture.svg", source: "docs/assets/architecture_option_a.svg" };

export type GraphNode = (typeof AGENT_REFERENCE.graph.nodes)[number];

/** What each node of `dispute_intake` does, condensed from its docstring in apps/agent/agent/intake.py. */
export const NODE_INFO: Record<GraphNode, string> = {
  identity: "Reads the session, mode and arm from the run config the api injects; never from the customer's text.",
  greet: "First turn of a verified session: greets with the first name returned by get_customer_profile.",
  understand:
    "Language, injection flag, intent and slots with the B0 rules; below τ, arms S1/S2 ask the LLM, only in a verified session.",
  route: "Spec 02 rules 1–4 through the policy engine's screen(); the engine, not the graph, picks the branch.",
  refuse: "Deny or re-authenticate with no data and a way forward; the denial is recorded in policy_denials.",
  connect: "Registers a call request where the policy says, on the active case or a general one; never refused.",
  retrieve:
    "Finds the customer's transaction with search_transaction; for exactly one, reads its card, score, amount and any active case.",
  decide: "Runs the policy engine's decide() on tool facts only; the graph follows its result, never a rule of its own.",
  plan: "States the numbered steps before acting; in the confirm state it asks before anything is done.",
  act: "Runs only the writes decide() allowed: open_case first, then block_card when allowed, each with an idempotency key.",
  verify:
    "Reads each write's post-condition with its verifying tool: verified only with a V- id, otherwise not confirmed and escalated.",
  duplicate: "The charge already has an active case: nothing is opened; the case and its stored deadlines come from get_case.",
  clarify: "One question, nothing done: up to the allowed number of option cards, or a request for the details.",
  status: "Re-reads cards or cases in this turn and answers with tool facts and the time of the reading.",
  respond:
    "Builds the reply, the receipt and the handoff card from templates and tool results; the grounding gate drops any fact no tool returned.",
};

/** The nodes a node can go to next, in edge order; a conditional edge is chosen by the policy engine's result. */
export function nextOf(node: string): { to: string[]; conditional: boolean } {
  const edges = AGENT_REFERENCE.graph.edges.filter((e) => e.from === node);
  return { to: edges.flatMap((e) => [...e.to]), conditional: edges.some((e) => e.conditional) };
}

/** The first sentence of a policies.yaml rule text, with "->" as an arrow and decision and spec references dropped. */
export function ruleSummary(text: string): string {
  const first = /^([\s\S]*?\.)\s+(?=[A-Z[])/.exec(text)?.[1] ?? text;
  return first
    .replace(/\s*\((?:[^()]*\bD-\d+[^()]*|spec \d+[^()]*)\)/g, "")
    .replaceAll("->", "→")
    .trim();
}

/** True when a rule text says more than its first sentence, so the page offers the full rule. */
export function ruleHasMore(text: string): boolean {
  return /^[\s\S]*?\.\s+(?=[A-Z[])/.test(text);
}

/** The policy ids that cite a guardrail. */
export function rulesCiting(guardrail: string): string[] {
  return AGENT_REFERENCE.policies.rules.filter((r) => r.guardrail === guardrail).map((r) => r.id);
}

/** Splits text on `backticks` so a page can render the code parts in mono. */
export function codeSpans(text: string): { code: boolean; text: string }[] {
  return text
    .split(/(`[^`]+`)/)
    .filter(Boolean)
    .map((part) => (part.startsWith("`") ? { code: true, text: part.slice(1, -1) } : { code: false, text: part }));
}

/** A zone's score range as policies.yaml states it. */
export function zoneRange(zone: (typeof AGENT_REFERENCE.policies.zones)[number]): string {
  const range = zone.scoreMax >= 100 ? `≥ ${zone.scoreMin}` : zone.scoreMin === 0 ? `< ${zone.scoreMax + 1}` : `${zone.scoreMin}–${zone.scoreMax}`;
  return zone.includesNull ? `${range} or no score` : range;
}

export interface InventoryRow {
  engine: string;
  kind: string;
  version: string;
  role: string;
  decides: "decides" | "scores" | "advises" | "checks" | "understands";
  source: string;
}

const { policies, models, graph } = AGENT_REFERENCE;
const scoring = policies.scoring.providers.find((p) => p.name === policies.scoring.provider);

/** Models and decision engines (ADR 0021 §0, spec 18): every version is read from its source file by sync-agent. */
export const INVENTORY: InventoryRow[] = [
  {
    engine: "Policy engine",
    kind: "Rules",
    version: `policies.yaml v${policies.version}`,
    role: `Decides every action, default ${policies.default}; the LLM never reads or edits it.`,
    decides: "decides",
    source: "contracts/policies.yaml · spec 02",
  },
  {
    engine: "Regulatory clock",
    kind: "Rules (data table)",
    version: `policies.yaml v${policies.version}`,
    role: "The legal deadline per country and product, each entry with source_url and verified_on; no entry → POL-CLOCK-UNKNOWN.",
    decides: "decides",
    source: "contracts/policies.yaml regulatory_clock · ADR 0019",
  },
  {
    engine: "Fraud score",
    kind: "Bank's score (vendor)",
    version: scoring ? `${scoring.name} · ${scoring.version}` : policies.scoring.provider,
    role: "Places the case in a zone; only the deciding sources below can.",
    decides: "scores",
    source: "contracts/policies.yaml scoring",
  },
  {
    engine: "Intent classifier and injection rules (B0)",
    kind: "Rules",
    version: models.b0,
    role: `Language, intent, slots and the injection flag in the understand node; the graph loads arm ${graph.nluArm}.`,
    decides: "understands",
    source: "packages/nick_of_time/nlu/rules.py · spec 11",
  },
  {
    engine: "Intent classifier (B1)",
    kind: "TF-IDF + logistic regression",
    version: models.b1,
    role: "Learned arm measured by the spec 11 protocol; not loaded by the graph.",
    decides: "understands",
    source: "packages/nick_of_time/nlu/learned.py · spec 11",
  },
  {
    engine: "LLM arm S1",
    kind: "LLM · Amazon Bedrock",
    version: models.s1,
    role: "Intent and slots below τ in a verified session when the run's arm is S1; also the demo persona's opening message.",
    decides: "understands",
    source: "packages/nick_of_time/config · spec 15",
  },
  {
    engine: "LLM arm S2",
    kind: "LLM · Amazon Bedrock",
    version: models.s2,
    role: "The same step on the quality-ceiling model when the run's arm is S2.",
    decides: "understands",
    source: "packages/nick_of_time/config · spec 15 §4.3",
  },
  {
    engine: "Judge",
    kind: "LLM · advisory",
    version: "Claude Haiku 4.5 until the spec 15 benchmark picks the judge's model",
    role: "A second opinion for the analyst on cases in review, every reason tied to evidence; never decides or changes state.",
    decides: "advises",
    source: "packages/nick_of_time/audit/judge.py · spec 18 · spec 15 Q4",
  },
  {
    engine: "Outcome auditor",
    kind: "Deterministic checks",
    version: "A1–A10",
    role: "Re-derives each run's decision, deadline, verified actions and facts from its records; findings go to audit_findings.",
    decides: "checks",
    source: "packages/nick_of_time/audit · spec 18 §4.1",
  },
];
