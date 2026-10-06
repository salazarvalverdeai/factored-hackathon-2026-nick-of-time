// As-is vs with Nick of Time (spec 12 AC-10). Every cell carries its label; nothing here is invented.
// On the sealed held-out it shows both scores of ADR 0031 (spec 10 AC-15) as two equal cards: official first.
import type { ReactNode } from "react";
import { rateText, type BenchmarkData, type EvaluationData, type Insight } from "@/lib/evaluation";
import { asIsRows, panelState, type PanelScore, type PitchContacts } from "@/lib/panel";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const fmt = (n: number) => n.toLocaleString("en-US");

/** A figure's label, set next to the figure it labels. */
const Tag = ({ children }: { children: ReactNode }) => <span className="font-mono text-xs font-normal text-muted-foreground">{children}</span>;

function ScoreCard({ s }: { s: PanelScore }) {
  const p = s.projection;
  return (
    <div data-slot={`as-is-${s.key}`} className="rounded-md border p-3">
      <p className={s.key === "official" ? "text-xs font-medium" : "text-xs text-muted-foreground"}>{s.label}</p>
      <p className="mt-1">
        <span className="text-lg font-semibold tabular-nums">{rateText(s.rate)}</span> safe automated resolution <Tag>[simulated]</Tag>
      </p>
      {p ? (
        <p className="mt-2" data-slot={`projection-${s.key}`}>
          {p.high === 0 ? (
            <>
              <span className="font-semibold tabular-nums">0</span> contacts avoided <Tag>[projected]</Tag>: the upper end of this score&apos;s 95% CI (
              {s.rate.ci_high === null ? "—" : pct(s.rate.ci_high)}) is not above today&apos;s first-contact resolution ({pct(p.fcrAsIs)}).
            </>
          ) : (
            <>
              Between <span className="font-semibold tabular-nums">{fmt(p.low)}</span> and <span className="font-semibold tabular-nums">{fmt(p.high)}</span> more of
              the {fmt(p.volume)} complaint contacts of the full synthetic dataset resolved at first contact <Tag>[projected]</Tag>, from this score&apos;s 95% CI
              (today&apos;s first-contact resolution is {pct(p.fcrAsIs)}).
            </>
          )}{" "}
          n = {s.n} runs.
        </p>
      ) : null}
    </div>
  );
}

export function AsIsPanel({ contacts, source, generatedAt, summary, benchmark = null }: { contacts: PitchContacts; source: string; generatedAt: string; summary: Insight<EvaluationData> | null; benchmark?: BenchmarkData | null }) {
  const rows = asIsRows(contacts);
  const state = panelState(summary, contacts, benchmark);
  return (
    <section aria-label="As-is vs with Nick of Time" data-slot="as-is-panel" className="rounded-lg border bg-card p-5 text-card-foreground">
      <h2 className="text-base font-semibold">As-is vs with Nick of Time</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">The bank today, the system on scripted cases, and what that would mean at the bank&apos;s volume.</p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm tabular-nums">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="border-b py-1.5 pr-4 font-normal">Measure</th>
              <th className="border-b py-1.5 pr-4 font-normal">Complaint contacts today <span className="font-mono">[data]</span></th>
              <th className="border-b py-1.5 pr-4 font-normal">Whole bank today <span className="font-mono">[data]</span></th>
              <th className="border-b py-1.5 font-normal">With Nick of Time{state.kind === "ready" ? ` (${state.note ?? `arm ${state.arm}`})` : ""} <span className="font-mono">[simulated]</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td className="border-b py-1.5 pr-4">{r.label}</td>
                <td className="border-b py-1.5 pr-4">{r.complaints.toFixed(1)} {r.unit}</td>
                <td className="border-b py-1.5 pr-4">{r.bank.toFixed(1)} {r.unit}</td>
                <td className="border-b py-1.5 text-muted-foreground">
                  {r.key !== "fcr"
                    ? "not measured by the harness"
                    : state.kind === "ready"
                      ? state.scores.map((s) => (
                          <span key={s.key} className="block">
                            {s.key === "official" ? "Official" : "Secondary (D-070)"}: {rateText(s.rate)} as safe automated resolution
                          </span>
                        ))
                      : "results pending"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div data-slot="projection" className="mt-4 rounded-lg border border-dashed px-4 py-3 text-sm">
        <p className="font-medium">
          Contacts avoided <span className="font-mono text-xs font-normal text-muted-foreground">[projected]</span>
        </p>
        {state.kind === "ready" && state.projection ? (
          <>
            {state.sentence ? (
              <p className="mt-1" data-slot="as-is-sentence">
                {state.sentence}
              </p>
            ) : null}
            <div className={`mt-3 grid gap-3 ${state.scores.length > 1 ? "sm:grid-cols-2" : ""}`}>
              {state.scores.map((s) => (
                <ScoreCard key={s.key} s={s} />
              ))}
            </div>
            <p className="mt-3 text-muted-foreground">
              Each range is computed on the share of contacts that end in an automatic block and case, from its own score; applied to all complaints as an
              upper-bound illustration, never multiplied out as a single figure. Savings in money are not projected: the repo has no cost per contact.
            </p>
          </>
        ) : (
          <p className="mt-1 text-muted-foreground">Results pending{state.kind === "pending" ? `: ${state.reason}` : ""} No number and no projection until then.</p>
        )}
      </div>
      <p className="mt-4 font-mono text-xs text-muted-foreground">
        {source} · generated {generatedAt.slice(0, 10)}
      </p>
    </section>
  );
}
