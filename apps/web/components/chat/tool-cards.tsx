"use client";

// What the agent did in a turn, as it happens (spec 01 §6.4.1, spec 04 AC-38): the plan checklist of tool calls with
// their state, and the cards built from tool results (charges to pick, the rules' verdict, deadline, case). Customer
// words come from the event (server text from messages.yaml) or from lib/chat-stream.ts; a tool name is never shown.
// Requested and verified look different (constitution #4); color is never the only signal.
import { CheckIcon, CircleIcon, CreditCardIcon, ExternalLinkIcon, LoaderCircleIcon, ScaleIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { Task, TaskContent, TaskItem, TaskTrigger } from "@/components/ai-elements/task";
import { Button } from "@/components/ui/button";
import {
  type ActionCard,
  type ActionState,
  type CaseCard,
  type ChargeCard,
  type DeadlineCard,
  STATE_WORDS,
  TOOL_STATUS_WORDS,
  type ToolEvent,
  type ToolStatus,
  type VerdictCard,
  customerText,
  deadlineWords,
  formatAmount,
  formatDate,
} from "@/lib/chat-stream";
import type { Language } from "@/lib/types";
import { cn } from "@/lib/utils";

const COPY = {
  steps: { es: "Lo que estoy haciendo", pt: "O que estou fazendo" },
  done: { es: (n: number, total: number) => `${n} de ${total} pasos listos`, pt: (n: number, total: number) => `${n} de ${total} etapas prontas` },
  plan: { es: "Plan", pt: "Plano" },
  pick: { es: "Es este cargo", pt: "É esta cobrança" },
  details: { es: "Ver detalle", pt: "Ver detalhe" },
  card: { es: "Tarjeta terminada en", pt: "Cartão com final" },
  test: { es: "Cargo de prueba", pt: "Cobrança de teste" },
  noMerchant: { es: "Comercio sin nombre", pt: "Estabelecimento sem nome" },
  caseLabel: { es: "Caso", pt: "Caso" },
  follow: { es: "Seguir mi caso", pt: "Acompanhar meu caso" },
  pending: { es: "Fecha pendiente: una persona la confirma", pt: "Data pendente: uma pessoa confirma" },
} as const;

// --- the plan checklist ----------------------------------------------------------------------------------------------

function StatusIcon({ status }: { status: ToolStatus }) {
  if (status === "running") return <LoaderCircleIcon aria-hidden className="size-4 shrink-0 text-primary motion-safe:animate-spin" />;
  if (status === "failed") return <XIcon aria-hidden className="size-4 shrink-0 text-destructive" />;
  return <CheckIcon aria-hidden className="size-4 shrink-0 text-brand-teal dark:text-teal-300" />;
}

const STATE_CLASS: Record<ActionState, string> = {
  in_progress: "border-border text-muted-foreground",
  requested: "border-brand-amber/50 text-amber-700 dark:text-amber-400",
  verified: "border-brand-teal/50 bg-brand-teal/10 text-teal-700 dark:text-teal-300",
  not_confirmed: "border-destructive/50 text-destructive",
};

/** An action's state as a pill with its words; verified carries its V- id. */
export function StateBadge({ card, lang }: { card: Pick<ActionCard, "state" | "verification_id">; lang: Language }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", STATE_CLASS[card.state])}>
      {card.state === "verified" ? <CheckIcon aria-hidden className="size-3" /> : null}
      {STATE_WORDS[card.state][lang]}
      {card.state === "verified" && card.verification_id ? <span className="font-mono font-normal">· {card.verification_id}</span> : null}
    </span>
  );
}

/**
 * The turn's tool calls as a checklist (plan §3.3): each one running, done or failed, with its summary and the state
 * of any action it took. Open while the turn runs; a row opens its detail.
 */
export function PlanChecklist({
  tools,
  plan,
  lang,
  running,
  onOpen,
}: {
  tools: readonly ToolEvent[];
  plan?: readonly string[];
  lang: Language;
  running: boolean;
  onOpen?: (tool: ToolEvent) => void;
}) {
  if (tools.length === 0 && !plan?.length) return null;
  const done = tools.filter((t) => t.status === "done").length;
  const title =
    tools.length > 0 ? (
      <>
        <span className="font-medium text-foreground">{COPY.steps[lang]}</span>
        <span className="ml-2 text-xs">{COPY.done[lang](done, tools.length)}</span>
      </>
    ) : (
      <span className="font-medium text-foreground">{COPY.plan[lang]}</span>
    );
  return (
    <Task defaultOpen={running || tools.length === 0} className="rounded-xl border bg-card px-3 py-2.5" data-slot="plan-checklist">
      <TaskTrigger title={title} />
      <TaskContent>
        {tools.length > 0
          ? tools.map((t) => {
              const actions = t.cards.filter((c): c is ActionCard => c.type === "action");
              return (
                <TaskItem key={t.id}>
                  <button
                    type="button"
                    onClick={() => onOpen?.(t)}
                    disabled={!onOpen}
                    className="flex w-full items-start gap-2 rounded-md py-0.5 text-left hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-default"
                  >
                    <StatusIcon status={t.status} />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-foreground">
                        {customerText(t.title)}
                        <span className="sr-only">: {TOOL_STATUS_WORDS[t.status][lang]}</span>
                        {actions.map((a, i) => (
                          <StateBadge key={`${a.tool}-${i}`} card={a} lang={lang} />
                        ))}
                      </span>
                      {t.summary ? <span className="block text-xs">{customerText(t.summary)}</span> : null}
                    </span>
                  </button>
                </TaskItem>
              );
            })
          : plan?.map((line, i) => (
              <TaskItem key={`${i}-${line}`} className="flex items-start gap-2">
                <CircleIcon aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                <span>{customerText(line.replace(/^\s*\d+[.)]\s*/, ""))}</span>
              </TaskItem>
            ))}
      </TaskContent>
    </Task>
  );
}

