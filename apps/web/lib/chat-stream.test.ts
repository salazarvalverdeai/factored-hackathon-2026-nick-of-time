// Offline checks for the agentic chat (spec 01 §6.4.1 and AC-09/AC-10, spec 04 AC-38/AC-39, spec 07 AC-02 to AC-09,
// design pass 1 findings 1-4). Each test cites the criterion it covers. No network, no LLM.
import assert from "node:assert/strict";
import test from "node:test";
import { createApi } from "./api.ts";
import {
  EMPTY_STREAM,
  applyText,
  applyTool,
  chipsFor,
  customerText,
  formatDate,
  formatTimestamp,
  localizeTimes,
  parseCard,
  parseTextChunk,
  parseToolEvent,
  replyBody,
  settleTools,
  stableMarkdown,
} from "./chat-stream.ts";
import { createLiveApi } from "./live.ts";
import { MESSAGES, fill } from "./mock/messages.ts";
import { MockStore } from "./mock/store.ts";
import { mockTurnEvents, textChunks } from "./mock/stream.ts";
import { traceRow } from "./trace.ts";
import type { TextChunk, ToolEvent } from "./chat-stream.ts";
import type { Receipt, Suggestion } from "./types.ts";

// A run as the api forwards it: the exact shapes of spec 01 §6.4.1.
const RUNNING = { kind: "tool", id: "tc-1", step: "block_card", title: "Bloqueando tu tarjeta", status: "running", cards: [], at: "2026-06-01T15:00:03Z" };
const DONE = {
  kind: "tool",
  id: "tc-1",
  step: "block_card",
  title: "Bloqueando tu tarjeta",
  status: "done",
  summary: "Bloqueo confirmado.",
  cards: [{ type: "action", tool: "block_card", state: "verified", verification_id: "V-K-0001-B" }],
  at: "2026-06-01T15:00:04Z",
};

test("spec 01 AC-09, spec 07 AC-11: tool events parse in the §6.4.1 shape, with or without kind; other chunks are dropped", () => {
  const t = parseToolEvent(RUNNING);
  assert.deepEqual(t, { id: "tc-1", step: "block_card", title: "Bloqueando tu tarjeta", status: "running", cards: [], at: "2026-06-01T15:00:03Z" });
  const bare: Record<string, unknown> = { ...DONE };
  delete bare.kind;
  assert.equal(parseToolEvent(bare)?.status, "done");
  assert.equal(parseToolEvent({ ...DONE, kind: "text" }), null, "a chunk of another kind");
  assert.equal(parseToolEvent({ ...DONE, status: "ok" }), null, "a status outside running|done|failed");
  assert.equal(parseToolEvent({ ...DONE, id: 3 }), null);
  assert.equal(parseToolEvent("nope"), null);
  assert.deepEqual(parseTextChunk({ kind: "text", message_id: "m1", delta: "Hola" }), { message_id: "m1", delta: "Hola" });
  assert.equal(parseTextChunk({ message_id: "m1" }), null);
});

test("spec 07 AC-11, spec 01 §6.4.1: cards come only on done, and a card outside the union is dropped, never guessed", () => {
  assert.deepEqual(parseToolEvent({ ...RUNNING, cards: DONE.cards })?.cards, [], "no cards on running");
  const mixed = parseToolEvent({
    ...DONE,
    cards: [
      { type: "charge", transaction_id: "tx-1", date: "2026-05-30", amount: 4200, currency: "MXN", merchant: null, last4: "4417", synthetic: false },
      { type: "verdict", headline: "Corresponde bloquear tu tarjeta.", actions: ["Bloquear la tarjeta"] },
      { type: "deadline", kind: "credit", date: "2026-06-03", source_label: "Banxico, Circular 3/2012", source_url: "https://www.banxico.org.mx/x.pdf" },
      { type: "case", case_id: "K-0001", status: "new" },
      { type: "score", value: 62 },
      { type: "charge", transaction_id: "tx-2" },
    ],
  });
  assert.deepEqual(
    mixed?.cards.map((c) => c.type),
    ["charge", "verdict", "deadline", "case"],
  );
  assert.equal(JSON.stringify(mixed).includes("62"), false, "a score never reaches the page");
});

