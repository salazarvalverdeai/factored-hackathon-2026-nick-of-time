// The visual views of /agent's policies, tools, guardrails and model inventory (spec 04 AC-08). Nothing here is typed
// by hand: every band, group and cell is derived from lib/agent-reference.ts (generated from contracts/ and the agent by
// scripts/sync-agent.mjs) or from lib/agent.ts's inventory, so lib/agent-visuals.test.ts binds the visuals to the same
// sources the tables come from.
import { AGENT_REFERENCE } from "./agent-reference.ts";
import { INVENTORY, NODE_INFO, ruleSummary, rulesCiting, type InventoryRow } from "./agent.ts";

const { policies, tools } = AGENT_REFERENCE;

type Rule = (typeof policies.rules)[number];
export type ZoneName = (typeof policies.zones)[number]["name"];

const ruleById = (id: string): Rule | undefined => policies.rules.find((r) => r.id === id);

/** What a rule decides: the clause after "->", up to the first ":", ";" or ",". */
export function decisionOf(text: string): string {
  const after = text.split("->")[1] ?? text;
  return after.split(/[:;,]/)[0].trim();
}

/** What a zone rule says about the card block, in its own words. */
export function blockOf(text: string): string | null {
  return /blocks and verifies|never a block|no block/.exec(text)?.[0] ?? null;
}

export interface ZoneBand {
  name: ZoneName;
  min: number;
  max: number;
  /** A missing score also lands here. */
  includesNull: boolean;
  /** Share of the 0–100 score axis, in percent. */
  share: number;
  rule: Rule;
  decision: string;
  block: string | null;
}

/** The zones from the bank's fraud score, highest first, each with the rule that decides it. */
export const ZONE_BANDS: ZoneBand[] = [...policies.zones]
  .sort((a, b) => b.scoreMin - a.scoreMin)
  .map((z) => {
    const rule = ruleById(`POL-ZONE-${z.name.toUpperCase()}`);
    if (!rule) throw new Error(`agent-visuals: no rule POL-ZONE-${z.name.toUpperCase()} in policies.yaml`);
    const max = Math.min(z.scoreMax, 100);
    return {
      name: z.name,
      min: z.scoreMin,
      max,
      includesNull: z.includesNull,
      share: max - z.scoreMin + 1,
      rule,
      decision: decisionOf(rule.text),
      block: blockOf(rule.text),
    };
  });

/** The score rules that send a case to the human zone whatever the number (no score, an LLM score, another source). */
export const SCORE_RULES = policies.rules.filter((r) => r.id.startsWith("POL-SCORE-"));

/** The amount gate and what it may touch: the approval mode of a money action, never the regulatory clock. */
export const AMOUNT_GATE = {
  rules: policies.rules.filter((r) => ["POL-AMOUNT-GATE", "POL-AMOUNT-UNKNOWN", "POL-SUPERVISED"].includes(r.id)),
  changesApprovalMode: /approval mode/.test(ruleById("POL-AMOUNT-GATE")?.text ?? ""),
  changesClock: !/never changes a deadline/.test(ruleById("POL-AMOUNT-GATE")?.text ?? ""),
  ticketAlways: ruleById("POL-TICKET-ALWAYS") ?? null,
  clockUnknown: ruleById("POL-CLOCK-UNKNOWN") ?? null,
};

export type ToolGroup = "read" | "act" | "followUp" | "notify";
type Tool = (typeof tools)[number];

export interface ToolView {
  name: string;
  kind: Tool["kind"];
  purpose: string;
  /** Writes and notifications take an idempotency key (contracts/tools.py _WriteIn). */
  idempotent: boolean;
  /** The read that confirms a write's post-condition, or null for a read. */
  verifiedWith: string | null;
}

/**
 * Tools by what they do, from their kind (spec 01 §6.3): R reads, N notifies, and a write either acts on the dispute
 * (the writes the graph's `act` node runs) or follows up on a case that already exists.
 */
export function groupOf(tool: Pick<Tool, "name" | "kind">): ToolGroup {
  if (tool.kind === "R") return "read";
  if (tool.kind === "N") return "notify";
  return new RegExp(`\\b${tool.name}\\b`).test(NODE_INFO.act) ? "act" : "followUp";
}

export const TOOL_GROUP_ORDER: ToolGroup[] = ["read", "act", "followUp", "notify"];

export const TOOL_GROUPS: { group: ToolGroup; tools: ToolView[] }[] = TOOL_GROUP_ORDER.map((group) => ({
  group,
  tools: tools
    .filter((t) => groupOf(t) === group)
    .map((t) => ({ name: t.name, kind: t.kind, purpose: t.purpose, idempotent: t.kind !== "R", verifiedWith: t.verifiedWith })),
}));

type Guardrail = (typeof policies.guardrails)[number];

/** Guardrails by layer, in the order the layers first appear in policies.yaml (input → … → operations). */
export const GUARDRAIL_LAYERS: { layer: string; guardrails: (Guardrail & { citedBy: string[] })[] }[] = [
  ...new Set(policies.guardrails.map((g) => g.layer)),
].map((layer) => ({
  layer,
  guardrails: policies.guardrails.filter((g) => g.layer === layer).map((g) => ({ ...g, citedBy: rulesCiting(g.id) })),
}));

/** What each engine does, in the order a turn uses them. */
export const TASK_ORDER: InventoryRow["decides"][] = ["understands", "scores", "decides", "checks", "advises"];

/** The model inventory as a task × engine grid: one row per task, every engine with its version. */
export const MODEL_GRID = TASK_ORDER.map((task) => ({ task, engines: INVENTORY.filter((r) => r.decides === task) })).filter(
  (row) => row.engines.length > 0,
);

/** A rule's first sentence, for a compact line under a visual. */
export const ruleLine = (rule: Rule) => ruleSummary(rule.text);
