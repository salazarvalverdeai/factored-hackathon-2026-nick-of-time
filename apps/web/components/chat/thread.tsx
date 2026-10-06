"use client";

// The conversation (spec 07), composed from AI Elements: `conversation` (a log that sticks to the newest message),
// `message` with the brand chat-agent avatar, `chain-of-thought` for the inline steps, `task` for a stated plan,
// `confirmation` for "confirm before acting", `shimmer` before the first event, `suggestion` chips inside the thread.
// Each reply keeps one order: steps → text → cards → chips (the approved mock), and its parts enter in that order
// (lib/chat-motion.ts). The running turn and the message it becomes are the same element, so its steps collapse with a
// height animation when the reply completes. The reply being revealed is aria-busy until the turn ends, so a screen
// reader reads it once, whole; a polite status line names the running step.
import { type ReactNode, useState } from "react";
import { Confirmation, ConfirmationAction, ConfirmationActions, ConfirmationRequest, ConfirmationTitle } from "@/components/ai-elements/confirmation";
import { Conversation, ConversationContent, ConversationScrollButton } from "@/components/ai-elements/conversation";
import { Message, MessageContent } from "@/components/ai-elements/message";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Task, TaskContent, TaskItem, TaskTrigger } from "@/components/ai-elements/task";
import { ChatChips } from "@/components/chat/chips";
import { CitationContext, Markdown } from "@/components/chat/markdown";
import { Reveal, Stagger } from "@/components/chat/motion";
import { ReceiptCard } from "@/components/chat/receipt-card";
import { TurnSteps } from "@/components/chat/steps";
import { CaseCardView, ChargeCardView, DeadlineCardView, OptionCardView } from "@/components/chat/tool-cards";
import { DenyState } from "@/components/states";
import { type ReplyPart, partDelay } from "@/lib/chat-motion";
import {
  type ChargeCard,
  type ToolEvent,
  type VerdictCard,
  TOOL_STATUS_WORDS,
  cardsOf,
  citeFigures,
  customerText,
  formatAmount,
  formatClock,
  formatDate,
  localizeDates,
  offeredCharges,
  replyBody,
} from "@/lib/chat-stream";
import { CHAT_STRINGS as S } from "@/lib/chat-strings";
import type { AgentReply, Language, Suggestion, TurnAction } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface ChatMessage {
  id: number;
  role: "customer" | "agent";
  text: string;
  reply?: AgentReply;
  /** When this browser sent or received it (epoch ms): shown as the time of day only. */
  at: number;
  /** The progress labels streamed during the turn (an api that sends no tool events). */
  progress?: string[];
}

/** The turn running now, as paced for display: steps so far and the reply revealed so far. */
export interface LiveTurnView {
  tools: readonly ToolEvent[];
  progress: readonly string[];
  /** Markdown safe to render (lib/chat-reveal.ts `revealMarkdown`). */
  text: string;
}

/** What the right detail panel shows for the chat. */
export type ChatDetail =
  | { kind: "tool"; tool: ToolEvent; reply?: AgentReply }
  | { kind: "charge"; card: ChargeCard; reply?: AgentReply }
  | { kind: "rule"; card: VerdictCard; tool?: ToolEvent; reply?: AgentReply }
  | { kind: "trace"; reply: AgentReply };

const PICK_LABEL_TEXT = {
  es: (label: string) => `Es este cargo: ${localizeDates(customerText(label), "es")}`,
  pt: (label: string) => `É esta cobrança: ${localizeDates(customerText(label), "pt")}`,
} as const;

const PICK_TEXT = {
  es: (c: ChargeCard) => `Es este cargo: ${c.merchant ?? "sin comercio"}, ${formatAmount(c.amount, c.currency, "es")}, ${formatDate(c.date, "es")}`,
  pt: (c: ChargeCard) => `É esta cobrança: ${c.merchant ?? "sem estabelecimento"}, ${formatAmount(c.amount, c.currency, "pt")}, ${formatDate(c.date, "pt")}`,
} as const;

