// Scripted stand-in for the LangGraph agent (spec 04) [simulated]. The LLM would only *understand*; here a few regexes do.
// The rules decide (zone from the bank score), the tools act (block, open case), verification confirms, a person closes.
import type { AgentReply, Customer, Language, Receipt, TraceStep, Zone } from "../types.ts";
import { type MockStore } from "./store.ts";

export interface AgentContext {
  /** Set when the previous turn asked the customer to confirm (medium zone). */
  pendingRequest?: string;
}

const INJECTION = /ignore (all |the )?(previous|prior) instructions|ignora (las |todas las )?instrucciones|ignore (as |todas as )?instru/i;
const OTHER_CUSTOMER = /otro cliente|otra cuenta|another customer|outro cliente|outra conta/i;
const DISPUTE = /no reconozco|desconozco|cargo|fraude|n[aã]o reconhe[cç]o|cobran[cç]a|d[eé]bito|unrecognized|charge/i;
// (?![\p{L}]) instead of \b: JavaScript's \b treats "í" as a non-letter, so "sí" would never match.
const YES = /^(s[ií]|sim|yes|confirmo|claro)(?![\p{L}])/iu;

export function zoneFor(score: number | null): Zone {
  if (score === null) return "human";
  if (score >= 50) return "high";
  if (score >= 30) return "medium";
  return "human";
}

const T: Record<Language, Record<string, (a?: string) => string>> = {
  es: {
    deny: () => "No puedo ayudarte con eso. Si quieres, cuéntame del cargo que no reconoces en tu propia cuenta.",
    askWhat: () => "Cuéntame qué cargo no reconoces: comercio, monto y fecha aproximada.",
    confirm: () => "Antes de bloquear tu tarjeta necesito confirmarlo: ¿reconoces o no este cargo? Responde «sí» para continuar.",
    cancelled: () => "Entendido, no bloqueé nada. Si cambias de idea, escríbeme de nuevo.",
    blocked: (id) => `Listo. Bloqueé tu tarjeta y abrí el caso ${id}. Un analista lo revisará; puedes seguirlo en /case/${id}.`,
    review: (id) => `Abrí el caso ${id}. Un analista lo revisará y te avisaremos de cada paso; todavía no bloqueé la tarjeta.`,
  },
  pt: {
    deny: () => "Não posso ajudar com isso. Se quiser, conte sobre a cobrança que você não reconhece na sua própria conta.",
    askWhat: () => "Conte qual cobrança você não reconhece: estabelecimento, valor e data aproximada.",
    confirm: () => "Antes de bloquear o cartão preciso confirmar: você reconhece ou não esta cobrança? Responda «sim» para continuar.",
    cancelled: () => "Entendido, não bloqueei nada. Se mudar de ideia, escreva de novo.",
    blocked: (id) => `Pronto. Bloqueei o seu cartão e abri o caso ${id}. Um analista irá revisá-lo; acompanhe em /case/${id}.`,
    review: (id) => `Abri o caso ${id}. Um analista irá revisá-lo e avisaremos cada etapa; ainda não bloqueei o cartão.`,
  },
};

function denied(lang: Language, guardrail: string): AgentReply {
  return {
    text: T[lang].deny(),
    deny: true,
    guardrails: [guardrail],
    trace: [
      { step: "guardrail", result: `${guardrail} fired`, kind: "guardrail" },
      { step: "decision", result: "DENY: nothing was executed", kind: "deny" },
    ],
  };
}

export function runAgentTurn(store: MockStore, text: string, ctx: AgentContext = {}): AgentReply {
  const session = store.requireCustomerSession(); // customer_id comes only from the session
  const customer: Customer = store.customerOf(session);
  const lang = customer.language;

  if (INJECTION.test(text)) return denied(lang, "injection_detector");
  if (OTHER_CUSTOMER.test(text)) return denied(lang, "own_products_only");

  const zone = zoneFor(customer.fraudScore);
  let request = text;

  if (ctx.pendingRequest) {
    if (!YES.test(text.trim())) {
      return { text: T[lang].cancelled(), guardrails: [], trace: [{ step: "confirm", result: "customer did not confirm", kind: "ok" }] };
    }
    request = ctx.pendingRequest;
  } else if (!DISPUTE.test(text)) {
    return { text: T[lang].askWhat(), guardrails: [], trace: [{ step: "understand", result: "intent=unclear", kind: "ok" }] };
  } else if (zone === "medium") {
    return {
      text: T[lang].confirm(),
      awaitingConfirmation: true,
      guardrails: [],
      trace: [
        { step: "understand", result: `intent=dispute · language=${lang}`, kind: "ok" },
        { step: "policy", result: "zone=medium → confirm with the customer first", kind: "ok" },
      ],
    };
  }

  const blocks = zone !== "human";
  const opened = store.openCase(customer, zone, request);
  const trace: TraceStep[] = [
    { step: "understand", result: `intent=dispute · language=${lang}`, kind: "ok" },
    { step: "policy", result: `zone=${zone} → ${blocks ? "block the card and verify" : "hand off to a person"}`, kind: "ok" },
  ];
  if (blocks) {
    trace.push(
      { step: "block_card", result: "accepted", kind: "accepted" },
      { step: "verify block_card", result: "verified ✓ (card status read back)", kind: "verified" },
    );
  }
  trace.push(
    { step: "open_case", result: `${opened.id} accepted`, kind: "accepted" },
    { step: "verify open_case", result: "verified ✓ (case read back)", kind: "verified" },
    {
      step: "deadline",
      result: opened.deadline.creditDeadline
        ? `${opened.deadline.creditDeadline} · ${opened.deadline.deadlineSource}`
        : `pending · ${opened.deadline.deadlineSource}`,
      kind: "ok",
    },
  );

  const receipt: Receipt = {
    caseId: opened.id,
    time: new Date(store.clock()).toTimeString().slice(0, 5),
    deadline: opened.deadline,
    aiDid: blocks
      ? ["Blocked your card (verified)", "Opened your case (verified)", "Computed the legal deadline"]
      : ["Opened your case (verified)", "Computed the legal deadline"],
    personWillDo: ["Review the evidence", "Decide on the provisional credit", "Close the case"],
  };

  return { text: blocks ? T[lang].blocked(opened.id) : T[lang].review(opened.id), trace, guardrails: [], receipt };
}
