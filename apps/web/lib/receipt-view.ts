// What the verified receipt shows and copies (spec 07 AC-02, AC-19 to AC-21): the deadline as the hero with a business-day
// countdown, the facts the card does not already carry, and a plain-text copy. Pure helpers, tested offline
// (lib/receipt-view.test.ts). "Today" is the demo date in replay and the receipt's own issue date in live mode: never the
// system clock (ADR 0020).
import { formatDate, zoneFor } from "./chat-stream.ts";
import { CHAT_STRINGS } from "./chat-strings.ts";
import { withoutWallClock } from "./demo-date.ts";
import { MESSAGES } from "./mock/messages.ts";
import type { Language, Receipt } from "./types.ts";

const ymd = (iso: string) => /^\d{4}-\d{2}-\d{2}$/.test(iso);

/**
 * Business days from `from` (exclusive) to `to` (inclusive), weekends skipped: Monday 1 June 2026 → Wednesday 3 June is
 * 2. Bank holidays are the policy engine's (spec 02); the server's own count wins when it sends one. Negative when past.
 */
export function businessDaysBetween(from: string, to: string): number | null {
  if (!ymd(from) || !ymd(to)) return null;
  const a = Date.parse(`${from}T00:00:00Z`);
  const b = Date.parse(`${to}T00:00:00Z`);
  const sign = b >= a ? 1 : -1;
  let n = 0;
  for (let t = a + sign * 86_400_000; sign > 0 ? t <= b : t >= b; t += sign * 86_400_000) {
    const wd = new Date(t).getUTCDay();
    if (wd !== 0 && wd !== 6) n += sign;
  }
  return n;
}

/** "faltan 2 días hábiles" (es) / "faltam 2 dias úteis" (pt); "vence hoy" / "vence hoje"; "venció" / "venceu". */
export function countdownWords(n: number, lang: Language): string {
  if (lang === "pt") {
    if (n < 0) return "prazo vencido";
    if (n === 0) return "vence hoje";
    return n === 1 ? "falta 1 dia útil" : `faltam ${n} dias úteis`;
  }
  if (n < 0) return "plazo vencido";
  if (n === 0) return "vence hoy";
  return n === 1 ? "falta 1 día hábil" : `faltan ${n} días hábiles`;
}

/** The receipt's "today": the demo date in replay, else the issue date in the case's country (an api fact, not our clock). */
export function receiptToday(receipt: Pick<Receipt, "issued_at" | "language" | "deadline">, demoDate: string | null | undefined, country?: string): string | null {
  if (demoDate && ymd(demoDate)) return demoDate;
  const t = Date.parse(receipt.issued_at);
  if (Number.isNaN(t)) return null;
  // en-CA writes dates as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", { timeZone: zoneFor(receipt.deadline.country || country, receipt.language) }).format(t);
}

export interface DeadlineHero {
  kind: "credit" | "ruling";
  label: string;
  date: string;
  /** Business days left from "today", or null when today is unknown. */
  left: number | null;
  /** The ruling date shown under a credit hero ("luego, resolución a más tardar el …"). */
  then: string | null;
}

/** The words before the colon of a deadline template: "Plazo legal del banco para pronunciarse sobre los fondos". */
const head = (m: { es: string; pt: string }, lang: Language) => m[lang].split(":")[0].trim();

/** The deadline the receipt leads with: the credit date when there is one, else the ruling date; null when none. */
export function deadlineHero(receipt: Receipt, today: string | null): DeadlineHero | null {
  const lang = receipt.language;
  const credit = receipt.deadline.creditDeadline;
  const ruling = receipt.ruling_deadline ?? receipt.deadline.rulingDeadline ?? null;
  const date = credit ?? ruling;
  if (!date) return null;
  const kind = credit ? "credit" : "ruling";
  const label = head(kind === "credit" ? MESSAGES.receipt.credit_deadline : MESSAGES.receipt.ruling_deadline, lang);
  return { kind, label, date, left: today ? businessDaysBetween(today, date) : null, then: credit && ruling ? ruling : null };
}

/** `contracts/messages.yaml` `act.case_opened` (not in the generated mock texts; lib/receipt-view.test.ts checks the copy). */
export const CASE_OPENED: Record<Language, string> = {
  es: "Caso {case_id} abierto y verificado (verificación {verification_id}, {verified_at}).",
  pt: "Caso {case_id} aberto e verificado (verificação {verification_id}, {verified_at}).",
};

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** A message template as a pattern: each `{field}` matches anything. */
function templatePattern(template: string): RegExp {
  return new RegExp(`^${template.split(/\{[a-z_]+\}/).map(escape).join(".*?")}$`);
}

