import { type Locale, translator } from "@/lib/i18n";
import { DEMO_TODAY, daysBetween } from "@/lib/mock/store";
import type { Deadline } from "@/lib/types";

/** "2026-06-05 · 2 days left", or "pending" while there is no date, in the UI language (spec 16 AC-06). The mock counts
 *  from the frozen demo date (ADR 0012); the live api sends its own count (`daysLeft`), or null when it has none, and
 *  then only the date is shown. The date itself stays as the tool returned it. */
export function formatDeadline(d: Pick<Deadline, "creditDeadline" | "daysLeft">, locale: Locale = "en"): string {
  const t = translator(locale);
  if (!d.creditDeadline) return t("ui.deadline.pending");
  const left = d.daysLeft === undefined ? daysBetween(DEMO_TODAY, d.creditDeadline) : d.daysLeft;
  if (left === null) return d.creditDeadline;
  const vars = { date: d.creditDeadline, n: left };
  return left === 1 ? t("ui.deadline.withLeft.one", vars) : t("ui.deadline.withLeft.other", vars);
}
