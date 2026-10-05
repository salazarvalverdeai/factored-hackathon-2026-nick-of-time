import { DEMO_TODAY, daysBetween } from "@/lib/mock/store";
import type { Deadline } from "@/lib/types";

/** "2026-06-05 · 2 days left", or "pending" while the policy engine (spec 02) cannot give a date. Demo date is frozen (ADR 0012). */
export function formatDeadline(d: Pick<Deadline, "creditDeadline">): string {
  if (!d.creditDeadline) return "pending";
  const left = daysBetween(DEMO_TODAY, d.creditDeadline);
  return `${d.creditDeadline} · ${left} day${left === 1 ? "" : "s"} left`;
}
