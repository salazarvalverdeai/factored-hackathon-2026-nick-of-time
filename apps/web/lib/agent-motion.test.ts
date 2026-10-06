// Offline checks for the motion of /agent's graph (spec 04 AC-08): the reveal order is derived from the graph's edges,
// a run's activeNode and path highlight the right nodes and edges, and reduced motion renders the final state.
import assert from "node:assert/strict";
import test from "node:test";
import { GRAPH_REVEAL, GRAPH_VIEW, graphHighlight } from "./agent-graph.ts";
import {
  TIMING,
  firstPhase,
  linkKey,
  pathOf,
  pointAt,
  polylineLength,
  replayPhase,
  revealSchedule,
  topologicalOrder,
  transitionFor,
} from "./agent-motion.ts";

const ids = GRAPH_VIEW.nodes.map((n) => n.id);

test("spec 04 AC-08: nodes reveal in topological order of the graph's edges, START first and END last, one stagger apart", () => {
  const { order, node } = GRAPH_REVEAL;
  assert.deepEqual([...order].sort(), [...ids].sort());
  assert.equal(order[0], "START");
  assert.equal(order.at(-1), "END");
  for (const e of GRAPH_VIEW.edges) {
    assert.ok(order.indexOf(e.from) < order.indexOf(e.to), `${linkKey(e)} reveals its target first`);
    assert.ok(node[e.from] < node[e.to], `${linkKey(e)}: ${e.to} appears before ${e.from}`);
  }
  order.forEach((n, i) => assert.equal(node[n], Math.round(i * TIMING.stagger * 1000) / 1000, n));
});

test("spec 04 AC-08: an edge draws after its source node appears, and its branch label fades in after the edge", () => {
  for (const e of GRAPH_VIEW.edges) {
    const k = linkKey(e);
    assert.ok(GRAPH_REVEAL.edge[k] >= GRAPH_REVEAL.node[e.from] + TIMING.node - 1e-9, k);
    assert.ok(GRAPH_REVEAL.label[k] >= GRAPH_REVEAL.edge[k] + TIMING.edge - 1e-9, k);
    assert.ok(GRAPH_REVEAL.total >= GRAPH_REVEAL.label[k] + TIMING.label - 1e-9, k);
  }
  assert.ok(GRAPH_REVEAL.total < 3, "the whole reveal stays short");
});

test("spec 04 AC-08: every single transition is 150–400 ms (BRAND.md calm motion)", () => {
  for (const s of [TIMING.node, TIMING.edge, TIMING.label, TIMING.highlight]) assert.ok(s >= 0.15 && s <= 0.4, String(s));
});

test("spec 04 AC-08: the topological order follows edges, not the given order, and keeps the given order on ties", () => {
  const edges = [{ from: "a", to: "c" }, { from: "c", to: "b" }];
  assert.deepEqual(topologicalOrder(["a", "b", "c"], edges), ["a", "c", "b"]);
  assert.deepEqual(topologicalOrder(["x", "a", "y"], []), ["x", "a", "y"]);
  assert.deepEqual(topologicalOrder(["a", "b"], [{ from: "a", to: "b" }, { from: "b", to: "a" }]), ["a", "b"], "a cycle keeps every node");
  const s = revealSchedule(["a", "b", "c"], edges);
  assert.ok(s.node.a < s.node.c && s.node.c < s.node.b);
});

test("spec 04 AC-08: activeNode marks the current node; with no path nothing dims", () => {
  const h = graphHighlight("decide");
  assert.equal(h.current, "decide");
  assert.deepEqual([...h.nodes], ["decide"]);
  assert.equal(h.edges.size, 0);
  assert.equal(h.dims, false);
  const none = graphHighlight();
  assert.equal(none.current, null);
  assert.equal(none.nodes.size + none.edges.size, 0);
  assert.equal(graphHighlight("not_a_node").current, null, "an unknown id is ignored");
});

test("spec 04 AC-08: a path highlights its nodes and the edges between consecutive nodes, and dims the rest", () => {
  // A real run: walk the first edge out of each node from START until END.
  const path = ["START"];
  while (path.at(-1) !== "END") path.push(GRAPH_VIEW.edges.find((e) => e.from === path.at(-1))!.to);
  const h = graphHighlight("respond", path);
  assert.equal(h.dims, true);
  assert.equal(h.current, "respond");
  assert.deepEqual([...h.nodes].sort(), [...new Set(path)].sort());
  assert.equal(h.edges.size, path.length - 1);
  for (let i = 1; i < path.length; i++) assert.ok(h.edges.has(linkKey({ from: path[i - 1], to: path[i] })));
  for (const e of GRAPH_VIEW.edges) {
    const consecutive = path.some((n, i) => i > 0 && path[i - 1] === e.from && n === e.to);
    assert.equal(h.edges.has(linkKey(e)), consecutive, linkKey(e));
  }
  const skip = graphHighlight(undefined, ["START", "decide", "nope"]);
  assert.equal(skip.edges.size, 0, "a jump that is not an edge highlights no edge");
  assert.deepEqual([...skip.nodes], ["START", "decide"]);
});

test("spec 04 AC-08: with reduced motion the drawing renders its final state and Replay never plays", () => {
  assert.equal(firstPhase({ reducedMotion: true, visible: false }), "final");
  assert.equal(firstPhase({ reducedMotion: true, visible: true }), "final");
  assert.equal(replayPhase(true), "final");
  assert.deepEqual(transitionFor("final", 1.2, 0.3), { duration: 0 }, "final waits for nothing");
  assert.deepEqual(transitionFor("hidden", 1.2, 0.3), { duration: 0 });
});

test("spec 04 AC-08: with motion, a drawing below the fold is armed and one already on screen stays final", () => {
  assert.equal(firstPhase({ reducedMotion: false, visible: false }), "hidden");
  assert.equal(firstPhase({ reducedMotion: false, visible: true }), "final");
  assert.equal(replayPhase(false), "play");
  const t = transitionFor("play", 0.5, 0.3);
  assert.equal(t.delay, 0.5);
  assert.equal(t.duration, 0.3);
});

test("spec 04 AC-08: a flow's dot travels along its polyline from start to end", () => {
  const pts = [[0, 0], [0, 10], [30, 10]] as const;
  assert.equal(polylineLength(pts), 40);
  assert.deepEqual(pointAt(pts, 0), { x: 0, y: 0 });
  assert.deepEqual(pointAt(pts, 0.25), { x: 0, y: 10 });
  assert.deepEqual(pointAt(pts, 0.625), { x: 15, y: 10 });
  assert.deepEqual(pointAt(pts, 1), { x: 30, y: 10 });
  assert.deepEqual(pointAt(pts, 2), { x: 30, y: 10 }, "clamped");
  assert.equal(pathOf(pts), "M0 0 L0 10 L30 10");
});
