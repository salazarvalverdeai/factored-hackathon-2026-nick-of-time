"use client";

// /evaluation content for evaluation_summary.json (spec 12 §7.3, parts 1 to 4). Nothing is computed here: every
// number is the harness's. Every rate shows its numerator, denominator and interval on hover, on keyboard focus and
// in the table view (AC-06, AC-07).
import { Explain, IntervalBar } from "./explain";
import { FOCUS, Swatch, TableView, TipBody, useTip } from "@/app/analytics/charts";
import {
  METRICS,
  METRIC_MEANING,
  developmentNotice,
  dollars,
  milliseconds,
  rateParts,
  rateText,
  type EvaluationArm,
  type EvaluationData,
  type Insight,
} from "@/lib/evaluation";

// Arm colors in fixed order, checked with the palette validator on the light and dark card surfaces (violet and teal
// as on /analytics, plus a deep violet on light and a pale violet on dark; amber stays for urgency).
// A fourth arm and beyond use the neutral context color and keep their label.
const PALETTE =
  "[--arm-1:#7c3aed] dark:[--arm-1:#8b5cf6] [--arm-2:#0d9488] [--arm-3:#4c1d95] dark:[--arm-3:#c4b5fd] " +
  "[--arm-rest:color-mix(in_oklab,var(--muted-foreground)_70%,transparent)]";
const armColor = (index: number) => (index < 3 ? `var(--arm-${index + 1})` : "var(--arm-rest)");
const HEADLINE = ["safe_automated_resolution", "unsafe_outcomes", "pass_4"];
const CELL_METRICS = ["safe_automated_resolution", "unsafe_outcomes", "pass_4"];
const label = (key: string) => METRICS.find((m) => m.key === key)?.label ?? key;

function Legend({ arms }: { arms: EvaluationArm[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {arms.map((arm, i) => (
        <li key={arm.arm} className="inline-flex items-center gap-1.5">
          <Swatch color={armColor(i)} />
          <span className="text-foreground">{arm.arm}</span>
          {arm.run_meta.model_graph ? <span>· {arm.run_meta.model_graph}</span> : <span>· no LLM</span>}
        </li>
      ))}
    </ul>
  );
}

function RunHeader({ data }: { data: EvaluationData }) {
  const facts: [string, string][] = [
    ["Set", data.set],
    ["Cases", String(data.cases)],
    ["Runs per case", String(data.runs_per_case)],
    ["Arms", data.arms.map((a) => a.arm).join(", ")],
    ["Protocol", data.protocol?.status ?? "UNSEALED"],
    ["Case file sha256", `${data.cases_sha256.slice(0, 12)}…`],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-lg border bg-card p-5 text-sm sm:grid-cols-3 lg:grid-cols-6">
      {facts.map(([name, value]) => (
        <div key={name} className="min-w-0">
          <dt className="text-xs text-muted-foreground">{name}</dt>
          <dd className="truncate font-medium tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Headline({ arm, index }: { arm: EvaluationArm; index: number }) {
  return (
    <section aria-label={`Arm ${arm.arm}`} className="rounded-lg border bg-card p-5">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Swatch color={armColor(index)} />
        {arm.arm}
        <span className="font-normal text-muted-foreground">{arm.run_meta.model_graph ?? "rules and templates, no LLM"}</span>
      </h3>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-5">
        {HEADLINE.map((key) => {
          const parts = rateParts(arm.overall[key]);
          return (
            <div key={key}>
              <dt className="text-xs text-muted-foreground">{label(key)}</dt>
              <dd className="text-2xl font-semibold tabular-nums tracking-tight">{parts.value}</dd>
              <dd className="text-xs tabular-nums text-muted-foreground">
                {parts.count}
                <br />
                95% CI {parts.interval}
              </dd>
            </div>
          );
        })}
        <div>
          <dt className="text-xs text-muted-foreground">Latency p95 per turn</dt>
          <dd className="text-2xl font-semibold tabular-nums tracking-tight">{milliseconds(arm.latency_ms.p95)}</dd>
          <dd className="text-xs tabular-nums text-muted-foreground">p50 {milliseconds(arm.latency_ms.p50)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Cost per case</dt>
          <dd className="text-2xl font-semibold tabular-nums tracking-tight">{dollars(arm.cost_usd.per_case)}</dd>
          <dd className="text-xs tabular-nums text-muted-foreground">per resolution {dollars(arm.cost_usd.per_resolution)}</dd>
        </div>
      </dl>
    </section>
  );
}

function Comparison({ arms }: { arms: EvaluationArm[] }) {
  const { bind, node } = useTip();
  return (
    <figure className={`rounded-lg border bg-card p-5 text-card-foreground ${PALETTE}`}>
      <h2 className="text-base font-semibold">The same cases on every arm</h2>
      <Explain detail="harness" className="mt-0.5">
        Each bar is a rate over the runs it applies to; the dot is the rate and the band is its 95% Wilson interval, on a scale of 0% to 100%. The arms
        run the same cases; arms whose bands overlap cannot be told apart.
      </Explain>
      <div className="mt-3">
        <Legend arms={arms} />
      </div>
      <div className="mt-5 space-y-5">
        {METRICS.map((metric) => (
          <div key={metric.key} className="grid gap-x-4 gap-y-1.5 sm:grid-cols-[14rem_1fr]">
            <p className="text-sm">
              {metric.label}
              <span className="block text-xs text-muted-foreground">{metric.good === "high" ? "higher is better" : "lower is better"}</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">{METRIC_MEANING[metric.key]}</span>
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
                        note="[simulated] scripted cases, final state compared"
                      />,
                    )}
                  >
                    <span className="w-8 shrink-0 text-xs text-muted-foreground">{arm.arm}</span>
                    <IntervalBar value={empty ? null : rate.value} low={rate.ci_low} high={rate.ci_high} color={armColor(i)} />
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
      <TableView
        head={["Metric", ...arms.map((a) => a.arm)]}
        rows={METRICS.map((m) => [m.label, ...arms.map((a) => rateText(a.overall[m.key]))])}
      />
      {node}
    </figure>
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
    <section className="rounded-lg border bg-card p-5">
      <h2 className="text-base font-semibold">By language, case type and segment</h2>
      <Explain detail="harness" className="mt-0.5">
        n is the number of cases in the cell. A cell marked small has fewer than 5 cases: read its interval, not its rate.
      </Explain>
      <div className="mt-4 overflow-x-auto">
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
    </section>
  );
}

export function EvaluationResults({ file }: { file: Insight<EvaluationData> }) {
  const data = file.data;
  const notice = developmentNotice(data);
  return (
    <div className={`space-y-4 ${PALETTE}`}>
      {notice ? (
        <p role="note" data-slot="development-notice" className="rounded-lg border border-border bg-muted px-4 py-3 text-sm font-medium text-foreground">
          {notice}
        </p>
      ) : null}
      <RunHeader data={data} />
      {data.arms.map((arm, i) => (
        <Headline key={arm.arm} arm={arm} index={i} />
      ))}
      <Comparison arms={data.arms} />
      <Breakdown arms={data.arms} />
      <p className="font-mono text-xs text-muted-foreground">
        {data.label} {file.source} · generated {file.generated_at.slice(0, 10)} at {file.git_sha}
      </p>
    </div>
  );
}
