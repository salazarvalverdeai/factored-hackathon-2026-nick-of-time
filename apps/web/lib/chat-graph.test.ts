// Offline checks for the live graph beside /chat (spec 07 AC-31): the stream → node mapping uses only nodes of
// lib/agent-reference.ts and covers every progress key and tool event intake.py emits; a scripted turn moves the
// current node and the path along the graph's edges; reduced motion leaves the rail still. Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { AGENT_REFERENCE } from "./agent-reference.ts";
import { graphHighlight } from "./agent-graph.ts";
import { CHAT_STRINGS } from "./chat-strings.ts";
import {
  EMPTY_RUN,
  GRAPH_NODES,
  PROGRESS_NODE,
  TOOL_NODE,
  type GraphFrame,
  type GraphRun,
  advance,
  applyFrame,
  finishRun,
  nodeOfTool,
  routeBetween,
  startRun,
  stopRun,
} from "./chat-graph.ts";

const read = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");
const INTAKE = read("../../../apps/agent/agent/intake.py");
const { graph } = AGENT_REFERENCE;
const EDGES = new Set(graph.edges.flatMap((e) => e.to.map((to) => `${e.from}->${to}`)));
const fold = (frames: GraphFrame[], from: GraphRun = startRun()) => frames.reduce(applyFrame, from);
const tool = (step: string, status: "running" | "done" | "failed"): GraphFrame => ({ kind: "tool", event: { step, status } });

test("spec 07 AC-31: every mapped node id exists in agent-reference, and START/END are the drawing's own", () => {
  const known = new Set<string>(["START", ...graph.nodes, "END"]);
  assert.deepEqual([...GRAPH_NODES].sort(), [...known].sort());
  for (const [key, node] of Object.entries(PROGRESS_NODE)) assert.ok(known.has(node), `progress ${key} → unknown node ${node}`);
  for (const [step, node] of Object.entries(TOOL_NODE)) assert.ok(known.has(node), `tool ${step} → unknown node ${node}`);
  for (const id of known) assert.ok(CHAT_STRINGS.graphNodes[id]?.es && CHAT_STRINGS.graphNodes[id]?.pt, `${id} has no ES/PT words`);
});

test("spec 07 AC-31: every progress key and tool event intake.py emits is mapped to the node that emits it", () => {
  const writing = [...INTAKE.matchAll(/WRITING = \{([^}]*)\}/g)].flatMap((m) => [...m[1].matchAll(/: "([a-z_]+)"/g)].map((x) => x[1]));
  const keys = [...INTAKE.matchAll(/progress\([^,()]+(?:\([^)]*\))?[^,]*, "([a-z_]+)"\)/g)].map((m) => m[1]);
  assert.ok(keys.length >= 6 && writing.length === 2, "intake.py still streams progress keys");
  for (const key of new Set([...keys, ...writing])) assert.ok(PROGRESS_NODE[key], `progress key ${key} is not mapped`);
  const tools = new Set([...INTAKE.matchAll(/tool_event\(state, "([a-z_]+)"/g)].map((m) => m[1]));
  assert.ok(tools.size >= 4, "intake.py still emits tool events");
  for (const step of tools) assert.ok(TOOL_NODE[step], `tool ${step} is not mapped`);
  // Writes start in act and are confirmed in verify (their `done` follows the read-back).
  assert.equal(nodeOfTool({ step: "open_case", status: "running" }, "act"), "act");
  assert.equal(nodeOfTool({ step: "block_card", status: "failed" }, "act"), "act");
  assert.equal(nodeOfTool({ step: "open_case", status: "done" }, "verify"), "verify");
  // A case read inside another step keeps that step; on its own it is the status step.
  assert.equal(nodeOfTool({ step: "get_case", status: "running" }, "connect"), "connect");
  assert.equal(nodeOfTool({ step: "get_case", status: "running" }, "route"), "status");
});

