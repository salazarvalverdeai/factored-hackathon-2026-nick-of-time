// Offline checks for the reply as the chat renders it (spec 07 AC-28 to AC-30, production fixes of the recomposed
// chat): the charge to confirm of D-067 is a card, text after a list is its own paragraph, ISO dates in long form.
// Each test cites the criterion it covers. No network, no LLM.
import assert from "node:assert/strict";
import test from "node:test";
import { fromMarkdown } from "mdast-util-from-markdown";
import { citeFigures, displayText, formatDate, localizeDates, offeredCharges, parseToolEvent, replyBody, separateLists } from "./chat-stream.ts";
import type { ToolEvent } from "./chat-stream.ts";
import { revealMarkdown, wordCount } from "./chat-reveal.ts";
import { replyFromTurn } from "./live.ts";
import { MESSAGES, fill } from "./mock/messages.ts";

const SEARCH = parseToolEvent({
  kind: "tool",
  id: "run-1:search_transaction",
  step: "search_transaction",
  title: "Buscando el cargo",
  status: "done",
  summary: "Encontré un cargo.",
  cards: [{ type: "charge", transaction_id: "TRX-000123", date: "2026-05-31", amount: 1250, currency: "USD", merchant: "TIENDA X", last4: "4417", synthetic: false }],
  at: "2026-06-01T15:00:04Z",
}) as ToolEvent;

// A D-067 turn as the api sends it (CustomerTurn, spec 01 §6.4): one option, the confirm_charge chips.
const CONFIRM_ONE = {
  reply: "¿Es este el cargo que quieres reportar? Aún no hice ningún cambio.",
  language: "es" as const,
  decision: "ask",
  options: [{ id: "TRX-000123", label: "USD 1,250.00 · 2026-05-31 · TIENDA X" }],
  suggestions: [
    { id: "confirm_charge_yes", label: "Sí, es ese cargo", kind: "action" as const, action: { type: "choose_option" as const, value: "TRX-000123" } },
    { id: "confirm_charge_no", label: "No es ese cargo", kind: "action" as const, action: { type: "choose_option" as const, value: "none" } },
    { id: "talk_to_person", label: "Hablar con una persona", kind: "action" as const, action: { type: "request_call" as const } },
  ],
};

test("spec 07 AC-28: a confirm_one turn (D-067) renders exactly one charge card, the tool's card of that transaction", () => {
  const reply = replyFromTurn(CONFIRM_ONE);
  assert.deepEqual(reply.options, CONFIRM_ONE.options, "the live client keeps the turn's options");
  const cards = offeredCharges(reply.options, [SEARCH]);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].id, "TRX-000123");
  assert.equal(cards[0].card?.merchant, "TIENDA X", "the tool's card when the turn streamed it");
  // No tool event reached the browser (the stream was not relayed): the option's own label still makes the card.
  const bare = offeredCharges(reply.options, []);
  assert.equal(bare.length, 1);
  assert.equal(bare[0].card, null);
  assert.equal(bare[0].label, CONFIRM_ONE.options[0].label);
});

test("spec 07 AC-28: several options are cards in the turn's order; a turn that offers none keeps its tools' charges", () => {
  const two = parseToolEvent({
    ...SEARCH,
    cards: [
      { type: "charge", transaction_id: "TRX-000123", date: "2026-05-31", amount: 1250, currency: "USD", merchant: "TIENDA X", last4: null },
      { type: "charge", transaction_id: "TRX-000456", date: "2026-05-30", amount: 80, currency: "USD", merchant: null, last4: null },
    ],
  }) as ToolEvent;
  assert.equal(two.cards.length, 2, "a candidate with a null last4 is kept, not dropped");
  const options = [
    { id: "TRX-000456", label: "USD 80.00 · 2026-05-30" },
    { id: "TRX-000123", label: "USD 1,250.00 · 2026-05-31 · TIENDA X" },
  ];
  assert.deepEqual(offeredCharges(options, [two]).map((o) => o.id), ["TRX-000456", "TRX-000123"]);
  assert.deepEqual(offeredCharges([], [SEARCH]).map((o) => o.id), ["TRX-000123"], "options: [] still shows the found charge");
  assert.deepEqual(offeredCharges(undefined, [SEARCH, SEARCH]).map((o) => o.id), ["TRX-000123"], "one card per transaction");
  assert.deepEqual(replyFromTurn({ ...CONFIRM_ONE, options: [] }).options, []);
});

