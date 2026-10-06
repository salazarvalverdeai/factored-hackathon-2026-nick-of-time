// The FCR hero must render its final figures in the initial (server) render, never a 0 start state (home page review P0).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { FCR } from "./landing.ts";
import { formatTicker, tickerStart } from "./ticker.ts";

test("initial render of the FCR figures contains 43.6 and 76.6 and never 0.0%", () => {
  // NumberTicker renders formatTicker(value) in the first render (server and client) and the figure adds the suffix.
  const initial = FCR.sides.map((s) => `${formatTicker(s.ticker!.value, s.ticker!.decimals)}${s.ticker!.suffix}`).join(" ");
  assert.ok(initial.includes("43.6") && initial.includes("76.6"));
  assert.ok(!initial.includes("0.0%"));
});

test("the count never starts at 0 and the ticker never writes a start value into the DOM", () => {
  for (const s of FCR.sides) assert.ok(tickerStart(s.ticker!.value) > 0);
  const src = readFileSync(new URL("../components/ui/number-ticker.tsx", import.meta.url), "utf-8");
  assert.ok(!/textContent = format\((startValue|from)/.test(src));
});
