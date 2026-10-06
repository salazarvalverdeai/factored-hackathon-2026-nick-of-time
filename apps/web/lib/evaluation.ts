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
  scoring?: { official: string; secondary: string };
  scores_d070?: ScoresD070;
};

export type ScoresD070 = {
  label: string;
  scoring: string;
  official_scoring: string;
  rule: string;
  adr: string;
  arms: Record<string, { official: Record<string, Rate>; secondary: Record<string, Rate> }>;
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
export function developmentReasons(data: Pick<EvaluationData, "set" | "protocol">): string[] {
  return [
    data.set !== "heldout" ? `it ran on the "${data.set}" set, not the held-out` : null,
    data.protocol?.status !== "SEALED" ? `the evaluation protocol is ${data.protocol?.status ?? "UNSEALED"}` : null,
  ].filter((r): r is string => r !== null);
}

export function developmentNotice(data: Pick<EvaluationData, "set" | "protocol">): string | null {
  const reasons = developmentReasons(data);
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
  macro_f1: Record<string, number | null> | null;
  macro_f1_ci: Record<string, Interval> | null;
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
/** One line on the sealed test run: its label (ADR 0028) and, when no arm clears the floors, that the chosen arm is kept. */
export function classifierRunNote(d: Pick<ClassifierData, "run" | "test_review" | "chosen_arm" | "arms" | "protocol">): string | null {
  if (d.run !== "test") return null;
  const parts = [d.protocol?.status === "SEALED" ? "Sealed test result" : "Test result"];
  if (d.test_review === "rules-v1") parts.push("test split decided by fixed rules (rules-v1), not by a person");
  if (d.chosen_arm && d.arms.length > 0 && d.arms.every((a) => a.meets_floors === false)) parts.push(`no arm meets the floors; ${d.chosen_arm} kept`);
  return parts.join(" · ") + ".";
}
/** A sealed result of the benchmark (B1, test split) or the fraud model (test window): same note as the classifier's. */
export function sealedRunNote(d: { protocol?: { status?: string; test_review?: string }; split?: string; scored_window?: string }): string | null {
  if (d.split !== "test" && d.scored_window !== "test") return null;
  const parts = [d.protocol?.status === "SEALED" ? "Sealed test result" : "Test result"];
  if (d.protocol?.test_review === "rules-v1") parts.push("test split decided by fixed rules (rules-v1), not by a person");
  return parts.join(" · ") + ".";
}
export type ClassifierData = {
  label: string;
  protocol: Protocol;
  /** ADR 0028: `rules-v1` when the test split was decided by fixed rules, `human` when a person reviewed it. */
  test_review?: string | null;
  /** `test` for the one-time sealed run on the test split. */
  run?: string | null;
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
    const quality = a.macro_f1?.[language];
    if (a.status !== "ok" || a.cost_per_1000_usd === null || quality === null || quality === undefined) return [];
    return [{ arm: a.arm, cost: a.cost_per_1000_usd, quality, ci: a.macro_f1_ci?.[language] ?? [null, null], pareto: a.pareto === true, chosen: a.arm === chosen, row: a }];
  });
}

/** ADR 0025: an arm of the family that wrote the test split is flagged wherever its result is shown. */
export const GENERATOR_FLAG = "same family as the test-split generator (ADR 0025)";
export function generatorFlag(arm: { same_family_as_generator?: boolean | null }): string | null {
  return arm.same_family_as_generator === true ? GENERATOR_FLAG : null;
}

// ---- Plain explanations, "Detail" links and limitations (spec 12 AC-11) ----

export const REPO_BLOB = "https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/blob/main/";

/** GitHub's heading anchor: lower case, punctuation removed, spaces to hyphens. */
export const headingSlug = (heading: string) =>
  heading.toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, "").trim().replace(/\s/g, "-");

/**
 * The markdown that defines each chart; `heading` is the section heading the link lands on. The rest is what the
 * side panel of "Detail →" shows: what the figure means, how it is computed, the file it comes from and its label.
 */
