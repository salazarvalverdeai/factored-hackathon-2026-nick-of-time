"use client";

// The verified receipt (spec 07 AC-02, ADR 0013): proof of what the AI did and what a person does next, from verified
// facts only, with the texts of contracts/messages.yaml. It carries the deadlines and their sources, so the reply
// above it does not repeat them (design pass 1). Sources are named links; times are in the session language and the
// case's zone; the seal is the brand's verified-state avatar (docs/brand/BRAND.md §9), never a redrawn mark.
import Link from "next/link";
import { Source, Sources, SourcesContent, SourcesTrigger } from "@/components/ai-elements/sources";
import { DEMO_TODAY, daysBetween } from "@/lib/mock/store";
import { MESSAGES } from "@/lib/mock/messages";
import { customerText, formatDate, formatTimestamp, localizeTimes } from "@/lib/chat-stream";
import type { Language, Receipt } from "@/lib/types";

const COPY = {
  verified: { es: "Verificado", pt: "Verificado" },
  issued: { es: "Emitido el", pt: "Emitido em" },
  left: { es: (n: number) => (n === 1 ? "falta 1 día" : `faltan ${n} días`), pt: (n: number) => (n === 1 ? "falta 1 dia" : `faltam ${n} dias`) },
  sources: { es: "Fuentes", pt: "Fontes" },
  checked: { es: "verificada el", pt: "verificada em" },
  actions: { es: "Acciones", pt: "Ações" },
} as const;

const STATE: Record<string, Record<Language, string>> = {
  verified: { es: "verificado", pt: "verificado" },
  requested: { es: "solicitado", pt: "solicitado" },
  in_progress: { es: "en curso", pt: "em andamento" },
  not_confirmed: { es: "no confirmado", pt: "não confirmado" },
};

/** The words before the colon of a deadline template: "Plazo legal del banco para resolver tu caso". */
const head = (m: { es: string; pt: string }, lang: Language) => m[lang].split(":")[0];

/** Days left to a date: the api's count when it sent one; the mock counts from its frozen demo date (ADR 0012). */
function daysLeft(date: string, sent: number | null | undefined): number | null {
  if (sent !== undefined) return sent;
  return daysBetween(DEMO_TODAY, date);
}

/** A receipt fact the card does not already show: deadline lines (with their raw URL) are shown as structured rows. */
function extraFacts(receipt: Receipt): string[] {
  const lang = receipt.language;
  const heads = [MESSAGES.receipt.credit_deadline, MESSAGES.receipt.ruling_deadline].map((m) => head(m, lang));
  return (receipt.facts ?? []).filter((f) => !/https?:\/\//.test(f) && !heads.some((h) => f.startsWith(h)) && f !== receipt.card_blocked);
}

export function ReceiptCard({ receipt, country }: { receipt: Receipt; country?: string }) {
  const lang = receipt.language;
  const zoneCountry = receipt.deadline.country || country;
  const rows = [
    { key: "credit", label: head(MESSAGES.receipt.credit_deadline, lang), date: receipt.deadline.creditDeadline },
    { key: "ruling", label: head(MESSAGES.receipt.ruling_deadline, lang), date: receipt.ruling_deadline ?? receipt.deadline.rulingDeadline ?? null },
  ].filter((r): r is { key: string; label: string; date: string } => Boolean(r.date));
  const source = receipt.source ?? (receipt.deadline.deadlineSource ? { label: receipt.deadline.deadlineSource, url: null, verified_on: null } : null);

  return (
    <section data-slot="receipt" aria-label={customerText(receipt.title)} className="rounded-xl border border-brand-teal/40 bg-card p-4 text-left text-sm">
      <header className="flex items-start gap-3">
        {/* Verified-state avatar: the symbol with its verification cue (docs/brand/BRAND.md §9). */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/verified-state-avatar.png" alt="" aria-hidden="true" className="size-9 shrink-0 rounded-full" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold leading-snug">{customerText(receipt.title)}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <span className="inline-flex items-center rounded-full border border-brand-teal/50 bg-brand-teal/10 px-2 py-0.5 font-medium text-teal-700 dark:text-teal-300">
              ✓ {COPY.verified[lang]}
            </span>
            <span>
              {COPY.issued[lang]} {formatTimestamp(receipt.issued_at, lang, zoneCountry)}
            </span>
          </p>
        </div>
      </header>

      <div className="mt-3 space-y-3">
        {receipt.card_blocked ? <p>{customerText(localizeTimes(receipt.card_blocked, lang, zoneCountry))}</p> : null}
        {extraFacts(receipt).length ? (
          <ul className="list-disc space-y-1 pl-5">
            {extraFacts(receipt).map((f) => (
              <li key={f}>{customerText(localizeTimes(f, lang, zoneCountry))}</li>
            ))}
          </ul>
        ) : null}

        {rows.length ? (
          <ul className="space-y-2">
            {rows.map((r) => {
              const left = daysLeft(r.date, receipt.deadline.daysLeft);
              return (
                <li key={r.key} className="border-l-2 border-brand-amber pl-3">
                  <span className="block text-xs text-muted-foreground">{r.label}</span>
                  <span className="font-medium">{formatDate(r.date, lang)}</span>
                  {left !== null && left >= 0 ? <span className="ml-2 text-xs text-muted-foreground">{COPY.left[lang](left)}</span> : null}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="border-l-2 border-brand-amber pl-3">{customerText(receipt.deadline_text)}</p>
        )}

        {receipt.actions?.length ? (
          <div>
            <p className="text-xs text-muted-foreground">{COPY.actions[lang]}</p>
            <ul className="mt-1 space-y-1 text-xs">
              {receipt.actions.map((a) => (
                <li key={`${a.label}-${a.verification_id ?? a.state}`}>
                  {customerText(a.label)}: {STATE[a.state]?.[lang] ?? a.state.replaceAll("_", " ")}
                  {a.verification_id ? <span className="font-mono text-muted-foreground"> · {a.verification_id}</span> : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <p>{customerText(receipt.what_ai_did)}</p>
        <p>{customerText(receipt.what_a_person_does)}</p>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
          {source ? (
            <Sources>
              <SourcesTrigger count={1} label={COPY.sources[lang]} />
              <SourcesContent>
                {source.url ? (
                  <Source href={source.url} title={customerText(source.label)} />
                ) : (
                  <span className="text-muted-foreground">{customerText(source.label)}</span>
                )}
                {source.verified_on ? (
                  <span className="text-muted-foreground">
                    {COPY.checked[lang]} {formatDate(source.verified_on, lang)}
                  </span>
                ) : null}
              </SourcesContent>
            </Sources>
          ) : (
            <span />
          )}
          <Link href={receipt.case_url} className="text-xs font-medium text-primary underline-offset-2 hover:underline">
            {MESSAGES.suggest.view_case[lang]} →
          </Link>
        </div>
      </div>
    </section>
  );
}
