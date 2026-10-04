import { StatusBadge } from "@/components/badges";
import { cn } from "@/lib/utils";
import type { CaseEvent } from "@/lib/types";

const LABEL: Record<CaseEvent["type"], string> = {
  case_opened: "Case opened",
  card_blocked: "Card blocked",
  verification_started: "Verification started",
  sent_to_review: "Sent to review",
  credit_approved: "Credit approved",
  case_closed: "Case closed",
  call_requested: "Call requested",
  customer_info_added: "Customer added information",
  telegram_linked: "Telegram linked",
  email_confirmed: "E-mail confirmed",
};

/** Vertical timeline of case events, oldest first. A case's status is its last event, so the last row is "now". */
export function Timeline({ events, className }: { events: CaseEvent[]; className?: string }) {
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
            <span className="font-medium">{LABEL[e.type]}</span>
            <StatusBadge status={e.status} />
          </div>
          <p className="text-xs text-muted-foreground">
            {new Date(e.at).toLocaleString()} · {e.actor}
            {e.reason ? ` · ${e.reason}` : ""}
          </p>
        </li>
      ))}
    </ol>
  );
}
