// Offline checks for the as-is vs with Nick of Time panel (spec 12 AC-10). Run with `npm test`.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import type { EvaluationData, Insight } from "./evaluation.ts";
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

test("spec 12 AC-10: with a sealed held-out run the projection is recomputed from the two inputs", () => {
  const state = panelState(SEALED, PITCH);
  assert.equal(state.kind, "ready");
  if (state.kind !== "ready") return;
  const fcr = PITCH.find((c) => c.key === "fcr")!.groups[0];
  const rate = SEALED.data.arms.find((a) => a.arm === "S1")!.overall.safe_automated_resolution.value!;
  assert.equal(state.projection!.contacts, Math.round((rate - fcr.value / 100) * fcr.denominator));
  assert.equal(project(50, 1000, 0.8).contacts, 300);
  assert.equal(project(50, 1000, 0.4).contacts, 0, "no improvement is never shown as a negative saving");
});

test("spec 12 AC-10: the panel carries the three labels and no placeholder result file is committed", () => {
  const src = readFileSync(new URL("../app/evaluation/panel.tsx", import.meta.url), "utf-8");
  for (const label of ["[data]", "[simulated]", "[projected]"]) assert.ok(src.includes(label), label);
  assert.equal(existsSync(new URL("../public/data/evaluation_summary.json", import.meta.url)), false);
});
