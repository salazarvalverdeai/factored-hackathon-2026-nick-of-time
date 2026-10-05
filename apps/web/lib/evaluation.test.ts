// Offline checks for the display logic of /evaluation (spec 12). Run with `npm test`.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import { METRICS, RESULT_FILES, developmentNotice, pending, rateParts, rateText } from "./evaluation.ts";
import type { EvaluationData, Insight } from "./evaluation.ts";

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
