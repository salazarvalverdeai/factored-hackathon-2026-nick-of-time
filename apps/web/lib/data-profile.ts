// "The data at a glance" on /data (spec 12 AC-03, AC-04, AC-07): the committed outputs of queries/data/d02..d06, read
// from data_quality.json `data.profile`, shaped for the charts. Pure, so `npm test` covers it. It only regroups and
// divides the counts of each row for display (shares, axis ticks); every figure is a `[data]` row of the file.
import { repoUrl, type Detail } from "./pipelines.ts";

export type Block<R> = { query: string; label: string; rows: R[] };

export type D02Row = {
  month: string;
  product_type: string;
  n_transactions: number;
  n_approved: number;
  n_declined: number;
  n_pending: number;
  n_reversed: number;
};
export type D03Row = { country: string; segment: string; n_customers: number; n_transactions: number };
export type D04Row = { country: string; n_card_transactions: number; n_null: number; n_lt30: number; n_30_49: number; n_ge50: number };
export type D05Row = { month: string; category: string; n_complaints: number; n_w3: number; n_month: number; n_w3_month: number; pct_w3_month: number };
export type D06Row = { table_name: string; kind: string; name: string; numerator: number; denominator: number; pct: number };

export type Profile = {
  d02?: Block<D02Row> | null;
  d03?: Block<D03Row> | null;
  d04?: Block<D04Row> | null;
  d05?: Block<D05Row> | null;
  d06?: Block<D06Row> | null;
};

export const PROFILE_KEYS = ["d02", "d03", "d04", "d05", "d06"] as const;
export type ProfileKey = (typeof PROFILE_KEYS)[number];

export const int = (n: number) => n.toLocaleString("en-US");
export const pct = (n: number, digits = 1) => `${n.toFixed(digits)}%`;
const share = (n: number, of: number) => (of > 0 ? (100 * n) / of : 0);
/** Axis numbers: 120000 → "120k". */
export const compact = (n: number) => (n >= 1e6 ? `${+(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${+(n / 1e3).toFixed(1)}k` : String(n));

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2025-06" → "Jun". */
export const monthName = (ym: string) => MONTHS[Number(ym.slice(5, 7)) - 1] ?? ym;
/** "2025-06" → "Jun 2025". */
export const monthLong = (ym: string) => `${monthName(ym)} ${ym.slice(0, 4)}`;

/** A clean axis: the smallest 1 / 2 / 2.5 / 5 × 10^k step that covers `max` in at most `count` + 1 steps. */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0, 1];
  const mag = 10 ** Math.floor(Math.log10(max / count));
  const step = [1, 2, 2.5, 5, 10, 20].map((m) => m * mag).find((s) => Math.ceil(max / s) <= count + 1) ?? 20 * mag;
  const top = Math.ceil(max / step) * step;
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => Math.round(i * step * 1e6) / 1e6);
}

const ready = <R>(block: Block<R> | null | undefined): block is Block<R> => !!block && Array.isArray(block.rows) && block.rows.length > 0;

/** The "Detail →" of a chart: what it shows, how, the query path (mono) and the label; the link reads the query. */
function detail(block: { query: string; label: string }, meaning: string, method: string): Detail {
  return { meaning, method, source: block.query, label: block.label, spec: repoUrl(block.query) };
}

// ---------------------------------------------------------------- d02: transactions per month by product type
export const PRODUCT_TYPES = [
  { key: "credit", label: "Credit card" },
  { key: "debit", label: "Debit card" },
  { key: "other", label: "Other products" },
] as const;
export const STATUSES = [
  { key: "approved", label: "Approved" },
  { key: "declined", label: "Declined" },
  { key: "pending", label: "Pending" },
  { key: "reversed", label: "Reversed" },
] as const;
type StatusKey = (typeof STATUSES)[number]["key"];
type StatusShare = { key: StatusKey; label: string; n: number; pct: number };

