// Offline checks for "The data at a glance" on /data (spec 12 AC-03, AC-04, AC-07, AC-09). Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  PROFILE_KEYS,
  complaintChart,
  countryChart,
  dataProfile,
  niceTicks,
  pendingHint,
  qualityChart,
  scoreChart,
  smallPct,
  volumeChart,
  type Profile,
} from "./data-profile.ts";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf-8"));
const QUALITY = read("../public/data/data_quality.json") as { data: { profile: Profile } };
const PITCH = read("../public/data/pitch_numbers.json") as { data: { share: { n_complaints: number; n_w3: number; pct_w3: number } } };
const PROFILE = QUALITY.data.profile;
const SRC = readFileSync(new URL("../app/data/profile-charts.tsx", import.meta.url), "utf-8");
const near100 = (xs: number[], what: string) => assert.ok(Math.abs(xs.reduce((a, b) => a + b, 0) - 100) < 1e-6, `${what}: shares sum to 100%`);
const ordered = (xs: string[]) => xs.every((x, i) => i === 0 || xs[i - 1] < x);

test("spec 12 AC-03: the five charts of the committed profile are ready, each with its query and [data] label", () => {
  const view = dataProfile(PROFILE);
  assert.equal(view.pending, false);
  assert.deepEqual(view.missing, []);
  for (const key of PROFILE_KEYS) {
    const chart = view.charts[key];
    assert.ok(chart, `${key} is drawn`);
    assert.equal(chart.label, "[data]");
    assert.match(chart.query, new RegExp(`^queries/data/${key}_\\w+\\.sql$`));
    assert.equal(chart.detail.source, chart.query, "the panel names the query");
    assert.ok(chart.detail.spec.endsWith(chart.query), "Read the query → links the query on GitHub");
    assert.ok(chart.detail.meaning && chart.detail.method, "what it shows, and how");
  }
});

test("spec 12 AC-03: d02 months are ordered 2025-06..2026-05 and every share sums to 100%", () => {
  const c = volumeChart(PROFILE.d02)!;
  const months = c.months.map((m) => m.month);
  assert.ok(ordered(months), "months ascend");
  assert.deepEqual([months.length, months[0], months[11]], [12, "2025-06", "2026-05"]);
  near100(c.status.map((s) => s.pct), "status over the window");
  for (const m of c.months) {
    near100(m.parts.map((p) => p.pct), `${m.month} product types`);
    near100(m.status.map((s) => s.pct), `${m.month} statuses`);
    assert.equal(m.parts.reduce((a, p) => a + p.n, 0), m.total);
  }
  assert.equal(c.total, PROFILE.d02!.rows.reduce((a, r) => a + r.n_transactions, 0));
  assert.ok(c.max >= Math.max(...c.months.map((m) => m.total)), "the axis covers the tallest column");
  // A shuffled file draws the same chart: the order comes from the months, not from the rows.
  const shuffled = volumeChart({ ...PROFILE.d02!, rows: [...PROFILE.d02!.rows].reverse() })!;
  assert.deepEqual(shuffled.months.map((m) => m.month), months);
});

test("spec 12 AC-03: d03 countries add up to every customer and transaction, segment shares to 100%", () => {
  const c = countryChart(PROFILE.d03)!;
  assert.deepEqual(c.countries.map((x) => x.country), ["MX", "CO", "AR"], "largest first, the empty unknown row left out");
  assert.equal(c.customers, 150000);
  assert.equal(c.unknownTransactions, 0);
  near100(c.segmentMix.map((s) => s.pct), "segment mix");
  for (const x of c.countries) {
    near100(x.segments.map((s) => s.pctCustomers), `${x.country} segments`);
    assert.equal(x.segments.reduce((a, s) => a + s.customers, 0), x.customers);
  }
});

test("spec 12 AC-03: d04 bands sum to 100% per country and the upper bands read as 0.067%", () => {
  const c = scoreChart(PROFILE.d04)!;
  assert.deepEqual(c.countries.map((x) => x.country), ["MX", "CO", "AR", "all"]);
  for (const x of c.countries) {
    near100(x.bands.map((b) => b.pct), `${x.country} bands`);
    assert.equal(x.bands.reduce((a, b) => a + b.n, 0), x.total);
  }
  assert.equal(smallPct(c.upperPct), "0.067%");
  assert.equal(c.nullPct.toFixed(1), "20.1");
  assert.equal(smallPct(0.0291), "0.029%");
  assert.equal(smallPct(20.05), "20.1%");
});

