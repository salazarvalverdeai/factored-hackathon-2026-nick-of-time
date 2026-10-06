"use client";

// The customer's history around the case, as cards: previous cases, transactions within ±30 days (the disputed one
// highlighted with a word, not only a color), cards, calls and notifications. "Detail →" opens the shared detail panel
// with the whole list (components/detail-panel.tsx, spec 07).
import { ArrowRight } from "lucide-react";
import { type ReactNode, useState } from "react";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { useLocale, useT } from "@/components/i18n-provider";
import { ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { CaseContext, ContextTransaction } from "@/lib/console-api";
import {
  callStatusLabel,
  cardStatusLabel,
  caseStatusLabel,
  channelLabel,
  deliveryLabel,
  formatAmount,
  formatDay,
  notificationEventLabel,
  outcomeLabel,
  productLabel,
} from "@/lib/console-view";
import { formatDateTime } from "@/lib/handoff-labels";
import type { Query } from "@/lib/use-query";
import { cn } from "@/lib/utils";

type Section = "cases" | "transactions" | "cards" | "calls" | "notifications";

const PREVIEW = 3;

export function CustomerHistory({ query }: { query: Query<CaseContext> }) {
  const t = useT();
  const { locale } = useLocale();
  const [open, setOpen] = useState<Section | null>(null);
  const title = (s: Section) => t(`console.history.sections.${s}`);
  return (
    <section aria-label={t("console.history.title")} className="space-y-2" data-slot="customer-history">
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("console.history.title")}
      </h3>
      {query.status === "loading" ? (
        <LoadingState label={t("console.history.reading")} className="p-3" />
      ) : query.status === "error" ? (
        <ErrorState title={t("console.history.none")} message={query.error.message} className="p-3" />
      ) : (
        <>
          <div className="grid gap-2 sm:grid-cols-2">
            <HistoryCard title={title("transactions")} count={query.data.transactions.length} onDetail={() => setOpen("transactions")} wide>
              {sortTx(query.data.transactions).slice(0, PREVIEW + 1).map((tx) => (
                <TxRow key={tx.transaction_id} t={tx} />
              ))}
            </HistoryCard>
            <HistoryCard title={title("cases")} count={query.data.previous_cases.length} onDetail={() => setOpen("cases")} empty={t("console.history.empty.cases")}>
              {query.data.previous_cases.slice(0, PREVIEW).map((p) => (
                <Row key={p.case_id} left={<span className="font-mono text-xs">{p.case_id}</span>} right={formatDay(locale, p.opened_at)}>
                  {caseStatusLabel(p.status, locale)} · {outcomeLabel(p.outcome, locale)}
                </Row>
              ))}
            </HistoryCard>
            <HistoryCard title={title("cards")} count={query.data.cards.length} onDetail={() => setOpen("cards")} empty={t("console.history.empty.cards")}>
              {query.data.cards.slice(0, PREVIEW).map((c) => (
                <Row key={c.last4 + c.product} left={`•••• ${c.last4}`} right={cardStatusLabel(c.status, locale)}>
                  {productLabel(c.product, locale)}
                </Row>
              ))}
            </HistoryCard>
            <HistoryCard title={title("calls")} count={query.data.calls.length} onDetail={() => setOpen("calls")} empty={t("console.history.empty.calls")}>
              {query.data.calls.slice(0, PREVIEW).map((c) => (
                <Row key={c.requested_at} left={formatDateTime(locale, c.requested_at)} right={callStatusLabel(c.status, locale)} />
              ))}
            </HistoryCard>
            <HistoryCard title={title("notifications")} count={query.data.notifications.length} onDetail={() => setOpen("notifications")} empty={t("console.history.empty.notifications")}>
              {query.data.notifications.slice(0, PREVIEW).map((n, i) => (
                <Row key={`${n.at}-${n.channel}-${i}`} left={notificationEventLabel(n.event, locale)} right={channelLabel(n.channel, locale)}>
                  {formatDateTime(locale, n.at)} · {deliveryLabel(n.status, locale)}
                </Row>
              ))}
            </HistoryCard>
          </div>
          <DetailPanel
            open={open !== null}
            onClose={() => setOpen(null)}
            title={open ? title(open) : ""}
            description={t("console.history.panelDescription")}
          >
            {open ? <SectionDetail section={open} data={query.data} /> : null}
          </DetailPanel>
        </>
      )}
    </section>
  );
}

const sortTx = (txs: ContextTransaction[]) =>
  [...txs].sort((a, b) => Number(b.disputed) - Number(a.disputed) || b.date.localeCompare(a.date));