const statusShares = (rows: D02Row[]): StatusShare[] => {
  const total = rows.reduce((a, r) => a + r.n_transactions, 0);
  const n: Record<StatusKey, number> = {
    approved: rows.reduce((a, r) => a + r.n_approved, 0),
    declined: rows.reduce((a, r) => a + r.n_declined, 0),
    pending: rows.reduce((a, r) => a + r.n_pending, 0),
    reversed: rows.reduce((a, r) => a + r.n_reversed, 0),
  };
  return STATUSES.map((s) => ({ ...s, n: n[s.key], pct: share(n[s.key], total) }));
};

export type VolumeMonth = { month: string; total: number; parts: { key: string; label: string; n: number; pct: number }[]; status: StatusShare[] };

export function volumeChart(block: Block<D02Row> | null | undefined) {
  if (!ready(block)) return null;
  const months = [...new Set(block.rows.map((r) => r.month))].sort();
  const data: VolumeMonth[] = months.map((month) => {
    const rows = block.rows.filter((r) => r.month === month);
    const total = rows.reduce((a, r) => a + r.n_transactions, 0);
    const parts = PRODUCT_TYPES.map((t) => {
      const n = rows.filter((r) => r.product_type === t.key).reduce((a, r) => a + r.n_transactions, 0);
      return { key: t.key, label: t.label, n, pct: share(n, total) };
    });
    return { month, total, parts, status: statusShares(rows) };
  });
  const total = data.reduce((a, m) => a + m.total, 0);
  const cards = block.rows.filter((r) => r.product_type !== "other").reduce((a, r) => a + r.n_transactions, 0);
  const ticks = niceTicks(Math.max(...data.map((m) => m.total)));
  return {
    label: block.label,
    query: block.query,
    months: data,
    total,
    cardShare: share(cards, total),
    status: statusShares(block.rows),
    ticks,
    max: ticks[ticks.length - 1],
    window: [months[0], months[months.length - 1]] as const,
    table: {
      head: ["Month", ...PRODUCT_TYPES.map((t) => t.label), "Total", ...STATUSES.map((s) => s.label)],
      rows: data.map((m) => [monthLong(m.month), ...m.parts.map((p) => int(p.n)), int(m.total), ...m.status.map((s) => pct(s.pct))]),
    },
    detail: detail(
      block,
      "How many transactions gold holds per month, split by the product they were made with, and how many were approved, declined, pending or reversed.",
      "Gold transactions of the 12-month window, joined to their product: debit and credit cards apart, every other product (accounts, loans, investment, insurance) as other. Status shares are counts over the month's transactions.",
    ),
  };
}

// ---------------------------------------------------------------- d03: customers and transactions per country
export const COUNTRY_NAMES: Record<string, string> = { MX: "Mexico", CO: "Colombia", AR: "Argentina", unknown: "Unknown", all: "All countries" };
export const SEGMENTS = ["Basic", "Plus", "Premium", "Student"] as const;

