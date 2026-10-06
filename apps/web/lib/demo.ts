// Pure helpers of the demo-mode start screen (spec 07 §8, D-068, ADR 0026). No fetch, no React: tested in lib/demo.test.ts.
import { type Locale, translator } from "./i18n.ts";
import type { Language, PersonaCharacter, RecentTransaction } from "./types.ts";

export const MAX_NAME_LENGTH = 40;
export const COUNTRIES = ["MX", "CO", "AR"] as const;

/** The six characters of demo type D; their names are UI strings (`chat.tools.personas` in messages/chat.ts). */
export const PERSONAS: { id: PersonaCharacter }[] = [
  { id: "aggressive" },
  { id: "passive" },
  { id: "terse" },
  { id: "verbose" },
  { id: "confused" },
  { id: "code_switching" },
];

// The identity step's copy (lead decision 5, 2026-10-05: plain sentences, no bracket tags; the intro says once that
// the customers are synthetic examples; the OTP line says where a real code would come from) is chrome of the page:
// `chat.verify` in messages/chat.ts, in the UI locale (spec 16 AC-06).

/**
 * Telegram and e-mail are off in a demo session (spec 07 §8, spec 05 AC-16: the link routes answer 403). Every session
 * of the live api is a demo run (ADR 0026), so the case page offers the channel links only on the mock.
 */
export function channelLinksOffered(apiMode: "mock" | "live"): boolean {
  return apiMode === "mock";
}

/**
 * A hint before the request, never the rule: the api checks the name (spec 05 AC-14) and its 422 message is what is shown.
 * Returns null when the name looks fine (or is empty: the field is optional), else why it will be refused.
 */
export function nameProblem(raw: string, locale: Locale = "en"): string | null {
  const name = raw.trim();
  if (name.length === 0) return null;
  const t = translator(locale);
  if (name.length > MAX_NAME_LENGTH) return t("chat.start.nameTooLong", { max: MAX_NAME_LENGTH });
  if (/\d/.test(name)) return t("chat.start.nameDigits");
  return null;
}

/** The name the request carries: trimmed, or absent when empty (so the agent greets with gold's first name). */
export function nameToSend(raw: string): string | undefined {
  const name = raw.trim();
  return name.length > 0 ? name : undefined;
}

/**
 * The message a transaction chip sends (spec 07 §8.6): the date, the amount with its currency and the merchant. When
 * `merchant` is null it names only the date and the amount; when the customer has more than one card it adds the
 * card's last 4. Customer-facing text, so Spanish or Portuguese; not in contracts/messages.yaml (LOCAL, like the refusal).
 */
export function chipMessage(tx: RecentTransaction, lang: Language, multipleCards: boolean): string {
  const amount = tx.amount.toLocaleString(lang === "es" ? "es-MX" : "pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const merchant = tx.merchant?.trim();
  const card = multipleCards && tx.last4;
  if (lang === "es") {
    return `No reconozco el cargo del ${tx.date} de ${amount} ${tx.currency}${merchant ? ` en ${merchant}` : ""}${card ? ` de la tarjeta terminada en ${tx.last4}` : ""}.`;
  }
  return `Não reconheço a cobrança de ${tx.date} de ${amount} ${tx.currency}${merchant ? ` em ${merchant}` : ""}${card ? ` do cartão com final ${tx.last4}` : ""}.`;
}

/** The chip's visible label: short; a test charge says so in plain words in the UI locale, never a bracket label (spec 07 AC-14). */
export function chipLabel(tx: RecentTransaction, locale: Locale = "en"): string {
  const test = tx.synthetic ? ` · ${translator(locale)("chat.tools.testChargeTag")}` : "";
  return `${tx.date} · ${tx.amount.toFixed(2)} ${tx.currency}${tx.merchant ? ` · ${tx.merchant}` : ""}${test}`;
}

/** Does the customer have more than one card among these charges? */
export function hasSeveralCards(txs: RecentTransaction[]): boolean {
  return new Set(txs.map((t) => t.last4).filter(Boolean)).size > 1;
}

/** Test-charge amount from the form's text ("1,250.50" or "1250.5"); null when it is not a positive number. */
export function parseAmount(raw: string): number | null {
  const n = Number(raw.trim().replace(/,/g, ""));
  return Number.isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : null;
}
