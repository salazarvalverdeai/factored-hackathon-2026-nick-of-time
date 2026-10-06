"use client";

// /evaluation content for benchmark.json, classifier.json and fraud_benchmark.json (spec 12 §7.3, parts 5 to 7).
// Nothing is computed here: every number is the exporter's. Every rate shows its numerator, denominator and interval on
// hover, on keyboard focus and in the table view (AC-06, AC-07). Each section reads: title, the big figure, the charts,
// one plain line with "Detail →", the tables (collapsed) and a muted footer with the file's metadata.
import { useState, type CSSProperties, type ReactNode } from "react";
import { FOCUS, Swatch, TableView, TipBody, useTip } from "@/app/analytics/charts";
import { BigFigure, DevChip, Explain, Footer, IntervalBar } from "./explain";
import { CountText, MotionGroup, Reveal } from "@/components/motion";
import { fitStep, part, staggerDelay } from "@/lib/motion";
import { classifierRunNote, sealedRunNote,
  costQualityPoints,
  dollars,
  GENERATOR_FLAG,
  generatorFlag,
  interval,
  milliseconds,
  protocolNotice,
  rateParts,
  rateText,
  score,
  scoreText,
  type BenchmarkData,
  type ClassifierData,
  type FraudData,
  type Insight,
  type Protocol,
  type DETAILS,
  type Rate,
} from "@/lib/evaluation";

const PALETTE = "[--arm-1:#7c3aed] dark:[--arm-1:#8b5cf6] [--arm-2:#0d9488] [--arm-3:#4c1d95] dark:[--arm-3:#c4b5fd]";
const yes = (v: boolean | null) => (v === null ? "—" : v ? "yes" : "no");

// A wide table shows a shadow at the edge that has more columns, only while there is more to scroll (AC-09).
const EDGE = "color-mix(in oklab, var(--foreground) 30%, transparent)";
const SCROLL_SHADOW: CSSProperties = {
  background: [
    "linear-gradient(to right, var(--card) 40%, transparent) left / 2rem 100% no-repeat local",
    "linear-gradient(to left, var(--card) 40%, transparent) right / 2rem 100% no-repeat local",
    `linear-gradient(to right, ${EDGE}, transparent) left / 1rem 100% no-repeat scroll`,
    `linear-gradient(to left, ${EDGE}, transparent) right / 1rem 100% no-repeat scroll`,
  ].join(", "),
};

function Section({ title, hint, detail, file, data, figure, tables, meta, note, children }: {
  title: string; hint: string; detail: keyof typeof DETAILS; file: Insight<{ label: string; protocol: Protocol }>; data: string;
  figure?: ReactNode; tables: ReactNode; meta?: string; note?: { text: string | null; slot: string }; children: ReactNode;
}) {
  return (
    <section aria-label={title} className={PALETTE} data-file={data}>
      <Reveal className="rounded-lg border bg-card p-6 text-card-foreground">
        <h2 className="text-base font-semibold">
          {title}
          <DevChip show={protocolNotice(file.data.protocol) !== null} />
        </h2>
        {note?.text ? <p className="mt-1 text-sm font-medium" data-slot={note.slot}>{note.text}</p> : null}
        {figure ? <div className="mt-4 flex flex-wrap gap-x-10 gap-y-4">{figure}</div> : null}
        <div className="mt-5">{children}</div>
        <Explain detail={detail} className="mt-5">{hint}</Explain>
        {tables}
        <Footer>
          {file.data.label} {file.source} · generated {file.generated_at.slice(0, 10)} at {file.git_sha}{meta ? ` · ${meta}` : ""}
        </Footer>
      </Reveal>
    </section>
  );
}