export function AgentAvatar({ className }: { className?: string }) {
  // Chat agent avatar: the symbol master, no face or mascot (docs/brand/BRAND.md §9).
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/brand/chat-agent-avatar.png" alt="" aria-hidden="true" className={cn("size-8 shrink-0 rounded-full", className)} />;
}

function Stamp({ at, lang, country, className }: { at: number; lang: Language; country?: string; className?: string }) {
  return (
    <time dateTime={new Date(at).toISOString()} className={cn("text-[0.7rem] tabular-nums text-muted-foreground", className)}>
      {formatClock(at, lang, country)}
    </time>
  );
}

function AgentShell({ children, busy }: { children: ReactNode; busy?: boolean }) {
  return (
    <Reveal kind="agent">
      <Message from="assistant" className="max-w-full flex-row items-start gap-2.5" data-slot="agent-message">
        {/* At 390 px the reply takes the full width; the avatar shows from sm up (the header carries it on phones). */}
        <AgentAvatar className="hidden sm:block" />
        <MessageContent className="w-full min-w-0 flex-1 gap-2.5 overflow-visible" aria-busy={busy || undefined}>
          {children}
        </MessageContent>
      </Message>
    </Reveal>
  );
}

/** The cards of a turn: charges to pick, and the deadline and case when no receipt carries them. */
function TurnCards({
  tools,
  reply,
  lang,
  country,
  demoDate,
  pickable,
  delay,
  onSend,
  onOpen,
}: {
  tools: readonly ToolEvent[];
  reply: AgentReply;
  lang: Language;
  country?: string;
  demoDate?: string | null;
  pickable: boolean;
  delay: number;
  onSend: (text: string, action?: TurnAction) => void;
  onOpen: (detail: ChatDetail) => void;
}) {
  const [chosen, setChosen] = useState<string | null>(null);
  const cards = cardsOf(tools);
  // Every charge the turn offers is a card, the one charge to confirm of D-067 included (spec 07 AC-28).
  const offered = offeredCharges(reply.options, tools);
  const charges = offered.flatMap((o) => (o.card ? [o.card] : []));
  const rest = reply.receipt ? [] : cards.filter((c) => c.type === "deadline" || c.type === "case");
  // One charge to confirm: its chips ("Sí, es ese cargo" · "No es ese cargo") answer, so the card has no pick button.
  const canPick = pickable && (reply.options ? reply.options.length > 1 : true);
  const pick = (id: string, text: string) => {
    setChosen(id);
    onSend(text, { type: "choose_option", value: id });
  };
  return (
    <>
      {offered.length && !reply.receipt ? (
        <Stagger className="grid gap-2" role="list" base={delay}>
          {offered.map((o) =>
            o.card ? (
              <ChargeCardView
                key={o.id}
                card={o.card}
                lang={lang}
                selected={chosen === null ? null : chosen === o.id}
                onPick={canPick ? (card) => pick(card.transaction_id, PICK_TEXT[lang](card)) : undefined}
                onOpen={(card) => onOpen({ kind: "charge", card, reply })}
              />
            ) : (
              <OptionCardView key={o.id} label={o.label ?? ""} lang={lang} onPick={canPick ? () => pick(o.id, PICK_LABEL_TEXT[lang](o.label ?? "")) : undefined} />
            ),
          )}
        </Stagger>
      ) : null}
      {rest.length ? (
        <Stagger className="grid gap-2" base={delay}>
          {rest.map((c, i) =>
            c.type === "deadline" ? <DeadlineCardView key={`d-${i}`} card={c} lang={lang} /> : c.type === "case" ? <CaseCardView key={`c-${c.case_id}`} card={c} lang={lang} /> : null,
          )}
        </Stagger>
      ) : null}
      {reply.receipt ? (
        <ReceiptCard receipt={reply.receipt} country={country} demoDate={demoDate} charge={charges.length === 1 ? charges[0] : undefined} />
      ) : null}
    </>
  );
}

