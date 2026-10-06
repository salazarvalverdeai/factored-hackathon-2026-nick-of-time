// Offline checks for the motion kit (components/motion/). Run with `npm test`.
// spec 12 AC-07: animation never changes what hover, keyboard focus and the table view show (final values, same marks);
// spec 12 AC-09: nothing moves with reduced motion, and nothing animates a layout property, so pages never shift or scroll sideways.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  MOTION,
  MOTION_HEAD_SCRIPT,
  MOTION_LIVE,
  MOTION_OK,
  firstFrame,
  fitStep,
  growTarget,
  initialState,
  joinFigures,
  splitFigures,
  staggerDelay,
  walkSchedule,
} from "./motion.ts";

const read = (f: string) => readFileSync(new URL(`../${f}`, import.meta.url), "utf-8");
const CSS = read("components/motion/motion.css");

/** Runs the head script against a fake <html>; returns the attributes it leaves and the pending timer. */
function runHeadScript(reduce: boolean, hydrated: boolean) {
  const attrs = new Set<string>();
  const timers: (() => void)[] = [];
  const documentElement = {
    setAttribute: (name: string) => attrs.add(name),
    removeAttribute: (name: string) => attrs.delete(name),
    hasAttribute: (name: string) => attrs.has(name),
  };
  const matchMedia = (q: string) => ({ matches: reduce && q.includes("reduce") });
  new Function("document", "window", "matchMedia", "setTimeout", MOTION_HEAD_SCRIPT)(
    { documentElement },
    { matchMedia },
    matchMedia,
    (fn: () => void) => timers.push(fn),
  );
  if (hydrated) attrs.add(MOTION_LIVE);
  for (const fn of timers) fn();
  return attrs;
}

test("spec 12 AC-09: with reduced motion every part starts in its final state, and a figure's first frame is its value", () => {
  assert.equal(initialState(true, true), "done");
  assert.equal(initialState(false, false), "done"); // no motion flag (no JavaScript, or the safety timer fired): final state
  assert.equal(initialState(false, true), "pending");
  assert.equal(firstFrame(43.6, true, 39.2), 43.6);
  assert.equal(firstFrame(43.6, false, 39.2), 39.2);
});

test("spec 12 AC-09: the head script turns motion on only without reduced motion, and off again if the app never hydrates", () => {
  assert.ok(!runHeadScript(true, true).has(MOTION_OK));
  assert.ok(runHeadScript(false, true).has(MOTION_OK));
  assert.ok(!runHeadScript(false, false).has(MOTION_OK)); // a failed script load never leaves a mark hidden
});

test("spec 12 AC-09: every hidden start state sits behind the motion flag and prefers-reduced-motion: no-preference", () => {
  const gate = CSS.indexOf("@media screen and (prefers-reduced-motion: no-preference)");
  assert.ok(gate > 0);
  const before = CSS.slice(0, gate).replace(/\/\*[^]*?\*\//g, "");
  assert.doesNotMatch(before, /opacity:\s*0|scale[XY]\(0\)|stroke-dashoffset|transition/);
  const gated = CSS.slice(gate, CSS.indexOf("@keyframes")).replace(/\/\*[^]*?\*\//g, "");
  for (const rule of gated.split("}").filter((r) => r.includes("{") && !r.includes("@media"))) {
    assert.match(rule, /html\[data-motion-ok\]/, rule);
  }
  // Only transform, opacity and stroke-dashoffset move: never a layout property, so the space is reserved from the first frame.
  for (const [, props] of gated.matchAll(/transition:([^;]+);/g)) {
    for (const [, prop] of props.matchAll(/(?:^|,)\s*([a-z-]+)\s+\d+m?s/g)) assert.ok(["opacity", "transform", "stroke-dashoffset"].includes(prop), prop);
  }
});

test("spec 12 AC-09: every animation is at most 600 ms, the CSS durations match MOTION, and a full sequence ends within 1.5 s", () => {
  for (const [, ms] of CSS.matchAll(/(\d+)ms var\(--motion-ease\)|(\d+)ms linear/g)) assert.ok(Number(ms ?? 0) <= 600);
  for (const key of ["rise", "fade", "grow", "draw", "flow", "after"] as const) {
    assert.ok(MOTION[key] <= 600, key);
    assert.ok(CSS.includes(`${MOTION[key]}ms`), `${key} ${MOTION[key]}ms in motion.css`);
  }
  for (let nodes = 1; nodes <= 12; nodes++) {
    for (let outputs = 0; outputs <= 6; outputs++) {
      const walk = walkSchedule(nodes, outputs);
      assert.ok(walk.end <= MOTION.sequence, `${nodes} nodes, ${outputs} outputs: ${walk.end} ms`);
      for (let i = 1; i < nodes; i++) assert.ok(walk.node(i) > walk.node(i - 1) && walk.edge(i - 1) < walk.node(i), "walks in order, edge between nodes");
    }
  }
  for (let i = 0; i < 40; i++) assert.ok(staggerDelay(i) + MOTION.rise <= MOTION.sequence);
  for (let n = 1; n <= 40; n++) assert.ok(fitStep(n) * (n - 1) + MOTION.rise <= MOTION.sequence + 1e-9);
});

test("spec 12 AC-07: GrowBar's target size maps the value onto its track and stays inside it", () => {
  assert.equal(growTarget(0.5), 50);
  assert.equal(growTarget(0.25, 1, 78), 19.5); // the contact bars use 78% of the row for the scale maximum
  assert.equal(growTarget(3, 6, 78), 39);
  assert.equal(growTarget(2), 100);
  assert.equal(growTarget(-1), 0);
  assert.equal(growTarget(null), 0);
  assert.equal(growTarget(1, 0), 0);
});

test("spec 12 AC-07: a counting figure always ends on the exact text the page formats, and never counts a version or a date", () => {
  const lines = ["88.9%", "0.912", "43.6%", "4 tables · 1,234,567 rows [data]", "1,024 files · 2,048.5 MB [data]", "2.0 d", "Same contact", "Gold v3", "window 2025-06-01", "—"];
  for (const line of lines) assert.equal(joinFigures(splitFigures(line)), line);
  const figures = (line: string) => splitFigures(line).flatMap((p) => ("value" in p ? [p.value] : []));
  assert.deepEqual(figures("88.9%"), [88.9]);
  assert.deepEqual(figures("4 tables · 1,234,567 rows [data]"), [4, 1234567]);
  assert.deepEqual(figures("Gold v3"), []);
  assert.deepEqual(figures("window 2025-06-01"), []);
  assert.deepEqual(figures("Same contact"), []);
});

test("spec 12 AC-07, AC-09: every kit component reads useReducedMotion and passes its props through (focus and tooltips unchanged)", () => {
  const group = read("components/motion/motion-group.tsx");
  const kit = read("components/motion/index.tsx");
  assert.match(group, /useReducedMotion\(\)/);
  assert.match(group, /createElement\(as \?\? "div", \{ \.\.\.rest/);
  for (const name of ["Reveal", "Stagger", "GrowBar", "GrowGroup", "DrawPath", "FlowConnector"]) {
    assert.match(kit, new RegExp(`export function ${name}[^]*?<MotionGroup`), name); // built on the one reduced-motion-aware root
  }
  for (const name of ["Lift", "Crossfade"]) assert.match(kit, new RegExp(`export function ${name}[^]*?useReducedMotion\\(\\)`), name);
  assert.match(kit, /export \{ NumberTicker \}/);
  assert.doesNotMatch(kit + group + CSS, /spring|bounce|overshoot\s*:/i);
});
