"use client";

// The customer–agent transcript of a case, read-only and analyst-only (spec 08 AC-15). It draws messages the way the
// chat does (spec 07): the customer's on the right, the agent's on the left as safe markdown (components/chat/markdown.tsx,
// reused, not forked), inside the AI Elements conversation log. Nothing here can send a message or press a chip.
import { Conversation, ConversationContent, ConversationEmptyState, ConversationScrollButton } from "@/components/ai-elements/conversation";
import { Markdown } from "@/components/chat/markdown";
import { useLocale, useT } from "@/components/i18n-provider";
import { ErrorState, LoadingState } from "@/components/states";
import type { CaseConversation } from "@/lib/console-api";
import { formatDateTime, formatTime } from "@/lib/handoff-labels";
import type { Query } from "@/lib/use-query";

export function ConversationTranscript({ query }: { query: Query<CaseConversation> }) {
  const t = useT();
  const { locale } = useLocale();
  if (query.status === "loading") return <LoadingState label={t("console.transcript.reading")} className="p-3" />;
  if (query.status === "error") return <ErrorState title={t("console.transcript.none")} message={query.error.message} className="p-3" />;
  const threads = query.data.threads.filter((th) => th.messages.length > 0);
  return (
    <Conversation className="h-[28rem] min-h-0 rounded-xl border bg-background" aria-label={t("console.transcript.aria")}>
      <ConversationContent className="gap-4 p-3 sm:p-4">
        {threads.length === 0 ? (
          <ConversationEmptyState title={t("console.transcript.emptyTitle")} description={t("console.transcript.emptyDescription")} />
        ) : (
          threads.map((th) => (
            <section key={th.thread_id} aria-label={t("console.transcript.sessionStarted", { at: formatDateTime(locale, th.session_started_at) })} className="flex flex-col gap-4">
              <p className="text-center text-xs text-muted-foreground">{t("console.transcript.sessionStarted", { at: formatDateTime(locale, th.session_started_at) })}</p>
              {th.messages.map((m, i) =>
                m.role === "customer" ? (
                  <div key={i} className="flex flex-col items-end gap-0.5" data-slot="customer-message">
                    <p className="max-w-[85%] whitespace-pre-line break-words rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2.5 text-sm text-primary-foreground">
                      <span className="sr-only">{t("console.transcript.customer")} </span>
                      {m.text}
                    </p>
                    <time dateTime={m.at} className="text-[0.7rem] text-muted-foreground">
                      {formatTime(locale, m.at)}
                    </time>
                  </div>
                ) : (
                  <div key={i} className="flex items-start gap-2.5" data-slot="agent-message">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src="/brand/chat-agent-avatar.png" alt="" aria-hidden="true" className="size-7 shrink-0 rounded-full" />
                    <div className="min-w-0 flex-1 space-y-0.5">
                      <div className="rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2.5">
                        <span className="sr-only">{t("console.transcript.agent")} </span>
                        <Markdown text={m.text} />
                      </div>
                      <time dateTime={m.at} className="text-[0.7rem] text-muted-foreground">
                        {formatTime(locale, m.at)}
                      </time>
                    </div>
                  </div>
                ),
              )}
            </section>
          ))
        )}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  );
}
