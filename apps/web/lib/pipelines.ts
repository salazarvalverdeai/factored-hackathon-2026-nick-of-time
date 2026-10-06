// The "how it's built" flows of /data, /evaluation and /analytics (spec 12 AC-03, AC-11), as plain data for the shared
// PipelineDiagram and the detail panel. Pure, so `npm test` covers it. The system architecture is not drawn here: it
// lives on /agent.
import { REPO_BLOB } from "./evaluation.ts";

/** What "Detail →" opens in the side panel: the method, its source, the label of its figures and the spec. */
export type Detail = {
  /** One to three plain sentences, no bracket label. */
  method: string;
  /** The query or file the figures come from. */
  source: string;
  label: "[data]" | "[simulated]" | "[projected]";
  /** The repo markdown on GitHub ("Read the spec →"). */
  spec: string;
};

export type PipelineStep = {
  title: string;
  /** One or two plain lines; a bracket label only sits beside a figure. */
  lines: string[];
  /** The detail shown on hover and on keyboard focus. */
  tip: [string, string][];
  note?: string;
  detail: Detail;
  tone?: "source" | "layer" | "output";
};

/** A heading anchor written as GitHub renders it (it keeps "_", which headingSlug drops). */
export const repoUrl = (path: string, anchor?: string) => `${REPO_BLOB}${path}${anchor ? `#${anchor}` : ""}`;

const int = (n: number) => n.toLocaleString("en-US");
const sum = (xs: { rows: number }[]) => xs.reduce((a, t) => a + t.rows, 0);
const REPORT = "data/quality_report.md";
const RUN = "data/gold/run_results.json → data_quality.json";

type Table = { table: string; rows: number; bytes: number | null; files?: number; quarantined?: number };
export type Medallion = {
  layers: { layer: string; note: string; tables: Table[] }[];
  manifest: { gold_version: number; contract_version: string; source_files: number; source_bytes: number };
};

/** spec 12 AC-03: source CSVs → bronze → silver → gold, with the real tables and rows of data_quality.json. */
export function medallionSteps({ layers, manifest }: Medallion): PipelineStep[] {
  const [bronze, silver, gold] = layers;
  const quarantined = silver.tables.reduce((a, t) => a + (t.quarantined ?? 0), 0);
  return [
    { title: "Source CSV files", tone: "source",
      lines: [`${int(manifest.source_files)} files · ${(manifest.source_bytes / 1e6).toFixed(1)} MB [data]`, "The bank's daily deliveries in S3."],
      tip: bronze.tables.map((t) => [t.table, `${int(t.files ?? 0)} files`]),
      detail: { method: "The pipeline lists the dataset bucket and reads each table's CSV partitions; transaction files dated before the 12-month window are not downloaded.", source: "data/pipeline/sources.py", label: "[data]", spec: repoUrl("docs/adr/0004-medallion-pipeline-on-duckdb.md") } },
    { title: "Bronze", tone: "layer",
      lines: [`${bronze.tables.length} tables · ${int(sum(bronze.tables))} rows [data]`, "A faithful copy, all text, with lineage."],
      tip: bronze.tables.map((t) => [t.table, `${int(t.rows)} rows`]), note: bronze.note,
      detail: { method: "Every CSV row is copied as text, with its source file and load time. Nothing is fixed or dropped here.", source: "data/pipeline/bronze.py", label: "[data]", spec: repoUrl(REPORT, "1-summary-by-table") } },
    { title: "Silver", tone: "layer",
      lines: [`${silver.tables.length} tables · ${int(sum(silver.tables))} rows [data]`, "Typed, deduplicated, checked against the contract."],
      tip: [...silver.tables.map((t): [string, string] => [t.table, `${int(t.rows)} rows`]), ["quarantined", int(quarantined)]], note: silver.note,
      detail: { method: "Columns are typed, labels normalized and duplicates resolved by key, then each table is validated with pandera. A row that breaks the contract goes to quarantine.", source: "data/pipeline/silver.py · contracts.py", label: "[data]", spec: repoUrl(REPORT, "4-silver-schema-contracts-pandera") } },
    { title: `Gold v${manifest.gold_version}`, tone: "layer",
      lines: [`${gold.tables.length} tables · ${int(sum(gold.tables))} rows [data]`, "Read-only Parquet; quality flags per row."],
      tip: gold.tables.map((t) => [t.table, `${int(t.rows)} rows`]), note: `contract ${manifest.contract_version}; ${gold.note}`,
      detail: { method: "Gold keeps the 12-month window, adds a quality flag per row and deletes nothing. It is published only if the five contract rules pass, with a new version when a table's hash changes.", source: "data/pipeline/gold.py · data/gold/manifest.json", label: "[data]", spec: repoUrl("contracts/gold_contract.md") } },
  ];
}

