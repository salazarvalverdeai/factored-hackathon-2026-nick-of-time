import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

function block(selector: string): Record<string, string> {
  const m = css.match(new RegExp(`(?:^|\\n)${selector.replace(".", "\\.")}\\s*\\{([\\s\\S]*?)\\n\\}`));
  assert.ok(m, `block ${selector}`);
  const out: Record<string, string> = {};
  for (const d of m[1].matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) out[d[1]] = d[2];
  return out;
}

function lum(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function ratio(a: string, b: string): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const pairs: [string, string][] = [
  ["foreground", "background"],
  ["card-foreground", "card"],
  ["muted-foreground", "background"],
  ["muted-foreground", "card"],
  ["muted-foreground", "muted"],
  ["primary-text", "background"],
  ["primary-text", "card"],
  ["primary-text", "muted"],
  ["teal-text", "background"],
  ["teal-text", "card"],
  ["amber-text", "background"],
  ["amber-text", "card"],
  ["primary-foreground", "primary"],
  ["accent-foreground", "accent"],
];

for (const [name, sel] of [["light", ":root"], ["dark", ".dark"]] as const) {
  const t = block(sel);
  for (const [fg, bg] of pairs) {
    test(`AA contrast ${name}: ${fg} on ${bg} >= 4.5`, () => {
      assert.ok(t[fg] && t[bg], `tokens ${fg}/${bg} defined`);
      const r = ratio(t[fg], t[bg]);
      assert.ok(r >= 4.5, `${fg} ${t[fg]} on ${bg} ${t[bg]} = ${r.toFixed(2)}`);
    });
  }
}

test("muted-foreground stays comfortably readable (>= 5.5) on its own surfaces", () => {
  for (const sel of [":root", ".dark"]) {
    const t = block(sel);
    for (const bg of ["background", "card", "muted"]) assert.ok(ratio(t["muted-foreground"], t[bg]) >= 5.5, `${sel} ${bg}`);
  }
});
