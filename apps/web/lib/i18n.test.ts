// Offline checks for the UI languages (spec 16 AC-06). Run with `npm test`.
import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_LOCALE,
  DICTIONARIES,
  LOCALES,
  formatDateTime,
  formatDay,
  formatNumber,
  interpolate,
  keysOf,
  parseLocale,
  translator,
} from "./i18n.ts";

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
const leaf = (dict: object, key: string) => key.split(".").reduce<unknown>((n, k) => (n as Record<string, unknown>)[k], dict) as string;

test("spec 16 AC-06: every key of the English source exists in Spanish and Portuguese, and no locale has extra keys", () => {
  const source = keysOf(DICTIONARIES.en).sort();
  assert.ok(source.length > 50, "the dictionaries carry the UI strings");
  for (const loc of LOCALES) {
    const keys = keysOf(DICTIONARIES[loc]).sort();
    assert.deepEqual(
      source.filter((k) => !keys.includes(k)),
      [],
      `missing in ${loc}`,
    );
    assert.deepEqual(
      keys.filter((k) => !source.includes(k)),
      [],
      `extra in ${loc}`,
    );
  }
});

test("spec 16 AC-06: no translation is empty and each keeps the source's placeholders", () => {
  for (const loc of LOCALES) {
    for (const key of keysOf(DICTIONARIES.en)) {
      const text = leaf(DICTIONARIES[loc], key);
      assert.ok(text.trim().length > 0, `${loc}.${key} is empty`);
      assert.deepEqual(placeholders(text), placeholders(leaf(DICTIONARIES.en, key)), `${loc}.${key} placeholders`);
    }
  }
});

test("spec 16 AC-06: the cookie value picks the locale; anything else is English", () => {
  assert.equal(DEFAULT_LOCALE, "en");
  assert.equal(parseLocale("pt"), "pt");
  assert.equal(parseLocale("en"), "en");
  assert.equal(parseLocale(undefined), "en");
  assert.equal(parseLocale("fr"), "en");
  assert.equal(parseLocale("EN"), "en");
});

test("spec 16 AC-06: translate fills placeholders and follows the locale", () => {
  assert.equal(translator("en")("shell.nav.console"), "Console");
  assert.equal(translator("es")("shell.nav.console"), "Consola");
  assert.equal(translator("pt")("shell.language.current", { name: "Português" }), "Idioma: Português");
  assert.equal(interpolate("{a} of {b}", { a: 1 }), "1 of {b}");
});

test("spec 16 AC-06: dates and numbers follow es-MX, pt-BR and en-US on a 24 h clock", () => {
  const at = "2026-10-05T19:04:00Z";
  for (const loc of LOCALES) {
    const s = formatDateTime(loc, at, { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
    assert.match(s, /19:04/, `${loc}: ${s}`);
    assert.doesNotMatch(s, /PM|p\. ?m\./i);
  }
  assert.equal(formatNumber("en", 1234.5), "1,234.5");
  assert.equal(formatNumber("pt", 1234.5), "1.234,5");
  assert.match(formatDay("es", "2026-10-05"), /oct/);
  assert.match(formatDay("pt", "2026-10-05"), /out/);
  assert.match(formatDay("en", "2026-10-05"), /Oct/);
});
