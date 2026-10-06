// The agent's summary at the top of the case: a few lines and the nearest legal deadline with its countdown and its
// source as a named link (spec 08 assisted console). With no verified clock entry it says a person decides, no date.
import { CalendarClock, ExternalLink } from "lucide-react";
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
  return (
    <section aria-label="Agent summary" className="space-y-2 rounded-xl border bg-card p-3" data-slot="agent-summary">
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Agent summary
      </h3>
      {query.status === "loading" ? (
        <LoadingState label="Reading the summary…" className="p-3" />
      ) : query.status === "error" ? (
        <ErrorState title="No summary" message={query.error.message} className="p-3" />
      ) : (
        <SummaryBody s={query.data} />
      )}
    </section>
  );
}

function SummaryBody({ s }: { s: CaseSummary }) {
  const d = s.deadline;
  const c = d ? countdown(d) : null;
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
        <p className="text-sm text-muted-foreground">The agent left no summary for this case.</p>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-2 text-sm">
        <CalendarClock aria-hidden className="size-4 text-brand-amber" />
        {d && c ? (
          <>
            <span>
              {deadlineKindLabel(d.kind)}: <b className="font-medium">{formatDay(d.date)}</b>
            </span>
            <span data-slot="deadline-countdown" data-level={c.level} className={cn("rounded-4xl px-2 py-0.5 text-xs font-medium", LEVEL[c.level])}>
              {c.text}
            </span>
            <span className="text-xs text-muted-foreground">
              Source:{" "}
              {d.source_url ? (
                <a href={d.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 underline underline-offset-2 hover:text-foreground">
                  {plain(d.source_label)}
                  <ExternalLink aria-hidden className="size-3" />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              ) : (
                plain(d.source_label)
              )}
            </span>
          </>
        ) : (
          <span className="text-muted-foreground">No legal deadline for this country · a person decides</span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{writerLabel(s.writer)}</p>
    </>
  );
}