/** What reads gold. Fixed by the specs, not by a run. */
export const GOLD_CONSUMERS: PipelineStep[] = [
  { title: "MCP tools at runtime", tone: "output", lines: ["The customer's own transactions, read-only."],
    tip: [["Reads", "transactions_enriched, products, customers"], ["Never", "the fraud label"]],
    detail: { method: "The customer tools load gold Parquet read-only and filter by the customer of the session. The fraud label is not in gold.", source: "apps/mcp/mcp_server/gold.py", label: "[data]", spec: repoUrl("specs/01-integration-contract.md", "63-mcp-server-appsmcp") } },
  { title: "Evaluation cases", tone: "output", lines: ["Demo and scripted cases on real gold state."],
    tip: [["Query", "queries/eval/demo_index.sql"], ["Writes", "eval/demo_index.csv"]],
    detail: { method: "A query lists approved card transactions per country and zone; the demo and the scripted cases are built on them.", source: "queries/eval/demo_index.sql", label: "[data]", spec: repoUrl("specs/09-demo-eval-data.md") } },
  { title: "Analytics queries", tone: "output", lines: ["Policy values and the limits below."],
    tip: [["queries/policy", "implied USD rates"], ["queries/data", "complaint-to-transaction link"]],
    detail: { method: "Versioned SQL runs on gold and its output is committed beside it, so every figure can be rerun.", source: "queries/policy/*.sql · queries/data/*.sql", label: "[data]", spec: repoUrl("queries/README.md") } },
  { title: "Operational lakehouse", tone: "output", lines: ["Joins case events to gold."],
    tip: [["Silver joins", "transaction and customer"], ["Spec", "14"]],
    detail: { method: "The ops job joins each case event to its gold transaction and customer in silver.", source: "data/ops/silver.py", label: "[simulated]", spec: repoUrl("specs/14-ops-lakehouse.md") } },
];

const SPEC14 = "specs/14-ops-lakehouse.md";
/** spec 14 §7: the case records of the system go through their own three layers. */
export const OPS_STEPS: PipelineStep[] = [
  { title: "Bronze", tone: "layer", lines: ["A copy of 8 operational tables, with load time."],
    tip: [["Tables", "cases, case_events, notifications, llm_calls…"], ["Not copied", "sessions, channels, tokens"]],
    detail: { method: "Each operational table is copied as it is, with its load time. The run fails if a row count or the latest timestamp differs from the source.", source: "data/ops/bronze.py", label: "[simulated]", spec: repoUrl(SPEC14, "71-bronze--dataopsbronze") } },
  { title: "Silver", tone: "layer", lines: ["Typed events joined to the gold transaction and customer."],
    tip: [["Tables", "case_events, cases, llm_calls, policy_denials"], ["Checks", "keys, status lists, seq per case"]],
    detail: { method: "Events are typed, checked against their contracts and joined to gold. A row that breaks a contract stays in bronze and is counted.", source: "data/ops/silver.py", label: "[simulated]", spec: repoUrl(SPEC14, "72-silver--dataopssilver") } },
  { title: "Gold", tone: "output", lines: ["KPIs per day, and the analysts' decisions as labels."],
    tip: [["Tables", "ops_kpis, feedback_cases"], ["Manifest", "data/ops/manifest.json"]],
    detail: { method: "Daily KPIs by mode, and the analyst's decision per case as a label. Evaluation runs are left out.", source: "data/ops/gold.py → ops_kpis.json", label: "[simulated]", spec: repoUrl(SPEC14, "73-gold--dataopsgold") } },
];

