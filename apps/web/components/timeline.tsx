"use client";

import type { ReactNode } from "react";
import { useLocale } from "@/components/i18n-provider";
import { formatDateTime } from "@/lib/handoff-labels";
import { cn } from "@/lib/utils";
import { ui } from "@/messages/ui";

export interface TimelineEvent {
  id: string;
  at: string; // ISO timestamp
  /** Mock event types, or the live store's (shown as words when there is no label). */
  type: string;
  /** The status after this event: a StatusBadge for analysts, the localized status label for customers. */
  badge: ReactNode;
  /** Small print under the title: the analyst sees "actor · reason", the customer sees nothing internal. */
  meta?: string;
}

/** Vertical timeline of case events, oldest first. A case's status is its last event, so the last row is "now".
 *  Event names and dates follow the UI language (spec 16 AC-06); 24 h clock. */
export function Timeline({ events, className }: { events: TimelineEvent[]; className?: string }) {
  const { locale } = useLocale();
  const labels: Record<string, string> = ui[locale].timeline;
  return (
    <ol data-slot="timeline" className={cn("relative space-y-4 border-l pl-5", className)}>
      {events.map((e, i) => (
        <li key={e.id} className="relative">
          <span
            aria-hidden
            className={cn(
              "absolute -left-[1.6rem] top-1 size-2.5 rounded-full border bg-background",
              i === events.length - 1 && "border-foreground bg-foreground",
            )}
          />
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{labels[e.type] ?? e.type.replaceAll("_", " ")}</span>
            {e.badge}
          </div>
          <p className="text-xs text-muted-foreground">
            {formatDateTime(locale, e.at)}
            {e.meta ? ` · ${e.meta}` : ""}
          </p>
        </li>
      ))}
    </ol>
  );
}
