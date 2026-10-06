"use client";

import { useT } from "@/components/i18n-provider";
import { cn } from "@/lib/utils";
import type { CaseStatus, Zone } from "@/lib/types";

const BASE = "inline-flex h-5 w-fit shrink-0 items-center gap-1 rounded-4xl px-2 text-xs font-medium whitespace-nowrap";

// Zone colors are a fixed convention for the whole product: high green, medium amber, human red.
// The text label always accompanies the color, so the meaning never depends on color alone; it follows the UI language.
const ZONE: Record<Zone, string> = {
  high: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  medium: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  human: "bg-red-500/15 text-red-700 dark:text-red-400",
};

export function ZoneBadge({ zone, className }: { zone: Zone; className?: string }) {
  const t = useT();
  return (
    <span data-slot="zone-badge" data-zone={zone} className={cn(BASE, ZONE[zone], className)}>
      {t(`ui.zone.${zone}`)}
    </span>
  );
}

const STATUS: Record<CaseStatus, string> = {
  new: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  verification: "bg-violet-500/15 text-violet-700 dark:text-violet-400",
  review: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  resolved: "bg-brand-teal/15 text-teal-700 dark:text-teal-300",
  closed: "bg-muted text-muted-foreground",
};

export function StatusBadge({ status, className }: { status: CaseStatus; className?: string }) {
  const t = useT();
  return (
    <span data-slot="status-badge" data-status={status} className={cn(BASE, STATUS[status], className)}>
      {t(`ui.status.${status}`)}
    </span>
  );
}
