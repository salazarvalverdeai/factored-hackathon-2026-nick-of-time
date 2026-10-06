// Offline checks: no bracket tags on customer or analyst operational screens (spec 08, spec 13) and the site footer (spec 16).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { demoDateLabel } from "./demo-date.ts";
import { COPILOT_ACTION_LABELS, formatDateTime, HANDOFF_REASON_LABELS, handoffReasonLabel } from "./handoff-labels.ts";
import { LOCALES, translator } from "./i18n.ts";

const src = (p: string) => readFileSync(new URL(p, import.meta.url), "utf-8");
const TAG = /\[(simulated|assumption|data|external|projected)\]/;

test("spec 08 / spec 13: login, console and case pages carry no bracket tags", () => {
  for (const f of ["../app/login/page.tsx", "../app/console/page.tsx", "../app/case/[id]/case-view.tsx"]) {
    assert.ok(!TAG.test(src(f)), f);
  }
  assert.ok(!/Deep link/.test(src("../app/case/[id]/case-view.tsx")));
});

test("spec 08, spec 16 AC-06: the handoff card says 'sin dato' without a score (a translated label) and hides an empty trace", () => {
  const s = src("../app/console/page.tsx");
  assert.ok(s.includes('t("console.handoff.scoreNone")'));
  assert.equal(translator("es")("console.handoff.scoreNone"), "Score del banco: sin dato");
  assert.equal(translator("pt")("console.handoff.scoreNone"), "Score do banco: sem dado");
  assert.equal(translator("en")("console.handoff.scoreNone"), "Bank score: no data");
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
  // spec 16 AC-06: in every UI language
  for (const loc of LOCALES) {
    const reasonLabels = HANDOFF_REASON_LABELS[loc];
    const actionLabels = COPILOT_ACTION_LABELS[loc];
    for (const r of reasons) assert.ok(reasonLabels[r] && !reasonLabels[r].includes("_"), `${loc} ${r}`);
    for (const a of actions) assert.ok(actionLabels[a] && !actionLabels[a].includes("_"), `${loc} ${a}`);
    assert.equal(Object.keys(reasonLabels).length, reasons.length);
    assert.equal(Object.keys(actionLabels).length, actions.length);
  }
  assert.equal(handoffReasonLabel("person_requested", "es"), "El cliente pidió hablar con una persona");
  assert.equal(handoffReasonLabel("some_new_reason", "pt"), "Some new reason");
});

test("spec 08 / spec 13, spec 16 AC-06: timeline dates are es-MX on a 24 h clock in Spanish, and 24 h in every language", () => {
  const out = formatDateTime("es", "2026-10-05T19:04:23Z");
  assert.ok(!/AM|PM/i.test(out), out);
  assert.match(out, /^\d{1,2}\/\d{1,2}\/2026, \d{2}:\d{2}:\d{2}$/);
  assert.equal(out, new Date("2026-10-05T19:04:23Z").toLocaleString("es-MX", { hour12: false, hourCycle: "h23" }));
  for (const loc of LOCALES) {
    const s = formatDateTime(loc, "2026-10-05T19:04:23Z");
    assert.ok(!/AM|PM|a\. ?m\.|p\. ?m\./i.test(s), `${loc}: ${s}`);
    assert.match(s, /\d{2}:04:23$/, `${loc}: ${s}`);
  }
  assert.match(formatDateTime("pt", new Date(2026, 9, 5, 9, 4, 23)), /^05\/10\/2026,? 09:04:23$/);
  assert.match(formatDateTime("en", new Date(2026, 9, 5, 9, 4, 23)), /^10\/5\/2026, 09:04:23$/);
  for (const f of ["../app/console/page.tsx", "../components/timeline.tsx", "../app/case/[id]/case-view.tsx"]) {
    assert.ok(!/toLocale(Time)?String\(\)/.test(src(f)), f);
  }
});
