"use client";

// The verified receipt (spec 07 AC-02, AC-19 to AC-21, ADR 0013), composed from the shadcn Card: proof of what the AI did
// and what a person does next, from verified facts only. The deadline is the hero, with a business-day countdown from
// the demo date (replay) or the receipt's issue date (live), never the system clock. Short rows, the source as a named
// link (AI Elements `sources`), and Copy / View my case (AI Elements message actions). The seal is the brand's
// verified-state avatar (docs/brand/BRAND.md §9), never a redrawn mark.
import { CheckIcon, CopyIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { MessageAction, MessageActions } from "@/components/ai-elements/message";
import { Source, Sources, SourcesContent, SourcesTrigger } from "@/components/ai-elements/sources";
import { Reveal, TickIn, useReducedMotionGuard } from "@/components/chat/motion";
import { Card } from "@/components/ui/card";
import { type ChargeCard, customerText, formatAmount, formatDate, formatTimestamp, localizeTimes } from "@/lib/chat-stream";
import { CHAT_STRINGS as S } from "@/lib/chat-strings";
import { demoDateLabel } from "@/lib/demo-date";
import { countdownWords, deadlineHero, receiptFacts, receiptPlainText, receiptToday, replayText, stateWord } from "@/lib/receipt-view";
import type { Language, Receipt } from "@/lib/types";

/** The countdown with its number ticking in once (spec 07 AC-26): the value is final from the first render. */
function Countdown({ left, lang }: { left: number; lang: Language }) {
  const reduce = useReducedMotionGuard();
  const words = countdownWords(left, lang);
  const m = /^(\D*)(\d+)(.*)$/.exec(words);
  if (!m || reduce) return <span className="font-medium text-foreground">{words}</span>;
  return (
    <span className="font-medium text-foreground">
      {m[1]}
      <TickIn>{m[2]}</TickIn>
      {m[3]}
    </span>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[4.5rem_1fr] gap-x-3 gap-y-0.5 sm:grid-cols-[6rem_1fr]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

/** `demoDate` is the replay "today" (YYYY-MM-DD) for replay sessions, null for live ones; `charge` is the turn's charge. */
export function ReceiptCard({ receipt, country, demoDate = null, charge }: { receipt: Receipt; country?: string; demoDate?: string | null; charge?: ChargeCard }) {
  const replay = Boolean(demoDate);
  const lang = receipt.language;
  const zoneCountry = receipt.deadline.country || country;
  const today = receiptToday(receipt, demoDate, country);
  const hero = deadlineHero(receipt, today);
  const facts = receiptFacts(receipt).map((f) => customerText(localizeTimes(replayText(f, replay), lang, zoneCountry)));
  const source = receipt.source ?? (receipt.deadline.deadlineSource ? { label: receipt.deadline.deadlineSource, url: null, verified_on: null } : null);
  const [copied, setCopied] = useState(false);

  async function copy() {
    const text = receiptPlainText(receipt, { today, demoDate, origin: typeof window === "undefined" ? "" : window.location.origin });
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false); // a blocked clipboard: the receipt stays on screen and on the case page
    }
  }

  return (
    <Reveal kind="receipt">
    <Card data-slot="receipt" aria-label={customerText(receipt.title)} className="overflow-hidden border-brand-teal/40 text-sm">
      <header className="flex items-center gap-3 px-4 pt-4">
        {/* Verified-state avatar: the symbol with its verification cue (docs/brand/BRAND.md §9). */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/verified-state-avatar.png" alt="" aria-hidden="true" className="size-8 shrink-0 rounded-full" />
        <p className="min-w-0 flex-1 font-semibold leading-snug">
          {S.receipt[lang]} · {S.caseWord[lang]} <span className="font-mono text-[0.8rem] font-medium">{receipt.case_id}</span>
        </p>
        <Reveal kind="seal" delay={0.25} className="inline-flex shrink-0 items-center gap-1 rounded-full border border-brand-teal/50 bg-brand-teal/10 px-2 py-0.5 text-xs font-medium text-teal-700 dark:text-teal-300">
          <CheckIcon aria-hidden className="size-3" />
          {S.verified[lang]}
        </Reveal>
      </header>

      <div className="space-y-3 p-4">
        {hero ? (
          <div data-slot="deadline-hero" className="rounded-lg border border-brand-amber/50 bg-brand-amber/10 px-3.5 py-3">
            <p className="text-xs font-medium text-amber-700 dark:text-amber-300">{hero.label}</p>
            <p className="mt-0.5 text-xl font-semibold leading-tight sm:text-2xl">{formatDate(hero.date, lang)}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {hero.left !== null ? <Countdown left={hero.left} lang={lang} /> : null}
              {hero.left !== null && hero.then ? " · " : null}
              {hero.then ? `${S.then[lang]} ${formatDate(hero.then, lang)}` : null}
            </p>
          </div>
        ) : (
          <p className="rounded-lg border border-brand-amber/50 px-3.5 py-3">{customerText(receipt.deadline_text)}</p>
        )}

        <dl className="space-y-2">
          {charge ? (
            <Row label={S.rowCharge[lang]}>
              {formatAmount(charge.amount, charge.currency, lang)} · {formatDate(charge.date, lang)}
              {charge.last4 ? ` · ··${charge.last4}` : ""}
            </Row>
          ) : null}
          {receipt.card_blocked ? <Row label={S.rowDone[lang]}>{customerText(localizeTimes(replayText(receipt.card_blocked, replay), lang, zoneCountry))}</Row> : null}
          {receipt.actions?.length ? (
            <Row label={S.rowDone[lang]}>
              <ul className="space-y-0.5">
                {receipt.actions.map((a) => (
                  <li key={`${a.label}-${a.verification_id ?? a.state}`}>
                    {customerText(replayText(a.label, replay))}: {stateWord(a.state, lang)}
                    {a.verification_id ? <span className="ml-1 font-mono text-[0.7rem] text-muted-foreground">{a.verification_id}</span> : null}
                  </li>
                ))}
              </ul>
            </Row>
          ) : !receipt.card_blocked ? (
            // The reply above usually says what the AI did; the row shows it only when nothing else says what was done.
            <Row label={S.rowDone[lang]}>{customerText(receipt.what_ai_did)}</Row>
          ) : null}
          {facts.length ? (
            <Row label="">
              <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
                {facts.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </Row>
          ) : null}
          <Row label={S.rowNext[lang]}>{customerText(receipt.what_a_person_does)}</Row>
        </dl>

        <p className="text-xs text-muted-foreground" data-slot="demo-date">
          {demoDate ? demoDateLabel(demoDate, lang) : `${lang === "pt" ? "Emitido em" : "Emitido el"} ${formatTimestamp(receipt.issued_at, lang, zoneCountry)}`}
        </p>
      </div>

      <footer className="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-2.5">
        {source ? (
          <Sources>
            <SourcesTrigger count={1} label={`${S.source[lang]}: ${customerText(source.label)}`} className="max-w-full text-left" />
            <SourcesContent>
              {source.url ? <Source href={source.url} title={customerText(source.label)} /> : <span className="text-muted-foreground">{customerText(source.label)}</span>}
              {source.verified_on ? (
                <span className="text-muted-foreground">
                  {S.checkedOn[lang]} {formatDate(source.verified_on, lang)}
                </span>
              ) : null}
            </SourcesContent>
          </Sources>
        ) : (
          <span />
        )}
        <MessageActions>
          <MessageAction size="sm" className="h-7 px-2 text-xs" label={S.copyReceipt[lang]} onClick={copy}>
            {copied ? <CheckIcon aria-hidden className="size-3.5" /> : <CopyIcon aria-hidden className="size-3.5" />}
            <span aria-hidden>{copied ? S.copied[lang] : S.copy[lang]}</span>
          </MessageAction>
          <Link href={receipt.case_url} className="rounded-md px-2 py-1 text-xs font-medium text-primary underline-offset-2 hover:underline">
            {S.viewCase[lang]} →
          </Link>
        </MessageActions>
        <span className="sr-only" role="status" aria-live="polite">
          {copied ? S.copied[lang] : ""}
        </span>
      </footer>
    </Card>
    </Reveal>
  );
}
