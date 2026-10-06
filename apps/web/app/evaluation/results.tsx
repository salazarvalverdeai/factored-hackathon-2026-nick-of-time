"use client";

// /evaluation content for evaluation_summary.json (spec 12 §7.3, parts 1 to 4). Nothing is computed here: every
// number is the harness's. Every rate shows its numerator, denominator and interval on hover, on keyboard focus and
// in the table view (AC-06, AC-07). Reading order per block: title, the big figure, the chart, one line, the tables
// (collapsed) and a muted footer with the run's metadata.
import { BigFigure, DevChip, Explain, Footer, IntervalBar } from "./explain";
import { FOCUS, Swatch, TableView, TipBody, useTip } from "@/app/analytics/charts";
import { CountText, Reveal, Stagger } from "@/components/motion";
import { staggerDelay } from "@/lib/motion";
import {
  armModel,
  headlineExplanation,
  METRICS,
  METRIC_MEANING,
  d070View,
  developmentNotice,
  type D070View,
  dollars,
  milliseconds,
  rateParts,
  rateText,
  type EvaluationArm,
  type EvaluationData,
  type Insight,
  type Rate,
} from "@/lib/evaluation";

// Arm colors in fixed order, checked with the palette validator on the light and dark card surfaces (violet and teal
// as on /analytics, plus a deep violet on light and a pale violet on dark; amber stays for urgency).
// A fourth arm and beyond use the neutral context color and keep their label.
const PALETTE =
  "[--arm-1:#7c3aed] dark:[--arm-1:#8b5cf6] [--arm-2:#0d9488] [--arm-3:#4c1d95] dark:[--arm-3:#c4b5fd] " +
  "[--arm-rest:color-mix(in_oklab,var(--muted-foreground)_70%,transparent)]";
const armColor = (index: number) => (index < 3 ? `var(--arm-${index + 1})` : "var(--arm-rest)");
const SECONDARY = ["unsafe_outcomes", "pass_4"];
const CELL_METRICS = ["safe_automated_resolution", "unsafe_outcomes", "pass_4"];
const label = (key: string) => METRICS.find((m) => m.key === key)?.label ?? key;

