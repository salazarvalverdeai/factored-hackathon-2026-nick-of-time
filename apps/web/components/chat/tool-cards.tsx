"use client";

// The domain cards built from tool results (spec 01 §6.4.1, spec 07 AC-11), composed from the shadcn Card: a charge the
// customer can pick, the rules' verdict in words, a deadline with its named source, the case. Customer words come from
// the event (server text from messages.yaml) or from lib/chat-stream.ts; a tool name is never shown. Requested and
// verified look different (constitution #4); color is never the only signal.
import { CheckIcon, CreditCardIcon, ExternalLinkIcon, ScaleIcon } from "lucide-react";
import Link from "next/link";
import { Pulse } from "@/components/chat/motion";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  type ActionCard,
  type ActionState,
  type CaseCard,
  type ChargeCard,
  type DeadlineCard,
  STATE_WORDS,
  type VerdictCard,
  customerText,
  deadlineWords,
  formatAmount,
  formatDate,
} from "@/lib/chat-stream";
import { CHAT_STRINGS } from "@/lib/chat-strings";
import type { Language } from "@/lib/types";
import { cn } from "@/lib/utils";

const COPY = {
  cardEnding: { es: "Tarjeta terminada en", pt: "Cartão com final" },
  test: { es: "Cargo de prueba", pt: "Cobrança de teste" },
  noMerchant: { es: "Comercio no informado", pt: "Estabelecimento não informado" },
  caseLabel: { es: "Caso", pt: "Caso" },
  follow: { es: "Seguir mi caso", pt: "Acompanhar meu caso" },
  pending: { es: "Fecha pendiente: una persona la confirma", pt: "Data pendente: uma pessoa confirma" },
} as const;

const STATE_CLASS: Record<ActionState, string> = {
  in_progress: "border-border text-muted-foreground",
  requested: "border-brand-amber/50 text-amber-700 dark:text-amber-400",
  verified: "border-brand-teal/50 bg-brand-teal/10 text-teal-700 dark:text-teal-300",
  not_confirmed: "border-destructive/50 text-destructive",
};

/** An action's state as a pill with its words; verified carries its V- id. */
export function StateBadge({ card, lang }: { card: Pick<ActionCard, "state" | "verification_id">; lang: Language }) {
  // "Verified" gets one brief pulse when it appears (spec 07 AC-26); nothing moves under reduced motion.
  return (
    <Pulse on={card.state === "verified"} className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", STATE_CLASS[card.state])}>
      {card.state === "verified" ? <CheckIcon aria-hidden className="size-3" /> : null}
      {STATE_WORDS[card.state][lang]}
      {card.state === "verified" && card.verification_id ? <span className="font-mono text-[0.7rem] font-normal">· {card.verification_id}</span> : null}
    </Pulse>
  );
}

/** A charge the search returned, as an option card: the customer can pick it (spec 04 clarify) or open its detail. */
export function ChargeCardView({
  card,
  lang,
  onPick,
  onOpen,
  selected = null,
}: {
  card: ChargeCard;
  lang: Language;
  onPick?: (card: ChargeCard) => void;
  onOpen?: (card: ChargeCard) => void;
  /** After a pick: true for the chosen card (it lifts), false for the others (they fade); null before any pick. */
  selected?: boolean | null;
}) {
  const merchant = card.merchant ? customerText(card.merchant) : COPY.noMerchant[lang];
  return (
    <Card
      className={cn(
        "flex items-center gap-3 p-3 text-sm motion-safe:transition-[border-color,opacity,transform] motion-safe:duration-200 motion-safe:ease-out hover:border-primary/50",
        selected === true && "border-primary/60 motion-safe:scale-[1.02]",
        selected === false && "opacity-50",
      )}
      data-slot="charge-card"
    >
      <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
        <CreditCardIcon className="size-4" />
      </span>
      <button
        type="button"
        onClick={() => onOpen?.(card)}
        disabled={!onOpen}
        className="min-w-0 flex-1 rounded-md text-left focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-default"
      >
        <span className="block truncate font-medium">{merchant}</span>
        <span className="block text-xs text-muted-foreground">
          {formatDate(card.date, lang)} · {COPY.cardEnding[lang]} {card.last4}
          {card.synthetic ? ` · ${COPY.test[lang]}` : ""}
        </span>
      </button>
      <span className="shrink-0 text-right font-semibold tabular-nums">{formatAmount(card.amount, card.currency, lang)}</span>
      {onPick ? (
        <Button size="sm" variant="ghost" className="shrink-0 text-primary" onClick={() => onPick(card)} aria-label={`${CHAT_STRINGS.pick[lang]}: ${merchant}`}>
          {CHAT_STRINGS.pick[lang]}
        </Button>
      ) : null}
    </Card>
  );
}

/** The rules' outcome in the customer's words (no score, zone or policy id). */
export function VerdictCardView({ card, onOpen, lang }: { card: VerdictCard; lang: Language; onOpen?: () => void }) {
  return (
    <Card className="border-primary/30 p-3 text-sm" data-slot="verdict-card">
      <p className="flex items-start gap-2 font-medium">
        <ScaleIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-primary" />
        <span className="min-w-0 flex-1">{customerText(card.headline)}</span>
      </p>
      {card.actions.length ? (
        <ul className="mt-2 list-disc space-y-1 pl-6 text-xs text-muted-foreground">
          {card.actions.map((a) => (
            <li key={a}>{customerText(a)}</li>
          ))}
        </ul>
      ) : null}
      {onOpen ? (
        <Button size="xs" variant="ghost" className="mt-1 -ml-2 text-primary" onClick={onOpen}>
          {CHAT_STRINGS.rule[lang]} →
        </Button>
      ) : null}
    </Card>
  );
}

/** A legal deadline with its source as a named link (design pass 1: never a raw URL). */
export function DeadlineCardView({ card, lang }: { card: DeadlineCard; lang: Language }) {
  return (
    <Card className="border-l-2 border-l-brand-amber p-3 text-sm" data-slot="deadline-card">
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
    </Card>
  );
}

/** The case the tools opened, with the way to follow it. */
export function CaseCardView({ card, lang }: { card: CaseCard; lang: Language }) {
  return (
    <Card className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm" data-slot="case-card">
      <p>
        <span className="text-xs text-muted-foreground">{COPY.caseLabel[lang]} </span>
        <span className="font-mono text-xs">{card.case_id}</span>
      </p>
      <Link href={`/case/${encodeURIComponent(card.case_id)}`} className="text-xs text-primary underline-offset-2 hover:underline">
        {COPY.follow[lang]} →
      </Link>
    </Card>
  );
}
