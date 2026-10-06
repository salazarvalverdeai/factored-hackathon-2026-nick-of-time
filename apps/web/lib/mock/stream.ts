// The mock of the live stream (spec 01 §6.4.1) [simulated]: the scripted agent's turn replayed as the `tool` and
// `text` SSE events the api forwards, in the exact wire shapes, so /chat shows the same cards and streaming text with
// no backend. The events go through the same parsers as live mode (lib/chat-stream.ts), so a drift fails here too.
import { type TextChunk, type ToolEvent, parseTextChunk, parseToolEvent } from "../chat-stream.ts";
import type { AgentReply, Language } from "../types.ts";

/** One SSE record as the api sends it: `event:` name and its `data:` JSON. */
export interface WireEvent {
  event: "tool" | "text";
  data: Record<string, unknown>;
}

/** What the scripted turn knew: the session's customer and the mock's frozen demo date (ADR 0012). */
export interface MockTurnFacts {
  language: Language;
  last4: string;
  country: string;
  /** The mock's demo date `YYYY-MM-DD`: the stream's `at` times sit on it, never on the system clock. */
  today: string;
}

/** The mock's charge per country [simulated]: what `search_transaction` returns in the scripted walk-through. */
const MOCK_CHARGE: Record<string, { amount: number; currency: string; merchant: string }> = {
  MX: { amount: 4200, currency: "MXN", merchant: "ELECTRO MUNDO CDMX" },
  AR: { amount: 85000, currency: "ARS", merchant: "TIENDA ONLINE BA" },
  BR: { amount: 380, currency: "BRL", merchant: "LOJA CENTRO SP" },
};

/** The legal sources of the mock's clock table, as named links: copied from `contracts/policies.yaml regulatory_clock`
 *  (`source_label.es`, `source_url`). A country the mock has no entry for keeps the mock's source text, with no link. */
const MOCK_SOURCE: Record<string, { label: string; url: string | null }> = {
  MX: {
    label: "Banxico, Circular 3/2012, arts. 19 Bis 3 y 19 Bis 4 (modificada por la Circular 14/2018)",
    url: "https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-3-2012/%7B4E0281A4-7AD8-1462-BC79-7F2925F3171D%7D.pdf",
  },
  AR: {
    label: "BCRA, Protección de los Usuarios de Servicios Financieros, punto 3.1.6",
    url: "https://www.bcra.gob.ar/archivos/Pdfs/texord/t-pusf.pdf",
  },
};

const TITLES: Record<string, Record<Language, string>> = {
  search_transaction: { es: "Buscando el cargo en tu cuenta", pt: "Buscando a cobrança na sua conta" },
  evaluate_policy: { es: "Revisando las reglas del banco", pt: "Verificando as regras do banco" },
  block_card: { es: "Bloqueando tu tarjeta", pt: "Bloqueando seu cartão" },
  open_case: { es: "Abriendo tu caso", pt: "Abrindo seu caso" },
  get_case: { es: "Confirmando que el caso quedó abierto", pt: "Confirmando que o caso foi aberto" },
  compute_deadline: { es: "Calculando el plazo legal", pt: "Calculando o prazo legal" },
};

const SUMMARIES: Record<string, Record<Language, string>> = {
  search_transaction: { es: "Encontré 1 cargo que coincide.", pt: "Encontrei 1 cobrança que corresponde." },
  evaluate_policy_block: { es: "Corresponde bloquear la tarjeta y abrir un caso.", pt: "É o caso de bloquear o cartão e abrir um caso." },
  evaluate_policy_confirm: { es: "Antes de actuar necesito tu confirmación.", pt: "Antes de agir preciso da sua confirmação." },
  evaluate_policy_person: { es: "Una persona revisará tu caso.", pt: "Uma pessoa vai revisar seu caso." },
  block_card: { es: "Bloqueo confirmado al leer de nuevo el sistema.", pt: "Bloqueio confirmado ao ler o sistema de novo." },
  open_case: { es: "Caso abierto.", pt: "Caso aberto." },
  get_case: { es: "Caso confirmado al leerlo de nuevo.", pt: "Caso confirmado ao lê-lo de novo." },
  compute_deadline: { es: "Plazo calculado con su fuente legal.", pt: "Prazo calculado com sua fonte legal." },
};

const VERDICT_ACTIONS: Record<"block" | "person", Record<Language, string[]>> = {
  block: {
    es: ["Bloquear tu tarjeta y confirmarlo", "Abrir tu caso", "Calcular el plazo legal", "Una persona decide el cierre"],
    pt: ["Bloquear seu cartão e confirmar", "Abrir seu caso", "Calcular o prazo legal", "Uma pessoa decide o fechamento"],
  },
  person: {
    es: ["Abrir tu caso", "Calcular el plazo legal", "Una persona revisa y decide"],
    pt: ["Abrir seu caso", "Calcular o prazo legal", "Uma pessoa revisa e decide"],
  },
};

