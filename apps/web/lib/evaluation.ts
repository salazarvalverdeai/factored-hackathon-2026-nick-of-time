// Display logic of /evaluation (spec 12). The page computes no metric: it shows what the harness wrote in
// evaluation_summary.json (spec 10 §7.2). Everything here is pure, so `npm test` covers it. Display strings follow the
// UI language through an optional `locale` (default English, the source of messages/evaluation.ts; spec 16 AC-06);
// numbers follow its locale, while counts, figure labels and sources stay as the result files wrote them.
import { evaluation as messages } from "../messages/evaluation.ts";
import { formatNumber, type Locale, translator } from "./i18n.ts";

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
  { key: "summary", file: "evaluation_summary.json", title: messages.en.files.summary.title, producedBy: messages.en.files.summary.producedBy },
  { key: "benchmark", file: "benchmark.json", title: messages.en.files.benchmark.title, producedBy: messages.en.files.benchmark.producedBy },
  { key: "classifier", file: "classifier.json", title: messages.en.files.classifier.title, producedBy: messages.en.files.classifier.producedBy },
  { key: "fraud", file: "fraud_benchmark.json", title: messages.en.files.fraud.title, producedBy: messages.en.files.fraud.producedBy },
] as const;

type MetricKey = keyof (typeof messages)["en"]["metrics"]["label"];
const GOOD: Record<MetricKey, "high" | "low"> = {
  safe_automated_resolution: "high",
  unsafe_outcomes: "low",
  pass_4: "high",
  receipt_rate: "high",
  complete_intake_rate: "high",
  missed_escalations: "low",
  unnecessary_escalations: "low",
  coherence_rate: "high",
  intent_accuracy: "high",
};

/** The metrics of spec 10 §4.1 in display order, with labels in the UI language; `good` says which direction is better. */
export function metrics(locale: Locale = "en"): { key: string; label: string; good: "high" | "low" }[] {
  const labels = messages[locale].metrics.label;
  return (Object.keys(GOOD) as MetricKey[]).map((key) => ({ key, label: labels[key], good: GOOD[key] }));
}
export const METRICS = metrics("en");

export type Pending = { title: string; missing: string };

/** spec 12 AC-04: a section whose result file does not exist shows what is missing, and no figure. */
export function pending(file: (typeof RESULT_FILES)[number], exists: boolean, locale: Locale = "en"): Pending | null {
  if (exists) return null;
  const t = translator(locale);
  return {
    title: t("evaluation.pending.title", { title: t(`evaluation.files.${file.key}.title` as const) }),
    missing: t("evaluation.pending.missing", { file: file.file, producedBy: t(`evaluation.files.${file.key}.producedBy` as const) }),
  };
}

/** spec 12 AC-05: anything but the sealed held-out is a development run and says so above the figures. */
export function developmentNotice(data: Pick<EvaluationData, "set" | "protocol">, locale: Locale = "en"): string | null {
  const t = translator(locale);
  const reasons = [
    data.set !== "heldout" ? t("evaluation.notice.set", { set: data.set }) : null,
    data.protocol?.status !== "SEALED" ? t("evaluation.notice.protocol", { status: data.protocol?.status ?? "UNSEALED" }) : null,
  ].filter(Boolean);
  return reasons.length ? t("evaluation.notice.dev", { reasons: reasons.join(t("evaluation.notice.and")) }) : null;
}

const decimals = (locale: Locale, value: number, digits: number) =>
  formatNumber(locale, value, { minimumFractionDigits: digits, maximumFractionDigits: digits });
const percent = (value: number, locale: Locale) => `${decimals(locale, value * 100, 1)}%`;

/** spec 12 AC-06: a rate is never shown without its numerator, its denominator and its interval. */
export function rateParts(rate: Rate | undefined, locale: Locale = "en"): { value: string; count: string; interval: string } {
  const t = translator(locale);
  if (!rate || rate.denominator === 0 || rate.value === null) {
    return { value: "—", count: t("evaluation.rate.none"), interval: "—" };
  }
  const interval =
    rate.ci_low === null || rate.ci_high === null
      ? "—"
      : t("evaluation.rate.interval", { low: percent(rate.ci_low, locale), high: percent(rate.ci_high, locale) });
  return { value: percent(rate.value, locale), count: t("evaluation.rate.count", { n: rate.numerator, d: rate.denominator }), interval };
}

export function rateText(rate: Rate | undefined, locale: Locale = "en"): string {
  const t = translator(locale);
  const parts = rateParts(rate, locale);
  return parts.value === "—" ? t("evaluation.rate.textNone") : t("evaluation.rate.text", parts);
}

export const milliseconds = (value: number | null, locale: Locale = "en") =>
  value === null ? "—" : `${formatNumber(locale, Math.round(value))} ms`;
