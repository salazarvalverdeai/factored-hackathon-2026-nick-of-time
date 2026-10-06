"use client";

// The composer (spec 07 AC-24) on AI Elements `prompt-input`: a growing textarea (Enter sends, Shift+Enter breaks the
// line), the mic inside it (PromptInputTools, #205's push-to-talk) and the send button, which never clips: the footer
// wraps instead of overflowing at 390 px or when zoomed.
import { SendHorizontalIcon } from "lucide-react";
import type { ReactNode, Ref } from "react";
import { PromptInput, PromptInputFooter, PromptInputSubmit, PromptInputTextarea, PromptInputTools } from "@/components/ai-elements/prompt-input";
import { CHAT_STRINGS as S } from "@/lib/chat-strings";
import type { Language } from "@/lib/types";

export function ChatComposer({
  lang,
  value,
  onChange,
  onSubmit,
  busy,
  tools,
  textareaRef,
  voice,
}: {
  lang: Language;
  value: string;
  onChange: (text: string) => void;
  onSubmit: (text: string) => void;
  busy: boolean;
  /** The mic (and any other control) inside the composer. */
  tools?: ReactNode;
  textareaRef?: Ref<HTMLTextAreaElement>;
  /** True when the mic is offered: the placeholder then says the customer can talk. */
  voice?: boolean;
}) {
  return (
    <PromptInput onSubmit={() => onSubmit(value)} className="rounded-2xl" data-slot="composer">
      <PromptInputTextarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.currentTarget.value)}
        placeholder={voice ? S.placeholder[lang] : S.placeholderTyped[lang]}
        aria-label={S.placeholderTyped[lang]}
        className="min-h-10 text-sm"
      />
      <PromptInputFooter className="flex-wrap">
        <PromptInputTools className="min-w-0 flex-1">{tools}</PromptInputTools>
        <PromptInputSubmit disabled={busy || !value.trim()} status={busy ? "submitted" : undefined} aria-label={S.send[lang]} className="ml-auto shrink-0 rounded-full">
          {busy ? undefined : <SendHorizontalIcon aria-hidden className="size-4" />}
        </PromptInputSubmit>
      </PromptInputFooter>
    </PromptInput>
  );
}
