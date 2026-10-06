// The live stream events of the agentic chat (spec 01 §6.4.1, contract 1.8.0, ADR 0030) and the pure helpers the /chat
// components use to show them. Nothing here renders: it parses, folds and words, so every rule is tested offline
// (lib/chat-stream.test.ts). Customer text stays ES/PT; it never carries a score, zone, policy id or bracket label.
import { MESSAGES } from "./mock/messages.ts";
import type { Language, Receipt, Suggestion } from "./types.ts";

// --- contract shapes (spec 01 §6.4.1) ------------------------------------------------------------------------------

export type ToolStatus = "running" | "done" | "failed";
/** The four action states of spec 04 AC-18; `verified` only with a `V-` id (constitution #4). */
export type ActionState = "in_progress" | "requested" | "verified" | "not_confirmed";

export interface ChargeCard {
  type: "charge";
  transaction_id: string;
  date: string;
  amount: number;
  currency: string;
  merchant: string | null;
  last4: string;
  synthetic: boolean;
}
export interface VerdictCard {
  type: "verdict";
  headline: string;
  actions: string[];
}
export interface ActionCard {
  type: "action";
  tool: string;
  state: ActionState;
  verification_id: string | null;
}
export interface DeadlineCard {
  type: "deadline";
  kind: string;
  date: string | null;
  source_label: string;
  source_url: string | null;
}
export interface CaseCard {
  type: "case";
  case_id: string;
  status: string;
}
export type ToolCard = ChargeCard | VerdictCard | ActionCard | DeadlineCard | CaseCard;

/** `ToolEvent {id, step, title, status, summary?, cards[], at}`: `running` first, then exactly one `done` or `failed`. */
export interface ToolEvent {
  id: string;
  step: string;
  title: string;
  status: ToolStatus;
  summary?: string;
  cards: ToolCard[];
  at: string;
}

/** `TextChunk {message_id, delta}`: customer-visible text of the reply being written (writer `llm` only). */
export interface TextChunk {
  message_id: string;
  delta: string;
}

/** The `step` values of spec 01 §6.4.1. */
export const TOOL_STEPS = [
  "search_transaction",
  "list_recent_transactions",
  "evaluate_policy",
  "block_card",
  "open_case",
  "get_case",
  "compute_deadline",
  "request_call",
  "get_case_status",
] as const;

const ACTION_STATES: readonly string[] = ["in_progress", "requested", "verified", "not_confirmed"];
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): v is string => typeof v === "string";
const strOrNull = (v: unknown): v is string | null => v === null || typeof v === "string";

/** One card of a `done` event, or null when it does not follow the contract (a card is dropped, never guessed). */
export function parseCard(raw: unknown): ToolCard | null {
  if (!isObj(raw)) return null;
  switch (raw.type) {
    case "charge":
      if (!str(raw.transaction_id) || !str(raw.date) || typeof raw.amount !== "number" || !Number.isFinite(raw.amount)) return null;
      if (!str(raw.currency) || !strOrNull(raw.merchant ?? null) || !str(raw.last4)) return null;
      return {
        type: "charge",
        transaction_id: raw.transaction_id,
        date: raw.date,
        amount: raw.amount,
        currency: raw.currency,
        merchant: (raw.merchant as string | null | undefined) ?? null,
        last4: raw.last4,
        synthetic: raw.synthetic === true,
      };
    case "verdict":
      if (!str(raw.headline) || !Array.isArray(raw.actions) || !raw.actions.every(str)) return null;
      return { type: "verdict", headline: raw.headline, actions: raw.actions as string[] };
    case "action": {
      if (!str(raw.tool) || !str(raw.state) || !ACTION_STATES.includes(raw.state)) return null;
      const vid = str(raw.verification_id) ? raw.verification_id : null;
      // Constitution #4: "verified" needs a V- id read back from the system; without it the card says "requested".
      const state = raw.state === "verified" && !(vid && vid.startsWith("V-")) ? "requested" : (raw.state as ActionState);
      return { type: "action", tool: raw.tool, state, verification_id: vid };
    }
    case "deadline":
      if (!str(raw.kind) || !strOrNull(raw.date ?? null) || !str(raw.source_label)) return null;
      return {
        type: "deadline",
        kind: raw.kind,
        date: (raw.date as string | null | undefined) ?? null,
        source_label: raw.source_label,
        source_url: str(raw.source_url) && /^https:\/\//.test(raw.source_url) ? raw.source_url : null,
      };
    case "case":
      if (!str(raw.case_id) || !str(raw.status)) return null;
      return { type: "case", case_id: raw.case_id, status: raw.status };
    default:
      return null;
  }
}

