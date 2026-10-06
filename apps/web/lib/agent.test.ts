// Offline checks for /agent (spec 04 AC-08, spec 02 T6): every table matches the file it is read from. Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parse } from "yaml";
import { extract, render } from "../scripts/sync-agent.mjs";
import { AGENT_REFERENCE } from "./agent-reference.ts";
import { DIAGRAM, INVENTORY, NODE_INFO, codeSpans, inventory, nextOf, nodeInfo, ruleHasMore, ruleSummary, rulesCiting, zoneRange } from "./agent.ts";

const repo = (path: string) => readFileSync(new URL(`../../../${path}`, import.meta.url), "utf8");
const POLICIES = parse(repo("contracts/policies.yaml"));
const TOOLS_PY = repo("contracts/tools.py");
const INTAKE = repo("apps/agent/agent/intake.py");
const { policies, tools, graph, models } = AGENT_REFERENCE;

test("spec 04 AC-08: the generated reference is up to date with its sources (npm run sync:agent)", () => {
  assert.equal(readFileSync(new URL("./agent-reference.ts", import.meta.url), "utf8"), render(extract()));
});

test("spec 02 T6, spec 04 AC-08: the policy ids table is every rule of policies.yaml, in order, with its text and guardrail", () => {
  const rules = Object.entries(POLICIES.rules as Record<string, { text: string; guardrail?: string }>);
  assert.ok(rules.length > 0);
  assert.deepEqual(
    policies.rules.map((r) => [r.id, r.text, r.guardrail]),
    rules.map(([id, r]) => [id, r.text, r.guardrail ?? null]),
  );
  assert.equal(policies.version, POLICIES.version);
  assert.equal(policies.default, "deny");
  for (const id of ["POL-DEFAULT-DENY", "POL-CLOCK-UNKNOWN", "POL-CLOSE-HUMAN"]) assert.ok(policies.rules.some((r) => r.id === id), id);
});

test("spec 04 AC-08: the guardrails are policies.yaml's, with id, layer and name, and every guardrail a rule cites exists", () => {
  const yaml = POLICIES.guardrails as { id: string; layer: string; name: string; impl: string }[];
  assert.deepEqual(
    policies.guardrails.map((g) => [g.id, g.layer, g.name, g.impl]),
    yaml.map((g) => [g.id, g.layer, g.name, g.impl]),
  );
  const ids = new Set(yaml.map((g) => g.id));
  for (const rule of policies.rules) if (rule.guardrail) assert.ok(ids.has(rule.guardrail), `${rule.id} cites ${rule.guardrail}`);
  assert.deepEqual(rulesCiting("G-SES-01"), ["POL-SESSION"]);
});

test("spec 04 AC-08: the tools table is the 16 customer tools of tools.py and policies.yaml, with the read that verifies each write", () => {
  const names = tools.map((t) => t.name);
  assert.equal(names.length, 16);
  assert.deepEqual(names, POLICIES.actors.customer.tools);
  const tuple = /CUSTOMER_TOOLS[^=]*=\s*\{tool: _models\(tool\) for tool in \(([\s\S]*?)\)\}/.exec(TOOLS_PY)![1];
  assert.deepEqual(names, [...tuple.matchAll(/"(\w+)"/g)].map((m) => m[1]));
  const verified = /VERIFIED_WITH[^=]*=\s*\{([\s\S]*?)\}/.exec(TOOLS_PY)![1];
  const pairs = Object.fromEntries([...verified.matchAll(/"(\w+)":\s*"(\w+)"/g)].map((m) => [m[1], m[2]]));
  assert.deepEqual(Object.fromEntries(tools.filter((t) => t.verifiedWith).map((t) => [t.name, t.verifiedWith])), pairs);
  for (const tool of tools) {
    assert.match(tool.kind, /^[RWN]$/, tool.name);
    assert.ok(tool.purpose.length > 0, tool.name);
    assert.doesNotMatch(tool.purpose, /\(D-\d+\)|\(\d+\.\d+\.\d+\)/, tool.name);
    if (tool.kind !== "R") assert.ok(tool.verifiedWith, `${tool.name} is a write with no verifying read`);
  }
});

