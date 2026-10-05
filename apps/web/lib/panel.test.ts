// Offline checks for the as-is vs with Nick of Time panel (spec 12 AC-10). Run with `npm test`.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import type { BenchmarkData, EvaluationData, Insight } from "./evaluation.ts";
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
  const fallback = panelState(SEALED, PITCH, sample);
  assert.ok(fallback.kind === "ready" && fallback.arm === "S1" && fallback.note === "arm S1 (lean-rule result pending)");
  const chosen = { ...sample, model_map: { understand: { chosen: "sample-model" } } } as BenchmarkData;
  const picked = panelState(SEALED, PITCH, chosen);
  assert.ok(picked.kind === "ready" && picked.note === null);
});

test("spec 12 AC-10: the panel carries the three labels and no placeholder result file is committed", () => {
  const src = readFileSync(new URL("../app/evaluation/panel.tsx", import.meta.url), "utf-8");
  for (const label of ["[data]", "[simulated]", "[projected]"]) assert.ok(src.includes(label), label);
  assert.match(src, /n = \{state\.n\} runs/);
  assert.match(src, /upper-bound/);
  assert.match(src, /full synthetic dataset/);
  assert.doesNotMatch(src, /\[data\] \{source\}/, "the source already carries its label");
  assert.equal(existsSync(new URL("../public/data/evaluation_summary.json", import.meta.url)), false);
});
