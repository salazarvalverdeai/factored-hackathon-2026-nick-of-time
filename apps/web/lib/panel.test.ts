// Offline checks for the as-is vs with Nick of Time panel (spec 12 AC-10). Run with `npm test`.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import { D070_SENTENCE, type BenchmarkData, type EvaluationData, type Insight } from "./evaluation.ts";
import { asIsRows, panelState, project, type PitchContacts } from "./panel.ts";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf-8"));
const PITCH = read("../public/data/pitch_numbers.json").data.contacts as PitchContacts;
const DEV = read("../app/evaluation/__fixtures__/evaluation_summary.json") as Insight<EvaluationData>;
const SEALED = read("../app/evaluation/__fixtures__/evaluation_summary_sealed.json") as Insight<EvaluationData>;

test("spec 12 AC-10: the as-is rows are the pitch numbers, FCR 43.6% against the bank's 76.6%", () => {
  const fcr = asIsRows(PITCH).find((r) => r.key === "fcr")!;
  assert.equal(fcr.complaints, 43.6);
  assert.equal(Math.round(fcr.bank * 10) / 10, 76.6);
  assert.deepEqual(asIsRows(PITCH).map((r) => r.key), ["fcr", "follow_up", "duration"]);
});

test("spec 12 AC-10: without the file, or on a development or unsealed run, WITH US is pending with no projection", () => {
  assert.equal(panelState(null, PITCH).kind, "pending");
  assert.equal(panelState(DEV, PITCH).kind, "pending");
  const unsealed = { ...SEALED, data: { ...SEALED.data, protocol: { status: "UNSEALED", sha256: null } } };
  assert.equal(panelState(unsealed, PITCH).kind, "pending");
  const dev = { ...SEALED, data: { ...SEALED.data, set: "dev" } };
  assert.equal(panelState(dev, PITCH).kind, "pending");
});

test("spec 12 AC-10: the projection is a range recomputed from the CI of the rate, never a point value", () => {
  const state = panelState(SEALED, PITCH);
  assert.equal(state.kind, "ready");
  if (state.kind !== "ready") return;
  const fcr = PITCH.find((c) => c.key === "fcr")!.groups[0];
  const rate = SEALED.data.arms.find((a) => a.arm === "S1")!.overall.safe_automated_resolution;
  assert.equal(state.projection!.low, Math.round((rate.ci_low! - fcr.value / 100) * fcr.denominator));
  assert.equal(state.projection!.high, Math.round((rate.ci_high! - fcr.value / 100) * fcr.denominator));
  assert.ok(state.projection!.low < state.projection!.high);
  assert.equal(state.n, rate.denominator, "n is the number of runs on the automatic block-and-case path");
  const flat = project(50, 1000, { value: 0.8, numerator: 8, denominator: 10, ci_low: 0.6, ci_high: 0.9 });
  assert.deepEqual([flat.low, flat.high], [100, 400]);
  assert.equal(project(50, 1000, { value: 0.4, numerator: 4, denominator: 10, ci_low: 0.2, ci_high: 0.45 }).high, 0, "never a negative saving");
});

test("spec 12 AC-10: the arm is the one running the benchmark's chosen model; otherwise S1 with a visible note", () => {
  const sample = read("../app/evaluation/__fixtures__/benchmark.json").data as BenchmarkData;
  const absent = panelState(SEALED, PITCH, null);
  assert.ok(absent.kind === "ready" && absent.arm === "S1" && absent.note === "arm S1 (lean-rule result pending)", "pending only without benchmark.json");
  const fallback = panelState(SEALED, PITCH, sample);
  assert.ok(fallback.kind === "ready" && fallback.arm === "S1" && fallback.note !== null);
  assert.doesNotMatch(fallback.note!, /pending/);
  assert.match(fallback.note!, /held-out arm shown: S1 = Haiku 4\.5 \[assumption\] \(D-080\)/);
  const chosen = { ...sample, model_map: { understand: { chosen: "sample-model" } } } as BenchmarkData;
  const picked = panelState(SEALED, PITCH, chosen);
  assert.ok(picked.kind === "ready" && picked.note === null);
});

test("spec 12 AC-10: without scores_d070 the panel keeps its single official score and no ADR 0031 sentence", () => {
  const state = panelState(SEALED, PITCH);
  assert.ok(state.kind === "ready");
  if (state.kind !== "ready") return;
  assert.deepEqual(state.scores.map((s) => s.key), ["official"]);
  assert.equal(state.sentence, null);
  assert.deepEqual(state.scores[0].projection, state.projection);
});