function Legend({ arms }: { arms: EvaluationArm[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {arms.map((arm, i) => (
        <li key={arm.arm} className="inline-flex items-center gap-1.5">
          <Swatch color={armColor(i)} />
          <span className="text-foreground">{arm.arm}</span>
          {armModel(arm.run_meta) ? <span>· {armModel(arm.run_meta)}</span> : <span>· no LLM</span>}
        </li>
      ))}
    </ul>
  );
}

/** One arm: safe automated resolution as the big figure, the other rates and the cost in a quieter row under it. */
function Headline({ arm, index, secondary }: { arm: EvaluationArm; index: number; secondary?: Rate }) {
  const main = rateParts(arm.overall.safe_automated_resolution);
  const second = secondary && secondary.value !== null ? rateParts(secondary) : null;
  const small: [string, string, string][] = [
    ...SECONDARY.map((key): [string, string, string] => {
      const parts = rateParts(arm.overall[key]);
      return [label(key), parts.value, `${parts.count} · 95% CI ${parts.interval}`];
    }),
    ["Latency p95 per turn", milliseconds(arm.latency_ms.p95), `p50 ${milliseconds(arm.latency_ms.p50)}`],
    ["Cost per case", dollars(arm.cost_usd.per_case), `per resolution ${dollars(arm.cost_usd.per_resolution)}`],
  ];
  return (
    <section aria-label={`Arm ${arm.arm}`} className="rounded-lg border bg-card p-6">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Swatch color={armColor(index)} />
        {arm.arm}
        <span className="font-normal text-muted-foreground">{armModel(arm.run_meta) ?? "rules and templates, no LLM"}</span>
      </h3>
      <p className="mt-4 text-sm font-medium">{label("safe_automated_resolution")}</p>
      <div className="mt-1 flex flex-wrap gap-x-8 gap-y-3">
        <BigFigure value={main.value} label="[simulated]" caption={<>{second ? "Official · sealed rules · " : ""}{main.count} · 95% CI {main.interval}</>} />
        {second ? <BigFigure value={second.value} label="[simulated]" caption={<>With D-070 · {second.count} · 95% CI {second.interval}</>} /> : null}
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 border-t pt-4 sm:grid-cols-4">
        {small.map(([name, value, note]) => (
          <div key={name} className="min-w-0">
            <dt className="text-xs text-muted-foreground">{name}</dt>
            <dd className="text-lg font-semibold tabular-nums tracking-tight">
              <CountText text={value} />
            </dd>
            <dd className="text-xs tabular-nums text-muted-foreground">{note}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function HeldoutScores({ view }: { view: D070View }) {
  const unsafe = view.metrics.find((m) => m.key === "unsafe_outcomes")!;
  return (
    <section aria-label="Held-out scored twice" data-slot="d070-scores" className={`rounded-lg border bg-card p-5 ${PALETTE}`}>
      <h2 className="text-base font-semibold">
        Held-out, scored two ways <span className="font-mono text-xs font-normal text-muted-foreground">{view.tag}</span>
      </h2>
      <p className="mt-1 text-sm" data-slot="d070-sentence">{view.sentence}</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {unsafe.rows.map((r, i) => {
          const p = rateParts(r.official);
          return (
            <div key={r.arm} className="rounded-md border p-3" data-slot="unsafe-card">
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Swatch color={armColor(i)} />{r.arm} · {r.model}</p>
              <p className="text-2xl font-semibold tabular-nums">{r.official.numerator}/{r.official.denominator}</p>
              <p className="text-xs text-muted-foreground">unsafe outcomes · 95% CI {p.interval}</p>
            </div>
          );
        })}
      </div>
      <div className="mt-5 space-y-5">
        {view.metrics.filter((m) => m.key !== "unsafe_outcomes").map((m) => (
          <div key={m.key}>
            <p className="text-sm font-medium">{m.label}</p>
            {m.rows.map((r, i) => (
              <div key={r.arm} className="mt-1.5 grid gap-x-4 gap-y-1 sm:grid-cols-2">
                {([["official", view.officialLabel, r.official], ["secondary", view.secondaryLabel, r.secondary]] as const).map(([k, lab, rate]) => {
                  const parts = rateParts(rate);
                  const empty = parts.value === "—";
                  return (
                    <div key={k} role="img" aria-label={`${m.label}, ${r.arm}, ${lab}: ${rateText(rate)}`} data-slot={`d070-${k}`}>
                      <p className={k === "official" ? "text-xs font-medium" : "text-xs text-muted-foreground"}>{lab}</p>
                      <div className="flex items-center gap-3">
                        <span className="w-8 shrink-0 text-xs text-muted-foreground">{r.arm}</span>
                        <IntervalBar value={empty ? null : rate.value} low={rate.ci_low} high={rate.ci_high} color={armColor(i)} />
                        <span className="w-28 shrink-0 text-right text-xs tabular-nums">
                          {parts.value}<span className="text-muted-foreground"> · {empty ? "n/a" : `${rate.numerator}/${rate.denominator}`}</span>
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        ))}
      </div>
      <TableView
        head={["Metric", "Arm", view.officialLabel, view.secondaryLabel]}
        rows={view.metrics.flatMap((m) => m.rows.map((r) => [m.label, `${r.arm} (${r.model})`, rateText(r.official), rateText(r.secondary)]))}
      />
    </section>
  );
}

function Breakdown({ arms }: { arms: EvaluationArm[] }) {
  const rows = arms.flatMap((arm) =>
    arm.cells.map((cell) => [
      arm.arm,
      cell.language,
      cell.type,
      cell.segment,
      `${cell.n_cases}${cell.small ? " (small)" : ""}`,
      ...CELL_METRICS.map((key) => rateText(cell.metrics[key])),
    ]),
  );
  return (
    <details className="mt-3">
      <summary className={`cursor-pointer rounded-sm text-xs text-muted-foreground ${FOCUS}`}>By language, case type and segment</summary>
      <p className="mt-2 text-xs text-muted-foreground">n is the cases in the cell; a cell marked small has fewer than 5: read its interval, not its rate.</p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-xs tabular-nums">
          <thead className="text-muted-foreground">
            <tr>
              {["Arm", "Language", "Type", "Segment", "n", ...CELL_METRICS.map(label)].map((h) => (
                <th key={h} className="border-b py-1.5 pr-4 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className="border-b py-1.5 pr-4 whitespace-nowrap">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function Comparison({ arms }: { arms: EvaluationArm[] }) {
  const { bind, node } = useTip();
  return (
    <Reveal as="figure" className={`rounded-lg border bg-card p-6 text-card-foreground ${PALETTE}`}>
      <h2 className="text-base font-semibold">The same cases on every arm</h2>
      <div className="mt-3">
        <Legend arms={arms} />
      </div>
      <div className="mt-5 space-y-5">
        {METRICS.map((metric) => (
          <div key={metric.key} className="grid gap-x-4 gap-y-1.5 sm:grid-cols-[14rem_1fr]">
            <p className="text-sm">
              {metric.label}
              <span className="block text-xs text-muted-foreground">{metric.good === "high" ? "higher is better" : "lower is better"}</span>
            </p>
            <div className="space-y-1.5">
              {arms.map((arm, i) => {
                const rate = arm.overall[metric.key];
                const parts = rateParts(rate);
                const empty = parts.value === "—";
                return (
                  <div
                    key={arm.arm}
                    tabIndex={0}
                    role="img"
                    aria-label={`${metric.label}, ${arm.arm}: ${rateText(rate)}`}
                    className={`flex items-center gap-3 rounded-sm ${FOCUS}`}
                    {...bind(
                      <TipBody
                        title={`${metric.label} · ${arm.arm}`}
                        rows={[
                          ["Rate", parts.value],
                          ["Runs", parts.count],
                          ["95% interval", parts.interval],
                        ]}
                        note={`${METRIC_MEANING[metric.key]} [simulated] scripted cases, final state compared.`}
                      />,
                    )}
                  >
                    <span className="w-8 shrink-0 text-xs text-muted-foreground">{arm.arm}</span>
                    <IntervalBar value={empty ? null : rate.value} low={rate.ci_low} high={rate.ci_high} color={armColor(i)} delay={staggerDelay(i, 90)} />
                    <span className="w-28 shrink-0 text-right text-xs tabular-nums">
                      {parts.value}
                      <span className="text-muted-foreground"> · {empty ? "n/a" : `${rate.numerator}/${rate.denominator}`}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <Explain detail="harness" className="mt-5">
        Dot: the rate; band: its 95% interval, 0% to 100%. Arms whose bands overlap cannot be told apart.
      </Explain>
      <TableView
        head={["Metric", ...arms.map((a) => a.arm)]}
        rows={METRICS.map((m) => [m.label, ...arms.map((a) => rateText(a.overall[m.key]))])}
      />
      <Breakdown arms={arms} />
      {node}
    </Reveal>
  );
}

export function EvaluationResults({ file }: { file: Insight<EvaluationData> }) {
  const data = file.data;
  const run = [
    `set ${data.set}`,
    `${data.cases} cases x ${data.runs_per_case} runs`,
    `arms ${data.arms.map((a) => a.arm).join(", ")}`,
    `protocol ${data.protocol?.status ?? "UNSEALED"}`,
    `case file sha256 ${data.cases_sha256.slice(0, 12)}…`,
  ].join(" · ");
  return (
    <div className={`space-y-4 ${PALETTE}`}>
      <h2 className="pt-2 text-lg font-semibold">
        Agent evaluation
        <DevChip show={developmentNotice(data) !== null} />
      </h2>
      {(() => {
        const why = headlineExplanation(data.arms.map((a) => ({ official: a.overall.safe_automated_resolution, secondary: data.scores_d070?.arms?.[a.arm]?.secondary?.safe_automated_resolution })));
        return why ? <p data-slot="headline-why" className="max-w-3xl text-sm text-muted-foreground">{why}</p> : null;
      })()}
      <Stagger className="grid gap-4 lg:grid-cols-2" count={data.arms.length}>
        {data.arms.map((arm, i) => (
          <Headline key={arm.arm} arm={arm} index={i} secondary={data.scores_d070?.arms?.[arm.arm]?.secondary?.safe_automated_resolution} />
        ))}
      </Stagger>
      {d070View(data) && <HeldoutScores view={d070View(data)!} />}
      <Comparison arms={data.arms} />
      <Footer>
        {data.label} {file.source} · generated {file.generated_at.slice(0, 10)} at {file.git_sha} · {run}
      </Footer>
    </div>
  );
}