test("spec 12 AC-03: d05 months ascend, each W3 share matches its row and the total matches /analytics", () => {
  const c = complaintChart(PROFILE.d05)!;
  const months = c.months.map((m) => m.month);
  assert.ok(ordered(months), "months ascend");
  assert.deepEqual([c.months[0].partial, c.months[1].partial, c.months[months.length - 1].partial], [true, false, true]);
  for (const m of c.months) {
    const row = PROFILE.d05!.rows.find((r) => r.month === m.month)!;
    assert.equal(m.w3Pct, row.pct_w3_month, `${m.month}: the line is the row's share`);
    assert.equal(Math.round((1000 * m.w3) / m.total) / 10, row.pct_w3_month, `${m.month}: the share is W3 over the month`);
    assert.equal(m.groups.reduce((a, g) => a + g.n, 0), m.total, `${m.month}: the stack is the month`);
  }
  // Same W3 rules as /analytics (CMP-01..03): the whole-window share is the pitch number.
  const { n_complaints, n_w3, pct_w3 } = PITCH.data.share;
  assert.deepEqual([c.total, c.w3], [n_complaints, n_w3]);
  assert.equal(c.w3Pct.toFixed(1), pct_w3.toFixed(1));
});

test("spec 12 AC-03: d06 lists each gold table with its rows, the non-zero findings first", () => {
  const c = qualityChart(PROFILE.d06)!;
  assert.deepEqual(c.tables.map((t) => t.table), ["customers", "products", "transactions", "complaints"]);
  assert.equal(c.checked, c.tables.reduce((a, t) => a + t.found.length + t.cleanNull.length + t.cleanFlag.length, 0));
  for (const t of c.tables) {
    assert.ok(t.found.every((f, i) => f.n > 0 && (i === 0 || t.found[i - 1].pct >= f.pct)), `${t.table}: findings by share`);
    assert.ok(t.found.every((f) => f.pct >= 0 && f.pct <= 100));
  }
});

test("spec 12 AC-04: no profile, or a missing block, shows Results pending with what is missing and no figure", () => {
  for (const empty of [null, undefined]) {
    const view = dataProfile(empty);
    assert.equal(view.pending, true);
    assert.deepEqual(view.missing.map((m) => m.key), [...PROFILE_KEYS]);
    assert.ok(Object.values(view.charts).every((c) => c === null));
  }
  const partial = dataProfile({ ...PROFILE, d04: null, d05: { query: "queries/data/d05_complaints_per_month.sql", label: "[data]", rows: [] } });
  assert.equal(partial.pending, false);
  assert.deepEqual(partial.missing.map((m) => m.key), ["d04", "d05"]);
  assert.ok(partial.charts.d02 && partial.charts.d06);
  assert.match(pendingHint("d04"), /no d04 block/);
  assert.doesNotMatch(pendingHint("d04"), /\d+\.\d|%/, "the pending text carries no figure");
  assert.match(SRC, /title="Results pending"/);
});

test("spec 12 AC-07: every chart has a table view with one row per mark group, and marks answer hover and focus alike", () => {
  const view = dataProfile(PROFILE);
  const { d02, d03, d04, d05, d06 } = view.charts;
  assert.equal(d02!.table.rows.length, d02!.months.length);
  assert.equal(d03!.table.rows.length, d03!.countries.reduce((a, x) => a + 1 + x.segments.length, 0));
  assert.equal(d04!.table.rows.length, d04!.countries.length);
  assert.equal(d05!.table.rows.length, d05!.months.length);
  assert.equal(d06!.table.rows.length, PROFILE.d06!.rows.filter((r) => r.kind !== "rows").length);
  for (const c of [d02, d03, d04, d05, d06]) assert.ok(c!.table.rows.every((r) => r.length === c!.table.head.length));
  // useTip().bind gives the same content to pointer and focus handlers; each card renders a TableView.
  assert.equal((SRC.match(/<TableView /g) ?? []).length, 5);
  assert.ok((SRC.match(/tabIndex=\{0\}/g) ?? []).length >= 5, "the marks take keyboard focus");
});

test("spec 12 AC-09: the charts fit 390 px: no fixed minimum width, and axes use clean ticks", () => {
  assert.doesNotMatch(SRC, /min-w-\[\d+px\]/, "no chart forces a sideways scroll");
  assert.deepEqual(niceTicks(124000), [0, 25000, 50000, 75000, 100000, 125000]);
  assert.deepEqual(niceTicks(2001), [0, 500, 1000, 1500, 2000, 2500]);
  assert.deepEqual(niceTicks(0), [0, 1]);
});
