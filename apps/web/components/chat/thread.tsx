"use client";

// The conversation (spec 07): a full-height log that sticks to the newest message (AI Elements `conversation`), the
// brand chat-agent avatar on agent messages, each turn's plan checklist and cards as the tools report them, the reply
// as safe markdown while it streams, and the verified receipt. The streaming reply is aria-busy until the turn ends,
// so a screen reader reads it once, whole; a polite status line says which step is running.
import type { ReactNode } from "react";
import { Conversation, ConversationContent, ConversationScrollButton } from "@/components/ai-elements/conversation";
import { Markdown } from "@/components/chat/markdown";
import { ReceiptCard } from "@/components/chat/receipt-card";
import { CaseCardView, ChargeCardView, DeadlineCardView, PlanChecklist, VerdictCardView } from "@/components/chat/tool-cards";
import { DenyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  type ChargeCard,
  type ToolEvent,
  type TurnStream,
  type VerdictCard,
  TOOL_STATUS_WORDS,
  cardsOf,
  customerText,
  formatAmount,
  formatDate,
  replyBody,
} from "@/lib/chat-stream";
import type { AgentReply, Language, TurnAction } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface ChatMessage {
  id: number;
  role: "customer" | "agent";
  text: string;
  reply?: AgentReply;
}

/** What the right detail panel shows for the chat. */
export type ChatDetail =
  | { kind: "tool"; tool: ToolEvent }
  | { kind: "charge"; card: ChargeCard }
  | { kind: "verdict"; card: VerdictCard }
  | { kind: "trace"; reply: AgentReply };

const COPY = {
  working: { es: "Estoy trabajando en tu solicitud…", pt: "Estou trabalhando no seu pedido…" },
  why: { es: "Cómo lo decidí", pt: "Como decidi" },
  pickText: {
    es: (c: ChargeCard) => `Es este cargo: ${c.merchant ?? "sin comercio"}, ${formatAmount(c.amount, c.currency, "es")}, ${formatDate(c.date, "es")}`,
    pt: (c: ChargeCard) => `É esta cobrança: ${c.merchant ?? "sem estabelecimento"}, ${formatAmount(c.amount, c.currency, "pt")}, ${formatDate(c.date, "pt")}`,
  },
} as const;

function AgentAvatar() {
  // Chat agent avatar: the symbol master, no face or mascot (docs/brand/BRAND.md §9).
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/brand/chat-agent-avatar.png" alt="" aria-hidden="true" className="size-8 shrink-0 rounded-full" />;
}

/** The cards of a turn: charges to pick, the verdict, and the deadline and case when no receipt carries them. */
function TurnCards({
  tools,
  hasReceipt,
  lang,
  pickable,
  onPick,
  onOpen,
}: {
  tools: readonly ToolEvent[];
  hasReceipt: boolean;
  lang: Language;
  pickable: boolean;
  onPick: (card: ChargeCard) => void;
  onOpen: (detail: ChatDetail) => void;
}) {
  const cards = cardsOf(tools);
  const charges = cards.filter((c): c is ChargeCard => c.type === "charge");
  const shown = cards.filter((c) => c.type === "verdict" || (!hasReceipt && (c.type === "deadline" || c.type === "case")));
  if (charges.length === 0 && shown.length === 0) return null;
  return (
    <div className="grid gap-2">
      {charges.map((c) => (
        <ChargeCardView
          key={c.transaction_id}
          card={c}
          lang={lang}
          onPick={pickable && !hasReceipt ? onPick : undefined}
          onOpen={(card) => onOpen({ kind: "charge", card })}
        />
      ))}
      {shown.map((c, i) =>
        c.type === "verdict" ? (
          <VerdictCardView key={`v-${i}`} card={c} lang={lang} onOpen={() => onOpen({ kind: "verdict", card: c })} />
        ) : c.type === "deadline" ? (
          <DeadlineCardView key={`d-${i}`} card={c} lang={lang} />
        ) : c.type === "case" ? (
          <CaseCardView key={`c-${c.case_id}`} card={c} lang={lang} />
        ) : null,
      )}
    </div>
  );
}

