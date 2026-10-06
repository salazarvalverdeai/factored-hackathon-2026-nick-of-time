// Offline checks for the console's agent path (spec 08 AC-23): every id the mapping can emit is a node of
// lib/agent-reference.ts, a path walks only real edges, and a node the case events cannot pin is left out.
import assert from "node:assert/strict";
import test from "node:test";
import { AGENT_REFERENCE } from "./agent-reference.ts";
import { GRAPH_IDS, PINS, casePath, forcedAfter, forcedBefore } from "./console-path.ts";

const EDGES = new Set(AGENT_REFERENCE.graph.edges.flatMap((e) => e.to.map((to) => `${e.from}->${to}`)));
const ev = (type: string, actor = "agent") => ({ type, actor });
const walks = (path: string[]) => path.slice(1).every((n, i) => EDGES.has(`${path[i]}->${n}`));

test("spec 08 AC-23: every node the mapping pins exists in agent-reference", () => {
  for (const [source, pin] of Object.entries(PINS)) assert.ok(GRAPH_IDS.has(pin.node), `${source} pins ${pin.node}, not a graph node`);
  for (const n of [...forcedBefore("act"), ...forcedAfter("act"), ...forcedAfter("connect"), ...forcedAfter("respond")]) {
    assert.ok(GRAPH_IDS.has(n), `${n} is not a graph node`);
  }
});

test("spec 08 AC-23: the way into act is forced by the graph, from START", () => {
  const before = forcedBefore("act");
  assert.equal(before[0], "START");
  assert.equal(before.at(-1), "act");
  assert.ok(walks(before));
  assert.deepEqual(forcedAfter("act"), ["verify"]);
});

test("spec 08 AC-23: a blocked case with its turn's handoff card runs from START to END through respond", () => {
  const r = casePath({
    events: [ev("case_opened"), ev("card_blocked"), ev("action_verified"), ev("block_verified"), ev("handoff_emitted"), ev("receipt_issued")],
    handoff: { actions: [{ tool: "open_case" }, { tool: "block_card" }] },
  });
  assert.equal(r.path[0], "START");
  assert.deepEqual(r.path.slice(-4), ["act", "verify", "respond", "END"]);
  assert.ok(walks(r.path));
  assert.equal(r.stop, null);
  for (const n of r.path) assert.ok(r.evidence.some((e) => e.node === n), `${n} has no evidence`);
});

test("spec 08 AC-23: a call in the opening turn's handoff card goes verify → connect → respond", () => {
  const r = casePath({ events: [ev("case_opened"), ev("call_requested")], handoff: { actions: [{ tool: "open_case" }, { tool: "request_call" }] } });
  assert.deepEqual(r.path.slice(-5), ["act", "verify", "connect", "respond", "END"]);
  assert.ok(walks(r.path));
});

test("spec 08 AC-23: a call the events cannot place in a turn stops the path at verify, never guessed", () => {
  const r = casePath({ events: [ev("case_opened"), ev("call_requested"), ev("handoff_emitted")], handoff: { actions: [] } });
  assert.equal(r.path.at(-1), "verify");
  assert.ok(!r.path.includes("connect") && !r.path.includes("respond"));
  assert.ok(r.stop);
});

test("spec 08 AC-23: a customer's own call request does not hide the agent's reply", () => {
  const r = casePath({ events: [ev("case_opened"), ev("call_requested", "customer"), ev("receipt_issued")], handoff: null });
  assert.deepEqual(r.path.slice(-3), ["verify", "respond", "END"]);
});

test("spec 08 AC-23: no case_opened event pins nothing", () => {
  const r = casePath({ events: [ev("assigned", "freddy")], handoff: null });
  assert.deepEqual(r.path, []);
  assert.ok(r.stop);
});
