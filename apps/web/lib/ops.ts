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

/** What the shared detail panel shows for a chart or a note (plan §14): method, source query, window, label, link. */
export type Detail = { title: string; description: string; method: string[]; source: string; window: string; label: string; href: string;
  /** A second link under the method (for example the dataset limitation). */ extra?: { label: string; href: string } };

const METHOD: Record<SeriesKey, string> = {
  bank_today: "The bank's own unrecognized and wrongful charge complaints, chosen with the rules of the pitch query " +
    "p01 and counted by the month they were created. The figures are the dataset's own records.",
  replay: "Real approved card charges from the dataset, as many each month as the bank's complaints of that kind. A " +
    "customer reports each charge the next day in a written message that names the amount, the date and the merchant. " +
    "The rules engine reads it, the transaction search finds the charge and the policy decides, with no language " +
    "model. The cases go into a test store and the operational job measures them.",
};
const SOURCE: Record<SeriesKey, string> = {
  bank_today: "queries/ops/asis_monthly.sql",
  replay: "queries/ops/replay_sample.sql · data/ops/replay.py",
};
const monthLabel = (m: string) => new Date(`${m}-15T00:00:00Z`).toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
export const windowText = (w: [string, string]) => `${monthLabel(w[0])} to ${monthLabel(w[1])} (${w[0]} to ${w[1]})`;

/** The panel of one chart: the series' method, then the figure's own definition. */
export function chartDetail(chart: Chart, series: Series): Detail {
  return { title: chart.title, description: series.name, method: [METHOD[series.key], chart.note].filter(Boolean),
           source: SOURCE[series.key], window: windowText(series.window), label: series.label,
           href: series.key === "bank_today" ? DETAIL.method : DETAIL.replay };
}

/** The panel of a pending position: what is missing and what will fill it. */
export function pendingDetail(state: { title: string; missing: string; detail: string }, all: OpsSeries | undefined): Detail {
  return { title: state.title, description: "No figure yet", method: [state.missing,
           "Live will read the cases of real conversations from the database through the same operational job; until "
           + "then the page shows no number for it."],
           source: "data/ops (spec 14 T5, the Postgres source)", window: all ? windowText(all.window) : "",
           label: "none yet", href: state.detail };
}

/** The panel of the section's note on the dataset limitation. */
export function limitationDetail(all: OpsSeries | undefined): Detail {
  return {
    title: "Why the bank's complaints are not replayed", description: "Dataset limitation",
    method: ["The dataset does not link a complaint to the charge it is about. Of the 8,129 unrecognized or wrongful " +
             "charge complaints from June 2025 to May 2026, only about one in five came from a customer with any card " +
             "charge in the 30 days before, and no claimed amount matched one. Replayed as they are, the system would " +
             "ask which charge in nine contacts out of ten, which describes the data rather than the system.",
             "So the simulation uses real card charges with a written message, and the bank's complaints keep only " +
             "their own figures. The window starts in January 2026 because the repository has verified bank holiday " +
             "calendars for 2026 only."],
    source: "queries/ops/replay_sample.sql · data/ops/replay.py", window: all ? windowText(all.window) : "",
    label: "[simulated]", href: DETAIL.limitation,
  };
}

/**
 * One chart slot. A "comparison" slot is filled by both series (the pairs of `data.series.compare`) and shares one
 * axis; a "context" slot belongs to one series only, with its own definition, and is never drawn next to the other.
 */
export type Metric = {
  id: string; kind: "rate" | "days"; role: "comparison" | "context";
  keys: Partial<Record<SeriesKey, string>>; titles: Partial<Record<SeriesKey, string>>;
};
export const METRICS: Metric[] = [
  { id: "headline", kind: "rate", role: "comparison", keys: { bank_today: "first_contact_resolution", replay: "complete_intake" },
    titles: { bank_today: "Resolved at first contact (FCR)", replay: "Complete intake at first contact (upper bound)" } },
  { id: "days_to_receipt", kind: "days", role: "comparison", keys: { bank_today: "days_to_receipt", replay: "days_to_receipt" },
    titles: { bank_today: "Days to a first response (proxy)", replay: "Days to a receipt with a legal deadline" } },
  { id: "handed_to_analyst", kind: "rate", role: "context", keys: { replay: "handed_to_analyst" },
    titles: { replay: "Handed to an analyst with evidence and a legal deadline" } },
  { id: "opened_without_deadline", kind: "rate", role: "context", keys: { replay: "opened_without_deadline" },
    titles: { replay: "Cases opened without a legal deadline" } },
  { id: "escalated", kind: "rate", role: "context", keys: { bank_today: "escalated" }, titles: { bank_today: "Escalated inside the bank" } },
  { id: "outside_sla", kind: "rate", role: "context", keys: { bank_today: "outside_sla_at_intake" },
    titles: { bank_today: "Flagged outside SLA by the bank" } },
  { id: "resolution_days", kind: "days", role: "context", keys: { bank_today: "resolution_days" },
    titles: { bank_today: "Days to the final resolution" } },
];

export type Point = { month: string; value: number | null; detail: [string, string][] };
export type Secondary = { title: string; value: string; note: string };
export type Chart = {
  metric: Metric; title: string; label: string; note: string; total: Point; points: Point[]; scaleMax: number;
  secondary: Secondary[];
};
export type OpsState = { kind: "pending"; title: string; missing: string; detail: string } | { kind: "ready"; series: Series; charts: Chart[] };

