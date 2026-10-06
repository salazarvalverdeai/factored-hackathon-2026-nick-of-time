"use client";

// Oversight in the case view (spec 18): first the deterministic auditor's facts (A1–A7 as a checklist with an icon and
// a word per check, AC-06), then the judge's second opinion, labeled advisory and shown after the auditor (AC-09).
// The judge never changes the case: asking for it only reads (AC-09); without one the panel says "No second opinion"
// (AC-11).
import { CircleCheck, CircleMinus, CircleX, Sparkles } from "lucide-react";
import { useState } from "react";
import { Task, TaskContent, TaskTrigger } from "@/components/ai-elements/task";
import { useLocale, useT } from "@/components/i18n-provider";
import { ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { type AuditResult, type SecondOpinion, consoleApi } from "@/lib/console-api";
import { auditCheckLabel, auditState, auditStateLabel, outcomeLabel, plain, verdictLabel } from "@/lib/console-view";
import { formatDateTime } from "@/lib/handoff-labels";
import type { Translate } from "@/lib/i18n";
import { type Query, useQuery } from "@/lib/use-query";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

// The panel titles are UI words (messages/console.ts `oversight`, spec 16 AC-06): `console.oversight.auditorTitle`,
// `console.oversight.advisory` and `console.oversight.noOpinion`. ADVISORY_LABEL is the label the api and the mock
// attach to an opinion; it is compared, never shown twice.
export const ADVISORY_LABEL = "AI second opinion — advisory";

const STATE_ICON = {
  passed: { icon: CircleCheck, className: "text-brand-teal" },
  finding: { icon: CircleX, className: "text-red-600 dark:text-red-400" },
  na: { icon: CircleMinus, className: "text-muted-foreground" },
};

/** "7 checks · 6 passed · 1 not applicable" */
function checksTitle(a: AuditResult, t: Translate): string {
  const n = { passed: 0, finding: 0, na: 0 };
  for (const c of a.checks) n[auditState(c)] += 1;
  const total = a.checks.length;
  const parts = [
    t(total === 1 ? "console.oversight.checks.one" : "console.oversight.checks.other", { n: total }),
    t("console.oversight.passed", { n: n.passed }),
  ];
  if (n.finding) parts.push(t("console.oversight.finding", { n: n.finding }));
  if (n.na) parts.push(t("console.oversight.na", { n: n.na }));
  return parts.join(" · ");
}

export function AuditChecklist({ query }: { query: Query<AuditResult> }) {
  const t = useT();
  const { locale } = useLocale();
  return (
    <section aria-label={t("console.oversight.auditorTitle")} className="space-y-2 rounded-xl border bg-card p-3" data-slot="auditor">
      <h3 className="text-sm font-medium">
        {t("console.oversight.auditorTitle")}
      </h3>
      <p className="text-xs text-muted-foreground">{t("console.oversight.auditorNote")}</p>
      {query.status === "loading" ? (
        <LoadingState label={t("console.oversight.rederiving")} className="p-3" />
      ) : query.status === "error" ? (
        <ErrorState title={t("console.oversight.auditorUnavailable")} message={query.error.message} className="p-3" />
      ) : (
        <>
          <p className="text-sm">
            {t("console.oversight.rederived")} <b className="font-medium">{outcomeLabel(query.data.rederived_outcome, locale)}</b>{" "}
            <span
              data-slot="audit-match"
              data-match={query.data.matches}
              className={cn(
                "ml-1 inline-flex items-center gap-1 rounded-4xl px-2 py-0.5 text-xs font-medium",
                query.data.matches ? "bg-brand-teal/15 text-teal-700 dark:text-teal-300" : "bg-red-500/15 text-red-700 dark:text-red-400",
              )}
            >
              {query.data.matches ? <CircleCheck aria-hidden className="size-3.5" /> : <CircleX aria-hidden className="size-3.5" />}
              {query.data.matches ? t("console.oversight.matches") : t("console.oversight.notMatches")}
            </span>
          </p>
          {/* AI Elements `task`: the checks fold, open by default, like the chat's tool steps. */}
          <Task>
            <TaskTrigger title={checksTitle(query.data, t)} />
            <TaskContent>
              <ul className="space-y-1.5" aria-label={t("console.oversight.checksAria")}>
                {query.data.checks.map((c) => {
                  const s = auditState(c);
                  const I = STATE_ICON[s];
                  return (
                    <li key={c.id} data-check={c.id} data-state={s} className="flex gap-2 text-sm text-foreground">
                      <I.icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", I.className)} />
                      <span className="min-w-0">
                        <span className="font-medium">
                          <span className="font-mono text-xs text-muted-foreground">{c.id}</span> {auditCheckLabel(c, locale)}
                        </span>
                        <span className="sr-only"> — {auditStateLabel(s, locale)}</span>
                        {c.detail ? <span className="block text-xs text-muted-foreground">{plain(c.detail)}</span> : null}
                      </span>
                      <span className="ml-auto shrink-0 text-xs text-muted-foreground" aria-hidden>
                        {auditStateLabel(s, locale)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </TaskContent>
          </Task>
        </>
      )}
    </section>
  );
}

type Asked = { status: "idle" } | { status: "asking" } | { status: "done"; opinion: SecondOpinion | null } | { status: "error"; message: string };

export function SecondOpinionPanel({ caseId }: { caseId: string }) {
  const t = useT();
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
      setAsked({ caseId, state: { status: "error", message: err instanceof ApiError ? err.message : t("console.oversight.somethingWrong") } });
    }
  }

  const opinion = state.status === "done" ? state.opinion : existing.status === "ok" ? existing.data : null;
  return (
    <section aria-label={t("console.oversight.advisory")} className="space-y-2 rounded-xl border border-dashed p-3" data-slot="second-opinion">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-medium">
          <Sparkles aria-hidden className="size-4 text-brand-violet" />
          {t("console.oversight.advisory")}
        </h3>
        <Button size="sm" variant="outline" onClick={ask} disabled={state.status === "asking"}>
          {opinion ? t("console.oversight.askAgain") : t("console.oversight.ask")}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t("console.oversight.modelNote")}</p>
      <div aria-live="polite">
        {state.status === "asking" ? (
          <LoadingState label={t("console.oversight.asking")} className="p-3" />
        ) : state.status === "error" ? (
          <ErrorState title={t("console.oversight.noOpinion")} message={state.message} className="p-3" />
        ) : opinion ? (
          <OpinionBody o={opinion} />
        ) : state.status === "done" ? (
          <p className="text-sm text-muted-foreground" data-slot="no-opinion">
            {t("console.oversight.noOpinion")}. {t("console.oversight.noOpinionDetail")}
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
  const t = useT();
  if (!ids.length) return null;
  return (
    <span className="mt-0.5 flex flex-wrap gap-1" aria-label={t("console.oversight.evidence")}>
      {ids.map((id) => (
        <Badge key={id} variant="outline" className="rounded-md font-mono text-[0.7rem] font-normal text-muted-foreground">
          {id}
        </Badge>
      ))}
    </span>
  );
}

function OpinionBody({ o }: { o: SecondOpinion }) {
  const t = useT();
  const { locale } = useLocale();
  return (
    <div className="space-y-2 text-sm" data-verdict={o.verdict}>
      <p>
        <Badge className={cn(VERDICT_STYLE[o.verdict] ?? "bg-muted text-muted-foreground")}>{verdictLabel(o.verdict, locale)}</Badge>
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
          <p className="text-xs font-medium text-muted-foreground">{t("console.oversight.questions")}</p>
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
        {plain(o.model)} · {formatDateTime(locale, o.created_at)}
      </p>
    </div>
  );
}
