"use client";

// /evaluation content for benchmark.json, classifier.json and fraud_benchmark.json (spec 12 §7.3, parts 5 to 7).
// Nothing is computed here: every number is the exporter's. Every rate shows its numerator, denominator and interval on
// hover, on keyboard focus and in the table view (AC-06, AC-07).
import { useState, type ReactNode } from "react";
import { FOCUS, Swatch, TableView, TipBody, useTip } from "@/app/analytics/charts";
import {
  costQualityPoints,
  dollars,
  interval,
  milliseconds,
  protocolNotice,
  rateText,
  score,
  scoreText,
  type BenchmarkData,
  type ClassifierData,
  type FraudData,
  type Insight,
  type Protocol,
  type Rate,
} from "@/lib/evaluation";

const PALETTE = "[--arm-1:#7c3aed] dark:[--arm-1:#8b5cf6] [--arm-2:#0d9488]";
const yes = (v: boolean | null) => (v === null ? "—" : v ? "yes" : "no");

function Notice({ protocol }: { protocol: Protocol }) {
  const text = protocolNotice(protocol);
  return text ? (
    <p role="note" data-slot="development-notice" className="rounded-lg border border-border bg-muted px-4 py-3 text-sm font-medium text-foreground">
      {text}
    </p>
  ) : null;
}

