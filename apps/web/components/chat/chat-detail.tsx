"use client";

// The chat's content for the shared right panel (components/detail-panel.tsx): a step with its cards, a charge, the
// rules' verdict in words, or how a reply was decided (the trace, spec 07 AC-03 and AC-08). Only facts a tool
// returned; no score, zone or policy id. The panel's own labels follow the UI locale (spec 16 AC-06); the values and
// cards come from the conversation and stay in the session's language, and so does the trace (messages/trace.ts).
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { TraceSteps } from "@/components/chat/trace-panel";
import { CaseCardView, DeadlineCardView, StateBadge, VerdictCardView } from "@/components/chat/tool-cards";
import type { ChatDetail } from "@/components/chat/thread";
import { useT } from "@/components/i18n-provider";
import { translator } from "@/lib/i18n";
import { TOOL_STATUS_WORDS, customerText, formatAmount, formatDate, formatTimestamp, toolWords } from "@/lib/chat-stream";
import type { Language } from "@/lib/types";

export function ChatDetailPanel({ detail, lang, country, onClose }: { detail: ChatDetail | null; lang: Language; country?: string; onClose: () => void }) {
  const t = useT();
  if (!detail) return <DetailPanel open={false} onClose={onClose} title="" />;
  const common = { open: true, onClose, closeLabel: t("shell.common.close") };

  if (detail.kind === "charge") {
    const c = detail.card;
    return (
      <DetailPanel {...common} title={t("chat.detail.charge")} description={c.synthetic ? t("chat.detail.test") : undefined}>
        <DetailFields>
          <DetailField label={t("chat.detail.merchant")}>{c.merchant ? customerText(c.merchant) : t("chat.detail.none")}</DetailField>
          <DetailField label={t("chat.detail.amount")}>{formatAmount(c.amount, c.currency, lang)}</DetailField>
          <DetailField label={t("chat.detail.date")}>{formatDate(c.date, lang)}</DetailField>
          <DetailField label={t("chat.detail.card")}>{c.last4}</DetailField>
          <DetailField label={t("chat.detail.id")} mono>
            {c.transaction_id}
          </DetailField>
        </DetailFields>
      </DetailPanel>
    );
  }

  if (detail.kind === "verdict") {
    return (
      <DetailPanel {...common} title={t("chat.detail.verdict")} description={t("chat.detail.verdictNote")}>
        <VerdictCardView card={detail.card} lang={lang} />
      </DetailPanel>
    );
  }

  if (detail.kind === "tool") {
    const tool = detail.tool;
    return (
      <DetailPanel {...common} title={customerText(tool.title)} description={tool.summary ? customerText(tool.summary) : undefined}>
        <DetailFields>
          <DetailField label={t("chat.detail.status")}>{TOOL_STATUS_WORDS[tool.status][lang]}</DetailField>
          <DetailField label={t("chat.detail.at")}>{formatTimestamp(tool.at, lang, country)}</DetailField>
        </DetailFields>
        <div className="mt-3 space-y-2">
          {tool.cards.map((c, i) =>
            c.type === "action" ? (
              <p key={i} className="flex flex-wrap items-center gap-2">
                {toolWords(c.tool, lang)} <StateBadge card={c} lang={lang} />
              </p>
            ) : c.type === "charge" ? (
              <p key={i} className="rounded-lg border p-2">
                {c.merchant ? customerText(c.merchant) : t("chat.detail.none")} · {formatAmount(c.amount, c.currency, lang)} · {formatDate(c.date, lang)}
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

  // The trace is customer-visible and speaks the conversation language, its headings included (spec 07 AC-03).
  const tr = translator(lang);
  return (
    <DetailPanel
      {...common}
      title={<span lang={lang}>{tr("trace.panel.detailTitle")}</span>}
      description={<span lang={lang}>{tr("trace.panel.detailDescription")}</span>}
    >
      <div lang={lang}>
        <TraceSteps trace={detail.reply.trace} guardrails={detail.reply.guardrails} lang={lang} />
      </div>
    </DetailPanel>
  );
}