function AgentTurn({
  reply,
  text,
  tools,
  streaming,
  lang,
  country,
  demoDate,
  pickable,
  onSend,
  onOpen,
}: {
  reply?: AgentReply;
  text: string;
  tools: readonly ToolEvent[];
  streaming: boolean;
  lang: Language;
  country?: string;
  demoDate?: string | null;
  pickable: boolean;
  onSend: (text: string, action?: TurnAction) => void;
  onOpen: (detail: ChatDetail) => void;
}) {
  const body = streaming ? customerText(text) : replyBody(text, reply?.receipt, lang);
  return (
    <div className="flex items-start gap-2.5" data-slot="agent-message">
      <AgentAvatar />
      <div className="min-w-0 flex-1 space-y-2.5">
        <PlanChecklist
          tools={tools}
          lang={lang}
          running={streaming}
          onOpen={(tool) => onOpen({ kind: "tool", tool })}
        />
        <TurnCards
          tools={tools}
          hasReceipt={Boolean(reply?.receipt)}
          lang={lang}
          pickable={pickable && !streaming}
          onPick={(card) => onSend(COPY.pickText[lang](card), { type: "choose_option", value: card.transaction_id })}
          onOpen={onOpen}
        />
        {reply?.deny ? (
          <DenyState message={body} />
        ) : body ? (
          <div className="w-fit max-w-full rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2.5" aria-busy={streaming || undefined}>
            <Markdown text={body} streaming={streaming} />
          </div>
        ) : streaming ? (
          <p className="text-sm text-muted-foreground motion-safe:animate-pulse">{COPY.working[lang]}</p>
        ) : null}
        {reply?.receipt ? <ReceiptCard receipt={reply.receipt} country={country} demoDate={demoDate} /> : null}
        {reply && !streaming && (reply.trace.length > 0 || reply.guardrails.length > 0) ? (
          <Button variant="ghost" size="xs" className="-ml-2 text-muted-foreground" onClick={() => onOpen({ kind: "trace", reply })}>
            {COPY.why[lang]} →
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function ChatThread({
  messages,
  live,
  lang,
  country,
  demoDate,
  greeting,
  footer,
  busy,
  onSend,
  onOpen,
  className,
}: {
  messages: readonly ChatMessage[];
  /** The turn running now: its tool calls and the reply being written. */
  live: TurnStream | null;
  lang: Language;
  country?: string;
  /** Replay sessions only: the demo "today", shown on the receipt instead of the real clock. */
  demoDate?: string | null;
  greeting?: ReactNode;
  /** Shown after the last message (an error). */
  footer?: ReactNode;
  busy: boolean;
  onSend: (text: string, action?: TurnAction) => void;
  onOpen: (detail: ChatDetail) => void;
  className?: string;
}) {
  const lastAgent = [...messages].reverse().find((m) => m.role === "agent")?.id;
  const running = live?.tools.find((t) => t.status === "running");
  return (
    <Conversation className={cn("min-h-0 rounded-xl border bg-background", className)} aria-label="Conversation">
      <ConversationContent className="gap-5 p-3 sm:p-4">
        {greeting ? (
          <div className="flex items-start gap-2.5">
            <AgentAvatar />
            <div className="min-w-0 flex-1 space-y-1 rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2.5 text-sm">{greeting}</div>
          </div>
        ) : null}
        {messages.map((m) =>
          m.role === "customer" ? (
            <div key={m.id} className="flex justify-end" data-slot="customer-message">
              <p className="max-w-[85%] whitespace-pre-line break-words rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2.5 text-sm text-primary-foreground">
                {m.text}
              </p>
            </div>
          ) : (
            <AgentTurn
              key={m.id}
              reply={m.reply}
              text={m.text}
              tools={m.reply?.tools ?? []}
              streaming={false}
              lang={lang}
              country={country}
              demoDate={demoDate}
              pickable={m.id === lastAgent && !busy}
              onSend={onSend}
              onOpen={onOpen}
            />
          ),
        )}
        {live ? (
          <AgentTurn text={live.text} tools={live.tools} streaming lang={lang} country={country} demoDate={demoDate} pickable={false} onSend={onSend} onOpen={onOpen} />
        ) : null}
        {footer}
      </ConversationContent>
      <ConversationScrollButton />
      <p className="sr-only" role="status" aria-live="polite">
        {running ? `${customerText(running.title)}: ${TOOL_STATUS_WORDS.running[lang]}` : ""}
      </p>
    </Conversation>
  );
}