const int = (n: number) => n.toLocaleString("en-US");
export const pct = (v: number | null, digits = 1) => (v === null ? "no value" : `${(v * 100).toFixed(v > 0 && v < 0.001 ? 2 : digits)}%`);
export const days = (v: number | null) => (v === null ? "no value" : `${v.toFixed(1)} d`);

/** The receipt is given in the first conversation: a median of 0 days reads "Same contact", not "0.0 d" (AC-07). */
export const SAME_CONTACT = "Same contact";
export const SAME_CONTACT_NOTE = "the receipt with its legal deadline is given in the first conversation";
export const daysText = (key: string, v: number | null) => (key === "days_to_receipt" && v === 0 ? SAME_CONTACT : days(v));

/** The short intro of the Operation section (AC-09: two lines, the rest sits in the detail panel). */
export const OPS_INTRO =
  "Bank today is the bank's own unrecognized and wrongful charge complaints, January to May 2026. With Nick of Time is the same number of contacts a month, taken in by the system over real card charges with no language model.";

/** The panel behind the intro's "Detail →": the replay, the window, the two headline figures and the limitation. */
export function introDetail(all: OpsSeries | undefined): Detail {
  return {
    title: "How the Operation figures are made", description: "Bank today and With Nick of Time",
    method: [METHOD.replay,
             "The two headline figures measure different things. The bank's first contact resolution means the complaint was resolved in the first call. Ours means complete intake: a case on the right charge, its legal deadline and the evidence handed to a person, who then decides.",
             "Ours is an upper bound, because the message names the charge exactly as the statement shows it, while real customers misremember amounts and dates. The simulation does not model the final resolution time, which a person decides.",
             "The window starts in January 2026 because the repository has verified bank holiday calendars for 2026 only; without them no legal deadline is computed."],
    source: SOURCE.replay, window: all ? windowText(all.window) : "", label: "[simulated]", href: DETAIL.method,
    extra: { label: "Why the bank's complaints are not replayed →", href: DETAIL.limitation },
  };
}

function point(kind: Metric["kind"], key: string, m: Month): Point {
  if (kind === "rate") {
    const r = m[key] as Rate;
    const detail: [string, string][] = [["Share", pct(r.value)], ["Numerator", int(r.numerator)], ["Denominator", int(r.denominator)]];
    return { month: m.month, value: r.value, detail: r.constant ? [...detail, ["Per month", "same period value"]] : detail };
  }
  const d = m[key] as Days | undefined;
  const detail: [string, string][] = [["Median", daysText(key, d?.p50 ?? null)], ["n", int(d?.n ?? 0)]];
  if (d?.mean !== undefined) detail.splice(1, 0, ["Mean", daysText(key, d.mean)]);
  if (d?.missing !== undefined) detail.push(["Without a value", int(d.missing)]);
  return { month: m.month, value: d?.p50 ?? null, detail };
}

type Sensitivity = { variant: string; named: Record<string, Rate>; amount_and_date: Record<string, Rate> };

/** Small figures under the replay's headline: safe automated resolution (as "k of n") and the no-merchant variant. */
function secondary(series: Series): Secondary[] {
  const out: Secondary[] = [];
  const safe = series.total.safe_automated_resolution as Rate | undefined;
  if (safe) out.push({ title: "Safe automated resolution", value: `${int(safe.numerator)} of ${int(safe.denominator)}`,
                       note: series.notes.safe_automated_resolution ?? "" });
  const sens = (series as Series & { sensitivity?: Sensitivity }).sensitivity;
  if (sens) {
    const [a, b] = [sens.named, sens.amount_and_date];
    out.push({ title: "If the message names only the amount and the date",
               value: `complete intake ${pct(b.complete_intake.value)}, asks ${pct(b.asked.value)}`,
               note: `With the merchant named too: complete intake ${pct(a.complete_intake.value)}, asks ${pct(a.asked.value)}. Same contacts and same charges; only the message changes.` });
  }
  return out;
}

/** The charts of one series. A comparison slot's axis spans both series, so switching keeps the scale (AC-07); a
 * context slot's axis is its own series only. */
export function charts(series: Series, all: OpsSeries): Chart[] {
  const both = [all.bank_today, all.replay].filter((s): s is Series => s !== null);
  return METRICS.filter((metric) => metric.keys[series.key] && metric.keys[series.key]! in series.total).map((metric) => {
    const key = metric.keys[series.key]!;
    const scope = metric.role === "comparison" ? both : [series];
    const values = scope.flatMap((s) => {
      const k = metric.keys[s.key];
      return k && k in s.total ? [...s.months, s.total].map((m) => point(metric.kind, k, m).value ?? 0) : [];
    });
    const top = Math.max(...values, metric.kind === "rate" ? 0.01 : 1);
    return {
      metric, title: metric.titles[series.key]!, label: series.label, note: series.notes[key] ?? "",
      total: point(metric.kind, key, series.total), points: series.months.map((m) => point(metric.kind, key, m)), scaleMax: top,
      secondary: metric.id === "headline" ? secondary(series) : [],
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
