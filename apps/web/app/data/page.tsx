import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { ReactNode } from "react";
import Link from "next/link";
import { PageShell } from "@/components/page-shell";
import { PipelineDiagram } from "@/components/pipeline-diagram";
import { TableView } from "@/app/analytics/charts";
import { DetailButton } from "@/components/detail-button";
import { DATA_CARDS, GOLD_CONSUMERS, OPS_STEPS, datasetLimits, medallionSteps, type Detail } from "@/lib/pipelines";
import quality from "@/public/data/data_quality.json";

// /data (spec 12 AC-03): the medallion, the gold rules, the checks with counts, the manifest versions, the
// late-arrival fixture result, the operational lakehouse and the dataset limits. Every value comes from
// data_quality.json, written by `python -m data.pipeline report --json`; the page computes nothing.
const int = (n: number) => n.toLocaleString("en-US");
const megabytes = (bytes: number | null) => (bytes === null ? "—" : `${(bytes / 1e6).toFixed(1)} MB`);
const TH = "border-b py-1.5 pr-4 font-normal";
const TD = "border-b py-1.5 pr-4";

/** The shared card: a title, one or two plain lines and "Detail →", which opens the side panel. */
function Section({ title, note, detail, chip, children }: { title: string; note: ReactNode; detail: Detail; chip?: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="rounded-lg border bg-card p-5 text-card-foreground">
      <h2 className="text-base font-semibold">
        {title}
        {chip ? <span className="ml-2 rounded-full border px-2 py-0.5 align-middle text-xs font-normal text-muted-foreground">{chip}</span> : null}
      </h2>
      <p className="mt-0.5 text-sm text-muted-foreground">
        {note} <DetailButton title={title} detail={detail} />
      </p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs tabular-nums">
        <thead className="text-muted-foreground">
          <tr>
            {head.map((h) => (
              <th key={h} className={TH}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j} className={TD}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="sticky left-0 mt-1 text-xs text-muted-foreground sm:hidden">Scroll the table sideways for every column →</p>
    </div>
  );
}

function Result({ ok }: { ok: boolean }) {
  return (
    <span className={`whitespace-nowrap font-medium ${ok ? "text-brand-teal" : "text-destructive"}`}>{ok ? "✓ pass" : "✕ fail"}</span>
  );
}

/** spec 14 AC-09: ops_kpis.json once the job exports to the site; its source names the ops manifest version. */
function opsExport(): { version: string; source: string; generated_at: string } | null {
  const file = path.join(process.cwd(), "public", "data", "ops_kpis.json");
  if (!existsSync(file)) return null;
  const json = JSON.parse(readFileSync(file, "utf-8")) as { source: string; generated_at: string };
  return { ...json, version: /manifest v(\d+)/.exec(json.source)?.[1] ?? "?" };
}

export default function Page() {
  const { layers, gold_rules, checks, manifest, late_arrival, complaint_link } = quality.data;
  const flagged = checks.filter((c) => c.rows_affected > 0);
  const checkRow = (c: (typeof checks)[number]) => [
    <span key="id" className="font-mono">
      {c.id}
    </span>,
    c.table,
    c.check,
    `${int(c.rows_affected)} of ${int(c.denominator)}`,
    c.action,
  ];
  const facts: [string, string][] = [
    ["Gold version", `v${manifest.gold_version}`],
    ["Contract", manifest.contract_version],
    ["Pipeline", manifest.pipeline_version],
    ["Run", manifest.run_at.slice(0, 10)],
    ["Transactions window", `${manifest.transactions_window[0]} to ${manifest.transactions_window[1]}`],
    ["Source", `${int(manifest.source_files)} files · ${megabytes(manifest.source_bytes)}`],
  ];
  const limits = complaint_link ? datasetLimits(complaint_link.rows) : [];
  const ops = opsExport();
  return (
    <PageShell title="Data" description="Can the data be trusted? Pipeline bronze → silver → gold, its checks and its versions.">
      <p className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        Synthetic dataset of the hackathon. Every count on this page is written by the pipeline run, not typed. A row with
        a quality problem is flagged, never deleted. How the system around this data is built:{" "}
        <Link className="underline underline-offset-2" href="/agent">
          the agent
        </Link>
        .
      </p>
      <div className="space-y-4">
        <Section
          title="Medallion pipeline"
          note="From the bank's CSV files to the read-only tables the system uses. Hover a layer, or reach it with the Tab key, to see its tables."
          detail={DATA_CARDS.medallion}
        >
          <PipelineDiagram label="Medallion pipeline" steps={medallionSteps(quality.data)} outputs={GOLD_CONSUMERS} />
          <TableView
            head={["Layer", "Table", "Rows", "Size"]}
            rows={layers.flatMap((l) => l.tables.map((t) => [l.layer, t.table, `${int(t.rows)} [data]`, megabytes(t.bytes)]))}
          />
        </Section>

        <Section title="Versions" note="What this page was built from: one run of the pipeline on one source delivery." detail={DATA_CARDS.versions}>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3 lg:grid-cols-6">
            {facts.map(([name, value]) => (
              <div key={name} className="min-w-0">
                <dt className="text-xs text-muted-foreground">{name}</dt>
                <dd className="font-medium tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        </Section>

        <Section
          title="Gold contract rules"
          note="Checked on every run before gold is published; if one fails, gold is not replaced."
          detail={DATA_CARDS.rules}
        >
          <Table
            head={["Rule", "Condition", "Value on this run", "Result"]}
            rows={gold_rules.map((r) => [<span key="id" className="font-mono">{r.id}</span>, r.rule, r.value, <Result key="ok" ok={r.ok} />])}
          />
        </Section>

        <Section
          title={`Quality checks: ${flagged.length} of ${checks.length} found rows`}
          note="Rows affected over the rows the check applies to, and what the pipeline does with them."
          detail={DATA_CARDS.checks}
        >
          <Table head={["Check", "Table", "What it looks for", "Rows affected", "Action"]} rows={flagged.map(checkRow)} />
          <details className="mt-4">
            <summary className="cursor-pointer rounded-sm text-xs text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">
              View all {checks.length} checks
            </summary>
            <div className="mt-2">
              <Table head={["Check", "Table", "What it looks for", "Rows affected", "Action"]} rows={checks.map(checkRow)} />
            </div>
          </details>
        </Section>

        {late_arrival ? (
          <Section
            title="Late arrivals and schema change"
            note={`Shown with a ${late_arrival.label}: the real dataset has no late arrivals or schema changes, so two labeled deliveries go through the same pipeline code.`}
            detail={DATA_CARDS.late}
          >
            <ul className="space-y-1.5 text-sm">
              <li>
                Deliveries:{" "}
                {late_arrival.deliveries.map((d) => `${d.name} (gold v${d.gold_version})`).join(" → ")}
              </li>
              <li>
                Rows added:{" "}
                {Object.entries(late_arrival.rows_added)
                  .map(([table, n]) => `${table} ${n}`)
                  .join(" · ")}
              </li>
              <li>
                New column kept in bronze only: <span className="font-mono">{late_arrival.columns_added.join(", ") || "none"}</span>
                {" · "}declared rename: <span className="font-mono">{late_arrival.columns_renamed.join(", ") || "none"}</span>
              </li>
              <li>
                Rows that arrived after their date, in silver: {late_arrival.late_rows}; kept and flagged <span className="font-mono">qc_late_arrival</span> (longest
                delay {late_arrival.max_lag_days} days)
              </li>
              <li>
                Counts matching the expected ones: {late_arrival.expected_counts.matched} of {late_arrival.expected_counts.total}
              </li>
            </ul>
            <div className="mt-4">
              <Table
                head={["Check", "Table", "What it looks for", "Before", "After"]}
                rows={late_arrival.checks_changed.map((c) => [
                  <span key="id" className="font-mono">
                    {c.id}
                  </span>,
                  c.table,
                  c.check,
                  String(c.before ?? "—"),
                  String(c.after),
                ])}
              />
            </div>
          </Section>
        ) : null}

        <Section
          title="Operational lakehouse"
          chip={ops ? `ops manifest v${ops.version}` : "Pending"}
          note="The system's own case records go through the same three layers, to measure it day by day."
          detail={DATA_CARDS.ops}
        >
          <PipelineDiagram label="Operational lakehouse" steps={OPS_STEPS} />
          <ul className="mt-4 space-y-1.5 text-sm">
            <li>Reads the case store&apos;s operational tables, read-only, and gold for the transaction and the customer.</li>
            <li>Writes Parquet and a manifest under data/ops/, and ops_kpis.json for the Analytics page.</li>
            {ops ? (
              <li>
                Last export: {ops.source}, generated {ops.generated_at.slice(0, 10)}.
              </li>
            ) : (
              <li>
                Pending: the job has run only on a seeded sample store, which writes to data/ops/ and never to this site. The
                run on the live case store waits for real traffic.
              </li>
            )}
          </ul>
        </Section>

        {complaint_link && limits.length ? (
          <Section title="Dataset limitations" note="What the data cannot tell us, measured on gold." detail={DATA_CARDS.limits}>
            <ul className="list-disc space-y-1.5 pl-5 text-sm">
              {limits.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted-foreground">
              Method: disputed-charge complaints created from 2025-07-01 to 2026-05-31, so the 30-day look-back stays inside the
              gold transactions window; a card transaction is one on a credit or debit card of the same customer. Query:{" "}
              <span className="break-all font-mono">{complaint_link.query}</span>.
            </p>
          </Section>
        ) : null}
      </div>
      <p className="mt-4 font-mono text-xs text-muted-foreground">
        {quality.source} · generated {quality.generated_at.slice(0, 10)} at {quality.git_sha}
      </p>
    </PageShell>
  );
}
