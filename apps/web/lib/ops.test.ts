// Offline checks for the Operation section of /analytics (spec 12 AC-02, AC-04, AC-07; spec 14 §11). Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  METRICS, OPS_INTRO, POSITIONS, SAME_CONTACT, SAME_CONTACT_NOTE, chartDetail, daysText, introDetail, limitationDetail, liveDetail, opsState, pct,
  pendingDetail, tableRows, type LivePending, type LiveReady, type OpsSeries,
} from "./ops.ts";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf-8"));
const FILE = read("../public/data/ops_kpis.json") as { source: string; data: { series: OpsSeries } };
const SERIES = FILE.data.series;
const SRC = readFileSync(new URL("../app/analytics/operations.tsx", import.meta.url), "utf-8");

test("spec 12 AC-02: the switch has three positions (the third, key live, is public demo traffic); both series carry their label, source and the 2026 window", () => {
  assert.deepEqual(POSITIONS.map((p) => p.label), ["Bank today", "With Nick of Time (simulated)", "Public demo traffic"]);
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

const LIVE = SERIES.live as LiveReady;
const pending: LivePending = { key: "live", name: "Public demo traffic", status: "pending",
  message: "Pending: no public demo traffic yet", reason: "spec 14 T5 (the Postgres source) has not run on the deployed app's demo traffic" };

test("spec 12 AC-02: the Live position draws public demo traffic in both modes when its status is ready", () => {
  assert.equal(POSITIONS[2].key, "live");
  assert.equal(LIVE.status, "ready", "the committed file carries the run on a restored production backup");
  const state = opsState(FILE, "live");
  if (state.kind !== "live") return assert.fail("Live is ready");
  const { view } = state;
  assert.equal(LIVE.name, "Public demo traffic");
  assert.equal(LIVE.label, "[simulated]");
  assert.equal(LIVE.message, `Public demo traffic on the deployed app since ${LIVE.window[0]}`);
  assert.match(LIVE.reason, /historical gold state with the fixed demo date 2026-06-01/);
  assert.match(LIVE.reason, /live-mode charges are synthetic \(ADR 0020\)/);
  assert.deepEqual(view.cards.map((c) => c.title), ["Cases", "Receipt with a legal deadline", "Handed to an analyst", "Unsafe outcomes"]);
  const t = LIVE.total;
  assert.deepEqual(view.cards.map((c) => c.value), [String(t.cases), pct(t.receipt_rate.value), pct(t.escalation_rate.value), String(t.unsafe_outcomes)]);
  assert.equal(view.cards[1].sub, `${t.receipt_rate.numerator} of ${t.receipt_rate.denominator} cases`, "every rate shows its counts");
  assert.deepEqual(view.modes.map((m) => [m.mode, m.title]), [["live", "Live mode"], ["replay", "Replay mode"]]);
  assert.equal(view.modes[0].cases + view.modes[1].cases, t.cases, "the breakdown adds up to the cases");
  assert.equal(view.bars.length, LIVE.days.length);
  view.bars.forEach((b) => assert.equal(b.byMode.live + b.byMode.replay, b.cases, `${b.day}: a column is split by mode`));
  assert.ok(view.bars.every((b) => b.cases <= view.scaleMax));
  assert.equal(view.line.split(/(?<=\.)\s+/).length, 1, "one plain line");
  assert.match(view.footer, /^make ops-live/);
  for (const fig of [view.cards.map((c) => c.value + c.sub), view.rows.flat()].flat()) {
    assert.doesNotMatch(fig, /CLI-|TRX-|demo-20|@/, "counts and rates only (spec 14 AC-08)");
  }
});

test("spec 12 AC-02: the Live headline uses the motion kit's count-up, a per-day column chart and the breakdown", () => {
  assert.match(SRC, /function LiveSection/);
  assert.match(SRC, /<CountText className="text-3xl[^"]*" text=\{card\.value\} \/>/);
  assert.match(SRC, /aria-label="Cases per day"/);
  assert.match(SRC, /<h4 className="text-sm font-semibold">By mode<\/h4>/);
  assert.match(SRC, /state\.kind === "live" \?/);
  assert.match(SRC, /setDetail\(liveDetail\(state\.view\.live\)\)/);
  const section = SRC.slice(SRC.indexOf("function LiveSection"), SRC.indexOf("export function Operations"));
  assert.doesNotMatch(section, /transition|animate-|@keyframes/, "only the kit moves, so nothing moves under reduced motion");
  assert.match(section, /<GrowBar[^>]*axis="y"/);
});

test("spec 12 AC-04: Live with status pending stays the empty state, with no figure", () => {
  const all = { ...SERIES, live: pending };
  const state = opsState({ data: { series: all } }, "live");
  assert.ok(state.kind === "pending" && state.title === "Pending: no public demo traffic yet" && /T5/.test(state.missing));
  assert.match(state.detail, /specs\/14-ops-lakehouse\.md#115-live/);
  const none = opsState({ data: {} }, "live");
  assert.ok(none.kind === "pending" && none.title === "Pending: no public demo traffic yet");
  assert.match(pendingDetail(state, all).method.join(" "), /Public demo traffic will read/);
});

test("spec 12 AC-07: the Live columns' tooltips and the table hold the same values; Detail opens the method", () => {
  const state = opsState(FILE, "live");
  if (state.kind !== "live") return assert.fail("Live is ready");
  const { view } = state;
  assert.deepEqual(view.head, ["Day", ...view.bars[0].detail.map(([k]) => k)]);
  view.bars.forEach((b, i) => assert.deepEqual(view.rows[i], [b.day, ...b.detail.map(([, v]) => v)]));
  const last = view.rows.at(-1)!;
  assert.equal(last[0], `${view.bars.length} ${view.bars.length === 1 ? "day" : "days"}`);
  assert.equal(last[1], String(LIVE.total.cases));
  assert.match(last[4], /^\d+\.\d% \(\d+ of \d+\)$/, "a rate with its numerator and denominator");
  assert.match(SRC, /<TableView head=\{view\.head\} rows=\{view\.rows\} \/>/);
  assert.match(SRC, /\{\.\.\.bind\(<TipBody title=\{dayName\(bar\.day\)\} rows=\{bar\.detail\} \/>\)\}/);
  const detail = liveDetail(LIVE);
  assert.equal(detail.title, LIVE.message);
  assert.equal(detail.label, "[simulated]");
  assert.match(detail.method.join(" "), /Evaluation runs never count/);
  assert.match(detail.method.join(" "), /UTC date the case was written/);
  assert.match(detail.href, /#115-live-the-postgres-source-t5-make-ops-live$/);
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
  assert.equal(OPS_INTRO.split(/(?<=\.)\s+/).length, 1, "one line (the lead's legibility pass)");
  assert.equal(OPS_INTRO.split("the system").length, 2, "the link to /agent sits on 'the system'");
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
