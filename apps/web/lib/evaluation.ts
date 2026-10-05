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

// ---- The three later result files (spec 12 §7.3 parts 5 to 7). Shapes: spec 15 §7.1, spec 11 §7.1, spec 17 §7.1. ----
// `null` marks a figure the run has not filled in; a rate with no runs shows "—" through rateParts.

export type Protocol = { status: string; sha256: string | null; [hash: string]: string | null };
export type Interval = [number | null, number | null];

export type BenchmarkArm = {
  arm: string;
  model_id: string;
  status: string;
  unavailable_reason: string | null;
  price: { label: string; input_per_1m_usd: number | null; output_per_1m_usd: number | null; source: string; date: string };
  macro_f1: Record<string, number | null>;
  macro_f1_ci: Record<string, Interval>;
  dispute_recall: Rate;
  human_request_recall: Rate;
  slot_accuracy: Rate;
  missing_tool_calls: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  cost_per_1000_usd: number | null;
  meets_bar: boolean | null;
  pareto: boolean | null;
  same_family_as_generator?: boolean | null;
  gate: { benchmark_pass: boolean | null; production_pass: boolean | null };
};
export type BenchmarkData = {
  label: string;
  protocol: Protocol;
  mode: string;
  demo_today: string;
  run_date: string;
  b1: { arms: BenchmarkArm[] };
  b2: { set: string; cases: number; runs_per_case: number; arms: ({ arm: string; cost_per_case_usd: number | null } & Record<string, Rate | string | number | null>)[] };
  model_map: Record<string, { best_measured?: string; cheapest_meeting_bar?: string; chosen?: string }>;
};

export type ClassifierLanguage = {
  macro_f1: number | null;
  macro_f1_ci: Interval;
  per_class_f1: Record<string, number | null>;
  dispute_recall: Rate;
  dispute_detected_recall: Rate;
  human_request_recall: Rate;
  slot_accuracy: Rate;
  ece: number | null;
  coverage_at_tau: Rate;
  precision_at_tau: Rate;
};
export type ClassifierArm = {
  arm: string;
  version: string;
  p95_ms: number | null;
  cost_per_1000_usd: number | null;
  meets_floors: boolean | null;
  mcnemar_p_vs_best: number | null;
  human_request_answered_out_of_scope: number | null;
  same_family_as_generator?: boolean | null;
  by_language: Record<string, ClassifierLanguage>;
};
export type ClassifierData = {
  label: string;
  protocol: Protocol;
  test_split: { sentences: Record<string, number | null>; injection_rows: number | null };
  tau: number | null;
  chosen_arm: string | null;
  arms: ClassifierArm[];
  injection: { arm: string; recall: Rate; false_positive_rate: Rate }[];
};

export type FraudSubset = {
  pr_auc: number | null;
  pr_auc_ci: Interval;
  brier: number | null;
  recall_at_bank_precision: Record<string, Rate>;
  recall_no_score_at_1pct: Rate;
};
export type FraudArm = {
  arm: string;
  family: string;
  passes_rule: boolean | null;
  cost: { train_seconds: number | null; score_p95_ms: number | null; throughput_per_s: number | null; model_mb: number | null };
  subsets: Record<string, Partial<FraudSubset>>;
};
export type FraudData = {
  label: string;
  protocol: Protocol;
  windows: { test: { from: string; to: string; transactions: number | null; frauds: number | null } };
  chosen_arm: string | null;
  arms: FraudArm[];
};

/** spec 12 AC-05 for the files without a set: only the protocol status says whether the run is final. */
export const protocolNotice = (protocol: Protocol | undefined): string | null =>
  developmentNotice({ set: "heldout", protocol: protocol as EvaluationData["protocol"] });

const fixed = (value: number | null | undefined, digits = 3) => (value === null || value === undefined ? "—" : value.toFixed(digits));
export const score = (value: number | null | undefined) => fixed(value);
export const interval = (ci: Interval | undefined) => (!ci || ci[0] === null || ci[1] === null ? "—" : `${fixed(ci[0])} to ${fixed(ci[1])}`);
/** A score with its 95% interval, e.g. "0.812 (95% CI 0.771 to 0.850)". */
export const scoreText = (value: number | null | undefined, ci: Interval | undefined) =>
  value === null || value === undefined ? "—" : `${fixed(value)} (95% CI ${interval(ci)})`;

export type CostQualityPoint = { arm: string; cost: number; quality: number; ci: Interval; pareto: boolean; chosen: boolean; row: BenchmarkArm };

/** spec 12 §7.3 part 5: the arms that have both a cost and a score in `language`; the others stay in the table only. */
export function costQualityPoints(data: BenchmarkData, language: string): CostQualityPoint[] {
  const chosen = data.model_map.understand?.chosen;
  return data.b1.arms.flatMap((a) => {
    const quality = a.macro_f1[language];
    if (a.status !== "ok" || a.cost_per_1000_usd === null || quality === null || quality === undefined) return [];
    return [{ arm: a.arm, cost: a.cost_per_1000_usd, quality, ci: a.macro_f1_ci[language], pareto: a.pareto === true, chosen: a.arm === chosen, row: a }];
  });
}

/** ADR 0025: an arm of the family that wrote the test split is flagged wherever its result is shown. */
export const GENERATOR_FLAG = "same family as the test-split generator (ADR 0025)";
export function generatorFlag(arm: { same_family_as_generator?: boolean | null }): string | null {
  return arm.same_family_as_generator === true ? GENERATOR_FLAG : null;
}