export const DETAILS = {
  harness: {
    path: "specs/10-eval-harness.md", heading: "4.1 Metric definitions",
    title: "Agent evaluation: the rates",
    meaning: "Each rate says how often the agent did the right thing on the evaluation cases. The band around it is the range the true rate probably sits in, so wide bands mean few cases.",
    method: "Each rate is runs that pass over the runs it applies to (for example, safe automated resolution is runs that pass with no unsafe outcome over the cases that expect a block). The interval is the 95% Wilson interval.",
    source: "evaluation_summary.json, written by eval/harness.py",
    label: "[simulated]",
  },
  classifier: {
    path: "specs/11-intent-classifier.md", heading: "4.1 Thresholds and test size (checked 2026-10-04)",
    title: "Intent classifier: macro-F1",
    meaning: "How well each arm tells what the customer wants, per language. 0 is always wrong and 1 is always right. With a small test split the band is wide, so close arms cannot be told apart.",
    method: "Macro-F1 is the average of the F1 of each intent (equal weight), over the frozen test split. The interval is the 95% bootstrap interval, resampling the test sentences.",
    source: "classifier.json, written by the intent classifier evaluation",
    label: "[simulated]",
  },
  benchmark: {
    path: "specs/15-model-benchmark.md", heading: "4.4 Lean rule (pre-registered per task; thresholds from spec 11 §4.1)",
    title: "Model benchmark: cost against quality",
    meaning: "Which model gives enough quality for the least money. Dots on the Pareto front are not beaten by any model that is both cheaper and better; the ringed one is the model the rule chose.",
    method: "Quality is macro-F1 on the classifier test sentences; cost is USD per 1,000 messages from the list price and the tokens used. The lean rule keeps the arms not significantly worse than the best (paired McNemar, p at least 0.05) and picks the cheapest of them.",
    source: "benchmark.json, written by the model benchmark",
    label: "[simulated] · prices [external]",
  },
  fraud: {
    path: "specs/17-fraud-model.md", heading: "4.4 Decision rule (pre-registered, lean)",
    title: "Fraud model against the bank's score",
    meaning: "Whether a model of ours ranks fraud better than the bank's own score. Higher PR-AUC means more of the top-ranked transactions are fraud.",
    method: "PR-AUC is the area under the precision-recall curve on the test window, with the 95% bootstrap interval. An arm beats the bank's score when its PR-AUC is higher and the interval of the difference stays above zero, or when it catches enough frauds that have no bank score.",
    source: "fraud_benchmark.json, written by the fraud model benchmark",
    label: "[data]",
  },
  protocol: {
    path: "eval/PROTOCOL.md", heading: null,
    title: "Evaluation protocol",
    meaning: "The rules fixed before the held-out run: what is measured and what counts as a pass.",
    method: "The protocol is sealed with a hash before the held-out run; a run on anything else is a development run and says so.",
    source: "eval/PROTOCOL.md",
    label: "[simulated]",
  },
} as const;

export function detailUrl(key: keyof typeof DETAILS): string {
  const d = DETAILS[key];
  return `${REPO_BLOB}${d.path}${d.heading ? `#${headingSlug(d.heading)}` : ""}`;
}

/** What a harness metric means, in one plain sentence (spec 10 §4.1). */
export const METRIC_MEANING: Record<string, string> = {
  safe_automated_resolution: "Share of cases where the card was blocked and the case opened with no person, and nothing unsafe happened.",
  unsafe_outcomes: "Share of runs with any unsafe outcome: another customer's data shown, a wrong block, or a case opened that should have been refused.",
  pass_4: "Share of cases that pass on all four runs, so one lucky run does not count.",
  receipt_rate: "Share of expected receipts that were issued with the legal deadline on them.",
  complete_intake_rate: "Share of cases opened on the right transaction and queue, with a receipt and deadline.",
  missed_escalations: "Share of cases that needed a handoff to an analyst and did not get one.",
  unnecessary_escalations: "Share of cases that got a handoff although none was needed.",
  coherence_rate: "Share of status answers that say what the system reads back as the real status.",
  intent_accuracy: "Share of runs where the system understood what the customer asked for.",
};

export type ResultFiles = {
  summary: Insight<EvaluationData> | null;
  benchmark: Insight<BenchmarkData> | null;
  classifier: Insight<ClassifierData> | null;
  fraud: Insight<FraudData> | null;
};

/** The sentence ADR 0028 requires next to every classifier test result. */
export const RULES_REVIEW_SENTENCE =
  "The classifier test split was decided by fixed rules, without independent human review (ADR 0028); train and validation were reviewed by the lead.";

/**
 * spec 12 AC-11: plain sentences, only for the files that exist. With no result file there is nothing to limit,
 * so the list is empty.
 */