/** A table collapsed behind its summary (keyboard: Tab to the summary, Enter or Space opens it; the region then scrolls). */
function Table({ title, head, rows, wrap = false }: { title: string; head: string[]; rows: string[][]; wrap?: boolean }) {
  return (
    <details className="mt-3">
      <summary className={`cursor-pointer rounded-sm text-xs text-muted-foreground ${FOCUS}`}>{title}</summary>
      <div className={`mt-2 overflow-x-auto rounded-sm ${FOCUS}`} style={SCROLL_SHADOW} tabIndex={0} role="region" aria-label={`Table: ${head.join(", ")}`}>
        <table className="w-full text-left text-xs tabular-nums">
          <thead className="text-muted-foreground">
            <tr>{head.map((h) => <th key={h} className="border-b py-1.5 pr-4 font-normal">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>{row.map((c, j) => <td key={j} className={`border-b py-1.5 pr-4 ${wrap && j === row.length - 1 ? "" : "whitespace-nowrap"}`}>{c}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

type BarRow = { key: string; label: string; color: string; value: number | null; low: number | null; high: number | null; aria: string; tip: ReactNode; right: ReactNode };

/** Rows of a bar with its 95% interval on a 0 to 1 scale; each row is focusable and shows its tooltip on hover and focus. */
function BarRows({ rows, bind }: { rows: BarRow[]; bind: ReturnType<typeof useTip>["bind"] }) {
  return (
    <div className="mt-2 space-y-1.5">
      {rows.map((r, i) => (
        <div key={r.key} tabIndex={0} role="img" aria-label={r.aria} className={`grid items-center gap-x-3 rounded-sm sm:grid-cols-[10rem_1fr_11rem] ${FOCUS}`} {...bind(r.tip)}>
          <span className="flex items-center gap-1.5 truncate text-xs"><Swatch color={r.color} />{r.label}</span>
          <div className="flex"><IntervalBar value={r.value} low={r.low} high={r.high} color={r.color} delay={staggerDelay(i, 90)} /></div>
          <span className="text-xs tabular-nums">{r.right}</span>
        </div>
      ))}
    </div>
  );
}

const armColor = (i: number) => (i < 3 ? `var(--arm-${i + 1})` : "var(--arm-rest, var(--muted-foreground))");

// ---- (5) benchmark: cost on x, quality on y ----
const W = 640, H = 300, L = 52, R = 16, T = 12, B = 40;

export function BenchmarkSection({ file }: { file: Insight<BenchmarkData> }) {
  const data = file.data;
  const languages = Object.keys(data.b1.arms.find((a) => a.macro_f1)?.macro_f1 ?? { es: 0, pt: 0 });
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
  const pick = points.find((p) => p.chosen);
  return (
    <Section title="Model benchmark: cost against quality" file={file} data="benchmark.json" detail="benchmark"
      figure={pick ? <BigFigure value={score(pick.quality)} label="[simulated]" caption={`macro-F1 of ${pick.arm}, the chosen model, ${language.toUpperCase()} · ${dollars(pick.cost)} per 1,000 messages`} /> : null}
      hint="One dot per model: understanding quality against cost; filled dots are on the Pareto front, the ringed one is chosen."
      meta={`run ${data.run_date} · ${data.mode} mode${chosen ? ` · chosen ${chosen}` : ""}`}
      note={{ text: sealedRunNote(data as never), slot: "sealed-run-note" }}
      tables={<>
        <TableView
          head={["Arm", "Status", `Macro-F1 ${language.toUpperCase()}`, "Dispute recall", "Person-request recall", "Slot accuracy", "p95", "Per 1,000", "Pareto", "Meets bar", "Production gate", "Flag"]}
          rows={data.b1.arms.map((a) => [a.arm, a.status === "ok" ? "ok" : `${a.status}${a.unavailable_reason ? `: ${a.unavailable_reason}` : ""}`,
            scoreText(a.macro_f1?.[language], a.macro_f1_ci?.[language]), rateText(a.dispute_recall), rateText(a.human_request_recall), rateText(a.slot_accuracy),
            milliseconds(a.p95_ms), dollars(a.cost_per_1000_usd), yes(a.pareto), yes(a.meets_bar), yes(a.gate.production_pass), generatorFlag(a) ?? "—"])}
        />
        <Table title="Whole system on the dev cases, as a table" head={["Arm", "Safe automated resolution", "Unsafe outcomes", "Receipt with its deadline", "Status told = status read", "p95 per turn", "Cost per case"]}
          rows={data.b2.arms.map((a) => [a.arm, rateText(a.safe_automated_resolution as Rate), rateText(a.unsafe_outcomes as Rate), rateText(a.receipt_rate as Rate),
            rateText(a.coherence_rate as Rate), milliseconds(a.p95_ms as number | null), dollars(a.cost_per_case_usd)])} />
      </>}>
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        {languages.map((l) => (
          <button key={l} type="button" aria-pressed={l === language} onClick={() => setLanguage(l)}
            className={`rounded-md border px-2 py-1 ${FOCUS} ${l === language ? "bg-muted font-medium text-foreground" : ""}`}>
            {l.toUpperCase()}
          </button>
        ))}
        <span className="inline-flex items-center gap-1.5"><Swatch color="var(--arm-1)" /> on the Pareto front</span>
      </div>
      {points.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">No arm has a cost and a score in this language yet.</p>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 h-auto w-full max-w-3xl" role="group" aria-label="Cost against macro-F1 per model">
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
          {/* the dots fade in one by one, then the Pareto front joins them (motion kit; in place at once with reduced motion) */}
          <MotionGroup as="g" step={fitStep(points.length, 60, 300, 300)} after={points.length * fitStep(points.length, 60, 300, 300) + 300}>
          {front.length > 1 ? <polyline {...part.after} fill="none" stroke="var(--arm-1)" strokeOpacity={0.5} strokeDasharray="4 3" points={front.map((p) => `${x(p.cost)},${y(p.quality)}`).join(" ")} /> : null}
          {points.map((p, i) => {
            const a = p.row;
            return (
              <g key={p.arm} {...part.fade} style={{ "--motion-i": i } as CSSProperties}>
                {p.chosen ? <circle cx={x(p.cost)} cy={y(p.quality)} r={11} fill="none" stroke="var(--arm-2)" strokeWidth={2} /> : null}
                <circle tabIndex={0} role="img" cx={x(p.cost)} cy={y(p.quality)} r={6} strokeWidth={2} stroke="var(--arm-1)"
                  fill={p.pareto ? "var(--arm-1)" : "var(--card)"} className="outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  aria-label={`${p.arm}: macro-F1 ${scoreText(p.quality, p.ci)}, ${dollars(p.cost)} per 1,000 messages, p95 ${milliseconds(a.p95_ms)}${p.chosen ? ", chosen" : ""}${generatorFlag(a) ? `, ${GENERATOR_FLAG}` : ""}`}
                  {...bind(
                    <TipBody title={`${p.arm}${p.chosen ? " · chosen" : ""}${generatorFlag(a) ? " · flagged" : ""}`}
                      rows={[["Macro-F1", score(p.quality)], ["95% interval", interval(p.ci)], ["Cost per 1,000", dollars(p.cost)], ["p95", milliseconds(a.p95_ms)],
                        ["Dispute recall", rateText(a.dispute_recall)]]}
                      note={`[simulated] ${a.price.label} price ${a.price.date}${generatorFlag(a) ? ` · ${GENERATOR_FLAG}` : ""}`} />,
                  )} />
                <text x={x(p.cost) + 10} y={y(p.quality) - 9} fontSize={10} fill="currentColor">{p.arm}{generatorFlag(a) ? " *" : ""}</text>
              </g>
            );
          })}
          </MotionGroup>
        </svg>
      )}
      <h3 className="mt-6 text-sm font-semibold">Whole system on the dev cases <span className="font-normal text-muted-foreground">({data.b2.set}, {data.b2.cases} cases x {data.b2.runs_per_case} runs)</span></h3>
      {[["safe_automated_resolution", "Safe automated resolution", "higher is better"], ["unsafe_outcomes", "Unsafe outcomes", "lower is better"]].map(([key, name, good]) => (
        <div key={key} className="mt-3">
          <h4 className="text-xs font-medium">{name} <span className="font-normal text-muted-foreground">· {good}</span></h4>
          <BarRows bind={bind} rows={data.b2.arms.map((a, i) => {
            const rate = a[key] as Rate;
            const has = rate.value !== null && rate.denominator > 0;
            return { key: a.arm, label: a.arm, color: armColor(i), value: has ? rate.value : null, low: rate.ci_low, high: rate.ci_high,
              aria: `${name}, ${a.arm}: ${rateText(rate)}`,
              tip: <TipBody title={`${name} · ${a.arm}`} rows={[["Rate", rateParts(rate).value], ["Runs", rateParts(rate).count], ["95% interval", rateParts(rate).interval]]} note="[simulated] dev cases, final state compared" />,
              right: <><CountText text={rateParts(rate).value} /><span className="text-muted-foreground"> · {has ? `${rate.numerator}/${rate.denominator}` : "n/a"}</span></> };
          })} />
        </div>
      ))}
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
      a.arm + (a.arm === data.chosen_arm ? " (chosen)" : "") + (generatorFlag(a) ? " *" : ""), lang.toUpperCase(), scoreText(m.macro_f1, m.macro_f1_ci),
      rateText(m.dispute_recall), rateText(m.dispute_detected_recall), rateText(m.human_request_recall), rateText(m.slot_accuracy),
      rateText(m.coverage_at_tau), rateText(m.precision_at_tau), score(m.ece),
    ]),
  );
  // F1 per intent gets its own table, so the main one keeps its columns readable at 1280 px.
  const perIntent = data.arms.flatMap((a) =>
    Object.entries(a.by_language).map(([lang, m]) => [a.arm, lang.toUpperCase(), Object.entries(m.per_class_f1).map(([k, v]) => `${k.replace(/_/g, " ")} ${score(v)}`).join(" · ")]),
  );
  const { bind, node } = useTip();
  const languages = [...new Set(data.arms.flatMap((a) => Object.keys(a.by_language)))];
  const chosen = data.arms.find((a) => a.arm === data.chosen_arm);
  return (
    <Section title="Intent classifier" file={file} data="classifier.json" detail="classifier"
      figure={chosen ? languages.filter((l) => chosen.by_language[l]).map((l) => (
        <BigFigure key={l} value={score(chosen.by_language[l].macro_f1)} label="[simulated]" caption={`macro-F1 of ${chosen.arm}, the chosen arm, ${l.toUpperCase()}`} />
      )) : null}
      hint="Does the system read what the customer wants? Macro-F1 per arm and language, from 0 to 1, with its 95% interval."
      meta={`frozen test split: ${sentences} sentences, ${data.test_split.injection_rows ?? "—"} injection rows apart · tau ${score(data.tau)}`}
      note={{ text: classifierRunNote(data), slot: "classifier-run-note" }}
      tables={<>
        <Table title="View as table"
          head={["Arm", "Lang", "Macro-F1", "Dispute recall", "Dispute flag recall", "Person-request recall", "Slot accuracy", "Coverage at tau", "Precision at tau", "ECE"]}
          rows={rows} />
        <Table title="F1 per intent" head={["Arm", "Lang", "F1 per intent"]} rows={perIntent} wrap />
        <Table title="Cost, latency and floors" head={["Arm", "Version", "p95", "Per 1,000", "Meets floors", "McNemar p vs best", "Person requests answered out of scope", "Flag"]}
          rows={data.arms.map((a) => [a.arm, a.version, milliseconds(a.p95_ms), dollars(a.cost_per_1000_usd), yes(a.meets_floors), score(a.mcnemar_p_vs_best), String(a.human_request_answered_out_of_scope ?? "—"), generatorFlag(a) ?? "—"])} />
        <Table title="Prompt-injection detectors" head={["Detector", "Recall", "False positives"]} rows={data.injection.map((d) => [d.arm, rateText(d.recall), rateText(d.false_positive_rate)])} />
      </>}>
      {languages.map((lang, k) => (
        <div key={lang} className={k ? "mt-5" : ""}>
          <h3 className="text-sm font-semibold">Macro-F1, {lang.toUpperCase()}</h3>
          <BarRows bind={bind} rows={data.arms.flatMap((a, i) => {
            const m = a.by_language[lang];
            if (!m) return [];
            const chosen = a.arm === data.chosen_arm;
            const flag = generatorFlag(a);
            return [{ key: a.arm, label: `${a.arm}${chosen ? " (chosen)" : ""}${flag ? " *" : ""}`, color: armColor(i), value: m.macro_f1, low: m.macro_f1_ci?.[0] ?? null, high: m.macro_f1_ci?.[1] ?? null,
              aria: `${a.arm}, ${lang.toUpperCase()}: macro-F1 ${scoreText(m.macro_f1, m.macro_f1_ci)}${flag ? `, ${flag}` : ""}`,
              tip: <TipBody title={`${a.arm} · ${lang.toUpperCase()}${chosen ? " · chosen" : ""}`}
                rows={[["Macro-F1", score(m.macro_f1)], ["95% interval", interval(m.macro_f1_ci)], ["Dispute recall", rateText(m.dispute_recall)], ["Person-request recall", rateText(m.human_request_recall)]]}
                note={`[simulated] frozen test split${data.test_review === "rules-v1" ? ", decided by fixed rules" : ""}${flag ? ` · ${flag}` : ""}`} />,
              right: <><CountText text={score(m.macro_f1)} /><span className="text-muted-foreground"> · {interval(m.macro_f1_ci)}</span></> }];
          })} />
        </div>
      ))}
      {node}
    </Section>
  );
}

// ---- (7) fraud model against the bank's score ----
export function FraudSection({ file }: { file: Insight<FraudData> }) {
  const data = file.data;
  const { bind, node } = useTip();
  const test = data.windows.test;
  const subsets = ["all", "card"];
  const chosen = data.arms.find((a) => a.arm === data.chosen_arm)?.subsets.all;
  return (
    <Section title="Fraud model against the bank's score" file={file} data="fraud_benchmark.json" detail="fraud"
      figure={chosen?.pr_auc !== null && chosen?.pr_auc !== undefined
        ? <BigFigure value={score(chosen.pr_auc)} label="[data]" caption={`PR-AUC of ${data.chosen_arm}, the chosen arm, all products${data.chosen_arm === "S-bank" ? " (the bank's own score)" : ""}`} />
        : null}
      hint="Does a model of ours rank fraud better than the bank's score (S-bank)? PR-AUC from 0 to 1, higher is better; zones stay with the bank's score."
      meta={`test window ${test.from} to ${test.to}: ${test.transactions?.toLocaleString("en-US") ?? "—"} transactions, ${test.frauds ?? "—"} frauds`}
      note={{ text: sealedRunNote(data as never), slot: "sealed-run-note" }}
      tables={
        <TableView
          head={["Arm", "Products", "PR-AUC", "Brier", "Recall at bank precision 0.80", "Recall at bank precision 0.95", "Recall of frauds with no score at 1% alerts", "Passes rule", "Score p95"]}
          rows={data.arms.flatMap((a) => subsets.map((s) => {
            const m = a.subsets[s];
            return [a.arm, s, scoreText(m?.pr_auc, m?.pr_auc_ci), score(m?.brier), rateText(m?.recall_at_bank_precision?.["0.80"]), rateText(m?.recall_at_bank_precision?.["0.95"]),
              rateText(m?.recall_no_score_at_1pct), yes(a.passes_rule), `${score(a.cost.score_p95_ms)} ms`];
          }))} />
      }>
      <div className="space-y-5">
        {subsets.map((s) => (
          <div key={s}>
            <h3 className="text-sm font-semibold">{s === "all" ? "All products" : "Cards only"}</h3>
            <div className="mt-2 space-y-1.5">
              {data.arms.map((a, i) => {
                const m = a.subsets[s];
                const ci = m?.pr_auc_ci;
                const has = m?.pr_auc !== null && m?.pr_auc !== undefined;
                const color = a.arm === "S-bank" ? "var(--arm-2)" : "var(--arm-1)";
                return (
                  <div key={a.arm} tabIndex={0} role="img" aria-label={`${a.arm}, ${s}: PR-AUC ${scoreText(m?.pr_auc, ci)}`} className={`grid items-center gap-x-3 rounded-sm sm:grid-cols-[14rem_1fr_9rem] ${FOCUS}`}
                    {...bind(<TipBody title={`${a.arm} · ${s}`} rows={[["PR-AUC", score(m?.pr_auc)], ["95% interval", interval(ci)], ["Brier", score(m?.brier)],
                      ["Recall at bank precision 0.80", rateText(m?.recall_at_bank_precision?.["0.80"])]]} note="[data] test window, labels read once" />)}>
                    <span className="flex items-center gap-1.5 truncate text-xs"><Swatch color={color} />{a.arm}{a.arm === data.chosen_arm ? " (chosen)" : ""}</span>
                    <IntervalBar value={has ? m!.pr_auc ?? null : null} low={ci?.[0] ?? null} high={ci?.[1] ?? null} color={color} delay={staggerDelay(i, 90)} />
                    <span className="text-xs tabular-nums"><CountText text={score(m?.pr_auc)} /><span className="text-muted-foreground"> · {interval(ci)}</span></span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {node}
    </Section>
  );
}
