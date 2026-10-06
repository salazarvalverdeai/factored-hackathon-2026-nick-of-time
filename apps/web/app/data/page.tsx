import { Fragment, type ReactNode } from "react";
import { PageShell } from "@/components/page-shell";
import { formatNumber, type Locale } from "@/lib/i18n";
import { getT } from "@/lib/i18n-server";
import quality from "@/public/data/data_quality.json";

// /data (spec 12 AC-03): the medallion, the gold rules, the checks with counts, the manifest versions and the
// late-arrival fixture result. Every value comes from data_quality.json, written by `python -m data.pipeline report --json`.
// Labels follow the UI language and numbers its locale (spec 16 AC-06); check texts and sources stay as written.
const numbers = (locale: Locale) => ({
  int: (n: number) => formatNumber(locale, n),
  megabytes: (bytes: number | null) =>
    bytes === null ? "—" : `${formatNumber(locale, bytes / 1e6, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MB`,
});

/** A translated sentence whose `{name}` placeholders are filled with React nodes. */
function fill(text: string, nodes: Record<string, ReactNode>): ReactNode {
  return text.split(/\{(\w+)\}/).map((part, i) => <Fragment key={i}>{i % 2 === 1 ? (nodes[part] ?? `{${part}}`) : part}</Fragment>);
}
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

function Result({ ok, label }: { ok: boolean; label: string }) {
  return <span className={`whitespace-nowrap font-medium ${ok ? "text-brand-teal" : "text-destructive"}`}>{label}</span>;
}

export default async function Page() {
  const { t, locale } = await getT();
  const { int, megabytes } = numbers(locale);
  const { layers, gold_rules, checks, manifest, late_arrival } = quality.data;
  const checkHead = [
    t("data.checks.head.check"),
    t("data.checks.head.table"),
    t("data.checks.head.looksFor"),
    t("data.checks.head.affected"),
    t("data.checks.head.action"),
  ];
  const flagged = checks.filter((c) => c.rows_affected > 0);
  const checkRow = (c: (typeof checks)[number]) => [
    <span key="id" className="font-mono">
      {c.id}
    </span>,
    c.table,
    c.check,
    t("data.ofN", { n: int(c.rows_affected), total: int(c.denominator) }),
    c.action,
  ];
  const facts: [string, string][] = [
    [t("data.facts.goldVersion"), `v${manifest.gold_version}`],
    [t("data.facts.contract"), manifest.contract_version],
    [t("data.facts.pipeline"), manifest.pipeline_version],
    [t("data.facts.run"), manifest.run_at.slice(0, 10)],
    [t("data.facts.window"), t("data.facts.windowValue", { from: manifest.transactions_window[0], to: manifest.transactions_window[1] })],
    [t("data.facts.source"), t("data.facts.sourceValue", { n: int(manifest.source_files), size: megabytes(manifest.source_bytes) })],
  ];
  return (
    <PageShell title={t("data.title")} description={t("data.description")}>
      <p className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        {fill(t("data.intro"), { label: <span className="font-mono">[data]</span> })}
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
                head={[t("data.tables.table"), t("data.tables.rows"), t("data.tables.size")]}
                rows={layer.tables.map((t) => [t.table, int(t.rows), megabytes(t.bytes)])}
              />
            </Section>
          ))}
        </div>

        <Section
          title={t("data.rules.title")}
          note={t("data.rules.note")}
        >
          <Table
            head={[t("data.rules.head.rule"), t("data.rules.head.condition"), t("data.rules.head.value"), t("data.rules.head.result")]}
            rows={gold_rules.map((r) => [
              <span key="id" className="font-mono">
                {r.id}
              </span>,
              r.rule,
              r.value,
              <Result key="ok" ok={r.ok} label={r.ok ? t("data.rules.pass") : t("data.rules.fail")} />,
            ])}
          />
        </Section>

        <Section
          title={t("data.checks.title", { flagged: flagged.length, total: checks.length })}
          note={t("data.checks.note")}
        >
          <Table head={checkHead} rows={flagged.map(checkRow)} />
          <details className="mt-4">
            <summary className="cursor-pointer rounded-sm text-xs text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">
              {t("data.checks.viewAll", { n: checks.length })}
            </summary>
            <div className="mt-2">
              <Table head={checkHead} rows={checks.map(checkRow)} />
            </div>
          </details>
        </Section>

        {late_arrival ? (
          <Section
            title={t("data.late.title")}
            note={t("data.late.note", { label: late_arrival.label })}
          >
            <ul className="space-y-1.5 text-sm">
              <li>
                {t("data.late.deliveries")} {late_arrival.deliveries.map((d) => `${d.name} (gold v${d.gold_version})`).join(" → ")}
              </li>
              <li>
                {t("data.late.rowsAdded")}{" "}
                {Object.entries(late_arrival.rows_added)
                  .map(([table, n]) => `${table} ${n}`)
                  .join(" · ")}
              </li>
              <li>
                {t("data.late.newColumn")} <span className="font-mono">{late_arrival.columns_added.join(", ") || t("data.none")}</span>
                {" · "}
                {t("data.late.rename")} <span className="font-mono">{late_arrival.columns_renamed.join(", ") || t("data.none")}</span>
              </li>
              <li>
                {fill(t("data.late.lateRows"), {
                  n: late_arrival.late_rows,
                  flag: <span className="font-mono">qc_late_arrival</span>,
                  days: late_arrival.max_lag_days,
                })}
              </li>
              <li>{t("data.late.matched", { matched: late_arrival.expected_counts.matched, total: late_arrival.expected_counts.total })}</li>
            </ul>
            <div className="mt-4">
              <Table
                head={[checkHead[0], checkHead[1], checkHead[2], t("data.late.before"), t("data.late.after")]}
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
        {t("data.generated", { source: quality.source, date: quality.generated_at.slice(0, 10), sha: quality.git_sha })}

      </p>
    </PageShell>
  );
}
