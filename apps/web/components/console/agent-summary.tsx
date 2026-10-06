"use client";

// The agent's summary at the top of the case: a few lines and the nearest legal deadline with its countdown and its
// source as a named link (spec 08 assisted console). With no verified clock entry it says a person decides, no date.
// Labels follow the UI language (spec 16 AC-06); the summary lines and the source name are shown as the api sent them.
import { CalendarClock, ExternalLink } from "lucide-react";
import { Source } from "@/components/ai-elements/sources";
import { useLocale, useT } from "@/components/i18n-provider";
import { ErrorState, LoadingState } from "@/components/states";
import type { CaseSummary } from "@/lib/console-api";
import { countdown, deadlineKindLabel, formatDay, plain, writerLabel } from "@/lib/console-view";
import type { Query } from "@/lib/use-query";
import { cn } from "@/lib/utils";

const LEVEL: Record<string, string> = {
  green: "bg-brand-teal/15 text-teal-700 dark:text-teal-300",
  amber: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  red: "bg-red-500/15 text-red-700 dark:text-red-400",
  unknown: "bg-muted text-muted-foreground",
};

export function AgentSummary({ query }: { query: Query<CaseSummary> }) {
  const t = useT();
  return (
    <section aria-label={t("console.summary.title")} className="space-y-2 rounded-xl border bg-card p-3" data-slot="agent-summary">
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("console.summary.title")}
      </h3>
      {query.status === "loading" ? (
        <LoadingState label={t("console.summary.reading")} className="p-3" />
      ) : query.status === "error" ? (
        <ErrorState title={t("console.summary.none")} message={query.error.message} className="p-3" />
      ) : (
        <SummaryBody s={query.data} />
      )}
    </section>
  );
}

function SummaryBody({ s }: { s: CaseSummary }) {
  const t = useT();
  const { locale } = useLocale();
  const d = s.deadline;
  const c = d ? countdown(d, locale) : null;
  return (
    <>
      {s.lines.length ? (
        <ul className="space-y-1 text-sm leading-relaxed">
          {s.lines.map((l, i) => (
            <li key={i} className="flex gap-2">
              <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-brand-violet" />
              <span>{plain(l)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{t("console.summary.noLines")}</p>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-2 text-sm">
        <CalendarClock aria-hidden className="size-4 text-brand-amber" />
        {d && c ? (
          <>
            <span>
              {deadlineKindLabel(d.kind, locale)}: <b className="font-medium">{formatDay(locale, d.date)}</b>
            </span>
            <span data-slot="deadline-countdown" data-level={c.level} className={cn("rounded-4xl px-2 py-0.5 text-xs font-medium", LEVEL[c.level])}>
              {c.text}
            </span>
            <span className="text-xs text-muted-foreground">
              {t("console.summary.source")}{" "}
              {d.source_url ? (
                // AI Elements `source`: always a named link, the URL is its target, never its text.
                <Source href={d.source_url} className="items-center gap-0.5 underline">
                  {plain(d.source_label)}
                  <ExternalLink aria-hidden className="size-3" />
                  <span className="sr-only">{t("console.summary.newTab")}</span>
                </Source>
              ) : (
                plain(d.source_label)
              )}
            </span>
          </>
        ) : (
          <span className="text-muted-foreground">{t("console.summary.noDeadline")}</span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{writerLabel(s.writer, locale)}</p>
    </>
  );
}
