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
export type LivePending = { key: "live"; name: string; status: "pending"; message: string; reason: string };
/** Public demo traffic (spec 14 §7.4, T5; the lead's reading of 2026-10-06): cases per UTC day, in both modes. */
export type ModeKey = "live" | "replay";
export type LiveDay = {
  day: string; cases: number; receipt_rate: Rate; escalation_rate: Rate; automated_rate: Rate; unsafe_outcomes: number;
  cost_per_case: number | null; latency_p95_ms: number | null; denials: number; cases_by_mode: Record<ModeKey, number>;
};
export type LiveMode = {
  cases: number; receipt_rate: Rate; escalation_rate: Rate; automated_rate: Rate; unsafe_outcomes: number;
  demo_sessions: number; synthetic_charges: number;
};
export type LiveTotal = Omit<LiveDay, "day" | "cases_by_mode"> & {
  day: "total"; cost_usd: number; demo_sessions: number; cases_without_demo_session: number; synthetic_charges: number;
  by_mode: Record<ModeKey, LiveMode>;
};
export type LiveReady = {
  key: "live"; name: string; status: "ready"; label: string; message: string; reason: string; source: string;
  window: [string, string]; as_of: string | null; days: LiveDay[]; total: LiveTotal;
  feedback: { decided: number; agreed: number }; notes: Record<string, string>;
};
export type Live = LivePending | LiveReady;
export type OpsSeries = { window: [string, string]; bank_today: Series | null; replay: Series | null; live: Live };

export const POSITIONS = [
  { key: "bank_today", label: "Bank today" },
  { key: "replay", label: "With Nick of Time (simulated)" },
  { key: "live", label: "Public demo traffic" },
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
  live: `${SPEC14}#115-live-the-postgres-source-t5-make-ops-live`,
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
           "Public demo traffic will read the cases of the deployed app's demo sessions from the database through the "
           + "same operational job; until then the page shows no number for it."],
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
export type OpsState =
  | { kind: "pending"; title: string; missing: string; detail: string }
  | { kind: "ready"; series: Series; charts: Chart[] }
  | { kind: "live"; view: LiveView };

const int = (n: number) => n.toLocaleString("en-US");
export const pct = (v: number | null, digits = 1) => (v === null ? "no value" : `${(v * 100).toFixed(v > 0 && v < 0.001 ? 2 : digits)}%`);
export const days = (v: number | null) => (v === null ? "no value" : `${v.toFixed(1)} d`);

/** The receipt is given in the first conversation: a median of 0 days reads "Same contact", not "0.0 d" (AC-07). */
export const SAME_CONTACT = "Same contact";
export const SAME_CONTACT_NOTE = "the receipt with its legal deadline is given in the first conversation";
export const daysText = (key: string, v: number | null) => (key === "days_to_receipt" && v === 0 ? SAME_CONTACT : days(v));

/** The short intro of the Operation section (AC-09: two lines, the rest sits in the detail panel). */
export const OPS_INTRO =
  "Bank today: the bank's own unrecognized and wrongful charge complaints, January to May 2026; With Nick of Time: the same volume taken in by the system over real card charges, with no language model.";

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

/** spec 12 AC-04: a missing file or series shows "Results pending" with what is missing and no figure. Public demo
 * traffic draws its figures only when its `status` is "ready". */