const REAL_SUMMARY = new URL("../public/data/evaluation_summary.json", import.meta.url);
const REAL_BENCH = new URL("../public/data/benchmark.json", import.meta.url);
const realFiles = existsSync(REAL_SUMMARY) && existsSync(REAL_BENCH);

test("spec 12 AC-10, spec 10 AC-15: with the real files the panel shows both held-out scores, both projections and the ADR 0031 sentence", { skip: !realFiles }, () => {
  const summary = JSON.parse(readFileSync(REAL_SUMMARY, "utf-8")) as Insight<EvaluationData>;
  const bench = JSON.parse(readFileSync(REAL_BENCH, "utf-8")).data as BenchmarkData;
  const state = panelState(summary, PITCH, bench);
  assert.equal(state.kind, "ready");
  if (state.kind !== "ready") return;
  // spec 15: B0 kept; the arm shown is S1, and the note says so instead of "pending".
  assert.equal(state.arm, "S1");
  assert.equal(state.note, "B0 kept: no arm meets the floors (spec 15); held-out arm shown: S1 = Haiku 4.5 [assumption] (D-080)");
  assert.doesNotMatch(state.note!, /pending/);
  // spec 10 AC-15 / ADR 0031: official first, secondary labeled as such (D-083: sealed = official).
  const [official, secondary] = state.scores;
  assert.equal(state.scores.length, 2);
  assert.equal(official.key, "official");
  assert.equal(official.label, "Official: sealed rules (protocol-v1)");
  assert.equal(secondary.key, "secondary");
  assert.match(secondary.label, /^Secondary: D-070 handoff rule \(ADR 0031, decided before the run\)$/);
  const d070 = summary.data.scores_d070!.arms.S1;
  assert.deepEqual(official.rate, d070.official.safe_automated_resolution);
  assert.deepEqual(secondary.rate, d070.secondary.safe_automated_resolution);
  assert.deepEqual([official.rate.numerator, official.rate.denominator], [0, 20]);
  assert.deepEqual([secondary.rate.numerator, secondary.rate.denominator, secondary.rate.value], [16, 20, 0.8]);
  assert.equal(state.rate, official.rate, "the panel's headline rate stays the official one");
  assert.equal(state.sentence, D070_SENTENCE);
  // Each projection is a CI range tied to its own score, over the same stated base.
  const fcr = PITCH.find((c) => c.key === "fcr")!.groups[0];
  for (const s of state.scores) {
    assert.ok(s.projection);
    assert.equal(s.projection!.volume, fcr.denominator);
    assert.equal(s.projection!.low, Math.max(0, Math.round((s.rate.ci_low! - fcr.value / 100) * fcr.denominator)));
    assert.equal(s.projection!.high, Math.max(0, Math.round((s.rate.ci_high! - fcr.value / 100) * fcr.denominator)));
  }
  assert.deepEqual([official.projection!.low, official.projection!.high], [0, 0]);
  assert.ok(secondary.projection!.low > 0 && secondary.projection!.low < secondary.projection!.high);
  // The view labels every projection [projected], ties it to its score and prints the ADR sentence.
  const src = readFileSync(new URL("../app/evaluation/panel.tsx", import.meta.url), "utf-8");
  assert.match(src, /state\.scores\.map\(\(s\) => \(\s*<ScoreCard/);
  assert.equal((src.match(/<Tag>\[projected\]<\/Tag>/g) ?? []).length, 2, "both projection branches carry [projected]");
  assert.match(src, /from this score&apos;s 95% CI/);
  assert.match(src, /\{state\.sentence\}/);
});

test("spec 12 AC-10: the panel carries the three labels and no placeholder result file is committed", () => {
  const src = readFileSync(new URL("../app/evaluation/panel.tsx", import.meta.url), "utf-8");
  for (const label of ["[data]", "[simulated]", "[projected]"]) assert.ok(src.includes(label), label);
  assert.match(src, /n = \{s\.n\} runs/);
  assert.match(src, /upper-bound/);
  assert.match(src, /full synthetic dataset/);
  assert.doesNotMatch(src, /\[data\] \{source\}/, "the source already carries its label");
  const summaryUrl = new URL("../public/data/evaluation_summary.json", import.meta.url);
  if (existsSync(summaryUrl)) assert.doesNotMatch(readFileSync(summaryUrl, "utf-8"), /SAMPLE FOR TESTS ONLY/);
});
