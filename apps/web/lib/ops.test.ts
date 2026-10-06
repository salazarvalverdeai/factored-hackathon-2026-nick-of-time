// Offline checks for the Operation section of /analytics (spec 12 AC-02, AC-04, AC-07; spec 14 §11). Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { METRICS, OPS_INTRO, POSITIONS, SAME_CONTACT, SAME_CONTACT_NOTE, chartDetail, daysText, introDetail, limitationDetail, opsState, tableRows, type OpsSeries } from "./ops.ts";

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
  assert.match(introDetail(SERIES).method.join(" "), /The two headline figures measure different things/);
  assert.match(introDetail(SERIES).method.join(" "), /upper bound/);
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
  assert.match(introDetail(SERIES).method.join(" "), /does not model the final resolution time, which a person decides/);
  assert.doesNotMatch(SRC, /\[(data|simulated|projected)\]\s*[a-z]/i, "labels sit on figures, not in prose");
});

test("spec 12 AC-07: 'Detail →' opens the shared detail panel with method, source query, window, label and spec link", () => {
  const sim = opsState(FILE, "replay");
  if (sim.kind !== "ready") return assert.fail("replay is ready");
  const detail = chartDetail(sim.charts[0], sim.series);
  assert.equal(detail.title, "Complete intake at first contact (upper bound)");
  assert.ok(detail.method.length === 2 && /no language\s+model/.test(detail.method[0]), "the method in plain sentences");
  assert.equal(detail.source, "queries/ops/replay_sample.sql · data/ops/replay.py");
  assert.equal(detail.window, "January 2026 to May 2026 (2026-01 to 2026-05)");
  assert.equal(detail.label, "[simulated]");
  assert.match(detail.href, /^https:\/\/github\.com\/.*specs\/14-ops-lakehouse\.md#11/);
  assert.match(limitationDetail(SERIES).method[0], /does not link a complaint to the charge/);
  assert.match(SRC, /<DetailPanel/);
  assert.match(SRC, /Read spec 14 §11 →/);
  assert.match(SRC, /<DetailField label="Source query" mono>/);
  assert.doesNotMatch(SRC, /<a href=\{[^}]*\}[^>]*>\s*Detail →/, "Detail opens the panel, never a plain link");
});

test("spec 12 AC-09: the Operation intro is at most two sentences and its detail panel holds the method and the limitation link", () => {
  assert.ok(OPS_INTRO.split(/(?<=\.)\s+/).length <= 2, "two lines at most");
  assert.match(SRC, /OPS_INTRO[^]*?setDetail\(introDetail\(all\)\)[^]*?Detail →/);
  const d = introDetail(SERIES);
  assert.match(d.method.join(" "), /real approved card charges/i);
  assert.match(d.method.join(" "), /holiday calendars for 2026 only/);
  assert.equal(d.window, "January 2026 to May 2026 (2026-01 to 2026-05)");
  assert.match(d.extra?.href ?? "", /specs\/14-ops-lakehouse\.md#114-dataset-limitation/);
  assert.match(SRC, /detail\.extra/);
});

test("spec 12 AC-07: a receipt in the first conversation reads 'Same contact', never '0.0 d'", () => {
  assert.equal(daysText("days_to_receipt", 0), SAME_CONTACT);
  assert.equal(daysText("days_to_receipt", 2.4), "2.4 d");
  assert.equal(daysText("resolution_days", 0), "0.0 d", "only the receipt metric is rewritten");
  const sim = opsState(FILE, "replay");
  if (sim.kind !== "ready") return assert.fail("replay is ready");
  const receipt = sim.charts.find((c) => c.metric.id === "days_to_receipt")!;
  if (receipt.total.value === 0) assert.equal(receipt.total.detail[0][1], SAME_CONTACT);
  assert.match(SAME_CONTACT_NOTE, /legal deadline is given in the first conversation/);
  assert.match(SRC, /SAME_CONTACT_NOTE/);
});

test("spec 12 AC-09: '✓ pass' on /data has a lighter teal in dark (4.5:1 on the card)", () => {
  const page = readFileSync(new URL("../app/data/page.tsx", import.meta.url), "utf-8");
  assert.match(page, /text-brand-teal dark:text-teal-300/);
  const lum = (hex: string) => {
    const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const ratio = (a: string, b: string) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);
  assert.ok(ratio("#5eead4", "#111827") >= 4.5, "teal-300 on the dark card");
  assert.ok(ratio("#0f766e", "#111827") < 4.5, "the light teal is the one that failed");
});
