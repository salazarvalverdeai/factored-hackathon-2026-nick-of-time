// Offline checks for /agent's visual views (spec 04 AC-08): the zone diagram, the tool groups, the guardrail list and
// the model grid come from the same generated reference as the tables, and that reference is bound to its sources.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parse } from "yaml";
import { AGENT_REFERENCE } from "./agent-reference.ts";
import { INVENTORY } from "./agent.ts";
import {
  AMOUNT_GATE,
  GUARDRAIL_LAYERS,
  MODEL_GRID,
  SCORE_RULES,
  TOOL_GROUPS,
  ZONE_BANDS,
  blockOf,
  decisionOf,
  groupOf,
} from "./agent-visuals.ts";

const repo = (path: string) => readFileSync(new URL(`../../../${path}`, import.meta.url), "utf8");
const POLICIES = parse(repo("contracts/policies.yaml"));
const TOOLS_PY = repo("contracts/tools.py");
const INTAKE = repo("apps/agent/agent/intake.py");
const { policies, tools } = AGENT_REFERENCE;

test("spec 04 AC-08: the zone bands are policies.yaml's zones, highest first, each with its POL-ZONE rule", () => {
  assert.deepEqual(
    ZONE_BANDS.map((b) => [b.name, b.min, b.max, b.includesNull]),
    Object.entries(POLICIES.zones as Record<string, { score_min: number; score_max: number; include_null?: boolean }>)
      .map(([name, z]) => [name, z.score_min, Math.min(z.score_max, 100), Boolean(z.include_null)])
      .sort((a, b) => (b[1] as number) - (a[1] as number)),
  );
  assert.deepEqual(ZONE_BANDS.map((b) => b.rule.id), ["POL-ZONE-HIGH", "POL-ZONE-MEDIUM", "POL-ZONE-HUMAN"]);
  assert.deepEqual(ZONE_BANDS.map((b) => [b.min, b.max]), [[50, 100], [30, 49], [0, 29]], "high ≥ 50 · medium 30–49 · human < 30");
  assert.ok(ZONE_BANDS.find((b) => b.name === "human")!.includesNull, "no score is zone human");
  for (const b of ZONE_BANDS) assert.ok(b.share > 0 && b.decision.length > 0 && b.block, b.name);
  assert.equal(ZONE_BANDS.reduce((s, b) => s + b.share, 0), 101, "the bands cover 0–100 with no gap");
  assert.deepEqual(ZONE_BANDS.map((b) => b.block), ["blocks and verifies", "never a block", "no block"]);
  assert.equal(decisionOf("x -> block_and_open_case: the high zone"), "block_and_open_case");
  assert.equal(blockOf("nothing here"), null);
});

test("spec 04 AC-08: the amount gate changes only the approval mode, never the clock; a case opens in every zone", () => {
  assert.equal(AMOUNT_GATE.changesApprovalMode, true);
  assert.equal(AMOUNT_GATE.changesClock, false);
  assert.ok(AMOUNT_GATE.ticketAlways, "POL-TICKET-ALWAYS");
  assert.ok(AMOUNT_GATE.clockUnknown, "POL-CLOCK-UNKNOWN");
  assert.deepEqual(AMOUNT_GATE.rules.map((r) => r.id), ["POL-AMOUNT-GATE", "POL-AMOUNT-UNKNOWN", "POL-SUPERVISED"]);
  assert.match(POLICIES.rules["POL-AMOUNT-GATE"].text, /never changes a deadline/);
  assert.deepEqual(SCORE_RULES.map((r) => r.id).sort(), Object.keys(POLICIES.rules).filter((id) => id.startsWith("POL-SCORE-")).sort());
});

test("spec 04 AC-08: every tool is in exactly one group, from its kind: R read, N notify, W act or follow up", () => {
  const grouped = TOOL_GROUPS.flatMap((g) => g.tools.map((t) => t.name));
  assert.deepEqual([...grouped].sort(), tools.map((t) => t.name).sort());
  for (const t of tools) {
    const group = groupOf(t);
    if (t.kind === "R") assert.equal(group, "read", t.name);
    else if (t.kind === "N") assert.equal(group, "notify", t.name);
    else assert.ok(group === "act" || group === "followUp", t.name);
  }
  const act = TOOL_GROUPS.find((g) => g.group === "act")!.tools.map((t) => t.name);
  assert.deepEqual(act.sort(), ["block_card", "open_case"]);
  const writing = Object.keys(JSON.parse(/^WRITING = (\{[^}]*\})/m.exec(INTAKE)![1]));
  assert.deepEqual(act, [...writing].sort(), "the act group is the writes intake.py's act node runs (WRITING)");
  for (const g of TOOL_GROUPS) assert.ok(g.tools.length > 0, g.group);
});

test("spec 04 AC-08: idempotency and post-condition icons follow contracts/tools.py", () => {
  const writeIn = new Set([...TOOLS_PY.matchAll(/^class (\w+)In\(_WriteIn\)/gm)].map((m) => m[1]));
  const pascal = (name: string) => name.split("_").map((w) => w[0].toUpperCase() + w.slice(1)).join("");
  for (const t of TOOL_GROUPS.flatMap((g) => g.tools)) {
    assert.equal(t.idempotent, writeIn.has(pascal(t.name)), `${t.name}: idempotency key in tools.py`);
    assert.equal(Boolean(t.verifiedWith), t.kind !== "R", `${t.name}: a write is verified by a read`);
    if (t.verifiedWith) assert.equal(tools.find((x) => x.name === t.verifiedWith)?.kind, "R", t.verifiedWith);
  }
});

test("spec 04 AC-08: the guardrail list is every guardrail once, grouped by its layer in policies.yaml order", () => {
  const listed = GUARDRAIL_LAYERS.flatMap((l) => l.guardrails.map((g) => g.id));
  assert.deepEqual(listed, policies.guardrails.map((g) => g.id));
  for (const l of GUARDRAIL_LAYERS) for (const g of l.guardrails) assert.equal(g.layer, l.layer);
  assert.deepEqual(GUARDRAIL_LAYERS.map((l) => l.layer), ["input", "session", "tools", "policy", "output", "operations"]);
});

test("spec 04 AC-08: the model grid holds every inventory engine once, by task, with its version", () => {
  const cells = MODEL_GRID.flatMap((r) => r.engines);
  assert.deepEqual(cells.map((c) => c.engine).sort(), INVENTORY.map((r) => r.engine).sort());
  for (const r of MODEL_GRID) for (const e of r.engines) assert.equal(e.decides, r.task);
  assert.ok(cells.some((c) => c.version === AGENT_REFERENCE.models.s1));
  assert.ok(cells.every((c) => c.version.length > 0));
});
