import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { translator } from "@/lib/i18n";
import { GUARDRAIL_IDS, guardrailLabel, kindLabel, traceRow } from "@/lib/trace";
import type { Language, TraceStep } from "@/lib/types";

// The panel speaks the session's conversation language, never the UI locale: it is customer-visible and its streamed
// step labels arrive in that language (spec 07 AC-03, spec 16 AC-06). Its words live in messages/trace.ts.

const KIND_CLASS: Record<TraceStep["kind"], string> = {
  ok: "bg-muted text-muted-foreground",
  in_progress: "bg-muted text-muted-foreground",
  accepted: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  verified: "bg-brand-teal/15 text-teal-700 dark:text-teal-300",
  not_confirmed: "bg-red-500/15 text-red-700 dark:text-red-400",
  guardrail: "bg-red-500/15 text-red-700 dark:text-red-400",
  deny: "bg-red-500/15 text-red-700 dark:text-red-400",
};

/** The steps as a list: each row leads with its plain name (design pass 1, finding 4), then its result. */
export function TraceSteps({ trace, guardrails, lang }: { trace: TraceStep[]; guardrails: string[]; lang: Language }) {
  const t = translator(lang);
  return (
    <>
      {trace.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("trace.panel.empty")}</p>
      ) : (
        <ol className="space-y-2 text-sm">
          {trace.map((step, i) => {
            const row = traceRow(step, lang);
            return (
              <li key={`${step.step}-${i}`} className="rounded-lg border p-2">
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0 font-medium">{row.title}</span>
                  <span className={`inline-flex h-5 shrink-0 items-center rounded-4xl px-2 text-xs font-medium ${KIND_CLASS[step.kind]}`}>
                    {kindLabel(step.kind, lang)}
                  </span>
                </span>
                {row.detail ? <span className="mt-1 block whitespace-pre-line break-words text-xs text-muted-foreground">{row.detail}</span> : null}
              </li>
            );
          })}
        </ol>
      )}
      <div className="mt-3 text-xs">
        <b>{t("trace.panel.guardrailsFired")}</b>{" "}
        {guardrails.length ? (
          <ul className="mt-1 space-y-1">
            {guardrails.map((g) => (
              <li key={g}>
                {guardrailLabel(g, lang)}
                {GUARDRAIL_IDS.includes(g) ? <span className="font-mono text-muted-foreground"> ({g})</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          t("trace.panel.none")
        )}
      </div>
    </>
  );
}

/**
 * Each step of the last turn with its result, and the guardrails that fired by name (spec 07 AC-03, AC-08).
 * "requested" is not "verified" (constitution #4). It shows no score, zone or policy id (D-013).
 */
export function TracePanel({ trace, guardrails, lang }: { trace: TraceStep[]; guardrails: string[]; lang: Language }) {
  const t = translator(lang);
  return (
    <aside aria-label={t("trace.panel.label")} lang={lang} className="min-w-0">
      <Card>
        <CardHeader>
          <CardTitle>{t("trace.panel.title")}</CardTitle>
          <CardDescription>{t("trace.panel.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <TraceSteps trace={trace} guardrails={guardrails} lang={lang} />
        </CardContent>
      </Card>
    </aside>
  );
}
