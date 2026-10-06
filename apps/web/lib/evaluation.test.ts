// Offline checks for the display logic of /evaluation (spec 12). Run with `npm test`.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import test from "node:test";
import { dataDir } from "./data-dir.ts";
import { classifierRunNote, DEVELOPMENT_CHIP, GENERATOR_FLAG, developmentRuns, pageNotice, METRICS, METRIC_MEANING, RULES_REVIEW_SENTENCE, DETAILS, detailUrl, headingSlug, limitations, RESULT_FILES, costQualityPoints, developmentNotice, generatorFlag, interval, pending, protocolNotice, rateParts, rateText, scoreText } from "./evaluation.ts";
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
  // Each result file is either absent (pending) or a real sealed result, never a sample or a development run.
  const sealedRuns: Record<string, (d: Record<string, unknown>) => boolean> = {
    "classifier.json": (d) => d.run === "test",
    "fraud_benchmark.json": (d) => d.scored_window === "test",
    "evaluation_summary.json": (d) => d.set === "heldout",
    "benchmark.json": (d) => d.split === "test",
  };
  for (const [name, isTestRun] of Object.entries(sealedRuns)) {
    const url = new URL(`../public/data/${name}`, import.meta.url);
    if (!existsSync(url)) continue;
    const file = JSON.parse(readFileSync(url, "utf-8")) as Insight<Record<string, unknown> & { protocol: { status: string } }>;
    assert.doesNotMatch(file.source ?? "", /SAMPLE FOR TESTS ONLY/, name);
    assert.equal(file.data.protocol.status, "SEALED", name);
    assert.ok(isTestRun(file.data), `${name} is the test or held-out run`);
  }
  // classifier.json is the real sealed test run (ADR 0028), not a placeholder
  const real = JSON.parse(readFileSync(new URL("../public/data/classifier.json", import.meta.url), "utf-8")) as Insight<ClassifierData>;
  assert.doesNotMatch(real.source, /SAMPLE FOR TESTS ONLY/);
  assert.equal(real.data.run, "test");
  assert.equal(real.data.protocol.status, "SEALED");
  assert.equal(real.data.test_review, "rules-v1");
  assert.equal(protocolNotice(real.data.protocol), null);
  assert.ok(real.data.arms.every((a) => a.meets_floors === false));
  assert.equal(classifierRunNote(real.data), "Sealed test result · test split decided by fixed rules (rules-v1), not by a person · no arm meets the floors; B0 kept.");
  assert.equal(classifierRunNote(CLASSIFIER.data), null);
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
  assert.deepEqual(Object.keys(CLASSIFIER.data).sort(), ["arms", "chosen_arm", "injection", "label", "protocol", "tau", "test_review", "test_split"]);
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

test("spec 12 AC-01: an arm of the family that wrote the test split is flagged (ADR 0025), others are not", () => {
  const bench = fixture<BenchmarkData>("benchmark.json").data.b1.arms;
  assert.deepEqual(bench.filter((a) => generatorFlag(a)).map((a) => a.arm), ["Sample D"]);
  assert.equal(generatorFlag({ same_family_as_generator: true }), GENERATOR_FLAG);
  for (const missing of [{}, { same_family_as_generator: null }, { same_family_as_generator: false }]) assert.equal(generatorFlag(missing), null);
  assert.ok(fixture<ClassifierData>("classifier.json").data.arms.every((a) => generatorFlag(a) === null));
});

const FILES = {
  summary: SAMPLE,
  benchmark: fixture<BenchmarkData>("benchmark.json"),
  classifier: fixture<ClassifierData>("classifier.json"),
  fraud: fixture<FraudData>("fraud_benchmark.json"),
};

