// Offline checks for the display logic of /evaluation (spec 12). Run with `npm test`.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import { METRICS, RESULT_FILES, costQualityPoints, developmentNotice, interval, pending, protocolNotice, rateParts, rateText, scoreText } from "./evaluation.ts";
import type { BenchmarkData, ClassifierData, EvaluationData, FraudData, Insight, Rate } from "./evaluation.ts";

const SAMPLE = JSON.parse(
  readFileSync(new URL("../app/evaluation/__fixtures__/evaluation_summary.json", import.meta.url), "utf-8"),
) as Insight<EvaluationData>;

test("spec 12 AC-04: a missing result file gives a pending section that names the file and shows no figure", () => {
  const [summary, benchmark] = RESULT_FILES;
  assert.deepEqual(pending(summary, false), {
    title: "Agent evaluation: results pending",
    missing: "Missing evaluation_summary.json, written by the evaluation harness (spec 10).",
  });
  assert.equal(pending(summary, true), null);
  for (const file of RESULT_FILES) {
    const state = pending(file, false)!;
    assert.ok(state.missing.includes(file.file));
    assert.doesNotMatch(state.title + state.missing.replace(/spec \d+/, "").replace(file.file, ""), /\d/);
  }
  assert.equal(pending(benchmark, false)!.title, "Model benchmark: results pending");
});

test("spec 12 AC-04: no placeholder result file is committed; the sample lives only in the test fixtures", () => {
  for (const name of ["benchmark.json", "classifier.json", "fraud_benchmark.json"]) {
    assert.equal(existsSync(new URL(`../public/data/${name}`, import.meta.url)), false, name);
  }
  assert.match(SAMPLE.source, /SAMPLE FOR TESTS ONLY/);
});

test("spec 12 AC-05: only a sealed held-out run is shown without the development notice", () => {
  const sealed = { status: "SEALED", sha256: "a".repeat(64) };
  assert.equal(developmentNotice({ set: "heldout", protocol: sealed }), null);
  assert.equal(
    developmentNotice({ set: "dev", protocol: sealed }),
    'Development run, not the final result: it ran on the "dev" set, not the held-out.',
  );
  assert.match(developmentNotice({ set: "heldout", protocol: { status: "UNSEALED", sha256: null } })!, /protocol is UNSEALED/);
  assert.match(developmentNotice(SAMPLE.data)!, /"dev" set, not the held-out and the evaluation protocol is UNSEALED/);
});

test("spec 12 AC-05: a result file without a protocol is treated as unsealed and shows the notice, without crashing", () => {
  assert.match(developmentNotice({ set: "heldout" })!, /protocol is UNSEALED/);
  assert.match(developmentNotice({ set: "dev" })!, /"dev" set, not the held-out and the evaluation protocol is UNSEALED/);
  const withoutProtocol: Omit<EvaluationData, "protocol"> = { ...SAMPLE.data };
  delete (withoutProtocol as Partial<EvaluationData>).protocol;
  assert.ok(developmentNotice(withoutProtocol));
});

test("spec 12 AC-04: a breakdown cell without the optional small flag is not marked small", () => {
  const cell = SAMPLE.data.arms[0].cells[0];
  const rest: typeof cell = { ...cell };
  delete rest.small;
  assert.equal(rest.small, undefined);
  assert.ok(rateText(rest.metrics.safe_automated_resolution).length > 0);
});

