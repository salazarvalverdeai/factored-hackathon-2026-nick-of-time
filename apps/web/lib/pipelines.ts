// The "how it's built" flows of /data, /evaluation and /analytics (spec 12 AC-03, AC-11), as plain data for the shared
// PipelineDiagram. Pure, so `npm test` covers it. The system architecture is not drawn here: it lives on /agent.
import { REPO_BLOB } from "./evaluation.ts";

export type PipelineStep = {
  title: string;
  /** One or two plain lines; a bracket label only sits beside a figure. */
  lines: string[];
  /** The detail shown on hover and on keyboard focus. */
  tip: [string, string][];
  note?: string;
  /** "Detail →": the markdown on GitHub that defines the step. */
  href: string;
  tone?: "source" | "layer" | "output";
};

/** A heading anchor written as GitHub renders it (it keeps "_", which headingSlug drops). */
export const repoUrl = (path: string, anchor?: string) => `${REPO_BLOB}${path}${anchor ? `#${anchor}` : ""}`;

const int = (n: number) => n.toLocaleString("en-US");
const sum = (xs: { rows: number }[]) => xs.reduce((a, t) => a + t.rows, 0);

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
    { title: "Source CSV files", tone: "source", href: repoUrl("docs/adr/0004-medallion-pipeline-on-duckdb.md"),
      lines: [`${int(manifest.source_files)} files · ${(manifest.source_bytes / 1e6).toFixed(1)} MB [data]`, "The bank's daily deliveries in S3."],
      tip: bronze.tables.map((t) => [t.table, `${int(t.files ?? 0)} files`]) },
    { title: "Bronze", tone: "layer", href: repoUrl("data/quality_report.md", "1-summary-by-table"),
      lines: [`${bronze.tables.length} tables · ${int(sum(bronze.tables))} rows [data]`, "A faithful copy, all text, with lineage."],
      tip: bronze.tables.map((t) => [t.table, `${int(t.rows)} rows`]), note: bronze.note },
    { title: "Silver", tone: "layer", href: repoUrl("data/quality_report.md", "4-silver-schema-contracts-pandera"),
      lines: [`${silver.tables.length} tables · ${int(sum(silver.tables))} rows [data]`, "Typed, deduplicated, checked against the contract."],
      tip: [...silver.tables.map((t): [string, string] => [t.table, `${int(t.rows)} rows`]), ["quarantined", int(quarantined)]], note: silver.note },
    { title: `Gold v${manifest.gold_version}`, tone: "layer", href: repoUrl("contracts/gold_contract.md"),
      lines: [`${gold.tables.length} tables · ${int(sum(gold.tables))} rows [data]`, "Read-only Parquet; quality flags per row."],
      tip: gold.tables.map((t) => [t.table, `${int(t.rows)} rows`]), note: `contract ${manifest.contract_version}; ${gold.note}` },
  ];
}

/** What reads gold. Fixed by the specs, not by a run. */
export const GOLD_CONSUMERS: PipelineStep[] = [
  { title: "MCP tools at runtime", tone: "output", href: repoUrl("specs/01-integration-contract.md", "63-mcp-server-appsmcp"),
    lines: ["The customer's own transactions, read-only."], tip: [["Reads", "transactions_enriched, products, customers"], ["Never", "the fraud label"]] },
  { title: "Evaluation cases", tone: "output", href: repoUrl("specs/09-demo-eval-data.md"),
    lines: ["Demo and scripted cases on real gold state."], tip: [["Query", "queries/eval/demo_index.sql"], ["Writes", "eval/demo_index.csv"]] },
  { title: "Analytics queries", tone: "output", href: repoUrl("queries/README.md"),
    lines: ["Policy values and the limits below."], tip: [["queries/policy", "implied USD rates"], ["queries/data", "complaint-to-transaction link"]] },
  { title: "Operational lakehouse", tone: "output", href: repoUrl("specs/14-ops-lakehouse.md"),
    lines: ["Joins case events to gold."], tip: [["Silver joins", "transaction and customer"], ["Spec", "14"]] },
];

const SPEC14 = "specs/14-ops-lakehouse.md";
/** spec 14 §7: the case records of the system go through their own three layers. */
export const OPS_STEPS: PipelineStep[] = [
  { title: "Bronze", tone: "layer", href: repoUrl(SPEC14, "71-bronze--dataopsbronze"),
    lines: ["A copy of 8 operational tables, with load time."],
    tip: [["Tables", "cases, case_events, notifications, llm_calls…"], ["Not copied", "sessions, channels, tokens"]] },
  { title: "Silver", tone: "layer", href: repoUrl(SPEC14, "72-silver--dataopssilver"),
    lines: ["Typed events joined to the gold transaction and customer."], tip: [["Tables", "case_events, cases, llm_calls, policy_denials"], ["Checks", "keys, status lists, seq per case"]] },
  { title: "Gold", tone: "output", href: repoUrl(SPEC14, "73-gold--dataopsgold"),
    lines: ["KPIs per day, and the analysts' decisions as labels."], tip: [["Tables", "ops_kpis, feedback_cases"], ["Manifest", "data/ops/manifest.json"]] },
];

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
