// As-is vs with Nick of Time (spec 12 AC-10). Every figure carries its label; nothing here is invented.
// Reading order: the bank's two first-contact figures and, beside them, the held-out's two scores as equal figures
// (ADR 0031, spec 10 AC-15: official sealed rules first, secondary D-070 labeled as such), the arm and ADR 0031's
// sentence, one line per score on the contacts avoided with "Detail →", the measures behind "View as table", the source.
import { TableView } from "@/app/analytics/charts";
import { DetailButton } from "@/components/detail-button";
import { GrowBar } from "@/components/motion";
import { growTarget } from "@/lib/motion";
import { repoUrl } from "@/lib/pipelines";
import { rateParts, rateText, type BenchmarkData, type EvaluationData, type Insight } from "@/lib/evaluation";
import { asIsRows, panelState, type PanelScore, type PitchContacts } from "@/lib/panel";
import { BigFigure, Footer } from "./explain";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const fmt = (n: number) => n.toLocaleString("en-US");
const SHORT: Record<PanelScore["key"], string> = { official: "Official", secondary: "Secondary (D-070)" };

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

/** The contacts avoided under one score: a range from that score's 95% CI, never one number without its basis. */
function ProjectionLine({ s, label }: { s: PanelScore; label: string }) {
  const p = s.projection!;
  return (
    <p data-slot={`projection-${s.key}`}>
      <span className="font-medium">{SHORT[s.key]} score</span> <span className="font-mono text-xs text-muted-foreground">{label}</span>:{" "}
      {p.high === 0 ? (
        <>
          <span className="font-semibold tabular-nums">0</span>; the upper end of its 95% CI ({s.rate.ci_high === null ? "—" : pct(s.rate.ci_high)}) is not above
          today&apos;s {pct(p.fcrAsIs)}.{" "}
        </>
      ) : (
        <>
          between <span className="font-semibold tabular-nums">{fmt(p.low)}</span> and <span className="font-semibold tabular-nums">{fmt(p.high)}</span> of{" "}
          {fmt(p.volume)} complaint contacts, an upper bound.{" "}
        </>
      )}
      <DetailButton
        title={`${SHORT[s.key]} score: contacts avoided`}
        detail={{
          meaning: `More complaint contacts of the full synthetic dataset resolved at first contact, against today's ${pct(p.fcrAsIs)}, under the ${s.label.toLowerCase()} score. An upper-bound illustration, never a forecast.`,
          method: `The 95% CI of safe automated resolution under this score, ${rateText(s.rate)}, n = ${s.n} runs that end in an automatic block and case, applied to every complaint contact. Savings in money are not projected: the repo has no cost per contact.`,
          source: "evaluation_summary.json (scores_d070) · pitch_numbers.json",
          label,
          spec: repoUrl("specs/12-insight-pages.md"),
        }}
      />
    </p>
  );
}

export function AsIsPanel({ contacts, source, generatedAt, summary, benchmark = null }: { contacts: PitchContacts; source: string; generatedAt: string; summary: Insight<EvaluationData> | null; benchmark?: BenchmarkData | null }) {
  const rows = asIsRows(contacts);
  const state = panelState(summary, contacts, benchmark);
  const fcr = rows.find((r) => r.key === "fcr");
  const scores = state.kind === "ready" ? state.scores.filter((s) => s.rate.value !== null) : [];
  const arm = state.kind === "ready" ? state.note ?? `arm ${state.arm}` : null;
  return (
    <section aria-label="As-is vs with Nick of Time" data-slot="as-is-panel" className="rounded-lg border bg-card p-6 text-card-foreground">
      <h2 className="text-base font-semibold">As-is vs with Nick of Time</h2>
      <div className={`mt-4 grid gap-6 sm:grid-cols-2 ${scores.length > 1 ? "lg:grid-cols-4" : "lg:grid-cols-3"}`}>
        <Side value={fcr?.complaints ?? null} label="[data]" caption="complaint contacts resolved at first contact today" color="var(--muted-foreground)" delay={0} />
        <Side value={fcr?.bank ?? null} label="[data]" caption="the whole bank, first-contact resolution today" color="var(--muted-foreground)" delay={120} />
        {scores.length > 0 ? (
          scores.map((s, i) => (
            <div key={s.key} data-slot={`as-is-${s.key}`}>
              <Side value={s.rate.value! * 100} label="[simulated]" caption={`with Nick of Time · ${s.label}: safe automated resolution, ${rateParts(s.rate).count}, 95% CI ${rateParts(s.rate).interval}`} color="var(--primary)" delay={240 + i * 120} />
            </div>
          ))
        ) : (
          <Side value={null} label="" caption="with Nick of Time" color="var(--primary)" delay={240} />
        )}
      </div>
      {arm ? <p className="mt-3 text-xs text-muted-foreground">Arm: {arm}.</p> : null}
      {state.kind === "ready" && state.sentence ? (
        <p data-slot="as-is-sentence" className="mt-2 text-sm">
          {state.sentence}
        </p>
      ) : null}
      <div data-slot="projection" className="mt-6 space-y-1 text-sm">
        <p>
          <span className="font-medium">Contacts avoided</span> <span className="font-mono text-xs text-muted-foreground">[projected]</span>
          {state.kind === "ready" && state.projection ? (
            scores.length > 1 ? ", one range per score:" : ":"
          ) : (
            <>
              :{" "}
              <span className="text-muted-foreground">none until the result is in{state.kind === "pending" ? ` (${state.reason.replace(/\.$/, "")})` : ""}.</span>
            </>
          )}
        </p>
        {state.kind === "ready" && state.projection ? scores.filter((s) => s.projection).map((s) => <ProjectionLine key={s.key} s={s} label="[projected]" />) : null}
      </div>
      <TableView
        head={["Measure", "Complaint contacts today [data]", "Whole bank today [data]", "With Nick of Time [simulated]"]}
        rows={rows.map((r) => [
          r.label,
          `${r.complaints.toFixed(1)} ${r.unit}`,
          `${r.bank.toFixed(1)} ${r.unit}`,
          r.key === "fcr"
            ? scores.length > 0
              ? scores.map((s) => `${SHORT[s.key]}: ${rateText(s.rate)} as safe automated resolution`).join("; ")
              : "results pending"
            : "not measured by the harness",
        ])}
      />
      <Footer>
        {source} · generated {generatedAt.slice(0, 10)}
      </Footer>
    </section>
  );
}
