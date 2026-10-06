// Offline checks for the /chat trace panel (spec 07 AC-03, AC-08; spec 16 AC-06). Each test cites the criterion it covers.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parse } from "yaml";
import { trace as TRACE } from "../messages/trace.ts";
import { keysOf } from "./i18n.ts";
import { GUARDRAIL_IDS, decisionLabel, guardrailLabel, kindLabel, traceFromTurn, traceRow } from "./trace.ts";
import type { TraceStep } from "./types.ts";

const POLICIES = parse(readFileSync(new URL("../../../contracts/policies.yaml", import.meta.url), "utf8")) as {
  guardrails: { id: string; name: string }[];
  rules: Record<string, unknown>;
};

/** A clarify turn as the live api sends it: no actions, no progress in the turn, labels only on the stream. */
const CLARIFY = {
  decision: "ask",
  intent: "unrecognized_charge",
  plan: [],
  progress: [],
  actions: [],
  guardrails_triggered: ["G-IN-03"],
  denials: [],
};
const STREAMED = [
  { step: "reading_account", label: "Revisando tu cuenta…", state: "in_progress" },
  { step: "reading_message", label: "Leyendo tu mensaje…", state: "in_progress" },
  { step: "searching", label: "Buscando el cargo…", state: "in_progress" },
];

/** A turn that touches every kind of row: streamed labels, intent, decision, plan, the four action states, a denial. */
const FULL = {
  decision: "block_and_open_case",
  intent: "unrecognized_charge",
  case_id: "NOT-0001",
  plan: ["1. Abrir un caso.", "2. Bloquear tu tarjeta terminada en 4417."],
  actions: [
    { tool: "open_case", state: "verified", verification_id: "V-0123456789AB" },
    { tool: "block_card", state: "requested" },
    { tool: "verify block_card", state: "in_progress" },
    { tool: "request_call", state: "not_confirmed" },
  ],
  guardrails_triggered: ["G-OUT-02"],
  denials: [{ guardrail_id: "G-SES-02", detail: "otro cliente" }],
};

test("spec 07 AC-08: a live turn with no actions still lists its steps from the streamed labels and the decision", () => {
  const trace = traceFromTurn(CLARIFY, STREAMED, "en");
  assert.deepEqual(trace.map((t) => t.step), ["reading_account", "reading_message", "searching", "understand", "decide"]);
  assert.ok(trace.slice(0, 3).every((t) => t.kind === "ok"), "a streamed label ran; it never claims a result");
  assert.equal(trace.at(-1)?.result, decisionLabel("ask", "en"));
  assert.match(trace[3].result, /unrecognized charge/);
});

test("spec 07 AC-08: actions carry the four states of spec 04 AC-18 and a verification summary", () => {
  const trace = traceFromTurn({
    decision: "block_and_open_case",
    case_id: "NOT-0001",
    plan: ["1. Abrir un caso.", "2. Bloquear tu tarjeta terminada en 4417."],
    actions: [
      { tool: "open_case", state: "verified", verification_id: "V-0123456789AB" },
      { tool: "block_card", state: "requested" },
      { tool: "notify", state: "in_progress" },
      { tool: "request_call", state: "not_confirmed" },
    ],
  }, [], "en");
  const by = Object.fromEntries(trace.map((t) => [t.step, t]));
  assert.equal(by.open_case.kind, "verified");
  assert.match(by.open_case.result, /verified · V-0123456789AB/);
  assert.equal(by.block_card.kind, "accepted", "requested is never shown as verified (constitution #4)");
  assert.equal(by.notify.kind, "in_progress");
  assert.equal(by.request_call.kind, "not_confirmed");
  assert.equal(by.verify.result, "1 of 4 confirmed by re-reading the system");
  assert.equal(by.verify.kind, "not_confirmed");
  assert.equal(by.plan.result, "1. Abrir un caso.\n2. Bloquear tu tarjeta terminada en 4417.");
  assert.equal(by.case.result, "NOT-0001");
  const es = Object.fromEntries(traceFromTurn(FULL, [], "es").map((t) => [t.step, t]));
  assert.equal(es.open_case.result, "verificado · V-0123456789AB");
  assert.equal(es.verify.result, "1 de 4 confirmadas al volver a leer el sistema");
});

