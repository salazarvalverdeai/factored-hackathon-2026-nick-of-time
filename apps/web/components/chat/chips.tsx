"use client";

// The chips under the last reply, as pills (AI Elements `suggestion`): at most three from the turn, and "talk to a
// person" always among them (spec 04 AC-20, AC-39; plan §4.2). An action chip sends its action, never its text;
// a link chip opens a path on our own host. The chips speak the session's language; the group's name follows the UI locale.
import Link from "next/link";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { useT } from "@/components/i18n-provider";
import { chipsFor, isPersonChip } from "@/lib/chat-stream";
import type { Language, Suggestion as Chip, TurnAction } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ChatChips({
  suggestions,
  lang,
  disabled,
  onSend,
  label,
}: {
  suggestions: readonly Chip[] | undefined;
  lang: Language;
  disabled?: boolean;
  onSend: (text: string, action?: TurnAction) => void;
  label?: string;
}) {
  const t = useT();
  const chips = chipsFor(suggestions, lang);
  return (
    <Suggestions role="group" aria-label={label ?? t("chat.conversation.suggestedReplies")} data-slot="chat-chips">
      {chips.map((chip) =>
        chip.href ? (
          <Link
            key={chip.label}
            href={chip.href}
            className="inline-flex min-h-8 items-center rounded-full border px-3.5 py-1.5 text-[0.8rem] font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
          >
            {chip.label}
          </Link>
        ) : (
          <Suggestion
            key={chip.label}
            suggestion={chip.label}
            disabled={disabled}
            onClick={() => onSend(chip.text, chip.action)}
            className={cn(isPersonChip(chip, lang) && "border-primary/40 text-primary")}
          />
        ),
      )}
    </Suggestions>
  );
}