function HistoryCard({
  title,
  count,
  onDetail,
  empty,
  wide,
  children,
}: {
  title: string;
  count: number;
  onDetail: () => void;
  empty?: string;
  wide?: boolean;
  children: ReactNode;
}) {
  const t = useT();
  return (
    <div className={cn("flex min-w-0 flex-col gap-2 rounded-xl border bg-card p-3", wide && "sm:col-span-2")}>
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-medium">
          {title} <span className="text-muted-foreground tabular-nums">({count})</span>
        </h4>
        {count > 0 ? (
          <Button size="xs" variant="ghost" onClick={onDetail} aria-label={t("console.history.detailAria", { title })}>
            {t("console.history.detail")} <ArrowRight aria-hidden />
          </Button>
        ) : null}
      </div>
      {count === 0 ? (
        <p className="text-xs text-muted-foreground">{empty ?? t("console.history.empty.any")}</p>
      ) : (
        <ul className="space-y-1">{children}</ul>
      )}
    </div>
  );
}

function Row({ left, right, children }: { left: ReactNode; right?: ReactNode; children?: ReactNode }) {
  return (
    <li className="min-w-0 text-sm">
      <span className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 truncate">{left}</span>
        {right ? <span className="shrink-0 text-xs text-muted-foreground">{right}</span> : null}
      </span>
      {children ? <span className="block truncate text-xs text-muted-foreground">{children}</span> : null}
    </li>
  );
}

function TxRow({ t }: { t: ContextTransaction }) {
  const tr = useT();
  const { locale } = useLocale();
  return (
    <li
      data-disputed={t.disputed || undefined}
      className={cn("min-w-0 rounded-lg px-2 py-1 text-sm", t.disputed ? "border border-brand-amber/60 bg-brand-amber/10" : "")}
    >
      <span className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 truncate">
          {t.disputed ? <Badge className="mr-1 bg-brand-amber/20 text-foreground">{tr("console.history.disputed")}</Badge> : null}
          {t.merchant}
        </span>
        <span className="shrink-0 font-mono text-xs tabular-nums">{formatAmount(locale, t.amount, t.currency)}</span>
      </span>
      <span className="block text-xs text-muted-foreground">
        {formatDay(locale, t.date)} · •••• {t.last4}
      </span>
    </li>
  );
}

function SectionDetail({ section, data }: { section: Section; data: CaseContext }) {
  const t = useT();
  const { locale } = useLocale();
  switch (section) {
    case "transactions":
      return (
        <ul className="space-y-1">
          {sortTx(data.transactions).map((tx) => (
            <TxRow key={tx.transaction_id} t={tx} />
          ))}
        </ul>
      );
    case "cases":
      return (
        <div className="space-y-4">
          {data.previous_cases.map((p) => (
            <DetailFields key={p.case_id}>
              <DetailField label={t("console.history.fields.case")} mono>{p.case_id}</DetailField>
              <DetailField label={t("console.history.fields.opened")}>{formatDateTime(locale, p.opened_at)}</DetailField>
              <DetailField label={t("console.history.fields.status")}>{caseStatusLabel(p.status, locale)}</DetailField>
              <DetailField label={t("console.history.fields.outcome")}>{outcomeLabel(p.outcome, locale)}</DetailField>
            </DetailFields>
          ))}
        </div>
      );
    case "cards":
      return (
        <div className="space-y-4">
          {data.cards.map((c) => (
            <DetailFields key={c.last4 + c.product}>
              <DetailField label={t("console.history.fields.card")}>•••• {c.last4}</DetailField>
              <DetailField label={t("console.history.fields.product")}>{productLabel(c.product, locale)}</DetailField>
              <DetailField label={t("console.history.fields.status")}>{cardStatusLabel(c.status, locale)}</DetailField>
            </DetailFields>
          ))}
        </div>
      );
    case "calls":
      return (
        <DetailFields>
          {data.calls.map((c) => (
            <DetailField key={c.requested_at} label={formatDateTime(locale, c.requested_at)}>
              {callStatusLabel(c.status, locale)}
            </DetailField>
          ))}
        </DetailFields>
      );
    case "notifications":
      return (
        <DetailFields>
          {data.notifications.map((n, i) => (
            <DetailField key={`${n.at}-${n.channel}-${i}`} label={formatDateTime(locale, n.at)}>
              {notificationEventLabel(n.event, locale)} · {channelLabel(n.channel, locale)} · {deliveryLabel(n.status, locale)}
            </DetailField>
          ))}
        </DetailFields>
      );
  }
}