test("spec 07 AC-31: a scripted dispute turn moves the current node and the path along the graph's edges", () => {
  const seen: (string | null)[] = [];
  let run = startRun();
  assert.deepEqual(run, { active: "identity", path: ["START", "identity"] });
  const frames: GraphFrame[] = [
    { kind: "progress", step: "reading_account" },
    { kind: "progress", step: "reading_message" },
    { kind: "progress", step: "searching" },
    tool("search_transaction", "running"),
    tool("search_transaction", "done"),
    { kind: "progress", step: "deciding" },
    tool("evaluate_policy", "running"),
    tool("evaluate_policy", "done"),
    { kind: "progress", step: "opening_case" },
    tool("open_case", "running"),
    { kind: "progress", step: "blocking_card" },
    tool("block_card", "running"),
    { kind: "progress", step: "verifying" },
    tool("open_case", "done"),
    tool("block_card", "done"),
    { kind: "progress", step: "writing" },
    { kind: "text" },
    { kind: "reply" },
  ];
  for (const f of frames) {
    run = applyFrame(run, f);
    seen.push(run.active);
  }
  assert.deepEqual(
    [...new Set(seen)],
    ["greet", "understand", "retrieve", "decide", "act", "verify", "respond"],
    "the current node follows the stream in order",
  );
  assert.deepEqual(run.path, ["START", "identity", "greet", "understand", "route", "retrieve", "decide", "plan", "act", "verify", "respond"]);
  for (let i = 1; i < run.path.length; i++) assert.ok(EDGES.has(`${run.path[i - 1]}->${run.path[i]}`), `${run.path[i - 1]}->${run.path[i]} is an edge`);
  const done = finishRun(run);
  assert.equal(done.active, null);
  assert.equal(done.path.at(-1), "END");
  // What the drawing receives: the walked edges highlighted, the rest dimmed, nothing current once the turn is over.
  const live = graphHighlight(run.active, run.path);
  assert.equal(live.current, "respond");
  assert.ok(live.edges.has("route->retrieve") && live.edges.has("plan->act") && !live.edges.has("route->status"));
  assert.equal(graphHighlight(done.active, done.path).current, null);
});

test("spec 07 AC-31: the mock stream (tools only, no progress) and the other paths still walk real edges", () => {
  const mock = fold([tool("search_transaction", "running"), tool("search_transaction", "done"), tool("evaluate_policy", "done"), { kind: "text" }, { kind: "reply" }]);
  assert.deepEqual(mock.path, ["START", "identity", "greet", "understand", "route", "retrieve", "decide", "respond"]);
  const status = fold([{ kind: "progress", step: "checking_status" }, tool("get_case", "running"), tool("get_case", "done"), { kind: "reply" }]);
  assert.deepEqual(status.path, ["START", "identity", "greet", "understand", "route", "status", "respond"]);
  const call = fold([{ kind: "progress", step: "requesting_call" }, tool("request_call", "running"), tool("get_case", "running"), tool("request_call", "done")]);
  assert.equal(call.active, "connect");
  assert.deepEqual(call.path, ["START", "identity", "greet", "understand", "route", "connect"]);
  const refused = finishRun(fold([{ kind: "text" }]));
  assert.deepEqual(refused.path.slice(-2), ["respond", "END"]);
});

test("spec 07 AC-31: the run only moves forward, ignores unknown steps, and resets cleanly", () => {
  const run = fold([{ kind: "progress", step: "searching" }, { kind: "progress", step: "reading_account" }, { kind: "progress", step: "not_a_step" }, tool("unknown_tool", "running")]);
  assert.equal(run.active, "retrieve", "a passed node or an unknown event never moves the run back");
  assert.equal(advance(run, "nope"), run);
  assert.deepEqual(routeBetween("decide", "act"), ["decide", "plan", "act"]);
  assert.equal(routeBetween("respond", "identity"), null);
  assert.deepEqual(applyFrame(EMPTY_RUN, { kind: "reply" }), EMPTY_RUN, "no turn, no path");
  assert.deepEqual(stopRun(run), { active: null, path: run.path });
  assert.deepEqual(finishRun(EMPTY_RUN), EMPTY_RUN);
});

test("spec 07 AC-27, AC-31: the rail moves only through the shared motion kit, opacity only, and not under reduced motion", () => {
  const src = read("../components/chat/live-graph.tsx");
  assert.doesNotMatch(src, /from "motion\/react"/);
  assert.match(src, /import \{ Reveal \} from "@\/components\/motion"/);
  assert.match(src, /<Reveal\s+fade/, "the panel only fades in (no rise on a fixed panel)");
  // The kit renders its final state under reduced motion: its CSS only plays under no-preference, and each part reads
  // useReducedMotion() (components/motion/README.md).
  assert.match(read("../components/motion/motion.css"), /prefers-reduced-motion: no-preference/);
  assert.match(read("../components/motion/motion-group.tsx"), /useReducedMotion\(\)/);
  assert.match(src, /<GraphView fit reveal=\{false\}/, "the chat draws the graph final, without the reveal");
  assert.match(src, /aria-expanded/, "the toggles say whether the graph is open");
  // Fit mode: no sideways scroll in a 390 px sheet; the drawing's transitions stop under reduced motion.
  const view = read("../components/agent/graph-view.tsx");
  assert.match(view, /fit \? "overflow-hidden" : "overflow-x-auto"/);
  assert.match(view, /!fit && "min-w-\[560px\]"/);
  assert.match(view, /motion-reduce:transition-none/);
  const page = read("../app/chat/page.tsx");
  assert.match(page, /\[graphOpen, setGraphOpen\] = useState\(false\)/, "closed by default, so the conversation keeps its width");
});
