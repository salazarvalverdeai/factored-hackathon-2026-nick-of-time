// Offline checks for the Operation section of /analytics (spec 12 AC-02, AC-04, AC-07; spec 14 §11). Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { METRICS, POSITIONS, opsState, tableRows, type OpsSeries } from "./ops.ts";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf-8"));
const FILE = read("../public/data/ops_kpis.json") as { source: string; data: { series: OpsSeries } };
const SERIES = FILE.data.series;
const SRC = readFileSync(new URL("../app/analytics/operations.tsx", import.meta.url), "utf-8");

test("spec 12 AC-02: the switch has the three positions, and both measured series carry their label and source", () => {
  assert.deepEqual(POSITIONS.map((p) => p.label), ["Bank today", "With Nick of Time (simulated)", "Live"]);
  const bank = opsState(FILE, "bank_today");
  const sim = opsState(FILE, "replay");
  assert.ok(bank.kind === "ready" && sim.kind === "ready");
  if (bank.kind !== "ready" || sim.kind !== "ready") return;
  assert.equal(bank.series.label, "[data]");
  assert.equal(sim.series.label, "[simulated]");
  assert.ok(bank.series.source && sim.series.source);
  assert.deepEqual(bank.series.window, ["2025-06", "2026-05"]);
  assert.equal(bank.series.total.contacts, sim.series.total.contacts, "both series count the same complaints");
  for (const chart of [...bank.charts, ...sim.charts]) {
    assert.ok(chart.label === "[data]" || chart.label === "[simulated]", "every figure carries its label");
    assert.ok(chart.note.length > 0, `${chart.metric.key}: a plain line on what it means`);
    assert.equal(chart.points.length, 12);
  }
  assert.deepEqual(bank.charts.map((c) => c.metric.key), METRICS.map((m) => m.key));
  assert.ok(!sim.charts.some((c) => c.metric.key === "resolution_days"), "the final resolution time is never simulated");
});

test("spec 12 AC-02: Live shows 'Pending: no live traffic yet' and no figure until spec 14 T5", () => {
  const live = opsState(FILE, "live");
  assert.equal(live.kind, "pending");
  assert.ok(live.kind === "pending" && live.title === "Pending: no live traffic yet" && /T5/.test(live.missing));
});

test("spec 12 AC-04: with no file, or a file with no series, the section shows 'Results pending' and what is missing", () => {
  for (const file of [null, { data: {} }, { data: { series: { ...SERIES, replay: null } } }]) {
    const state = opsState(file as never, "replay");
    assert.equal(state.kind, "pending");
    assert.ok(state.kind === "pending" && state.title === "Results pending" && /make ops-replay/.test(state.missing));
  }
});

test("spec 12 AC-07: the table view holds the values of the marks, with numerator and denominator for every rate", () => {
  const state = opsState(FILE, "replay");
  assert.ok(state.kind === "ready");
  if (state.kind !== "ready") return;
  for (const chart of state.charts) {
    const rows = tableRows(chart);
    assert.equal(rows.length, 13, "12 months and the 12-month total");
    rows.slice(0, 12).forEach((row, i) => assert.deepEqual(row, [chart.points[i].month, ...chart.points[i].detail.map(([, v]) => v)]));
    if (chart.metric.kind === "rate") assert.deepEqual(chart.total.detail.map(([k]) => k).slice(0, 3), ["Share", "Numerator", "Denominator"]);
    assert.ok(chart.points.every((p) => p.value === null || p.value <= chart.scaleMax), "one axis for both series");
  }
});

test("spec 12 AC-07: every bar answers hover and keyboard focus, every chart has a table view and a Detail link", () => {
  assert.match(SRC, /tabIndex=\{0\}/);
  assert.match(SRC, /\{\.\.\.bind\(/, "the tooltip binds pointer and focus (useTip)");
  assert.match(SRC, /<TableView/);
  assert.match(SRC, /Detail →/);
  assert.match(SRC, /href="\/agent"/, "the system links to /agent, no diagram here");
  assert.match(SRC, /it does not model\s+the final resolution time, which a person decides/);
  assert.doesNotMatch(SRC, /\[(data|simulated|projected)\]\s*[a-z]/i, "labels sit on figures, not in prose");
});