// --- result cards ----------------------------------------------------------------------------------------------------

const CARD = "rounded-xl border bg-card p-3 text-sm";

/** A charge the search returned: the customer can pick it (spec 04 clarify: a tap on the card confirms it). */
export function ChargeCardView({
  card,
  lang,
  onPick,
  onOpen,
}: {
  card: ChargeCard;
  lang: Language;
  onPick?: (card: ChargeCard) => void;
  onOpen?: (card: ChargeCard) => void;
}) {
  return (
    <div className={cn(CARD, "flex flex-col gap-2")} data-slot="charge-card">
      <div className="flex items-start gap-3">
        <CreditCardIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{card.merchant ? customerText(card.merchant) : COPY.noMerchant[lang]}</p>
          <p className="text-xs text-muted-foreground">
            {formatDate(card.date, lang)} · {COPY.card[lang]} {card.last4}
            {card.synthetic ? ` · ${COPY.test[lang]}` : ""}
          </p>
        </div>
        <p className="shrink-0 font-semibold tabular-nums">{formatAmount(card.amount, card.currency, lang)}</p>
      </div>
      {onPick || onOpen ? (
        <div className="flex flex-wrap gap-2">
          {onPick ? (
            <Button size="sm" className="rounded-full px-3" onClick={() => onPick(card)}>
              {COPY.pick[lang]}
            </Button>
          ) : null}
          {onOpen ? (
            <Button size="sm" variant="ghost" className="rounded-full px-3" onClick={() => onOpen(card)}>
              {COPY.details[lang]}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** The rules' outcome in the customer's words (no score, zone or policy id). */
export function VerdictCardView({ card, onOpen, lang }: { card: VerdictCard; lang: Language; onOpen?: () => void }) {
  return (
    <div className={cn(CARD, "border-primary/30")} data-slot="verdict-card">
      <p className="flex items-start gap-2 font-medium">
        <ScaleIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-primary" />
        <span className="min-w-0 flex-1">{customerText(card.headline)}</span>
      </p>
      {card.actions.length ? (
        <ul className="mt-2 space-y-1 pl-6 text-xs text-muted-foreground">
          {card.actions.map((a) => (
            <li key={a} className="list-disc">
              {customerText(a)}
            </li>
          ))}
        </ul>
      ) : null}
      {onOpen ? (
        <Button size="sm" variant="ghost" className="mt-1 -ml-2 rounded-full px-2" onClick={onOpen}>
          {COPY.details[lang]}
        </Button>
      ) : null}
    </div>
  );
}

/** A legal deadline with its source as a named link (design pass 1: never a raw URL). */
export function DeadlineCardView({ card, lang }: { card: DeadlineCard; lang: Language }) {
  return (
    <div className={cn(CARD, "border-l-2 border-l-brand-amber")} data-slot="deadline-card">
      <p className="text-xs text-muted-foreground">{deadlineWords(card.kind, lang)}</p>
      <p className="font-medium">{card.date ? formatDate(card.date, lang) : COPY.pending[lang]}</p>
      {card.source_url ? (
        <a href={card.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-primary underline-offset-2 hover:underline">
          {customerText(card.source_label)}
          <ExternalLinkIcon aria-hidden className="size-3" />
        </a>
      ) : (
        <p className="mt-1 text-xs text-muted-foreground">{customerText(card.source_label)}</p>
      )}
    </div>
  );
}

/** The case the tools opened, with the way to follow it. */
export function CaseCardView({ card, lang }: { card: CaseCard; lang: Language }) {
  return (
    <div className={cn(CARD, "flex flex-wrap items-center justify-between gap-2")} data-slot="case-card">
      <p>
        <span className="text-xs text-muted-foreground">{COPY.caseLabel[lang]} </span>
        <span className="font-mono text-xs">{card.case_id}</span>
      </p>
      <Link href={`/case/${encodeURIComponent(card.case_id)}`} className="text-xs text-primary underline-offset-2 hover:underline">
        {COPY.follow[lang]} →
      </Link>
    </div>
  );
}