/** The "Detail →" of each /data card. */
export const DATA_CARDS = {
  medallion: { method: "The diagram reads the layer counts written by the last pipeline run; the page computes nothing.", source: RUN, label: "[data]", spec: repoUrl("docs/adr/0004-medallion-pipeline-on-duckdb.md") },
  versions: { method: "The gold manifest records the version, the contract and the run; the version goes up only when a table's content changes.", source: "data/gold/manifest.json", label: "[data]", spec: repoUrl(REPORT) },
  rules: { method: "Five rules run on every pipeline run before gold is published. If one fails, the previous gold stays.", source: "data/pipeline/gold.py · data/gold/manifest.json", label: "[data]", spec: repoUrl("contracts/gold_contract.md", "verifiable-rules-every-run") },
  checks: { method: "Each check counts the rows it finds over the rows it applies to, and the action taken. Rows are flagged, never deleted.", source: "data/pipeline/checks.py", label: "[data]", spec: repoUrl(REPORT, "3-checks-with-counts") },
  late: { method: "Two labeled deliveries of synthetic test rows go through the same pipeline code, and the counts are compared with the expected ones.", source: "data/fixtures/late_arrival/ → data/_fixture_run/fixture_results.json", label: "[data]", spec: repoUrl("data/fixtures/late_arrival/README.md") },
  ops: { method: "A batch job copies the case store's tables to bronze, cleans and joins them in silver, and writes daily KPIs and analyst labels to gold.", source: "python -m data.ops run", label: "[simulated]", spec: repoUrl(SPEC14) },
  limits: { method: "Disputed-charge complaints created from 2025-07-01 to 2026-05-31 are matched to card transactions of the same customer in the 30 days before. Amounts match when the currency is the same and they differ by at most 2%.", source: "queries/data/d01_complaint_transaction_link.sql", label: "[data]", spec: repoUrl("queries/README.md", "data-dataset-limits") },
} satisfies Record<string, Detail>;

type LinkRow = { metric: string; numerator: number; denominator: number };
const share = (r: LinkRow) => `${((100 * r.numerator) / r.denominator).toFixed(1)}%`;

/** spec 12 AC-03: the dataset limits in plain sentences, each figure from queries/data beside its [data] label. */
export function datasetLimits(rows: LinkRow[]): string[] {
  const get = (metric: string) => rows.find((r) => r.metric === metric);
  const people = get("w3_complainants_with_card_txn_30d"), other = get("other_complaints_with_card_txn_30d");
  const amount = get("w3_claimed_amount_matches_card_txn_2pct"), product = get("w3_affected_product_of_other_customer");
  if (!people || !other || !amount || !product) return [];
  return [
    `Only ${share(people)} of the customers with a disputed-charge complaint (${int(people.numerator)} of ${int(people.denominator)}) [data] had any card transaction in the 30 days before it, no more than for other complaints (${share(other)}) [data].`,
    `Where the complaint states an amount, it matches one of those transactions within ±2% in ${int(amount.numerator)} of ${int(amount.denominator)} complaints [data].`,
    `Every disputed-charge complaint that names an affected product names another customer's product (${int(product.numerator)} of ${int(product.denominator)}) [data].`,
    "So a complaint cannot be linked to the transaction it disputes. The demo and the evaluation cases replay real transactions of the customer instead of complaint records.",
  ];
}