/** A `tool` SSE event (spec 01 AC-09): the api may send the graph chunk with or without its `kind`. */
export function parseToolEvent(raw: unknown): ToolEvent | null {
  if (!isObj(raw)) return null;
  if (raw.kind !== undefined && raw.kind !== "tool") return null;
  if (!str(raw.id) || !str(raw.step) || !str(raw.title) || !str(raw.at)) return null;
  if (raw.status !== "running" && raw.status !== "done" && raw.status !== "failed") return null;
  // Cards come on `done` only (spec 01 §6.4.1).
  const cards = raw.status === "done" && Array.isArray(raw.cards) ? raw.cards.map(parseCard).filter((c): c is ToolCard => c !== null) : [];
  return {
    id: raw.id,
    step: raw.step,
    title: raw.title,
    status: raw.status,
    ...(str(raw.summary) && raw.summary ? { summary: raw.summary } : {}),
    cards,
    at: raw.at,
  };
}

/** A `text` SSE event: a chunk of the reply being written. */
export function parseTextChunk(raw: unknown): TextChunk | null {
  if (!isObj(raw)) return null;
  if (raw.kind !== undefined && raw.kind !== "text") return null;
  if (!str(raw.message_id) || !str(raw.delta)) return null;
  return { message_id: raw.message_id, delta: raw.delta };
}

// --- the running turn ------------------------------------------------------------------------------------------------

/** What the web shows while a turn runs: the tool calls in the order they started, and the reply being written. */
export interface TurnStream {
  tools: ToolEvent[];
  text: string;
  messageId: string | null;
}

export const EMPTY_STREAM: TurnStream = { tools: [], text: "", messageId: null };

/**
 * Folds one event into the turn. A `running` call is added once; its `done` or `failed` replaces it in place (same
 * `id`). A result never goes back to `running`, and a second result for the same id is ignored (spec 04 AC-38).
 */
export function applyTool(state: TurnStream, event: ToolEvent): TurnStream {
  const i = state.tools.findIndex((t) => t.id === event.id);
  if (i === -1) return { ...state, tools: [...state.tools, event] };
  if (state.tools[i].status !== "running" || event.status === "running") return state;
  const tools = state.tools.slice();
  tools[i] = event;
  return { ...state, tools };
}

/** Appends a text chunk; a chunk of another message starts that message over (one reply per turn). */
export function applyText(state: TurnStream, chunk: TextChunk): TurnStream {
  if (state.messageId !== null && state.messageId !== chunk.message_id) return { ...state, text: chunk.delta, messageId: chunk.message_id };
  return { ...state, text: state.text + chunk.delta, messageId: chunk.message_id };
}

/** Once the turn ends, a call still `running` did not report a result: it is shown as failed, never as done. */
export function settleTools(tools: readonly ToolEvent[]): ToolEvent[] {
  return tools.map((t) => (t.status === "running" ? { ...t, status: "failed" as const, cards: [] } : t));
}

/** The cards of a turn's tool calls, in order. */
export function cardsOf(tools: readonly ToolEvent[]): ToolCard[] {
  return tools.flatMap((t) => t.cards);
}

// --- customer text -----------------------------------------------------------------------------------------------

const BRACKET_TAG = /\s*\[(?:simulated|data|external|assumption|projected)\]/gi;
const RAW_URL = /https?:\/\/[^\s),]+/g;

/**
 * Text as a customer screen shows it: no bracket labels (`[simulated]`…, plan §5) and no raw URL (a source is a named
 * link on its card). A parenthesis left holding only the URL goes with it.
 */
