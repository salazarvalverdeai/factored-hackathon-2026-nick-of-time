// Offline checks of the receipt card (spec 07 AC-19 to AC-21): deadline hero with a business-day countdown from the demo
// date, no duplicated bullet, plain-text copy. No network, no system clock.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parse } from "yaml";
import { CASE_OPENED, replayText, businessDaysBetween, countdownWords, deadlineHero, receiptFacts, receiptPlainText, receiptToday } from "./receipt-view.ts";
import type { Receipt } from "./types.ts";

const RECEIPT: Receipt = {
  case_id: "K-845156",
  language: "pt",
  issued_at: "2026-10-06T01:00:00Z",
  title: "Comprovante do caso K-845156",
  card_blocked: null,
  deadline: { country: "MX", product: "debit", creditDeadline: "2026-06-03", deadlineSource: "Banxico 3/2012", daysLeft: null },
  deadline_text: "",
  what_ai_did: "Abri seu caso e confirmei no sistema.",
  what_a_person_does: "Uma pessoa revisa seu caso.",
  case_url: "/case/K-845156",
  facts: [
    "Caso K-845156 aberto e verificado (verificação V-273C5CAD141B, 2026-10-06 01:00 UTC).",
    "Cobrança de USD 1,366.10 em 2026-05-26.",
    "Prazo legal do banco para se pronunciar sobre os valores: 2026-06-03 (https://www.banxico.org.mx/x.pdf).",
  ],
  actions: [{ label: "Abrir o caso", state: "verified", verification_id: "V-273C5CAD141B" }],
  source: { label: "Banxico, Circular 3/2012", url: "https://www.banxico.org.mx/x.pdf", verified_on: "2026-10-01" },
  ruling_deadline: "2026-07-16",
};

test("spec 07 AC-19: the hero counts business days to the deadline from the demo date, never the system clock", () => {
  assert.equal(businessDaysBetween("2026-06-01", "2026-06-03"), 2, "Monday 1 June → Wednesday 3 June");
  assert.equal(businessDaysBetween("2026-06-05", "2026-06-08"), 1, "Friday → Monday skips the weekend");
  assert.equal(businessDaysBetween("2026-06-03", "2026-06-03"), 0);
  assert.equal(businessDaysBetween("2026-06-03", "2026-06-01"), -2);
  assert.equal(businessDaysBetween("2026-06-01", "soon"), null);
  const today = receiptToday(RECEIPT, "2026-06-01");
  assert.equal(today, "2026-06-01", "replay: the demo date, not the issue instant");
  const hero = deadlineHero(RECEIPT, today);
  assert.equal(hero?.date, "2026-06-03");
  assert.equal(hero?.left, 2);
  assert.equal(hero?.then, "2026-07-16", "the ruling date follows the credit hero");
  assert.equal(countdownWords(2, "pt"), "faltam 2 dias úteis");
  assert.equal(countdownWords(2, "es"), "faltan 2 días hábiles");
  assert.equal(countdownWords(1, "es"), "falta 1 día hábil");
  assert.equal(countdownWords(0, "pt"), "vence hoje");
  // Live: the issue date in the case's zone (01:00 UTC on 6 Oct is still 5 Oct in Mexico City).
  assert.equal(receiptToday(RECEIPT, null), "2026-10-05");
  const rulingOnly = deadlineHero({ ...RECEIPT, deadline: { ...RECEIPT.deadline, creditDeadline: null } }, "2026-06-01");
  assert.equal(rulingOnly?.kind, "ruling");
  assert.equal(rulingOnly?.then, null);
  assert.equal(deadlineHero({ ...RECEIPT, deadline: { ...RECEIPT.deadline, creditDeadline: null }, ruling_deadline: null }, "2026-06-01"), null);
});

test("spec 07 AC-20: the case-opened line is not repeated as a bullet beside the Actions rows", () => {
  const facts = receiptFacts(RECEIPT);
  assert.deepEqual(facts, ["Cobrança de USD 1,366.10 em 2026-05-26."], "no case-opened bullet, no deadline line, no raw URL");
  const es = receiptFacts({ ...RECEIPT, language: "es", facts: ["Caso K-1 abierto y verificado (verificación V-9, 2026-10-06 01:00 UTC).", "Otro hecho."], actions: [] });
  assert.deepEqual(es, ["Otro hecho."], "the template matches without the Actions rows too");
  const yaml = parse(readFileSync(new URL("../../../contracts/messages.yaml", import.meta.url), "utf8"));
  assert.deepEqual(CASE_OPENED, { es: yaml.act.case_opened.es, pt: yaml.act.case_opened.pt }, "the copy matches contracts/messages.yaml");
});

test("spec 07 AC-21: the copied receipt is plain text with the verified facts and nothing the customer must not see", () => {
  const text = receiptPlainText(RECEIPT, { today: "2026-06-01", demoDate: "2026-06-01", origin: "https://chat.example" });
  assert.match(text, /^Comprovante · caso K-845156 · Verificado/);
  assert.match(text, /3 de junho de 2026 \(faltam 2 dias úteis\)/);
  assert.match(text, /- Abrir o caso: verificado \(V-273C5CAD141B\)/);
  assert.match(text, /Fonte: Banxico, Circular 3\/2012 \(https:\/\/www\.banxico\.org\.mx\/x\.pdf\)/);
  assert.match(text, /Data da demo: 1 de junho de 2026/);
  assert.match(text, /Ver meu caso: https:\/\/chat\.example\/case\/K-845156$/);
  assert.equal(text.match(/aberto e verificado/g), null, "no duplicated case line");
  assert.doesNotMatch(text, /\*\*|score|zona|zone|POL-/i);
});

test("spec 07 AC-14, AC-20: in replay a receipt line drops the real-clock instant and keeps its parentheses closed", () => {
  const line = "Tarjeta terminada en 4417: bloqueada y verificada (verificación V-1, 2026-10-05T19:39:00.000Z).";
  assert.equal(replayText(line, true), "Tarjeta terminada en 4417: bloqueada y verificada (verificación V-1).");
  assert.equal(replayText(line, false), line, "live keeps the instant (the page localizes it)");
  assert.equal(replayText("Sin hora.", true), "Sin hora.");
});