test("spec 04 AC-08: the graph table is the nodes of dispute_intake, each described, every node reachable and ending at END", () => {
  const tuple = /for _node in \(([\s\S]*?)\):\s*\n\s*builder\.add_node/.exec(INTAKE)![1];
  assert.deepEqual([...graph.nodes], tuple.split(",").map((n) => n.trim()).filter(Boolean));
  assert.equal(graph.name, "dispute_intake");
  assert.deepEqual(Object.keys(NODE_INFO).sort(), [...graph.nodes].sort());
  const seen = new Set<string>(["START"]);
  const queue = ["START"];
  while (queue.length) {
    for (const to of nextOf(queue.shift()!).to) {
      if (!seen.has(to)) {
        seen.add(to);
        queue.push(to);
      }
    }
  }
  for (const node of [...graph.nodes, "END"]) assert.ok(seen.has(node), `${node} is not reachable`);
  assert.deepEqual(nextOf("respond"), { to: ["END"], conditional: false });
  assert.equal(nextOf("decide").conditional, true);
});

test("spec 04 AC-08: the model inventory shows the versions of its sources", () => {
  const config = repo("packages/nick_of_time/config/__init__.py");
  assert.equal(models.s1, /^HAIKU = "([^"]+)"/m.exec(config)![1]);
  assert.equal(models.s2, /^SONNET = "([^"]+)"/m.exec(config)![1]);
  assert.match(repo("packages/nick_of_time/nlu/rules.py"), new RegExp(`ARM, VERSION = "B0", "${models.b0}"`));
  assert.match(repo("packages/nick_of_time/nlu/learned.py"), new RegExp(`B1_VERSION = "${models.b1}"`));
  const versions = INVENTORY.map((row) => row.version);
  for (const version of [models.s1, models.s2, models.b0, models.b1, `policies.yaml v${POLICIES.version}`]) {
    assert.ok(versions.includes(version), version);
  }
  const providers = POLICIES.scoring.providers as Record<string, { version: string }>;
  assert.deepEqual(
    policies.scoring.providers.map((p) => [p.name, p.version, p.decidesZone]),
    Object.entries(providers).map(([name, p]) => [name, p.version, POLICIES.scoring.deciding_sources.includes(name)]),
  );
  for (const row of INVENTORY) assert.ok(row.source.length > 0 && row.role.length > 0, row.engine);
});

test("spec 04 AC-08: the published diagram is the docs file, unchanged", () => {
  const published = readFileSync(new URL(`../public${DIAGRAM.src}`, import.meta.url));
  assert.ok(published.equals(readFileSync(new URL(`../../../${DIAGRAM.source}`, import.meta.url))));
});

test("spec 04 AC-08: a rule is summarized by its first sentence, without decision or spec references", () => {
  const text = (id: string) => policies.rules.find((r) => r.id === id)!.text;
  assert.equal(ruleSummary(text("POL-HUMAN-REQUEST")), "intent human_request → connect_person with a call request; never refused.");
  assert.equal(ruleSummary(text("POL-DEFAULT-DENY")), "no rule allows the action → deny");
  assert.equal(ruleHasMore(text("POL-HUMAN-REQUEST")), true);
  assert.equal(ruleHasMore(text("POL-INJECTION")), false);
  for (const rule of policies.rules) assert.doesNotMatch(ruleSummary(rule.text), /D-\d+|spec \d+|->/, rule.id);
  assert.deepEqual(codeSpans("Find `a` and `b`"), [
    { code: false, text: "Find " },
    { code: true, text: "a" },
    { code: false, text: " and " },
    { code: true, text: "b" },
  ]);
});

test("spec 04 AC-08: the zones read as policies.yaml states them; a null score is the human zone", () => {
  assert.deepEqual(policies.zones.map((zone) => zoneRange(zone)), ["≥ 50", "30–49", "< 30 or no score"]);
  assert.deepEqual(policies.zones.map((zone) => zoneRange(zone, "es")), ["≥ 50", "30–49", "< 30 o sin puntaje"]);
  assert.deepEqual(policies.zones.map((zone) => zoneRange(zone, "pt")), ["≥ 50", "30–49", "< 30 ou sem score"]);
});

test("spec 04 AC-08, spec 16 AC-06: every node and inventory row is described in each UI language; versions and sources do not change", () => {
  for (const locale of ["es", "pt", "en"] as const) {
    const info = nodeInfo(locale);
    assert.deepEqual(Object.keys(info).sort(), [...graph.nodes].sort(), locale);
    for (const node of graph.nodes) assert.ok(info[node].length > 0, `${locale} ${node}`);
    const rows = inventory(locale);
    assert.deepEqual(
      rows.map((r) => [r.version, r.decides, r.source]).slice(0, -2),
      INVENTORY.map((r) => [r.version, r.decides, r.source]).slice(0, -2),
      locale,
    );
    for (const row of rows) assert.ok(row.engine && row.kind && row.role, `${locale} ${row.source}`);
  }
  assert.match(inventory("es")[0].role, /por defecto deny/);
});