function Section({ title, hint, file, data, children }: { title: string; hint: string; file: Insight<{ label: string; protocol: Protocol }>; data: string; children: ReactNode }) {
  return (
    <section aria-label={title} className={`space-y-4 ${PALETTE}`} data-file={data}>
      <Notice protocol={file.data.protocol} />
      <div className="rounded-lg border bg-card p-5 text-card-foreground">
        <h2 className="text-base font-semibold">
          {title} <span className="font-mono text-xs font-normal text-muted-foreground">{file.data.label}</span>
        </h2>
        <p className="mt-0.5 text-sm text-muted-foreground">{hint}</p>
        {children}
        <p className="mt-4 font-mono text-xs text-muted-foreground">
          {file.data.label} {file.source} · generated {file.generated_at.slice(0, 10)} at {file.git_sha}
        </p>
      </div>
    </section>
  );
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-xs tabular-nums">
        <thead className="text-muted-foreground">
          <tr>{head.map((h) => <th key={h} className="border-b py-1.5 pr-4 font-normal">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>{row.map((c, j) => <td key={j} className="border-b py-1.5 pr-4 whitespace-nowrap">{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- (5) benchmark: cost on x, quality on y ----
const W = 640, H = 300, L = 52, R = 16, T = 12, B = 40;

export function BenchmarkSection({ file }: { file: Insight<BenchmarkData> }) {
  const data = file.data;
  const languages = Object.keys(data.b1.arms[0]?.macro_f1 ?? { es: 0, pt: 0 });
  const [language, setLanguage] = useState(languages[0] ?? "es");
  const { bind, node } = useTip();
  const points = costQualityPoints(data, language);
  const maxCost = Math.max(...points.map((p) => p.cost), 0.01) * 1.1;
  const lows = points.map((p) => p.ci?.[0] ?? p.quality);
  const yMin = Math.max(0, Math.floor((Math.min(...lows, 1) - 0.05) * 10) / 10);
  const x = (c: number) => L + (c / maxCost) * (W - L - R);
  const y = (q: number) => T + (1 - (q - yMin) / (1 - yMin)) * (H - T - B);
  const front = points.filter((p) => p.pareto).sort((a, b) => a.cost - b.cost);
  const chosen = data.model_map.understand?.chosen;
  return (
    <Section title="Model benchmark: cost against quality" file={file} data="benchmark.json"
      hint={`Understanding task: one dot per model, macro-F1 on the ${language.toUpperCase()} test sentences against USD per 1,000 messages. Filled dots are on the Pareto front; the ringed one is the chosen model${chosen ? ` (${chosen})` : ""}. Axis starts at ${yMin.toFixed(1)}.`}>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        {languages.map((l) => (
          <button key={l} type="button" aria-pressed={l === language} onClick={() => setLanguage(l)}
            className={`rounded-md border px-2 py-1 ${FOCUS} ${l === language ? "bg-muted font-medium text-foreground" : ""}`}>
            {l.toUpperCase()}
          </button>
        ))}
        <span className="inline-flex items-center gap-1.5"><Swatch color="var(--arm-1)" /> on the Pareto front</span>
        <span>run {data.run_date} · {data.mode} mode</span>
      </div>
      {points.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">No arm has a cost and a score in this language yet.</p>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 h-auto w-full" role="group" aria-label="Cost against macro-F1 per model">
          {[0, 1, 2, 3, 4].map((i) => {
            const q = yMin + ((1 - yMin) * i) / 4;
            return (
              <g key={i} className="text-muted-foreground">
                <line x1={L} x2={W - R} y1={y(q)} y2={y(q)} stroke="currentColor" strokeOpacity={0.2} />
                <text x={L - 6} y={y(q) + 3} textAnchor="end" fontSize={10} fill="currentColor">{q.toFixed(2)}</text>
                <text x={x((maxCost * i) / 4)} y={H - T - 14} textAnchor="middle" fontSize={10} fill="currentColor">${((maxCost * i) / 4).toFixed(2)}</text>
              </g>
            );
          })}
          <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" fontSize={11} fill="currentColor" className="text-muted-foreground">USD per 1,000 messages</text>
          <text transform={`translate(12 ${(T + H - B) / 2}) rotate(-90)`} textAnchor="middle" fontSize={11} fill="currentColor" className="text-muted-foreground">macro-F1</text>
          {front.length > 1 ? <polyline fill="none" stroke="var(--arm-1)" strokeOpacity={0.5} strokeDasharray="4 3" points={front.map((p) => `${x(p.cost)},${y(p.quality)}`).join(" ")} /> : null}
          {points.map((p) => {
            const a = p.row;
            return (
              <g key={p.arm}>
                {p.chosen ? <circle cx={x(p.cost)} cy={y(p.quality)} r={11} fill="none" stroke="var(--arm-2)" strokeWidth={2} /> : null}
                <circle tabIndex={0} role="img" cx={x(p.cost)} cy={y(p.quality)} r={6} strokeWidth={2} stroke="var(--arm-1)"
                  fill={p.pareto ? "var(--arm-1)" : "var(--card)"} className="outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  aria-label={`${p.arm}: macro-F1 ${scoreText(p.quality, p.ci)}, ${dollars(p.cost)} per 1,000 messages, p95 ${milliseconds(a.p95_ms)}${p.chosen ? ", chosen" : ""}`}
                  {...bind(
                    <TipBody title={`${p.arm}${p.chosen ? " · chosen" : ""}`}
                      rows={[["Macro-F1", score(p.quality)], ["95% interval", interval(p.ci)], ["Cost per 1,000", dollars(p.cost)], ["p95", milliseconds(a.p95_ms)],
                        ["Dispute recall", rateText(a.dispute_recall)]]}
                      note={`[simulated] ${a.price.label} price ${a.price.date}`} />,
                  )} />
                <text x={x(p.cost) + 10} y={y(p.quality) - 9} fontSize={10} fill="currentColor">{p.arm}</text>
              </g>
            );
          })}
        </svg>
      )}
      <TableView
        head={["Arm", "Status", `Macro-F1 ${language.toUpperCase()}`, "Dispute recall", "Person-request recall", "Slot accuracy", "p95", "Per 1,000", "Pareto", "Meets bar", "Production gate"]}
        rows={data.b1.arms.map((a) => [a.arm, a.status === "ok" ? "ok" : `${a.status}${a.unavailable_reason ? `: ${a.unavailable_reason}` : ""}`,
          scoreText(a.macro_f1[language], a.macro_f1_ci[language]), rateText(a.dispute_recall), rateText(a.human_request_recall), rateText(a.slot_accuracy),
          milliseconds(a.p95_ms), dollars(a.cost_per_1000_usd), yes(a.pareto), yes(a.meets_bar), yes(a.gate.production_pass)])}
      />
      <h3 className="mt-5 text-sm font-semibold">Whole system on the dev cases ({data.b2.set}, {data.b2.cases} cases x {data.b2.runs_per_case} runs)</h3>
      <Table head={["Arm", "Safe automated resolution", "Unsafe outcomes", "Receipt with its deadline", "Status told = status read", "p95 per turn", "Cost per case"]}
        rows={data.b2.arms.map((a) => [a.arm, rateText(a.safe_automated_resolution as Rate), rateText(a.unsafe_outcomes as Rate), rateText(a.receipt_rate as Rate),
          rateText(a.coherence_rate as Rate), milliseconds(a.p95_ms as number | null), dollars(a.cost_per_case_usd)])} />
      {node}
    </Section>
  );
}

// ---- (6) classifier: arm x language ----
export function ClassifierSection({ file }: { file: Insight<ClassifierData> }) {
  const data = file.data;
  const sentences = Object.entries(data.test_split.sentences).map(([l, n]) => `${l.toUpperCase()} ${n ?? "—"}`).join(", ");
  const rows = data.arms.flatMap((a) =>
    Object.entries(a.by_language).map(([lang, m]) => [
      a.arm + (a.arm === data.chosen_arm ? " (chosen)" : ""), lang.toUpperCase(), scoreText(m.macro_f1, m.macro_f1_ci),
      rateText(m.dispute_recall), rateText(m.dispute_detected_recall), rateText(m.human_request_recall), rateText(m.slot_accuracy),
      rateText(m.coverage_at_tau), rateText(m.precision_at_tau), score(m.ece),
      Object.entries(m.per_class_f1).map(([k, v]) => `${k.replace(/_/g, " ")} ${score(v)}`).join(" · "),
    ]),
  );
  return (
    <Section title="Intent classifier" file={file} data="classifier.json"
      hint={`Frozen test split: ${sentences} sentences, ${data.test_split.injection_rows ?? "—"} injection rows apart. Confidence threshold tau ${score(data.tau)}. Rates show their count and 95% Wilson interval; macro-F1 its 95% bootstrap interval.`}>
      <Table
        head={["Arm", "Lang", "Macro-F1", "Dispute recall", "Dispute flag recall", "Person-request recall", "Slot accuracy", "Coverage at tau", "Precision at tau", "ECE", "F1 per intent"]}
        rows={rows} />
      <Table head={["Arm", "Version", "p95", "Per 1,000", "Meets floors", "McNemar p vs best", "Person requests answered out of scope"]}
        rows={data.arms.map((a) => [a.arm, a.version, milliseconds(a.p95_ms), dollars(a.cost_per_1000_usd), yes(a.meets_floors), score(a.mcnemar_p_vs_best), String(a.human_request_answered_out_of_scope ?? "—")])} />
      <h3 className="mt-5 text-sm font-semibold">Prompt-injection detectors</h3>
      <Table head={["Detector", "Recall", "False positives"]} rows={data.injection.map((d) => [d.arm, rateText(d.recall), rateText(d.false_positive_rate)])} />
    </Section>
  );
}

// ---- (7) fraud model against the bank's score ----
export function FraudSection({ file }: { file: Insight<FraudData> }) {
  const data = file.data;
  const { bind, node } = useTip();
  const test = data.windows.test;
  const subsets = ["all", "card"];
  return (
    <Section title="Fraud model against the bank's score" file={file} data="fraud_benchmark.json"
      hint={`Test window ${test.from} to ${test.to}: ${test.transactions?.toLocaleString("en-US") ?? "—"} transactions, ${test.frauds ?? "—"} frauds. PR-AUC (scale 0 to 1) with its 95% bootstrap interval; S-bank is the bank's own score. Chosen: ${data.chosen_arm ?? "—"}.`}>
      <div className="mt-4 space-y-4">
        {subsets.map((s) => (
          <div key={s}>
            <h3 className="text-sm font-semibold">{s === "all" ? "All products" : "Cards only"}</h3>
            <div className="mt-2 space-y-1.5">
              {data.arms.map((a) => {
                const m = a.subsets[s];
                const ci = m?.pr_auc_ci;
                const has = m?.pr_auc !== null && m?.pr_auc !== undefined;
                const color = a.arm === "S-bank" ? "var(--arm-2)" : "var(--arm-1)";
                return (
                  <div key={a.arm} tabIndex={0} role="img" aria-label={`${a.arm}, ${s}: PR-AUC ${scoreText(m?.pr_auc, ci)}`} className={`grid items-center gap-x-3 rounded-sm sm:grid-cols-[14rem_1fr_9rem] ${FOCUS}`}
                    {...bind(<TipBody title={`${a.arm} · ${s}`} rows={[["PR-AUC", score(m?.pr_auc)], ["95% interval", interval(ci)], ["Brier", score(m?.brier)],
                      ["Recall at bank precision 0.80", rateText(m?.recall_at_bank_precision?.["0.80"])]]} note="[data] test window, labels read once" />)}>
                    <span className="flex items-center gap-1.5 truncate text-xs"><Swatch color={color} />{a.arm}{a.arm === data.chosen_arm ? " (chosen)" : ""}</span>
                    <div className="relative h-4">
                      <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
                      {has && ci && ci[0] !== null && ci[1] !== null ? <div className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full opacity-35" style={{ left: `${ci[0] * 100}%`, width: `${Math.max((ci[1] - ci[0]) * 100, 0.5)}%`, background: color }} /> : null}
                      {has ? <div className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card" style={{ left: `${(m!.pr_auc ?? 0) * 100}%`, background: color }} /> : null}
                    </div>
                    <span className="text-xs tabular-nums">{score(m?.pr_auc)}<span className="text-muted-foreground"> · {interval(ci)}</span></span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <TableView
        head={["Arm", "Products", "PR-AUC", "Brier", "Recall at bank precision 0.80", "Recall at bank precision 0.95", "Recall of frauds with no score at 1% alerts", "Passes rule", "Score p95"]}
        rows={data.arms.flatMap((a) => subsets.map((s) => {
          const m = a.subsets[s];
          return [a.arm, s, scoreText(m?.pr_auc, m?.pr_auc_ci), score(m?.brier), rateText(m?.recall_at_bank_precision?.["0.80"]), rateText(m?.recall_at_bank_precision?.["0.95"]),
            rateText(m?.recall_no_score_at_1pct), yes(a.passes_rule), `${score(a.cost.score_p95_ms)} ms`];
        }))} />
      <p className="mt-3 text-xs text-muted-foreground">The model is a second signal for the analyst; zones stay with the bank&apos;s score.</p>
      {node}
    </Section>
  );
}
