"use client";

// The console's KPI strip, SLA light and Closed list (spec 08 AC-07 to AC-09). The figures come from lib/console-metrics.ts;
// this file only draws them. Color is never the only signal: every light and outcome carries an icon and its text.
import { CircleCheck, CircleDashed, Clock, Info, OctagonAlert, TriangleAlert, UserRound } from "lucide-react";
import { useId, type ReactNode } from "react";
import { StatusBadge } from "@/components/badges";
import { useLocale, useT } from "@/components/i18n-provider";
import { EmptyState } from "@/components/states";
import {
  AT_RISK_DAYS,
  type BoardCase,
  type ClosedRow,
  type DeadlineOutcome,
  type Sla,
  type SlaLevel,
  closedRows,
  definitions,
  formatDuration,
  kpis,
} from "@/lib/console-metrics";
import { cn } from "@/lib/utils";

const PILL = "inline-flex w-fit shrink-0 items-center gap-1 rounded-4xl px-2 py-0.5 text-xs font-medium";

/** A definition that opens on hover and on keyboard focus; screen readers get it as the button's description. */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const t = useT();
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={t("console.board.definitionOf", { label })}
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
  const t = useT();
  const { locale } = useLocale();
  const k = kpis(board);
  const defs = definitions(locale);
  return (
    <section aria-label={t("console.board.kpiAria")} className="mb-4 space-y-1">
      <div className="grid gap-3 sm:grid-cols-3">
        <Kpi
          title={t("console.board.open")}
          value={String(k.open)}
          detail={t("console.board.openDetail", { n: k.openWithoutDeadline })}
          definition={defs.open}
        />
        <Kpi
          title={t("console.board.atRisk")}
          value={String(k.atRisk)}
          detail={t("console.board.atRiskDetail", { open: k.open, days: AT_RISK_DAYS })}
          definition={defs.atRisk}
        />
        <Kpi
          title={t("console.board.toVerification")}
          value={formatDuration(k.medianToVerificationMs, locale)}
          detail={
            k.verifiedCases
              ? t(k.verifiedCases === 1 ? "console.board.medianOf.one" : "console.board.medianOf.other", { n: k.verifiedCases })
              : t("console.board.noVerified")
          }
          definition={defs.toVerification}
        />
      </div>
      <p className="text-xs text-muted-foreground">{defs.label}</p>
    </section>
  );
}

const MET: Record<DeadlineOutcome, { icon: typeof Clock; className: string }> = {
  met: { icon: CircleCheck, className: "bg-brand-teal/15 text-teal-700 dark:text-teal-300" },
  missed: { icon: OctagonAlert, className: "bg-red-500/15 text-red-700 dark:text-red-400" },
  none: { icon: UserRound, className: "bg-muted text-muted-foreground" },
  unknown: { icon: CircleDashed, className: "bg-muted text-muted-foreground" },
};

function DeadlineMet({ row }: { row: ClosedRow }) {
  const t = useT();
  const m = MET[row.deadline];
  const Icon = m.icon;
  return (
    <span data-slot="deadline-met" data-outcome={row.deadline} className={cn(PILL, m.className)}>
      <Icon aria-hidden className="size-3.5" />
      {t(`console.board.met.${row.deadline}`)}
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
  const t = useT();
  const { locale } = useLocale();
  const rows = closedRows(board);
  if (rows.length === 0) return <EmptyState title={t("console.board.closedEmpty")} />;
  return (
    <ul className="space-y-1" aria-label={t("console.board.closedAria")}>
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
              {t(`console.board.outcome.${r.outcome}`)}
              {r.decidedBy ? ` · ${t("console.board.by", { name: r.decidedBy })}` : ""} ·{" "}
              {r.timeToCloseMs !== null
                ? t("console.board.closedIn", { duration: formatDuration(r.timeToCloseMs, locale) })
                : t("console.board.waiting")}
            </span>
            <DeadlineMet row={r} />
          </button>
        </li>
      ))}
    </ul>
  );
}
