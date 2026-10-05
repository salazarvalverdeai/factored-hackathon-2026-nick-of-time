import { DEMO_TODAY, daysBetween } from "@/lib/mock/store";
import type { Deadline } from "@/lib/types";

/** "2026-06-05 · 2 days left", or "pending" while there is no date. The mock counts from the frozen demo date (ADR 0012);
 *  the live api sends its own count (`daysLeft`), or null when it has none, and then only the date is shown. */
export function formatDeadline(d: Pick<Deadline, "creditDeadline" | "daysLeft">): string {
  if (!d.creditDeadline) return "pending";
  const left = d.daysLeft === undefined ? daysBetween(DEMO_TODAY, d.creditDeadline) : d.daysLeft;
  if (left === null) return d.creditDeadline;
  return `${d.creditDeadline} · ${left} day${left === 1 ? "" : "s"} left`;
}
