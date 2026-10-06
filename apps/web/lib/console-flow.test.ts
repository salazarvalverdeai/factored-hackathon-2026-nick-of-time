// Offline checks for "How the console works" (spec 08 AC-24): the analyst's flow in order, the case card's evidence,
// what it runs on, edges that join drawn boxes and point the right way on the grid, and a detail for every box.
import assert from "node:assert/strict";
import test from "node:test";
import { FLOW_BOXES, FLOW_LINE, FLOW_LINKS, NEEDS_TITLE } from "./console-flow.ts";
import { MOTION, fitStep } from "./motion.ts";

const ids = (group: string) => FLOW_BOXES.filter((b) => b.group === group).map((b) => b.id);
const box = (id: string) => FLOW_BOXES.find((b) => b.id === id);

test("spec 08 AC-24: the steps are queue → case card → analyst action → verification → close, linked in that order", () => {
  const steps = ids("step");
  assert.deepEqual(steps, ["queue", "case", "action", "verification", "close"]);
  const stepLinks = FLOW_LINKS.filter((l) => l.kind === "step").map((l) => [l.from, l.to]);
  assert.deepEqual(stepLinks, steps.slice(1).map((s, i) => [steps[i], s]));
});

test("spec 08 AC-24: the case card's evidence and what the flow runs on are drawn", () => {
  assert.deepEqual(ids("evidence"), ["receipt", "deadline", "handoff", "opinion"]);
  assert.deepEqual(ids("need"), ["cognito", "api", "postgres"]);
  for (const b of FLOW_BOXES) assert.equal(b.row === null, b.group === "evidence", `${b.id}: only evidence sits inside the case card`);
});

test("spec 08 AC-24: one plain line, and every box has a detail and a source for the detail panel", () => {
  assert.ok(FLOW_LINE.length > 0 && !FLOW_LINE.includes("\n"));
  for (const b of FLOW_BOXES) assert.ok(b.detail.length > 0 && b.source.length > 0, b.id);
});

test("spec 08 AC-24: every edge joins two drawn boxes and points the right way on the grid", () => {
  for (const l of FLOW_LINKS) {
    const [a, b] = [box(l.from), box(l.to)];
    assert.ok(a?.row && b?.row && a.col && b.col, `${l.from}->${l.to} joins a box that is not on the grid`);
    if (l.direction === "down") {
      assert.ok(a.col === l.col && b.col === l.col, `${l.from}->${l.to} is not in its boxes' column`);
      assert.equal(l.row, a.row + 1, `${l.from}->${l.to} does not start under ${l.from}`);
      assert.equal(l.row + l.rows, b.row, `${l.from}->${l.to} does not end over ${l.to}`);
    } else {
      assert.ok(a.row === l.row && b.row === l.row && l.col === 2, `${l.from}->${l.to} is not across one row`);
      assert.equal(l.direction === "right", a.col < b.col, `${l.from}->${l.to} points the wrong way`);
    }
  }
});

test("spec 08 AC-24: no two boxes or edges share a cell", () => {
  const cells = new Map<string, string>();
  const take = (col: number, row: number, who: string) => {
    const key = `${col}:${row}`;
    assert.ok(!cells.has(key), `${who} and ${cells.get(key)} share ${key}`);
    cells.set(key, who);
  };
  for (const b of FLOW_BOXES) if (b.row && b.col) take(b.col, b.row, b.id);
  for (const l of FLOW_LINKS) for (let r = l.row; r < l.row + l.rows; r++) take(l.col, r, `${l.from}->${l.to}`);
  take(NEEDS_TITLE.col, NEEDS_TITLE.row, "title");
});

test("spec 08 AC-24: the edges play once in order within the motion kit's sequence", () => {
  const step = fitStep(FLOW_LINKS.length, 150, MOTION.flow + MOTION.after);
  const last = (FLOW_LINKS.length - 1) * step + MOTION.flow + MOTION.after;
  assert.ok(last <= MOTION.sequence, `the walk takes ${last} ms`);
  assert.ok(MOTION.flow <= 600);
});
