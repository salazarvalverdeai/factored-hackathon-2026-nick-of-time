// "Operation" section of /analytics (spec 12 AC-02, T6; spec 14 §7.4 and §11). Pure, so `npm test` covers it.
// The page only displays: every figure is read from ops_kpis.json `data.series`, never computed here beyond a share.
export type Rate = { value: number | null; numerator: number; denominator: number; constant?: boolean };
export type Days = { p50: number | null; mean?: number | null; n: number; missing?: number };
export type Month = { month: string; contacts: number } & Record<string, Rate | Days | number | string>;
export type SeriesKey = "bank_today" | "replay";
export type Series = {
  key: SeriesKey;
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
const SPEC14 = `${REPO}specs/14-ops-lakehouse.md`;
export const DETAIL = {
  bank_today: `${REPO}queries/ops/asis_monthly.sql`,
  replay: `${SPEC14}#112-with-nick-of-time-simulated-the-replay-dataopsreplaypy`,
  method: `${SPEC14}#11-amendment-bank-today-and-replay-over-the-dataset-lead-2026-10-05`,
  limitation: `${SPEC14}#114-dataset-limitation-complaints-cannot-be-replayed-as-they-are`,
  shape: `${SPEC14}#74-appswebpublicdataops_kpisjson`,
  live: `${SPEC14}#10-plan-tasks-and-verification`,
};

/** One chart slot; `keys` names the field each series fills it with, so the headline pairs FCR with complete intake. */
export type Metric = { id: string; kind: "rate" | "days"; keys: Partial<Record<SeriesKey, string>>; titles: Partial<Record<SeriesKey, string>> };
export const METRICS: Metric[] = [
  { id: "headline", kind: "rate", keys: { bank_today: "first_contact_resolution", replay: "complete_intake" },
    titles: { bank_today: "Resolved at first contact (FCR)", replay: "Complete intake at first contact" } },
  { id: "days_to_receipt", kind: "days", keys: { bank_today: "days_to_receipt", replay: "days_to_receipt" },
    titles: { bank_today: "Days to a first response", replay: "Days to a receipt with a legal deadline" } },
  { id: "escalated", kind: "rate", keys: { bank_today: "escalated", replay: "escalated" },
    titles: { bank_today: "Escalated", replay: "Handed to a person at intake" } },
  { id: "outside_sla_at_intake", kind: "rate", keys: { bank_today: "outside_sla_at_intake", replay: "outside_sla_at_intake" },
    titles: { bank_today: "Outside SLA", replay: "Opened without a legal deadline" } },
  { id: "resolution_days", kind: "days", keys: { bank_today: "resolution_days" }, titles: { bank_today: "Days to the final resolution" } },
];

export type Point = { month: string; value: number | null; detail: [string, string][] };
export type Secondary = { title: string; point: Point; note: string };
export type Chart = {
  metric: Metric; title: string; label: string; note: string; total: Point; points: Point[]; scaleMax: number;
  secondary: Secondary | null;
};
export type OpsState = { kind: "pending"; title: string; missing: string; detail: string } | { kind: "ready"; series: Series; charts: Chart[] };

const int = (n: number) => n.toLocaleString("en-US");
export const pct = (v: number | null, digits = 1) => (v === null ? "no value" : `${(v * 100).toFixed(v > 0 && v < 0.001 ? 2 : digits)}%`);
export const days = (v: number | null) => (v === null ? "no value" : `${v.toFixed(1)} d`);

function point(kind: Metric["kind"], key: string, m: Month): Point {
  if (kind === "rate") {
    const r = m[key] as Rate;
    const detail: [string, string][] = [["Share", pct(r.value)], ["Numerator", int(r.numerator)], ["Denominator", int(r.denominator)]];
    return { month: m.month, value: r.value, detail: r.constant ? [...detail, ["Per month", "same period value"]] : detail };
  }
  const d = m[key] as Days | undefined;
  const detail: [string, string][] = [["Median", days(d?.p50 ?? null)], ["n", int(d?.n ?? 0)]];
  if (d?.mean !== undefined) detail.splice(1, 0, ["Mean", days(d.mean)]);
  if (d?.missing !== undefined) detail.push(["Without a value", int(d.missing)]);
  return { month: m.month, value: d?.p50 ?? null, detail };
}

/** The charts of one series; the axis of each slot spans both series, so switching keeps the scale (AC-07). */
export function charts(series: Series, all: OpsSeries): Chart[] {
  const both = [all.bank_today, all.replay].filter((s): s is Series => s !== null);
  return METRICS.filter((metric) => metric.keys[series.key] && metric.keys[series.key]! in series.total).map((metric) => {
    const key = metric.keys[series.key]!;
    const values = both.flatMap((s) => {
      const k = metric.keys[s.key];
      return k && k in s.total ? [...s.months, s.total].map((m) => point(metric.kind, k, m).value ?? 0) : [];
    });
    const top = Math.max(...values, metric.kind === "rate" ? 0.01 : 1);
    const safe = metric.id === "headline" && "safe_automated_resolution" in series.total;
    return {
      metric, title: metric.titles[series.key]!, label: series.label, note: series.notes[key] ?? "",
      total: point(metric.kind, key, series.total), points: series.months.map((m) => point(metric.kind, key, m)), scaleMax: top,
      secondary: safe ? { title: "Safe automated resolution", point: point("rate", "safe_automated_resolution", series.total),
                          note: series.notes.safe_automated_resolution ?? "" } : null,
    };
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
  return [...chart.points, { ...chart.total, month: `${chart.points.length} months` }].map((p) => [p.month, ...p.detail.map(([, v]) => v)]);
}
