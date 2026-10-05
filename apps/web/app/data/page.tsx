import type { ReactNode } from "react";
import { PageShell } from "@/components/page-shell";
import quality from "@/public/data/data_quality.json";

// /data (spec 12 AC-03): the medallion, the gold rules, the checks with counts, the manifest versions and the
// late-arrival fixture result. Every value comes from data_quality.json, written by `python -m data.pipeline report --json`.
const int = (n: number) => n.toLocaleString("en-US");
const megabytes = (bytes: number | null) => (bytes === null ? "—" : `${(bytes / 1e6).toFixed(1)} MB`);
const TH = "border-b py-1.5 pr-4 font-normal";
const TD = "border-b py-1.5 pr-4";

function Section({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border bg-card p-5 text-card-foreground">
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{note}</p>
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
    </div>
  );
}

function Result({ ok }: { ok: boolean }) {
  return (
    <span className={`whitespace-nowrap font-medium ${ok ? "text-brand-teal" : "text-destructive"}`}>{ok ? "✓ pass" : "✕ fail"}</span>
  );
}

export default function Page() {
  const { layers, gold_rules, checks, manifest, late_arrival } = quality.data;
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
  return (
    <PageShell title="Data" description="Can the data be trusted? Pipeline bronze → silver → gold, its checks and its versions.">
      <p className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        Synthetic dataset of the hackathon. Every count on this page is <span className="font-mono">[data]</span>: it is
        written by the pipeline run, not typed. A row with a quality problem is flagged, never deleted.
      </p>
      <div className="space-y-4">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-lg border bg-card p-5 text-sm sm:grid-cols-3 lg:grid-cols-6">
          {facts.map(([name, value]) => (
            <div key={name} className="min-w-0">
              <dt className="text-xs text-muted-foreground">{name}</dt>
              <dd className="font-medium tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>

        <div className="grid gap-4 lg:grid-cols-3">
          {layers.map((layer, i) => (
            <Section key={layer.layer} title={`${i + 1}. ${layer.layer[0].toUpperCase()}${layer.layer.slice(1)}`} note={layer.note}>
              <Table
                head={["Table", "Rows", "Size"]}
                rows={layer.tables.map((t) => [t.table, int(t.rows), megabytes(t.bytes)])}
              />
            </Section>
          ))}
        </div>

        <Section
          title="Gold contract rules"
          note="Checked on every run before gold is published; if one fails, gold is not replaced (contracts/gold_contract.md)."
        >
          <Table
            head={["Rule", "Condition", "Value on this run", "Result"]}
            rows={gold_rules.map((r) => [<span key="id" className="font-mono">{r.id}</span>, r.rule, r.value, <Result key="ok" ok={r.ok} />])}
          />
        </Section>

        <Section
          title={`Quality checks: ${flagged.length} of ${checks.length} found rows`}
          note="Rows affected over the rows the check applies to, and what the pipeline does with them."
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
      </div>
      <p className="mt-4 font-mono text-xs text-muted-foreground">
        {quality.source} · generated {quality.generated_at.slice(0, 10)} at {quality.git_sha}
      </p>
    </PageShell>
  );
}
