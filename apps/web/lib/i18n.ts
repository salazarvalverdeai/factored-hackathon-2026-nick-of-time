// The web UI's languages (spec 16 AC-06): ES, PT and EN, picked in the site header and kept in a cookie. English is the
// source of the keys (`messages/en.ts`); Spanish and Portuguese must carry every key (the `Messages` type and
// `lib/i18n.test.ts`). The agent still converses in ES or PT only (spec 04): customer-facing agent text, receipts and
// notifications are never translated here. Isomorphic: imported by server and client components and by node tests.
import { en } from "../messages/en.ts";
import { es } from "../messages/es.ts";
import { pt } from "../messages/pt.ts";

export const LOCALES = ["es", "pt", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
/** The cookie the header selector writes and the root layout reads (one year, path /, SameSite=Lax). */
export const LOCALE_COOKIE = "not_locale";
export const LOCALE_MAX_AGE = 60 * 60 * 24 * 365;

/** BCP 47 tag for dates and numbers (24 h everywhere). */
export const INTL_LOCALE: Record<Locale, string> = { es: "es-MX", pt: "pt-BR", en: "en-US" };
/** Each language's name in itself, for the selector's accessible names. */
export const LOCALE_NAMES: Record<Locale, string> = { es: "Español", pt: "Português", en: "English" };

/** A dictionary has the shape of the English one, with every leaf a string. */
type Widen<T> = { [K in keyof T]: T[K] extends string ? string : Widen<T[K]> };
export type Messages = Widen<typeof en>;

type Leaves<T, P extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : Leaves<T[K], `${P}${K}.`>;
}[keyof T & string];
/** Every key, as a dot path ("header.nav.chat"). */
export type MessageKey = Leaves<typeof en>;
export type Vars = Record<string, string | number>;
export type Translate = (key: MessageKey, vars?: Vars) => string;

export const DICTIONARIES: Record<Locale, Messages> = { en, es, pt };

export function isLocale(v: unknown): v is Locale {
  return typeof v === "string" && (LOCALES as readonly string[]).includes(v);
}

/** A cookie value as a locale; anything else is the default (EN). */
export function parseLocale(v: string | null | undefined): Locale {
  return isLocale(v) ? v : DEFAULT_LOCALE;
}

function lookup(dict: object, key: string): string | undefined {
  let node: unknown = dict;
  for (const part of key.split(".")) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

/** "{name}" placeholders filled from `vars`; an unknown placeholder stays as written. */
export function interpolate(text: string, vars?: Vars): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** The translate function for a locale. A key missing at run time falls back to English, then to the key itself. */
export function translator(locale: Locale): Translate {
  const dict = DICTIONARIES[locale];
  return (key, vars) => interpolate(lookup(dict, key) ?? lookup(en, key) ?? key, vars);
}

/** Every leaf key of a dictionary, as dot paths (for the completeness test). */
export function keysOf(dict: object, prefix = ""): string[] {
  return Object.entries(dict).flatMap(([k, v]) =>
    typeof v === "string" ? [`${prefix}${k}`] : keysOf(v as object, `${prefix}${k}.`),
  );
}

/** Numbers per locale ("1,234.5" en-US and es-MX, "1.234,5" pt-BR). */
export function formatNumber(locale: Locale, n: number, opts?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(INTL_LOCALE[locale], opts).format(n);
}

/** Date and time per locale, always on a 24 h clock. */
export function formatDateTime(locale: Locale, d: Date | string, opts?: Intl.DateTimeFormatOptions): string {
  const date = typeof d === "string" ? new Date(d) : d;
  return new Intl.DateTimeFormat(INTL_LOCALE[locale], { ...opts, hourCycle: "h23" }).format(date);
}

/** A raw `YYYY-MM-DD` day per locale ("5 oct 2026"), read as a calendar day (UTC noon, no zone shift). */
export function formatDay(locale: Locale, day: string, opts?: Intl.DateTimeFormatOptions): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return day;
  const fmt = new Intl.DateTimeFormat(INTL_LOCALE[locale], { day: "numeric", month: "short", year: "numeric", timeZone: "UTC", ...opts });
  return fmt.format(new Date(`${day}T12:00:00Z`));
}
