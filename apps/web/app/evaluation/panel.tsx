// As-is vs with Nick of Time (spec 12 AC-10). Every cell carries its label; nothing here is invented. Labels follow the
// UI language and numbers its locale (spec 16 AC-06); the bracket labels stay as written.
import { Fragment, type ReactNode } from "react";
import { rateText, type BenchmarkData, type EvaluationData, type Insight } from "@/lib/evaluation";
import { formatNumber, type Locale, translator } from "@/lib/i18n";
import { asIsRows, panelState, type PitchContacts } from "@/lib/panel";

const MEASURES = ["fcr", "follow_up", "duration"] as const;

/** A translated sentence whose `{name}` placeholders are filled with React nodes. */
function fill(text: string, nodes: Record<string, ReactNode>): ReactNode {
  return text.split(/\{(\w+)\}/).map((part, i) => <Fragment key={i}>{i % 2 === 1 ? (nodes[part] ?? `{${part}}`) : part}</Fragment>);
}

export function AsIsPanel({
  contacts,
  source,
  generatedAt,
  summary,
  benchmark = null,
  locale = "en",
}: {
  contacts: PitchContacts;
  source: string;
  generatedAt: string;
  summary: Insight<EvaluationData> | null;
  benchmark?: BenchmarkData | null;
  locale?: Locale;
}) {
  const t = translator(locale);
  const one = (v: number) => formatNumber(locale, v, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const pct = (v: number) => `${one(v * 100)}%`;
  const fmt = (n: number) => formatNumber(locale, n);
  const measure = (key: string, fallback: string) =>
    (MEASURES as readonly string[]).includes(key) ? t(`analytics.measures.${key as (typeof MEASURES)[number]}` as const) : fallback;
  const rows = asIsRows(contacts);
  const state = panelState(summary, contacts, benchmark);
  const bold = (n: number) => <span className="font-semibold tabular-nums">{fmt(n)}</span>;
  return (
    <section aria-label={t("evaluation.panel.title")} data-slot="as-is-panel" className="rounded-lg border bg-card p-5 text-card-foreground">
      <h2 className="text-base font-semibold">{t("evaluation.panel.title")}</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{t("evaluation.panel.note")}</p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm tabular-nums">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="border-b py-1.5 pr-4 font-normal">{t("evaluation.panel.head.measure")}</th>
              <th className="border-b py-1.5 pr-4 font-normal">{t("evaluation.panel.head.complaints")} <span className="font-mono">[data]</span></th>
              <th className="border-b py-1.5 pr-4 font-normal">{t("evaluation.panel.head.bank")} <span className="font-mono">[data]</span></th>
              <th className="border-b py-1.5 font-normal">{t("evaluation.panel.head.withUs")}{state.kind === "ready" ? ` (${state.note ?? t("evaluation.panel.arm", { arm: state.arm })})` : ""} <span className="font-mono">[simulated]</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td className="border-b py-1.5 pr-4">{measure(r.key, r.label)}</td>
                <td className="border-b py-1.5 pr-4">{one(r.complaints)} {r.unit}</td>
                <td className="border-b py-1.5 pr-4">{one(r.bank)} {r.unit}</td>
                <td className="border-b py-1.5 text-muted-foreground">
                  {r.key === "fcr"
                    ? state.kind === "ready"
                      ? t("evaluation.panel.asSafe", { rate: rateText(state.rate, locale) })
                      : t("evaluation.panel.resultsPending")
                    : t("evaluation.panel.notMeasured")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div data-slot="projection" className="mt-4 rounded-lg border border-dashed px-4 py-3 text-sm">
        <p className="font-medium">
          {t("evaluation.panel.avoided")} <span className="font-mono text-xs font-normal text-muted-foreground">[projected]</span>
        </p>
        {state.kind === "ready" && state.projection ? (
          <p className="mt-1">
            {fill(t("evaluation.panel.projection"), {
              low: bold(state.projection.low),
              high: bold(state.projection.high),
              volume: fmt(state.projection.volume),
              fcr: pct(state.projection.fcrAsIs),
              n: state.n,
            })}
          </p>
        ) : (
          <p className="mt-1 text-muted-foreground">
            {state.kind === "pending" ? t("evaluation.panel.pendingReason", { reason: state.reason }) : t("evaluation.panel.pendingPlain")}
          </p>
        )}
      </div>
      <p className="mt-4 font-mono text-xs text-muted-foreground">{t("evaluation.panel.generated", { source, date: generatedAt.slice(0, 10) })}</p>
    </section>
  );
}
