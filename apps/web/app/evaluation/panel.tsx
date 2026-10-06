// As-is vs with Nick of Time (spec 12 AC-10). Every cell carries its label; nothing here is invented.
import { rateText, type BenchmarkData, type EvaluationData, type Insight } from "@/lib/evaluation";
import { asIsRows, panelState, type PitchContacts } from "@/lib/panel";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const fmt = (n: number) => n.toLocaleString("en-US");

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
                  {r.key === "fcr" ? (state.kind === "ready" ? `${rateText(state.rate)} as safe automated resolution` : "results pending") : "not measured by the harness"}
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
          <p className="mt-1">
            Between <span className="font-semibold tabular-nums">{fmt(state.projection.low)}</span> and{" "}
            <span className="font-semibold tabular-nums">{fmt(state.projection.high)}</span> more of the {fmt(state.projection.volume)} complaint contacts of the
            full synthetic dataset resolved at first contact (95% CI of the rate; today&apos;s first-contact resolution is {pct(state.projection.fcrAsIs)}).
            Computed on the share of contacts that end in an automatic block and case (n = {state.n} runs); applied to all complaints as an upper-bound
            illustration. Savings in money are not projected: the repo has no cost per contact.
          </p>
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
