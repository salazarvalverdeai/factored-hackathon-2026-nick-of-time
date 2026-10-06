"use client";

// Oversight in the case view (spec 18): first the deterministic auditor's facts (A1–A7 as a checklist with an icon and
// a word per check, AC-06), then the judge's second opinion, labeled advisory and shown after the auditor (AC-09).
// The judge never changes the case: asking for it only reads (AC-09); without one the panel says "No second opinion"
// (AC-11).
import { CircleCheck, CircleMinus, CircleX, Sparkles } from "lucide-react";
import { useState } from "react";
import { ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { type AuditResult, type SecondOpinion, consoleApi } from "@/lib/console-api";
import { AUDIT_STATE_LABELS, auditCheckLabel, auditState, outcomeLabel, plain, verdictLabel } from "@/lib/console-view";
import { formatDateTime } from "@/lib/handoff-labels";
import { type Query, useQuery } from "@/lib/use-query";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export const AUDITOR_TITLE = "The outcome re-derives from the rules";
export const ADVISORY_LABEL = "AI second opinion — advisory";
export const NO_OPINION = "No second opinion";

const STATE_ICON = {
  passed: { icon: CircleCheck, className: "text-brand-teal" },
  finding: { icon: CircleX, className: "text-red-600 dark:text-red-400" },
  na: { icon: CircleMinus, className: "text-muted-foreground" },
};

export function AuditChecklist({ query }: { query: Query<AuditResult> }) {
  return (
    <section aria-label={AUDITOR_TITLE} className="space-y-2 rounded-xl border bg-card p-3" data-slot="auditor">
      <h3 className="text-sm font-medium">
        {AUDITOR_TITLE}
      </h3>
      <p className="text-xs text-muted-foreground">A deterministic check, no model: it re-runs the rules on what the case recorded.</p>
      {query.status === "loading" ? (
        <LoadingState label="Re-deriving the outcome…" className="p-3" />
      ) : query.status === "error" ? (
        <ErrorState title="Auditor not available" message={query.error.message} className="p-3" />
      ) : (
        <>
          <p className="text-sm">
            Re-derived outcome: <b className="font-medium">{outcomeLabel(query.data.rederived_outcome)}</b>{" "}
            <span
              data-slot="audit-match"
              data-match={query.data.matches}
              className={cn(
                "ml-1 inline-flex items-center gap-1 rounded-4xl px-2 py-0.5 text-xs font-medium",
                query.data.matches ? "bg-brand-teal/15 text-teal-700 dark:text-teal-300" : "bg-red-500/15 text-red-700 dark:text-red-400",
              )}
            >
              {query.data.matches ? <CircleCheck aria-hidden className="size-3.5" /> : <CircleX aria-hidden className="size-3.5" />}
              {query.data.matches ? "Matches the case" : "Does not match the case"}
            </span>
          </p>
          <ul className="space-y-1.5" aria-label="Auditor checks">
            {query.data.checks.map((c) => {
              const s = auditState(c);
              const I = STATE_ICON[s];
              return (
                <li key={c.id} data-check={c.id} data-state={s} className="flex gap-2 text-sm">
                  <I.icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", I.className)} />
                  <span className="min-w-0">
                    <span className="font-medium">
                      <span className="font-mono text-xs text-muted-foreground">{c.id}</span> {auditCheckLabel(c)}
                    </span>
                    <span className="sr-only"> — {AUDIT_STATE_LABELS[s]}</span>
                    {c.detail ? <span className="block text-xs text-muted-foreground">{plain(c.detail)}</span> : null}
                  </span>
                  <span className="ml-auto shrink-0 text-xs text-muted-foreground" aria-hidden>
                    {AUDIT_STATE_LABELS[s]}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

type Asked = { status: "idle" } | { status: "asking" } | { status: "done"; opinion: SecondOpinion | null } | { status: "error"; message: string };

export function SecondOpinionPanel({ caseId }: { caseId: string }) {
  // An opinion already issued for this case (the api runs the judge when a case enters review).
  const existing = useQuery(() => consoleApi.getSecondOpinion(caseId), [caseId]);
  const [asked, setAsked] = useState<{ caseId: string; state: Asked }>({ caseId, state: { status: "idle" } });
  const state = asked.caseId === caseId ? asked.state : ({ status: "idle" } as Asked);

  async function ask() {
    setAsked({ caseId, state: { status: "asking" } });
    try {
      const opinion = await consoleApi.requestSecondOpinion(caseId);
      setAsked({ caseId, state: { status: "done", opinion } });
    } catch (err) {
      setAsked({ caseId, state: { status: "error", message: err instanceof ApiError ? err.message : "Something went wrong." } });
    }
  }

  const opinion = state.status === "done" ? state.opinion : existing.status === "ok" ? existing.data : null;
  return (
    <section aria-label={ADVISORY_LABEL} className="space-y-2 rounded-xl border border-dashed p-3" data-slot="second-opinion">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-medium">
          <Sparkles aria-hidden className="size-4 text-brand-violet" />
          {ADVISORY_LABEL}
        </h3>
        <Button size="sm" variant="outline" onClick={ask} disabled={state.status === "asking"}>
          {opinion ? "Ask again" : "Ask for a second opinion"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        A model reads the handoff card and its evidence. It cannot change the case or reach the customer: you decide.
      </p>
      <div aria-live="polite">
        {state.status === "asking" ? (
          <LoadingState label="Asking the judge model…" className="p-3" />
        ) : state.status === "error" ? (
          <ErrorState title={NO_OPINION} message={state.message} className="p-3" />
        ) : opinion ? (
          <OpinionBody o={opinion} />
        ) : state.status === "done" ? (
          <p className="text-sm text-muted-foreground" data-slot="no-opinion">
            {NO_OPINION}. The judge did not answer in time or within its budget; nothing else changed.
          </p>
        ) : null}
      </div>
    </section>
  );
}

const VERDICT_STYLE: Record<string, string> = {
  agree: "bg-brand-teal/15 text-teal-700 dark:text-teal-300",
  disagree: "bg-red-500/15 text-red-700 dark:text-red-400",
  uncertain: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
};

function Evidence({ ids }: { ids: string[] }) {
  if (!ids.length) return null;
  return (
    <span className="mt-0.5 flex flex-wrap gap-1" aria-label="Evidence">
      {ids.map((id) => (
        <span key={id} className="rounded-md border px-1.5 font-mono text-[0.7rem] text-muted-foreground">
          {id}
        </span>
      ))}
    </span>
  );
}

function OpinionBody({ o }: { o: SecondOpinion }) {
  return (
    <div className="space-y-2 text-sm" data-verdict={o.verdict}>
      <p>
        <span className={cn("rounded-4xl px-2 py-0.5 text-xs font-medium", VERDICT_STYLE[o.verdict] ?? "bg-muted")}>{verdictLabel(o.verdict)}</span>
      </p>
      {o.reasons.length ? (
        <ol className="list-decimal space-y-1.5 pl-5">
          {o.reasons.map((r, i) => (
            <li key={i}>
              {plain(r.text)}
              <Evidence ids={r.evidence_ids} />
            </li>
          ))}
        </ol>
      ) : null}
      {o.questions?.length ? (
        <div>
          <p className="text-xs font-medium text-muted-foreground">Questions for you</p>
          <ul className="list-disc space-y-1 pl-5">
            {o.questions.map((q, i) => (
              <li key={i}>
                {plain(q.text)}
                <Evidence ids={q.evidence_ids} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground">
        {o.label && o.label !== ADVISORY_LABEL ? `${plain(o.label)} · ` : ""}
        {plain(o.model)} · {formatDateTime(o.created_at)}
      </p>
    </div>
  );
}