/** The `tool` events of one call: `running`, then exactly one `done` with its cards (spec 04 AC-38). */
function call(n: number, step: string, at: string, lang: Language, summaryKey: string, cards: Record<string, unknown>[]): WireEvent[] {
  const id = `tc-${n}-${step}`;
  const base = { kind: "tool", id, step, title: TITLES[step][lang] };
  return [
    { event: "tool", data: { ...base, status: "running", cards: [], at } },
    { event: "tool", data: { ...base, status: "done", summary: SUMMARIES[summaryKey][lang], cards, at } },
  ];
}

/**
 * The reply as `text` chunks the way the writer releases them (spec 01 AC-10): words without digits go one by one; a
 * line that holds a digit goes whole, once complete.
 */
export function textChunks(reply: string, messageId: string): WireEvent[] {
  const out: WireEvent[] = [];
  const lines = reply.split("\n");
  lines.forEach((line, i) => {
    const end = i < lines.length - 1 ? "\n" : "";
    if (/\d/.test(line) || !line) {
      out.push({ event: "text", data: { kind: "text", message_id: messageId, delta: line + end } });
      return;
    }
    const words = line.split(/(?<= )/);
    words.forEach((w, j) => out.push({ event: "text", data: { kind: "text", message_id: messageId, delta: w + (j === words.length - 1 ? end : "") } }));
  });
  return out;
}

/** The scripted turn as the stream the live api would send before its `turn` [simulated]. */
export function mockTurnEvents(reply: AgentReply, facts: MockTurnFacts, turnNo: number): WireEvent[] {
  const lang = facts.language;
  const at = (s: number) => `${facts.today}T15:00:${String(s).padStart(2, "0")}Z`;
  const events: WireEvent[] = [];
  const steps = new Set(reply.trace.map((t) => t.step));
  const charge = MOCK_CHARGE[facts.country] ?? MOCK_CHARGE.MX;
  const source = MOCK_SOURCE[facts.country] ?? { label: reply.receipt?.deadline.deadlineSource ?? "", url: null };

  if (reply.deny || !steps.has("policy")) {
    events.push(...textChunks(reply.text, `msg-${turnNo}`));
    return events;
  }
  let n = 0;
  events.push(
    ...call(++n, "search_transaction", at(1), lang, "search_transaction", [
      {
        type: "charge",
        transaction_id: `tx-mock-${facts.country.toLowerCase()}-001`,
        date: facts.today,
        amount: charge.amount,
        currency: charge.currency,
        merchant: charge.merchant,
        last4: facts.last4,
        synthetic: false,
      },
    ]),
  );
  const blocks = steps.has("block_card");
  const confirm = reply.awaitingConfirmation === true;
  events.push(
    ...call(++n, "evaluate_policy", at(2), lang, confirm ? "evaluate_policy_confirm" : blocks ? "evaluate_policy_block" : "evaluate_policy_person", [
      {
        type: "verdict",
        headline: SUMMARIES[confirm ? "evaluate_policy_confirm" : blocks ? "evaluate_policy_block" : "evaluate_policy_person"][lang],
        actions: VERDICT_ACTIONS[blocks || confirm ? "block" : "person"][lang],
      },
    ]),
  );
  const receipt = reply.receipt;
  if (!receipt) {
    events.push(...textChunks(reply.text, `msg-${turnNo}`));
    return events;
  }
  if (blocks) {
    events.push(...call(++n, "block_card", at(3), lang, "block_card", [{ type: "action", tool: "block_card", state: "verified", verification_id: `V-${receipt.case_id}-B` }]));
  }
  events.push(
    ...call(++n, "open_case", at(4), lang, "open_case", [
      { type: "action", tool: "open_case", state: "requested", verification_id: null },
      { type: "case", case_id: receipt.case_id, status: "new" },
    ]),
    ...call(++n, "get_case", at(5), lang, "get_case", [{ type: "action", tool: "open_case", state: "verified", verification_id: `V-${receipt.case_id}-C` }]),
    ...call(++n, "compute_deadline", at(6), lang, "compute_deadline", [
      { type: "deadline", kind: "credit", date: receipt.deadline.creditDeadline, source_label: source.label, source_url: source.url },
    ]),
  );
  events.push(...textChunks(reply.text, `msg-${turnNo}`));
  return events;
}

export interface StreamHandlers {
  onTool?: (event: ToolEvent) => void;
  onText?: (chunk: TextChunk) => void;
}

/** Plays the events through the live parsers, with a pause between them so the walk-through reads like a live run. */
export async function playEvents(events: readonly WireEvent[], handlers: StreamHandlers, delayMs: number): Promise<void> {
  for (const e of events) {
    if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, e.event === "text" ? Math.round(delayMs / 6) : delayMs));
    if (e.event === "tool") {
      const parsed = parseToolEvent(e.data);
      if (parsed) handlers.onTool?.(parsed);
    } else {
      const parsed = parseTextChunk(e.data);
      if (parsed) handlers.onText?.(parsed);
    }
  }
}
