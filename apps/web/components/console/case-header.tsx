"use client";

// The case header of the assisted console: id, customer, zone, priority, the status stepper and the SLA countdown.
// The stepper says each step's state in words as well as by its mark (never color alone, spec 08 AC-08), in the UI
// language (spec 16 AC-06).
import { Check } from "lucide-react";
import type { ReactNode } from "react";
import { StatusBadge, ZoneBadge } from "@/components/badges";
import { useLocale, useT } from "@/components/i18n-provider";
import { Badge } from "@/components/ui/badge";
import { stepperSteps } from "@/lib/console-view";
import type { CaseStatus, Priority, Zone } from "@/lib/types";
import { cn } from "@/lib/utils";

export function StatusStepper({ status, path }: { status: CaseStatus; path?: { verification?: boolean; review?: boolean } }) {
  const t = useT();
  const { locale } = useLocale();
  const steps = stepperSteps(status, locale, path);
  return (
    <ol aria-label={t("console.header.stepperAria")} className="grid grid-cols-4 gap-1" data-slot="status-stepper">
      {steps.map((s, i) => (
        <li
          key={s.key}
          aria-current={s.state === "current" ? "step" : undefined}
          data-state={s.state}
          className="flex min-w-0 flex-col gap-1"
        >
          <span
            aria-hidden
            className={cn(
              "h-1 rounded-full",
              s.state === "done" && "bg-brand-teal",
              s.state === "current" && "bg-brand-violet",
              s.state === "upcoming" && "bg-muted",
            )}
          />
          <span
            className={cn(
              "flex min-w-0 items-center gap-1 text-xs",
              s.state === "upcoming" ? "text-muted-foreground" : "text-foreground",
              s.state === "current" && "font-semibold",
            )}
          >
            {s.state === "done" ? <Check aria-hidden className="size-3 shrink-0 text-brand-teal" /> : <span aria-hidden className="hidden tabular-nums text-muted-foreground sm:inline">{i + 1}</span>}
            <span className="min-w-0 break-words leading-tight">{s.label}</span>
            <span className="sr-only">, {t(`console.header.state.${s.state}`)}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

export function CaseHeader({
  id,
  customerName,
  zone,
  priority,
  status,
  path,
  sla,
}: {
  id: string;
  customerName: string;
  zone: Zone;
  priority: Priority;
  status: CaseStatus;
  path?: { verification?: boolean; review?: boolean };
  /** The SLA light of the inbox for this case (time left to the nearest legal deadline). */
  sla: ReactNode;
}) {
  const t = useT();
  return (
    <header className="space-y-3" data-slot="case-header">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-mono text-base font-semibold">{id}</h2>
        <ZoneBadge zone={zone} />
        <StatusBadge status={status} />
        {priority === "high" ? (
          <Badge variant="outline" className="border-brand-amber/50">{t("console.header.highPriority")}</Badge>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 truncate text-sm text-muted-foreground">{customerName}</p>
        {sla}
      </div>
      <StatusStepper status={status} path={path} />
    </header>
  );
}
