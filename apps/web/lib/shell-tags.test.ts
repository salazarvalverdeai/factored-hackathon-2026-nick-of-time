// Offline checks: no bracket tags on customer or analyst operational screens (spec 08, spec 13) and the site footer (spec 16).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { demoDateLabel } from "./demo-date.ts";
import { COPILOT_ACTION_LABELS, formatDateTime, HANDOFF_REASON_LABELS } from "./handoff-labels.ts";

const src = (p: string) => readFileSync(new URL(p, import.meta.url), "utf-8");
const TAG = /\[(simulated|assumption|data|external|projected)\]/;

test("spec 08 / spec 13: login, console and case pages carry no bracket tags", () => {
  for (const f of ["../app/login/page.tsx", "../app/console/page.tsx", "../app/case/[id]/case-view.tsx"]) {
    assert.ok(!TAG.test(src(f)), f);
  }
  assert.ok(!/Deep link/.test(src("../app/case/[id]/case-view.tsx")));
});

test("spec 08: the handoff card says 'sin dato' without a score and hides an empty trace", () => {
  const s = src("../app/console/page.tsx");
  assert.ok(s.includes("Score del banco: sin dato"));
  assert.ok(s.includes("h.trace_id ? ` · trace"));
});

test("spec 13: the demo date is shown in words per language", () => {
  assert.equal(demoDateLabel("2026-06-01", "es"), "Fecha de la demo: 1 de junio de 2026");
  assert.equal(demoDateLabel("2026-06-01", "pt"), "Data da demo: 1 de junho de 2026");
});

test("spec 16: the site footer lists the team, the repo and the five labels, and is wired in the layout", () => {
  const f = src("../components/site-footer.tsx");
  for (const x of ["Freddy", "GianMarco", "Diego", "Factored AI", "github.com/salazarvalverdeai", "[data]", "[external]", "[assumption]", "[simulated]", "[projected]"]) {
    assert.ok(f.includes(x), x);
  }
  assert.ok(src("../app/layout.tsx").includes("<SiteFooter />"));
});

test("spec 08: every handoff_reason and copilot action of the contract has a human label", () => {
  const schema = JSON.parse(src("../../../contracts/handoff.schema.json"));
  const reasons: string[] = schema.properties.handoff_reason.enum;
  const actions: string[] = schema.properties.copilot_proposal.properties.action.enum;
  for (const r of reasons) assert.ok(HANDOFF_REASON_LABELS[r] && !HANDOFF_REASON_LABELS[r].includes("_"), r);
  for (const a of actions) assert.ok(COPILOT_ACTION_LABELS[a] && !COPILOT_ACTION_LABELS[a].includes("_"), a);
  assert.equal(Object.keys(HANDOFF_REASON_LABELS).length, reasons.length);
  assert.equal(Object.keys(COPILOT_ACTION_LABELS).length, actions.length);
});

test("spec 08 / spec 13: timeline dates are es-MX on a 24 h clock", () => {
  const out = formatDateTime("2026-10-05T19:04:23Z");
  assert.ok(!/AM|PM/i.test(out), out);
  assert.match(out, /^\d{1,2}\/\d{1,2}\/2026, \d{2}:\d{2}:\d{2}$/);
  for (const f of ["../app/console/page.tsx", "../components/timeline.tsx", "../app/case/[id]/case-view.tsx"]) {
    assert.ok(!/toLocale(Time)?String\(\)/.test(src(f)), f);
  }
});
