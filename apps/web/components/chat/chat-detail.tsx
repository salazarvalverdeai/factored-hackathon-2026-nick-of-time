"use client";

// The chat's content for the shared right panel (components/detail-panel.tsx): a step with its cards, a charge, the
// rules' verdict in words, or how a reply was decided (the trace, spec 07 AC-03 and AC-08). Only facts a tool
// returned; no score, zone or policy id.
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { TraceSteps } from "@/components/chat/trace-panel";
import { CaseCardView, DeadlineCardView, StateBadge, VerdictCardView } from "@/components/chat/tool-cards";
import type { ChatDetail } from "@/components/chat/thread";
import { TOOL_STATUS_WORDS, customerText, formatAmount, formatDate, formatTimestamp, toolWords } from "@/lib/chat-stream";
import type { Language } from "@/lib/types";

const COPY = {
  charge: { es: "Detalle del cargo", pt: "Detalhe da cobrança" },
  merchant: { es: "Comercio", pt: "Estabelecimento" },
  amount: { es: "Monto", pt: "Valor" },
  date: { es: "Fecha", pt: "Data" },
  card: { es: "Tarjeta terminada en", pt: "Cartão com final" },
  id: { es: "Identificador", pt: "Identificador" },
  test: { es: "Cargo de prueba de la demo", pt: "Cobrança de teste da demo" },
  verdict: { es: "Lo que dicen las reglas", pt: "O que dizem as regras" },
  verdictNote: {
    es: "Las reglas del banco deciden; el asistente no puede saltárselas. Una persona cierra cada caso.",
    pt: "As regras do banco decidem; o assistente não pode contorná-las. Uma pessoa fecha cada caso.",
  },
  status: { es: "Estado", pt: "Situação" },
  at: { es: "Hora", pt: "Hora" },
  summary: { es: "Resultado", pt: "Resultado" },
  actions: { es: "Acciones", pt: "Ações" },
  none: { es: "Sin datos", pt: "Sem dados" },
  close: { es: "Cerrar", pt: "Fechar" },
} as const;

export function ChatDetailPanel({ detail, lang, country, onClose }: { detail: ChatDetail | null; lang: Language; country?: string; onClose: () => void }) {
  if (!detail) return <DetailPanel open={false} onClose={onClose} title="" />;
  const common = { open: true, onClose, closeLabel: COPY.close[lang] };

  if (detail.kind === "charge") {
    const c = detail.card;
    return (
      <DetailPanel {...common} title={COPY.charge[lang]} description={c.synthetic ? COPY.test[lang] : undefined}>
        <DetailFields>
          <DetailField label={COPY.merchant[lang]}>{c.merchant ? customerText(c.merchant) : COPY.none[lang]}</DetailField>
          <DetailField label={COPY.amount[lang]}>{formatAmount(c.amount, c.currency, lang)}</DetailField>
          <DetailField label={COPY.date[lang]}>{formatDate(c.date, lang)}</DetailField>
          <DetailField label={COPY.card[lang]}>{c.last4}</DetailField>
          <DetailField label={COPY.id[lang]} mono>
            {c.transaction_id}
          </DetailField>
        </DetailFields>
      </DetailPanel>
    );
  }

  if (detail.kind === "verdict") {
    return (
      <DetailPanel {...common} title={COPY.verdict[lang]} description={COPY.verdictNote[lang]}>
        <VerdictCardView card={detail.card} lang={lang} />
      </DetailPanel>
    );
  }

  if (detail.kind === "tool") {
    const t = detail.tool;
    return (
      <DetailPanel {...common} title={customerText(t.title)} description={t.summary ? customerText(t.summary) : undefined}>
        <DetailFields>
          <DetailField label={COPY.status[lang]}>{TOOL_STATUS_WORDS[t.status][lang]}</DetailField>
          <DetailField label={COPY.at[lang]}>{formatTimestamp(t.at, lang, country)}</DetailField>
        </DetailFields>
        <div className="mt-3 space-y-2">
          {t.cards.map((c, i) =>
            c.type === "action" ? (
              <p key={i} className="flex flex-wrap items-center gap-2">
                {toolWords(c.tool, lang)} <StateBadge card={c} lang={lang} />
              </p>
            ) : c.type === "charge" ? (
              <p key={i} className="rounded-lg border p-2">
                {c.merchant ? customerText(c.merchant) : COPY.none[lang]} · {formatAmount(c.amount, c.currency, lang)} · {formatDate(c.date, lang)}
              </p>
            ) : c.type === "verdict" ? (
              <VerdictCardView key={i} card={c} lang={lang} />
            ) : c.type === "deadline" ? (
              <DeadlineCardView key={i} card={c} lang={lang} />
            ) : (
              <CaseCardView key={i} card={c} lang={lang} />
            ),
          )}
        </div>
      </DetailPanel>
    );
  }

  return (
    <DetailPanel {...common} title="How this reply was decided" description="Each step of the turn and the guardrails that fired. No score, zone or policy id.">
      <TraceSteps trace={detail.reply.trace} guardrails={detail.reply.guardrails} />
    </DetailPanel>
  );
}
