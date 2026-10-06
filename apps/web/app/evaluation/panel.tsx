// As-is vs with Nick of Time (spec 12 AC-10). Every figure carries its label; nothing here is invented.
// Reading order: three big first-contact figures with a bar each, one line on the contacts avoided with "Detail →"
// (the method and its caveats), the other measures behind "View as table", and the source in the footer.
import { TableView } from "@/app/analytics/charts";
import { DetailButton } from "@/components/detail-button";
import { GrowBar } from "@/components/motion";
import { growTarget } from "@/lib/motion";
import { repoUrl } from "@/lib/pipelines";
import { rateText, type BenchmarkData, type EvaluationData, type Insight } from "@/lib/evaluation";
import { asIsRows, panelState, type PitchContacts } from "@/lib/panel";
import { BigFigure, Footer } from "./explain";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const fmt = (n: number) => n.toLocaleString("en-US");

/** One first-contact figure with its bar on a 0 to 100% track (grows once; in place with reduced motion). */
function Side({ value, label, caption, color, delay }: { value: number | null; label: string; caption: string; color: string; delay: number }) {
  return (
    <div className="min-w-0">
      <BigFigure value={value === null ? "results pending" :`${value.toFixed(1)}%`} label={label} caption={caption} />
      <div className="mt-2 h-2 rounded-full bg-muted" aria-hidden>
        {value !== null ? <GrowBar delay={delay} className="h-2 rounded-full" style={{ width: `${growTarget(value, 100)}%`, background: color }} /> : null}
      </div>
    </div>
  );
}

export function AsIsPanel({ contacts, source, generatedAt, summary, benchmark = null }: { contacts: PitchContacts; source: string; generatedAt: string; summary: Insight<EvaluationData> | null; benchmark?: BenchmarkData | null }) {
  const rows = asIsRows(contacts);
  const state = panelState(summary, contacts, benchmark);
  const fcr = rows.find((r) => r.key === "fcr");
  const withUs = state.kind === "ready" && state.rate.value !== null ? state.rate.value * 100 : null;
  const arm = state.kind === "ready" ? state.note ?? `arm ${state.arm}` : null;
  return (
    <section aria-label="As-is vs with Nick of Time" data-slot="as-is-panel" className="rounded-lg border bg-card p-6 text-card-foreground">
      <h2 className="text-base font-semibold">As-is vs with Nick of Time</h2>
      <div className="mt-4 grid gap-6 sm:grid-cols-3">
        <Side value={fcr?.complaints ?? null} label="[data]" caption="complaint contacts resolved at first contact today" color="var(--muted-foreground)" delay={0} />
        <Side value={fcr?.bank ?? null} label="[data]" caption="the whole bank, first-contact resolution today" color="var(--muted-foreground)" delay={120} />
        <Side value={withUs} label={withUs === null ? "" : "[simulated]"} caption={withUs === null ? "with Nick of Time" : `with Nick of Time: safe automated resolution (${arm})`} color="var(--primary)" delay={240} />
      </div>
      <p data-slot="projection" className="mt-6 text-sm">
        <span className="font-medium">Contacts avoided</span> <span className="font-mono text-xs text-muted-foreground">[projected]</span>:{" "}
        {state.kind === "ready" && state.projection ? (
          <>
            between <span className="font-semibold tabular-nums">{fmt(state.projection.low)}</span> and{" "}
            <span className="font-semibold tabular-nums">{fmt(state.projection.high)}</span> of {fmt(state.projection.volume)} complaint contacts, an upper bound.{" "}
            <DetailButton
              title="Contacts avoided"
              detail={{
                meaning: `More complaint contacts of the full synthetic dataset resolved at first contact, against today's ${pct(state.projection.fcrAsIs)}. An upper-bound illustration, never a forecast.`,
                method: `The 95% CI of safe automated resolution, ${rateText(state.rate)}, n = ${state.n} runs that end in an automatic block and case, applied to every complaint contact. Savings in money are not projected: the repo has no cost per contact.`,
                source: "evaluation_summary.json · pitch_numbers.json",
                label: "[projected]",
                spec: repoUrl("specs/12-insight-pages.md"),
              }}
            />
          </>
        ) : (
          <span className="text-muted-foreground">none until the result is in{state.kind === "pending" ? ` (${state.reason.replace(/\.$/, "")})` : ""}.</span>
        )}
      </p>
      <TableView
        head={["Measure", "Complaint contacts today [data]", "Whole bank today [data]", "With Nick of Time [simulated]"]}
        rows={rows.map((r) => [
          r.label,
          `${r.complaints.toFixed(1)} ${r.unit}`,
          `${r.bank.toFixed(1)} ${r.unit}`,
          r.key === "fcr" ? (state.kind === "ready" ? `${rateText(state.rate)} as safe automated resolution` : "results pending") : "not measured by the harness",
        ])}
      />
      <Footer>
        {source} · generated {generatedAt.slice(0, 10)}
      </Footer>
    </section>
  );
}