test("spec 07 AC-11, constitution #4: an action card says verified only with a V- id; otherwise it is shown as requested", () => {
  assert.equal(parseCard({ type: "action", tool: "block_card", state: "verified", verification_id: "V-1" })?.type, "action");
  const noProof = parseCard({ type: "action", tool: "block_card", state: "verified", verification_id: null });
  assert.equal(noProof && noProof.type === "action" ? noProof.state : null, "requested");
  assert.equal(parseCard({ type: "action", tool: "block_card", state: "done", verification_id: null }), null, "not one of the four states");
});

test("spec 07 AC-11, spec 04 AC-38: running then exactly one done or failed with the same id; a result never goes back", () => {
  let s = applyTool(EMPTY_STREAM, parseToolEvent(RUNNING) as ToolEvent);
  assert.equal(s.tools.length, 1);
  s = applyTool(s, parseToolEvent(DONE) as ToolEvent);
  assert.equal(s.tools.length, 1);
  assert.equal(s.tools[0].status, "done");
  assert.equal(s.tools[0].cards.length, 1);
  const again = applyTool(s, parseToolEvent({ ...DONE, status: "failed" }) as ToolEvent);
  assert.equal(again.tools[0].status, "done", "a second result is ignored");
  assert.equal(applyTool(s, parseToolEvent(RUNNING) as ToolEvent).tools[0].status, "done", "never back to running");
  const open = applyTool(s, parseToolEvent({ ...RUNNING, id: "tc-2", step: "open_case" }) as ToolEvent);
  assert.deepEqual(
    settleTools(open.tools).map((t) => t.status),
    ["done", "failed"],
    "a call with no result when the turn ends is failed, never done",
  );
});

test("spec 07 AC-12, spec 01 AC-10: text chunks build the reply; a line with a digit arrives whole", () => {
  const reply = "Listo, Ana.\nTu caso K-0001 quedó abierto.\nUna persona lo revisa.";
  const chunks = textChunks(reply, "m1");
  for (const c of chunks) {
    const delta = String(c.data.delta);
    if (/\d/.test(delta)) assert.ok(delta.startsWith("Tu caso K-0001 quedó abierto."), `a digit line is released whole: ${delta}`);
  }
  let s = EMPTY_STREAM;
  for (const c of chunks) s = applyText(s, parseTextChunk(c.data) as TextChunk);
  assert.equal(s.text, reply);
  assert.equal(applyText(s, { message_id: "m2", delta: "Otra" }).text, "Otra", "another message starts over");
});

test("spec 07 AC-12: a markdown mark still being typed is held back while streaming", () => {
  assert.equal(stableMarkdown("Tu tarjeta está **bloq"), "Tu tarjeta está ");
  assert.equal(stableMarkdown("Tu tarjeta está **bloqueada**"), "Tu tarjeta está **bloqueada**");
  assert.equal(stableMarkdown("ver `get_ca"), "ver ");
  assert.equal(stableMarkdown("un *énfa"), "un ");
  assert.equal(stableMarkdown("* uno\n* do"), "* uno\n* do", "a bullet is not an open mark");
  assert.equal(stableMarkdown("lee [la fuente](https://ban"), "lee ");
  assert.equal(stableMarkdown("a [b] c"), "a [b] c");
});