test("spec 12 AC-06: every rate is shown with its numerator, its denominator and its interval", () => {
  const rate = SAMPLE.data.arms[0].overall.safe_automated_resolution;
  assert.deepEqual(rateParts(rate), { value: "75.0%", count: "9 of 12", interval: "46.8% to 91.1%" });
  assert.equal(rateText(rate), "75.0% (9 of 12; 95% CI 46.8% to 91.1%)");
  const none = { value: null, numerator: 0, denominator: 0, ci_low: null, ci_high: null };
  assert.equal(rateText(none), "— (no runs apply)");
  assert.equal(rateText(undefined), "— (no runs apply)");
  for (const arm of SAMPLE.data.arms) {
    for (const metric of METRICS) {
      assert.match(rateText(arm.overall[metric.key]), /^\d+\.\d% \(\d+ of \d+; 95% CI /, `${arm.arm} ${metric.key}`);
    }
  }
});

test("spec 12 AC-01: the page lists every metric the harness reports (spec 10 §4.1)", () => {
  assert.deepEqual(
    METRICS.map((m) => m.key).sort(),
    Object.keys(SAMPLE.data.arms[0].overall).sort(),
  );
});

// ---- benchmark, classifier and fraud sections (spec 12 §7.3 parts 5 to 7) ----
const fixture = <T>(name: string) =>
  JSON.parse(readFileSync(new URL(`../app/evaluation/__fixtures__/${name}`, import.meta.url), "utf-8")) as Insight<T>;
const BENCH = fixture<BenchmarkData>("benchmark.json");
const CLASSIFIER = fixture<ClassifierData>("classifier.json");
const FRAUD = fixture<FraudData>("fraud_benchmark.json");
const RATE_KEYS = ["value", "numerator", "denominator", "ci_low", "ci_high"];

function rates(node: unknown, found: Record<string, unknown>[] = []): Record<string, unknown>[] {
  if (Array.isArray(node)) node.forEach((n) => rates(n, found));
  else if (node && typeof node === "object") {
    if ("numerator" in node) found.push(node as Record<string, unknown>);
    else Object.values(node).forEach((n) => rates(n, found));
  }
  return found;
}

test("spec 12 AC-04: the three later sections are pending with their file named, and the samples are test fixtures only", () => {
  const [, benchmark, classifier, fraud] = RESULT_FILES;
  for (const [file, name] of [[benchmark, "benchmark.json"], [classifier, "classifier.json"], [fraud, "fraud_benchmark.json"]] as const) {
    const state = pending(file, false)!;
    assert.match(state.title, /results pending$/);
    assert.ok(state.missing.includes(name));
    assert.equal(pending(file, true), null);
  }
  for (const f of [BENCH, CLASSIFIER, FRAUD]) assert.match(f.source, /SAMPLE FOR TESTS ONLY/);
});

test("spec 12 AC-05: a result file whose protocol is not SEALED shows the development notice, a sealed one does not", () => {
  for (const f of [BENCH, CLASSIFIER, FRAUD]) {
    assert.match(protocolNotice(f.data.protocol)!, /^Development run, not the final result: the evaluation protocol is UNSEALED\.$/);
  }
  assert.equal(protocolNotice({ status: "SEALED", sha256: "a".repeat(64) }), null);
  assert.ok(protocolNotice(undefined));
});

test("spec 12 AC-01: the sample files have the shapes of specs 15, 11 and 17 §7.1", () => {
  assert.deepEqual(Object.keys(BENCH.data).sort(), ["b1", "b2", "demo_today", "judge", "label", "mode", "model_map", "protocol", "run_date", "word"]);
  assert.equal(BENCH.data.label, "[simulated]");
  assert.deepEqual(Object.keys(CLASSIFIER.data).sort(), ["arms", "chosen_arm", "injection", "label", "protocol", "tau", "test_split"]);
  assert.deepEqual(Object.keys(CLASSIFIER.data.arms[0].by_language.es).sort(), [
    "coverage_at_tau", "dispute_detected_recall", "dispute_recall", "ece", "human_request_recall", "macro_f1", "macro_f1_ci", "per_class_f1", "precision_at_tau", "slot_accuracy",
  ]);
  assert.deepEqual(Object.keys(FRAUD.data).sort(), ["arms", "chosen_arm", "label", "machine", "protocol", "windows"]);
  assert.equal(FRAUD.data.label, "[data]");
  assert.ok(FRAUD.data.arms.some((a) => a.arm === "S-bank"));
  assert.deepEqual(Object.keys(FRAUD.data.arms[0].subsets).sort(), ["all", "card"]);
});

test("spec 12 AC-06: every rate in the three sample files has its parts and renders with count and interval", () => {
  const all = [...rates(BENCH.data), ...rates(CLASSIFIER.data), ...rates(FRAUD.data)];
  assert.ok(all.length > 30);
  for (const r of all) {
    assert.deepEqual(Object.keys(r).sort(), [...RATE_KEYS].sort());
    const text = rateText(r as Rate);
    assert.match(text, r.denominator === 0 ? /^— \(no runs apply\)$/ : /^\d+\.\d% \(\d+ of \d+; 95% CI \d+\.\d% to \d+\.\d%\)$/);
  }
  assert.equal(scoreText(0.812, [0.771, 0.85]), "0.812 (95% CI 0.771 to 0.850)");
  assert.equal(scoreText(null, [null, null]), "—");
  assert.equal(interval([null, null]), "—");
});

test("spec 12 AC-07: the cost-quality chart keeps only arms with a cost and a score, and marks the chosen one", () => {
  const points = costQualityPoints(BENCH.data, "es");
  assert.deepEqual(points.map((p) => p.arm), ["Haiku 4.5", "Sonnet 4.6", "Sample C"]);
  assert.deepEqual(points.filter((p) => p.chosen).map((p) => p.arm), ["Haiku 4.5"]);
  assert.deepEqual(points.filter((p) => p.pareto).map((p) => p.arm), ["Haiku 4.5", "Sonnet 4.6"]);
  assert.equal(costQualityPoints(BENCH.data, "pt")[0].quality, 0.83);
});
