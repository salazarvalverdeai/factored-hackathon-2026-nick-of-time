// Simulated answers of the assisted console routes (lib/console-api.ts), built from the mock case so the console works
// without the backend. Nothing here comes from the dataset; every value is derived from the case the mock store holds,
// deterministically (same case → same answer). Live mode never reads this file.
import type {
  AuditResult,
  CaseContext,
  CaseConversation,
  CaseSummary,
  ContextNotification,
  SecondOpinion,
  TranscriptMessage,
} from "../console-api.ts";
import type { ConsoleCase, NotificationEntry } from "../types.ts";
import { DEMO_TODAY, daysBetween } from "./store.ts";

/** Official sources of the clock entries the mock uses (contracts/policies.yaml `source_url`). */
const SOURCE_URLS: Record<string, string> = {
  MX: "https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-3-2012/%7B4E0281A4-7AD8-1462-BC79-7F2925F3171D%7D.pdf",
  AR: "https://www.bcra.gob.ar/archivos/Pdfs/texord/t-pusf.pdf",
  BR: "https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Resolu%C3%A7%C3%A3o%20CMN&numero=4860",
  CO: "https://www.superfinanciera.gov.co/preguntas-frecuentes/3/3-derechos-de-peticion-ante-entidades-vigiladas/",
};

const MERCHANTS = ["Supermercado Central", "Farmacia Plaza", "Gasolinera Norte", "Cafetería Luna", "Tienda en línea"];

function hash(s: string): number {
  let h = 7;
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h;
}

