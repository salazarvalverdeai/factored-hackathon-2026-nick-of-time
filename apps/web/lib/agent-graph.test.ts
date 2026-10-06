// Offline checks for the drawn graph of /agent (spec 04 AC-08): every node, edge and branch label of
// lib/agent-reference.ts is in the SVG model, and the labels are read from intake.py's routers. Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { BRANCH_KINDS, graphOf } from "../scripts/sync-agent.mjs";
import { AGENT_REFERENCE } from "./agent-reference.ts";
import { GRAPH_VIEW, KIND_TEXT, ariaLabelOf, infoOf, linksOf } from "./agent-graph.ts";

const INTAKE = readFileSync(new URL("../../../apps/agent/agent/intake.py", import.meta.url), "utf8");
const { graph } = AGENT_REFERENCE;
const pairs = graph.edges.flatMap((e) => e.to.map((to) => ({ from: e.from, to, conditional: e.conditional })));
const key = (e: { from: string; to: string }) => `${e.from}->${e.to}`;

test("spec 04 AC-08: every node of agent-reference, START and END is drawn once", () => {
  const drawn = GRAPH_VIEW.nodes.map((n) => n.id);
  assert.deepEqual([...drawn].sort(), ["START", ...graph.nodes, "END"].sort());
  for (const n of GRAPH_VIEW.nodes) assert.ok(infoOf(n.id).length > 0, `${n.id} has no one-liner`);
});

test("spec 04 AC-08: every edge of agent-reference is drawn once, and no other", () => {
  assert.deepEqual(GRAPH_VIEW.edges.map(key).sort(), pairs.map(key).sort());
  for (const e of GRAPH_VIEW.edges) assert.match(e.path, /^M[\d.]+ [\d.]+( [LC][\d. ]+)+$/, key(e));
});

test("spec 04 AC-08: every branch edge carries a label, a kind and its condition; an unconditional edge carries none", () => {
  for (const p of pairs) {
    const drawn = GRAPH_VIEW.edges.find((e) => key(e) === key(p))!;
    const branch = graph.branches.find((b) => key(b) === key(p));
    if (p.conditional) {
      assert.ok(branch && branch.label && branch.when, `${key(p)} has no branch label`);
      assert.equal(drawn.label, branch.label);
      assert.equal(drawn.kind, branch.kind);
      assert.ok(drawn.labelBox, `${key(p)} has no label box`);
      assert.ok(Object.keys(KIND_TEXT).includes(branch.kind));
      assert.ok(ariaLabelOf(p.from).includes(`${p.to} when ${branch.label}`), `${p.from}'s accessible name lacks ${p.to}`);
    } else {
      assert.equal(branch, undefined, key(p));
      assert.equal(drawn.label, null, key(p));
      assert.equal(drawn.labelBox, null, key(p));
    }
  }
  assert.equal(graph.branches.length, pairs.filter((p) => p.conditional).length);
});

test("spec 04 AC-08: the labels are the router's own keys: the BRANCH dict, decide's lookup and the ternaries' conditions", () => {
  const BRANCH = Object.fromEntries([...(/^BRANCH = \{([^}]*)\}/m.exec(INTAKE)![1]).matchAll(/"(\w+)":\s*"(\w+)"/g)].map((m) => [m[1], m[2]]));
  for (const [decision, node] of Object.entries(BRANCH)) {
    assert.ok(graph.branches.find((b) => b.from === "route" && b.to === node)!.label.split(" | ").includes(decision), decision);
  }
  const label = (from: string, to: string) => graph.branches.find((b) => b.from === from && b.to === to)?.label;
  assert.equal(label("decide", "clarify"), "ask");
  assert.equal(label("decide", "refuse"), "deny");
  assert.equal(label("retrieve", "respond"), "read_failed");
  assert.equal(label("plan", "respond"), "decision = confirm");
  assert.equal(label("duplicate", "connect"), "request_call");
  assert.match(graph.branches.find((b) => b.from === "decide" && b.to === "clarify")!.when, /^decide\(\) = ask$/);
  assert.equal(graph.branches.find((b) => b.from === "route" && b.to === "connect")!.kind, "policy");
  assert.equal(graph.branches.find((b) => b.from === "retrieve" && b.to === "decide")!.kind, "tool");
});

test("spec 04 AC-08: a router change changes the labels, and a router the generator cannot read stops the sync", () => {
  const added = INTAKE.replace(/^(BRANCH = \{)/m, '$1"escalate": "connect", ');
  const route = graphOf(added).branches.find((b: { from: string; to: string }) => b.from === "route" && b.to === "connect");
  assert.equal(route.label, "escalate | connect_person");
  assert.throws(() => graphOf(INTAKE.replace('"respond" if state.get("read_failed")', '"respond" if state.get("lookup_failed")')), /no kind/);
  assert.throws(() => graphOf(INTAKE.replace('"connect_person": "connect"', '"connect_person": "status_typo"')), /not in its edge list/);
  assert.ok(Object.values(BRANCH_KINDS).flat().length > 0);
});

test("spec 04 AC-08: the layout keeps every node and label inside the drawing, nodes of a rank apart, START first and END last", () => {
  const { width, height, nodes } = GRAPH_VIEW;
  for (const n of nodes) {
    assert.ok(n.x - n.w / 2 >= 0 && n.x + n.w / 2 <= width && n.y - n.h / 2 >= 0 && n.y + n.h / 2 <= height, n.id);
  }
  for (const e of GRAPH_VIEW.edges) {
    if (e.labelBox) assert.ok(e.labelBox.x >= 0 && e.labelBox.x + e.labelBox.w <= width && e.labelBox.y + e.labelBox.h <= height, key(e));
  }
  for (const a of nodes) {
    for (const b of nodes) {
      if (a.id < b.id && a.y === b.y) assert.ok(Math.abs(a.x - b.x) >= (a.w + b.w) / 2, `${a.id} overlaps ${b.id}`);
    }
  }
  assert.equal(nodes[0].id, "START");
  assert.equal(nodes.at(-1)!.id, "END");
  for (const e of GRAPH_VIEW.edges) {
    const [from, to] = [nodes.find((n) => n.id === e.from)!, nodes.find((n) => n.id === e.to)!];
    assert.ok(to.y > from.y, `${key(e)} does not point down`);
  }
  assert.deepEqual(linksOf("respond").out.map((e) => e.to), ["END"]);
});
