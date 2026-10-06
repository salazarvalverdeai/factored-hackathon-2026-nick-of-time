// Offline checks for the Operation section of /analytics (spec 12 AC-02, AC-04, AC-07; spec 14 §11). Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { METRICS, POSITIONS, opsState, tableRows, type OpsSeries } from "./ops.ts";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf-8"));
const FILE = read("../public/data/ops_kpis.json") as { source: string; data: { series: OpsSeries } };
const SERIES = FILE.data.series;
const SRC = readFileSync(new URL("../app/analytics/operations.tsx", import.meta.url), "utf-8");

test("spec 12 AC-02: the switch has three positions; both series carry their label, source and the 2026 window", () => {
  assert.deepEqual(POSITIONS.map((p) => p.label), ["Bank today", "With Nick of Time (simulated)", "Live"]);
  const bank = opsState(FILE, "bank_today");
  const sim = opsState(FILE, "replay");
  assert.ok(bank.kind === "ready" && sim.kind === "ready");
  if (bank.kind !== "ready" || sim.kind !== "ready") return;
  assert.deepEqual([bank.series.label, sim.series.label], ["[data]", "[simulated]"]);
  assert.ok(bank.series.source && sim.series.source);
  assert.deepEqual(bank.series.window, ["2026-01", "2026-05"]);
  assert.equal(bank.series.total.contacts, sim.series.total.contacts, "both series count the same volume");
  for (const chart of [...bank.charts, ...sim.charts]) {
    assert.ok(chart.label === "[data]" || chart.label === "[simulated]", "every figure carries its label");
    assert.ok(chart.note.length > 0, `${chart.metric.id}: a plain line on what it means`);
    assert.equal(chart.points.length, 5);
  }
  const ids = (key: "bank_today" | "replay") => METRICS.filter((m) => m.keys[key]).map((m) => m.id);
  assert.deepEqual(bank.charts.map((c) => c.metric.id), ids("bank_today"));
  assert.deepEqual(sim.charts.map((c) => c.metric.id), ids("replay"));
  assert.ok(!sim.charts.some((c) => c.metric.id === "resolution_days"), "the final resolution time is never simulated");
});

test("spec 12 AC-02: the headline pairs the bank's FCR with complete intake, and says they differ", () => {
  const bank = opsState(FILE, "bank_today");
  const sim = opsState(FILE, "replay");
  if (bank.kind !== "ready" || sim.kind !== "ready") return assert.fail("both series are ready");
  const [fcr, intake] = [bank.charts[0], sim.charts[0]];
  assert.deepEqual([fcr.title, intake.title], ["Resolved at first contact (FCR)", "Complete intake at first contact (upper bound)"]);
  assert.equal(Math.round(fcr.total.value! * 1000) / 10, 43.6);
  assert.match(intake.note, /not the bank's resolved-at-first-contact/);
  assert.match(intake.note, /upper bound: the message names the charge exactly/);
  assert.deepEqual(intake.secondary.map((x) => x.title), ["Safe automated resolution", "If the message names only the amount and the date"]);
  assert.equal(fcr.secondary.length, 0);
  assert.match(SRC, /The two headline figures measure different things/);
});

test("spec 12 AC-02: only the data's compare pairs are side by side; every other figure is context of one series", () => {
  const pairs = (SERIES as OpsSeries & { compare: Record<string, string>[] }).compare;
  const compared = METRICS.filter((m) => m.role === "comparison");
  assert.deepEqual(compared.map((m) => m.keys), pairs);
  for (const m of METRICS.filter((x) => x.role === "context")) {
    assert.equal(Object.keys(m.keys).length, 1, `${m.id} belongs to one series only`);
  }
  const sim = opsState(FILE, "replay");
  if (sim.kind !== "ready") return assert.fail("replay is ready");
  const handed = sim.charts.find((c) => c.metric.id === "handed_to_analyst")!;
  assert.equal(handed.title, "Handed to an analyst with evidence and a legal deadline");
  assert.match(handed.note, /always go to a person, who decides the block or the credit/);
  assert.ok(!sim.charts.some((c) => c.metric.id === "escalated" || c.metric.id === "outside_sla"));
  assert.match(SRC, /Context · \$\{state\.series\.name\} only/);
  assert.match(SRC, /Compared with the other series/);
});

test("spec 12 AC-02: Live shows 'Pending: no live traffic yet' and no figure until spec 14 T5", () => {
  const live = opsState(FILE, "live");
  assert.ok(live.kind === "pending" && live.title === "Pending: no live traffic yet" && /T5/.test(live.missing));
});

test("spec 12 AC-04: with no file, or a file with no series, the section shows 'Results pending' and what is missing", () => {
  for (const file of [null, { data: {} }, { data: { series: { ...SERIES, replay: null } } }]) {
    const state = opsState(file as never, "replay");
    assert.ok(state.kind === "pending" && state.title === "Results pending" && /make ops-replay/.test(state.missing));
  }
});

test("spec 12 AC-07: the table view holds the values of the marks, with numerator and denominator for every rate", () => {
  const state = opsState(FILE, "replay");
  if (state.kind !== "ready") return assert.fail("replay is ready");
  for (const chart of state.charts) {
    const rows = tableRows(chart);
    assert.equal(rows.length, 6, "5 months and the total");
    assert.equal(rows[5][0], "5 months");
    rows.slice(0, 5).forEach((row, i) => assert.deepEqual(row, [chart.points[i].month, ...chart.points[i].detail.map(([, v]) => v)]));
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
  assert.match(SRC, /does not\s+model the final resolution time,\s+which a person decides/);
  assert.doesNotMatch(SRC, /\[(data|simulated|projected)\]\s*[a-z]/i, "labels sit on figures, not in prose");
});