export function opsState(file: { data?: { series?: OpsSeries } } | null, position: Position): OpsState {
  const all = file?.data?.series;
  if (position === "live") {
    const live = all?.live;
    if (live?.status === "ready") return { kind: "live", view: liveView(live) };
    return { kind: "pending", title: live?.message ?? "Pending: no public demo traffic yet",
             missing: live?.reason ?? "spec 14 T5 (the Postgres source) has not run on the deployed app's demo traffic",
             detail: DETAIL.live };
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

// ---------- Public demo traffic (the Live position) ----------

export type LiveCard = { id: string; title: string; value: string; sub: string };
export type LiveBar = { day: string; cases: number; byMode: Record<ModeKey, number>; detail: [string, string][] };
export type LiveModeRow = { mode: ModeKey; title: string; cases: number; share: number; text: string; note: string };
export type LiveView = {
  live: LiveReady; cards: LiveCard[]; bars: LiveBar[]; scaleMax: number; modes: LiveModeRow[]; line: string;
  head: string[]; rows: string[][]; footer: string;
};

/** The one plain line under the figures; the method sits behind "Detail →". */
export const LIVE_LINE = "Cases visitors opened on the public demo, in both modes: an illustration, not a measurement.";
export const MODE_TITLE: Record<ModeKey, string> = { live: "Live mode", replay: "Replay mode" };
const MODE_NOTE: Record<ModeKey, string> = {
  live: "today's date, synthetic charges",
  replay: "the dataset's historical state, demo date 1 June 2026",
};
const rateText = (r: Rate) => (r.denominator ? `${pct(r.value)} (${int(r.numerator)} of ${int(r.denominator)})` : "no value");
const LIVE_HEAD = ["Cases", MODE_TITLE.live, MODE_TITLE.replay, "Receipt with a legal deadline", "Handed to an analyst", "Unsafe outcomes"];
const plural = (n: number, word: string) => `${int(n)} ${n === 1 ? word : `${word}s`}`;
export const dayName = (d: string) =>
  new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

function liveDetailRows(d: { cases: number; receipt_rate: Rate; escalation_rate: Rate; unsafe_outcomes: number },
                        byMode: Record<ModeKey, number>): [string, string][] {
  const values = [int(d.cases), int(byMode.live), int(byMode.replay), rateText(d.receipt_rate), rateText(d.escalation_rate),
                  int(d.unsafe_outcomes)];
  return LIVE_HEAD.map((h, i) => [h, values[i]]);
}

/** The Live position's figures, read from the file only: four cards, the per-day columns, the mode breakdown and the
 * table (spec 12 AC-02; AC-07: the table holds exactly the values of the columns' tooltips). */
export function liveView(live: LiveReady): LiveView {
  const t = live.total;
  const n = live.days.length;
  const byMode = { live: t.by_mode.live?.cases ?? 0, replay: t.by_mode.replay?.cases ?? 0 };
  const bars = live.days.map((d) => ({ day: d.day, cases: d.cases, byMode: d.cases_by_mode, detail: liveDetailRows(d, d.cases_by_mode) }));
  const share = (r: Rate) => `${int(r.numerator)} of ${plural(r.denominator, "case")}`;
  return {
    live,
    cards: [
      { id: "cases", title: "Cases", value: int(t.cases), sub: `${plural(t.demo_sessions, "demo session")} over ${plural(n, "day")}` },
      { id: "receipt", title: "Receipt with a legal deadline", value: pct(t.receipt_rate.value), sub: share(t.receipt_rate) },
      { id: "handed", title: "Handed to an analyst", value: pct(t.escalation_rate.value), sub: share(t.escalation_rate) },
      { id: "unsafe", title: "Unsafe outcomes", value: int(t.unsafe_outcomes), sub: "the auditor's lifecycle check" },
    ],
    bars,
    scaleMax: Math.max(1, ...live.days.map((d) => d.cases)),
    modes: (["live", "replay"] as const).map((mode) => ({
      mode, title: MODE_TITLE[mode], cases: byMode[mode], share: t.cases ? byMode[mode] / t.cases : 0,
      text: plural(byMode[mode], "case"), note: MODE_NOTE[mode],
    })),
    line: LIVE_LINE,
    head: ["Day", ...LIVE_HEAD],
    rows: [...bars.map((b) => [b.day, ...b.detail.map(([, v]) => v)]),
           [plural(n, "day"), ...liveDetailRows(t, byMode).map(([, v]) => v)]],
    footer: `${live.source} · ${live.window.join(" to ")}${live.as_of ? ` · snapshot ${live.as_of}` : ""}`,
  };
}

/** The panel behind the Live position's "Detail →": what counts, the labels, the day, the modes and each figure. */
export function liveDetail(live: LiveReady): Detail {
  const notes = live.notes;
  return {
    title: live.message, description: live.name,
    method: [notes.cases, live.reason, notes.day, notes.by_mode, notes.receipt_rate, notes.escalation_rate,
             notes.unsafe_outcomes].filter(Boolean),
    source: live.source, window: `${dayName(live.window[0])} to ${dayName(live.window[1])} (${live.window.join(" to ")})`,
    label: live.label, href: DETAIL.live,
  };
}
