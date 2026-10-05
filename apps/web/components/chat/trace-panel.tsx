import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { GUARDRAIL_LABELS, guardrailLabel } from "@/lib/trace";
import type { TraceStep } from "@/lib/types";

const KIND_LABEL: Record<TraceStep["kind"], string> = {
  ok: "done",
  in_progress: "in progress",
  accepted: "requested",
  verified: "verified ✓",
  not_confirmed: "not confirmed",
  guardrail: "guardrail",
  deny: "DENY",
};

const KIND_CLASS: Record<TraceStep["kind"], string> = {
  ok: "bg-muted text-muted-foreground",
  in_progress: "bg-muted text-muted-foreground",
  accepted: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  verified: "bg-brand-teal/15 text-teal-700 dark:text-teal-300",
  not_confirmed: "bg-red-500/15 text-red-700 dark:text-red-400",
  guardrail: "bg-red-500/15 text-red-700 dark:text-red-400",
  deny: "bg-red-500/15 text-red-700 dark:text-red-400",
};

/**
 * Each step of the last turn with its result, and the guardrails that fired by name (spec 07 AC-03, AC-08).
 * "requested" is not "verified" (constitution #4). It shows no score, zone or policy id (D-013).
 */
export function TracePanel({ trace, guardrails }: { trace: TraceStep[]; guardrails: string[] }) {
  return (
    <aside aria-label="Trace" className="min-w-0">
      <Card>
        <CardHeader>
          <CardTitle>Trace</CardTitle>
          <CardDescription>What the agent did on the last message</CardDescription>
        </CardHeader>
        <CardContent>
          {trace.length === 0 ? (
            <p className="text-sm text-muted-foreground">No steps yet.</p>
          ) : (
            <ol className="space-y-2 text-sm">
              {trace.map((t, i) => (
                <li key={`${t.step}-${i}`} className="rounded-lg border p-2">
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs">{t.step}</span>
                    <span className={`inline-flex h-5 shrink-0 items-center rounded-4xl px-2 text-xs font-medium ${KIND_CLASS[t.kind]}`}>
                      {KIND_LABEL[t.kind]}
                    </span>
                  </span>
                  <span className="mt-1 block whitespace-pre-line break-words text-xs text-muted-foreground">{t.result}</span>
                </li>
              ))}
            </ol>
          )}
          <div className="mt-3 text-xs">
            <b>Guardrails fired:</b>{" "}
            {guardrails.length ? (
              <ul className="mt-1 space-y-1">
                {guardrails.map((g) => (
                  <li key={g}>
                    {guardrailLabel(g)}
                    {g in GUARDRAIL_LABELS ? <span className="font-mono text-muted-foreground"> ({g})</span> : null}
                  </li>
                ))}
              </ul>
            ) : (
              "none"
            )}
          </div>
        </CardContent>
      </Card>
    </aside>
  );
}