/** "Confirm before acting" (spec 04 AC-16, spec 07 AC-06): the turn's confirm chip, or a plain yes, and a plain no. */
function ConfirmBeforeActing({ reply, lang, onSend }: { reply: AgentReply; lang: Language; onSend: (text: string, action?: TurnAction) => void }) {
  const yes = reply.suggestions?.find((s) => s.action?.type === "confirm");
  return (
    <Confirmation approval={{ id: "confirm" }} state="approval-requested" className="border-primary/30">
      <ConfirmationTitle className="font-medium text-foreground">{S.confirmTitle[lang]}</ConfirmationTitle>
      <ConfirmationRequest>{null}</ConfirmationRequest>
      <ConfirmationActions className="flex-wrap">
        <ConfirmationAction variant="outline" onClick={() => onSend(S.confirmNo[lang])}>
          {S.confirmNo[lang]}
        </ConfirmationAction>
        <ConfirmationAction onClick={() => onSend(yes?.text ?? S.confirmYes[lang], yes?.action)}>{yes?.label ?? S.confirmYes[lang]}</ConfirmationAction>
      </ConfirmationActions>
    </Confirmation>
  );
}

/** One agent turn: the running one (`live`) and the message it becomes are the same element. */
function AgentTurn({
  message,
  live,
  thinking = false,
  last,
  busy,
  lang,
  country,
  demoDate,
  onSend,
  onOpen,
}: {
  message?: ChatMessage;
  live?: LiveTurnView;
  thinking?: boolean;
  last: boolean;
  busy: boolean;
  lang: Language;
  country?: string;
  demoDate?: string | null;
  onSend: (text: string, action?: TurnAction) => void;
  onOpen: (detail: ChatDetail) => void;
}) {
  const reply = message?.reply;
  const running = Boolean(live);
  const tools = live ? live.tools : (reply?.tools ?? []);
  const progress = live ? live.progress : message?.progress;
  const body = live ? live.text : replyBody(message?.text ?? "", reply?.receipt, lang);
  const plan = !running && !tools.length && reply?.plan?.length ? reply.plan : null;
  const hasSteps = tools.length > 0 || (progress?.length ?? 0) > 0;
  const hasCards = Boolean(
    reply && (reply.receipt || offeredCharges(reply.options, tools).length > 0 || cardsOf(tools).some((c) => c.type === "deadline" || c.type === "case")),
  );
  const parts: ReplyPart[] = [hasSteps ? "steps" : null, body ? "text" : null, hasCards ? "cards" : null].filter((p): p is ReplyPart => p !== null);

  if (thinking)
    return (
      <AgentShell busy>
        <Shimmer as="p" className="text-sm" duration={1.4}>
          {S.thinking[lang]}
        </Shimmer>
      </AgentShell>
    );

  return (
    <AgentShell busy={running}>
      {hasSteps ? (
        <Reveal kind="part" delay={partDelay("steps", parts)}>
          <TurnSteps
            tools={tools}
            progress={progress}
            running={running}
            lang={lang}
            onOpenTool={(tool) => onOpen({ kind: "tool", tool, reply })}
            onOpenRule={(card, tool) => onOpen({ kind: "rule", card, tool, reply })}
          />
        </Reveal>
      ) : null}
      {plan ? (
        <Task defaultOpen className="rounded-xl border bg-card px-3 py-2.5" data-slot="plan">
          <TaskTrigger title={<span className="font-medium text-foreground">{lang === "es" ? "Plan" : "Plano"}</span>} />
          <TaskContent>
            {plan.map((line, i) => (
              <TaskItem key={`${i}-${line}`}>{customerText(line.replace(/^\s*\d+[.)]\s*/, ""))}</TaskItem>
            ))}
          </TaskContent>
        </Task>
      ) : null}
      {reply?.deny ? (
        <DenyState message={body} />
      ) : body ? (
        <Reveal kind="part" delay={running ? 0 : partDelay("text", parts)} data-slot="reply-text">
          {running ? (
            <Markdown text={body} streaming />
          ) : (
            <CitationContext.Provider value={{ tools, lang, onOpen: (tool) => onOpen({ kind: "tool", tool, reply }) }}>
              <Markdown text={citeFigures(body, tools, lang)} />
            </CitationContext.Provider>
          )}
        </Reveal>
      ) : null}
      {reply && hasCards ? (
        <TurnCards tools={tools} reply={reply} lang={lang} country={country} demoDate={demoDate} pickable={last && !busy} delay={partDelay("cards", parts)} onSend={onSend} onOpen={onOpen} />
      ) : null}
      {reply?.awaitingConfirmation && last && !busy ? <ConfirmBeforeActing reply={reply} lang={lang} onSend={onSend} /> : null}
      {message ? <Stamp at={message.at} lang={lang} country={country} /> : null}
    </AgentShell>
  );
}

