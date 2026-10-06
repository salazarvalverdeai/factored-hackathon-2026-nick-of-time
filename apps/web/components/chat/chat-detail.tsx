"use client";

// The chat's content for the shared right panel (components/detail-panel.tsx, spec 07 AC-15): a step as an AI Elements
// `tool` with its status and result cards, a charge, or the rule in words (the approved mock: what the rules decided
// and which actions they allow, no score and no policy id). The technical trace (AC-03, AC-08) is a toggle inside the
// panel, no longer a permanent column. Only facts a tool returned.
import { useState } from "react";
import { Tool, ToolContent, ToolHeader } from "@/components/ai-elements/tool";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { TraceSteps } from "@/components/chat/trace-panel";
import { CaseCardView, DeadlineCardView, StateBadge, VerdictCardView } from "@/components/chat/tool-cards";
import type { ChatDetail } from "@/components/chat/thread";
import { Button } from "@/components/ui/button";
import { TOOL_STATUS_WORDS, type ToolEvent, customerText, formatAmount, formatDate, formatTimestamp, toolWords } from "@/lib/chat-stream";
import { CHAT_STRINGS as S } from "@/lib/chat-strings";
import type { AgentReply, Language } from "@/lib/types";

const COPY = {
  charge: { es: "Detalle del cargo", pt: "Detalhe da cobrança" },
  merchant: { es: "Comercio", pt: "Estabelecimento" },
  amount: { es: "Monto", pt: "Valor" },
  date: { es: "Fecha", pt: "Data" },
  card: { es: "Tarjeta terminada en", pt: "Cartão com final" },
  id: { es: "Identificador", pt: "Identificador" },
  test: { es: "Cargo de prueba de la demo", pt: "Cobrança de teste da demo" },
  at: { es: "Hora", pt: "Hora" },
  none: { es: "Sin datos", pt: "Sem dados" },
} as const;

const TOOL_STATE = { running: "input-available", done: "output-available", failed: "output-error" } as const;

/** "Ver traza técnica": each step of the turn and the guardrails that fired, folded by default. */
function TechnicalTrace({ reply, lang }: { reply?: AgentReply; lang: Language }) {
  const [open, setOpen] = useState(false);
  if (!reply || (reply.trace.length === 0 && reply.guardrails.length === 0)) return null;
  return (
    <div className="mt-4 border-t pt-3">
      <Button variant="ghost" size="sm" className="-ml-2" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {open ? S.hideTechnicalTrace[lang] : S.technicalTrace[lang]}
      </Button>
      {open ? (
        <div className="mt-2" data-slot="technical-trace">
          <TraceSteps trace={reply.trace} guardrails={reply.guardrails} />
        </div>
      ) : null}
    </div>
  );
}

function ToolDetail({ tool, lang, country }: { tool: ToolEvent; lang: Language; country?: string }) {
  return (
    <Tool defaultOpen className="mb-0">
      <ToolHeader title={customerText(tool.title)} type={`tool-${tool.step}`} state={TOOL_STATE[tool.status]} statusLabel={TOOL_STATUS_WORDS[tool.status][lang]} />
      <ToolContent className="space-y-3 border-t p-3">
        <DetailFields>
          {tool.summary ? <DetailField label={S.stepResult[lang]}>{customerText(tool.summary)}</DetailField> : null}
          <DetailField label={COPY.at[lang]}>{formatTimestamp(tool.at, lang, country)}</DetailField>
        </DetailFields>
        {tool.cards.map((c, i) =>
          c.type === "action" ? (
            <p key={i} className="flex flex-wrap items-center gap-2 text-sm">
              {toolWords(c.tool, lang)} <StateBadge card={c} lang={lang} />
            </p>
          ) : c.type === "charge" ? (
            <p key={i} className="rounded-lg border p-2 text-sm">
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
      </ToolContent>
    </Tool>
  );
}

export function ChatDetailPanel({ detail, lang, country, onClose }: { detail: ChatDetail | null; lang: Language; country?: string; onClose: () => void }) {
  if (!detail) return <DetailPanel open={false} onClose={onClose} title="" />;
  const common = { open: true, onClose, closeLabel: S.close[lang] };

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
        <TechnicalTrace reply={detail.reply} lang={lang} />
      </DetailPanel>
    );
  }

  if (detail.kind === "rule") {
    const c = detail.card;
    return (
      <DetailPanel {...common} title={detail.tool ? customerText(detail.tool.title) : S.ruleTitle[lang]} description={S.ruleLead[lang]}>
        <DetailFields>
          <DetailField label={S.ruleResult[lang]}>{customerText(c.headline)}</DetailField>
          {c.actions.length ? (
            <DetailField label={S.ruleAllowed[lang]}>{c.actions.map((a) => customerText(a)).join(" · ")}</DetailField>
          ) : null}
        </DetailFields>
        <p className="mt-3 text-xs text-muted-foreground">{S.ruleNote[lang]}</p>
        <TechnicalTrace reply={detail.reply} lang={lang} />
      </DetailPanel>
    );
  }

  if (detail.kind === "tool") {
    return (
      <DetailPanel {...common} title={customerText(detail.tool.title)} description={detail.tool.summary ? customerText(detail.tool.summary) : undefined}>
        <ToolDetail tool={detail.tool} lang={lang} country={country} />
        <TechnicalTrace reply={detail.reply} lang={lang} />
      </DetailPanel>
    );
  }

  return (
    <DetailPanel {...common} title={S.howDecided[lang]} description={S.ruleNote[lang]}>
      <TraceSteps trace={detail.reply.trace} guardrails={detail.reply.guardrails} />
    </DetailPanel>
  );
}