export function countryChart(block: Block<D03Row> | null | undefined) {
  if (!ready(block)) return null;
  const totals = block.rows.filter((r) => r.segment === "all" && (r.country !== "unknown" || r.n_customers + r.n_transactions > 0));
  const countries = totals
    .map((t) => {
      const segs = block.rows.filter((r) => r.country === t.country && r.segment !== "all");
      return {
        country: t.country,
        name: COUNTRY_NAMES[t.country] ?? t.country,
        customers: t.n_customers,
        transactions: t.n_transactions,
        segments: segs.map((s) => ({
          segment: s.segment,
          customers: s.n_customers,
          transactions: s.n_transactions,
          pctCustomers: share(s.n_customers, t.n_customers),
        })),
      };
    })
    .sort((a, b) => b.customers - a.customers);
  const customers = countries.reduce((a, c) => a + c.customers, 0);
  const transactions = countries.reduce((a, c) => a + c.transactions, 0);
  const segmentNames = [...new Set(block.rows.filter((r) => r.segment !== "all").map((r) => r.segment))];
  const segmentMix = segmentNames.map((segment) => {
    const n = block.rows.filter((r) => r.segment === segment).reduce((a, r) => a + r.n_customers, 0);
    return { segment, n, pct: share(n, customers) };
  });
  const unknown = block.rows.find((r) => r.country === "unknown" && r.segment === "all");
  return {
    label: block.label,
    query: block.query,
    countries,
    customers,
    transactions,
    unknownTransactions: unknown?.n_transactions ?? 0,
    segmentMix,
    maxCustomers: Math.max(...countries.map((c) => c.customers)),
    maxTransactions: Math.max(...countries.map((c) => c.transactions)),
    table: {
      head: ["Country", "Segment", "Customers", "Transactions"],
      rows: countries.flatMap((c) => [
        [c.name, "All", int(c.customers), int(c.transactions)],
        ...c.segments.map((s) => [c.name, s.segment, int(s.customers), int(s.transactions)]),
      ]),
    },
    detail: detail(
      block,
      "Where the bank's customers live and how many transactions they make, by country and by segment.",
      "Gold customers counted by country and segment; each transaction is attributed to the customer who owns its product. Transactions with no resolved customer would show as unknown.",
    ),
  };
}

// ---------------------------------------------------------------- d04: the bank's fraud_score bands per country
export const SCORE_BANDS = [
  { key: "null", label: "No score", zone: "Human zone: a person decides." },
  { key: "lt30", label: "Below 30", zone: "Human zone: a person decides." },
  { key: "30_49", label: "30 to 49", zone: "Medium zone: the customer confirms first." },
  { key: "ge50", label: "50 or more", zone: "High zone: the card is blocked and verified." },
] as const;
export type BandKey = (typeof SCORE_BANDS)[number]["key"];

export function scoreChart(block: Block<D04Row> | null | undefined) {
  if (!ready(block)) return null;
  const order = ["MX", "CO", "AR", "unknown", "all"];
  const rows = [...block.rows].filter((r) => r.n_card_transactions > 0).sort((a, b) => order.indexOf(a.country) - order.indexOf(b.country));
  const countries = rows.map((r) => {
    const n: Record<BandKey, number> = { null: r.n_null, lt30: r.n_lt30, "30_49": r.n_30_49, ge50: r.n_ge50 };
    const bands = SCORE_BANDS.map((b) => ({ ...b, n: n[b.key], pct: share(n[b.key], r.n_card_transactions), per10k: (1e4 * n[b.key]) / r.n_card_transactions }));
    const upper = r.n_30_49 + r.n_ge50;
    return { country: r.country, name: COUNTRY_NAMES[r.country] ?? r.country, total: r.n_card_transactions, bands, upper, upperPct: share(upper, r.n_card_transactions) };
  });
  const all = countries.find((c) => c.country === "all") ?? countries[countries.length - 1];
  const nullBand = all.bands.find((b) => b.key === "null")!;
  return {
    label: block.label,
    query: block.query,
    countries,
    all,
    nullPct: nullBand.pct,
    upperPct: all.upperPct,
    maxPer10k: Math.max(...countries.flatMap((c) => c.bands.filter((b) => b.key === "30_49" || b.key === "ge50").map((b) => b.per10k))),
    table: {
      head: ["Country", "Card transactions", ...SCORE_BANDS.map((b) => b.label)],
      rows: countries.map((c) => [c.name, int(c.total), ...c.bands.map((b) => `${int(b.n)} (${pct(b.pct, 3)})`)]),
    },
    detail: detail(
      block,
      "The score the bank gives each card transaction, grouped in the bands the policy uses. It is a score, not a fraud label: this query never reads the label.",
      "Gold card transactions (debit and credit), by the country of the customer who owns the card. Bands as in contracts/policies.yaml: below 30, 30 to 49, 50 or more; a transaction with no score is counted apart.",
    ),
  };
}