/**
 * The receipt facts the card shows as bullets: not the deadline lines (the hero carries them), not a raw URL, not the
 * card-blocked line, and not the "case opened and verified" line nor any fact naming a V- id the Actions rows already
 * list (design pass 2: the duplicated bullet).
 */
export function receiptFacts(receipt: Receipt): string[] {
  const lang = receipt.language;
  const heads = [MESSAGES.receipt.credit_deadline, MESSAGES.receipt.ruling_deadline].map((m) => head(m, lang));
  const caseOpened = [templatePattern(CASE_OPENED.es), templatePattern(CASE_OPENED.pt)];
  const ids = (receipt.actions ?? []).map((a) => a.verification_id).filter((v): v is string => Boolean(v));
  return (receipt.facts ?? []).filter((f) => {
    const l = f.trim();
    if (!l || /https?:\/\//.test(l) || heads.some((h) => l.startsWith(h)) || l === receipt.card_blocked) return false;
    if (caseOpened.some((re) => re.test(l))) return false;
    return !ids.some((id) => l.includes(id));
  });
}

/**
 * A receipt line as a replay session shows it: the real-clock instant of a tool text is dropped (it means nothing next
 * to the demo date, ADR 0020), and a parenthesis it left open is closed again. Live lines are kept as they are.
 */
export function replayText(text: string, replay: boolean): string {
  if (!replay) return text;
  let out = withoutWallClock(text);
  const open = (out.match(/\(/g) ?? []).length - (out.match(/\)/g) ?? []).length;
  if (open > 0) out = out.replace(/([.;:]?)$/, `${")".repeat(open)}$1`);
  return out;
}

const STATE: Record<string, Record<Language, string>> = {
  verified: { es: "verificado", pt: "verificado" },
  requested: { es: "solicitado", pt: "solicitado" },
  in_progress: { es: "en curso", pt: "em andamento" },
  not_confirmed: { es: "no confirmado", pt: "não confirmado" },
};

export function stateWord(state: string, lang: Language): string {
  return STATE[state]?.[lang] ?? state.replaceAll("_", " ");
}

/**
 * The receipt as plain text for the clipboard: the same verified facts the card shows, no markdown, no score, zone or
 * policy id. `origin` makes the case link absolute when the page knows its host.
 */
export function receiptPlainText(receipt: Receipt, options: { today: string | null; demoDate?: string | null; origin?: string } = { today: null }): string {
  const lang = receipt.language;
  const s = CHAT_STRINGS;
  const hero = deadlineHero(receipt, options.today);
  const lines: string[] = [`${s.receipt[lang]} · ${s.caseWord[lang]} ${receipt.case_id} · ${s.verified[lang]}`];
  if (hero) {
    lines.push(`${hero.label}: ${formatDate(hero.date, lang)}${hero.left !== null ? ` (${countdownWords(hero.left, lang)})` : ""}`);
    if (hero.then) lines.push(`${s.then[lang]} ${formatDate(hero.then, lang)}`);
  } else lines.push(receipt.deadline_text);
  const replay = Boolean(options.demoDate);
  if (receipt.card_blocked) lines.push(replayText(receipt.card_blocked, replay));
  for (const f of receiptFacts(receipt)) lines.push(`- ${replayText(f, replay)}`);
  for (const a of receipt.actions ?? []) lines.push(`- ${replayText(a.label, replay)}: ${stateWord(a.state, lang)}${a.verification_id ? ` (${a.verification_id})` : ""}`);
  lines.push(receipt.what_ai_did, receipt.what_a_person_does);
  if (receipt.source) lines.push(`${s.source[lang]}: ${receipt.source.label}${receipt.source.url ? ` (${receipt.source.url})` : ""}`);
  if (options.demoDate) lines.push(`${lang === "pt" ? "Data da demo" : "Fecha de la demo"}: ${formatDate(options.demoDate, lang)}`);
  lines.push(`${s.viewCase[lang]}: ${(options.origin ?? "") + receipt.case_url}`);
  return lines.filter((l) => l && l.trim()).join("\n");
}
