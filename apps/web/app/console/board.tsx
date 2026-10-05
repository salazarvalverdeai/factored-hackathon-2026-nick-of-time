"use client";

// The console's KPI strip, SLA light and Closed list (spec 08 AC-07 to AC-09). The figures come from lib/console-metrics.ts;
// this file only draws them. Color is never the only signal: every light and outcome carries an icon and its text.
import { CircleCheck, CircleDashed, Clock, Info, OctagonAlert, TriangleAlert, UserRound } from "lucide-react";
import { useId, type ReactNode } from "react";
import { StatusBadge } from "@/components/badges";
import { EmptyState } from "@/components/states";
import {
  AT_RISK_DAYS,
  type BoardCase,
  type ClosedRow,
  DEFINITIONS,
  type DeadlineOutcome,
  type Sla,
  type SlaLevel,
  closedRows,
  formatDuration,
  kpis,
} from "@/lib/console-metrics";
import { cn } from "@/lib/utils";

const PILL = "inline-flex w-fit shrink-0 items-center gap-1 rounded-4xl px-2 py-0.5 text-xs font-medium";

/** A definition that opens on hover and on keyboard focus; screen readers get it as the button's description. */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={`Definition: ${label}`}
        aria-describedby={id}
        className="rounded-full text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Info aria-hidden className="size-3.5" />
      </button>
      <span
        id={id}
        role="tooltip"
        className="pointer-events-none invisible absolute top-full left-1/2 z-20 mt-1 w-64 max-w-[80vw] -translate-x-1/2 rounded-lg border bg-popover p-2 text-left text-xs font-normal normal-case tracking-normal text-popover-foreground opacity-0 transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
      >
        {children}
      </span>
    </span>
  );
}

const LIGHT: Record<SlaLevel, { icon: typeof Clock; className: string }> = {
  green: { icon: CircleCheck, className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" },
  amber: { icon: TriangleAlert, className: "bg-amber-500/15 text-amber-700 dark:text-amber-400" },
  red: { icon: OctagonAlert, className: "bg-red-500/15 text-red-700 dark:text-red-400" },
  none: { icon: UserRound, className: "bg-muted text-muted-foreground" },
  unknown: { icon: CircleDashed, className: "bg-muted text-muted-foreground" },
};

/** Time left to the legal deadline as a traffic light, with its icon and text (spec 08 AC-08). */
export function SlaLight({ sla, className }: { sla: Sla; className?: string }) {
  const l = LIGHT[sla.level];
  const Icon = l.icon;
  return (
    <span data-slot="sla-light" data-level={sla.level} className={cn(PILL, l.className, className)}>
      <Icon aria-hidden className="size-3.5" />
      {sla.label}
    </span>
  );
}

function Kpi({ title, value, detail, definition }: { title: string; value: string; detail: string; definition: string }) {
  return (
    <div className="rounded-xl border bg-card p-3 text-card-foreground">
      <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
        <InfoTip label={title}>{definition}</InfoTip>
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}

/** Open cases, deadlines at risk and the median time to verification (spec 08 AC-07). */
export function KpiStrip({ board }: { board: BoardCase[] }) {
  const k = kpis(board);
  return (
    <section aria-label="Key figures" className="mb-4 space-y-1">
      <div className="grid gap-3 sm:grid-cols-3">
        <Kpi
          title="Open cases"
          value={String(k.open)}
          detail={`${k.openWithoutDeadline} without a legal deadline · a person decides`}
          definition={DEFINITIONS.open}
        />
        <Kpi
          title="Deadlines at risk"
          value={String(k.atRisk)}
          detail={`of ${k.open} open · ${AT_RISK_DAYS} days or less, or past`}
          definition={DEFINITIONS.atRisk}
        />
        <Kpi
          title="Time to verification"
          value={formatDuration(k.medianToVerificationMs)}
          detail={k.verifiedCases ? `median of ${k.verifiedCases} verified case${k.verifiedCases === 1 ? "" : "s"}` : "no verified action yet"}
          definition={DEFINITIONS.toVerification}
        />
      </div>
      <p className="text-xs text-muted-foreground">{DEFINITIONS.label}</p>
    </section>
  );
}

const MET: Record<DeadlineOutcome, { label: string; icon: typeof Clock; className: string }> = {
  met: { label: "Deadline met", icon: CircleCheck, className: "bg-brand-teal/15 text-teal-700 dark:text-teal-300" },
  missed: { label: "Deadline missed", icon: OctagonAlert, className: "bg-red-500/15 text-red-700 dark:text-red-400" },
  none: { label: "No legal deadline", icon: UserRound, className: "bg-muted text-muted-foreground" },
  unknown: { label: "Deadline not measurable", icon: CircleDashed, className: "bg-muted text-muted-foreground" },
};

function DeadlineMet({ row }: { row: ClosedRow }) {
  const m = MET[row.deadline];
  const Icon = m.icon;
  return (
    <span data-slot="deadline-met" data-outcome={row.deadline} className={cn(PILL, m.className)}>
      <Icon aria-hidden className="size-3.5" />
      {m.label}
      {row.legalDeadline && row.deadline !== "none" ? <span className="font-normal">· {row.legalDeadline}</span> : null}
    </span>
  );
}

/** Resolved and closed cases with outcome, time to close and whether the legal deadline was met (spec 08 AC-09). */
export function ClosedList({
  board,
  activeId,
  onSelect,
}: {
  board: BoardCase[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const rows = closedRows(board);
  if (rows.length === 0) return <EmptyState title="No resolved or closed cases yet" />;
  return (
    <ul className="space-y-1" aria-label="Resolved and closed cases">
      {rows.map((r) => (
        <li key={r.id}>
          <button
            type="button"
            onClick={() => onSelect(r.id)}
            aria-current={activeId === r.id}
            className="w-full space-y-1 rounded-lg border p-2 text-left text-sm hover:bg-accent aria-[current=true]:border-foreground"
          >
            <span className="flex items-center justify-between gap-2">
              <span className="font-mono text-xs">{r.id}</span>
              <StatusBadge status={r.status} />
            </span>
            <span className="block truncate">{r.customerName}</span>
            <span className="block text-xs text-muted-foreground">
              {r.outcome}
              {r.decidedBy ? ` · by ${r.decidedBy}` : ""} ·{" "}
              {r.timeToCloseMs !== null ? `closed in ${formatDuration(r.timeToCloseMs)}` : "waiting for a person to close it"}
            </span>
            <DeadlineMet row={r} />
          </button>
        </li>
      ))}
    </ul>
  );
}
