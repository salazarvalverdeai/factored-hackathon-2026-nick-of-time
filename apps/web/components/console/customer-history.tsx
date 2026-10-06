"use client";

// The customer's history around the case, as cards: previous cases, transactions within ±30 days (the disputed one
// highlighted with a word, not only a color), cards, calls and notifications. "Detail →" opens the shared detail panel
// with the whole list (components/detail-panel.tsx, spec 07).
import { ArrowRight } from "lucide-react";
import { type ReactNode, useState } from "react";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { ErrorState, LoadingState } from "@/components/states";
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

const TITLES: Record<Section, string> = {
  cases: "Previous cases",
  transactions: "Transactions ±30 days",
  cards: "Cards",
  calls: "Calls",
  notifications: "Notifications",
};

const PREVIEW = 3;

export function CustomerHistory({ query }: { query: Query<CaseContext> }) {
  const [open, setOpen] = useState<Section | null>(null);
  return (
    <section aria-label="Customer history" className="space-y-2" data-slot="customer-history">
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Customer history
      </h3>
      {query.status === "loading" ? (
        <LoadingState label="Reading the customer's history…" className="p-3" />
      ) : query.status === "error" ? (
        <ErrorState title="No history" message={query.error.message} className="p-3" />
      ) : (
        <>
          <div className="grid gap-2 sm:grid-cols-2">
            <HistoryCard title={TITLES.transactions} count={query.data.transactions.length} onDetail={() => setOpen("transactions")} wide>
              {sortTx(query.data.transactions).slice(0, PREVIEW + 1).map((t) => (
                <TxRow key={t.transaction_id} t={t} />
              ))}
            </HistoryCard>
            <HistoryCard title={TITLES.cases} count={query.data.previous_cases.length} onDetail={() => setOpen("cases")} empty="No previous cases">
              {query.data.previous_cases.slice(0, PREVIEW).map((p) => (
                <Row key={p.case_id} left={<span className="font-mono text-xs">{p.case_id}</span>} right={formatDay(p.opened_at)}>
                  {caseStatusLabel(p.status)} · {outcomeLabel(p.outcome)}
                </Row>
              ))}
            </HistoryCard>
            <HistoryCard title={TITLES.cards} count={query.data.cards.length} onDetail={() => setOpen("cards")} empty="No cards on record">
              {query.data.cards.slice(0, PREVIEW).map((c) => (
                <Row key={c.last4 + c.product} left={`•••• ${c.last4}`} right={cardStatusLabel(c.status)}>
                  {productLabel(c.product)}
                </Row>
              ))}
            </HistoryCard>
            <HistoryCard title={TITLES.calls} count={query.data.calls.length} onDetail={() => setOpen("calls")} empty="No calls requested">
              {query.data.calls.slice(0, PREVIEW).map((c) => (
                <Row key={c.requested_at} left={formatDateTime(c.requested_at)} right={callStatusLabel(c.status)} />
              ))}
            </HistoryCard>
            <HistoryCard title={TITLES.notifications} count={query.data.notifications.length} onDetail={() => setOpen("notifications")} empty="No notifications yet">
              {query.data.notifications.slice(0, PREVIEW).map((n, i) => (
                <Row key={`${n.at}-${n.channel}-${i}`} left={notificationEventLabel(n.event)} right={channelLabel(n.channel)}>
                  {formatDateTime(n.at)} · {deliveryLabel(n.status)}
                </Row>
              ))}
            </HistoryCard>
          </div>
          <DetailPanel
            open={open !== null}
            onClose={() => setOpen(null)}
            title={open ? TITLES[open] : ""}
            description="From the bank's records for this customer, read by the console."
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
  empty = "Nothing on record",
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
  return (
    <div className={cn("flex min-w-0 flex-col gap-2 rounded-xl border bg-card p-3", wide && "sm:col-span-2")}>
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-medium">
          {title} <span className="text-muted-foreground tabular-nums">({count})</span>
        </h4>
        {count > 0 ? (
          <Button size="xs" variant="ghost" onClick={onDetail} aria-label={`${title}: detail`}>
            Detail <ArrowRight aria-hidden />
          </Button>
        ) : null}
      </div>
      {count === 0 ? <p className="text-xs text-muted-foreground">{empty}</p> : <ul className="space-y-1">{children}</ul>}
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
  return (
    <li
      data-disputed={t.disputed || undefined}
      className={cn("min-w-0 rounded-lg px-2 py-1 text-sm", t.disputed ? "border border-brand-amber/60 bg-brand-amber/10" : "")}
    >
      <span className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 truncate">
          {t.disputed ? <span className="mr-1 rounded-4xl bg-brand-amber/20 px-1.5 text-xs font-medium">Disputed</span> : null}
          {t.merchant}
        </span>
        <span className="shrink-0 font-mono text-xs tabular-nums">{formatAmount(t.amount, t.currency)}</span>
      </span>
      <span className="block text-xs text-muted-foreground">
        {formatDay(t.date)} · •••• {t.last4}
      </span>
    </li>
  );
}

function SectionDetail({ section, data }: { section: Section; data: CaseContext }) {
  switch (section) {
    case "transactions":
      return (
        <ul className="space-y-1">
          {sortTx(data.transactions).map((t) => (
            <TxRow key={t.transaction_id} t={t} />
          ))}
        </ul>
      );
    case "cases":
      return (
        <div className="space-y-4">
          {data.previous_cases.map((p) => (
            <DetailFields key={p.case_id}>
              <DetailField label="Case" mono>{p.case_id}</DetailField>
              <DetailField label="Opened">{formatDateTime(p.opened_at)}</DetailField>
              <DetailField label="Status">{caseStatusLabel(p.status)}</DetailField>
              <DetailField label="Outcome">{outcomeLabel(p.outcome)}</DetailField>
            </DetailFields>
          ))}
        </div>
      );
    case "cards":
      return (
        <div className="space-y-4">
          {data.cards.map((c) => (
            <DetailFields key={c.last4 + c.product}>
              <DetailField label="Card">•••• {c.last4}</DetailField>
              <DetailField label="Product">{productLabel(c.product)}</DetailField>
              <DetailField label="Status">{cardStatusLabel(c.status)}</DetailField>
            </DetailFields>
          ))}
        </div>
      );
    case "calls":
      return (
        <DetailFields>
          {data.calls.map((c) => (
            <DetailField key={c.requested_at} label={formatDateTime(c.requested_at)}>
              {callStatusLabel(c.status)}
            </DetailField>
          ))}
        </DetailFields>
      );
    case "notifications":
      return (
        <DetailFields>
          {data.notifications.map((n, i) => (
            <DetailField key={`${n.at}-${n.channel}-${i}`} label={formatDateTime(n.at)}>
              {notificationEventLabel(n.event)} · {channelLabel(n.channel)} · {deliveryLabel(n.status)}
            </DetailField>
          ))}
        </DetailFields>
      );
  }
}
