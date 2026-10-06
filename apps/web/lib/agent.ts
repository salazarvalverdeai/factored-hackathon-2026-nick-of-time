// Display logic of /agent (spec 04 AC-08, spec 02 T6). The facts come from lib/agent-reference.ts, generated from
// the repo's sources; this file only adds what each graph node does and the model inventory rows, each tied to the
// file it was read from. `lib/agent.test.ts` fails when a node or a source changes without this file. The prose is
// in messages/agent.ts in the three UI languages (spec 16 AC-06); identifiers, versions and sources are not translated.
import { agent as agentMessages } from "../messages/agent.ts";
import { AGENT_REFERENCE } from "./agent-reference.ts";
import { type Locale, translator } from "./i18n.ts";

export const REPO_URL = "https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/blob/main";
export const CONSTITUTION = agentMessages.en.constitution;

/** The published copy of the architecture diagram and the docs file it is copied from (README.md shows the same). */
export const DIAGRAM = { src: "/agent/architecture.svg", source: "docs/assets/architecture_option_a.svg" };

export type GraphNode = (typeof AGENT_REFERENCE.graph.nodes)[number];

/** What each node of `dispute_intake` does, condensed from its docstring in apps/agent/agent/intake.py. */
export function nodeInfo(locale: Locale = "en"): Record<GraphNode, string> {
  return agentMessages[locale].nodes;
}
export const NODE_INFO: Record<GraphNode, string> = nodeInfo("en");

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

/** A zone's score range as policies.yaml states it; the null-score note follows the UI locale. */
export function zoneRange(zone: (typeof AGENT_REFERENCE.policies.zones)[number], locale: Locale = "en"): string {
  const range = zone.scoreMax >= 100 ? `≥ ${zone.scoreMin}` : zone.scoreMin === 0 ? `< ${zone.scoreMax + 1}` : `${zone.scoreMin}–${zone.scoreMax}`;
  return zone.includesNull ? translator(locale)("agent.policies.orNoScore", { range }) : range;
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
export function inventory(locale: Locale = "en"): InventoryRow[] {
  const m = agentMessages[locale].inventory;
  const t = translator(locale);
  const yaml = `policies.yaml v${policies.version}`;
  const row = (key: keyof typeof m, rest: Pick<InventoryRow, "version" | "decides" | "source">, role?: string): InventoryRow => ({
    engine: m[key].engine,
    kind: m[key].kind,
    version: rest.version,
    role: role ?? m[key].role,
    decides: rest.decides,
    source: rest.source,
  });
  return [
    row("policy", { version: yaml, decides: "decides", source: "contracts/policies.yaml · spec 02" }, t("agent.inventory.policy.role", { default: policies.default })),
    row("clock", { version: yaml, decides: "decides", source: "contracts/policies.yaml regulatory_clock · ADR 0019" }),
    row("fraud", {
      version: scoring ? `${scoring.name} · ${scoring.version}` : policies.scoring.provider,
      decides: "scores",
      source: "contracts/policies.yaml scoring",
    }),
    row("b0", { version: models.b0, decides: "understands", source: "packages/nick_of_time/nlu/rules.py · spec 11" }, t("agent.inventory.b0.role", { arm: graph.nluArm })),
    row("b1", { version: models.b1, decides: "understands", source: "packages/nick_of_time/nlu/learned.py · spec 11" }),
    row("s1", { version: models.s1, decides: "understands", source: "packages/nick_of_time/config · spec 15" }),
    row("s2", { version: models.s2, decides: "understands", source: "packages/nick_of_time/config · spec 15 §4.3" }),
    row("judge", { version: m.judge.version, decides: "advises", source: "packages/nick_of_time/audit/judge.py · spec 18 · spec 15 Q4" }),
    row("auditor", { version: "A1–A10", decides: "checks", source: "packages/nick_of_time/audit · spec 18 §4.1" }),
  ];
}
export const INVENTORY: InventoryRow[] = inventory("en");
