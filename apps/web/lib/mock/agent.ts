// Scripted stand-in for the LangGraph agent (spec 04) [simulated]. The LLM would only *understand*; here a few regexes do.
// The rules decide (zone from the bank score), the tools act (block, open case), verification confirms, a person closes.
import type { AgentReply, Language, MockCustomer, Receipt, Suggestion, TraceStep, Zone } from "../types.ts";
import { MESSAGES, fill } from "./messages.ts";
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

// Texts that contracts/messages.yaml does not have yet (refusal, clarify, cancel): spec 04 tasks T2-T7 will add them
// there [assumption]. Everything else (plan, receipt, deadlines, chips) comes from MESSAGES, copied from the contract.
const LOCAL: Record<Language, Record<"deny" | "askWhat" | "cancelled", string>> = {
  es: {
    deny: "No puedo ayudarte con eso. Si quieres, cuéntame del cargo que no reconoces en tu propia cuenta.",
    askWhat: "Cuéntame qué cargo no reconoces: comercio, monto y fecha aproximada.",
    cancelled: "Entendido, no bloqueé nada. Si cambias de idea, escríbeme de nuevo.",
  },
  pt: {
    deny: "Não posso ajudar com isso. Se quiser, conte sobre a cobrança que você não reconhece na sua própria conta.",
    askWhat: "Conte qual cobrança você não reconhece: estabelecimento, valor e data aproximada.",
    cancelled: "Entendido, não bloqueei nada. Se mudar de ideia, escreva de novo.",
  },
};

function chip(key: "confirm_yes" | "confirm_no" | "report_unrecognized" | "talk_to_person", lang: Language): Suggestion {
  const label = MESSAGES.suggest[key][lang];
  return { label, text: label };
}

function denied(lang: Language, guardrail: string): AgentReply {
  return {
    text: LOCAL[lang].deny,
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
  const customer: MockCustomer = store.customerOf(session);
  const lang = customer.language;

  if (INJECTION.test(text)) return denied(lang, "injection_detector");
  if (OTHER_CUSTOMER.test(text)) return denied(lang, "own_products_only");

  const zone = zoneFor(customer.fraudScore);
  let request = text;

  if (ctx.pendingRequest) {
    if (!YES.test(text.trim())) {
      return {
        text: LOCAL[lang].cancelled,
        guardrails: [],
        suggestions: [chip("report_unrecognized", lang), chip("talk_to_person", lang)],
        trace: [{ step: "confirm", result: "customer did not confirm", kind: "ok" }],
      };
    }
    request = ctx.pendingRequest;
  } else if (!DISPUTE.test(text)) {
    return {
      text: LOCAL[lang].askWhat,
      guardrails: [],
      suggestions: [chip("report_unrecognized", lang), chip("talk_to_person", lang)],
      trace: [{ step: "understand", result: "intent=unclear", kind: "ok" }],
    };
  } else if (zone === "medium") {
    return {
      // spec 04 AC-16: the plan is stated before acting; the medium zone waits for the customer's confirmation.
      text: [
        MESSAGES.plan.intro[lang],
        fill(MESSAGES.plan.step_block_card, lang, { step_n: 1, last4: customer.last4 }),
        fill(MESSAGES.plan.step_verify, lang, { step_n: 2 }),
        fill(MESSAGES.plan.step_deadline, lang, { step_n: 3 }),
        fill(MESSAGES.plan.step_person, lang, { step_n: 4 }),
        MESSAGES.plan.confirm_ask[lang],
      ].join("\n"),
      suggestions: [chip("confirm_yes", lang), chip("confirm_no", lang)],
      awaitingConfirmation: true,
      guardrails: [],
      trace: [
        { step: "understand", result: `intent=dispute · language=${lang}`, kind: "ok" },
        { step: "policy", result: "confirm with the customer first", kind: "ok" },
      ],
    };
  }

  const blocks = zone !== "human";
  const opened = store.openCase(customer, zone, request);
  const trace: TraceStep[] = [
    { step: "understand", result: `intent=dispute · language=${lang}`, kind: "ok" },
    { step: "policy", result: blocks ? "block the card and verify" : "hand off to a person", kind: "ok" },
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

  const issuedAt = new Date(store.clock()).toISOString();
  const deadlineText = opened.deadline.creditDeadline
    ? fill(MESSAGES.status.credit_deadline, lang, {
        credit_deadline: opened.deadline.creditDeadline,
        deadline_source: opened.deadline.deadlineSource,
      })
    : MESSAGES.status.deadline_unknown[lang];
  const receipt: Receipt = {
    case_id: opened.id,
    language: lang,
    issued_at: issuedAt,
    title: fill(MESSAGES.receipt.title, lang, { case_id: opened.id }),
    card_blocked: blocks
      ? fill(MESSAGES.receipt.card_blocked, lang, {
          last4: customer.last4,
          verification_id: `ver-${opened.id}`,
          verified_at: issuedAt,
        })
      : null,
    deadline: opened.deadline,
    deadline_text: deadlineText,
    what_ai_did: (blocks ? MESSAGES.receipt.what_ai_did_blocked : MESSAGES.receipt.what_ai_did_case_only)[lang],
    what_a_person_does: MESSAGES.receipt.what_a_person_does[lang],
    case_url: `/case/${opened.id}`,
  };

  const replyText = [receipt.what_ai_did, fill(MESSAGES.receipt.case_link, lang, { case_url: receipt.case_url })].join("\n");
  return { text: replyText, trace, guardrails: [], receipt };
}
