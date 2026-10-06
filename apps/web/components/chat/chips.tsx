"use client";

// The chips under the last reply, inside the conversation (AI Elements `suggestion`): at most three from the turn, the
// main next step filled, and "talk to a person" always among them (spec 04 AC-20, AC-39; spec 07 AC-13, AC-23). The row
// wraps, never scrolls sideways, so nothing is clipped at 390 px or when zoomed (AC-05). An action chip sends its
// action, never its text; a link chip opens a path on our own host.
import { PhoneIcon } from "lucide-react";
import Link from "next/link";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { buttonVariants } from "@/components/ui/button";
import { chipsFor, isPersonChip, primaryChipIndex } from "@/lib/chat-stream";
import type { Language, Suggestion as Chip, TurnAction } from "@/lib/types";
import { cn } from "@/lib/utils";

/** The row's wrapping layout; lib/chat-view.test.ts checks it never becomes a horizontal scroller. */
export const CHIP_ROW_CLASS = "flex flex-wrap gap-2";

export function ChatChips({
  suggestions,
  lang,
  disabled,
  onSend,
  label = "Suggested replies",
}: {
  suggestions: readonly Chip[] | undefined;
  lang: Language;
  disabled?: boolean;
  onSend: (text: string, action?: TurnAction) => void;
  label?: string;
}) {
  const chips = chipsFor(suggestions, lang);
  const primary = primaryChipIndex(chips, lang);
  return (
    <Suggestions role="group" aria-label={label} data-slot="chat-chips" className={CHIP_ROW_CLASS}>
      {chips.map((chip, i) => {
        const person = isPersonChip(chip, lang);
        const variant = i === primary ? "default" : "outline";
        const pill = cn("h-auto min-h-8 whitespace-normal rounded-full px-3.5 py-1.5 text-left", person && "border-primary/40 text-primary");
        const body = (
          <>
            {person ? <PhoneIcon aria-hidden className="size-3.5" /> : null}
            {chip.label}
          </>
        );
        return chip.href ? (
          <Link key={chip.label} href={chip.href} className={cn(buttonVariants({ variant, size: "sm" }), pill)}>
            {body}
          </Link>
        ) : (
          <Suggestion key={chip.label} suggestion={chip.label} variant={variant} disabled={disabled} onClick={() => onSend(chip.text, chip.action)} className={pill}>
            {body}
          </Suggestion>
        );
      })}
    </Suggestions>
  );
}