export function customerText(text: string): string {
  return text
    .replace(BRACKET_TAG, "")
    .replace(/\(\s*https?:\/\/[^\s),]+\s*,\s*/g, "(")
    .replace(/\s*\(\s*https?:\/\/[^\s)]+\s*\)/g, "")
    .replace(RAW_URL, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/ +([.,;:])/g, "$1");
}

/**
 * While text streams, a markdown mark that is not closed yet (`**`, `*`, `` ` ``) is held back, so the customer never
 * sees half a mark (plan §3.3). The full reply then replaces the streamed text.
 */
export function stableMarkdown(text: string): string {
  let out = text;
  const tail = (mark: string) => {
    const count = out.split(mark).length - 1;
    if (count % 2 === 1) out = out.slice(0, out.lastIndexOf(mark));
  };
  tail("**");
  tail("`");
  // A single `*` left open (italic being typed); a `* ` bullet at the start of a line is not a mark.
  const single = (i: number) => out[i] === "*" && out[i - 1] !== "*" && out[i + 1] !== "*" && !(out[i + 1] === " " && (i === 0 || out[i - 1] === "\n"));
  const singles = [...out].map((_, i) => i).filter(single);
  if (singles.length % 2 === 1) out = out.slice(0, singles[singles.length - 1]);
  // A link whose text or target is still being typed.
  return out.replace(/\[[^\]\n]*$|\[[^\]\n]*\]\([^)\n]*$/, "");
}

const LINK_LINE: Record<Language, RegExp> = { es: /^Sigue tu caso/i, pt: /^Acompanhe seu caso/i };

/**
 * The reply text beside its receipt (design pass 1, finding 1): the receipt card carries the deadlines and their
 * sources, so a reply line that repeats a receipt fact, a deadline line or a raw URL is not shown twice. When nothing
 * is left, the reply points at the card.
 */
export function replyBody(text: string, receipt: Pick<Receipt, "facts" | "deadline_text" | "language"> | undefined, lang: Language): string {
  if (!receipt) return customerText(text);
  const repeated = new Set([...(receipt.facts ?? []), receipt.deadline_text].map((l) => l.trim()).filter(Boolean));
  const deadlineHead = [MESSAGES.receipt.credit_deadline, MESSAGES.receipt.ruling_deadline, MESSAGES.status.credit_deadline]
    .map((m) => m[lang].split("{")[0].trim())
    .filter(Boolean);
  const kept = text
    .split("\n")
    .filter((line) => {
      const l = line.trim();
      if (!l) return true;
      if (repeated.has(l) || /https?:\/\//.test(l) || LINK_LINE[lang].test(l)) return false;
      return !deadlineHead.some((head) => l.startsWith(head));
    })
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return kept ? customerText(kept) : RECEIPT_POINTER[lang];
}

const RECEIPT_POINTER: Record<Language, string> = {
  es: "Listo. Aquí está tu comprobante con los plazos y sus fuentes.",
  pt: "Pronto. Aqui está seu comprovante com os prazos e suas fontes.",
};

// --- chips -------------------------------------------------------------------------------------------------------

/** True for the chip that reaches a person (`talk_to_person`, or a call request). */
export function isPersonChip(s: Suggestion, lang: Language): boolean {
  return s.action?.type === "request_call" || s.label === MESSAGES.suggest.talk_to_person[lang];
}

/** The person chip of `contracts/messages.yaml` (`suggest.talk_to_person`, kind action → `request_call`). */
export function personChip(lang: Language): Suggestion {
  const label = MESSAGES.suggest.talk_to_person[lang];
  return { label, text: label, action: { type: "request_call" } };
}

/**
 * The chips under the last reply: at most 3 from the turn, labels without bracket tags, and "talk to a person" always
 * there (spec 04 AC-20, AC-39; plan §4.2). A person chip already in the row keeps its place.
 */
export function chipsFor(suggestions: readonly Suggestion[] | undefined, lang: Language): Suggestion[] {
  const row = (suggestions ?? []).slice(0, 3).map((s) => ({ ...s, label: customerText(s.label).trim() })).filter((s) => s.label);
  if (row.some((s) => isPersonChip(s, lang))) return row;
  return [...row.slice(0, 2), personChip(lang)];
}

// --- words and times in the session language ---------------------------------------------------------------------

const LOCALE: Record<Language, string> = { es: "es-MX", pt: "pt-BR" };

/** The business clock of each country of the bank (ADR 0020): times are shown where the case lives. */
const ZONE: Record<string, string> = {
  MX: "America/Mexico_City",
  CO: "America/Bogota",
  AR: "America/Argentina/Buenos_Aires",
  BR: "America/Sao_Paulo",
  PE: "America/Lima",
  CL: "America/Santiago",
};

export function zoneFor(country: string | undefined, lang: Language): string {
  return (country && ZONE[country.toUpperCase()]) || (lang === "pt" ? ZONE.BR : ZONE.MX);
}

/** "5 oct 2026, 19:04" (es-MX) or "5 de out. de 2026, 19:04" (pt-BR), 24 h, in the case's zone. Never the system clock. */
export function formatTimestamp(iso: string, lang: Language, country?: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  return new Intl.DateTimeFormat(LOCALE[lang], {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: zoneFor(country, lang),
  }).format(t);
}

/** A business date `YYYY-MM-DD` as "14 de octubre de 2026": a date, not an instant, so no zone shift. */
export function formatDate(ymd: string, lang: Language): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd);
  if (!m) return ymd;
  const t = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return new Intl.DateTimeFormat(LOCALE[lang], { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(t);
}

const ISO_INSTANT = /\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})\b/g;