test("spec 07 AC-14: no bracket labels and no raw URL on customer screens", () => {
  assert.equal(customerText("Cargo de prueba [simulated] registrado"), "Cargo de prueba registrado");
  assert.equal(customerText("Cifra [data] y [assumption]."), "Cifra y.");
  const line = fill(MESSAGES.receipt.credit_deadline, "es", {
    credit_deadline: "2026-06-03",
    deadline_source: "Banxico 3/2012",
    source_url: "https://www.banxico.org.mx/circular.pdf",
    verified_on: "2026-10-01",
  });
  const shown = customerText(line);
  assert.ok(!/https?:\/\//.test(shown), shown);
  assert.ok(shown.includes("verificada el 2026-10-01"), shown);
});

test("spec 07 AC-13, spec 04 AC-20, AC-39: chips are at most 3 and always include a person", () => {
  const person = MESSAGES.suggest.talk_to_person.es;
  const row: Suggestion[] = [
    { label: "Sí, bloquear", text: "Sí" },
    { label: "No", text: "No" },
    { label: "Ver mi caso [simulated]", text: "caso" },
    { label: "Otro", text: "otro" },
  ];
  const chips = chipsFor(row, "es");
  assert.ok(chips.length <= 3);
  assert.ok(chips.some((c) => c.label === person && c.action?.type === "request_call"));
  assert.ok(chips.every((c) => !c.label.includes("[")), "no bracket tag on a chip");
  for (const lang of ["es", "pt"] as const) {
    assert.ok(chipsFor(undefined, lang).some((c) => c.label === MESSAGES.suggest.talk_to_person[lang]), `${lang}: empty row`);
  }
  const already = chipsFor([{ label: "Llamar", text: "", action: { type: "request_call" } }, { label: "No", text: "No" }], "es");
  assert.equal(already.length, 2, "a person chip already there is not added twice");
});

const RECEIPT: Receipt = {
  case_id: "K-0001",
  language: "es",
  issued_at: "2026-10-06T00:04:23.618792Z",
  title: "Comprobante de tu caso K-0001",
  card_blocked: null,
  deadline: { country: "MX", product: "debit", creditDeadline: "2026-06-03", deadlineSource: "Banxico 3/2012", daysLeft: null },
  deadline_text: "Plazo legal del banco para pronunciarse sobre los fondos en disputa: 2026-06-03. Fuente: Banxico 3/2012 (https://www.banxico.org.mx/c.pdf, verificada el 2026-10-01).",
  what_ai_did: "Bloqueé tu tarjeta y abrí tu caso.",
  what_a_person_does: "Una persona revisa tu caso.",
  case_url: "/case/K-0001",
  facts: ["Cargo reportado: ELECTRO MUNDO, 4200 MXN."],
  source: { label: "Banxico, Circular 3/2012", url: "https://www.banxico.org.mx/c.pdf", verified_on: "2026-10-01" },
};

test("spec 07 AC-14 (design pass 1, finding 1): beside a receipt, the reply does not repeat the deadlines, their sources or a raw URL", () => {
  const reply = [RECEIPT.what_ai_did, RECEIPT.deadline_text, "Plazo legal del banco para resolver tu caso: 2026-07-16. Fuente: X (https://x.org, verificada el 2026-10-01).", "Sigue tu caso en /case/K-0001"].join("\n");
  const body = replyBody(reply, RECEIPT, "es");
  assert.equal(body, RECEIPT.what_ai_did);
  assert.ok(!body.includes("Plazo legal"));
  assert.ok(replyBody(RECEIPT.deadline_text, RECEIPT, "es").length > 0, "never an empty bubble: it points at the card");
  assert.equal(replyBody("Hola [simulated]", undefined, "es"), "Hola", "without a receipt only the labels go");
});

test("spec 07 AC-14 (design pass 1, finding 3): times in the session language, 24 h, in the case's zone; dates without a zone shift", () => {
  const es = formatTimestamp(RECEIPT.issued_at, "es", "MX");
  assert.match(es, /5 oct/, es); // 00:04 UTC on Oct 6 is Oct 5 in Mexico City
  assert.match(es, /18:04/, es);
  assert.ok(!es.includes("T00:04"), es);
  const pt = formatTimestamp(RECEIPT.issued_at, "pt", "BR");
  assert.match(pt, /21:04/, pt);
  assert.match(formatDate("2026-06-03", "es"), /3 de junio de 2026/);
  assert.match(formatDate("2026-06-03", "pt"), /3 de junho de 2026/);
  const line = localizeTimes("Tarjeta terminada en 4417: bloqueada y verificada (verificación V-1, 2026-10-06T00:04:23Z).", "es", "MX");
  assert.ok(!/\d{4}-\d{2}-\d{2}T/.test(line), line);
});

test("spec 07 AC-14 (design pass 1, finding 4): a trace row leads with words, not a node key", () => {
  assert.deepEqual(traceRow({ step: "reading_message", result: "Leyendo tu mensaje…", kind: "ok" }), { title: "Leyendo tu mensaje…", detail: null });
  assert.deepEqual(traceRow({ step: "block_card", result: "verified · V-1", kind: "verified" }), { title: "Block the card", detail: "verified · V-1" });
  assert.equal(traceRow({ step: "deciding", result: "", kind: "ok" }).title, "deciding");
});

test("spec 07 AC-11, spec 01 §6.4.1: the mock stream follows the contract exactly and goes through the live parsers", async () => {
  const store = new MockStore(null, () => Date.parse("2026-06-03T15:00:00Z"));
  const api = createApi(store, { delayMs: 0 });
  store.requestOtp("demo-ana");
  store.verifyOtp(store.getState().pendingOtp!.otp);
  const tools: ToolEvent[] = [];
  const chunks: TextChunk[] = [];
  const reply = await api.chat("No reconozco un cargo de 4,200 pesos", { onTool: (t) => tools.push(t), onText: (c) => chunks.push(c) });
  assert.ok(reply.receipt, "the high zone opens a case");
  const ids = new Set(tools.map((t) => t.id));
  for (const id of ids) {
    const seq = tools.filter((t) => t.id === id).map((t) => t.status);
    assert.deepEqual(seq, ["running", "done"], id);
  }
  assert.ok(reply.tools?.every((t) => t.status === "done"));
  const steps = [...new Set(tools.map((t) => t.step))];
  assert.deepEqual(steps, ["search_transaction", "evaluate_policy", "block_card", "open_case", "get_case", "compute_deadline"]);
  const verified = reply.tools?.flatMap((t) => t.cards).filter((c) => c.type === "action" && c.state === "verified") ?? [];
  assert.ok(verified.length >= 2 && verified.every((c) => c.type === "action" && c.verification_id?.startsWith("V-")));
  assert.equal(chunks.map((c) => c.delta).join(""), reply.text, "the streamed text is the reply");
  for (const e of mockTurnEvents(reply, { language: "es", last4: "4417", country: "MX", today: "2026-06-03" }, 1)) {
    assert.ok(e.data.kind === e.event, "every chunk carries its kind");
    assert.equal(JSON.stringify(e).match(/score|zone|POL-/i), null, "no score, zone or policy id");
  }
});

test("spec 07 AC-12, spec 01 AC-09, spec 07 AC-08: the live client forwards tool and text events and keeps the settled tools", async () => {
  const body = [
    ["progress", { step: "reading_message", label: "Leyendo tu mensaje…", state: "in_progress" }],
    ["tool", RUNNING],
    ["text", { kind: "text", message_id: "m1", delta: "Listo." }],
    ["tool", DONE],
    ["tool", { kind: "tool", id: "x", step: "open_case", title: "Abriendo", status: "maybe", cards: [], at: "t" }],
    ["values", { secret: true }],
    ["turn", { reply: "Listo.", language: "es", suggestions: [], plan: ["1. Bloquear tu tarjeta"] }],
  ]
    .map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`)
    .join("");
  const fetchImpl = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/api/demo/customers")) return new Response("[]", { status: 200 });
    if (url.endsWith("/api/sessions")) return new Response(JSON.stringify({ session_id: "s1", otp_demo: "123456" }), { status: 200 });
    if (url.endsWith("/verify")) return new Response(JSON.stringify({ expires_at: "2026-10-05T16:00:00Z" }), { status: 200 });
    if (url.endsWith("/api/agent/threads")) return new Response(JSON.stringify({ thread_id: "t1" }), { status: 200 });
    if (url.endsWith("/runs/stream")) return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
    return new Response("{}", { status: 404 });
  }) as typeof fetch;
  const data = new Map<string, string>();
  const api = createLiveApi({
    fetch: fetchImpl,
    baseUrl: "http://api.test",
    storage: { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v), removeItem: (k) => void data.delete(k) },
    now: () => Date.parse("2026-10-05T15:00:00Z"),
    cognito: null,
  });
  await api.requestOtp("demo-ana");
  await api.verifyOtp("123456");
  const tools: ToolEvent[] = [];
  const text: TextChunk[] = [];
  const reply = await api.chat("No reconozco un cargo", { onTool: (t) => tools.push(t), onText: (c) => text.push(c) });
  assert.deepEqual(tools.map((t) => t.status), ["running", "done"], "the malformed tool event is dropped");
  assert.deepEqual(text, [{ message_id: "m1", delta: "Listo." }]);
  assert.equal(reply.text, "Listo.", "turn.reply replaces the streamed text");
  assert.deepEqual(reply.tools?.map((t) => t.status), ["done"]);
  assert.deepEqual(reply.plan, ["1. Bloquear tu tarjeta"]);
});
