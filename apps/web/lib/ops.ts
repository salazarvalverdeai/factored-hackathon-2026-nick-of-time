// "Operation" section of /analytics (spec 12 AC-02, T6; spec 14 §7.4 and §11). Pure, so `npm test` covers it.
// The page only displays: every figure is read from ops_kpis.json `data.series`, never computed here beyond a share.
export type Rate = { value: number | null; numerator: number; denominator: number; constant?: boolean };
export type Days = { p50: number | null; mean?: number | null; n: number; missing?: number };
export type Month = {
  month: string;
  contacts: number;
  days_to_receipt: Days;
  first_contact_resolution: Rate;
  escalated: Rate;
  outside_sla_at_intake: Rate;
  resolution_days?: Days;
  cases_opened?: number;
  asked_several?: Rate;
  asked_none?: Rate;
};
export type Series = {
  key: "bank_today" | "replay";
  name: string;
  label: string;
  source: string;
  window: [string, string];
  notes: Record<string, string>;
  months: Month[];
  total: Month;
};
export type Live = { key: "live"; name: string; status: "pending"; message: string; reason: string };
export type OpsSeries = { window: [string, string]; bank_today: Series | null; replay: Series | null; live: Live };

export const POSITIONS = [
  { key: "bank_today", label: "Bank today" },
  { key: "replay", label: "With Nick of Time (simulated)" },
  { key: "live", label: "Live" },
] as const;
export type Position = (typeof POSITIONS)[number]["key"];

const REPO = "https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/blob/main/";
export const DETAIL = {
  bank_today: `${REPO}queries/ops/asis_monthly.sql`,
  replay: `${REPO}specs/14-ops-lakehouse.md#112-with-nick-of-time-simulated-the-replay-dataopsreplaypy`,
  method: `${REPO}specs/14-ops-lakehouse.md#11-amendment-bank-today-and-replay-over-the-dataset-lead-2026-10-05`,
  shape: `${REPO}specs/14-ops-lakehouse.md#74-appswebpublicdataops_kpisjson`,
  live: `${REPO}specs/14-ops-lakehouse.md#10-plan-tasks-and-verification`,
};

export type Metric = { key: "first_contact_resolution" | "days_to_receipt" | "escalated" | "outside_sla_at_intake" | "resolution_days"; title: string; kind: "rate" | "days" };
export const METRICS: Metric[] = [
  { key: "first_contact_resolution", title: "Resolved at first contact", kind: "rate" },
  { key: "days_to_receipt", title: "Days to a receipt with a legal deadline", kind: "days" },
  { key: "escalated", title: "Escalated to a person", kind: "rate" },
  { key: "outside_sla_at_intake", title: "Outside SLA at intake", kind: "rate" },
  { key: "resolution_days", title: "Days to the final resolution", kind: "days" },
];

export type Point = { month: string; value: number | null; detail: [string, string][] };
export type Chart = { metric: Metric; label: string; note: string; total: Point; points: Point[]; scaleMax: number };
export type OpsState = { kind: "pending"; title: string; missing: string; detail: string } | { kind: "ready"; series: Series; charts: Chart[] };

const int = (n: number) => n.toLocaleString("en-US");
export const pct = (v: number | null, digits = 1) => (v === null ? "no value" : `${(v * 100).toFixed(v > 0 && v < 0.001 ? 2 : digits)}%`);
export const days = (v: number | null) => (v === null ? "no value" : `${v.toFixed(1)} d`);

function point(metric: Metric, m: Month): Point {
  if (metric.kind === "rate") {
    const r = m[metric.key] as Rate;
    const detail: [string, string][] = [["Share", pct(r.value)], ["Numerator", int(r.numerator)], ["Denominator", int(r.denominator)]];
    return { month: m.month, value: r.value, detail: r.constant ? [...detail, ["Per month", "same period value"]] : detail };
  }
  const d = m[metric.key] as Days | undefined;
  const detail: [string, string][] = [["Median", days(d?.p50 ?? null)], ["n", int(d?.n ?? 0)]];
  if (d?.mean !== undefined) detail.splice(1, 0, ["Mean", days(d.mean)]);
  if (d?.missing !== undefined) detail.push(["Without a value", int(d.missing)]);
  return { month: m.month, value: d?.p50 ?? null, detail };
}

/** The charts of one series; the axis of each metric spans both series, so switching keeps the scale (AC-07). */
export function charts(series: Series, all: OpsSeries): Chart[] {
  const both = [all.bank_today, all.replay].filter((s): s is Series => s !== null);
  return METRICS.filter((metric) => metric.key in series.total).map((metric) => {
    const values = both.flatMap((s) => [...s.months, s.total].map((m) => point(metric, m).value ?? 0));
    const top = Math.max(...values, metric.kind === "rate" ? 0.01 : 1);
    return { metric, label: series.label, note: series.notes[metric.key] ?? "", total: point(metric, series.total),
             points: series.months.map((m) => point(metric, m)), scaleMax: top };
  });
}

/** spec 12 AC-04: a missing file or series shows "Results pending" with what is missing and no figure. */
export function opsState(file: { data?: { series?: OpsSeries } } | null, position: Position): OpsState {
  const all = file?.data?.series;
  if (position === "live") {
    return { kind: "pending", title: all?.live.message ?? "Pending: no live traffic yet",
             missing: all?.live.reason ?? "spec 14 T5 (the Postgres source) has not run on live traffic", detail: DETAIL.live };
  }
  const series = all?.[position] ?? null;
  if (!all || !series) {
    return { kind: "pending", title: "Results pending",
             missing: `ops_kpis.json has no ${position} series yet; \`make ops-replay\` (spec 14 §11) writes it.`, detail: DETAIL.shape };
  }
  return { kind: "ready", series, charts: charts(series, all) };
}

/** AC-07: the table view holds exactly the values the chart marks show. */
export function tableRows(chart: Chart): string[][] {
  return [...chart.points, { ...chart.total, month: "12 months" }].map((p) => [p.month, ...p.detail.map(([, v]) => v)]);
}