/** "0.067%": two decimals of significance for shares under 1%, so the tiny upper bands read as more than zero. */
export function smallPct(n: number): string {
  if (n === 0) return "0%";
  if (n >= 1) return pct(n);
  const digits = Math.min(4, Math.max(1, 1 - Math.floor(Math.log10(n))));
  return `${n.toFixed(digits)}%`;
}

// ---------------------------------------------------------------- d05: complaints per month by category, W3 share
/** The two categories W3 is drawn from (rules CMP-01..03, the same as /analytics); the other three are grouped. */
export const COMPLAINT_GROUPS = [
  { key: "Fees", label: "Fees", categories: ["Fees"] },
  { key: "Transactions", label: "Transactions", categories: ["Transactions"] },
  { key: "other", label: "Branch, Service, Technical", categories: ["Branch", "Service", "Technical"] },
] as const;

export function complaintChart(block: Block<D05Row> | null | undefined) {
  if (!ready(block)) return null;
  const months = [...new Set(block.rows.map((r) => r.month))].sort();
  const data = months.map((month, i) => {
    const rows = block.rows.filter((r) => r.month === month);
    const { n_month, n_w3_month, pct_w3_month } = rows[0];
    // A category the query adds later falls into the grouped "other" stack, so the columns always sum to the month.
    const groupOf = (category: string) => (category === "Fees" || category === "Transactions" ? category : "other");
    const groups = COMPLAINT_GROUPS.map((g) => ({
      key: g.key,
      label: g.label,
      n: rows.filter((r) => groupOf(r.category) === g.key).reduce((a, r) => a + r.n_complaints, 0),
    }));
    return {
      month,
      total: n_month,
      w3: n_w3_month,
      w3Pct: pct_w3_month,
      groups,
      categories: [...rows].sort((a, b) => a.category.localeCompare(b.category)).map((r) => ({ category: r.category, n: r.n_complaints, w3: r.n_w3 })),
      // The query window starts and ends mid-month (d05_complaints_per_month.sql): the first and last months are partial.
      partial: i === 0 || i === months.length - 1,
    };
  });
  const total = data.reduce((a, m) => a + m.total, 0);
  const w3 = data.reduce((a, m) => a + m.w3, 0);
  const ticks = niceTicks(Math.max(...data.map((m) => m.total)));
  const categories = [...new Set(block.rows.map((r) => r.category))].sort();
  return {
    label: block.label,
    query: block.query,
    months: data,
    total,
    w3,
    w3Pct: share(w3, total),
    ticks,
    max: ticks[ticks.length - 1],
    shareTicks: [0, 25, 50],
    window: [months[0], months[months.length - 1]] as const,
    table: {
      head: ["Month", ...categories, "Total", "W3", "W3 share"],
      rows: data.map((m) => [
        `${monthLong(m.month)}${m.partial ? " (partial)" : ""}`,
        ...categories.map((c) => int(m.categories.find((x) => x.category === c)?.n ?? 0)),
        int(m.total),
        int(m.w3),
        pct(m.w3Pct),
      ]),
    },
    detail: detail(
      block,
      "Every complaint in the dataset per month, by category, and the share that are unrecognized or wrongful charges (W3), the workflow this system handles.",
      "Gold complaints by creation month and category. W3 uses the same rules as /analytics (CMP-01..03): Transactions claims, complaints and requests, and Fees claims and complaints. The share is W3 over all complaints of the month; the first and last months are partial.",
    ),
  };
}

