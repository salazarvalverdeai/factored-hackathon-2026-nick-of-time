// Offline checks for the home page figures (spec 16 AC-01 home page; constitution #8). Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { LOCALES, translator } from "./i18n.ts";
import { DEADLINES, FCR, RESOLUTION, STATS, figureTexts, numbersIn } from "./landing.ts";

const DOC = readFileSync(new URL("../../../docs/problem_in_numbers.md", import.meta.url), "utf-8");
const POLICIES = readFileSync(new URL("../../../contracts/policies.yaml", import.meta.url), "utf-8");

test("spec 16 AC-01, AC-06: every number on the home page appears, spelled the same, in docs/problem_in_numbers.md, in every UI language", () => {
  for (const loc of LOCALES) {
    const missing = figureTexts(translator(loc))
      .flatMap(numbersIn)
      .filter((n) => !DOC.includes(n));
    assert.deepEqual(missing, [], loc);
  }
});

test("spec 16 AC-01: the headline is the doc's FCR, 43.6% against 76.6%, and every ticker matches its text", () => {
  assert.deepEqual(FCR.sides.map((s) => s.value), ["43.6%", "76.6%"]);
  for (const side of [FCR, ...STATS].flatMap((s) => s.sides)) {
    if (!side.ticker) continue;
    assert.equal(`${side.ticker.value.toFixed(side.ticker.decimals)}${side.ticker.suffix}`, side.value);
  }
});

test("constitution #8: every figure carries a label and a source", () => {
  for (const stat of [FCR, ...STATS, RESOLUTION]) {
    assert.ok(["data", "external", "assumption", "simulated", "projected"].includes(stat.label), stat.id);
    assert.ok(stat.sources.length > 0 && stat.sources.every((s) => s.href.startsWith("https://")), stat.id);
  }
});

test("spec 16 AC-01: every legal deadline links the official source_url recorded in contracts/policies.yaml", () => {
  assert.equal(DEADLINES.length, 5);
  for (const d of DEADLINES) assert.ok(POLICIES.includes(`source_url: ${d.source.href}`), d.country);
});
