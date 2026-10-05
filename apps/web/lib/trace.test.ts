// Offline checks for the /chat trace panel (spec 07 AC-03, AC-08). Each test cites the criterion it covers.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parse } from "yaml";
import { DECISION_LABELS, GUARDRAIL_LABELS, guardrailLabel, traceFromTurn } from "./trace.ts";

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

test("spec 07 AC-08: a live turn with no actions still lists its steps from the streamed labels and the decision", () => {
  const trace = traceFromTurn(CLARIFY, STREAMED);
  assert.deepEqual(trace.map((t) => t.step), ["reading_account", "reading_message", "searching", "understand", "decide"]);
  assert.ok(trace.slice(0, 3).every((t) => t.kind === "ok"), "a streamed label ran; it never claims a result");
  assert.equal(trace.at(-1)?.result, DECISION_LABELS.ask);
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
  });
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
});

test("spec 07 AC-08: every guardrail of contracts/policies.yaml has a plain-language name", () => {
  assert.deepEqual(Object.keys(GUARDRAIL_LABELS).sort(), POLICIES.guardrails.map((g) => g.id).sort());
  assert.equal(guardrailLabel("G-IN-03"), "Language or ambiguity: asked to clarify");
  assert.equal(guardrailLabel("injection_detector"), "injection detector", "an unknown id is shown as words");
});

test("spec 07 AC-03: the trace and the guardrail names never show a policy id, the score or the zone", () => {
  const trace = traceFromTurn(
    { ...CLARIFY, decision: "deny", denials: [{ guardrail_id: "G-SES-02", detail: "another customer's data" }] },
    STREAMED,
  );
  assert.equal(trace.at(-1)?.kind, "deny");
  assert.match(trace.at(-1)!.result, /Another customer's data refused/);
  const shown = JSON.stringify([trace, GUARDRAIL_LABELS, DECISION_LABELS]);
  for (const id of Object.keys(POLICIES.rules)) assert.ok(!shown.includes(id), `${id} is never shown`);
  assert.ok(!/(?<!G-)POL-|score|zone/i.test(shown), "a guardrail id (G-POL-01) is not a policy id");
});