/** Every ISO instant inside a customer line, formatted in the session language and the case's zone. */
export function localizeTimes(text: string, lang: Language, country?: string): string {
  return text.replace(ISO_INSTANT, (iso) => formatTimestamp(iso, lang, country));
}

/** Money as the session language writes it, with the currency code the tool returned. */
export function formatAmount(amount: number, currency: string, lang: Language): string {
  return `${new Intl.NumberFormat(LOCALE[lang], { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount)} ${currency}`;
}

/** The action states as the customer reads them (constitution #4: requested is not verified). */
export const STATE_WORDS: Record<ActionState, Record<Language, string>> = {
  in_progress: { es: "En curso", pt: "Em andamento" },
  requested: { es: "Solicitado", pt: "Solicitado" },
  verified: { es: "Verificado", pt: "Verificado" },
  not_confirmed: { es: "No confirmado", pt: "Não confirmado" },
};

export const TOOL_STATUS_WORDS: Record<ToolStatus, Record<Language, string>> = {
  running: { es: "En curso", pt: "Em andamento" },
  done: { es: "Listo", pt: "Pronto" },
  failed: { es: "No se completó", pt: "Não concluído" },
};

/** What a tool does, in the customer's words, for the action cards (the tool name itself is never shown). */
export const TOOL_WORDS: Record<string, Record<Language, string>> = {
  search_transaction: { es: "Buscar el cargo", pt: "Buscar a cobrança" },
  list_recent_transactions: { es: "Ver tus cargos recientes", pt: "Ver suas cobranças recentes" },
  evaluate_policy: { es: "Revisar las reglas", pt: "Verificar as regras" },
  block_card: { es: "Bloquear la tarjeta", pt: "Bloquear o cartão" },
  open_case: { es: "Abrir el caso", pt: "Abrir o caso" },
  get_case: { es: "Confirmar el caso", pt: "Confirmar o caso" },
  compute_deadline: { es: "Calcular el plazo legal", pt: "Calcular o prazo legal" },
  request_call: { es: "Pedir una llamada", pt: "Pedir uma ligação" },
  get_case_status: { es: "Leer el estado del caso", pt: "Ler a situação do caso" },
};

export function toolWords(tool: string, lang: Language): string {
  return TOOL_WORDS[tool]?.[lang] ?? tool.replaceAll("_", " ");
}

/** Deadline kinds in the customer's words. */
export function deadlineWords(kind: string, lang: Language): string {
  const words: Record<string, Record<Language, string>> = {
    credit: { es: "Plazo para pronunciarse sobre los fondos", pt: "Prazo para se pronunciar sobre os valores" },
    ruling: { es: "Plazo para resolver tu caso", pt: "Prazo para resolver seu caso" },
  };
  return words[kind]?.[lang] ?? (lang === "es" ? "Plazo legal" : "Prazo legal");
}