test("spec 12 AC-11: every metric has a plain explanation and every chart links to the markdown that defines it", () => {
  for (const m of METRICS) assert.ok(METRIC_MEANING[m.key]?.length > 20, m.key);
  assert.match(METRIC_MEANING.safe_automated_resolution, /blocked and the case opened with no person/);
  for (const key of Object.keys(DETAILS) as (keyof typeof DETAILS)[]) {
    const d = DETAILS[key];
    const url = detailUrl(key);
    assert.ok(url.startsWith("https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/blob/main/" + d.path), key);
    const file = new URL(`../../../${d.path}`, import.meta.url);
    assert.ok(existsSync(file), `${d.path} exists`);
    if (d.heading) {
      const headings = readFileSync(file, "utf-8").split("\n").filter((l) => l.startsWith("#")).map((l) => l.replace(/^#+\s*/, ""));
      assert.ok(headings.includes(d.heading), `${d.path} has the heading "${d.heading}"`);
      assert.ok(url.endsWith(`#${headingSlug(d.heading)}`));
    }
  }
  assert.equal(headingSlug("4.1 Metric definitions"), "41-metric-definitions");
});

test("spec 12 AC-11: limitations are plain sentences, with no bracket labels, only for the files that exist", () => {
  assert.deepEqual(limitations({ summary: null, benchmark: null, classifier: null, fraud: null }), []);
  const all = limitations(FILES);
  assert.match(all.join(" "), /Only 20 cases were scored/);
  assert.ok(all.includes(RULES_REVIEW_SENTENCE));
  assert.match(all.join(" "), /run once/);
  assert.match(all.join(" "), /synthetic dataset/);
  assert.match(all.join(" "), /written by the team with AI assistance/);
  for (const text of all) assert.ok(text.length <= 120, `one line per item: ${text}`); // the lead: one line per limitation
  assert.match(all.join(" "), /one model family per split/);
  assert.match(all.join(" "), /benchmark scores the models/);
  for (const text of all) assert.doesNotMatch(text, /\[(simulated|data|projected|assumption)\]/);
  const onlyFraud = limitations({ ...FILES, summary: null, benchmark: null, classifier: null });
  assert.equal(onlyFraud.length, 1);
  assert.match(onlyFraud[0], /synthetic dataset/);
  const reviewed = fixture<ClassifierData>("classifier.json");
  reviewed.data.test_review = "human";
  assert.ok(!limitations({ ...FILES, classifier: reviewed }).includes(RULES_REVIEW_SENTENCE));
  const noClassifier = limitations({ ...FILES, classifier: null });
  assert.ok(!noClassifier.includes(RULES_REVIEW_SENTENCE));
});

test("spec 12 AC-04, AC-05, AC-06, AC-07, AC-11: the new charts keep the empty state, the notice, the hover and focus detail and a table", () => {
  const read = (f: string) => readFileSync(new URL(`../app/evaluation/${f}`, import.meta.url), "utf-8");
  const page = read("page.tsx"), sections = read("sections.tsx"), results = read("results.tsx"), panel = read("panel.tsx");
  assert.match(page, /<Pending \{\.\.\.classifier\.missing!\} \/>/); // AC-04 still reaches every section
  assert.match(sections, /<DevChip show=\{protocolNotice\(file\.data\.protocol\) !== null\} \/>/); // AC-05: a chip per section
  assert.match(results, /<DevChip show=\{developmentNotice\(data\) !== null\} \/>/);
  for (const text of [sections, results]) assert.doesNotMatch(text, /development-notice/); // AC-05: the notice is said once, on the page
  assert.equal((page.match(/data-slot="development-notice"/g) ?? []).length, 1);
  assert.match(page, /pageNotice\(files\)/);
  assert.match(sections, /tabIndex=\{0\}[^]*?\{\.\.\.bind\(r\.tip\)\}/); // AC-06, AC-07: the bar rows take focus and show the tooltip
  assert.ok((sections.match(/<TableView/g) ?? []).length >= 2 && (sections.match(/<Table\b/g) ?? []).length >= 3); // AC-07 tables stay
  assert.equal((sections.match(/<Section title=/g) ?? []).length, 3);
  assert.equal((sections.match(/detail="(benchmark|classifier|fraud)"/g) ?? []).length, 3); // AC-11
  assert.match(results, /detail="harness"/);
  assert.match(page, /href="\/agent"/); // the architecture lives on /agent
  const intro = page.slice(page.indexOf('<p className="mb-6'), page.indexOf('<div className="space-y-6">'));
  assert.ok(intro.length > 0 && intro.split(/(?<=[.:;])\s/).length <= 3, "the intro is one line");
  // labels sit beside figures (a figure's label prop, a table head) or in the projection line, never in prose
  const prose = panel.replace(/label=\{?[^}\n]*?\[(data|simulated|projected)\][^}\n]*?\}?(?=\s)/g, "").replace(/head=\{\[[^]*?\]\}/g, "")
    .replace(/Contacts avoided[^]*?<\/p>/, "");
  for (const text of [intro, prose]) assert.doesNotMatch(text, /\[(simulated|data|projected)\]/); // AC-11: labels go on figures, not in prose
});

