// Offline checks for "How the console works" (spec 08 AC-24): the analyst's flow in order, the case card's evidence,
// what it runs on, links between drawn boxes only, and every box inside the drawing with a detail and a source.
import assert from "node:assert/strict";
import test from "node:test";
import { EVIDENCE_FRAME, FLOW_BOXES, FLOW_LINE, FLOW_LINKS, FLOW_VIEW, NEEDS_FRAME } from "./console-flow.ts";

type Box = { x: number; y: number; w: number; h: number };
const ids = (group: string) => FLOW_BOXES.filter((b) => b.group === group).map((b) => b.id);
const inside = (b: Box, f: Box) => b.x - b.w / 2 >= f.x && b.x + b.w / 2 <= f.x + f.w && b.y - b.h / 2 >= f.y && b.y + b.h / 2 <= f.y + f.h;

test("spec 08 AC-24: the steps are queue → case card → analyst action → verification → close, linked in that order", () => {
  const steps = ids("step");
  assert.deepEqual(steps, ["queue", "case", "action", "verification", "close"]);
  const stepLinks = FLOW_LINKS.filter((l) => l.kind === "step").map((l) => [l.from, l.to]);
  assert.deepEqual(stepLinks, steps.slice(1).map((s, i) => [steps[i], s]));
});

test("spec 08 AC-24: the case card's evidence and what the flow runs on are drawn", () => {
  assert.deepEqual(ids("evidence"), ["receipt", "deadline", "handoff", "opinion"]);
  assert.deepEqual(ids("need"), ["cognito", "api", "postgres"]);
  for (const b of FLOW_BOXES.filter((x) => x.group === "evidence")) assert.ok(inside(b, EVIDENCE_FRAME), `${b.id} outside its frame`);
  for (const b of FLOW_BOXES.filter((x) => x.group === "need")) assert.ok(inside(b, NEEDS_FRAME), `${b.id} outside its frame`);
});

test("spec 08 AC-24: one plain line, and every box has a detail and a source for the detail panel", () => {
  assert.ok(FLOW_LINE.length > 0 && !FLOW_LINE.includes("\n"));
  for (const b of FLOW_BOXES) {
    assert.ok(b.detail.length > 0 && b.source.length > 0, b.id);
    assert.ok(inside(b, { x: 0, y: 0, w: FLOW_VIEW.width, h: FLOW_VIEW.height }), `${b.id} outside the drawing`);
  }
});

test("spec 08 AC-24: links start and end on the edge of a drawn box, and no two boxes overlap", () => {
  const onEdge = (p: readonly [number, number], id: string) => {
    const b = FLOW_BOXES.find((x) => x.id === id);
    if (!b) return false;
    const d = Math.max(Math.abs(p[0] - b.x) - b.w / 2, Math.abs(p[1] - b.y) - b.h / 2);
    return Math.abs(d) <= 0.5;
  };
  for (const l of FLOW_LINKS) {
    assert.ok(onEdge(l.points[0], l.from), `${l.from}->${l.to} does not start on ${l.from}`);
    assert.ok(onEdge(l.points[l.points.length - 1], l.to), `${l.from}->${l.to} does not end on ${l.to}`);
  }
  for (const a of FLOW_BOXES)
    for (const b of FLOW_BOXES) {
      if (a === b) continue;
      const apart = Math.abs(a.x - b.x) >= (a.w + b.w) / 2 || Math.abs(a.y - b.y) >= (a.h + b.h) / 2;
      assert.ok(apart, `${a.id} overlaps ${b.id}`);
    }
});
