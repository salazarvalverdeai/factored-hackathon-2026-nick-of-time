// Offline checks for the pure helpers of the demo start screen (spec 07 §8, D-068). Each test cites its criterion.
import assert from "node:assert/strict";
import test from "node:test";
import { PERSONAS, VERIFY_COPY, channelLinksOffered, chipLabel, chipMessage, hasSeveralCards, nameProblem, nameToSend, parseAmount } from "./demo.ts";
import type { RecentTransaction } from "./types.ts";

const TX: RecentTransaction = { transaction_id: "T-1", date: "2026-10-04", amount: 4200, currency: "MXN", merchant: "TIENDA X", last4: "4417", synthetic: false };

test("spec 07 §8.6: a chip names the date, the amount with its currency and the merchant", () => {
  assert.equal(chipMessage(TX, "es", false), "No reconozco el cargo del 2026-10-04 de 4,200.00 MXN en TIENDA X.");
  assert.equal(chipMessage(TX, "pt", false), "Não reconheço a cobrança de 2026-10-04 de 4.200,00 MXN em TIENDA X.");
});

test("spec 07 §8.6: a null merchant names only the date and the amount", () => {
  const es = chipMessage({ ...TX, merchant: null }, "es", false);
  assert.equal(es, "No reconozco el cargo del 2026-10-04 de 4,200.00 MXN.");
  assert.ok(!es.includes(" en "), "no merchant, no \"en\"");
  assert.equal(chipMessage({ ...TX, merchant: "  " }, "pt", false), "Não reconheço a cobrança de 2026-10-04 de 4.200,00 MXN.");
});

test("spec 07 §8.6: with more than one card the chip adds the card ending", () => {
  assert.match(chipMessage(TX, "es", true), /de la tarjeta terminada en 4417\.$/);
  assert.match(chipMessage(TX, "pt", true), /do cartão com final 4417\.$/);
  assert.ok(!chipMessage(TX, "es", false).includes("4417"), "a single card is not named");
  assert.ok(!chipMessage({ ...TX, last4: null }, "es", true).includes("tarjeta"), "no last4, no card clause");
});

test("spec 07 §8.6: several cards are detected from the charges", () => {
  assert.equal(hasSeveralCards([TX, { ...TX, transaction_id: "T-2" }]), false);
  assert.equal(hasSeveralCards([TX, { ...TX, transaction_id: "T-2", last4: "9999" }]), true);
  assert.equal(hasSeveralCards([{ ...TX, last4: null }]), false);
});

test("spec 07 §8.7, AC-14: a test charge's chip says so in plain words, with no bracket label", () => {
  assert.match(chipLabel({ ...TX, synthetic: true }), / · test charge$/);
  assert.ok(!chipLabel({ ...TX, synthetic: true }).includes("["));
  assert.ok(!chipLabel(TX).includes("test charge"));
  assert.equal(chipLabel({ ...TX, merchant: null }), "2026-10-04 · 4200.00 MXN");
});

test("spec 07 §8.1: the optional name is trimmed, absent when empty, and obviously bad names are flagged before the request", () => {
  assert.equal(nameToSend("  Ana María  "), "Ana María");
  assert.equal(nameToSend("   "), undefined);
  assert.equal(nameProblem(""), null);
  assert.equal(nameProblem("O'Brien-Núñez"), null);
  assert.match(nameProblem("a".repeat(41)) ?? "", /40/);
  assert.match(nameProblem("Ana 2") ?? "", /digits/);
});

test("spec 07 §8.7: the test-charge amount is a positive number with at most cents", () => {
  assert.equal(parseAmount("1,250.505"), 1250.51);
  assert.equal(parseAmount(" 99 "), 99);
  assert.equal(parseAmount("0"), null);
  assert.equal(parseAmount("-5"), null);
  assert.equal(parseAmount("abc"), null);
  assert.equal(parseAmount(""), null);
});

test("spec 07 §8.8: the six characters of demo type D are offered", () => {
  assert.deepEqual(PERSONAS.map((p) => p.id), ["aggressive", "passive", "terse", "verbose", "confused", "code_switching"]);
});

test("spec 07 §8 (lead decision 5): the identity step is plain ES/PT copy with no bracket tags, and the OTP line says SMS", () => {
  assert.equal(VERIFY_COPY.es.who, "1 · ¿Quién eres?");
  assert.equal(VERIFY_COPY.es.intro, "Demo con datos sintéticos del hackathon: elige un cliente de ejemplo.");
  assert.equal(VERIFY_COPY.es.code("094407"), "Tu código es 094407. En un banco real llegaría por SMS.");
  assert.equal(VERIFY_COPY.pt.code("123456"), "Seu código é 123456. Em um banco real, chegaria por SMS.");
  for (const lang of ["es", "pt"] as const) {
    const all = [VERIFY_COPY[lang].intro, VERIFY_COPY[lang].who, VERIFY_COPY[lang].code("1")].join(" ");
    assert.ok(!/\[(simulated|data|external|assumption|projected)\]/.test(all), lang);
  }
});

test("spec 07 §8, spec 05 AC-16: Telegram and e-mail links are offered in a live (demo) session too (ADR 0026 amended)", () => {
  assert.equal(channelLinksOffered("live"), true);
  assert.equal(channelLinksOffered("mock"), true);
});