test("spec 12 AC-11: EVALUATION_DATA_DIR is honored only inside the repo or the temp dir", () => {
  const cwd = resolve("/repo/apps/web");
  assert.equal(dataDir(undefined, cwd, "/tmp"), resolve(cwd, "public/data"));
  assert.equal(dataDir("/etc", cwd, tmpdir()), resolve(cwd, "public/data"));
  assert.equal(dataDir("/repo/apps/web/app/evaluation/__fixtures__", cwd, tmpdir()), "/repo/apps/web/app/evaluation/__fixtures__");
  assert.equal(dataDir("/repo/../etc", cwd, tmpdir()), resolve(cwd, "public/data"));
  assert.equal(dataDir(resolve(tmpdir(), "fx"), cwd, tmpdir()), resolve(tmpdir(), "fx"));
});

test("spec 12 AC-05: one page notice names every development-run file and why; a sealed held-out file is not named", () => {
  assert.deepEqual(developmentRuns(FILES).map((r) => r.file), ["evaluation_summary.json", "benchmark.json", "classifier.json", "fraud_benchmark.json"]);
  const notice = pageNotice(FILES)!;
  assert.match(notice, /^Development run, not the final result: evaluation_summary\.json \(it ran on the "dev" set, not the held-out and the evaluation protocol is UNSEALED\); benchmark\.json \(the evaluation protocol is UNSEALED\);/);
  assert.ok(notice.includes(`"${DEVELOPMENT_CHIP}"`));
  const sealed = { status: "SEALED", sha256: "a".repeat(64) };
  const final = {
    summary: { ...SAMPLE, data: { ...SAMPLE.data, set: "heldout", protocol: sealed } },
    benchmark: { ...BENCH, data: { ...BENCH.data, protocol: sealed } },
    classifier: null,
    fraud: null,
  };
  assert.equal(pageNotice(final), null);
  assert.deepEqual(developmentRuns({ ...final, fraud: FRAUD }).map((r) => r.file), ["fraud_benchmark.json"]);
  assert.equal(pageNotice({ summary: null, benchmark: null, classifier: null, fraud: null }), null);
});

test("spec 12 AC-11: every 'Detail →' on /evaluation opens the shared panel, none is a plain anchor", () => {
  const dir = new URL("../app/evaluation/", import.meta.url);
  for (const file of ["explain.tsx", "page.tsx", "results.tsx", "sections.tsx", "panel.tsx"]) {
    const src = readFileSync(new URL(file, dir), "utf-8");
    assert.doesNotMatch(src, /<a\b[^>]*>\s*Detail →/, `${file}: Detail opens the panel, never a plain link`);
  }
  const explain = readFileSync(new URL("explain.tsx", dir), "utf-8");
  assert.match(explain, /<DetailButton title=\{d\.title\} detail=\{\{ meaning: d\.meaning, method: d\.method, source: d\.source, label: d\.label, spec: detailUrl\(detail\) \}\}/);
  const button = readFileSync(new URL("../components/detail-button.tsx", import.meta.url), "utf-8");
  assert.match(button, /What it means/);
  assert.match(button, /Read the spec →/);
  for (const key of Object.keys(DETAILS) as (keyof typeof DETAILS)[]) {
    const d = DETAILS[key];
    for (const text of [d.meaning, d.method]) {
      const sentences = text.split(/(?<=\.)\s+/).filter(Boolean);
      assert.ok(sentences.length >= 1 && sentences.length <= 3, `${key}: ${sentences.length} sentences`);
      assert.doesNotMatch(text, /\[(simulated|data|projected|assumption|external)\]/, `${key}: the label sits in its own field`);
    }
    assert.match(d.label, /^\[(data|simulated)\]/, key);
    assert.ok(d.source.length > 0, key);
  }
});
