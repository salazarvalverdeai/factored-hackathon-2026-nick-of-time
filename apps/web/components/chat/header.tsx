"use client";

// The chat's header bar (spec 07 AC-24, the approved mock): the agent avatar, "Asistente de disputas", the customer's
// name, and "Nuevo caso", which starts a fresh thread. Extra controls (read aloud, sign out) sit at the end.
import { RotateCcwIcon } from "lucide-react";
import type { ReactNode } from "react";
import { AgentAvatar } from "@/components/chat/thread";
import { Button } from "@/components/ui/button";
import { CHAT_STRINGS as S } from "@/lib/chat-strings";
import type { Language } from "@/lib/types";

export function ChatHeader({ lang, name, onNewCase, newCaseDisabled, children }: { lang: Language; name?: string | null; onNewCase: () => void; newCaseDisabled?: boolean; children?: ReactNode }) {
  return (
    <header className="flex items-center gap-x-2 gap-y-2 border-b px-3 py-2.5 sm:gap-x-3 sm:px-4" data-slot="chat-header">
      <AgentAvatar className="size-9" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold leading-tight">{S.assistant[lang]}</p>
        <p className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
          <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-brand-teal" />
          {S.online[lang]}
          {name ? (
            <>
              {" · "}
              <span className="hidden sm:inline">{S.talkingWith[lang](name)}</span>
              <span className="sm:hidden">{name}</span>
            </>
          ) : null}
        </p>
      </div>
      <div className="flex shrink-0 items-center justify-end gap-1">
        {children}
        <Button size="sm" variant="outline" onClick={onNewCase} disabled={newCaseDisabled} title={S.newCaseHint[lang]}>
          <RotateCcwIcon aria-hidden className="size-3.5" />
          {S.newCase[lang]}
        </Button>
      </div>
    </header>
  );
}