export function ChatThread({
  messages,
  live,
  lang,
  country,
  demoDate,
  note,
  greeting,
  chips,
  footer,
  busy,
  onSend,
  onOpen,
  className,
}: {
  messages: readonly ChatMessage[];
  /** The turn running now, paced for display, under the id the message will take; null when none runs. */
  live: { id: number; view: LiveTurnView | null; thinking: boolean } | null;
  lang: Language;
  country?: string;
  /** Replay sessions only: the demo "today", shown on the receipt instead of the real clock. */
  demoDate?: string | null;
  /** The one-line demo note at the top of the conversation. */
  note?: ReactNode;
  greeting?: ReactNode;
  /** The chips under the last message (the turn's, or examples before the first one). */
  chips: readonly Suggestion[] | undefined;
  /** Shown after the last message (an error). */
  footer?: ReactNode;
  busy: boolean;
  onSend: (text: string, action?: TurnAction) => void;
  onOpen: (detail: ChatDetail) => void;
  className?: string;
}) {
  const lastId = messages.length ? messages[messages.length - 1].id : null;
  const running = live?.view?.tools.findLast((t) => t.status === "running");
  const lastReply = [...messages].reverse().find((m) => m.reply)?.reply;
  const turn = (m: ChatMessage) =>
    m.role === "customer" ? (
      <Reveal key={`m-${m.id}`} kind="user" className="flex flex-col items-end gap-1">
        <Message from="user" data-slot="customer-message" className="max-w-[85%] items-end gap-1">
          <MessageContent>
            <p className="whitespace-pre-line break-words">{m.text}</p>
          </MessageContent>
        </Message>
        <Stamp at={m.at} lang={lang} country={country} />
      </Reveal>
    ) : (
      <AgentTurn key={`m-${m.id}`} message={m} last={m.id === lastId} busy={busy} lang={lang} country={country} demoDate={demoDate} onSend={onSend} onOpen={onOpen} />
    );
  // One keyed list: the running turn keeps its element when it becomes a message (same key), so its state carries over.
  const items = [
    ...messages.map(turn),
    ...(live
      ? [
          <AgentTurn
            key={`m-${live.id}`}
            live={live.view ?? { tools: [], progress: [], text: "" }}
            thinking={live.thinking}
            last
            busy
            lang={lang}
            country={country}
            demoDate={demoDate}
            onSend={onSend}
            onOpen={onOpen}
          />,
        ]
      : []),
  ];
  return (
    <Conversation className={cn("min-h-0", className)} aria-label="Conversation">
      <ConversationContent className="gap-5 px-3 py-4 sm:px-5">
        {note ? <p className="mx-auto w-fit max-w-full rounded-full border px-3 py-1 text-center text-xs text-muted-foreground">{note}</p> : null}
        {greeting ? <AgentShell>{greeting}</AgentShell> : null}
        {items}
        {!busy ? (
          <Reveal kind="chips" delay={0.12} className="sm:pl-10.5">
            {/* Under "confirm before acting" the confirm chip lives in the confirmation; the person chip always stays. */}
            <ChatChips
              suggestions={lastReply?.awaitingConfirmation ? chips?.filter((c) => c.action?.type !== "confirm") : chips}
              lang={lang}
              disabled={busy}
              onSend={onSend}
            />
          </Reveal>
        ) : null}
        {footer}
      </ConversationContent>
      <ConversationScrollButton />
      <p className="sr-only" role="status" aria-live="polite">
        {running ? `${customerText(running.title)}: ${TOOL_STATUS_WORDS.running[lang]}` : live?.thinking ? S.thinking[lang] : ""}
      </p>
    </Conversation>
  );
}