test("spec 07 AC-08: every guardrail of contracts/policies.yaml has a plain-language name in each language", () => {
  assert.deepEqual([...GUARDRAIL_IDS].sort(), POLICIES.guardrails.map((g) => g.id).sort());
  for (const lang of ["en", "es", "pt"] as const) assert.deepEqual(Object.keys(TRACE[lang].guardrail).sort(), [...GUARDRAIL_IDS].sort(), lang);
  assert.equal(guardrailLabel("G-IN-03", "en"), "Language or ambiguity: asked to clarify");
  assert.equal(guardrailLabel("G-IN-03", "es"), "Idioma o ambigüedad: se pidió aclarar");
  assert.equal(guardrailLabel("injection_detector", "pt"), "injection detector", "an unknown id is shown as words");
});

test("spec 07 AC-03: the trace and the guardrail names never show a policy id, the score or the zone", () => {
  for (const lang of ["en", "es", "pt"] as const) {
    const trace = traceFromTurn(
      { ...CLARIFY, decision: "deny", denials: [{ guardrail_id: "G-SES-02", detail: "another customer's data" }] },
      STREAMED,
      lang,
    );
    assert.equal(trace.at(-1)?.kind, "deny");
    assert.ok(trace.at(-1)!.result.startsWith(guardrailLabel("G-SES-02", lang)));
    const { step, decision, state, intent, guardrail, kind } = TRACE[lang]; // the panel's own note names what it never shows
    const shown = JSON.stringify([trace, step, decision, state, intent, guardrail, kind]);
    for (const id of Object.keys(POLICIES.rules)) assert.ok(!shown.includes(id), `${lang}: ${id} is never shown`);
    assert.ok(!/(?<!G-)POL-|score|zone/i.test(shown), `${lang}: a guardrail id (G-POL-01) is not a policy id`);
  }
  assert.match(traceFromTurn({ denials: [{ guardrail_id: "G-SES-02", detail: "x" }] }, [], "en").at(-1)!.result, /Another customer's data refused/);
});

test("spec 07 AC-03 / spec 16 AC-06: the trace speaks one language", () => {
  // Every English phrase the trace could show: step titles, states, badges, decisions, intents and its own sentences.
  const en = TRACE.en;
  const english = [
    ...Object.values(en.step),
    ...Object.values(en.state),
    ...Object.values(en.kind),
    ...Object.values(en.decision),
    ...Object.values(en.intent),
    ...Object.values(en.guardrail),
    ...Object.values(en.panel),
    "Request:",
    "confirmed by re-reading the system",
  ];
  for (const lang of ["es", "pt"] as const) {
    // the language comes from the turn itself, as the api sends it (`CustomerTurn.language`)
    const trace: TraceStep[] = traceFromTurn({ ...FULL, language: lang }, STREAMED);
    const shown = trace.flatMap((t) => {
      const row = traceRow(t, lang);
      return [row.title, row.detail ?? "", kindLabel(t.kind, lang)];
    });
    shown.push(...FULL.guardrails_triggered.map((g) => guardrailLabel(g, lang)), ...Object.values(TRACE[lang].panel));
    for (const text of shown) {
      for (const phrase of english) {
        const leak = text === phrase || (phrase.includes(" ") && text.includes(phrase));
        assert.ok(!leak, `${lang}: "${text}" shows the English "${phrase}"`);
      }
    }
    assert.equal(traceRow({ step: "block_card", result: "", kind: "accepted" }, lang).title, TRACE[lang].step.block_card);
    assert.equal(traceRow({ step: "verify block_card", result: "", kind: "ok" }, lang).title, TRACE[lang].step.verify_block_card);
  }
  // the streamed labels keep their own words, and every trace key exists in the three languages
  assert.equal(traceRow({ step: "reading_message", result: "Leyendo tu mensaje…", kind: "ok" }, "es").title, "Leyendo tu mensaje…");
  for (const lang of ["es", "pt"] as const) assert.deepEqual(keysOf(TRACE[lang]).sort(), keysOf(TRACE.en).sort(), lang);
});