export const dollars = (value: number | null, locale: Locale = "en") => (value === null ? "—" : `$${decimals(locale, value, 4)}`);

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
  /** ADR 0028: `rules-v1` when the test split was decided by fixed rules, `human` when a person reviewed it. */
  test_review?: string | null;
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
export const protocolNotice = (protocol: Protocol | undefined, locale: Locale = "en"): string | null =>
  developmentNotice({ set: "heldout", protocol: protocol as EvaluationData["protocol"] }, locale);

const fixed = (value: number | null | undefined, locale: Locale) => (value === null || value === undefined ? "—" : decimals(locale, value, 3));
export const score = (value: number | null | undefined, locale: Locale = "en") => fixed(value, locale);
export const interval = (ci: Interval | undefined, locale: Locale = "en") =>
  !ci || ci[0] === null || ci[1] === null ? "—" : translator(locale)("evaluation.rate.interval", { low: fixed(ci[0], locale), high: fixed(ci[1], locale) });
/** A score with its 95% interval, e.g. "0.812 (95% CI 0.771 to 0.850)". */
export const scoreText = (value: number | null | undefined, ci: Interval | undefined, locale: Locale = "en") =>
  value === null || value === undefined ? "—" : translator(locale)("evaluation.rate.score", { value: fixed(value, locale), interval: interval(ci, locale) });

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
export const GENERATOR_FLAG = messages.en.generatorFlag;
export function generatorFlag(arm: { same_family_as_generator?: boolean | null }, locale: Locale = "en"): string | null {
  return arm.same_family_as_generator === true ? messages[locale].generatorFlag : null;
}

// ---- Plain explanations, "Detail" links and limitations (spec 12 AC-11) ----

export const REPO_BLOB = "https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/blob/main/";

/** GitHub's heading anchor: lower case, punctuation removed, spaces to hyphens. */
export const headingSlug = (heading: string) =>
  heading.toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, "").trim().replace(/\s/g, "-");

/** The markdown that defines each chart; `heading` is the section heading the link lands on. */
export const DETAILS = {
  harness: { path: "specs/10-eval-harness.md", heading: "4.1 Metric definitions" },
  classifier: { path: "specs/11-intent-classifier.md", heading: "4.1 Thresholds and test size (checked 2026-10-04)" },
  benchmark: { path: "specs/15-model-benchmark.md", heading: "4.4 Lean rule (pre-registered per task; thresholds from spec 11 §4.1)" },
  fraud: { path: "specs/17-fraud-model.md", heading: "4.4 Decision rule (pre-registered, lean)" },
  protocol: { path: "eval/PROTOCOL.md", heading: null },
} as const;

export function detailUrl(key: keyof typeof DETAILS): string {
  const d = DETAILS[key];
  return `${REPO_BLOB}${d.path}${d.heading ? `#${headingSlug(d.heading)}` : ""}`;
}

/** What a harness metric means, in one plain sentence (spec 10 §4.1), in the UI language. */
export function metricMeaning(locale: Locale = "en"): Record<string, string> {
  return messages[locale].metrics.meaning;
}
export const METRIC_MEANING: Record<string, string> = metricMeaning("en");

export type ResultFiles = {
  summary: Insight<EvaluationData> | null;
  benchmark: Insight<BenchmarkData> | null;
  classifier: Insight<ClassifierData> | null;
  fraud: Insight<FraudData> | null;
};

/** The sentence ADR 0028 requires next to every classifier test result. */
export const RULES_REVIEW_SENTENCE = messages.en.rulesReview;

/**
 * spec 12 AC-11: plain sentences, only for the files that exist. With no result file there is nothing to limit,
 * so the list is empty.
 */
export function limitations(files: ResultFiles, locale: Locale = "en"): string[] {
  const t = translator(locale);
  const out: string[] = [];
  const { summary, benchmark, classifier, fraud } = files;
  if (summary) {
    const d = summary.data;
    out.push(t("evaluation.limits.cases", { cases: d.cases, runs: d.runs_per_case }));
  }
  if (classifier) {
    const n = Object.values(classifier.data.test_split.sentences).reduce<number>((a, b) => a + (b ?? 0), 0);
    out.push(t("evaluation.limits.split", { sentences: n > 0 ? t("evaluation.limits.sentences", { n }) : t("evaluation.limits.fewSentences") }));
  }
  if (summary) out.push(t("evaluation.limits.agentMessages"));
  if (classifier) out.push(t("evaluation.limits.classifierSentences"));
  if (benchmark) out.push(t("evaluation.limits.benchmark"));
  if (classifier?.data.test_review === "rules-v1") out.push(messages[locale].rulesReview);
  if (summary) out.push(t("evaluation.limits.heldout"));
  if (summary || benchmark || classifier || fraud) out.push(t("evaluation.limits.synthetic"));
  return out;
}

