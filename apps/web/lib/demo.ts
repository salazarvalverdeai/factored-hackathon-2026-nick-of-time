// Pure helpers of the demo-mode start screen (spec 07 §8, D-068, ADR 0026). No fetch, no React: tested in lib/demo.test.ts.
import type { Language, PersonaCharacter, RecentTransaction } from "./types.ts";

export const MAX_NAME_LENGTH = 40;
export const COUNTRIES = ["MX", "CO", "AR"] as const;

export const PERSONAS: { id: PersonaCharacter; label: string }[] = [
  { id: "aggressive", label: "Aggressive" },
  { id: "passive", label: "Passive" },
  { id: "terse", label: "Terse" },
  { id: "verbose", label: "Verbose" },
  { id: "confused", label: "Confused" },
  { id: "code_switching", label: "Code-switching ES/PT" },
];

/**
 * The customer-facing copy of the identity step (lead decision 5, 2026-10-05): plain sentences, no bracket tags.
 * The intro says once that the customers are synthetic examples; the OTP line says where a real code would come from.
 */
export const VERIFY_COPY = {
  es: {
    intro: "Demo con datos sintéticos del hackathon: elige un cliente de ejemplo.",
    who: "1 · ¿Quién eres?",
    code: (otp: string) => `Tu código es ${otp}. En un banco real llegaría por SMS.`,
  },
  pt: {
    intro: "Demo com dados sintéticos do hackathon: escolha um cliente de exemplo.",
    who: "1 · Quem é você?",
    code: (otp: string) => `Seu código é ${otp}. Em um banco real, chegaria por SMS.`,
  },
} as const;

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
export function nameProblem(raw: string): string | null {
  const name = raw.trim();
  if (name.length === 0) return null;
  if (name.length > MAX_NAME_LENGTH) return `At most ${MAX_NAME_LENGTH} characters.`;
  if (/\d/.test(name)) return "Letters only: no digits.";
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

/** The chip's visible label: short, with the `[simulated]` label on a test charge. */
export function chipLabel(tx: RecentTransaction): string {
  return `${tx.date} · ${tx.amount.toFixed(2)} ${tx.currency}${tx.merchant ? ` · ${tx.merchant}` : ""}${tx.synthetic ? " [simulated]" : ""}`;
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