/** The top-level blocks of a markdown text, as the chat's renderer parses them (mdast, CommonMark). */
const blocks = (md: string) => fromMarkdown(md).children.map((n) => n.type);

test("spec 07 AC-29: the line after the greeting's bullets is its own paragraph, never part of the last bullet", () => {
  const greet = MESSAGES.greet as Record<string, Record<"es" | "pt", string>>;
  for (const lang of ["es", "pt"] as const) {
    const text = [
      fill(MESSAGES.greet.hello, lang, { first_name: "Ana" }),
      greet.capability_1[lang],
      greet.capability_2[lang],
      greet.capability_3[lang],
      greet.human_review[lang],
      lang === "es" ? "Listo, registré tu solicitud." : "Pronto, registrei sua solicitação.",
    ].join("\n");
    assert.deepEqual(blocks(text).slice(-1), ["list"], `${lang}: the bug, as raw markdown parses it`);
    const shown = displayText(text, lang);
    assert.deepEqual(blocks(shown), ["paragraph", "list", "paragraph"], `${lang}: ${shown}`);
    const list = fromMarkdown(shown).children[1] as { children: unknown[] };
    assert.equal(list.children.length, 3, "three bullets, nothing swallowed");
    // Partial (revealed) text gets the same blocks once the line after the list shows.
    const words = wordCount(shown);
    assert.deepEqual(blocks(revealMarkdown(shown, words - 1)), ["paragraph", "list", "paragraph"]);
  }
  assert.equal(separateLists("1. Uno\n2. Dos\nTexto"), "1. Uno\n2. Dos\n\nTexto", "numbered plans too");
  assert.equal(separateLists("- Uno\n  sigue\n\nTexto"), "- Uno\n  sigue\n\nTexto", "an indented line stays in its item");
  assert.equal(separateLists("**Hola**\nlinea"), "**Hola**\nlinea", "bold is not a bullet");
});

test("spec 07 AC-30: ISO dates in the long form of the turn language; ids, instants and amounts untouched", () => {
  assert.equal(localizeDates("a más tardar el 2026-06-02.", "es"), "a más tardar el 2 de junio de 2026.");
  assert.equal(localizeDates("até 2026-06-02.", "pt"), "até 2 de junho de 2026.");
  assert.equal(formatDate("2026-03-01", "pt"), "1 de março de 2026");
  assert.equal(formatDate("2026-09-15", "es"), "15 de septiembre de 2026");
  assert.equal(formatDate("2026-02-30", "es"), "2026-02-30", "not a calendar date: left as it is");
  const kept = "Caso K-2026-06-02-01, TRX-2026-06-02, verificado V-1 2026-10-06T00:04:23Z, monto 2026.06 USD, /case/2026-06-02";
  assert.equal(localizeDates(kept, "es"), kept);
  const body = replyBody("Abrí tu caso K-0001. Plazo: 2026-06-02.", undefined, "es");
  assert.equal(body, "Abrí tu caso K-0001. Plazo: 2 de junio de 2026.");
});

test("spec 07 AC-30, AC-22: a localized date a tool returned still links to its source", () => {
  const deadline = parseToolEvent({
    kind: "tool",
    id: "run-1:compute_deadline",
    step: "compute_deadline",
    title: "Calculando tu plazo",
    status: "done",
    cards: [{ type: "deadline", kind: "credit", date: "2026-06-02", source_label: "Banxico 3/2012", source_url: null }],
    at: "2026-06-01T15:00:05Z",
  }) as ToolEvent;
  const shown = displayText("Te responderemos a más tardar el 2026-06-02.", "es");
  const cited = citeFigures(shown, [deadline], "es");
  assert.equal(cited, "Te responderemos a más tardar el [2 de junio de 2026](#cite-run-1%3Acompute_deadline).");
});