/** YYYY-MM-DD shifted by `days`. */
function shift(iso: string, days: number): string {
  const d = new Date(`${iso.slice(0, 10)}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** "Cargo no reconocido de 4,200 MXN" → 4200 MXN; null when the request names no amount. */
export function amountFromRequest(text: string): { amount: number; currency: string } | null {
  const m = /([\d][\d.,]*)\s*([A-Z]{3})\b/.exec(text);
  if (!m) return null;
  return { amount: Number(m[1].replace(/[.,](?=\d{3}\b)/g, "").replace(",", ".")), currency: m[2] };
}

const CURRENCY: Record<string, string> = { MX: "MXN", AR: "ARS", BR: "BRL", CO: "COP" };

function last4Of(c: ConsoleCase): string {
  return String(1000 + (hash(c.customerId) % 9000));
}

function blocked(c: ConsoleCase): boolean {
  return c.handoff.actions.some((a) => a.tool === "block_card" && a.verified) || c.events.some((e) => e.type === "card_blocked");
}

export function mockContext(c: ConsoleCase, notes: NotificationEntry[] = []): CaseContext {
  const disputedDay = c.openedAt.slice(0, 10);
  const last4 = last4Of(c);
  const named = amountFromRequest(c.handoff.request);
  const currency = named?.currency ?? CURRENCY[c.deadline.country] ?? "USD";
  const base = named?.amount ?? 1000;
  const seed = hash(c.id);
  const offsets = [-26, -17, -9, -3, 0, 4];
  const transactions = offsets.map((off, i) => ({
    transaction_id: `TRX-${c.id.replace(/\D/g, "")}${String(i + 1).padStart(2, "0")}`,
    date: shift(disputedDay, off),
    amount: off === 0 ? base : Math.round((base * (((seed >>> i) % 7) + 1)) / 20),
    currency,
    merchant: off === 0 ? "Comercio no identificado" : MERCHANTS[(seed + i) % MERCHANTS.length],
    last4,
    disputed: off === 0,
  }));
  const fromStore: ContextNotification[] = notes.flatMap((n) =>
    n.channels.map((ch) => ({ at: n.at, channel: ch.channel, event: `status_${n.status}`, status: ch.delivered ? "delivered" : "failed" })),
  );
  const derived: ContextNotification[] = c.events
    .filter((e) => e.status && e.actor !== "customer")
    .map((e) => ({ at: e.at, channel: "in_app", event: `status_${e.status}`, status: "delivered" }));
  return {
    previous_cases:
      c.zone === "human"
        ? []
        : [{ case_id: `NOT-P${c.id.replace(/\D/g, "")}`, opened_at: `${shift(disputedDay, -140)}T15:20:00.000Z`, status: "closed", outcome: "credit_approved" }],
    transactions: transactions.sort((a, b) => b.date.localeCompare(a.date)),
    cards: [
      { last4, product: c.deadline.product || c.handoff.deadline.product || "debit", status: blocked(c) ? "blocked" : "active" },
      ...(c.zone === "high" ? [{ last4: String(((Number(last4) + 3517) % 9000) + 1000), product: "credit", status: "active" }] : []),
    ],
    calls: c.events.filter((e) => e.type === "call_requested").map((e) => ({ requested_at: e.at, status: "requested" })),
    notifications: (fromStore.length ? fromStore : derived).sort((a, b) => b.at.localeCompare(a.at)),
  };
}

/** A short scripted transcript in the customer's language, built from the case's own request (simulated). */
export function mockConversation(c: ConsoleCase): CaseConversation {
  const pt = c.language === "pt";
  const t0 = Date.parse(c.openedAt) - 4 * 60_000;
  const at = (min: number) => new Date(t0 + min * 60_000).toISOString();
  const blocks = c.zone !== "human";
  const messages: TranscriptMessage[] = [
    {
      role: "agent",
      text: pt
        ? "Olá! Posso ajudar com uma **cobrança que você não reconhece**: encontro a transação, abro o caso e digo o prazo legal."
        : "¡Hola! Puedo ayudarte con un **cargo que no reconoces**: encuentro la transacción, abro el caso y te digo el plazo legal.",
      at: at(0),
    },
    { role: "customer", text: c.handoff.request, at: at(1) },
    {
      role: "agent",
      text: pt
        ? "Encontrei a transação. Vou fazer isto:\n1. Abrir o caso\n2. Verificar o resultado"
        : "Encontré la transacción. Voy a hacer esto:\n1. Abrir el caso\n2. Verificar el resultado",
      at: at(2),
    },
    {
      role: "agent",
      text: blocks
        ? pt
          ? `Caso **${c.id}** aberto e cartão bloqueado (verificado).`
          : `Caso **${c.id}** abierto y tarjeta bloqueada (verificado).`
        : pt
          ? `Caso **${c.id}** aberto. Uma pessoa vai revisar e decidir.`
          : `Caso **${c.id}** abierto. Una persona lo revisará y decidirá.`,
      at: at(4),
    },
  ];
  return { threads: [{ thread_id: `TH-${c.id}`, session_started_at: at(0), messages }] };
}

export function mockSummary(c: ConsoleCase): CaseSummary {
  const h = c.handoff;
  const lines = [
    `El cliente reporta: ${h.request}.`,
    ...h.verified_facts.slice(0, 2).map((f) => `Verificado: ${f.fact}.`),
    h.actions.length
      ? `El agente ${h.actions.map((a) => (a.tool === "block_card" ? "bloqueó la tarjeta" : a.tool)).join(", ")} y lo confirmó con una lectura.`
      : "El agente no tomó acciones: el caso pasó a revisión de una persona.",
  ];
  const date = c.deadline.creditDeadline ?? c.deadline.rulingDeadline ?? null;
  return {
    lines,
    writer: "template",
    deadline: date
      ? {
          kind: c.deadline.creditDeadline ? "credit" : "ruling",
          date,
          days_left: c.deadline.daysLeft ?? daysBetween(DEMO_TODAY, date),
          source_label: c.deadline.deadlineSource.split(" — ")[0] || c.deadline.deadlineSource,
          source_url: SOURCE_URLS[c.deadline.country] ?? null,
        }
      : null,
  };
}

/** Evidence ids the judge may cite: the verified facts' sources and the verification ids (spec 18 §4.2, D-036). */
function evidenceIds(c: ConsoleCase): string[] {
  return [...c.handoff.verified_facts.map((f) => f.source_id), ...c.handoff.actions.map((a) => a.verification_id)].filter(Boolean);
}

export function mockSecondOpinion(c: ConsoleCase): SecondOpinion | null {
  const ids = evidenceIds(c);
  if (ids.length === 0) return null; // nothing to ground a reason on: "No second opinion" (spec 18 AC-11)
  const agree = c.zone === "high";
  return {
    verdict: agree ? "agree" : "uncertain",
    reasons: agree
      ? [
          { text: "The disputed transaction matches the customer's account of it.", evidence_ids: [ids[0]] },
          { text: "The card block was verified by a read after the write.", evidence_ids: ids.slice(1, 2).length ? ids.slice(1, 2) : [ids[0]] },
        ]
      : [{ text: "The bank sent no fraud score, so the evidence alone does not settle the dispute.", evidence_ids: [ids[0]] }],
    questions: agree ? [] : [{ text: "Does the customer recognize the merchant?", evidence_ids: [ids[0]] }],
    model: "claude-haiku-4-5 (simulated)",
    label: "AI second opinion — advisory",
    created_at: `${DEMO_TODAY}T10:00:00.000Z`,
  };
}

const OUTCOME_BY_ZONE: Record<string, string> = {
  high: "block_and_verify",
  medium: "confirm_with_customer",
  human: "human_review",
};

export function mockAudit(c: ConsoleCase): AuditResult {
  const hasDeadline = Boolean(c.deadline.creditDeadline || c.deadline.rulingDeadline);
  const verified = c.handoff.actions.filter((a) => a.verified).length;
  return {
    checks: [
      { id: "A1", name: "Decision", passed: true, detail: `The rules give the same decision for zone ${c.zone}.` },
      {
        id: "A2",
        name: "Deadline",
        passed: hasDeadline ? true : null,
        detail: hasDeadline ? "The clock gives the same legal dates." : "No verified clock entry for this country: a person decides.",
      },
      {
        id: "A3",
        name: "Actions",
        passed: verified ? true : null,
        detail: verified ? `${verified} verified action, each with a read after its write.` : "No action claimed as verified.",
      },
      // As the api: A4 and A5 need the turn's tool results and replies from the agent trace (the harness runs them).
      { id: "A4", name: "Grounding", status: "not_applicable", passed: null, detail: "Needs the agent trace; the evaluation harness runs it." },
      { id: "A5", name: "Coherence", status: "not_applicable", passed: null, detail: "Needs the agent trace; the evaluation harness runs it." },
      { id: "A6", name: "Privacy", passed: true, detail: "No score, policy id or card number reached the customer." },
      { id: "A7", name: "Lifecycle", passed: true, detail: "Valid transitions only; nothing resolved or closed without a person." },
    ],
    rederived_outcome: OUTCOME_BY_ZONE[c.zone] ?? "human_review",
    matches: true,
  };
}
