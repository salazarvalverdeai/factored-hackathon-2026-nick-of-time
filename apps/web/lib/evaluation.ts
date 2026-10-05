// Display logic of /evaluation (spec 12). The page computes no metric: it shows what the harness wrote in
// evaluation_summary.json (spec 10 §7.2). Everything here is pure, so `npm test` covers it.

export type Rate = {
  value: number | null;
  numerator: number;
  denominator: number;
  ci_low: number | null;
  ci_high: number | null;
};

export type EvaluationArm = {
  arm: string;
  run_meta: { git_sha?: string; model_graph?: string | null; prompt_hash?: string | null; policies_version?: number };
  overall: Record<string, Rate>;
  cells: { language: string; type: string; segment: string; n_cases: number; small?: boolean; metrics: Record<string, Rate> }[];
  latency_ms: { p50: number | null; p95: number | null };
  cost_usd: { per_case: number | null; per_resolution: number | null };
  blocks_vs_label: { blocked: number; blocked_fraud: number; fraud_cases: number; precision: number | null; recall: number | null } | null;
};

export type EvaluationData = {
  label: string;
  set: string;
  cases: number;
  runs_per_case: number;
  cases_sha256: string;
  protocol?: { status: string; sha256: string | null };
  arms: EvaluationArm[];
};

export type Insight<T> = { generated_at: string; git_sha: string; source: string; data: T };

/** The result files of spec 12 §7.1 that /evaluation reads, in page order. */
export const RESULT_FILES = [
  { file: "evaluation_summary.json", title: "Agent evaluation", producedBy: "the evaluation harness (spec 10)" },
  { file: "benchmark.json", title: "Model benchmark", producedBy: "the model benchmark (spec 15)" },
  { file: "classifier.json", title: "Intent classifier", producedBy: "the intent classifier (spec 11)" },
  { file: "fraud_benchmark.json", title: "Fraud model against the bank's score", producedBy: "the fraud model (spec 17)" },
] as const;

/** The metrics of spec 10 §4.1 in display order; `good` says which direction is better. */
export const METRICS: { key: string; label: string; good: "high" | "low" }[] = [
  { key: "safe_automated_resolution", label: "Safe automated resolution", good: "high" },
  { key: "unsafe_outcomes", label: "Unsafe outcomes", good: "low" },
  { key: "pass_4", label: "Cases passing all runs (pass^4)", good: "high" },
  { key: "receipt_rate", label: "Receipt with its deadline", good: "high" },
  { key: "complete_intake_rate", label: "Complete intake", good: "high" },
  { key: "missed_escalations", label: "Missed escalations", good: "low" },
  { key: "unnecessary_escalations", label: "Unnecessary escalations", good: "low" },
  { key: "coherence_rate", label: "Status told = status read", good: "high" },
  { key: "intent_accuracy", label: "Intent accuracy", good: "high" },
];

export type Pending = { title: string; missing: string };

/** spec 12 AC-04: a section whose result file does not exist shows what is missing, and no figure. */
export function pending(file: (typeof RESULT_FILES)[number], exists: boolean): Pending | null {
  return exists ? null : { title: `${file.title}: results pending`, missing: `Missing ${file.file}, written by ${file.producedBy}.` };
}

/** spec 12 AC-05: anything but the sealed held-out is a development run and says so above the figures. */
export function developmentNotice(data: Pick<EvaluationData, "set" | "protocol">): string | null {
  const reasons = [
    data.set !== "heldout" ? `it ran on the "${data.set}" set, not the held-out` : null,
    data.protocol?.status !== "SEALED" ? `the evaluation protocol is ${data.protocol?.status ?? "UNSEALED"}` : null,
  ].filter(Boolean);
  return reasons.length ? `Development run, not the final result: ${reasons.join(" and ")}.` : null;
}

const percent = (value: number) => `${(value * 100).toFixed(1)}%`;

/** spec 12 AC-06: a rate is never shown without its numerator, its denominator and its interval. */
export function rateParts(rate: Rate | undefined): { value: string; count: string; interval: string } {
  if (!rate || rate.denominator === 0 || rate.value === null) {
    return { value: "—", count: "no runs apply", interval: "—" };
  }
  const interval = rate.ci_low === null || rate.ci_high === null ? "—" : `${percent(rate.ci_low)} to ${percent(rate.ci_high)}`;
  return { value: percent(rate.value), count: `${rate.numerator} of ${rate.denominator}`, interval };
}

export function rateText(rate: Rate | undefined): string {
  const parts = rateParts(rate);
  return parts.value === "—" ? "— (no runs apply)" : `${parts.value} (${parts.count}; 95% CI ${parts.interval})`;
}

export const milliseconds = (value: number | null) => (value === null ? "—" : `${Math.round(value).toLocaleString("en-US")} ms`);
export const dollars = (value: number | null) => (value === null ? "—" : `$${value.toFixed(4)}`);