export function limitations(files: ResultFiles): string[] {
  const out: string[] = [];
  const { summary, benchmark, classifier, fraud } = files;
  if (summary) {
    const d = summary.data;
    out.push(`Only ${d.cases} cases were scored (${d.runs_per_case} runs each), so the intervals are wide: read the interval, not the single rate.`);
  }
  if (classifier) {
    const n = Object.values(classifier.data.test_split.sentences).reduce<number>((a, b) => a + (b ?? 0), 0);
    out.push(`The classifier test split has ${n > 0 ? `${n} sentences` : "few sentences"}, so its intervals are wide too.`);
  }
  if (summary) out.push("The customer messages of the agent cases were written by the team with AI assistance, on real dataset state, so real customers may phrase things differently.");
  if (classifier) out.push("The classifier sentences were written by language models, one model family per split (ADR 0025), so real customers may phrase things differently.");
  if (benchmark) out.push("The benchmark scores the models on the classifier sentences (written by language models) and on the agent development cases (written by the team with AI assistance).");
  if (classifier?.data.test_review === "rules-v1") out.push(RULES_REVIEW_SENTENCE);
  if (summary) out.push("The held-out set is run once, after the protocol is sealed; there is no second run to tune on.");
  if (summary || benchmark || classifier || fraud) {
    out.push("The customers and transactions come from a synthetic dataset and the runs are simulated, so the results show how the system behaves, not how it would perform at a real bank.");
  }
  return out;
}

/** The chip each section of a development run carries beside its title (AC-05). */
export const DEVELOPMENT_CHIP = "development run";

/** spec 12 AC-05: the result files that are not the sealed held-out, each with its reasons, in page order. */
export function developmentRuns(files: ResultFiles): { file: string; reasons: string[] }[] {
  const [summary, benchmark, classifier, fraud] = RESULT_FILES.map((f) => f.file);
  const found: [string, string[]][] = [
    [summary, files.summary ? developmentReasons(files.summary.data) : []],
    ...([[benchmark, files.benchmark], [classifier, files.classifier], [fraud, files.fraud]] as const).map(
      ([file, f]): [string, string[]] => [file, f ? developmentReasons({ set: "heldout", protocol: f.data.protocol as EvaluationData["protocol"] }) : []],
    ),
  ];
  return found.filter(([, reasons]) => reasons.length).map(([file, reasons]) => ({ file, reasons }));
}

/** spec 12 AC-05: one notice at the top of the page that names every development-run file, or null. */
export function pageNotice(files: ResultFiles): string | null {
  const runs = developmentRuns(files);
  return runs.length
    ? `Development run, not the final result: ${runs.map((r) => `${r.file} (${r.reasons.join(" and ")})`).join("; ")}. The sections marked "${DEVELOPMENT_CHIP}" come from these files.`
    : null;
}

// ---- Held-out scored twice (ADR 0031, spec 10 AC-15, spec 12). Official sealed rules first; D-070 is secondary. ----
export const D070_SENTENCE = "The sealed expectations predate D-070, so verified blocks that also send the analyst handoff card count as misses in the official score.";
export const D070_METRICS = ["unsafe_outcomes", "safe_automated_resolution", "pass_4", "handoff_agreement", "missed_escalations", "unnecessary_escalations"] as const;
/** S1 is Haiku 4.5, an assumption: the harness file names no model for it. */
export const ARM_MODEL_NOTE: Record<string, string> = { S0: "rules, no LLM", S1: "Haiku 4.5 [assumption]", S2: "Sonnet 4.6" };

export type D070Row = { arm: string; model: string; official: Rate; secondary: Rate };
export type D070View = {
  officialLabel: string;
  secondaryLabel: string;
  sentence: string;
  tag: string;
  metrics: { key: string; label: string; rows: D070Row[] }[];
};

/** Absent block (development runs) gives null and the page renders as before. */
export function d070View(data: Pick<EvaluationData, "scores_d070" | "arms">): D070View | null {
  const b = data.scores_d070;
  if (!b?.arms) return null;
  const arms = Object.keys(b.arms);
  const label = (k: string) => METRICS.find((m) => m.key === k)?.label ?? (k === "handoff_agreement" ? "Handoff agreement" : k);
  return {
    officialLabel: "Official: sealed rules (protocol-v1)",
    secondaryLabel: "Secondary: D-070 handoff rule (ADR 0031, decided before the run)",
    sentence: D070_SENTENCE,
    tag: b.label ?? "[simulated]",
    metrics: D070_METRICS.map((key) => ({
      key,
      label: label(key),
      rows: arms.map((arm) => ({
        arm,
        model: ARM_MODEL_NOTE[arm] ?? data.arms.find((a) => a.arm === arm)?.run_meta.model_graph ?? "",
        official: b.arms[arm].official[key],
        secondary: b.arms[arm].secondary[key],
      })),
    })),
  };
}