// ---------------------------------------------------------------- d06: data quality per gold table
const FLAG_TEXT: Record<string, string> = {
  qc_future_last_updated: "last update dated in the future",
  qc_label_normalized: "label normalized in silver",
  qc_customer_orphan: "customer not in customers",
  qc_product_orphan: "product not in products",
  qc_product_other_customer: "product of another customer",
  qc_before_product_open: "made before its product was opened",
  qc_future_date: "dated in the future",
  qc_late_arrival: "arrived after its date",
  qc_affected_product_orphan: "affected product not in products",
  qc_affected_product_other_customer: "affected product of another customer",
};
export const flagText = (name: string) => FLAG_TEXT[name] ?? name;

export type QualityItem = { kind: "null" | "flag"; name: string; n: number; of: number; pct: number };

export function qualityChart(block: Block<D06Row> | null | undefined) {
  if (!ready(block)) return null;
  const tables = [...new Set(block.rows.map((r) => r.table_name))].map((table) => {
    const rows = block.rows.filter((r) => r.table_name === table);
    const count = rows.find((r) => r.kind === "rows")?.numerator ?? rows[0]?.denominator ?? 0;
    const items: QualityItem[] = rows
      .filter((r) => r.kind === "null" || r.kind === "flag")
      .map((r) => ({ kind: r.kind as QualityItem["kind"], name: r.name, n: r.numerator, of: r.denominator, pct: share(r.numerator, r.denominator) }));
    return {
      table,
      rows: count,
      found: items.filter((i) => i.n > 0).sort((a, b) => b.pct - a.pct),
      cleanNull: items.filter((i) => i.kind === "null" && i.n === 0).map((i) => i.name),
      cleanFlag: items.filter((i) => i.kind === "flag" && i.n === 0).map((i) => i.name),
      checked: items.length,
    };
  });
  const rows = tables.reduce((a, t) => a + t.rows, 0);
  const checked = tables.reduce((a, t) => a + t.checked, 0);
  const clean = tables.reduce((a, t) => a + t.cleanNull.length + t.cleanFlag.length, 0);
  return {
    label: block.label,
    query: block.query,
    tables,
    rows,
    checked,
    clean,
    table: {
      head: ["Table", "Kind", "Column or flag", "Rows", "Of", "Share"],
      rows: block.rows.filter((r) => r.kind !== "rows").map((r) => [r.table_name, r.kind === "null" ? "null" : "flag", r.name, int(r.numerator), int(r.denominator), pct(share(r.numerator, r.denominator))]),
    },
    detail: detail(
      block,
      "For each gold table: how often a key column is empty, and how many rows each quality check (qc_*) flagged. Flagged rows are kept, never deleted.",
      "Counts over each gold table: rows where a key column is null, and rows where a qc_* flag is true. Personal columns are not profiled; only counts per column name, never values.",
    ),
  };
}

// ---------------------------------------------------------------- the group
const WHAT: Record<ProfileKey, string> = {
  d02: "transactions per month",
  d03: "customers and transactions per country",
  d04: "fraud_score bands",
  d05: "complaints per month",
  d06: "data quality per table",
};

/** spec 12 AC-04: every chart, or "Results pending" with what is missing when the profile or one of its blocks is absent. */
export function dataProfile(profile: Profile | null | undefined) {
  const p = profile ?? {};
  const charts = {
    d02: volumeChart(p.d02),
    d03: countryChart(p.d03),
    d04: scoreChart(p.d04),
    d05: complaintChart(p.d05),
    d06: qualityChart(p.d06),
  };
  const missing = PROFILE_KEYS.filter((k) => charts[k] === null);
  return {
    pending: !profile || missing.length === PROFILE_KEYS.length,
    charts,
    missing: missing.map((k) => ({ key: k, what: WHAT[k], file: `queries/data/${k}_*.csv` })),
  };
}

export type DataProfile = ReturnType<typeof dataProfile>;

/** What a pending chart says: what is missing, and no figure. */
export const pendingHint = (key: ProfileKey) =>
  `data_quality.json has no ${key} block yet (${WHAT[key]}): run the query under queries/data/ and \`python -m data.pipeline report --json\`.`;
